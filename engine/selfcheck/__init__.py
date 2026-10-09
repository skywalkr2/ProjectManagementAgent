"""The self-check: the product's own checks, run before finishing any change (`python -m engine.selfcheck`)."""

from __future__ import annotations

import filecmp
import tempfile
from collections.abc import Callable
from pathlib import Path

from engine.config import ConfigError, load_config
from engine.records import REFERENCES, values_at
from engine.selfcheck.scans import (
    REPO,
    Finding,
    scan_boundary,
    scan_config_coverage,
    scan_patterns,
    scan_providers,
    scan_specificity,
)
from engine.storage import Store, StoreError
from engine.storage.export import export_data, import_data

FIXTURES = (REPO / "workspaces" / "demo-a", REPO / "workspaces" / "demo-b")


def check_workspace_fixture(ws_root: Path) -> list[Finding]:
    """A fictional workspace's config validates, its data imports, its references resolve and it round-trips."""
    name = ws_root.name
    findings: list[Finding] = []
    try:
        load_config(ws_root / "config", env={})
    except ConfigError as err:
        return [Finding("fixture", f"workspaces/{name}/config", 0, str(err))]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            first = Store(tmp_path / "a.db")
            import_data(first, ws_root / "data")
            findings += _check_references(first, name)
            export_data(first, tmp_path / "export-1")
            first.close()
            second = Store(tmp_path / "b.db")
            import_data(second, tmp_path / "export-1")
            export_data(second, tmp_path / "export-2")
            second.close()
        except StoreError as err:
            return [Finding("fixture", f"workspaces/{name}/data", 0, str(err))]
        cmp = filecmp.dircmp(tmp_path / "export-1", tmp_path / "export-2")
        if cmp.left_only or cmp.right_only or cmp.diff_files:
            changed = sorted(cmp.left_only + cmp.right_only + cmp.diff_files)
            findings.append(
                Finding(
                    "roundtrip",
                    f"workspaces/{name}/data",
                    0,
                    f"export → import → export differs in {', '.join(changed)}",
                )
            )
    return findings


def _check_references(store: Store, name: str) -> list[Finding]:
    view = store.read()
    ids = {kind: {s.id for s in view.list(kind)} for kind in REFERENCES}
    findings = []
    for kind, refs in REFERENCES.items():
        for stored in view.list(kind):
            for field, target in refs:
                for value in values_at(stored.data, field):
                    if value is not None and value not in ids.get(target, set()):
                        findings.append(
                            Finding(
                                "fixture",
                                f"workspaces/{name}/data/{kind}.json",
                                0,
                                f"{stored.id}.{field} points to missing {target} {value}",
                            )
                        )
    return findings


def run(private_workspace: Path | None = None, *, out: Callable[[str], None] = print) -> int:
    checks: list[tuple[str, Callable[[], list[Finding]]]] = [
        ("specificity scan", lambda: scan_specificity(list(FIXTURES), private_workspace)),
        ("provider scan", lambda: scan_providers(_fixture_ai_names())),
        ("pattern scan", scan_patterns),
        ("boundary scan", scan_boundary),
        ("config coverage", scan_config_coverage),
    ]
    checks += [(f"workspace {ws.name}", lambda ws=ws: check_workspace_fixture(ws)) for ws in FIXTURES]
    checks.append(("api schema", check_api_schema))
    failed = 0
    for label, check in checks:
        findings = check()
        if findings:
            failed += 1
            out(f"FAIL  {label}")
            for f in findings:
                out(f"      {f}")
        else:
            out(f"ok    {label}")
    out("Self-check passed." if not failed else f"Self-check failed: {failed} of {len(checks)} checks.")
    return 1 if failed else 0


def check_api_schema() -> list[Finding]:
    """The committed OpenAPI schema, which the web client's types are generated from, matches the API."""
    from api.openapi import SCHEMA_PATH, build

    committed = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
    if committed != build():
        rel = SCHEMA_PATH.relative_to(REPO)
        return [Finding("api", str(rel), 0, "out of date; run `uv run python -m api.openapi`")]
    return []


def _fixture_ai_names() -> list[str]:
    """Adapter names and model ids from the fixtures' ai.yaml: these may appear only in adapters and config."""
    names: list[str] = []
    for ws in FIXTURES:
        try:
            cfg = load_config(ws / "config", env={})
        except ConfigError:
            continue
        for provider in cfg.ai.providers.values():
            if provider.adapter != "stub":
                names.append(provider.adapter)
            names += [m for m in provider.models.values() if m != "scripted"]
    return names
