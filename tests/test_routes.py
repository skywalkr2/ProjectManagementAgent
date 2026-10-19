"""The HTTP API end to end: hand in, review, Follow-ups and backups, with the stub AI answering from the eval cases.

Names come from the imprint fixture, never written out here.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, connection_answer, fixture_records

TOKEN = "test-token-value"


def case(case_id: str) -> dict:
    return next(c for c in load_cases(DEMO_B) if c["id"] == case_id)


def by_role(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


@pytest.fixture(params=["/", "/admin"])
def api(request, tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (tmp_path / "offsite").mkdir()
    flags = {
        "server.base_path": request.param,
        "storage.backups.targets": [{"path": str(tmp_path / "offsite")}],
        "storage.backups.automatic": False,
    }
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
    # The close read from the message waits for the person's Keep (design 6.33); keep it, then undo the change.
    kept = client.post(f"{base}/changesets/{item['changeset']['id']}/ops/0/release", json={})
    assert kept.status_code == 200, kept.text
    assert client.app.state.store.read().get("action", action_id).data["status"] == "done"
    report = client.post(f"{base}/changesets/{item['changeset']['id']}/undo", json={}).json()
    assert report["restored"] and not report["skipped"]
    store = client.app.state.store
    assert store.read().get("action", action_id).data["status"] == "open"


def test_a_held_action_gets_an_owner(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "no-owner")
    (op,) = item["changeset"]["ops"]
    assert op["meta"]["action_status"] == "held" and op["ask"]["about"] == "owner"
    publicist = by_role("Publicist")["id"]
    assert client.post(f"{base}/questions/{op['ask']['id']}/pick-owner", json={}).status_code == 422
    assert client.post(f"{base}/questions/{op['ask']['id']}/pick-owner", json={"person": publicist}).status_code == 200
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
    # Two requests wait: the work again, and the assistant's learning from the note.
    assert client.get(f"{base}/status").json()["requests"]["queued"] == 2
    queued = [r for r in client.app.state.store.read().list("request") if r.data["state"] == "queued"]
    assert {r.data["task"] for r in queued} == {"notes", "learn-correction"} and new in {r.id for r in queued}


def test_a_followup_row_names_its_project_and_carries_its_pages_for_the_copied_table(api):
    client, base, _ = api
    reader = client.app.state.store.read()
    names = {p.id: p.data["name"] for p in reader.list("project")}
    links = {p.id: p.data.get("links", []) for p in reader.list("project")}
    sections = client.get(f"{base}/followups").json()
    for q in (q for s in sections for q in s["questions"]):
        record = reader.get("question", q["id"]).data
        assert q["project_name"] == ", ".join(names[p] for p in record.get("projects", []) if p in names)
        assert q["links"] == [dict(x) for x in record.get("links", [])]
    seen = [a for s in sections for a in s["actions"]]
    assert seen
    for a in seen:
        record = reader.get("action", a["id"]).data
        assert a["links"] == [dict(x) for x in links.get(record.get("project"), [])]


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
    assert sec["to_send"] == 0 and sec["message"] == ""
    sent = [q for q in sec["questions"] if q["status"] == "sent"]
    assert sent and all(q["sent"] for q in sent)
    assert all(a["told"] for a in sec["actions"])


def _waiting_action_of_the_editor(client, base):
    """Mark the editor's message sent, and return the editor's id and one action now waiting on them."""
    editor = by_role("Editor")
    sec = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor["id"])
    client.post(f"{base}/followups/{editor['id']}/mark-sent", json={"text": sec["message"]})
    sec = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor["id"])
    return editor["id"], sec["actions"][0]["id"]


def test_followed_up_records_the_chase_keeps_the_action_open_and_undo_removes_it(api):
    client, base, _ = api
    person, action_id = _waiting_action_of_the_editor(client, base)
    store = client.app.state.store
    before = store.read().get("action", action_id).data
    r = client.post(f"{base}/followups/{person}/actions/{action_id}/followed-up")
    assert r.status_code == 200
    chase = r.json()
    data = store.read().get("action", action_id).data
    assert data["status"] == "open"
    assert [str(d) for d in data["followed_up"][person]] == [chase["on"]]
    assert str(data["told"][person]) == chase["on"] and chase["previous_told"] == str(before["told"][person])
    row = next(
        a
        for s in client.get(f"{base}/followups").json()
        if s["person"] == person
        for a in s["actions"]
        if a["id"] == action_id
    )
    assert row["followed_up"] == chase["on"] and not row["chase_due"]
    body = {"on": chase["on"], "previous_told": chase["previous_told"]}
    assert client.post(f"{base}/followups/{person}/actions/{action_id}/unfollow", json=body).status_code == 200
    data = store.read().get("action", action_id).data
    assert data.get("followed_up", {}) == {} and data["status"] == "open"
    assert str(data["told"][person]) == str(before["told"][person])


def test_they_finished_it_credits_the_owner_and_records_the_pm_as_the_reporter(api):
    client, base, _ = api
    person, action_id = _waiting_action_of_the_editor(client, base)
    store = client.app.state.store
    assert client.post(f"{base}/followups/{person}/actions/{action_id}/finished").status_code == 200
    data = store.read().get("action", action_id).data
    assert data["status"] == "done" and data["done_by"] == [person]
    assert data["reported_by"] == next(s["person"] for s in client.get(f"{base}/followups").json() if s["is_pm"])
    assert client.post(f"{base}/followups/{person}/actions/{action_id}/finished").status_code == 409
    assert client.post(f"{base}/actions/{action_id}/status", json={"status": "open"}).status_code == 200
    data = store.read().get("action", action_id).data
    assert data["status"] == "open" and data["done_by"] == [] and data["reported_by"] is None


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


def test_a_shared_first_name_asks_who_and_releases_with_the_choice(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "shared-first-name")
    held = next(o for o in item["changeset"]["ops"] if o["status"] == "held")
    ask = held["ask"]
    assert ask["about"] == "held-op" and ask["name"] and len(ask["options"]) == 2
    choice = ask["options"][0]["id"]
    url = f"{base}/changesets/{item['changeset']['id']}/ops/{held['index']}/release"
    assert client.post(url, json={"person": choice}).status_code == 200
    after = next(i for i in client.get(f"{base}/changes").json() if i["id"] == item["id"])
    assert after["changeset"]["ops"][held["index"]]["status"] == "applied"


def test_a_source_shows_the_pasted_text(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "close-action")
    src = client.get(f"{base}/sources/{item['source']}").json()
    assert src["trust"] == "untrusted"
    quote = item["changeset"]["ops"][0]["evidence"]["quote"]
    assert quote in src["text"]
    assert client.get(f"{base}/sources/SRC-999").status_code == 404


def test_runtime_config_carries_ui_settings(api):
    client, base, _ = api
    rc = client.get(f"{base}/runtime-config").json()
    assert rc["shortcuts"]["next"] and rc["narrow_below_px"] >= 320 and rc["pm"]
    assert rc["demo"] is True and rc["shortcuts"]["ask"]  # the demo workspaces are labeled as made up
    assert rc["feedback_to"] and rc["feedback_to"].endswith("@example.com")


def test_mark_sent_can_be_undone(api):
    client, base, _ = api
    editor = by_role("Editor")["id"]
    before = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor)
    sent = client.post(f"{base}/followups/{editor}/mark-sent", json={}).json()
    body = {"question_ids": sent["question_ids"], "action_ids": sent["action_ids"]}
    assert client.post(f"{base}/followups/{editor}/unmark-sent", json=body).status_code == 200
    after = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor)
    assert after["to_send"] == before["to_send"] and after["message"] == before["message"]


def test_answering_a_who_question_releases_the_item(api):
    client, base, worker = api
    item = hand_in_case(client, base, worker, "shared-first-name")
    held = next(o for o in item["changeset"]["ops"] if o["status"] == "held")
    url = f"{base}/questions/{held['ask']['id']}/answer"
    assert client.post(url, json={"text": "no"}).status_code == 422
    assert client.post(url, json={"person": held["ask"]["options"][1]["id"]}).status_code == 200
    after = next(i for i in client.get(f"{base}/changes").json() if i["id"] == item["id"])
    assert after["changeset"]["ops"][held["index"]]["status"] == "applied"


def test_the_pm_marks_an_action_done_and_back(api):
    client, base, _ = api
    action = next(a for a in fixture_records(DEMO_B, "action") if a.get("status", "open") == "open")
    assert client.post(f"{base}/actions/{action['id']}/status", json={"status": "done"}).status_code == 200
    assert client.app.state.store.read().get("action", action["id"]).data["status"] == "done"
    client.post(f"{base}/actions/{action['id']}/status", json={"status": "open"})
    assert client.app.state.store.read().get("action", action["id"]).data["status"] == "open"


def test_a_stopped_request_can_be_tried_again(api):
    client, base, worker = api
    from engine.ai.task import AiError

    def fail(task):
        raise AiError("quota", "out of credit")

    set_responder(fail)
    req = client.post(f"{base}/handin", json={"note": "file this"}).json()["request"]
    worker.run_pending()
    item = next(i for i in client.get(f"{base}/changes").json() if i["id"] == req)
    assert item["state"] == "needs_you" and item["waiting"]
    set_responder(None)
    assert client.post(f"{base}/requests/{req}/retry").status_code == 200
    worker.run_pending()
    assert next(i for i in client.get(f"{base}/changes").json() if i["id"] == req)["state"] == "review"
    assert client.post(f"{base}/requests/{req}/retry").status_code == 409


def _stopped_request(client, base, worker):
    from engine.ai.task import AiError

    def fail(task):
        raise AiError("quota", "out of credit")

    set_responder(fail)
    req = client.post(f"{base}/handin", json={"note": "file this"}).json()["request"]
    worker.run_pending()
    set_responder(None)
    return req


def _item(client, base, req):
    return next(i for i in client.get(f"{base}/changes").json() if i["id"] == req)


def test_a_stopped_request_can_be_dismissed_and_put_back(api):
    client, base, worker = api
    req = _stopped_request(client, base, worker)
    item = _item(client, base, req)
    assert item["state"] == "needs_you" and not item["dismissed"]
    assert client.get(f"{base}/status").json()["requests"]["needs_you"] == 1
    gone = client.post(f"{base}/requests/{req}/dismiss", json={"read_version": item["version"]})
    assert gone.status_code == 200
    after = _item(client, base, req)
    assert after["state"] == "done" and after["dismissed"] and after["waiting"] == item["waiting"]
    assert client.get(f"{base}/status").json()["requests"]["needs_you"] == 0
    assert client.post(f"{base}/requests/{req}/dismiss", json={"read_version": after["version"]}).status_code == 409
    assert client.post(f"{base}/requests/{req}/retry").status_code == 409
    ledger = [
        e for e in client.app.state.store.read().ledger() if e["record_id"] == req and e["op"] == "request.dismiss"
    ]
    assert {e["field"] for e in ledger} >= {"state", "dismissed"}
    # An undo with a stale version is refused; with the version the dismissal returned, the old state comes back.
    assert client.post(f"{base}/requests/{req}/undismiss", json={"read_version": item["version"]}).status_code == 409
    back = client.post(f"{base}/requests/{req}/undismiss", json={"read_version": gone.json()["version"]})
    assert back.status_code == 200
    restored = _item(client, base, req)
    assert restored["state"] == "needs_you" and not restored["dismissed"]
    assert (
        client.post(f"{base}/requests/{req}/undismiss", json={"read_version": back.json()["version"]}).status_code
        == 409
    )
    assert client.post(f"{base}/requests/{req}/retry").status_code == 200


def test_a_request_that_is_not_stopped_cannot_be_dismissed(api):
    client, base, _ = api
    req = client.post(f"{base}/handin", json={"note": "file this"}).json()["request"]
    item = _item(client, base, req)
    assert item["state"] == "queued"
    assert client.post(f"{base}/requests/{req}/dismiss", json={"read_version": item["version"]}).status_code == 409
    assert client.post(f"{base}/requests/NOPE-1/dismiss", json={"read_version": 1}).status_code == 404


def test_a_reply_is_handed_in_against_its_question_and_closes_it(api):
    client, base, worker = api
    c = case("answer-question")
    qid = next(e["id"] for e in c["expect"] if e.get("op") == "question.done")
    set_responder(lambda task: json.dumps(c["stub_answer"]))
    r = client.post(f"{base}/questions/{qid}/reply", json={"text": c["pasted"]})
    assert r.status_code == 200
    req = client.app.state.store.read().get("request", r.json()["request"]).data
    assert qid in req["note"] and req["source"]
    worker.run_pending()
    assert client.app.state.store.read().get("question", qid).data["status"] == "answered"
    assert client.post(f"{base}/questions/{qid}/reply", json={"text": "again"}).status_code == 409


def test_people_can_be_added_renamed_and_removed_when_unused(api):
    client, base, _ = api
    new = client.post(f"{base}/people", json={"full_name": "Pat Example", "role": "Proofreader"}).json()["id"]
    assert client.post(f"{base}/people", json={"full_name": "pat example"}).status_code == 409
    assert client.post(f"{base}/people/{new}", json={"full_name": "Pat Sample"}).status_code == 200
    names = {p["id"]: p["name"] for p in client.get(f"{base}/people").json()}
    assert names[new] == "Pat Sample"
    assert client.post(f"{base}/people/{new}/remove").status_code == 200
    assert new not in {p["id"] for p in client.get(f"{base}/people").json()}
    assert client.post(f"{base}/people/{new}/restore").status_code == 200
    assert new in {p["id"] for p in client.get(f"{base}/people").json()}


def test_a_first_name_set_on_the_person_is_what_the_copied_message_greets_them_by(api):
    client, base, _ = api
    editor = by_role("Editor")
    greeting = "Hi Greeted-Name,"
    assert client.post(f"{base}/people/{editor['id']}", json={"first_name": "Greeted-Name"}).status_code == 200
    row = next(p for p in client.get(f"{base}/people").json() if p["id"] == editor["id"])
    assert row["first_name"] == "Greeted-Name"
    sec = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor["id"])
    assert sec["message"].startswith(greeting)
    assert client.post(f"{base}/people/{editor['id']}", json={"first_name": None}).status_code == 200
    sec = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor["id"])
    assert sec["message"].startswith("Hi " + editor["full_name"].split()[0])


def test_a_person_in_use_cannot_be_removed_and_a_rename_shows_everywhere(api):
    client, base, _ = api
    editor = by_role("Editor")
    r = client.post(f"{base}/people/{editor['id']}/remove")
    assert r.status_code == 409 and "left instead" in r.json()["detail"]
    client.post(f"{base}/people/{editor['id']}", json={"full_name": "Renamed Editor"})
    sec = next(s for s in client.get(f"{base}/followups").json() if s["person"] == editor["id"])
    assert sec["name"] == "Renamed Editor" and sec["message"].startswith("Hi Renamed")
    pm = next(p for p in client.get(f"{base}/people").json() if p["is_pm"])
    assert client.post(f"{base}/people/{pm['id']}/remove").status_code == 409


def test_projects_can_be_added_and_edited(api):
    client, base, _ = api
    owner = by_role("Editor")["id"]
    statuses = next(v for v in client.get(f"{base}/lists").json() if v["name"] == "project-status")["values"]
    body = {"name": "Second title", "target": "2027-03-01", "owner": owner, "status": statuses[0]}
    prj = client.post(f"{base}/projects", json=body).json()["id"]
    assert client.post(f"{base}/projects", json={"name": "second title"}).status_code == 409
    assert client.post(f"{base}/projects", json={"name": "X", "owner": "PER-999"}).status_code == 404
    off_list = client.post(f"{base}/projects/{prj}", json={"status": "Writing"})
    assert off_list.status_code >= 400 and "isn't on the list" in off_list.text  # a status comes from its list
    assert client.post(f"{base}/lists/project-status/add", json={"value": "Writing"}).status_code == 200
    assert client.post(f"{base}/projects/{prj}", json={"status": "Writing"}).status_code == 200
    view = next(p for p in client.get(f"{base}/projects").json() if p["id"] == prj)
    assert view["status"] == "Writing" and view["target"] == "2027-03-01" and view["owner"] == owner
    priorities = next(v for v in client.get(f"{base}/lists").json() if v["name"] == "project-priority")["values"]
    assert client.post(f"{base}/projects/{prj}", json={"priority": priorities[0]}).status_code == 200
    assert next(p for p in client.get(f"{base}/projects").json() if p["id"] == prj)["priority"] == priorities[0]
    assert client.post(f"{base}/projects/{prj}", json={"priority": "Whenever"}).status_code >= 400
    assert client.post(f"{base}/projects/{prj}/remove").status_code == 200
    in_use = fixture_records(DEMO_B, "project")[0]["id"]
    assert client.post(f"{base}/projects/{in_use}/remove").status_code == 409


def _file_notes(client, base, worker, ops) -> None:
    set_responder(lambda task: json.dumps({"summary": "Filed.", "ops": ops}))
    assert client.post(f"{base}/handin", json={"note": "file these"}).status_code == 200
    assert worker.run_pending() == 1


def test_notes_are_listed_newest_first_with_their_project_and_trust(api):
    client, base, worker = api
    project = fixture_records(DEMO_B, "project")[0]
    assert client.get(f"{base}/notes").json() == []
    _file_notes(client, base, worker, [{"op": "note", "text": "first one", "project": project["id"]}])
    _file_notes(client, base, worker, [{"op": "note", "text": "second one"}])
    notes = client.get(f"{base}/notes").json()
    assert [n["text"] for n in notes] == ["second one", "first one"]
    assert notes[1]["project"] == project["id"] and notes[1]["project_name"] == project["name"]
    assert notes[0]["project"] is None and notes[0]["project_name"] is None
    assert all(n["created_at"] and n["trust"] == "trusted" for n in notes)


def test_a_filed_note_says_which_project_it_went_under(api):
    client, base, worker = api
    project = fixture_records(DEMO_B, "project")[0]
    _file_notes(
        client,
        base,
        worker,
        [{"op": "note", "text": "under", "project": project["id"]}, {"op": "note", "text": "loose"}],
    )
    item = client.get(f"{base}/changes").json()[0]
    under, loose = item["changeset"]["ops"]
    assert under["meta"]["project"] == project["name"] and loose["meta"]["project"] is None


def test_status_says_when_the_assistant_is_not_ready(api, tmp_path, monkeypatch):
    client, base, worker = api
    # The demo workspace runs on the built-in stand-in, and says so.
    assert client.get(f"{base}/status").json()["ai"] == {"state": "stand_in", "detail": None}
    # From here the stand-in plays a real account. Never tested: no passing connection test yet.
    monkeypatch.setattr("engine.ai.smoke.stand_in", lambda cfg: False)
    assert client.get(f"{base}/status").json()["ai"] == {"state": "untested", "detail": None}
    from engine.ai.smoke import record, smoke_test

    set_responder(connection_answer)
    record(worker.ws, smoke_test(worker.cfg, env={}))
    assert client.get(f"{base}/status").json()["ai"] == {"state": "ok", "detail": None}
    # A request that ends with the account refusing its key makes the assistant "failing", with the provider's reason.
    from engine.ai.task import AiError

    def refuse(task):
        raise AiError("auth", 'HTTP 401: {"error": {"message": "User not found.", "code": 401}}')

    set_responder(refuse)
    client.post(f"{base}/handin", json={"note": "file this"})
    worker.run_pending()
    assert client.get(f"{base}/status").json()["ai"] == {"state": "failing", "detail": "User not found"}
    # A later connection test that passes clears it.
    set_responder(connection_answer)
    record(worker.ws, smoke_test(worker.cfg, env={}))
    assert client.get(f"{base}/status").json()["ai"]["state"] == "ok"


def _record_run(store, cost: float, when) -> None:
    from engine.storage import WriteContext

    with store.transaction() as tx:
        tx.create(
            "run",
            {
                "request": "REQ-1",
                "task": "notes",
                "provider": "stub",
                "model": "stub",
                "tier": "routine",
                "cost_usd": cost,
                "outcome": "ok",
                "started_at": when.isoformat(),
            },
            WriteContext("engine", "trusted", "test"),
        )


def test_status_reports_what_the_assistant_has_cost_and_when_a_limit_is_near(api):
    from datetime import UTC, datetime, timedelta

    client, base, _ = api
    store = client.app.state.store
    quiet = client.get(f"{base}/status").json()["spend"]
    assert quiet["today_usd"] == 0 and quiet["month_usd"] == 0 and not quiet["warn"]
    assert quiet["per_day_usd"] > 0 and quiet["per_month_usd"] > 0
    now = datetime.now(UTC)
    _record_run(store, 0.1, now)
    _record_run(store, 0.2, now - timedelta(days=40))  # last month or earlier: counts toward neither total
    spend = client.get(f"{base}/status").json()["spend"]
    assert spend["today_usd"] == pytest.approx(0.1) and spend["month_usd"] == pytest.approx(0.1)
    assert not spend["warn"] and not spend["warn_today"] and not spend["warn_month"]
    # A run that brings the day to its warning share warns for the day only.
    _record_run(store, spend["per_day_usd"] * 0.8, now)
    near = client.get(f"{base}/status").json()["spend"]
    assert near["warn"] and near["warn_today"] and not near["warn_month"]


@pytest.fixture
def gated(tmp_path):
    """A workspace where every run is priced above the amount to confirm, so each waits for the PM's go."""
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    flags = {
        "server.base_path": "/",
        "storage.backups.targets": [{"path": str(tmp_path / "offsite")}],
        "storage.backups.automatic": False,
        "ai.prices.stub/default": {"input_per_million": 50.0, "output_per_million": 50.0},
        "ai.budgets.confirm_above_usd": 0.001,
        "ai.budgets.per_run_usd": 10.0,
    }
    cfg = ws.config(env={}, flags=flags)
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.worker
    set_responder(None)


