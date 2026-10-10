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
        ({"project": [{"id": "x"}, {"id": "x"}]}, "unique"),
        ({"project": [{"id": "x", "entry": ["missing"]}]}, "unknown entry check missing"),
        ({"project": [{"id": "x", "starts": ["missing"]}]}, "unknown task kind missing"),
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
                "plugin_api": ">=0.1,<0.2",
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
        assert [s.model_dump() for s in actual] == [dict(entry=[], starts=[], **s) for s in override]
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
    with pytest.raises(StoreError, match="stage-test/ready: not ready"):
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
