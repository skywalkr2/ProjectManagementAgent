"""Projects inside projects: starting one with an op, moving it under another without loops, the language work is
written in (its own, a parent's or the workspace's), and a budget that covers everything inside it."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.ai.router import Router
from engine.dispatcher import process
from engine.storage import WriteContext
from tests.conftest import DEMO_B
from tests.test_plugin_api_02 import apply, env  # noqa: F401 - the fixture is reused

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
_PM = WriteContext("pm", "trusted", "test")


def projects(store):
    return {p.data["name"]: p for p in store.read().list("project")}


def add(env, name, **fields):  # noqa: F811
    return apply(env, [{"op": "project.add", "name": name, **fields}], pm=True)


def test_project_add_starts_a_project_inside_another(env):  # noqa: F811
    _, _, store = env
    add(env, "The Harbor Trilogy", language="en-GB")
    series = projects(store)["The Harbor Trilogy"]
    _, statuses = add(env, "Book One: Low Tide", parent=series.id, summary="The first book.")
    assert statuses == ["applied"]
    book = projects(store)["Book One: Low Tide"]
    assert book.data["parent"] == series.id and book.data["language"] is None


def test_project_add_from_the_assistant_waits_for_the_person(env):  # noqa: F811
    _, _, store = env
    _, statuses = apply(env, [{"op": "project.add", "name": "A Project Nobody Asked For"}])
    assert statuses == ["held"] and "A Project Nobody Asked For" not in projects(store)


def test_names_parents_and_languages_are_checked(env):  # noqa: F811
    _, _, store = env
    existing = next(iter(projects(store)))
    assert add(env, existing.upper())[1] == ["refused"]
    assert add(env, "Orphan", parent="PRJ-999")[1] == ["refused"]
    assert add(env, "Unknown Tongue", language="not a tag")[1] == ["refused"]


def test_a_project_can_move_under_another_but_never_inside_itself(env):  # noqa: F811
    _, _, store = env
    add(env, "Series")
    series = projects(store)["Series"]
    add(env, "Book", parent=series.id)
    book = projects(store)["Book"]

    def set_parent(project, parent):
        op = {"op": "record.set", "kind": "project", "id": project.id, "field": "parent", "value": parent}
        return apply(env, [op], pm=True)[1]

    assert set_parent(series, book.id) == ["refused"]  # the series would sit inside its own book
    assert set_parent(series, series.id) == ["refused"]
    other = next(p for name, p in projects(store).items() if name not in ("Series", "Book"))
    assert set_parent(book, other.id) == ["applied"]
    assert projects(store)["Book"].data["parent"] == other.id


def test_language_comes_from_the_project_its_parents_or_the_workspace(env):  # noqa: F811
    from engine.plugin_api import ReadView
    from engine.projects import language_for

    _, cfg, store = env
    add(env, "Series", language="en-GB")
    series = projects(store)["Series"]
    add(env, "Book", parent=series.id)
    add(env, "Standalone")
    view = store.read()
    named = projects(store)
    assert language_for(view, cfg.workspace.language, named["Book"]) == "en-GB"
    assert language_for(view, cfg.workspace.language, named["Standalone"]) == cfg.workspace.language
    plugin_view = store.plugins._with_files(ReadView(view, "p02"))
    assert plugin_view.language(named["Book"]) == "en-GB"


def test_a_budget_covers_the_project_and_everything_inside_it(env):  # noqa: F811
    ws, cfg, store = env
    add(env, "Series")
    series = projects(store)["Series"]
    add(env, "Book", parent=series.id)
    book = projects(store)["Book"]
    with store.transaction() as tx:
        tx.update("project", series.id, {"budget_usd": 0.05}, _PM, read_version=series.version)
        spent = tx.create(
            "request",
            {
                "task": "notes",
                "about": {"kind": "project", "id": book.id},
                "origin": "pm",
                "state": "done",
                "created_at": NOW.isoformat(),
            },
            _PM,
        )
        tx.create(
            "run",
            {
                "request": spent.id,
                "task": "notes",
                "provider": "stub",
                "model": "stub",
                "tier": "routine",
                "cost_usd": 0.06,
                "outcome": "ok",
                "started_at": NOW.isoformat(),
            },
            _PM,
        )
        queued = tx.create(
            "request",
            {
                "task": "notes",
                "about": {"kind": "project", "id": book.id},
                "note": "Plan the next chapter.",
                "origin": "pm",
                "state": "queued",
                "created_at": NOW.isoformat(),
            },
            _PM,
        )
    assert process(ws, store, cfg, Router(cfg, store, env={}), queued.id, now=NOW) is None
    waiting = store.read().get("request", queued.id).data
    assert waiting["state"] == "needs_you" and waiting["waiting"].startswith("Series has a budget of $0.05")


def test_projects_in_the_api_show_language_parent_and_spend(env):  # noqa: F811
    from api.app import create_app

    ws, cfg, store = env
    add(env, "Series", language="en-GB")
    series = projects(store)["Series"]
    add(env, "Book", parent=series.id)
    book = projects(store)["Book"]
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    shown = {p["name"]: p for p in client.get(f"{api}/projects").json()}
    assert shown["Book"]["parent"] == series.id and shown["Book"]["language"] == "en-GB"
    assert not shown["Book"]["language_own"] and shown["Series"]["language_own"]
    loop = client.post(f"{api}/projects/{series.id}", json={"parent": book.id})
    assert loop.status_code == 409 and "inside itself" in loop.json()["detail"]
    budget = client.post(f"{api}/projects/{book.id}", json={"budget_usd": 2.5})
    assert budget.status_code == 200
    assert {p["name"]: p for p in client.get(f"{api}/projects").json()}["Book"]["budget_usd"] == 2.5


def test_only_the_person_sets_a_budget(env):  # noqa: F811
    from engine.ops import SETTABLE

    assert "budget_usd" not in SETTABLE["project"] and "content_levels" not in SETTABLE["project"]


@pytest.mark.parametrize("workspace", [DEMO_B])
def test_the_workspace_language_is_a_setting(workspace, tmp_path):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=workspace, git=False)
    assert ws.config(env={}).workspace.language
    assert ws.config(env={}, flags={"workspace.language": "fr-CA"}).workspace.language == "fr-CA"


def test_project_add_can_move_existing_projects_inside_it_and_undo_takes_both_back(env):  # noqa: F811
    from engine.applier import undo

    _, cfg, store = env
    add(env, "Book One")
    add(env, "Book Two")
    one, two = projects(store)["Book One"], projects(store)["Book Two"]
    cs_id, statuses = add(env, "The Lake Series", children=[one.id, two.id])
    assert statuses == ["applied"]
    series = projects(store)["The Lake Series"]
    assert projects(store)["Book One"].data["parent"] == series.id
    assert projects(store)["Book Two"].data["parent"] == series.id
    undo(store, cs_id)
    assert "The Lake Series" not in projects(store) and projects(store)["Book One"].data["parent"] is None


def test_project_add_refuses_children_that_would_make_a_loop(env):  # noqa: F811
    _, _, store = env
    add(env, "Outer")
    outer = projects(store)["Outer"]
    add(env, "Inner", parent=outer.id)
    inner = projects(store)["Inner"]
    assert add(env, "Middle", parent=inner.id, children=[outer.id])[1] == ["refused"]
    assert add(env, "Twice", children=[outer.id, outer.id])[1] == ["refused"]
    assert add(env, "Missing", children=["PRJ-999"])[1] == ["refused"]


def _priority_set(env, project, value, *, actor="assistant"):  # noqa: F811
    """One `record.set` of a project's priority, applied as the assistant or as the person."""
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    _, cfg, store = env
    op = {"op": "record.set", "kind": "project", "id": project.id, "field": "priority", "value": value}
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", None, "", "", "trusted"), actor=actor
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, store.read().get("changeset", cs_id).data["ops"][0]


def test_the_assistant_never_sets_a_projects_priority_but_the_person_does(env):  # noqa: F811
    from engine.applier import release
    from engine.lists import core_lists

    _, cfg, store = env
    add(env, "Ranked")
    project = projects(store)["Ranked"]
    values = core_lists()["project-priority"]["values"]
    low, high = values[0], values[-1]

    cs_id, outcome = _priority_set(env, project, low)
    assert outcome["status"] == "held" and "only you can set priority" in outcome["reason"]
    assert projects(store)["Ranked"].data["priority"] is None

    _, outcome = _priority_set(env, project, high, actor="pm")
    assert outcome["status"] == "applied" and projects(store)["Ranked"].data["priority"] == high

    release(store, cfg, cs_id, 0)  # the person accepts the assistant's proposal
    assert projects(store)["Ranked"].data["priority"] == low


def test_another_project_field_from_the_assistant_still_applies(env):  # noqa: F811
    _, _, store = env
    add(env, "Plain")
    project = projects(store)["Plain"]
    op = {"op": "record.set", "kind": "project", "id": project.id, "field": "summary", "value": "A short summary."}
    assert apply(env, [op])[1] == ["applied"]
    assert projects(store)["Plain"].data["summary"] == "A short summary."
