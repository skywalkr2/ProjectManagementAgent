"""The HTTP API end to end: hand in, review, Follow-ups and backups, with the stub AI answering from the eval cases.

Names come from the imprint fixture, never written out here.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "test-token-value"


def case(case_id: str) -> dict:
    return next(c for c in load_cases(DEMO_B) if c["id"] == case_id)


def by_role(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


@pytest.fixture(params=["/", "/admin"])
def api(request, tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    flags = {"server.base_path": request.param, "storage.backups.targets": [{"path": str(tmp_path / "offsite")}]}
    cfg = ws.config(env={}, flags=flags)
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    prefix = "" if request.param == "/" else request.param
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, f"{prefix}/api", app.state.worker
    set_responder(None)


def hand_in_case(client, base, worker, case_id: str) -> dict:
    c = case(case_id)
    set_responder(lambda task: json.dumps(c["stub_answer"]))
    r = client.post(f"{base}/handin", json={"note": c.get("note", ""), "pasted": c.get("pasted", "")})
    assert r.status_code == 200
    assert worker.run_pending() == 1
    return next(item for item in client.get(f"{base}/changes").json() if item["id"] == r.json()["request"])


def test_a_hand_in_is_processed_and_shows_in_what_changed(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "production-checkin")
    assert item["state"] == "review"
    ops = item["changeset"]["ops"]
    assert [o["status"] for o in ops] == ["applied"] * 3
    assert all(o["evidence"]["quote"] and o["title"] and o["meta"]["owners"] for o in ops)
    designer = by_role("Cover designer")["full_name"]
    assert any(designer in o["meta"]["owners"] for o in ops)


def test_status_counts_requests_and_reports_backups(api):
    client, base, worker = api
    before = client.get(f"{base}/status").json()
    assert before["backup"]["needs_attention"]
    client.post(f"{base}/handin", json={"note": "remember the reading series"})
    assert client.get(f"{base}/status").json()["requests"]["queued"] == 1
    worker.run_pending()
    assert client.get(f"{base}/status").json()["version"] > before["version"]
    client.post(f"{base}/backup")
    assert not client.get(f"{base}/status").json()["backup"]["needs_attention"]


def test_an_empty_hand_in_is_refused(api):
    client, base, _ = api
    assert client.post(f"{base}/handin", json={"note": "", "pasted": "  "}).status_code == 409


def test_looks_good_then_reopen(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "close-action")
    cs = item["changeset"]["id"]
    assert client.post(f"{base}/changesets/{cs}/looks-good").status_code == 200
    after = next(i for i in client.get(f"{base}/changes").json() if i["id"] == item["id"])
    assert after["state"] == "done" and after["changeset"]["reviewed"]
    client.post(f"{base}/changesets/{cs}/reopen")
    again = next(i for i in client.get(f"{base}/changes").json() if i["id"] == item["id"])
    assert again["state"] == "review" and not again["changeset"]["reviewed"]


def test_undo_restores_the_records(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "close-action")
    action_id = case("close-action")["expect"][0]["id"]
    report = client.post(f"{base}/changesets/{item['changeset']['id']}/undo", json={}).json()
    assert report["restored"] and not report["skipped"]
    store = client.app.state.store
    assert store.read().get("action", action_id).data["status"] == "open"


def test_a_held_action_gets_an_owner(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "no-owner")
    (op,) = item["changeset"]["ops"]
    assert op["meta"]["action_status"] == "held" and op["question"]
    publicist = by_role("Publicist")["id"]
    assert client.post(f"{base}/questions/{op['question']}/pick-owner", json={}).status_code == 422
    assert client.post(f"{base}/questions/{op['question']}/pick-owner", json={"person": publicist}).status_code == 200
    action = client.app.state.store.read().get("action", op["record"]["id"])
    assert action.data["status"] == "open" and action.data["owners"][0]["person"] == publicist


def test_send_back_queues_a_new_request(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "close-action")
    r = client.post(
        f"{base}/changesets/{item['changeset']['id']}/send-back", json={"note": "that was a different file"}
    )
    new = r.json()["request"]
    assert new != item["id"]
    assert client.get(f"{base}/status").json()["requests"]["queued"] == 1


def test_followups_put_the_pm_first_and_mark_sent_clears_a_person(api):
    client, base, _ = api
    sections = client.get(f"{base}/followups").json()
    assert sections[0]["is_pm"]
    editor = by_role("Editor")
    sec = next(s for s in sections if s["person"] == editor["id"])
    assert sec["to_send"] > 0 and sec["message"]
    counts = client.post(f"{base}/followups/{editor['id']}/mark-sent", json={"text": sec["message"]}).json()
    assert counts["questions"] + counts["actions"] == sec["to_send"]
    sec = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor["id"])
    assert sec["to_send"] == 0


def test_answering_a_question(api):
    client, base, _ = api
    q = fixture_records(DEMO_B, "question")[0]
    assert client.post(f"{base}/questions/{q['id']}/answer", json={"text": "Yes, go ahead."}).status_code == 200
    stored = client.app.state.store.read().get("question", q["id"])
    assert stored.data["status"] == "answered"
    assert client.post(f"{base}/questions/Q-999/answer", json={"text": "x"}).status_code == 404
    assert client.post(f"{base}/changesets/CS-999/looks-good").status_code == 404


def test_people_lists_everyone_by_id(api):
    client, base, _ = api
    people = client.get(f"{base}/people").json()
    assert {p["id"] for p in people} == {p["id"] for p in fixture_records(DEMO_B, "person")}


def test_the_api_needs_the_token(api):
    client, base, _ = api
    assert client.get(f"{base}/changes", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_the_openapi_schema_lists_the_routes(api):
    client, base, _ = api
    paths = client.get(f"{base}/openapi.json").json()["paths"]
    assert {"/api/handin", "/api/changes", "/api/followups", "/api/status"} <= set(paths)