def _held_for_cost(client, base, worker):
    set_responder(lambda task: json.dumps({"summary": "Filed as a note.", "ops": [{"op": "note", "text": "Noted."}]}))
    req = client.post(f"{base}/handin", json={"note": "file this"}).json()["request"]
    worker.run_pending()
    return _item(client, base, req)


def test_a_run_held_for_its_cost_shows_its_estimate_and_goes_on_the_go(gated):
    client, base, worker = gated
    item = _held_for_cost(client, base, worker)
    assert item["state"] == "needs_you" and item["approval"] == "required" and not item["stage_task"]
    # The line rounds the full estimate to cents; the field is kept to a tenth of a cent, so they agree within a cent.
    shown = float(re.search(r"\$(\d+\.\d\d)", item["waiting"]).group(1))
    assert item["estimate_usd"] > 0.001 and abs(shown - item["estimate_usd"]) < 0.006
    assert client.post(f"{base}/requests/{item['id']}/retry").status_code == 409
    assert client.post(f"{base}/requests/{item['id']}/go", json={"read_version": item["version"]}).status_code == 200
    assert _item(client, base, item["id"])["approval"] == "granted"
    assert worker.run_pending() == 1
    assert _item(client, base, item["id"])["state"] == "review"


def test_a_run_held_for_its_cost_can_be_dismissed_and_put_back(gated):
    client, base, worker = gated
    item = _held_for_cost(client, base, worker)
    gone = client.post(f"{base}/requests/{item['id']}/dismiss", json={"read_version": item["version"]})
    assert gone.status_code == 200
    after = _item(client, base, item["id"])
    assert after["state"] == "done" and after["dismissed"] and after["approval"] == "required"
    back = client.post(f"{base}/requests/{item['id']}/undismiss", json={"read_version": gone.json()["version"]})
    assert back.status_code == 200
    restored = _item(client, base, item["id"])
    assert restored["state"] == "needs_you" and not restored["dismissed"] and restored["approval"] == "required"


def test_marking_an_action_done_credits_its_owners_and_records_the_pm_as_the_reporter(api):
    """The person's path: they tick their own action on Today. The work is credited to its owners, and they are the
    one who said it was done."""
    client, base, _ = api
    store = client.app.state.store
    action = next(a for a in store.read().list("action") if a.data["status"] == "open" and a.data.get("owners"))
    owners = [o["person"] for o in action.data["owners"]]
    assert client.post(f"{base}/actions/{action.id}/status", json={"status": "done"}).status_code == 200
    data = store.read().get("action", action.id).data
    pm = next(s["person"] for s in client.get(f"{base}/followups").json() if s["is_pm"])
    assert data["status"] == "done" and data["done_by"] == owners and data["reported_by"] == pm
