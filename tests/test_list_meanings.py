"""Value-list values carry meaning (design 5.4): each value has a tone, and a status list's values a meaning, so a value
the person adds still ranks, colors and counts as done correctly. The ranking, the at-risk lines, the colors and
"completed" read the meaning, never the label. A workspace whose lists were made before meanings existed still loads.
Names and ids come from the fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.applier import apply_as_person, undo
from engine.lists import (
    MEANINGS,
    TONES,
    core_lists,
    describe,
    ensure,
    projects_at_risk,
    status_rank,
    suggest,
)
from engine.records import ValueList
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records

TOKEN = "meanings-token"
_PM = WriteContext("pm", "trusted", "test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    ensure(store)  # the app does this when it opens a workspace
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.store, cfg


def _add(store, cfg, **op):
    return apply_as_person(store, cfg, [{"op": "list.add", "list": "project-status", **op}], "Added to a list")


def _list(store, name="project-status"):
    return next(r for r in store.read().list("value_list") if r.data["name"] == name)


# ---- what ships -----------------------------------------------------------------------------------------------------


def test_every_shipped_value_has_a_tone_and_every_shipped_status_value_a_meaning():
    lists = core_lists()
    for name, entry in lists.items():
        assert set(entry["tones"]) == set(entry["values"]), f"{name}: every shipped value has a tone"
        assert set(entry["tones"].values()) <= set(TONES)
    status = lists["project-status"]
    assert status["status"] and set(status["meanings"]) == set(status["values"])
    assert set(status["meanings"].values()) <= set(MEANINGS)
    assert {"at_risk", "done", "blocked", "open"} <= set(status["meanings"].values())
    assert not lists["project-priority"]["status"] and lists["project-priority"]["meanings"] == {}


@pytest.mark.parametrize("template", [DEMO_A, DEMO_B], ids=lambda p: p.name)
def test_both_demo_workspaces_read_a_tone_and_a_meaning_for_the_statuses_their_projects_hold(template, tmp_path):
    ws = init_workspace(tmp_path / "ws", template=template, git=False)
    store = Store(ws.db_path, cfg=ws.config(env={}))
    try:
        used = {p["status"] for p in fixture_records(template, "project") if p.get("status")}
        assert used
        for value in used:
            found = describe(store.read(), "project-status", value)
            assert found.meaning in MEANINGS and found.tone in TONES, value
    finally:
        store.close()


# ---- a workspace made before meanings existed -----------------------------------------------------------------------


def test_a_list_record_without_tones_or_meanings_still_loads_and_reads_the_shipped_ones(env):
    _, cfg, store = env
    old = {
        "id": "LIST-9",
        "name": "project-status",
        "label": "Project status",
        "values": ["On track", "Sideways"],
        "retired": [],
    }
    assert ValueList.model_validate(old).meanings == {}
    record = _list(store)
    with store.transaction() as tx:
        tx.update(
            "value_list", record.id, {"values": [*record.data["values"], "Sideways"]}, _PM, read_version=record.version
        )
        current = tx.get("value_list", record.id)
        # Strip the fields as an older record would have them.
        tx.update("value_list", record.id, {"tones": {}, "meanings": {}}, _PM, read_version=current.version)
    view = store.read()
    shipped = core_lists()["project-status"]
    assert describe(view, "project-status", "On track").meaning == shipped["meanings"]["On track"]
    assert describe(view, "project-status", "Sideways").meaning is None  # not shipped, never guessed from its label
    assert describe(view, "project-status", "Sideways").tone == "neutral"
    assert describe(view, "no-such-list", "x").tone == "neutral"


# ---- adding a value asks for its meaning ----------------------------------------------------------------------------


def test_a_value_added_with_a_meaning_and_tone_keeps_them_and_undo_takes_them_back(env):
    _, cfg, store = env
    cs = _add(store, cfg, value="Paused", tone="warn", meaning="blocked")
    found = describe(store.read(), "project-status", "Paused")
    assert (found.tone, found.meaning) == ("warn", "blocked")
    assert _list(store).data["meanings"]["Paused"] == "blocked"
    assert undo(store, cs).restored
    assert "Paused" not in _list(store).data["values"] and "Paused" not in _list(store).data["meanings"]


def test_a_value_added_without_a_meaning_takes_the_suggestion_and_a_word_it_cannot_place_is_open(env):
    _, cfg, store = env
    assert suggest("Paused")["meaning"] == "blocked" and suggest("Finished")["meaning"] == "done"
    assert suggest("Running late")["meaning"] == "at_risk" and suggest("Not started yet")["meaning"] == "not_started"
    _add(store, cfg, value="Paused")
    assert describe(store.read(), "project-status", "Paused").meaning == "blocked"
    _add(store, cfg, value="Zzzz")
    assert describe(store.read(), "project-status", "Zzzz").meaning == "open"
    assert describe(store.read(), "project-status", "Zzzz").tone == "neutral"


def test_a_meaning_is_refused_on_a_list_that_has_none_and_a_bad_meaning_or_tone_is_refused(env):
    _, cfg, store = env
    with pytest.raises(StoreError):
        apply_as_person(
            store, cfg, [{"op": "list.add", "list": "project-priority", "value": "Urgent", "meaning": "done"}], "x"
        )
    apply_as_person(
        store, cfg, [{"op": "list.add", "list": "project-priority", "value": "Urgent", "tone": "danger"}], "x"
    )
    assert describe(store.read(), "project-priority", "Urgent").tone == "danger"
    assert describe(store.read(), "project-priority", "Urgent").meaning is None
    with pytest.raises(ValidationError):
        _add(store, cfg, value="Odd", meaning="sideways")
    with pytest.raises(ValidationError):
        _add(store, cfg, value="Odd", tone="purple")


def test_renaming_carries_a_values_tone_and_meaning_and_merging_drops_them_and_retiring_keeps_them(env):
    _, cfg, store = env
    _add(store, cfg, value="Paused", tone="warn", meaning="blocked")
    apply_as_person(
        store, cfg, [{"op": "list.rename", "list": "project-status", "value": "Paused", "to": "Parked"}], "Renamed"
    )
    kept = describe(store.read(), "project-status", "Parked")
    assert (kept.tone, kept.meaning) == ("warn", "blocked")
    assert "Paused" not in _list(store).data["meanings"]
    apply_as_person(store, cfg, [{"op": "list.retire", "list": "project-status", "value": "Parked"}], "Retired")
    assert describe(store.read(), "project-status", "Parked").meaning == "blocked"
    _add(store, cfg, value="Stuck", meaning="blocked")
    apply_as_person(
        store, cfg, [{"op": "list.merge", "list": "project-status", "value": "Stuck", "into": "On track"}], "Merged"
    )
    assert "Stuck" not in _list(store).data["meanings"] and "Stuck" not in _list(store).data["tones"]


# ---- ranking, at-risk lines and completed read the meaning -----------------------------------------------------------


def test_ranking_reads_the_meaning_so_an_added_value_ranks_where_its_meaning_says(env):
    _, cfg, store = env
    view = store.read()
    by_meaning = {
        m: next(v for v, got in core_lists()["project-status"]["meanings"].items() if got == m)
        for m in ("at_risk", "blocked", "open", "done")
    }
    ranks = {m: status_rank(view, "project-status", v) for m, v in by_meaning.items()}
    assert ranks["at_risk"] < ranks["blocked"] < ranks["open"] < ranks["done"]
    _add(store, cfg, value="Paused", meaning="blocked")
    _add(store, cfg, value="Mystery", meaning="at_risk")
    view = store.read()
    assert status_rank(view, "project-status", "Paused") == ranks["blocked"]
    assert status_rank(view, "project-status", "Mystery") == ranks["at_risk"]
    assert status_rank(view, "project-status", None) > ranks["open"]  # unknown stays unknown, after open work


def test_the_at_risk_line_counts_projects_by_meaning_not_by_the_words_at_risk(env):
    _, cfg, store = env
    project = fixture_records(DEMO_B, "project")[0]["id"]
    assert project not in projects_at_risk(store.read())
    _add(store, cfg, value="Wobbly", meaning="at_risk")
    rec = store.read().get("project", project)
    with store.transaction() as tx:
        tx.update("project", project, {"status": "Wobbly"}, _PM, read_version=rec.version)
    assert project in projects_at_risk(store.read())


def test_completed_follows_the_done_meaning_so_an_added_finished_value_completes_a_project(api):
    client, base, store, cfg = api
    project = fixture_records(DEMO_B, "project")[0]["id"]
    first = next(p for p in client.get(f"{base}/projects").json() if p["id"] == project)
    assert not first["completed"] and first["status_meaning"] and first["status_tone"] in TONES
    added = client.post(f"{base}/lists/project-status/add", json={"value": "Shipped", "meaning": "done", "tone": "ok"})
    assert added.status_code == 200, added.text
    rec = store.read().get("project", project)
    with store.transaction() as tx:
        tx.update("project", project, {"status": "Shipped"}, _PM, read_version=rec.version)
    row = next(p for p in client.get(f"{base}/projects").json() if p["id"] == project)
    assert row["completed"] and row["status_meaning"] == "done" and row["status_tone"] == "ok"
    assert row["status_rank"] > first["status_rank"]


# ---- through the API ------------------------------------------------------------------------------------------------


def test_the_lists_view_carries_tones_meanings_and_whether_a_list_asks_for_one(api):
    client, base, store, cfg = api
    found = {v["name"]: v for v in client.get(f"{base}/lists").json()}
    status, priority = found["project-status"], found["project-priority"]
    assert status["status"] and not priority["status"]
    assert set(status["meanings"]) == set(status["values"]) and set(status["tones"]) == set(status["values"])
    assert priority["meanings"] == {} and set(priority["tones"]) == set(priority["values"])
    assert (
        client.post(f"{base}/lists/project-priority/add", json={"value": "Urgent", "meaning": "done"}).status_code
        == 409
    )
    assert client.post(f"{base}/lists/project-status/add", json={"value": "Odd", "tone": "purple"}).status_code == 422


def test_the_api_suggests_a_tone_and_a_meaning_for_a_typed_value(api):
    client, base, _, _ = api
    got = client.get(f"{base}/list-suggestion", params={"list": "project-status", "value": "Paused"})
    assert got.status_code == 200 and got.json() == {"tone": suggest("Paused")["tone"], "meaning": "blocked"}
    plain = client.get(f"{base}/list-suggestion", params={"list": "project-priority", "value": "Paused"}).json()
    assert plain["meaning"] is None  # a list with no meanings suggests only a tone
