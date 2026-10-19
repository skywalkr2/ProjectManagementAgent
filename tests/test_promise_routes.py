"""A promise shows why and is corrected from a list (design 6.33): its words, who owes it to whom, its day and the words
it came from, how it is known and what was heard since; each correction is the person's own edit with Undo, and one to
what the assistant set is a signal. Names, ids and texts come from the fixtures."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "promise-routes-token"
SAID = "I will send the floor plan by Tuesday."


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.app_store = app.state.store
        client.worker = app.state.worker
        client.me = cfg.workspace.user.person
        yield client
    set_responder(None)


def people(client) -> tuple[str, str]:
    others = [p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != client.me]
    return others[0], others[1]


def made_by_the_assistant(client) -> str:
    """A promise read from an input, so its fields were set by the assistant."""
    owner, to = people(client)
    op = {
        "op": "action.add",
        "text": "Send the floor plan",
        "owners": [owner],
        "promised_to": [to],
        "basis": "inferred",
        "due_words": "by Tuesday",
        "evidence": {"quote": SAID},
    }
    set_responder(lambda task: json.dumps({"summary": "Promise.", "ops": [op]}))
    assert client.post("/api/handin", json={"note": "", "pasted": SAID}).status_code == 200
    assert client.worker.run_pending() == 1
    return next(a.id for a in client.app_store.read().list("action") if a.data["text"] == "Send the floor plan")


def stored(client, action_id: str) -> dict:
    return client.app_store.read().get("action", action_id).data


def test_a_promise_view_says_why_it_exists(api):
    action = made_by_the_assistant(api)
    owner, to = people(api)
    with api.app_store.transaction() as tx:
        tx.update(
            "action",
            action,
            {
                "news": [
                    {"on": "2026-10-10", "text": "Replied with no date"},
                    {"on": "2026-10-12", "text": "Sent the draft", "delivered": True},
                ]
            },
            WriteContext(actor="pm", trust="trusted", op="test.promise-routes"),
            read_version=tx.get("action", action).version,
        )
    got = api.get(f"/api/promises/{action}")
    assert got.status_code == 200
    view = got.json()
    names = {p["id"]: p["full_name"] for p in fixture_records(DEMO_B, "person")}
    assert view["quote"] == SAID and view["basis"] == "inferred" and view["due_words"] == "by Tuesday"
    assert [o["id"] for o in view["owners"]] == [owner] and view["owners"][0]["name"] == names[owner]
    assert [p["id"] for p in view["promised_to"]] == [to] and view["mine"] is False
    assert view["origin"] is not None and view["due"] is not None
    # Newest first; a delivered part is credited to the owners in the owner format.
    assert [n["text"] for n in view["news"]] == ["Sent the draft", "Replied with no date"]
    assert view["news"][0]["delivered"] is True and view["news"][0]["credited"] == [names[owner]]
    assert view["news"][1]["credited"] == []
    assert api.get("/api/promises/ACT-NOPE").status_code == 404


def test_correcting_who_owes_it_to_whom_how_it_is_known_and_its_day_is_the_persons_own_edit(api):
    action = made_by_the_assistant(api)
    other, to = people(api)
    version = api.get(f"/api/promises/{action}").json()["version"]
    done = api.post(
        f"/api/promises/{action}/correct",
        json={"read_version": version, "owner": to, "promised_to": [api.me], "basis": "said", "due": "2026-11-03"},
    )
    assert done.status_code == 200, done.text
    now = stored(api, action)
    assert [o["person"] for o in now["owners"]] == [to] and now["promised_to"] == [api.me] and now["basis"] == "said"
    # The person chose the day, so the words the old one was read from, and the doubt about them, are gone.
    assert now["due"] == date(2026, 11, 3).isoformat() and now["due_words"] is None and now["due_check"] is False
    # One correction of what the assistant set records one signal naming the action, and Undo takes it back.
    (signal,) = [s.data for s in api.app_store.read().list("signal") if s.data["kind"] == "edited"]
    assert action in signal["refs"] and "owners" in signal["note"] and "basis" in signal["note"]
    assert api.post(f"/api/changesets/{done.json()['changeset']}/undo", json={"ops": None}).status_code == 200
    back = stored(api, action)
    assert [o["person"] for o in back["owners"]] == [other] and back["basis"] == "inferred"


def test_a_correction_that_changes_nothing_or_names_nobody_is_refused(api):
    action = made_by_the_assistant(api)
    other, _ = people(api)
    version = api.get(f"/api/promises/{action}").json()["version"]
    same = api.post(f"/api/promises/{action}/correct", json={"read_version": version, "owner": other})
    assert same.status_code == 409
    nobody = api.post(f"/api/promises/{action}/correct", json={"read_version": version, "owner": "PER-NOPE"})
    assert nobody.status_code == 404
