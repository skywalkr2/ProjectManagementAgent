"""Plugin contracts, isolation, failure containment and the real applier path."""

import json
import shutil
from dataclasses import replace
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.applier import Context, Inputs, apply_changeset, check, release, undo
from engine.config import load_config
from engine.dispatcher import parse, process
from engine.intake import hand_in
from engine.names import People
from engine.plugin_api import ReadView
from engine.plugin_host import BUNDLED
from engine.plugin_manifest import Manifest, read_manifest
from engine.storage import Store, StoreError, WriteContext
from engine.storage.export import export_data, import_data
from engine.workspace import init_workspace

EXAMPLE = read_manifest(BUNDLED / "example" / "plugin.yaml")
KIND = EXAMPLE.provides.record_types[0]
OP = EXAMPLE.provides.ops[0]
TASK = EXAMPLE.provides.ai_task_kinds[0]
WRITE = WriteContext(actor="pm", trust="trusted", op="test")


def make_plugin(tmp_path, *, name="scratch", edits=None, source=None):
    root = tmp_path / "plugins" / name
    root.mkdir(parents=True)
    raw = yaml.safe_load((BUNDLED / "example/plugin.yaml").read_text().replace("example", name))
    if edits:
        edits(raw)
    (root / "plugin.yaml").write_text(yaml.safe_dump(raw))
    code = (BUNDLED / "example/__init__.py").read_text().replace("example", name)
    (root / "__init__.py").write_text(source if source is not None else code)
    return root


def config(root, names):
    cfg = load_config(root / "config", env={})
    cfg.workspace.plugins.enabled = names
    cfg.stages.types = {
        kind: value for kind, value in cfg.stages.types.items() if "/" not in kind or kind.split("/")[0] in names
    }
    return cfg


def context(ws, store, *, origin="pm", trust="trusted"):
    req = hand_in(ws, store, note="Capture a reminder").request
    if origin != "pm":
        with store.transaction() as tx:
            r = tx.get("request", req)
            tx.update("request", req, {"origin": origin}, WRITE, read_version=r.version)
    return Context(
        store,
        ws.config(env={}),
        People(store, ws.config(env={})),
        (OP, "note"),
        Inputs(req, None, "", "Capture a reminder", trust),
    )


def changeset(store, text="A new reminder"):
    return parse(json.dumps({"ops": [{"op": OP, "text": text}]}), store.plugins.ops)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(typo=True),
        lambda d: d["requires"].update(typo=True),
        lambda d: d["provides"].update(typo=[]),
        lambda d: d.update(plugin_api="not a range"),
        lambda d: d.update(version="not a version"),
        lambda d: d["provides"].update(ops=["wrong/add"]),
    ],
)
def test_invalid_manifests_are_refused(mutate):
    raw = EXAMPLE.model_dump()
    mutate(raw)
    with pytest.raises((ValidationError, ValueError)):
        Manifest.model_validate(raw)


@pytest.mark.parametrize(
    "edits,reason",
    [
        (lambda d: d.update(plugin_api=">=2"), "plugin API"),
        (lambda d: d.update(depends_on=[{"name": "missing", "version": ">=1"}]), "not enabled"),
        (lambda d: d["provides"].update(ops=[]), "does not match"),
        (lambda d: d.update(subscribes=[]), "handlers do not match"),
        (lambda d: d["provides"].update(playbook="playbook"), "not available"),
    ],
)
def test_load_refusals_are_atomic(tmp_path, edits, reason):
    make_plugin(tmp_path, edits=edits)
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    try:
        assert store.plugins.status["scratch"].state == "disabled"
        assert reason in store.plugins.status["scratch"].reason
        assert not any(k.startswith("scratch/") for k in store.plugins.records)
    finally:
        store.close()


