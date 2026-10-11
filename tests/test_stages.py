import pytest
import yaml

from engine.config import ConfigError, load_config


def config(tmp_path, stages):
    (tmp_path / "stages.yaml").write_text(yaml.safe_dump(stages))
    return load_config(tmp_path, env={})


@pytest.mark.parametrize(
    "stages, message",
    [
        ({"missing": []}, "unknown record type missing"),
        ({"project": [{"id": "x", "label": "X"}, {"id": "x", "label": "X"}]}, "unique"),
        ({"project": [{"id": "x", "label": "X", "entry": ["missing"]}]}, "unknown entry check missing"),
        ({"project": [{"id": "x", "label": "X", "starts": ["missing"]}]}, "unknown task kind missing"),
        ({"moves": "assistant"}, "person"),
    ],
)
def test_invalid_config(tmp_path, stages, message):
    with pytest.raises(ConfigError, match=message):
        config(tmp_path, stages)


def test_order_wording_and_mode_override(tmp_path):
    cfg = config(
        tmp_path,
        {
            "moves": "rule",
            "project": {
                "moves": "person",
                "stages": [{"id": "draft", "label": "Draft"}, {"id": "ready", "label": "Ready", "starts": ["notes"]}],
            },
        },
    )
    assert cfg.stages.moves == "rule"
    assert cfg.stages.types["project"].moves == "person"
    assert [s.id for s in cfg.stages.types["project"].stages] == ["draft", "ready"]


@pytest.fixture
def stage_workspace(tmp_path):
    from engine.storage import Store, WriteContext

    root = tmp_path / "ws"
    plugin = root / "plugins" / "stage-test"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "stage-test",
                "version": "0.1.0",
                "plugin_api": ">=0.3,<0.4",
                "description": "Stage contract fixture",
                "entry": "fixture:register",
                "config_schema": "fixture:Config",
                "provides": {
                    "record_types": ["stage-test/item"],
                    "stage_checks": ["stage-test/ready"],
                    "stages": ["stage-test/item"],
                },
            }
        )
    )
    (plugin / "fixture.py").write_text("""
from typing import ClassVar
from engine.plugin_api import Record, Settings, StageCheckResult
class Config(Settings):
    pass
class Item(Record):
    record_kind: ClassVar[str] = "stage-test/item"
    prefix: ClassVar[str] = "STG"
    ready: bool = False
def ready(record, view, config):
    return StageCheckResult(record.data.get("ready", False), "ready" if record.data.get("ready") else "not ready")
def register(registrar):
    registrar.record_type(Item)
    registrar.stage_check("stage-test/ready", ready)
    registrar.stages(Item.record_kind, [
        {"id": "draft", "label": "Draft"},
        {"id": "ready", "label": "Ready", "entry": ["stage-test/ready"]},
    ])
""")
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "workspace.yaml").write_text("plugins:\n  enabled: [stage-test]\n")
    cfg = load_config(config_dir, env={})
    store = Store(root / "cockpit.db", cfg=cfg)
    with store.transaction() as tx:
        record = tx.create("stage-test/item", {}, WriteContext("pm", "trusted", "test"))
    yield store, cfg, record
    store.close()


def test_plugin_checks_and_default_stages(stage_workspace):
    from engine.stages import entry_check

    store, cfg, record = stage_workspace
    assert store.plugins.active("stage-test")
    assert [s.id for s in store.plugins.stages.types[record.kind].stages] == ["draft", "ready"]
    result = entry_check(store, "stage-test/ready", record)
    assert not result.passed and result.reason == "not ready"
    store.plugins.disable("stage-test", "test failure")
    assert not entry_check(store, "stage-test/ready", record).passed


def test_rule_entry_checks_never_interpret_prose(stage_workspace):
    from engine.config.schema import RulesFile
    from engine.stages import entry_check

    store, cfg, record = stage_workspace
    cfg.files["rules"] = RulesFile(
        rules=[
            {"id": "R-1", "text": "Be ready", "check": "stage-test/ready"},
            {"id": "R-2", "text": "Decide whether this is good"},
        ]
    )
    assert entry_check(store, "R-1", record).reason == "Be ready: not ready"
    assert not entry_check(store, "R-2", record).passed
    assert "deterministic" in entry_check(store, "R-2", record).reason


