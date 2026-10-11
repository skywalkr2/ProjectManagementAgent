"""Plugin API 0.3.22: requests that always wait for the go, proposals that queue work, validators that know the run,
placing a record through a reference, numeric collection order, the current text version and "don't copy" parts."""

from datetime import UTC, datetime

import yaml

from tests.test_today_panels_jobs import FIXTURE, goals, workspace

QUEUEING = (
    FIXTURE.replace(
        "def tidy(context):\n",
        "def tidy(context):\n"
        '    for goal in context.list("p18/goal", status="open"):\n'
        '        context.queue_request("p18/plan", "Plan it", goal, needs_go=True)\n'
        "    return\n",
    )
    .replace(
        "def close(target, context, choices):\n",
        "SEEN = []\n\n"
        "def check(op, view, origin):\n"
        "    SEEN.append(origin)\n"
        "    return []\n\n"
        "def plan_all(target, context, choices):\n"
        '    goals = context.list("p18/goal", status="open")\n'
        '    asks = [{"task": "p18/plan", "about": ("p18/goal", g.id)} for g in goals]\n'
        '    return Proposal("Plan every goal", requests=asks)\n\n'
        "def close(target, context, choices):\n",
    )
    .replace(
        '    registrar.action("p18/close", label="Close", run=close, on="p18/goal")\n',
        '    registrar.action("p18/close", label="Close", run=close, on="p18/goal")\n'
        '    registrar.action("p18/plan-all", label="Plan all", run=plan_all)\n'
        '    registrar.op_validator("p18/add-goal", check)\n',
    )
)


def queueing_workspace(tmp_path):
    from engine.storage import Store

    ws, cfg, store = workspace(tmp_path, QUEUEING)
    store.close()
    manifest_path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["provides"]["actions"].append("p18/plan-all")
    manifest["provides"]["op_validators"] = ["p18/add-goal"]
    manifest_path.write_text(yaml.safe_dump(manifest))
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p18"), store.plugins.status["p18"].reason
    return ws, cfg, store


def test_a_request_can_always_wait_for_the_go(tmp_path):
    ws, cfg, store = queueing_workspace(tmp_path)
    try:
        goals(cfg, store, "Finish the map")
        store.plugins.run_job("p18/tidy", datetime.now(UTC))
        request = store.read().list("request")[-1]
        assert request.data["task"] == "p18/plan" and request.data["state"] == "needs_you"
        assert request.data["approval"] == "required"
    finally:
        store.close()


def test_a_proposal_queues_work_that_waits_for_the_go(tmp_path):
    from engine import actions

    ws, cfg, store = queueing_workspace(tmp_path)
    try:
        goals(cfg, store, "One", "Two")
        pending = actions.preview(store, cfg, "p18/plan-all")
        assert [r["about"]["kind"] for r in pending.requests] == ["p18/goal", "p18/goal"]
        before = len(store.read().list("request"))
        actions.apply(store, cfg, pending.token, {})
        made = store.read().list("request")[before:]
        assert [r.data["task"] for r in made if r.data["task"] == "p18/plan"] == ["p18/plan", "p18/plan"]
        assert all(r.data["approval"] == "required" for r in made if r.data["task"] == "p18/plan")
    finally:
        store.close()


def test_a_validator_knows_the_runs_task_and_record(tmp_path):
    import sys

    ws, cfg, store = queueing_workspace(tmp_path)
    try:
        goals(cfg, store, "Finish the map")
        seen = next(m for name, m in sys.modules.items() if name.endswith(".fixture") and hasattr(m, "SEEN")).SEEN
        assert seen and {"task", "about"} <= set(seen[-1]) and seen[-1]["task"] == "notes"
    finally:
        store.close()


def test_unpriced_work_can_wait_for_the_go(tmp_path):
    from engine.ai.router import Router
    from engine.config import load_config
    from engine.dispatcher import process
    from engine.storage import Store, WriteContext

    ws, cfg, store = workspace(tmp_path)
    store.close()
    ai = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())
    ai["budgets"]["confirm_unpriced"] = True
    (ws.config_dir / "ai.yaml").write_text(yaml.safe_dump(ai))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        with store.transaction() as tx:
            request = tx.create(
                "request",
                {"task": "notes", "note": "x", "origin": "pm", "state": "queued", "created_at": "2026-10-12T09:00:00"},
                WriteContext("pm", "trusted", "ui"),
            )
        process(ws, store, cfg, Router(cfg, store, env={}), request.id)
        waiting = store.read().get("request", request.id).data
        assert waiting["state"] == "needs_you" and "can't be estimated" in waiting["waiting"]
    finally:
        store.close()


def test_collections_sort_numbers_as_numbers():
    from engine.plugin_api import Record
    from engine.sync import Entry, _collection_files, _Names

    class Step(Record):
        record_kind = "p/step"
        prefix = "STP"
        layout = "plan/steps"
        layout_collection = True
        layout_sort = "order"
        order: int = 0

    class Stored:
        def __init__(self, rid, order):
            self.id, self.kind, self.version, self.data = rid, "p/step", 1, {"id": rid, "order": order}

    files, index = {}, {}
    records = [Stored("STP-1", 10), Stored("STP-2", 9), Stored("STP-3", None)]
    _collection_files({}, Step, records, lambda r: "_workspace", None, _Names(), files, index)
    assert [e["order"] for e in yaml.safe_load(files["_workspace/plan/steps.yaml"]) if "order" in e] == [9, 10]
    assert isinstance(next(iter(index.values())), Entry)


def test_a_part_can_forbid_copying_but_allow_quoting():
    from engine.packet import _render_part
    from engine.plugin_api import Part

    rendered = _render_part(Part("Character", "Ada keeps the ferry log.", no_copy=True))
    assert rendered.startswith('<material copy="no"')