def test_version_checked_before_import_and_disabled_plugins_never_import(tmp_path):
    make_plugin(tmp_path, edits=lambda d: d.update(plugin_api=">=2"), source="raise RuntimeError('imported')")
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    assert "plugin API" in store.plugins.status["scratch"].reason
    store.close()
    store = Store(tmp_path / "other", cfg=config(tmp_path, []))
    assert store.plugins.status == {}
    store.close()


def test_dependency_versions_and_cycles(tmp_path):
    make_plugin(tmp_path, name="first", edits=lambda d: d.update(depends_on=[{"name": "second", "version": ">=2"}]))
    make_plugin(tmp_path, name="second")
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["first", "second"]))
    assert "does not satisfy" in store.plugins.status["first"].reason
    assert store.plugins.active("second")
    store.close()
    path = tmp_path / "plugins/second/plugin.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["depends_on"] = [{"name": "first", "version": ">=0"}]
    path.write_text(yaml.safe_dump(raw))
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["first", "second"]))
    assert all(s.state == "disabled" for s in store.plugins.status.values())
    store.close()


def test_private_and_installed_discovery(tmp_path, monkeypatch):
    root = make_plugin(tmp_path)
    cfg = config(tmp_path, ["scratch"])
    store = Store(tmp_path / "db", cfg=cfg)
    assert store.plugins.active("scratch")
    store.close()
    installed = tmp_path / "installed/scratch"
    installed.parent.mkdir()
    shutil.move(root, installed)
    ep = SimpleNamespace(
        name="scratch", value="scratch:register", dist=SimpleNamespace(locate_file=lambda module: installed)
    )
    monkeypatch.setattr("engine.plugin_host.entry_points", lambda **kwargs: [ep])
    store = Store(tmp_path / "db", cfg=cfg)
    assert store.plugins.active("scratch")
    store.close()


def test_bad_config_and_load_crash_do_not_stop_core(tmp_path):
    root = make_plugin(tmp_path)
    config_dir = tmp_path / "config/plugins"
    config_dir.mkdir(parents=True)
    (config_dir / "scratch.yaml").write_text("unknown: true")
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    assert "Extra inputs" in store.plugins.status["scratch"].reason
    store.close()
    (config_dir / "scratch.yaml").unlink()
    (root / "__init__.py").write_text("raise RuntimeError('broken load')")
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    assert "broken load" in store.plugins.status["scratch"].reason
    with store.transaction() as tx:
        tx.create("note", {"text": "Core keeps running"}, WRITE)
    store.close()


def test_runtime_namespace_violation_refused(tmp_path):
    root = make_plugin(tmp_path)
    p = root / "__init__.py"
    p.write_text(p.read_text().replace('"scratch/reminder"', '"other/reminder"'))
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    assert "namespaced" in store.plugins.status["scratch"].reason
    assert "other/reminder" not in store.plugins.records
    store.close()


def test_plugin_op_applies_emits_and_undoes(workspace):
    store = Store(workspace.db_path)
    ctx = context(workspace, store)
    received = []
    registrar = store.plugins.registrars[EXAMPLE.name]
    original = registrar.handlers["record.changed"]

    def handler(event, context):
        received.append(event)
        original(event, context)

    registrar.handlers["record.changed"] = handler
    before = len(store.read().list("question"))
    cs = changeset(store)
    cs_id = apply_changeset(cs, check(cs, ctx), ctx, run=None)
    outcome = store.read().get("changeset", cs_id).data["ops"][0]
    assert outcome["status"] == "applied"
    rid = outcome["records"][0]["id"]
    assert len(store.read().list("question")) == before + 1
    event = next(e for e in received if e["kind"] == KIND and e["id"] == rid)
    assert event["version"] == 1 and "text" in event["fields"] and event["op"] == OP + "#0"
    ledger = store.read().ledger(kind=KIND, record_id=rid)
    assert ledger and all(e["changeset"] == cs_id for e in ledger)
    assert undo(store, cs_id).restored == [0]
    assert store.read().get(KIND, rid) is None
    store.close()