def test_workspace_replaces_or_removes_plugin_stages(stage_workspace):
    from engine.storage import Store

    store, cfg, record = stage_workspace
    config_dir = store.path.parent / "config"
    for override in ([{"id": "ready", "label": "Renamed"}], []):
        (config_dir / "stages.yaml").write_text(yaml.safe_dump({record.kind: override}))
        loaded = load_config(config_dir, env={})
        other = Store(store.path.parent / "other.db", cfg=loaded)
        actual = other.plugins.stages.types[record.kind].stages
        assert [s.model_dump() for s in actual] == [dict(entry=[], starts=[], description="", **s) for s in override]
        other.close()


def test_stage_check_registration_names_and_duplicates():
    from engine.plugin_api import Registrar, Settings

    reg = Registrar("test", Settings())
    with pytest.raises(ValueError, match="namespaced"):
        reg.stage_check("foreign/check", lambda: None)
    reg.stage_check("test/check", lambda: None)
    with pytest.raises(ValueError, match="duplicate"):
        reg.stage_check("test/check", lambda: None)


def test_check_crash_disables_plugin_and_fails_closed(stage_workspace):
    from engine.stages import entry_check

    store, cfg, record = stage_workspace

    def broken(*args):
        raise RuntimeError("test")

    store.plugins.stage_checks["stage-test/ready"] = ("stage-test", broken)
    assert not entry_check(store, "stage-test/ready", record).passed
    assert not store.plugins.active("stage-test")


def move_op(record, to):
    from engine.ops import StageMoveOp

    return StageMoveOp(record={"kind": record.kind, "id": record.id}, to=to, read_version=record.version)


def test_move_refuses_with_reasons_then_applies_and_undoes(stage_workspace):
    from engine.applier import move_stage, undo
    from engine.storage import StoreError, WriteContext

    store, cfg, record = stage_workspace
    with pytest.raises(StoreError, match="not ready"):
        move_stage(store, move_op(record, "ready"))
    assert store.read().list("changeset") == []
    with store.transaction() as tx:
        record = tx.update(
            record.kind, record.id, {"ready": True}, WriteContext("pm", "trusted", "test"), read_version=record.version
        )
    cs = move_stage(store, move_op(record, "ready"))
    assert store.read().get(record.kind, record.id).data["stage"] == "ready"
    assert undo(store, cs).restored == [0]
    assert store.read().get(record.kind, record.id).data["stage"] is None


@pytest.mark.parametrize("trust", ["trusted", "untrusted"])
def test_ai_stage_proposal_is_always_held(stage_workspace, trust):
    from engine.applier import Context, Inputs, apply_changeset, release
    from engine.names import People
    from engine.ops import ChangesetIn

    store, cfg, record = stage_workspace
    ctx = Context(store, cfg, People(store, cfg), ("stage.move",), Inputs("request", None, "", "", trust))
    cs = apply_changeset(ChangesetIn(ops=[move_op(record, "draft")]), [], ctx, run=None)
    assert store.read().get("changeset", cs).data["ops"][0]["status"] == "held"
    assert store.read().get(record.kind, record.id).data["stage"] is None
    release(store, cfg, cs, 0)
    assert store.read().get(record.kind, record.id).data["stage"] == "draft"
    entry = [e for e in store.read().ledger() if e["field"] == "stage" and e["after"] == "draft"][-1]
    assert entry["actor"] == "pm"


def test_release_rechecks_entry_conditions_and_version(stage_workspace):
    from engine.applier import Context, Inputs, apply_changeset, release
    from engine.names import People
    from engine.ops import ChangesetIn
    from engine.storage import StoreError, WriteContext

    store, cfg, record = stage_workspace
    ctx = Context(store, cfg, People(store, cfg), ("stage.move",), Inputs("request", None, "", "", "trusted"))
    cs = apply_changeset(ChangesetIn(ops=[move_op(record, "ready")]), [], ctx, run=None)
    with pytest.raises(StoreError, match="not ready"):
        release(store, cfg, cs, 0)
    with store.transaction() as tx:
        tx.update(
            record.kind, record.id, {"ready": True}, WriteContext("pm", "trusted", "test"), read_version=record.version
        )
    with pytest.raises(StoreError, match="changed since"):
        release(store, cfg, cs, 0)
    assert store.read().get(record.kind, record.id).data["stage"] is None


