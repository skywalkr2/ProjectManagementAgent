"""A rule's code check runs on what a change would write before it applies: a failure goes back to the assistant once,
then holds the change for the person; an outward act is refused (design 6.22)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from engine.applier import Context, Inputs, apply_changeset, check, needs_another_round, release
from engine.config import load_config
from engine.names import People
from engine.ops import CHANGESET
from engine.rule_use import RULE_CHECK, record_applied
from engine.storage import Store, WriteContext

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.rule-check-before-apply")
KIND = "before-test/item"
CHECK = "before-test/ready"
ADD = "before-test/add"

PLUGIN = """
from typing import ClassVar, Literal
from engine.plugin_api import OpModel, Record, Settings, StageCheckResult
class Config(Settings):
    pass
class Item(Record):
    record_kind: ClassVar[str] = "before-test/item"
    prefix: ClassVar[str] = "BEF"
    ready: bool = False
    group: str = ""
class Add(OpModel):
    op: Literal["before-test/add"] = "before-test/add"
    writes: ClassVar[dict] = {"before-test/item": ("*",)}
    ready: bool = False
    group: str = ""
def add(op, writer, cfg):
    writer.create("before-test/item", {"ready": op.ready, "group": op.group})
def ready(record, view, config):
    return StageCheckResult(record.data.get("ready", False), "ready" if record.data.get("ready") else "not ready")
def register(registrar):
    registrar.record_type(Item)
    registrar.op(Add, "data", add)
    registrar.stage_check("before-test/ready", ready)
"""


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "ws"
    plugin = root / "plugins" / "before-test"
    plugin.mkdir(parents=True)
    manifest = {
        "name": "before-test",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Rule check fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"record_types": [KIND], "ops": [ADD], "stage_checks": [CHECK]},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (plugin / "fixture.py").write_text(PLUGIN)
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "workspace.yaml").write_text("plugins:\n  enabled: [before-test]\n")
    found = Store(root / "cockpit.db", cfg=load_config(config_dir, env={}))
    assert found.plugins.active("before-test"), found.plugins.status.get("before-test")
    yield found
    found.close()


def make(store, kind, data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def rule(store, name, *, scope=None, status="active", text="Items are ready before they are added.") -> str:
    return make(
        store,
        "rule",
        {
            "name": name,
            "text": text,
            "origin": "person",
            "status": status,
            "learned_at": NOW.isoformat(),
            "check": CHECK,
            "applies_to": scope if scope is not None else {"records": [KIND]},
        },
    )


def context(store, *, task="notes", actor="assistant", pm=False) -> Context:
    request = make(store, "request", {"task": task, "origin": "pm", "state": "done", "created_at": NOW.isoformat()})
    inputs = Inputs(request, None, "", "", "trusted")
    allowed = tuple(store.plugins.ops)
    return Context(
        store, store.plugins.cfg, People(store, store.plugins.cfg), allowed, inputs, confirmed_by_pm=pm, actor=actor
    )


def changeset(store, *ops):
    return CHANGESET.validate_python(
        {"ops": [{"op": ADD, **op} for op in ops]}, context={"op_models": store.plugins.ops}
    )


def outcomes(store, cs_id):
    return store.read().get("changeset", cs_id).data["ops"]


def items(store):
    return store.read().list(KIND)


def test_a_failing_check_goes_back_to_the_assistant_with_the_rule_and_the_reason(store):
    rule(store, "ready-first")
    ctx = context(store)
    problems = [p for p in check(changeset(store, {"ready": False}), ctx) if p.check == RULE_CHECK]
    assert [(p.severity, p.op) for p in problems] == [("return", 0)]
    assert "Items are ready before they are added." in problems[0].message
    assert "not ready" in problems[0].message
    assert needs_another_round(problems)
    assert items(store) == []


def test_a_change_that_still_fails_the_check_is_held_for_the_person_and_writes_nothing(store):
    rule(store, "ready-first")
    ctx = context(store)
    cs_id = apply_changeset(changeset(store, {"ready": False}, {"ready": True}), [], ctx, run=None)
    held, applied = outcomes(store, cs_id)
    assert held["status"] == "held"
    assert "Items are ready before they are added." in held["reason"]
    assert applied["status"] == "applied"
    assert [i.data["ready"] for i in items(store)] == [True]


def test_the_person_releasing_the_held_change_applies_it(store):
    rule(store, "ready-first")
    cs_id = apply_changeset(changeset(store, {"ready": False}), [], context(store), run=None)
    release(store, store.plugins.cfg, cs_id, 0)
    assert outcomes(store, cs_id)[0]["status"] == "applied"
    assert [i.data["ready"] for i in items(store)] == [False]


def test_a_rule_out_of_scope_retired_or_without_a_failing_check_changes_nothing(store):
    rule(store, "other-group", scope={"records": [KIND], "filter": {"group": "b"}})
    rule(store, "other-task", scope={"records": [KIND], "task_kinds": ["extract"]})
    rule(store, "other-kind", scope={"records": ["project"]})
    rule(store, "retired", status="retired")
    ctx = context(store)
    cs = changeset(store, {"ready": False, "group": "a"})
    assert [p for p in check(cs, ctx) if p.check == RULE_CHECK] == []
    cs_id = apply_changeset(cs, [], ctx, run=None)
    assert [o["status"] for o in outcomes(store, cs_id)] == ["applied"]


def test_the_persons_own_change_is_not_held_by_their_rule(store):
    rule(store, "ready-first")
    for ctx in (context(store, actor="pm"), context(store, pm=True)):
        cs_id = apply_changeset(changeset(store, {"ready": False}), [], ctx, run=None)
        assert [o["status"] for o in outcomes(store, cs_id)] == ["applied"]


def test_an_outward_act_that_fails_the_check_is_refused(store, monkeypatch):
    rule(store, "ready-first")
    monkeypatch.setitem(store.plugins.tiers, ADD, "outbound")
    ctx = context(store)
    problems = [p for p in check(changeset(store, {"ready": False}), ctx) if p.check == RULE_CHECK]
    assert [p.severity for p in problems] == ["refuse"]


def test_the_rule_that_held_a_change_counts_as_applied_on_the_run(store):
    held_by = rule(store, "ready-first")
    log = {"given": [held_by], "rules_present": [held_by], "rules_applied": [], "rules_moved": [], "stable_chars": 1}
    run = make(
        store,
        "run",
        {
            "task": "notes",
            "provider": "stub",
            "model": "stub",
            "tier": "low",
            "outcome": "ok",
            "started_at": NOW.isoformat(),
            "knowledge": log,
        },
    )
    cs_id = apply_changeset(changeset(store, {"ready": False}), [], context(store), run=run)
    assert record_applied(store, run, cs_id) == [held_by]
