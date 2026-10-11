"""Plugin API 0.3.48: Today lines that offer the core's own actions, what a setup step's `done` can see, suggested
mappings that merge, computed panel columns, panels filtered by project through `layout_project` and listed only on
some projects, a record's effective stage status, and the callback addresses an add-on's own registration allows."""

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_today_panels_jobs import MANIFEST, workspace

CODE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import OpModel, Proposal, Record, RefTo, Settings, StageCheckResult, TodayLine

class Config(Settings):
    pass

class Goal(Record):
    record_kind: ClassVar[str] = "p18/goal"
    prefix: ClassVar[str] = "GOL"
    title: str
    status: Literal["open", "done"] = "open"
    project: Annotated[str | None, RefTo("project")] = None

class Entry(Record):
    record_kind: ClassVar[str] = "p18/entry"
    prefix: ClassVar[str] = "ENT"
    layout_project: ClassVar[str] = "goal"
    words: str = ""
    goal: Annotated[str, RefTo("p18/goal")]

class AddGoal(OpModel):
    op: Literal["p18/add-goal"] = "p18/add-goal"
    writes: ClassVar[dict] = {"p18/goal": ("*",)}
    title: str
    status: str = "open"
    project: str | None = None

class AddEntry(OpModel):
    op: Literal["p18/add-entry"] = "p18/add-entry"
    writes: ClassVar[dict] = {"p18/entry": ("*",)}
    goal: str
    words: str = ""

def add_goal(op, writer, cfg):
    writer.create("p18/goal", {"title": op.title, "status": op.status, "project": op.project})

def add_entry(op, writer, cfg):
    writer.create("p18/entry", {"goal": op.goal, "words": op.words})

def close(target, context, choices):
    return Proposal("Close " + target.data["title"])

def is_big(record, view, settings):
    return StageCheckResult(record.data["title"].startswith("Big"), "Only big goals are done.")

def asks_status(record, view, settings):
    view.stage_status(record)
    return StageCheckResult(True, "never reached")

def lines(view, settings):
    found = []
    for g in view.list("p18/goal", status="open"):
        status = view.stage_status(g)
        if status is not None and status.ready:
            found.append(TodayLine("ready-" + g.id, g.data["title"] + " can move on", about=("p18/goal", g.id),
                                   action="move-stage"))
        found.append(TodayLine("open-" + g.id, "See " + g.data["title"], about=("p18/goal", g.id), action="open"))
    return found

def bad_lines(view, settings):
    return [TodayLine(g.id, "Answer it", about=("p18/goal", g.id), action="answer") for g in view.list("p18/goal")]

def words(record, view, settings):
    return len(record.data["words"].split())

def broken(record, view, settings):
    raise RuntimeError("no")

def has_children(project, view):
    return bool(view.list("project", parent=project.id))

def unpriced_on(view, settings, state):
    return state.settings.get("ai.budgets.confirm_unpriced") is True

def register(registrar):
    registrar.record_type(Goal)
    registrar.record_type(Entry)
    registrar.op(AddGoal, "data", add_goal)
    registrar.op(AddEntry, "data", add_entry)
    registrar.action("p18/close", label="Close", run=close, on="p18/goal")
    registrar.stage_check("p18/big", is_big)
    registrar.stage_check("p18/asks", asks_status)
    registrar.stages("p18/goal", [{"id": "new", "label": "New", "entry": ["p18/big"]},
                                  {"id": "done", "label": "Done"}])
    registrar.today("p18/open-goals", lines=lines)
    registrar.today("p18/bad", lines=bad_lines)
    registrar.panel("p18/goals", title="Goals", kind="p18/goal", columns=("title", "status"))
    registrar.panel("p18/entries", title="Entries", kind="p18/entry", columns=("goal", "count", "oops"),
                    computed={"count": words, "oops": broken})
    registrar.panel("p18/shared", title="Shared", kind="p18/goal", columns=("title",), show_for=has_children)
    registrar.setup_step("p18/unpriced", label="Ask before unpriced work", done=unpriced_on,
                         settings={"ai.budgets.confirm_unpriced": True})
    registrar.setup_step("p18/levels", label="Name the content levels", done=lambda view, settings: False,
                         settings={"ai.content_levels": {"p18-level": "A level this add-on uses."}})