def test_worker_rule_moves_without_ai_and_records_rule_source(stage_workspace):
    from engine.storage import WriteContext
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    store.plugins.stages.moves = "rule"

    def no_ai():
        pytest.fail("stage checks must not use AI")

    worker = Worker(Workspace(store.path.parent), store, cfg, Events(), router_factory=no_ai)
    worker.run_pending()
    current = store.read().get(record.kind, record.id)
    assert current.data["stage"] == "draft"
    worker.run_pending()
    assert store.read().get(record.kind, record.id).data["stage"] == "draft"
    with store.transaction() as tx:
        tx.update(
            record.kind, record.id, {"ready": True}, WriteContext("pm", "trusted", "test"), read_version=current.version
        )
    worker.run_pending()
    assert store.read().get(record.kind, record.id).data["stage"] == "ready"
    ledger = [e for e in store.read().ledger() if e["field"] == "stage" and e["after"] == "ready"]
    assert ledger[-1]["actor"] == "rule"
    assert ledger[-1]["evidence"]["rule"].endswith("/ready")
    assert ledger[-1]["changeset"]


def test_person_override_and_restart_stop_rule_moves(stage_workspace):
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    store.plugins.stages.moves = "rule"
    settings = store.plugins.stages.types[record.kind]
    settings.moves = "person"
    worker = Worker(Workspace(store.path.parent), store, cfg, Events())
    worker.run_pending()
    assert store.read().get(record.kind, record.id).data["stage"] is None
    settings.moves = "rule"
    (store.path.parent / "config" / "stages.yaml").write_text("moves: person\n")
    worker.run_pending()
    assert worker.restart_needed
    assert store.read().get(record.kind, record.id).data["stage"] is None


def test_starts_wait_until_go_and_retry_cannot_bypass(stage_workspace):
    from engine.applier import move_stage
    from engine.dispatcher import process, retry
    from engine.stages import approve_stage_request
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    cs = move_stage(store, move_op(record, "draft"))
    request = next(r for r in store.read().list("request") if r.data.get("stage_start"))
    assert request.data["state"] == "needs_you"
    assert request.data["stage_start"]["changeset"] == cs
    ws = Workspace(store.path.parent)
    worker = Worker(ws, store, cfg, Events(), router_factory=lambda: pytest.fail("no AI before go"))
    assert worker.run_pending() == 0
    with pytest.raises(ValueError, match="explicit go"):
        retry(store, request.id)
    assert process(ws, store, cfg, None, request.id) is None
    request = store.read().get("request", request.id)
    approve_stage_request(store, request.id, request.version)
    granted = store.read().get("request", request.id)
    assert granted.data["state"] == "queued" and granted.data["approval"] == "granted"


def test_undo_cancels_unapproved_starts_atomically(stage_workspace):
    from engine.applier import move_stage, undo

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    cs = move_stage(store, move_op(record, "draft"))
    request = next(r for r in store.read().list("request") if r.data.get("stage_start"))
    assert undo(store, cs).restored == [0]
    assert store.read().get("request", request.id) is None
    assert store.read().get(record.kind, record.id).data["stage"] is None


def test_undo_wont_remove_an_approved_task(stage_workspace):
    from engine.applier import move_stage, undo
    from engine.stages import approve_stage_request

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    cs = move_stage(store, move_op(record, "draft"))
    request = next(r for r in store.read().list("request") if r.data.get("stage_start"))
    approve_stage_request(store, request.id, request.version)
    report = undo(store, cs)
    assert not report.restored and report.skipped
    assert store.read().get(record.kind, record.id).data["stage"] == "draft"


