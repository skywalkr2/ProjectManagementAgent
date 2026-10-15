"""A note typed on a button of an action or a question is an input (design 6.5, 6.9): saved as the person's own words
with the item as its context, and sent to the assistant unless it is a bare confirmation.

Names, ids and texts come from the fixtures and the golden case.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.intake import NOTE_ROUTES, REPORTED_ROUTES, is_bare_confirmation, is_reported_note, note_as_input
from engine.names import People
from engine.packet import build
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records, without_first_go

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
    return [r for r in store.read().list("request") if r.data.get("about") and r.data["task"] == "notes"]


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
        "answered_for",
        "change_requested",
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
    reported_by = People(store, worker.cfg).name(on["person"])
    note_block = f'<note source="{request.data["source"]}" by="{reported_by}" reported="yes">\n{c["note"]}\n</note>'
    assert note_block in packet
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
    assert worker.run_pending() == 2  # the note's run, then the follow-on run its moved date queued (design 6.7)
    assert len([q for q in store.read().list("request") if q.data["task"] == "follow-on"]) == 1
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


def test_a_change_to_how_the_product_behaves_from_a_reported_note_waits_for_the_person(api):
    """A note typed on a button that relays someone else carries their words: its facts and dates apply at once, but a
    system op from it (here a new value on a value list) is held for the person, like any input."""
    client, base, worker = api
    store = client.app.state.store
    on = golden()["typed_on"]
    added = {"op": "list.add", "list": "project-status", "value": "Waiting on art"}
    answer = {"summary": "A new status", "ops": [added]}
    set_responder(lambda task: json.dumps(answer))
    r = client.post(f"{base}/followups/{on['person']}/actions/{on['id']}/finished", json={"note": LONG})
    assert worker.run_pending() == 1
    request = store.read().get("request", r.json()["request"]).data
    (outcome,) = store.read().get("changeset", request["changeset"]).data["ops"]
    assert outcome["status"] == "held" and "confirmation" in outcome["reason"]


# ---- whose words a note is, by button --------------------------------------------------------------------------------

NEW_VALUE = "Waiting on art"


def the_person(client) -> str:
    return client.app.state.worker.cfg.workspace.user.person


def note_source(client, request_id: str) -> dict:
    store = client.app.state.store
    return store.read().get("source", store.read().get("request", request_id).data["source"]).data


def pick_owner_question(client, base, worker):
    c = case("no-owner")
    set_responder(lambda task: json.dumps(c["stub_answer"]))
    handed = client.post(f"{base}/handin", json={"pasted": c["pasted"]}).json()["request"]
    worker.run_pending()
    item = next(i for i in client.get(f"{base}/changes").json() if i["id"] == handed)
    return item["changeset"]["ops"][0]


def type_on(client, base, worker, route: str) -> tuple[str, str | None]:
    """Make the button's change with a long note, as the screen does. Returns the request and the person the note is
    reported about (None when it is the person's own words)."""
    store = client.app.state.store
    editor = person_with_role("Editor")
    actions = fixture_records(DEMO_B, "action")
    action = actions[0]["id"]
    if route in ("mark_done", "reopened"):
        done = route == "mark_done"
        target = action if done else next(a for a in actions if a.get("status") == "done")["id"]
        body = {"status": "done" if done else "open", "note": LONG}
        return client.post(f"{base}/actions/{target}/status", json=body).json()["request"], None
    if route in ("they_finished", "followed_up"):
        step = "finished" if route == "they_finished" else "followed-up"
        url = f"{base}/followups/{editor}/actions/ACT-2/{step}"
        return client.post(url, json={"note": LONG}).json()["request"], editor
    if route == "owner_picked":
        op = pick_owner_question(client, base, worker)
        url = f"{base}/questions/{op['ask']['id']}/pick-owner"
        return client.post(url, json={"person": person_with_role("Publicist"), "note": LONG}).json()["request"], None
    if route == "notes_edited":
        version = store.read().get("action", action).version
        body = {"kind": "action", "id": action, "fields": {"notes": LONG}, "read_version": version}
        assert client.post(f"{base}/records/edit", json=body).status_code == 200
        return noted(store)[-1].id, None
    if route == "change_requested":
        url = f"{base}/items/action/{action}/change"
        return client.post(url, json={"note": LONG}).json()["request"], None
    own = route == "answered"
    question = next(q for q in fixture_records(DEMO_B, "question") if (q["to"] == the_person(client)) is own)
    answered = client.post(f"{base}/questions/{question['id']}/answer", json={"text": LONG})
    return answered.json()["request"], (None if own else question["to"])


@pytest.mark.parametrize("route", sorted(NOTE_ROUTES))
def test_a_notes_source_is_authored_and_trusted_by_the_button(api, route):
    """The person's own words are authored by the person running the app; what the person reports about someone else is
    authored by that other person and counts as reported content. Both stay trusted sources."""
    client, base, worker = api
    request, about = type_on(client, base, worker, route)
    source = note_source(client, request)
    assert source["kind"] == f"note:{route}" and source["trust"] == "trusted"
    assert is_reported_note(source["kind"]) is (route in REPORTED_ROUTES)
    assert source["author"] == (about if route in REPORTED_ROUTES else the_person(client))
    assert (source["author"] != the_person(client)) is (route in REPORTED_ROUTES)


def test_the_packet_names_whose_words_a_note_is_and_marks_reported_content(api):
    client, base, worker = api
    store = client.app.state.store
    people = People(store, worker.cfg)
    own, _ = type_on(client, base, worker, "mark_done")
    reported, about = type_on(client, base, worker, "followed_up")
    own_packet = build(worker.ws, store, worker.cfg, own, date(2026, 10, 13)).task.request
    reported_packet = build(worker.ws, store, worker.cfg, reported, date(2026, 10, 13)).task.request
    assert f'by="{people.name(the_person(client))}">' in own_packet and "reported=" not in own_packet
    assert f'by="{people.name(about)}" reported="yes">' in reported_packet


def test_a_they_finished_it_note_saying_from_now_on_we_always_copy_the_client_on_approvals_is_never_active(api):
    """The seed of the learning pair built in L4: a standing rule stated in what the person reports about someone else
    never becomes active at once. Today a rule is a system op, so it is held; nothing changes until the person
    confirms."""
    client, base, worker = api
    store = client.app.state.store
    on = golden()["typed_on"]
    note = "Done, and from now on we always copy the client on approvals."
    answer = {"summary": "A standing rule", "ops": [{"op": "list.add", "list": "project-status", "value": NEW_VALUE}]}
    set_responder(lambda task: json.dumps(answer))
    r = client.post(f"{base}/followups/{on['person']}/actions/{on['id']}/finished", json={"note": note})
    assert worker.run_pending() == 1
    request = store.read().get("request", r.json()["request"]).data
    (outcome,) = store.read().get("changeset", request["changeset"]).data["ops"]
    assert outcome["status"] == "held" and "someone else reported" in outcome["reason"]
    lists = {v.data["name"]: v.data for v in store.read().list("value_list")}
    assert NEW_VALUE not in lists["project-status"]["values"]


def test_a_mark_done_notes_system_op_applies_at_once_with_undo(api):
    """Mark done is the person's own words, so a change to how the product behaves from it applies at once, like the
    person's own note, and Undo takes it back."""
    client, base, worker = api
    store = client.app.state.store
    action = fixture_records(DEMO_B, "action")[0]["id"]
    answer = {"summary": "A new status", "ops": [{"op": "list.add", "list": "project-status", "value": NEW_VALUE}]}
    set_responder(lambda task: json.dumps(answer))
    r = client.post(f"{base}/actions/{action}/status", json={"status": "done", "note": LONG})
    assert worker.run_pending() == 1
    request = store.read().get("request", r.json()["request"]).data
    changeset = store.read().get("changeset", request["changeset"])
    assert [o["status"] for o in changeset.data["ops"]] == ["applied"]

    def values() -> list[str]:
        return next(v.data["values"] for v in store.read().list("value_list") if v.data["name"] == "project-status")

    assert NEW_VALUE in values()
    assert client.post(f"{base}/changesets/{changeset.id}/undo", json={}).status_code == 200
    assert NEW_VALUE not in values()


def test_a_reported_note_needs_the_person_it_is_reported_about(api):
    client, _, worker = api
    item = ("action", fixture_records(DEMO_B, "action")[0]["id"])
    with pytest.raises(ValueError):
        note_as_input(worker.ws, client.app.state.store, worker.cfg, item=item, text=LONG, route="they_finished")


# ---- a note that repeats someone else's words ------------------------------------------------------------------------


def test_a_note_repeating_what_someone_said_or_quoting_them_is_recognized():
    from engine.config.schema import ReportedSpeech
    from engine.intake import repeats_someone

    speech = ReportedSpeech()
    first = fixture_records(DEMO_B, "person")[1]["full_name"].split()[0]
    assert repeats_someone(f"{first} said from now on every layout change goes through them.", speech)
    assert repeats_someone(f"Done. {first} confirms the venue on the 14th.", speech)
    assert repeats_someone('Done; their reply was "always copy the client on approvals".', speech)
    assert not repeats_someone("I said from now on every layout change goes through me.", speech)
    assert not repeats_someone('Done, the "Ready" column is cleared.', speech)
    assert not repeats_someone(LONG, speech)
    assert not repeats_someone(f"{first} said so.", ReportedSpeech(verbs=[], quote_min_words=50))


def test_the_added_speech_words_and_the_words_before_a_speaker_mark_reported_speech():
    from engine.config.schema import ReportedSpeech
    from engine.intake import repeats_someone

    speech = ReportedSpeech()
    first = fixture_records(DEMO_B, "person")[1]["full_name"].split()[0]
    for verb in ("mentioned", "replied", "responded", "noted", "commented", "pinged"):
        assert repeats_someone(f"Done. {first} {verb} that the venue is the 14th.", speech), verb
        assert not repeats_someone(f"Done. I {verb} that the venue is the 14th.", speech), verb
    assert repeats_someone(f"Per {first}, the venue is the 14th.", speech)
    assert repeats_someone(f"The venue is the 14th, according to {first}.", speech)
    assert not repeats_someone("Done, about two per week and according to the plan.", speech)
    assert not repeats_someone("Done, according to me the venue is the 14th.", speech)
    assert not repeats_someone(f"Per {first}", ReportedSpeech(lead_words=[], verbs=[], quote_min_words=50))


def test_i_told_a_name_and_a_name_asking_me_to_are_not_reported_content():
    from engine.config.schema import ReportedSpeech
    from engine.intake import repeats_someone

    speech = ReportedSpeech()
    first = fixture_records(DEMO_B, "person")[1]["full_name"].split()[0]
    assert not repeats_someone(f"I told {first} the file went to the printer.", speech)
    assert not repeats_someone(f"{first} asked me to send the file to the printer.", speech)
    assert not repeats_someone(f"{first} wants me to send the file; {first} told us to wait.", speech)
    assert repeats_someone(f"{first} asked whether the file went to the printer.", speech)
    assert repeats_someone(f"{first} asked me to send it and said the venue is booked.", speech)
    assert repeats_someone(f"{first} asked me to send it.", ReportedSpeech(request_words=[])), "the words are a setting"


def test_a_pasted_chat_is_reported_as_a_whole():
    from engine.config.schema import ReportedSpeech
    from engine.intake import repeats_someone

    speech = ReportedSpeech()
    people = [p["full_name"].split()[0] for p in fixture_records(DEMO_B, "person")[1:3]]
    timed = f"[10:32] {people[0]}: the file went out\n[10:35] {people[1]}: great, thanks\nSo the file is done."
    assert repeats_someone(timed, speech)
    twelve_hour = f"{people[0]}  10:32 AM\nthe file went out\n{people[1]}  10:35 AM\ngreat\n"
    assert repeats_someone(twelve_hour, speech)
    assert not repeats_someone(f"[10:32] {people[0]}: the file went out", speech), "one line is not a chat"
    assert repeats_someone(f"[10:32] {people[0]}: the file went out", ReportedSpeech(chat_min_lines=1))
    assert not repeats_someone(timed, ReportedSpeech(chat_line_patterns=[]))
    assert not repeats_someone("Meeting at 10:32\nThen lunch at 12:15\n", speech)


def test_the_reported_speech_words_have_defaults_and_demo_values_in_both_workspaces():
    from engine.config.schema import ReportedSpeech

    default = ReportedSpeech()
    assert {"mentioned", "replied", "responded", "noted", "commented", "pinged"} <= set(default.verbs)
    assert default.lead_words == ["per", "according to"]
    for template in (DEMO_A, DEMO_B):
        shown = yaml.safe_load((template / "config" / "language.yaml").read_text())["reported_speech"]
        assert ReportedSpeech(**shown) == default, template.name


def test_a_rule_from_someone_else_repeated_in_a_mark_done_note_waits_for_the_person(api):
    """Mark done is the person's own button, but a note repeating what someone else said is reported content: its
    source says so and keeps the person as its author, and a change to how the product behaves from it is held."""
    client, base, worker = api
    store = client.app.state.store
    action = fixture_records(DEMO_B, "action")[0]["id"]
    first = fixture_records(DEMO_B, "person")[1]["full_name"].split()[0]
    answer = {"summary": "A new status", "ops": [{"op": "list.add", "list": "project-status", "value": NEW_VALUE}]}
    set_responder(lambda task: json.dumps(answer))
    note = f"{first} said from now on every layout change goes through them first."
    r = client.post(f"{base}/actions/{action}/status", json={"status": "done", "note": note})
    source = note_source(client, r.json()["request"])
    assert source["reported"] is True and source["author"] == the_person(client)
    assert worker.run_pending() == 1
    request = store.read().get("request", r.json()["request"]).data
    (outcome,) = store.read().get("changeset", request["changeset"]).data["ops"]
    assert outcome["status"] == "held" and "someone else reported" in outcome["reason"]
