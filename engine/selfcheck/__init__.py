"""The self-check: the product's own checks, run before finishing any change (`python -m engine.selfcheck`)."""

from __future__ import annotations

import shutil
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


def check_workspace_fixture(ws_root: Path, *, plugins: bool = True) -> list[Finding]:
    """A fictional workspace's config validates, its data imports, its references resolve and it round-trips."""
    name = ws_root.name
    findings: list[Finding] = []
    try:
        cfg = load_config(ws_root / "config", env={})
        if not plugins:
            cfg.workspace.plugins.enabled = []
            cfg.stages.types = {kind: value for kind, value in cfg.stages.types.items() if "/" not in kind}
    except ConfigError as err:
        return [Finding("fixture", f"workspaces/{name}/config", 0, str(err))]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shutil.copytree(ws_root / "config", tmp_path / "config")
        data = tmp_path / "data"
        shutil.copytree(ws_root / "data", data)
        if not plugins:
            for path in data.iterdir():
                if path.is_dir():
                    shutil.rmtree(path)
        try:
            first = Store(tmp_path / "a.db", cfg=cfg)
            failures = [s for s in first.plugins.status.values() if s.state != "enabled"]
            if failures:
                first.close()
                return [Finding("plugin", name, 0, str(s.reason)) for s in failures]
            import_data(first, data)
            findings += _check_references(first, name)
            export_data(first, tmp_path / "export-1")
            first.close()
            second = Store(tmp_path / "b.db", cfg=cfg)
            import_data(second, tmp_path / "export-1")
            export_data(second, tmp_path / "export-2")
            second.close()
        except StoreError as err:
            return [Finding("fixture", f"workspaces/{name}/data", 0, str(err))]

        def contents(folder: Path) -> dict[str, bytes]:
            return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}

        if contents(tmp_path / "export-1") != contents(tmp_path / "export-2"):
            findings.append(Finding("roundtrip", f"workspaces/{name}/data", 0, "export round trip differs"))
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
    checks += [(f"core alone {ws.name}", lambda ws=ws: check_workspace_fixture(ws, plugins=False)) for ws in FIXTURES]
    checks.append(("bundled manifests", check_manifests))
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


def check_manifests() -> list[Finding]:
    from engine.plugin_host import BUNDLED
    from engine.plugin_manifest import read_manifest

    findings = []
    for path in sorted(BUNDLED.glob("*/plugin.yaml")):
        try:
            read_manifest(path)
        except Exception as err:
            findings.append(Finding("manifest", str(path.relative_to(REPO)), 0, str(err)))
    if not findings:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(None, env={})
            cfg.workspace.plugins.enabled = [path.parent.name for path in sorted(BUNDLED.glob("*/plugin.yaml"))]
            store = Store(Path(tmp) / "check.db", cfg=cfg)
            try:
                for status in store.plugins.status.values():
                    if status.state != "enabled":
                        findings.append(Finding("manifest", status.name, 0, status.reason or "load failed"))
            finally:
                store.close()
    return findings
