"""Handing an action to the assistant, over the API (design 7.5, roadmap B-6b): `POST /api/actions/{id}/hand-over`
queues the request, `GET /api/actions/handed` says which actions the assistant has in hand and which have a draft
waiting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "hand-over-token"
_PM = WriteContext("pm", "trusted", "test")
OWNER = fixture_records(DEMO_B, "person")[1]["id"]


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store


def make_action(store, **fields) -> str:
    with store.transaction() as tx:
        return tx.create("action", {"text": "Send the agenda", "owners": [{"person": OWNER}], **fields}, _PM).id


def test_handing_over_queues_the_request_and_the_action_is_listed_as_in_hand(api):
    client, store = api
    action = make_action(store)
    assert client.get("/api/actions/handed").json() == []
    done = client.post(f"/api/actions/{action}/hand-over", json={"note": "Three lines."})
    assert done.status_code == 200
    request = done.json()["request"]
    assert store.read().get("request", request).data["note"] == "Three lines."
    (line,) = client.get("/api/actions/handed").json()
    assert (line["action"], line["request"], line["state"], line["draft"]) == (action, request, "working", None)


def test_a_second_hand_over_or_a_closed_action_is_a_plain_refusal(api):
    client, store = api
    action = make_action(store)
    assert client.post(f"/api/actions/{action}/hand-over", json={}).status_code == 200
    again = client.post(f"/api/actions/{action}/hand-over", json={})
    assert again.status_code == 409 and "already" in again.json()["detail"]
    closed = make_action(store, status="done", done_by=[OWNER])
    assert client.post(f"/api/actions/{closed}/hand-over", json={}).status_code == 409
    assert client.post("/api/actions/ACT-9999/hand-over", json={}).status_code == 404


def test_a_request_held_for_the_go_is_listed_as_needing_it(api):
    client, store = api
    action = make_action(store)
    request = client.post(f"/api/actions/{action}/hand-over", json={}).json()["request"]
    with store.transaction() as tx:
        current = tx.get("request", request)
        tx.update(
            "request",
            request,
            {"state": "needs_you", "approval": "required", "estimate_usd": 0.31},
            _PM,
            read_version=current.version,
        )
    (line,) = client.get("/api/actions/handed").json()
    assert (line["state"], line["estimate_usd"]) == ("needs_go", 0.31)


def test_a_draft_waiting_for_review_is_listed_with_its_version(api):
    client, store = api
    action = make_action(store)
    request = client.post(f"/api/actions/{action}/hand-over", json={}).json()["request"]
    from engine.texts import new_version

    with store.transaction() as tx:
        version = new_version(
            store, tx, _PM, "action", action, "work", "A draft.\n", source="draft", by="assistant", run="RUN-1"
        )
        current = tx.get("request", request)
        tx.update("request", request, {"state": "review"}, _PM, read_version=current.version)
    (line,) = client.get("/api/actions/handed").json()
    assert (line["state"], line["draft"]) == ("draft", version.id)
