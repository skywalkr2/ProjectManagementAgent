"""A note typed on a button of an action or a question is an input (design 6.5, 6.9): saved as the person's own words
with the item as its context, and sent to the assistant unless it is a bare confirmation.

Names, ids and texts come from the fixtures and the golden case.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.intake import NOTE_ROUTES, is_bare_confirmation, note_as_input
from engine.packet import build
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records, without_first_go

TOKEN = "note-token"


def golden() -> dict:
    return next(c for c in load_cases(DEMO_B) if c["id"] == "they-finished-note")


def case(case_id: str) -> dict:
    return next(c for c in load_cases(DEMO_B) if c["id"] == case_id)


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.worker
    set_responder(None)


def person_with_role(role: str) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


def noted(store) -> list:
    """The notes work queued about an action or a question."""
    return [r for r in store.read().list("request") if r.data.get("about")]


LINK = fixture_records(DEMO_B, "project")[0]["links"][0]["url"]
HOST = LINK.split("//")[1].split("/")[0]
LONG = "The reviewer list is final and the printer proof is expected on a later day than planned."


# ---- the rule --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "bare"),
    [
        ("", True),
        ("   ", True),
        ("Done, thanks.", True),
        ("ok sent it", True),
        ("Done, sent it today", False),  # four words
        (f"see {LINK}", False),  # a link makes it count
        (f"see www.{HOST}", False),
        (f"see {HOST}/page", False),
        (f"mail me@{HOST}", True),  # an address is not a link
    ],
)
def test_a_note_under_four_words_with_no_link_is_a_bare_confirmation(text, bare):
    assert is_bare_confirmation(text, 4) is bare


def test_the_word_count_comes_from_the_setting(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    assert ws.config(env={}).language.bare_confirmation_words == 4
    assert ws.config(env={}, flags={"language.bare_confirmation_words": 2}).language.bare_confirmation_words == 2


# ---- the helper ------------------------------------------------------------------------------------------------------


def test_a_note_is_saved_as_the_persons_own_words_with_the_item_as_its_context(api):
    client, _, worker = api
    store = client.app.state.store
    action = fixture_records(DEMO_B, "action")[1]
    request_id = note_as_input(
        worker.ws, store, worker.cfg, item=("action", action["id"]), text=LONG, route="mark_done"
    )
    request = store.read().get("request", request_id).data
    source = store.read().get("source", request["source"]).data
    assert source["trust"] == "trusted" and source["kind"] == "note:mark_done"
    assert source["projects"] == [action["project"]]
    assert request["task"] == "notes" and request["origin"] == "pm" and request["state"] == "queued"
    assert request["about"] == {"kind": "action", "id": action["id"]} and request["project"] == action["project"]
    assert (worker.ws.sources_dir / f"{source['content_hash']}.txt").read_text(encoding="utf-8") == LONG


def test_a_bare_confirmation_makes_no_request_and_an_unknown_route_is_refused(api):
    client, _, worker = api
    store = client.app.state.store
    item = ("action", fixture_records(DEMO_B, "action")[0]["id"])
    assert note_as_input(worker.ws, store, worker.cfg, item=item, text="Done.", route="mark_done") is None
    assert noted(store) == [] and store.read().list("source") == []
    with pytest.raises(ValueError):
        note_as_input(worker.ws, store, worker.cfg, item=item, text=LONG, route="nowhere")


# ---- the routes ------------------------------------------------------------------------------------------------------


def test_a_note_under_four_words_with_no_link_makes_no_request(api):
    client, base, _ = api
    action = fixture_records(DEMO_B, "action")[0]["id"]
    r = client.post(f"{base}/actions/{action}/status", json={"status": "done", "note": "Done, thanks."})
    assert r.status_code == 200 and r.json()["request"] is None
    assert client.app.state.store.read().get("action", action).data["status"] == "done"
    assert noted(client.app.state.store) == []


def test_a_short_note_with_a_link_makes_a_request(api):
    client, base, _ = api
    action = fixture_records(DEMO_B, "action")[0]["id"]
    r = client.post(f"{base}/actions/{action}/status", json={"status": "done", "note": f"see {LINK}"})
    request = client.app.state.store.read().get("request", r.json()["request"]).data
    assert request["about"]["id"] == action and request["source"]


def test_mark_done_with_a_note_makes_one_request_about_the_action(api):
    client, base, _ = api
    store = client.app.state.store
    action = fixture_records(DEMO_B, "action")[0]["id"]
    r = client.post(f"{base}/actions/{action}/status", json={"status": "done", "note": LONG})
    (request,) = noted(store)
    assert r.json()["request"] == request.id and request.data["about"] == {"kind": "action", "id": action}
    assert store.read().get("source", request.data["source"]).data["kind"] == "note:mark_done"
    assert store.read().get("action", action).data["status"] == "done"


def test_they_finished_it_with_a_note_makes_one_request_and_the_note_survives_the_undo(api):
    client, base, _ = api
    store = client.app.state.store
    editor, action = person_with_role("Editor"), "ACT-2"
    r = client.post(f"{base}/followups/{editor}/actions/{action}/finished", json={"note": LONG})
    assert r.status_code == 200
    (request,) = noted(store)
    assert r.json()["request"] == request.id
    assert store.read().get("source", request.data["source"]).data["kind"] == "note:they_finished"
    # The toast's undo reopens the action; the person's words stay with the assistant.
    assert client.post(f"{base}/actions/{action}/status", json={"status": "open"}).status_code == 200
    assert store.read().get("action", action).data["status"] == "open"
    assert [x.id for x in noted(store)] == [request.id]
    assert store.read().get("source", request.data["source"]) is not None


def test_followed_up_with_a_note_makes_one_request_and_without_a_body_none(api):
    client, base, _ = api
    store = client.app.state.store
    editor, action = person_with_role("Editor"), "ACT-2"
    bare = client.post(f"{base}/followups/{editor}/actions/{action}/followed-up")
    assert bare.status_code == 200 and bare.json()["request"] is None and noted(store) == []
    r = client.post(f"{base}/followups/{editor}/actions/{action}/followed-up", json={"note": LONG})
    (request,) = noted(store)
    assert r.json()["request"] == request.id and request.data["about"]["id"] == action
    assert store.read().get("source", request.data["source"]).data["kind"] == "note:followed_up"


def test_picking_an_owner_with_a_note_makes_one_request_about_the_action(api):
    client, base, worker = api
    store = client.app.state.store
    c = case("no-owner")
    set_responder(lambda task: json.dumps(c["stub_answer"]))
    handed = client.post(f"{base}/handin", json={"pasted": c["pasted"]}).json()["request"]
    worker.run_pending()
    item = next(i for i in client.get(f"{base}/changes").json() if i["id"] == handed)
    (op,) = item["changeset"]["ops"]
    publicist = person_with_role("Publicist")
    r = client.post(f"{base}/questions/{op['ask']['id']}/pick-owner", json={"person": publicist, "note": LONG})
    assert r.status_code == 200
    (request,) = noted(store)
    assert request.data["about"] == {"kind": "action", "id": op["record"]["id"]}
    assert store.read().get("source", request.data["source"]).data["kind"] == "note:owner_picked"


def test_adding_to_an_actions_notes_hands_in_only_what_was_added(api):
    client, base, _ = api
    store = client.app.state.store
    action = fixture_records(DEMO_B, "action")[0]["id"]

    def edit(notes: str):
        version = store.read().get("action", action).version
        return client.post(
            f"{base}/records/edit",
            json={"kind": "action", "id": action, "fields": {"notes": notes}, "read_version": version},
        )

    assert edit("First line.").status_code == 200  # short and bare: kept on the record only
    assert noted(store) == []
    assert edit(f"First line. {LONG}").status_code == 200
    (request,) = noted(store)
    text = (
        client.app.state.worker.ws.sources_dir
        / f"{store.read().get('source', request.data['source']).data['content_hash']}.txt"
    ).read_text()
    assert text == LONG and store.read().get("source", request.data["source"]).data["kind"] == "note:notes_edited"
    stale = client.post(
        f"{base}/records/edit",
        json={"kind": "action", "id": action, "fields": {"notes": LONG + " More."}, "read_version": 1},
    )
    assert stale.status_code == 409 and len(noted(store)) == 1  # a refused edit hands nothing in


def test_answering_a_question_in_words_makes_one_request_about_the_question(api):
    client, base, _ = api
    store = client.app.state.store
    short, long = fixture_records(DEMO_B, "question")[:2]
    assert client.post(f"{base}/questions/{short['id']}/answer", json={"text": "Yes."}).json()["request"] is None
    r = client.post(f"{base}/questions/{long['id']}/answer", json={"text": LONG})
    (request,) = noted(store)
    assert r.json()["request"] == request.id and request.data["about"] == {"kind": "question", "id": long["id"]}
    assert store.read().get("question", long["id"]).data["answer"] == LONG


def test_every_route_a_note_can_be_typed_on_has_its_words_for_the_assistant():
    assert set(NOTE_ROUTES) == {
        "mark_done",
        "reopened",
        "they_finished",
        "followed_up",
        "owner_picked",
        "notes_edited",
        "answered",
    }


# ---- what the assistant reads ----------------------------------------------------------------------------------------


def test_the_packet_carries_the_item_and_the_note_as_the_persons_own_words(api):
    client, base, worker = api
    store = client.app.state.store
    c = golden()
    on = c["typed_on"]
    client.post(f"{base}/followups/{on['person']}/actions/{on['id']}/finished", json={"note": c["note"]})
    (request,) = noted(store)
    packet = build(worker.ws, store, worker.cfg, request.id, date(2026, 10, 13)).task.request
    action = store.read().get("action", on["id"]).data
    assert f'<note source="{request.data["source"]}">\n{c["note"]}\n</note>' in packet
    assert "<untrusted" in packet  # the record is shown as data
    context = json.loads(packet.split('<untrusted source="record">\n')[1].split("\n</untrusted>")[0])
    assert context["record"]["id"] == on["id"] and context["record"]["text"] == action["text"]
    assert context["record"]["status"] == "done" and context["the person"] == NOTE_ROUTES["they_finished"]
    assert context["record"]["due"] == str(action["due"])
    assert not any(
        part.startswith("<untrusted") and c["note"] in part for part in packet.split("\n\n")
    )  # the note is not wrapped as outside content


def test_a_note_with_a_link_and_a_new_date_comes_back_as_a_fact_and_a_moved_date_the_person_can_trust(api):
    """The person's path: They finished it with a note; the next run records the link as a fact, cites the saved note
    as its source, and moves the date, all as the person's own words."""
    client, base, worker = api
    store = client.app.state.store
    c = golden()
    on = c["typed_on"]
    set_responder(lambda task: json.dumps(c["stub_answer"]))
    r = client.post(f"{base}/followups/{on['person']}/actions/{on['id']}/finished", json={"note": c["note"]})
    assert worker.run_pending() == 1
    request = store.read().get("request", r.json()["request"]).data
    changeset = store.read().get("changeset", request["changeset"]).data
    assert changeset["trust"] == "trusted" and [o["status"] for o in changeset["ops"]] == ["applied", "applied"]
    (fact,) = store.read().list("fact")
    assert fact.data["source"] == request["source"] and fact.data["trust"] == "trusted"
    moved = c["stub_answer"]["ops"][1]
    assert str(store.read().get("action", moved["id"]).data["due"]) == moved["value"]
    # It shows with the person's other work as their own words.
    item = next(i for i in client.get(f"{base}/changes").json() if i["id"] == r.json()["request"])
    assert item["title"]["kind"] == "note"


def test_a_change_to_how_the_product_behaves_from_a_typed_note_waits_for_the_person(api):
    """A note typed on a button may carry someone else's reply: its facts and dates apply at once, but a system op from
    it (here a new value on a value list) is held for the person, like any input."""
    client, base, worker = api
    store = client.app.state.store
    on = golden()["typed_on"]
    answer = {"summary": "A new status", "ops": [{"op": "list.add", "list": "project-status", "value": "Waiting on art"}]}
    set_responder(lambda task: json.dumps(answer))
    r = client.post(f"{base}/followups/{on['person']}/actions/{on['id']}/finished", json={"note": LONG})
    assert worker.run_pending() == 1
    request = store.read().get("request", r.json()["request"]).data
    (outcome,) = store.read().get("changeset", request["changeset"]).data["ops"]
    assert outcome["status"] == "held" and "confirmation" in outcome["reason"]