def test_stage_event_only_after_commit_including_undo(stage_workspace, monkeypatch):
    import json
    import sqlite3

    from engine.applier import move_stage, undo

    store, cfg, record = stage_workspace
    events = []

    def publish(event, payload):
        if event != "stage.moved":
            return
        with sqlite3.connect(store.path) as conn:
            data = conn.execute("SELECT data FROM records WHERE kind=? AND id=?", (record.kind, record.id)).fetchone()
        assert json.loads(data[0])["stage"] == payload["to"]
        events.append(payload)

    monkeypatch.setattr(store.plugins, "publish", publish)
    cs = move_stage(store, move_op(record, "draft"))
    assert len(events) == 1 and events[0]["from"] is None and events[0]["to"] == "draft"
    undo(store, cs)
    assert len(events) == 2 and events[1]["to"] is None and events[1]["op"] == "undo"


def test_stage_event_and_starts_rollback_together(stage_workspace, monkeypatch):
    from engine.stages import apply_move
    from engine.storage import WriteContext

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    events = []
    monkeypatch.setattr(store.plugins, "publish", lambda *args: events.append(args))
    before = store.read().ledger()
    with pytest.raises(RuntimeError), store.transaction() as tx:
        apply_move(store, tx, move_op(record, "draft"), WriteContext("pm", "trusted", "stage.move#0", "CS-1"))
        assert not events
        raise RuntimeError("force rollback")
    assert not events
    assert not store.read().list("request")
    assert store.read().ledger() == before
    assert store.read().get(record.kind, record.id).data["stage"] is None


@pytest.mark.parametrize("prefix", ["", "/admin"])
def test_record_stage_api_and_explicit_go(stage_workspace, prefix):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import build_router
    from engine.storage import WriteContext
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    ws = Workspace(store.path.parent)
    worker = Worker(ws, store, cfg, Events())
    app = FastAPI()
    app.include_router(build_router(ws, cfg, store, worker.events, worker), prefix=prefix)
    base = prefix + "/api"
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    with TestClient(app) as client:
        path = f"{base}/records/{record.id}"
        response = client.get(path, params={"kind": record.kind})
        assert response.status_code == 200
        stage = response.json()["stages"]
        assert stage["current"] is None and stage["next"]["id"] == "draft" and stage["ready"]
        # An item that is not in a stage yet can start one from Stages, but Today doesn't suggest it.
        assert not any(s["record"]["id"] == record.id for s in client.get(f"{base}/stages/ready").json())
        body = {"record": stage["record"], "to": "draft", "read_version": stage["version"]}
        moved = client.post(f"{base}/stages/move", json=body)
        assert moved.status_code == 200
        assert moved.json()["stages"]["current"] == "draft"
        history = client.get(f"{path}/stage-history", params={"kind": record.kind}).json()
        assert len(history) == 1 and history[0]["to_stage"] == "draft"
        assert client.get(path, params={"kind": record.kind}).json()["stage_history"] == history
        checks = moved.json()["stages"]["checks"]
        assert checks == [{"id": "stage-test/ready", "passed": False, "reason": "not ready"}]
        assert client.post(f"{base}/stages/move", json=body).status_code == 409
        assert not client.get(f"{base}/stages/ready").json()
        request = client.get(f"{base}/stages/requests").json()[0]
        assert request["approval"] == "required" and request["estimate_usd"] is None
        assert client.post(f"{base}/requests/{request['id']}/retry").status_code == 409
        go = client.post(f"{base}/requests/{request['id']}/go", json={"read_version": request["version"]})
        assert go.status_code == 200
        with store.transaction() as tx:
            latest = tx.get(record.kind, record.id)
            tx.update(
                record.kind,
                record.id,
                {"ready": True},
                WriteContext("pm", "trusted", "test"),
                read_version=latest.version,
            )
        assert client.get(f"{base}/stages/ready").json()[0]["checks"][0]["passed"]