"""


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path, CODE)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = dict(MANIFEST)
    manifest["provides"] = {
        "record_types": ["p18/goal", "p18/entry"],
        "ops": ["p18/add-goal", "p18/add-entry"],
        "actions": ["p18/close"],
        "today": ["p18/open-goals", "p18/bad"],
        "panels": ["p18/goals", "p18/entries", "p18/shared"],
        "stage_checks": ["p18/big", "p18/asks"],
        "stages": ["p18/goal"],
        "setup_steps": ["p18/unpriced", "p18/levels"],
    }
    path.write_text(yaml.safe_dump(manifest))
    from tests.test_plugin_api_0329 import reopen

    cfg, store = reopen(ws, cfg)
    yield ws, cfg, store
    store.close()


def _apply(store, cfg, *ops):
    from engine.applier import apply_as_person

    apply_as_person(store, cfg, list(ops), "Set up")


def _client(ws, cfg, store):
    from api.app import create_app

    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    return c, cfg.server.base_path.rstrip("/") + "/api"


def test_today_lines_offer_the_cores_own_actions_and_bad_ones_are_contained(env):
    ws, cfg, store = env
    _apply(store, cfg, {"op": "p18/add-goal", "title": "Big harbor"}, {"op": "p18/add-goal", "title": "Small"})
    lines = store.plugins.today()
    texts = {line.text: line.action for _, line in lines}
    assert texts == {
        "Big harbor can move on": "move-stage",
        "See Big harbor": "open",
        "See Small": "open",
    }
    assert "p18/bad" in str(store.plugins.status["p18"].notes) or any(
        "Today lines p18/bad" in str(n) for n in store.plugins.status["p18"].notes
    )
    c, api = _client(ws, cfg, store)
    shown = {line["text"]: line["action_is"] for line in c.get(f"{api}/plugin-today").json()}
    assert shown["Big harbor can move on"] == "core" and shown["See Small"] == "core"


def test_stage_status_reads_the_effective_stages_and_isnt_open_to_stage_checks(env):
    ws, cfg, store = env
    _apply(store, cfg, {"op": "p18/add-goal", "title": "Small"})
    goal = store.read().list("p18/goal")[-1]
    from engine.plugin_api import ReadView

    view = store.plugins._with_files(ReadView(store.read(), "p18"))
    status = view.stage_status(goal)
    assert status.current is None and status.next == "new" and status.stages == ("new", "done")
    assert not status.ready and status.checks["p18/big"].reason == "Only big goals are done."
    stages = yaml.safe_load((ws.config_dir / "stages.yaml").read_text()) or {}
    stages.setdefault("types", {})["p18/goal"] = {"stages": [{"id": "new", "label": "New"}]}
    (ws.config_dir / "stages.yaml").write_text(yaml.safe_dump(stages))
    store.close()
    from tests.test_plugin_api_0329 import reopen

    cfg, store = reopen(ws, cfg)
    try:
        view = store.plugins._with_files(ReadView(store.read(), "p18"))
        assert view.stage_status(goal).stages == ("new",)  # the workspace's own stages
        assert view.stage_status(store.read().list("person")[0]) is None  # a kind without stages
        result = store.plugins.stage_check("p18/asks", goal)
        assert not result.passed  # asking for stage status inside a stage check is refused
    finally:
        store.close()


def test_setup_done_sees_effective_settings_accounts_and_mappings_merge(env):
    ws, cfg, store = env
    steps = {step.name: step for _, step in store.plugins.setup_steps()}
    state = store.plugins.setup_state("p18", steps["p18/unpriced"])
    assert set(state.accounts) == {"write", "check", "research"}
    assert all(isinstance(n, int) for n in state.accounts.values())
    assert not state.tool_available("anything")
    budgets = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())
    budgets.setdefault("budgets", {})["confirm_unpriced"] = False
    (ws.config_dir / "ai.yaml").write_text(yaml.safe_dump(budgets))
    assert not store.plugins.setup_step_done("p18", steps["p18/unpriced"])
    budgets["budgets"]["confirm_unpriced"] = True
    (ws.config_dir / "ai.yaml").write_text(yaml.safe_dump(budgets))  # a hand edit, no restart
    assert store.plugins.setup_step_done("p18", steps["p18/unpriced"])

    before = dict(yaml.safe_load((ws.config_dir / "ai.yaml").read_text()).get("content_levels") or {})
    c, api = _client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    applied = c.post(f"{api}/setup/p18/levels/apply-settings", json={"fingerprint": fingerprint})
    assert applied.status_code == 200, applied.text
    after = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())["content_levels"]
    assert after == {**before, "p18-level": "A level this add-on uses."}


def test_computed_columns_and_a_project_filter_through_layout_project(env):
    ws, cfg, store = env
    project = store.read().list("project")[0]
    _apply(store, cfg, {"op": "p18/add-goal", "title": "In it", "project": project.id})
    _apply(store, cfg, {"op": "p18/add-goal", "title": "Elsewhere"})
    inside, outside = store.read().list("p18/goal")[-2:]
    _apply(
        store,
        cfg,
        {"op": "p18/add-entry", "goal": inside.id, "words": "three short words"},
        {"op": "p18/add-entry", "goal": outside.id, "words": "one"},
    )
    rows = store.plugins.panel_rows("p18/entries", project.id)
    assert [r["values"] for r in rows] == [{"goal": inside.id, "count": 3, "oops": None}]
    assert any("p18/entries column oops" in str(n) for n in store.plugins.status["p18"].notes)
    assert len(store.plugins.panel_rows("p18/entries")) == 2


def test_a_panel_is_listed_only_on_the_projects_it_shows_for(env):
    ws, cfg, store = env
    projects = store.read().list("project")
    parent = next((p for p in projects if any(q.data.get("parent") == p.id for q in projects)), None)
    alone = next(p for p in projects if not any(q.data.get("parent") == p.id for q in projects))
    c, api = _client(ws, cfg, store)
    names = lambda project: {p["name"] for p in c.get(f"{api}/panels", params={"project": project}).json()}  # noqa: E731
    assert "p18/shared" not in names(alone.id) and "p18/goals" in names(alone.id)
    if parent is not None:
        assert "p18/shared" in names(parent.id)
    assert "p18/shared" in {p["name"] for p in c.get(f"{api}/panels").json()}


def test_an_add_ons_registration_is_used_only_at_the_addresses_it_allows(tmp_path):
    from engine.sign_in import address_allowed

    allowed = ("http" + "://localhost/api/sign-ins/callback",)
    assert address_allowed("http" + "://localhost:8766/api/sign-ins/callback", allowed)
    assert not address_allowed("http" + "://localhost:8766/nested/api/sign-ins/callback", allowed)
    assert address_allowed("http" + "://anywhere.example.com/x", ())
    from engine.plugin_api import Registrar

    with pytest.raises(ValueError, match="describe default_client_id"):
        Registrar("p18", {}, None).sign_in(
            "p18/x", label="X", authorize_url="a", token_url="t", scopes=["read"], default_redirects=allowed
        )
