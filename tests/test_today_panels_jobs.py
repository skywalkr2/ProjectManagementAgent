"""Plugins' Today lines, panels described as data, and scheduled jobs with a record of each run."""

from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.config import load_config
from tests.conftest import DEMO_B

FIXTURE = """
from typing import ClassVar, Literal
from engine.plugin_api import OpModel, Proposal, Record, Settings, TodayLine

class Config(Settings):
    pass

class Goal(Record):
    record_kind: ClassVar[str] = "p18/goal"
    prefix: ClassVar[str] = "GOL"
    title: str
    status: Literal["open", "done"] = "open"

class AddGoal(OpModel):
    op: Literal["p18/add-goal"] = "p18/add-goal"
    writes: ClassVar[dict] = {"p18/goal": ("*",)}
    title: str
    status: str = "open"

def add_goal(op, writer, cfg):
    writer.create("p18/goal", {"title": op.title, "status": op.status})

def close(target, context, choices):
    return Proposal("Close " + target.data["title"])

def lines(view, settings):
    return [
        TodayLine(g.id, "Look at " + g.data["title"], about=("p18/goal", g.id), action="p18/close")
        for g in view.list("p18/goal", status="open")
    ]

def tidy(context):
    if context.list("p18/goal", status="open"):
        context.file_question("Tidy the open goals?")

def register(registrar):
    registrar.record_type(Goal)
    registrar.op(AddGoal, "data", add_goal)
    registrar.action("p18/close", label="Close", run=close, on="p18/goal")
    registrar.task_kind("p18/plan", label="Plan", ops=("note",), on="p18/goal")
    registrar.today("p18/open-goals", lines=lines)
    registrar.panel(
        "p18/goals", title="Goals", kind="p18/goal", columns=("title", "status"), filter={"status": "open"},
        primary_action="p18/close", row_actions=("p18/plan",),
    )
    registrar.job("p18/tidy", every_minutes=60, run=tidy)
"""

MANIFEST = {
    "name": "p18",
    "version": "0.1.0",
    "plugin_api": ">=0.3,<0.4",
    "description": "Today, panels and jobs fixture",
    "entry": "fixture:register",
    "config_schema": "fixture:Config",
    "provides": {
        "record_types": ["p18/goal"],
        "ops": ["p18/add-goal"],
        "actions": ["p18/close"],
        "ai_task_kinds": ["p18/plan"],
        "today": ["p18/open-goals"],
        "panels": ["p18/goals"],
        "jobs": ["p18/tidy"],
    },
}