def test_stages_and_ledger_history_round_trip(stage_workspace, tmp_path):
    from engine.applier import move_stage, undo
    from engine.stages import stage_history
    from engine.storage import Store
    from engine.storage.export import export_data, import_data

    store, cfg, record = stage_workspace
    cs = move_stage(store, move_op(record, "draft"))
    undo(store, cs)
    current = store.read().get(record.kind, record.id)
    move_stage(store, move_op(current, "draft"))
    history = stage_history(store, record.kind, record.id)
    assert [row["to_stage"] for row in history] == ["draft", None, "draft"]
    assert history[1]["op"] == "undo"
    export_data(store, tmp_path / "export1")
    other = Store(store.path.parent / "restored.db", cfg=cfg)
    try:
        import_data(other, tmp_path / "export1")
        assert stage_history(other, record.kind, record.id) == history
        assert other.read().get(record.kind, record.id).data["stage"] == "draft"
        export_data(other, tmp_path / "export2")

        def files(path):
            return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}

        assert files(tmp_path / "export1") == files(tmp_path / "export2")
    finally:
        other.close()


def test_example_stage_check_and_workspace_wording(workspace):
    from engine.applier import move_stage
    from engine.stages import record_status
    from engine.storage import Store

    cfg = workspace.config(env={})
    store = Store(workspace.db_path, cfg=cfg)
    try:
        kinds = [kind for kind in store.plugins.stages.types if "/" in kind]
        if not kinds:
            # The separate core-only fixture run intentionally removes plugin config and data.
            return
        record = store.read().list(kinds[0])[0]
        stages = cfg.stages.types[record.kind].stages
        move_stage(store, move_op(record, stages[0].id))
        status = record_status(store, store.read().get(record.kind, record.id))
        assert status["current_label"] == stages[0].label
        assert status["checks"][0]["passed"] and status["checks"][0]["reason"]
    finally:
        store.close()


def test_direct_move_obeys_plugin_validators(stage_workspace):
    from engine.applier import move_stage
    from engine.storage import StoreError

    store, cfg, record = stage_workspace
    store.plugins.registrars["stage-test"].validators["stage.move"] = [lambda op, view: ["blocked by validator"]]
    with pytest.raises(StoreError, match="blocked by validator"):
        move_stage(store, move_op(record, "draft"))
    assert store.read().get(record.kind, record.id).data["stage"] is None
    assert not store.read().list("changeset")


def test_disabled_plugin_records_cannot_move_even_without_checks(stage_workspace):
    from engine.applier import move_stage
    from engine.stages import record_status
    from engine.storage import StoreError

    store, cfg, record = stage_workspace
    store.plugins.disable("stage-test", "test")
    assert not record_status(store, record)["ready"]
    with pytest.raises(StoreError, match="disabled"):
        move_stage(store, move_op(record, "draft"))


def test_stage_task_packet_carries_record_context(stage_workspace):
    from datetime import date

    from engine.applier import move_stage
    from engine.packet import build
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    move_stage(store, move_op(record, "draft"))
    request = next(r for r in store.read().list("request") if r.data.get("stage_start"))
    packet = build(Workspace(store.path.parent), store, cfg, request.id, date.today())
    assert record.id in packet.task.request and '"stage": "draft"' in packet.task.request
    assert "<untrusted>" in packet.task.request


def test_rule_yaml_date_and_binding_validate_at_load(stage_workspace):
    store, cfg, record = stage_workspace
    path = store.path.parent / "config" / "rules.yaml"
    path.write_text("rules:\n  - id: R-1\n    text: Be ready\n    added: 2026-10-01\n    check: stage-test/ready\n")
    cfg = load_config(path.parent, env={})
    assert cfg.rules.rules[0].added.isoformat() == "2026-10-01"
    path.write_text("rules:\n  - id: R-1\n    check: missing\n")
    with pytest.raises(ConfigError, match="unknown code check missing"):
        load_config(path.parent, env={})


def _set_ready(store, record, value=True):
    from engine.storage import WriteContext

    current = store.read().get(record.kind, record.id)
    with store.transaction() as tx:
        return tx.update(
            record.kind,
            record.id,
            {"ready": value},
            WriteContext("pm", "trusted", "test"),
            read_version=current.version,
        )


