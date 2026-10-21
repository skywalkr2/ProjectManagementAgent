"""The self-check: the product's own checks, run before finishing any change (`python -m engine.selfcheck`)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from engine.config import ConfigError, load_config
from engine.records import REFERENCES, values_at
from engine.selfcheck.built_claims import scan_built_claims
from engine.selfcheck.decisions import check_decisions
from engine.selfcheck.free_text import check_free_text
from engine.selfcheck.invariants import check_invariant_lines
from engine.selfcheck.scans import (
    REPO,
    Finding,
    scan_boundary,
    scan_config_coverage,
    scan_patterns,
    scan_providers,
    scan_specificity,
)
from engine.selfcheck.skills import check_skills_named
from engine.storage import Store, StoreError
from engine.storage.export import export_data, import_data
from engine.workspace import HISTORY

FIXTURES = (REPO / "workspaces" / "demo-a", REPO / "workspaces" / "demo-b")


def check_workspace_fixture(ws_root: Path, *, plugins: bool = True, history: bool = False) -> list[Finding]:
    """A fictional workspace's config validates, its data imports, its references resolve and it round-trips. With
    `history`, the data is the history the demo opens on (a full export with its ledger)."""
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
        shutil.copytree(ws_root / HISTORY / "data" if history else ws_root / "data", data)
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


def check_fresh_workspace() -> list[Finding]:
    """A workspace made with no template shows no problem: its settings load, the AI setup is simply not set up, no
    source or data file is in trouble, no setup step is stuck, and the kinds of source offered can be listed."""
    from engine import data_forms, setup, watch
    from engine.ai.smoke import ai_state
    from engine.settings import SettingsError, describe
    from engine.workspace import init_workspace

    findings: list[Finding] = []

    def found(message: str) -> None:
        findings.append(Finding("fresh", "engine/workspace.py", 0, f"a fresh workspace: {message}"))

    with tempfile.TemporaryDirectory() as tmp:
        try:
            ws = init_workspace(Path(tmp) / "fresh", git=False)
            cfg = ws.config(env={})
            store = Store(ws.db_path, cfg=cfg)
        except (ConfigError, StoreError, OSError) as err:
            return [Finding("fresh", "engine/workspace.py", 0, f"a workspace with no template can't be made: {err}")]
        try:
            try:
                describe(cfg, store.plugins, ws.config_dir)
            except (ConfigError, SettingsError) as err:
                found(f"the settings don't load: {err}")
            state, detail = ai_state(ws, cfg, store)
            if state != "not_set_up":
                found(f'the AI setup reads "{state}" ({detail or "no detail"}), not "not_set_up"')
            for source in cfg.watch.sources:
                last = watch.last_run(store, source.id)
                if last is not None and last.data["outcome"] == "failed":
                    found(f"the source {source.id} shows a problem")
            for plugin, registrar in sorted(store.plugins.registrars.items()):
                if not store.plugins.active(plugin):
                    continue
                for form in registrar.data_forms.values():
                    for entry in data_forms.files(store.plugins, form.name):
                        if entry["problem"]:
                            found(f"the data file {entry['file']} of {form.name} shows a problem: {entry['problem']}")
            steps = setup.steps(ws, cfg, store)
            if {step.id for step in steps} < set(setup.CORE_STEPS):
                found("a setup step is missing")
            for step in steps:
                if step.skipped:
                    found(f"the setup step {step.id} starts out skipped")
            if not watch.connectors(store):
                found("no kind of source is offered")
        finally:
            store.close()
    return findings


def _check_references(store: Store, name: str) -> list[Finding]:
    view = store.read()
    kinds = set(REFERENCES) | {target for refs in REFERENCES.values() for _, target in refs}
    ids = {kind: {s.id for s in view.list(kind)} for kind in kinds}
    findings = []
    for kind, refs in REFERENCES.items():
        # A path that may name more than one kind of record (a hold's blocker) is declared once for each kind, and the
        # value has to be found among them.
        targets: dict[str, list[str]] = {}
        for field, target in refs:
            targets.setdefault(field, []).append(target)
        for stored in view.list(kind):
            for field, kinds_named in targets.items():
                for value in values_at(stored.data, field):
                    if value is not None and not any(value in ids.get(target, set()) for target in kinds_named):
                        findings.append(
                            Finding(
                                "fixture",
                                f"workspaces/{name}/data/{kind}.json",
                                0,
                                f"{stored.id}.{field} points to missing {' or '.join(kinds_named)} {value}",
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
        ("built claims", scan_built_claims),
        ("decisions", check_decisions),
        ("invariant lines", check_invariant_lines),
        ("case skills", check_skills_named),
    ]
    checks += [(f"workspace {ws.name}", lambda ws=ws: check_workspace_fixture(ws)) for ws in FIXTURES]
    checks += [(f"demo history {ws.name}", lambda ws=ws: check_workspace_fixture(ws, history=True)) for ws in FIXTURES]
    checks += [(f"core alone {ws.name}", lambda ws=ws: check_workspace_fixture(ws, plugins=False)) for ws in FIXTURES]
    checks.append(("fresh workspace", check_fresh_workspace))
    checks.append(("bundled manifests", check_manifests))
    checks.append(("api schema", check_api_schema))
    checks.append(("free text", check_free_text))
    checks.append(("plugin guide", check_plugin_guide))
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


def check_plugin_guide() -> list[Finding]:
    """The committed plugin developer guide matches the plugin API it is generated from."""
    from engine.plugin_guide import GUIDE_PATH, build

    committed = GUIDE_PATH.read_text(encoding="utf-8") if GUIDE_PATH.exists() else ""
    if committed != build():
        rel = GUIDE_PATH.relative_to(REPO)
        return [Finding("guide", str(rel), 0, "out of date; run `uv run python -m engine.plugin_guide`")]
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
