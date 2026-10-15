"""A rule's code check runs on the records a run's output wrote, so a checked rule counts as applied (design 6.22)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from engine.config import load_config
from engine.rule_use import record_applied
from engine.storage import Store, WriteContext

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.rule-output-checks")
KIND = "output-test/item"
CHECK = "output-test/ready"

PLUGIN = """
from typing import ClassVar
from engine.plugin_api import Record, Settings, StageCheckResult
class Config(Settings):
    pass
class Item(Record):
    record_kind: ClassVar[str] = "output-test/item"
    prefix: ClassVar[str] = "OUT"
    ready: bool = False
    group: str = ""
def ready(record, view, config):
    return StageCheckResult(record.data.get("ready", False), "ready" if record.data.get("ready") else "not ready")
def register(registrar):
    registrar.record_type(Item)
    registrar.stage_check("output-test/ready", ready)
"""


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "ws"
    plugin = root / "plugins" / "output-test"
    plugin.mkdir(parents=True)
    manifest = {
        "name": "output-test",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Output check fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"record_types": [KIND], "stage_checks": [CHECK]},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (plugin / "fixture.py").write_text(PLUGIN)
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "workspace.yaml").write_text("plugins:\n  enabled: [output-test]\n")
    found = Store(root / "cockpit.db", cfg=load_config(config_dir, env={}))
    yield found
    found.close()


def make(store, kind, data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def rule(store, name, *, check=CHECK, scope=None, status="active") -> str:
    return make(
        store,
        "rule",
        {
            "name": name,
            "text": "A checked rule.",
            "origin": "person",
            "status": status,
            "learned_at": NOW.isoformat(),
            "check": check,
            "applies_to": scope if scope is not None else {"records": [KIND]},
        },
    )


def output(store, rules, *, written=(), task="notes", op_status="applied") -> tuple[str, str]:
    """A run given `rules` whose changeset wrote `written` (record ids of the fixture kind)."""
    request = make(store, "request", {"task": task, "origin": "pm", "state": "done", "created_at": NOW.isoformat()})
    log = {
        "given": list(rules),
        "rules_present": list(rules),
        "rules_applied": [],
        "rules_moved": [],
        "stable_chars": 1,
    }
    run = make(
        store,
        "run",
        {
            "task": task,
            "provider": "stub",
            "model": "stub",
            "tier": "low",
            "outcome": "ok",
            "started_at": NOW.isoformat(),
            "knowledge": log,
        },
    )
    ops = [
        {
            "index": i,
            "op": {"op": "note.add"},
            "status": op_status,
            "group": f"op{i}",
            "records": [{"kind": KIND, "id": record_id}],
        }
        for i, record_id in enumerate(written)
    ]
    changeset = make(
        store,
        "changeset",
        {
            "request": request,
            "ops": ops,
            "status": "applied",
            "trust": "trusted",
            "run": run,
            "created_at": NOW.isoformat(),
        },
    )
    return run, changeset


def counts(store, run) -> dict[str, list[str]]:
    log = store.read().get("run", run).data["knowledge"]
    return {"applied": log["rules_applied"], "present": log["rules_present"]}


def test_a_rule_whose_check_holds_on_the_output_it_covers_counts_as_applied(store):
    item = make(store, KIND, {"ready": True})
    checked = rule(store, "checked")
    run, changeset = output(store, [checked], written=[item])
    assert record_applied(store, run, changeset) == [checked]
    assert counts(store, run) == {"applied": [checked], "present": []}


def test_a_check_that_fails_on_the_output_still_counts_the_rule_as_applied(store):
    item = make(store, KIND, {"ready": False})
    checked = rule(store, "checked")
    run, changeset = output(store, [checked], written=[item])
    assert record_applied(store, run, changeset) == [checked]


def test_a_rule_stays_present_when_its_scope_does_not_cover_what_the_output_wrote(store):
    item = make(store, KIND, {"ready": True, "group": "a"})
    by_filter = rule(store, "by-filter", scope={"records": [KIND], "filter": {"group": "b"}})
    by_kind = rule(store, "by-kind", scope={"records": ["project"]})
    by_task = rule(store, "by-task", scope={"records": [KIND], "task_kinds": ["extract"]})
    run, changeset = output(store, [by_filter, by_kind, by_task], written=[item])
    assert record_applied(store, run, changeset) == []
    assert counts(store, run)["present"] == [by_filter, by_kind, by_task]


def test_a_scope_naming_the_task_kind_and_the_filter_of_the_output_is_covered(store):
    item = make(store, KIND, {"ready": True, "group": "a"})
    scoped = rule(store, "scoped", scope={"records": [KIND], "task_kinds": ["notes"], "filter": {"group": "a"}})
    run, changeset = output(store, [scoped], written=[item])
    assert record_applied(store, run, changeset) == [scoped]


def test_nothing_runs_for_an_output_that_wrote_nothing_or_ops_that_were_not_applied(store):
    item = make(store, KIND, {"ready": True})
    checked = rule(store, "checked")
    empty_run, empty = output(store, [checked])
    held_run, held = output(store, [checked], written=[item], op_status="held")
    assert record_applied(store, empty_run, empty) == []
    assert record_applied(store, held_run, held) == []


def test_a_retired_rule_and_a_rule_the_run_was_not_given_are_not_marked(store):
    item = make(store, KIND, {"ready": True})
    retired = rule(store, "retired", status="retired")
    not_given = rule(store, "not-given")
    run, changeset = output(store, [retired], written=[item])
    assert record_applied(store, run, changeset) == []
    assert not_given not in counts(store, run)["applied"]


def test_a_record_the_output_wrote_that_is_gone_is_left_out(store):
    item = make(store, KIND, {"ready": True})
    checked = rule(store, "checked")
    run, changeset = output(store, [checked], written=[item])
    with store.transaction() as tx:
        tx.delete(KIND, item, _TEST, read_version=tx.get(KIND, item).version)
    assert record_applied(store, run, changeset) == []


def test_a_check_that_is_unavailable_does_not_break_the_marking(store):
    item = make(store, KIND, {"ready": True})
    checked = rule(store, "checked")
    store.plugins.disable("output-test", "test failure")
    run, changeset = output(store, [checked], written=[item])
    assert record_applied(store, run, changeset) == [checked]