def test_disabled_or_failing_plugin_never_stops_the_workspace(stage_workspace):
    from engine.storage import Store

    store, cfg, record = stage_workspace
    root = store.path.parent
    (root / "config" / "stages.yaml").write_text(yaml.safe_dump({record.kind: {"moves": "person"}}))
    # Turned off: its stages stay in config and the workspace still opens.
    (root / "config" / "workspace.yaml").write_text("plugins:\n  enabled: []\n")
    off = Store(root / "off.db", cfg=load_config(root / "config", env={}))
    off.close()
    # Enabled but failing to load: disabled for the run, workspace still opens.
    (root / "config" / "workspace.yaml").write_text("plugins:\n  enabled: [stage-test]\n")
    fixture = root / "plugins" / "stage-test" / "fixture.py"
    fixture.write_text(fixture.read_text() + "\ndef register(registrar):\n    raise RuntimeError('broken')\n")
    failing = Store(root / "failing.db", cfg=load_config(root / "config", env={}))
    assert not failing.plugins.active("stage-test")
    failing.close()


def test_override_without_stages_keeps_the_pack_stages(stage_workspace):
    from engine.storage import Store

    store, cfg, record = stage_workspace
    config_dir = store.path.parent / "config"
    (config_dir / "stages.yaml").write_text(yaml.safe_dump({record.kind: {"moves": "rule"}}))
    other = Store(store.path.parent / "other.db", cfg=load_config(config_dir, env={}))
    settings = other.plugins.stages.types[record.kind]
    assert settings.moves == "rule" and [s.id for s in settings.stages] == ["draft", "ready"]
    other.close()


def test_rule_mode_refuses_stages_without_entry_checks(tmp_path):
    stages = {"moves": "rule", "project": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}
    with pytest.raises(ConfigError, match="needs an entry check"):
        config(tmp_path, stages)


def test_moves_go_one_stage_forward_or_back(stage_workspace):
    from engine.applier import move_stage
    from engine.config.schema import StageDefinition
    from engine.storage import StoreError

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages.append(StageDefinition(id="done", label="Done"))
    move_stage(store, move_op(store.read().get(record.kind, record.id), "draft"))
    with pytest.raises(StoreError, match="one stage at a time"):
        move_stage(store, move_op(store.read().get(record.kind, record.id), "done"))
    _set_ready(store, record)
    move_stage(store, move_op(store.read().get(record.kind, record.id), "ready"))
    _set_ready(store, record, False)
    # Back needs no entry checks; forward again does.
    move_stage(store, move_op(store.read().get(record.kind, record.id), "draft"))
    with pytest.raises(StoreError, match="not ready"):
        move_stage(store, move_op(store.read().get(record.kind, record.id), "ready"))


def test_rules_leave_an_item_the_person_moved_back(stage_workspace):
    from engine.applier import undo
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    store.plugins.stages.moves = "rule"
    _set_ready(store, record)
    worker = Worker(Workspace(store.path.parent), store, cfg, Events())
    worker.run_pending()
    worker.run_pending()
    assert store.read().get(record.kind, record.id).data["stage"] == "ready"
    last = [e for e in store.read().ledger(kind=record.kind, record_id=record.id) if e["field"] == "stage"][-1]
    undo(store, last["changeset"])
    assert store.read().get(record.kind, record.id).data["stage"] == "draft"
    worker.run_pending()
    assert store.read().get(record.kind, record.id).data["stage"] == "draft"


def test_starts_are_not_duplicated_and_close_when_the_item_moves_on(stage_workspace):
    from engine.applier import move_stage, undo

    store, cfg, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]

    def waiting():
        return [r for r in store.read().list("request") if r.data.get("stage_start") and r.data["state"] == "needs_you"]

    move_stage(store, move_op(store.read().get(record.kind, record.id), "draft"))
    assert len(waiting()) == 1
    _set_ready(store, record)
    cs = move_stage(store, move_op(store.read().get(record.kind, record.id), "ready"))
    assert waiting() == []
    undo(store, cs)
    assert len(waiting()) == 1
    move_stage(store, move_op(store.read().get(record.kind, record.id), "ready"))
    move_stage(store, move_op(store.read().get(record.kind, record.id), "draft"))
    assert len(waiting()) == 1