def test_validators_refuse_even_when_caller_passes_no_findings(workspace):
    store = Store(workspace.db_path)
    ctx = context(workspace, store)
    cs = changeset(store, store.read().list(KIND)[0].data["text"])
    cs_id = apply_changeset(cs, [], ctx, run=None)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "refused"
    store.close()


@pytest.mark.parametrize("origin,trust", [("input", "untrusted"), ("schedule", "trusted")])
def test_system_tier_is_held_until_confirmation(workspace, origin, trust):
    store = Store(workspace.db_path)
    ctx = context(workspace, store, origin=origin, trust=trust)
    store.plugins.tiers[OP] = "system"
    cs_id = apply_changeset(changeset(store), [], ctx, run=None)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "held"
    release(store, ctx.cfg, cs_id, 0)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "applied"
    store.close()


def test_crashing_handler_stages_nothing_and_disables_plugin(workspace):
    store = Store(workspace.db_path)
    registrar = store.plugins.registrars[EXAMPLE.name]
    before = len(store.read().list("question"))

    def crash(event, context):
        context.file_question("Never filed")
        raise RuntimeError("handler failed")

    registrar.handlers["record.changed"] = crash
    with store.transaction() as tx:
        record = tx.create("note", {"text": "Committed before handler"}, WRITE)
    assert store.read().get("note", record.id)
    assert len(store.read().list("question")) == before
    assert store.plugins.active(EXAMPLE.name)
    assert "event record.changed failed" in store.plugins.status[EXAMPLE.name].notes[-1]
    for _ in range(store.plugins.cfg.workspace.plugins.failures_before_off - 1):
        with store.transaction() as tx:
            tx.create("note", {"text": "Again"}, WRITE)
    assert not store.plugins.active(EXAMPLE.name)
    store.close()


