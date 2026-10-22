"""Adding a to-do by hand (design 6.32): the words, a day in plain words said back, who does it, a project and how it
repeats; it applies at once as the person's own and Undo takes it all back; words that aren't clear save nothing. Names
and ids come from the fixtures; the date is moved by the store's own clock."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.today import zone
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_corrections import other_of, pm_of

TOKEN = "add-todo-token"
MONDAY = date(2026, 11, 2)
TEXT = "Send the weekly update"


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    store = app.state.store
    stamp = datetime(MONDAY.year, MONDAY.month, MONDAY.day, 12, tzinfo=zone(cfg)).astimezone(UTC).isoformat()
    store.clock = lambda: stamp
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, store, cfg


def data(store, action_id) -> dict:
    return store.read().get("action", action_id).data


def undo_all(client, made):
    for changeset in reversed(made["changesets"]):
        assert client.post(f"/api/changesets/{changeset}/undo", json={}).status_code == 200


def test_the_day_typed_is_read_from_today_and_said_back_or_said_to_be_unclear(api):
    client, _, _ = api
    said = client.post("/api/todos/day", json={"words": "Friday"}).json()
    assert said == {"status": "ok", "day": "2026-11-06"}
    assert client.post("/api/todos/day", json={"words": "  "}).json() == {"status": "none", "day": None}
    assert client.post("/api/todos/day", json={"words": "whenever the moon is out"}).json()["status"] == "unclear"


def test_a_to_do_with_a_day_in_words_is_the_persons_own_and_applies_at_once(api):
    client, store, cfg = api
    me = pm_of(cfg)
    made = client.post("/api/todos", json={"text": TEXT, "when": "Friday", "owners": [me]})
    assert made.status_code == 200
    body = made.json()
    assert len(body["changesets"]) == 1
    row = data(store, body["action"])
    assert row["text"] == TEXT and row["status"] == "open" and row["due"] == "2026-11-06"
    assert [o["person"] for o in row["owners"]] == [me]
    todo = next(t for t in client.get("/api/today/todo").json() if t["action"] == body["action"])
    assert todo["due"] == "2026-11-06" and todo["repeat"] is None


def test_undo_of_a_to_do_with_no_repeat_takes_it_back(api):
    client, store, cfg = api
    made = client.post("/api/todos", json={"text": TEXT, "owners": [pm_of(cfg)]}).json()
    assert store.read().get("action", made["action"]) is not None
    undo_all(client, made)
    assert store.read().get("action", made["action"]) is None


def test_a_to_do_with_no_day_has_none(api):
    client, store, cfg = api
    made = client.post("/api/todos", json={"text": TEXT, "owners": [pm_of(cfg)]}).json()
    assert data(store, made["action"])["due"] is None


def test_a_to_do_for_someone_else_with_a_project_is_theirs(api):
    client, store, cfg = api
    other = other_of(cfg)
    project = client.get("/api/projects").json()[0]["id"]
    made = client.post("/api/todos", json={"text": TEXT, "owners": [other], "project": project}).json()
    row = data(store, made["action"])
    assert [o["person"] for o in row["owners"]] == [other] and row["project"] == project


def test_a_to_do_with_a_repeat_has_it_in_its_own_change_and_undo_takes_both_back(api):
    client, store, cfg = api
    made = client.post(
        "/api/todos", json={"text": TEXT, "when": "Friday", "owners": [pm_of(cfg)], "repeat": "every Friday"}
    ).json()
    assert len(made["changesets"]) == 2
    repeat = data(store, made["action"])["repeat"]
    assert repeat["phrase"] == "every Friday" and repeat["start"] == "2026-11-06"
    todo = next(t for t in client.get("/api/today/todo").json() if t["action"] == made["action"])
    assert todo["repeat"]["phrase"] == "every Friday" and todo["repeat"]["shape"]["kind"] == "weekly"
    undo_all(client, made)
    assert store.read().get("action", made["action"]) is None, "the to-do and its repeat are both gone"
    assert all(t["action"] != made["action"] for t in client.get("/api/today/todo").json())


def test_a_repeat_with_no_day_makes_the_to_do_due_on_the_first_day_of_the_repeat(api):
    client, store, cfg = api
    made = client.post("/api/todos", json={"text": TEXT, "owners": [pm_of(cfg)], "repeat": "every Tuesday"}).json()
    assert data(store, made["action"])["due"] == "2026-11-03"


def test_what_is_not_clear_is_said_and_nothing_is_saved(api):
    client, store, cfg = api
    before = len(store.read().list("action"))
    me = pm_of(cfg)
    cases = [
        ({"text": TEXT, "when": "whenever the moon is out", "owners": [me]}, "day isn't clear"),
        ({"text": TEXT, "owners": [me], "repeat": "quarterly"}, "repeat isn't clear"),
        ({"text": TEXT, "when": "Friday", "owners": [me], "repeat": "every Tuesday"}, "2026-11-10"),
        ({"text": TEXT, "owners": []}, "Pick who"),
        ({"text": "   ", "owners": [me]}, "Say what"),
        ({"text": TEXT, "owners": ["no-such-person"]}, "isn't on file"),
        ({"text": TEXT, "owners": [me], "project": "no-such-project"}, "isn't on file"),
    ]
    for body, said in cases:
        result = client.post("/api/todos", json=body)
        assert result.status_code in (409, 422), body
        if result.status_code == 409:
            assert said in result.json()["detail"], body
    assert len(store.read().list("action")) == before