def test_record_types_may_not_redefine_the_stage_field(stage_workspace):
    from engine.storage import Store

    store, cfg, record = stage_workspace
    fixture = store.path.parent / "plugins" / "stage-test" / "fixture.py"
    fixture.write_text(
        fixture.read_text().replace("    ready: bool = False", "    ready: bool = False\n    stage: int = 0")
    )
    other = Store(store.path.parent / "other.db", cfg=cfg)
    assert not other.plugins.active("stage-test")
    assert "stage field" in other.plugins.status["stage-test"].reason
    other.close()


def test_record_title_prefers_name_then_title_then_text_then_id():
    from engine.stages import record_title
    from engine.storage.store import Stored

    def stored(**data):
        return Stored(kind="k/x", id="X-1", version=1, deleted=False, data=data)

    assert record_title(stored(name="A", title="B", text="C")) == "A"
    assert record_title(stored(name=" ", title="B", text="C")) == "B"
    assert record_title(stored(text="C")) == "C"
    assert record_title(stored(stage="draft")) == "X-1"


@pytest.mark.parametrize("prefix", ["", "/admin"])
def test_stage_records_list_titles_and_every_stage(stage_workspace, prefix):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import build_router
    from engine.storage import WriteContext
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    with store.transaction() as tx:
        gone = tx.create(record.kind, {}, WriteContext("pm", "trusted", "test"))
    with store.transaction() as tx:
        tx.delete(record.kind, gone.id, WriteContext("pm", "trusted", "test"), read_version=gone.version)
    ws = Workspace(store.path.parent)
    worker = Worker(ws, store, cfg, Events())
    app = FastAPI()
    app.include_router(build_router(ws, cfg, store, worker.events, worker), prefix=prefix)
    with TestClient(app) as client:
        rows = client.get(f"{prefix}/api/stages/records").json()
        assert [row["record"]["id"] for row in rows] == [record.id]
        row = rows[0]
        assert row["title"] == record.id
        assert row["stages"] == [{"id": "draft", "label": "Draft"}, {"id": "ready", "label": "Ready"}]
        assert row["current"] is None and row["next"]["id"] == "draft" and row["ready"]
        store.plugins.disable("stage-test", "test failure")
        assert client.get(f"{prefix}/api/stages/records").json() == []


def test_today_suggests_moves_only_for_items_already_in_a_stage(stage_workspace):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import build_router
    from engine.applier import move_stage
    from engine.storage import WriteContext
    from engine.worker import Events, Worker
    from engine.workspace import Workspace

    store, cfg, record = stage_workspace
    ws = Workspace(store.path.parent)
    worker = Worker(ws, store, cfg, Events())
    app = FastAPI()
    app.include_router(build_router(ws, cfg, store, worker.events, worker))
    with TestClient(app) as client:
        everywhere = {v["record"]["id"]: v for v in client.get("/api/stages/records").json()}
        assert everywhere[record.id]["current"] is None and everywhere[record.id]["ready"]
        assert client.get("/api/stages/ready").json() == []
        move_stage(store, move_op(record, "draft"))
        with store.transaction() as tx:
            current = tx.get(record.kind, record.id)
            tx.update(
                record.kind,
                record.id,
                {"ready": True},
                WriteContext("pm", "trusted", "test"),
                read_version=current.version,
            )
        ready = client.get("/api/stages/ready").json()
        assert [v["record"]["id"] for v in ready] == [record.id] and ready[0]["current"] == "draft"


def test_a_stage_task_waiting_for_a_go_cannot_be_dismissed(stage_workspace):
    from engine.applier import move_stage
    from engine.dispatcher import dismiss
    from engine.storage import StoreError

    store, _, record = stage_workspace
    store.plugins.stages.types[record.kind].stages[0].starts = ["notes"]
    move_stage(store, move_op(record, "draft"))
    request = next(r for r in store.read().list("request") if r.data.get("stage_start"))
    assert request.data["state"] == "needs_you" and request.data["approval"] == "required"
    with pytest.raises(ValueError, match="can't be dismissed"):
        dismiss(store, request.id, request.version)
    with pytest.raises(StoreError, match="changed"):
        dismiss(store, request.id, request.version + 1)
    assert store.read().get("request", request.id).data["state"] == "needs_you"