def test_op_crash_rolls_back_writes_and_keeps_other_ops(workspace):
    store = Store(workspace.db_path)
    ctx = context(workspace, store)
    before = store.read().list(KIND)
    registration = store.plugins.registrars[EXAMPLE.name].ops[OP]

    def crash(op, writer, cfg):
        writer.create(KIND, {"text": "Must roll back"})
        raise RuntimeError("op failed")

    store.plugins.registrars[EXAMPLE.name].ops[OP] = replace(registration, apply=crash)
    cs = parse(
        json.dumps({"ops": [{"op": OP, "text": "x"}, {"op": "note", "text": "Still applies"}]}), store.plugins.ops
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    outcomes = store.read().get("changeset", cs_id).data["ops"]
    assert [o["status"] for o in outcomes] == ["refused", "applied"]
    assert store.read().list(KIND) == before
    assert not store.plugins.active(EXAMPLE.name)
    store.close()


def test_no_event_on_rollback_and_read_surface_has_no_writes(workspace):
    store = Store(workspace.db_path)
    received = []
    store.plugins.registrars[EXAMPLE.name].handlers["record.changed"] = lambda e, c: received.append(e)
    with pytest.raises(RuntimeError), store.transaction() as tx:
        tx.create("note", {"text": "Rollback"}, WRITE)
        raise RuntimeError()
    assert received == []
    view = ReadView(store.read(), EXAMPLE.name)
    assert not hasattr(view, "create") and not hasattr(view, "sql") and not hasattr(view, "update")
    with pytest.raises(StoreError):
        view.list("other/type")
    store.close()


def test_round_trip_preserves_plugin_records_ledger_and_versions(workspace, tmp_path):
    first = Store(workspace.db_path)
    ctx = context(workspace, first)
    apply_changeset(changeset(first), [], ctx, run=None)
    export_data(first, tmp_path / "e1")
    cfg = workspace.config(env={})
    second = Store(tmp_path / "second.db", cfg=cfg)
    import_data(second, tmp_path / "e1")
    export_data(second, tmp_path / "e2")

    def contents(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    assert contents(tmp_path / "e1") == contents(tmp_path / "e2")
    assert first.read().list(KIND) == second.read().list(KIND)
    assert first.read().ledger() == second.read().ledger()
    first.close()
    second.close()


def test_workspace_registries_do_not_leak(workspace, tmp_path):
    enabled = Store(workspace.db_path)
    disabled = Store(tmp_path / "empty.db", cfg=config(tmp_path, []))
    assert KIND in enabled.plugins.records and KIND not in disabled.plugins.records
    assert OP not in disabled.plugins.ops and TASK not in disabled.plugins.tasks
    with pytest.raises(Exception, match="unknown op"):
        changeset(disabled)
    enabled.close()
    disabled.close()


def test_api_reports_plugin_status(workspace):
    cfg = workspace.config(env={})
    app = create_app(workspace, cfg, "test")
    with TestClient(app) as client:
        prefix = "" if cfg.server.base_path == "/" else cfg.server.base_path
        result = client.get(prefix + "/api/plugins", headers={"Authorization": "Bearer test"})
        assert result.status_code == 200
        assert any(s["name"] == EXAMPLE.name and s["state"] == "enabled" for s in result.json())


@pytest.mark.parametrize("enabled", [False, True])
def test_core_pipeline_runs_with_and_without_plugins(tmp_path, demo, enabled):
    from engine.ai.adapters.stub import set_responder
    from engine.ai.router import Router

    template = tmp_path / "template"
    shutil.copytree(demo, template)
    if not enabled:
        p = template / "config/workspace.yaml"
        raw = yaml.safe_load(p.read_text())
        raw["plugins"]["enabled"] = []
        p.write_text(yaml.safe_dump(raw))
        p = template / "config/stages.yaml"
        stages = yaml.safe_load(p.read_text())
        stages["types"] = {kind: value for kind, value in stages["types"].items() if "/" not in kind}
        p.write_text(yaml.safe_dump(stages))
        for directory in (template / "data").iterdir():
            if directory.is_dir():
                shutil.rmtree(directory)
    ws = init_workspace(tmp_path / "core", template=template, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    set_responder(lambda task: '{"ops":[{"op":"note","text":"A core note"}]}')
    try:
        request = hand_in(ws, store, note="Record a note").request
        cs = process(ws, store, cfg, Router(cfg, store, env={}), request)
        assert store.read().get("changeset", cs).data["status"] == "applied"
        assert bool(store.plugins.registrars) == enabled
    finally:
        set_responder(None)
        store.close()


def test_all_named_events_and_queue_command(workspace):
    store = Store(workspace.db_path)
    registrar = store.plugins.registrars[EXAMPLE.name]
    seen = []
    for event in ("request.queued", "changeset.applied", "changeset.undone", "question.answered"):
        registrar.handlers[event] = lambda data, ctx, event=event: seen.append((event, data))
    ctx = context(workspace, store)
    cs_id = apply_changeset(changeset(store), [], ctx, run=None)
    question = store.read().list("question")[-1]
    with store.transaction() as tx:
        tx.update(
            "question", question.id, {"status": "answered", "answer": "Reviewed"}, WRITE, read_version=question.version
        )
    undo(store, cs_id)
    assert {event for event, _ in seen} == {
        "request.queued",
        "changeset.applied",
        "changeset.undone",
        "question.answered",
    }
    registrar.handlers["changeset.applied"] = lambda e, c: c.queue_request(TASK, "Capture another reminder")
    before = len(store.read().list("request"))
    store.plugins.publish("changeset.applied", {"id": cs_id})
    assert len(store.read().list("request")) == before + 1
    assert store.read().list("request")[-1].data["origin"] == "schedule"
    store.close()


def test_plugin_task_runs_through_dispatcher(workspace):
    from engine.ai.adapters.stub import set_responder
    from engine.ai.router import Router

    cfg = workspace.config(env={})
    store = Store(workspace.db_path)
    ctx = context(workspace, store)
    with store.transaction() as tx:
        req = tx.get("request", ctx.inputs.request)
        tx.update("request", req.id, {"task": TASK}, WRITE, read_version=req.version)
    observed = []

    def answer(task):
        observed.append(task)
        return json.dumps({"ops": [{"op": OP, "text": "Via the dispatcher"}]})

    set_responder(answer)
    try:
        cs = process(workspace, store, cfg, Router(cfg, store, env={}), req.id)
        assert store.read().get("changeset", cs).data["ops"][0]["status"] == "applied"
        assert observed[0].kind == TASK
        assert OP in json.dumps(observed[0].output_schema)
    finally:
        set_responder(None)
        store.close()


def test_write_scope_is_enforced_and_validator_crash_fails_closed(workspace):
    store = Store(workspace.db_path)
    ctx = context(workspace, store)
    registrar = store.plugins.registrars[EXAMPLE.name]

    def invalid_write(op, writer, cfg):
        writer.create("note", {"text": "Outside the op's write declaration"})

    registrar.ops[OP] = replace(registrar.ops[OP], apply=invalid_write)
    before = store.read().list("note")
    cs = apply_changeset(changeset(store), [], ctx, run=None)
    assert store.read().get("changeset", cs).data["ops"][0]["status"] == "refused"
    assert store.read().list("note") == before
    store.close()
    store = Store(workspace.db_path)
    ctx = context(workspace, store)

    def broken_validator(op, view):
        raise RuntimeError("Broken validator")

    store.plugins.registrars[EXAMPLE.name].validators["note"] = [broken_validator]
    cs = parse('{"ops":[{"op":"note","text":"Refuse this"}]}')
    result = apply_changeset(cs, [], ctx, run=None)
    assert store.read().get("changeset", result).data["ops"][0]["status"] == "refused"
    assert not store.plugins.active(EXAMPLE.name)
    # The crash refused the op it was checking; later core ops carry on without the disabled plugin.
    assert check(cs, ctx) == []
    store.close()


def test_disabled_records_survive_and_reenable(workspace, tmp_path):
    first = Store(workspace.db_path)
    records = first.read().list(KIND)
    first.close()
    cfg = workspace.config(env={})
    cfg.workspace.plugins.enabled = []
    cfg.stages.types = {kind: value for kind, value in cfg.stages.types.items() if "/" not in kind}
    disabled = Store(workspace.db_path, cfg=cfg)
    assert disabled.read().list(KIND) == records
    export_data(disabled, tmp_path / "export")
    assert (tmp_path / "export" / f"{KIND}.json").exists()
    disabled.close()
    enabled = Store(workspace.db_path)
    assert enabled.plugins.active(EXAMPLE.name)
    assert enabled.read().list(KIND) == records
    enabled.close()


def test_boundary_rejects_import_of_engine_internals(tmp_path):
    from engine.selfcheck.scans import scan_boundary

    root = make_plugin(tmp_path, source="from engine.storage import Store\n")
    findings = scan_boundary(root=tmp_path)
    assert any(f.path.endswith(str(root.relative_to(tmp_path) / "__init__.py")) for f in findings)


def test_invalid_changeset_shape_is_a_validation_failure():
    from engine.dispatcher import Unreadable

    with pytest.raises(Unreadable, match="ops must be a list"):
        parse('{"ops":null}')


def test_handler_cannot_smuggle_record_writes_as_commands(workspace):
    store = Store(workspace.db_path)
    before = store.read().list(KIND)

    def invalid_command(event, context):
        context.commands.append((KIND, {"text": "Must go through the applier"}))

    store.plugins.registrars[EXAMPLE.name].handlers["request.queued"] = invalid_command
    hand_in(workspace, store, note="Trigger the handler")
    assert store.read().list(KIND) == before
    assert not store.plugins.active(EXAMPLE.name)
    store.close()