def workspace(tmp_path, fixture=FIXTURE, jobs=None):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p18"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(fixture)
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(MANIFEST))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p18"]
    if jobs is not None:
        settings["plugins"]["jobs"] = jobs
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    storage = yaml.safe_load((ws.config_dir / "storage.yaml").read_text())
    storage["backups"]["automatic"] = False
    (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    assert store.plugins.active("p18"), store.plugins.status["p18"].reason
    yield ws, cfg, store
    store.close()


def goals(cfg, store, *titles, status="open"):
    from engine.applier import apply_as_person

    for title in titles:
        apply_as_person(store, cfg, [{"op": "p18/add-goal", "title": title, "status": status}], "Add a goal")


def client(env):
    from api.app import create_app

    ws, cfg, store = env
    store.close()
    token = "test-token"
    c = TestClient(create_app(ws, cfg, token, start_worker=False))
    c.headers["Authorization"] = f"Bearer {token}"
    return c, cfg.server.base_path.rstrip("/") + "/api"


def test_today_lines_come_from_the_plugin_with_their_one_action(env):
    _, cfg, store = env
    goals(cfg, store, "Finish the map", "Call the harbor office")
    goals(cfg, store, "Already done", status="done")
    c, api = client(env)
    lines = c.get(f"{api}/plugin-today").json()
    assert [line["text"] for line in lines] == ["Look at Finish the map", "Look at Call the harbor office"]
    assert lines[0]["action"] == "p18/close" and lines[0]["action_is"] == "action"
    assert lines[0]["about"]["kind"] == "p18/goal"


def test_a_panel_is_described_as_data_and_lists_its_rows(env):
    _, cfg, store = env
    goals(cfg, store, "Finish the map")
    goals(cfg, store, "Already done", status="done")
    c, api = client(env)
    panels = [p for p in c.get(f"{api}/panels").json() if p["name"].startswith("p18/")]
    assert panels == [
        {
            "name": "p18/goals",
            "title": "Goals",
            "tab": "work",
            "kind": "p18/goal",
            "view": "table",
            "columns": ["title", "status"],
            "primary_action": "p18/close",
            "row_actions": ["p18/plan"],
            "new_action": None,
        }
    ]
    rows = c.get(f"{api}/panels/p18/goals/rows").json()
    assert [r["values"] for r in rows] == [{"title": "Finish the map", "status": "open"}]
    assert c.get(f"{api}/panels/p18/nothing/rows").status_code in (400, 404, 409)


@pytest.mark.parametrize(
    "change,reason",
    [
        ('columns=("title", "status")', 'columns=("title", "colour")'),
        ('row_actions=("p18/plan",)', 'row_actions=("p18/elsewhere",)'),
    ],
)
def test_a_panel_must_name_real_fields_and_its_own_actions(tmp_path, change, reason):
    ws, cfg, store = workspace(tmp_path, FIXTURE.replace(change, reason))
    try:
        assert "panel p18/goals" in store.plugins.status["p18"].reason
    finally:
        store.close()


def test_a_today_line_with_an_unknown_action_turns_the_plugin_off(tmp_path):
    ws, cfg, store = workspace(tmp_path, FIXTURE.replace('action="p18/close")', 'action="p18/nope")'))
    try:
        goals(cfg, store, "Finish the map")
        assert store.plugins.today() == []
        assert "Today lines" in store.plugins.status["p18"].reason
    finally:
        store.close()


def test_a_job_runs_when_due_and_is_recorded(env):
    _, cfg, store = env
    goals(cfg, store, "Finish the map")
    now = datetime.now(UTC)
    assert store.plugins.due_jobs(now) == ["p18/tidy"]
    assert store.plugins.run_job("p18/tidy", now) == "ok"
    assert store.read().list("question")[-1].data["title"] == "Tidy the open goals?"
    run = store.read().list("job_run")[-1]
    assert run.data["outcome"] == "ok" and run.data["job"] == "p18/tidy"
    assert store.plugins.due_jobs(now + timedelta(minutes=30)) == []
    assert store.plugins.due_jobs(now + timedelta(minutes=61)) == ["p18/tidy"]


def test_the_workspace_sets_how_often_or_turns_a_job_off(tmp_path):
    ws, cfg, store = workspace(tmp_path, jobs={"p18/tidy": {"every_minutes": 15}})
    try:
        assert store.plugins.job_settings("p18/tidy") == (True, 15)
    finally:
        store.close()
    ws, cfg, store = workspace(tmp_path / "off", jobs={"p18/tidy": {"enabled": False}})
    try:
        assert store.plugins.due_jobs(datetime.now(UTC)) == []
    finally:
        store.close()


def test_a_failing_job_is_recorded_and_turns_the_plugin_off(tmp_path):
    ws, cfg, store = workspace(tmp_path, FIXTURE.replace("def tidy(context):\n", "def tidy(context):\n    1 / 0\n"))
    try:
        assert store.plugins.run_job("p18/tidy") == "failed"
        assert store.read().list("job_run")[-1].data["outcome"] == "failed"
        assert "job p18/tidy failed" in store.plugins.status["p18"].reason
    finally:
        store.close()


def test_the_worker_runs_due_jobs_and_the_jobs_route_shows_them(env):
    from engine.worker import Events, Worker

    ws, cfg, store = env
    goals(cfg, store, "Finish the map")
    worker = Worker(ws, store, cfg, Events())
    assert worker.run_due_jobs() == 1 and worker.run_due_jobs() == 0
    c, api = client(env)
    listed = c.get(f"{api}/jobs").json()
    assert listed[0]["name"] == "p18/tidy" and listed[0]["last_outcome"] == "ok" and listed[0]["every_minutes"] == 60
