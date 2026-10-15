"""The obvious next step from what came in, as one click (design 6.7, 6.9): a new person answers "Who is this?", an
organization no record has is made with them, a contact detail from a signature always waits, and a project the
workspace lacks can be added, filed under another project or set aside as not a project.

Names, ids and texts come from the fixtures; the invented newcomers are about no one.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import PROJECT_WAITS, apply_as_person, release, undo
from engine.dispatcher import process
from engine.intake import hand_in
from engine.next_steps import (
    NewPersonForm,
    add_new_person,
    add_project,
    file_under,
    new_person_prefill,
    not_a_project,
    unfile_missing,
)
from engine.packet import build
from engine.storage import Store, StoreError, WriteContext
from engine.tasks import TASKS
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records
from tests.test_evaluate_harness import case_of, run_edited
from tests.test_knowledge_records import apply, source

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TOKEN = "next-steps-token"
PEOPLE = fixture_records(DEMO_B, "person")
ORGS = fixture_records(DEMO_B, "organization")
PROJECT = fixture_records(DEMO_B, "project")[0]
STRANGER = "Jordan " + "Pike"
NEW_ORG = "Fernhill " + "Press"
NEW_PROJECT = "Harvest " + "Fair"
RAW = f"{STRANGER} will book the venue. {STRANGER} will also print the signs. The {NEW_PROJECT} needs a plan."


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, ws, cfg
    set_responder(None)


def answers(*ops: dict) -> None:
    set_responder(lambda task: json.dumps({"summary": "Done.", "ops": list(ops)}))


def run(env, pasted: str) -> str:
    ws, cfg, store = env
    handed = hand_in(ws, store, note="", pasted=pasted, now=NOW)
    return process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)


def data(store, kind, record_id) -> dict:
    return store.read().get(kind, record_id).data


def outcomes(store, cs_id) -> list[dict]:
    return data(store, "changeset", cs_id)["ops"]


def signals(store, kind) -> list[dict]:
    return [s.data for s in store.read().list("signal") if s.data["kind"] == kind]


def two_actions_for(name: str) -> list[dict]:
    return [
        {
            "op": "action.add",
            "text": text,
            "owners": [name],
            "evidence": {"quote": f"{name} will {quote}"},
        }
        for text, quote in (("Book the venue", "book the venue"), ("Print the signs", "also print the signs"))
    ]


def held_for_a_stranger(env, *extra: dict) -> tuple[str, str]:
    """A run whose two actions wait on an unknown name: the changeset and its one question."""
    _, _, store = env
    answers(*two_actions_for(STRANGER), *extra)
    cs_id = run(env, RAW)
    first, second = outcomes(store, cs_id)[:2]
    assert first["status"] == second["status"] == "held" and first["question"] == second["question"]
    return cs_id, first["question"]


def people_named(store, name: str) -> list[dict]:
    return [p.data for p in store.read().list("person") if p.data["full_name"] == name]


# ---- a new person ----------------------------------------------------------------------------------------------------


def test_a_new_person_answers_the_question_releases_every_held_op_records_routed_and_undo_takes_it_all_back(env):
    ws, cfg, store = env
    cs_id, qid = held_for_a_stranger(env)
    form = NewPersonForm(
        full_name=STRANGER,
        first_name="Jo",
        org=NEW_ORG,
        role="Sign printer",
        contact_kind="Phone",
        contact_value="555 0100",
    )
    done = add_new_person(store, cfg, ws, qid, form, now=NOW)
    (person,) = people_named(store, STRANGER)
    assert person["first_name"] == "Jo" and person["role"] == "Sign printer"
    assert person["how_to_reach"] == {"phone": "555 0100"}
    assert data(store, "organization", person["org"])["name"] == NEW_ORG
    assert done.released == [0, 1] and done.changeset == cs_id
    for outcome in outcomes(store, cs_id)[:2]:
        assert outcome["status"] == "applied"
        owners = data(store, "action", outcome["records"][0]["id"])["owners"]
        assert [o["person"] for o in owners] == [done.person]
    assert data(store, "question", qid)["status"] == "answered"
    assert data(store, "changeset", cs_id)["status"] == "applied"
    (routed,) = signals(store, "routed")
    assert routed["refs"] == [cs_id, qid, done.person] and routed["note"] == STRANGER
    # The person is the author: a change of their own, already looked over, and none of it counts against the assistant.
    for change in done.changesets:
        saved = data(store, "changeset", change)
        assert saved["reviewed"] and saved["trust"] == "trusted"
    assert {e["actor"] for e in store.read().ledger() if e["kind"] == "person" and e["record_id"] == done.person} == {
        "pm"
    }
    # Undo: the released items first, then the changes that added the person, newest first.
    assert sorted(undo(store, cs_id, done.released).restored) == [0, 1]
    for change in done.changesets:
        assert undo(store, change).skipped == []
    assert people_named(store, STRANGER) == []
    assert [o.data["name"] for o in store.read().list("organization")] == [o["name"] for o in ORGS]
    assert signals(store, "undone") == []


def test_an_unknown_organization_is_made_once_and_a_known_name_or_alias_is_linked(env):
    ws, cfg, store = env
    known = ORGS[0]
    other = "Casey " + "Moor"
    _, qid = held_for_a_stranger(env)
    first = add_new_person(store, cfg, ws, qid, NewPersonForm(full_name=STRANGER, org=known["name"].upper()), now=NOW)
    assert data(store, "person", first.person)["org"] == known["id"]
    # An alias the person gave an organization is a known name too.
    with store.transaction() as tx:
        current = tx.get("organization", known["id"])
        tx.update(
            "organization",
            known["id"],
            {"aliases": ["The House"]},
            WriteContext("pm", "trusted", "test"),
            read_version=current.version,
        )
    _, other_q = _second_stranger(env, other)
    second = add_new_person(store, cfg, ws, other_q, NewPersonForm(full_name=other, org="the house"), now=NOW)
    assert data(store, "person", second.person)["org"] == known["id"]
    assert len(store.read().list("organization")) == len(ORGS)
    # An organization no record has is made once, however many people name it.
    third_name, fourth_name = "Robin " + "Vale", "Sky " + "Marsh"
    for name in (third_name, fourth_name):
        _, q = _second_stranger(env, name)
        add_new_person(store, cfg, ws, q, NewPersonForm(full_name=name, org=NEW_ORG), now=NOW)
    made = [o for o in store.read().list("organization") if o.data["name"] == NEW_ORG]
    assert len(made) == 1
    assert {p.data["org"] for p in store.read().list("person") if p.data["full_name"] in (third_name, fourth_name)} == {
        made[0].id
    }


def _second_stranger(env, name: str) -> tuple[str, str]:
    _, _, store = env
    answers(*two_actions_for(name))
    pasted = f"{name} will book the venue. {name} will also print the signs."
    cs_id = run(env, pasted)
    first = outcomes(store, cs_id)[0]
    assert first["status"] == "held"
    return cs_id, first["question"]


def test_a_confirmed_person_add_makes_its_unknown_organization_once_and_links_a_known_one(env):
    ws, cfg, store = env
    one, two, three = "Robin " + "Vale", "Sky " + "Marsh", "Dale " + "Reed"
    answers(
        *(
            {"op": "person.add", "full_name": n, "org": o}
            for n, o in ((one, NEW_ORG), (two, NEW_ORG), (three, ORGS[1]["name"].lower()))
        )
    )
    cs_id = run(env, f"{one}, {two} and {three} joined the thread.")
    assert [o["status"] for o in outcomes(store, cs_id)] == ["held", "held", "held"]
    for index in range(3):
        release(store, cfg, cs_id, index, ws=ws)
    orgs = {o.data["name"]: o.id for o in store.read().list("organization")}
    assert len(orgs) == len(ORGS) + 1
    by_name = {p.data["full_name"]: p.data["org"] for p in store.read().list("person")}
    assert by_name[one] == by_name[two] == orgs[NEW_ORG] and by_name[three] == ORGS[1]["id"]


def test_the_form_starts_with_the_name_as_written_what_a_proposed_person_gives_and_the_address_in_the_header(env):
    ws, cfg, store = env
    address = "jordan.pike@example.org"
    pasted = f"From: {STRANGER} <{address}>\nTo: {PEOPLE[0]['full_name']}\n\n{RAW}"
    answers(
        *two_actions_for(STRANGER),
        {"op": "person.add", "full_name": STRANGER, "org": NEW_ORG, "role": "Sign printer"},
    )
    cs_id = run(env, pasted)
    qid = outcomes(store, cs_id)[0]["question"]
    found = new_person_prefill(store, cfg, ws, qid)
    assert (found.full_name, found.first_name) == (STRANGER, "Jordan")
    assert (found.org, found.role) == (NEW_ORG, "Sign printer")
    assert (found.contact_kind, found.contact_value) == ("email", address)
    assert found.contact_kinds == ["email", "phone", "address"]
    # With nothing about them in the input the form starts with the name alone.
    cs_id, qid = _second_stranger(env, "Casey " + "Moor")
    blank = new_person_prefill(store, cfg, ws, qid)
    assert (blank.org, blank.role, blank.contact_value) == ("", "", "")


def test_a_new_person_needs_a_name_not_on_file_a_kind_from_the_list_and_an_open_question(env):
    ws, cfg, store = env
    _, qid = held_for_a_stranger(env)
    before = len(store.read().list("person"))
    for form, words in (
        (NewPersonForm(full_name="  "), "Write the person's name"),
        (NewPersonForm(full_name=PEOPLE[1]["full_name"].lower()), "already on file"),
        (NewPersonForm(full_name=STRANGER, contact_kind="pigeon", contact_value="coo"), "kind of contact"),
        (NewPersonForm(full_name=STRANGER, contact_value="555 0100"), "kind of contact"),
    ):
        with pytest.raises(StoreError, match=words):
            add_new_person(store, cfg, ws, qid, form, now=NOW)
    assert len(store.read().list("person")) == before and data(store, "question", qid)["status"] == "open"
    add_new_person(store, cfg, ws, qid, NewPersonForm(full_name=STRANGER), now=NOW)
    with pytest.raises(StoreError, match="isn't asking who"):
        add_new_person(store, cfg, ws, qid, NewPersonForm(full_name="Casey " + "Moor"), now=NOW)


def test_the_new_person_routes_prefill_answer_and_undo_in_order(api):
    client, store, ws, cfg = api
    env = (ws, cfg, store)
    cs_id, qid = held_for_a_stranger(env)
    form = client.get(f"/api/questions/{qid}/new-person").json()
    assert form["full_name"] == STRANGER and form["contact_kinds"] == cfg.workspace.contact_kinds
    done = client.post(
        f"/api/questions/{qid}/new-person",
        json={
            "full_name": form["full_name"],
            "org": NEW_ORG,
            "contact_kind": "email",
            "contact_value": "jp@example.org",
        },
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["released"] == [0, 1] and body["changeset"] == cs_id and len(body["undo"]) == 2
    assert client.post(f"/api/questions/{qid}/new-person", json={"full_name": "Casey " + "Moor"}).status_code == 409
    undone = client.post(f"/api/changesets/{cs_id}/undo", json={"ops": body["released"]})
    assert undone.status_code == 200 and sorted(undone.json()["restored"]) == [0, 1]
    for change in body["undo"]:
        assert client.post(f"/api/changesets/{change}/undo", json={}).json()["skipped"] == []
    assert people_named(store, STRANGER) == []
    assert client.post("/api/questions/Q-404/new-person", json={"full_name": "A"}).status_code == 404


# ---- a contact detail ------------------------------------------------------------------------------------------------


def contact(person: dict, **more) -> dict:
    return {"op": "person.contact", "person": person["id"], "kind": "phone", "value": "555 0100", **more}


def test_a_contact_detail_waits_even_from_the_persons_own_note_and_confirming_sets_it_with_undo(env):
    ws, cfg, store = env
    target = PEOPLE[2]
    quote = "call me on 555 0100"
    note = f"Their number: {quote}."
    cs_id, statuses = apply(
        store,
        cfg,
        [contact(target, evidence={"quote": quote})],
        origin="pm",
        trust="trusted",
        source_id=source(store, trust="trusted"),
        raw=note,
    )
    assert statuses == ["held"]  # the person's own note proposes it; still not applied
    held = outcomes(store, cs_id)[0]
    assert target["full_name"] in held["label"] and "phone" in held["label"] and "555 0100" in held["label"]
    assert held["reason"] == "A way to reach someone waits for your confirmation."
    assert not data(store, "person", target["id"]).get("how_to_reach")
    release(store, cfg, cs_id, 0)
    assert data(store, "person", target["id"])["how_to_reach"] == {"phone": "555 0100"}
    assert undo(store, cs_id).restored == [0]
    assert data(store, "person", target["id"]).get("how_to_reach", {}) == {}
    # From an input: the same wait, with evidence from the input's words.
    sid = source(store)
    proposed = contact(target, evidence={"quote": quote})
    cs_id, statuses = apply(
        store, cfg, [proposed], origin="input", trust="untrusted", source_id=sid, raw=f"x {quote} y"
    )
    assert statuses == ["held"]
    # The person's own act on screen is the confirmation.
    person_cs = apply_as_person(
        store, cfg, [contact(target, kind="Email", value="  jp@example.org ")], "Added a contact"
    )
    assert data(store, "person", target["id"])["how_to_reach"] == {"email": "jp@example.org"}
    assert outcomes(store, person_cs)[0]["status"] == "applied"


def test_a_contact_detail_needs_evidence_a_known_person_and_a_kind_from_the_list(env):
    ws, cfg, store = env
    target = PEOPLE[2]
    sid = source(store)
    raw = "Reach me on 555 0100 any time."

    def refused(op) -> str:
        cs_id, statuses = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=sid, raw=raw)
        assert statuses == ["refused"]
        return outcomes(store, cs_id)[0]["reason"]

    assert "needs evidence" in refused(contact(target))
    assert "isn't in the input" in refused(contact(target, evidence={"quote": "call 555 0199"}))
    assert "there is no person" in refused(contact({"id": "PER-404"}, evidence={"quote": "555 0100"}))
    why = refused(contact(target, kind="pigeon", evidence={"quote": "555 0100"}))
    assert "email, phone, address" in why
    with pytest.raises(ValidationError):
        contact_op = {**contact(target, evidence={"quote": "555 0100"}), "value": "  "}
        apply(store, cfg, [contact_op], origin="input", trust="untrusted", source_id=sid, raw=raw)


def test_reading_notes_is_offered_the_contact_and_the_project_ops_and_an_ask_is_not():
    for name in ("person.contact", "project.add"):
        assert name in TASKS["notes"].ops and name not in TASKS["ask"].ops


def test_the_notes_packet_tells_when_to_propose_a_project_or_a_contact_and_lists_the_kinds(env):
    ws, cfg, store = env
    answers()
    handed = hand_in(ws, store, note="", pasted=RAW, now=NOW)
    task = build(ws, store, cfg, handed.request, date(2026, 10, 9)).task
    for words in ("project.add", "person.contact", "email, phone, address", "it is not a project at all"):
        assert words in task.instructions + task.stable
    assert "Never propose a project for a topic" in task.instructions


# ---- a project the assistant found ----------------------------------------------------------------


def project_run(env, *, with_project: str | None = None) -> str:
    """Two records the run filed with no project and the project it found, held."""
    _, cfg, store = env
    me = cfg.workspace.user.person
    ops = [
        {"op": "note", "text": "The plan is due soon."},
        {
            "op": "action.add",
            "text": "Write the plan",
            "owners": [me],
            "evidence": {"quote": f"The {NEW_PROJECT} needs a plan"},
        },
        {
            "op": "action.add",
            "text": "Book the hall",
            "owners": [me],
            "project": PROJECT["id"],
            "evidence": {"quote": f"{STRANGER} will book the venue"},
        },
        {"op": "project.add", "name": NEW_PROJECT},
    ]
    answers(*ops)
    cs_id = run(env, RAW)
    assert [o["status"] for o in outcomes(store, cs_id)] == ["applied", "applied", "applied", "held"]
    return cs_id


def test_a_project_from_an_input_waits_and_from_the_persons_own_note_applies(env):
    ws, cfg, store = env
    cs_id = project_run(env)
    held = outcomes(store, cs_id)[3]
    assert held["reason"] == PROJECT_WAITS and held["op"]["name"] == NEW_PROJECT
    assert not [p for p in store.read().list("project") if p.data["name"] == NEW_PROJECT]
    own_cs, statuses = apply(
        store, cfg, [{"op": "project.add", "name": "Lantern " + "Walk"}], origin="pm", trust="trusted"
    )
    assert statuses == ["applied"]
    # Adding the held one is the existing release, with Undo.
    release(store, cfg, cs_id, 3)
    assert [p for p in store.read().list("project") if p.data["name"] == NEW_PROJECT]
    assert undo(store, cs_id, [3]).restored == [3]
    assert data(store, "changeset", own_cs)["status"] == "applied"


def test_add_files_the_unfiled_work_under_the_new_project_and_undo_takes_the_project_and_the_filing_away(env):
    ws, cfg, store = env
    cs_id = project_run(env)
    note_id, action_id, other_id = (outcomes(store, cs_id)[i]["records"][0]["id"] for i in range(3))
    project_id = add_project(store, cfg, cs_id, 3, ws=ws, now=NOW)
    assert data(store, "project", project_id)["name"] == NEW_PROJECT
    assert data(store, "note", note_id)["project"] == project_id
    assert data(store, "action", action_id)["project"] == project_id
    assert data(store, "action", other_id)["project"] == PROJECT["id"]  # it named a project already
    assert outcomes(store, cs_id)[3]["status"] == "applied"
    assert undo(store, cs_id, [3]).restored == [3]
    assert not [p for p in store.read().list("project") if p.data["name"] == NEW_PROJECT]
    assert not data(store, "note", note_id).get("project") and not data(store, "action", action_id).get("project")
    assert data(store, "action", other_id)["project"] == PROJECT["id"]


def test_add_also_files_the_held_ops_that_have_not_made_their_records_yet(env):
    ws, cfg, store = env
    answers(
        {"op": "project.add", "name": NEW_PROJECT},
        {
            "op": "action.add",
            "text": "Book the venue",
            "owners": [STRANGER],
            "evidence": {"quote": f"{STRANGER} will book the venue"},
        },
    )
    cs_id = run(env, RAW)
    project_id = add_project(store, cfg, cs_id, 0, ws=ws, now=NOW)
    release(store, cfg, cs_id, 1, person=PEOPLE[1]["id"], ws=ws)
    made = outcomes(store, cs_id)[1]["records"][0]["id"]
    assert data(store, "action", made)["project"] == project_id


def test_undoing_add_takes_the_project_off_the_held_ops_it_was_filed_on(env):
    ws, cfg, store = env
    answers(
        {"op": "project.add", "name": NEW_PROJECT},
        {
            "op": "action.add",
            "text": "Book the venue",
            "owners": [STRANGER],
            "evidence": {"quote": f"{STRANGER} will book the venue"},
        },
    )
    cs_id = run(env, RAW)
    add_project(store, cfg, cs_id, 0, ws=ws, now=NOW)
    assert outcomes(store, cs_id)[1]["op"]["project"]
    assert undo(store, cs_id, [0]).restored == [0]
    unfile_missing(store, cs_id)
    assert not outcomes(store, cs_id)[1]["op"].get("project")
    release(store, cfg, cs_id, 1, person=PEOPLE[1]["id"], ws=ws)
    made = outcomes(store, cs_id)[1]["records"][0]["id"]
    assert not data(store, "action", made).get("project")


def test_the_release_route_adds_a_held_project_and_files_the_work(api):
    client, store, ws, cfg = api
    cs_id = project_run((ws, cfg, store))
    note_id = outcomes(store, cs_id)[0]["records"][0]["id"]
    assert client.post(f"/api/changesets/{cs_id}/ops/3/release", json={}).status_code == 200
    (added,) = [p for p in store.read().list("project") if p.data["name"] == NEW_PROJECT]
    assert data(store, "note", note_id)["project"] == added.id
    assert client.post(f"/api/changesets/{cs_id}/undo", json={"ops": [3]}).status_code == 200
    assert not data(store, "note", note_id).get("project")


def test_part_of_files_the_work_under_the_project_keeps_a_confirmed_entry_records_a_signal_and_undo_restores_it(env):
    ws, cfg, store = env
    cs_id = project_run(env)
    note_id, action_id, other_id = (outcomes(store, cs_id)[i]["records"][0]["id"] for i in range(3))
    change = file_under(store, cfg, cs_id, 3, PROJECT["id"], now=NOW)
    assert data(store, "note", note_id)["project"] == PROJECT["id"]
    assert data(store, "action", action_id)["project"] == PROJECT["id"]
    assert data(store, "action", other_id)["project"] == PROJECT["id"]  # it named this project already
    held = outcomes(store, cs_id)[3]
    assert held["status"] == "refused" and PROJECT["name"] in held["reason"]
    assert data(store, "changeset", cs_id)["status"] == "applied"
    assert not [p for p in store.read().list("project") if p.data["name"] == NEW_PROJECT]
    (entry,) = [g.data for g in store.read().list("glossary_entry") if g.data["term"] == NEW_PROJECT]
    # For the whole workspace: the name turns up in inputs not yet filed under the project; the meaning names it.
    assert entry["status"] == "active" and entry["confidence"] == "confirmed" and entry["project"] is None
    assert entry["origin"] == "person" and entry["kept_by"] == cfg.workspace.user.person
    assert PROJECT["name"] in entry["meaning"]
    (signal,) = signals(store, "held_declined")
    assert signal["changeset"] == cs_id and signal["refs"] == [cs_id, PROJECT["id"]]
    assert signal["note"].startswith("part of") and NEW_PROJECT in signal["note"]
    assert data(store, "changeset", change)["reviewed"]
    assert undo(store, change).restored == [0]
    assert "project" not in {k for k, v in data(store, "note", note_id).items() if v}
    assert not data(store, "action", action_id).get("project")
    assert outcomes(store, cs_id)[3]["status"] == "held" and data(store, "changeset", cs_id)["status"] == "held"
    assert [g for g in store.read().list("glossary_entry") if g.data["term"] == NEW_PROJECT] == []
    assert len(signals(store, "held_declined")) == 1  # the person's choice stays recorded


def test_part_of_also_files_the_held_ops_that_have_not_made_their_records_yet(env):
    ws, cfg, store = env
    answers(
        {"op": "project.add", "name": NEW_PROJECT},
        {
            "op": "action.add",
            "text": "Book the venue",
            "owners": [STRANGER],
            "evidence": {"quote": f"{STRANGER} will book the venue"},
        },
    )
    cs_id = run(env, RAW)
    file_under(store, cfg, cs_id, 0, PROJECT["id"], now=NOW)
    assert outcomes(store, cs_id)[1]["op"]["project"] == PROJECT["id"]
    release(store, cfg, cs_id, 1, person=PEOPLE[1]["id"], ws=ws)
    made = outcomes(store, cs_id)[1]["records"][0]["id"]
    assert data(store, "action", made)["project"] == PROJECT["id"]


def test_not_a_project_sets_the_proposal_aside_keeps_an_entry_saying_so_records_a_signal_and_undo_restores_it(env):
    ws, cfg, store = env
    cs_id = project_run(env)
    note_id = outcomes(store, cs_id)[0]["records"][0]["id"]
    change = not_a_project(store, cfg, cs_id, 3, now=NOW)
    held = outcomes(store, cs_id)[3]
    assert held["status"] == "refused" and held["reason"] == cfg.language.messages.not_a_project_reason
    assert not data(store, "note", note_id).get("project")  # nothing is filed anywhere
    (entry,) = [g.data for g in store.read().list("glossary_entry") if g.data["term"] == NEW_PROJECT]
    assert entry["status"] == "active" and entry["confidence"] == "confirmed" and not entry.get("project")
    assert entry["meaning"] == cfg.language.messages.not_a_project_meaning
    (signal,) = signals(store, "held_declined")
    assert signal["note"].startswith("not a project") and NEW_PROJECT in signal["note"]
    assert signal["refs"] == [cs_id]
    assert undo(store, change).restored == [0]
    assert outcomes(store, cs_id)[3]["status"] == "held"
    assert [g for g in store.read().list("glossary_entry") if g.data["term"] == NEW_PROJECT] == []


def test_only_a_project_that_is_still_held_can_be_filed_or_set_aside(env):
    ws, cfg, store = env
    cs_id = project_run(env)
    with pytest.raises(StoreError, match="isn't a project waiting"):
        file_under(store, cfg, cs_id, 0, PROJECT["id"])
    with pytest.raises(StoreError, match="there is no project"):
        file_under(store, cfg, cs_id, 3, "PRJ-404")
    not_a_project(store, cfg, cs_id, 3, now=NOW)
    with pytest.raises(StoreError, match="isn't a project waiting"):
        not_a_project(store, cfg, cs_id, 3)
    with pytest.raises(StoreError, match="there is no changeset"):
        not_a_project(store, cfg, "CS-404", 0)


def test_the_project_routes_file_and_set_aside_with_undo(api):
    client, store, ws, cfg = api
    env = (ws, cfg, store)
    cs_id = project_run(env)
    assert client.post(f"/api/changesets/{cs_id}/ops/3/part-of", json={"project": "PRJ-404"}).status_code == 404
    assert client.post(f"/api/changesets/{cs_id}/ops/0/not-a-project").status_code == 409
    done = client.post(f"/api/changesets/{cs_id}/ops/3/part-of", json={"project": PROJECT["id"]})
    assert done.status_code == 200, done.text
    assert outcomes(store, cs_id)[3]["status"] == "refused"
    assert client.post(f"/api/changesets/{cs_id}/ops/3/not-a-project").status_code == 409
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).json()["restored"] == [0]
    assert client.post(f"/api/changesets/{cs_id}/ops/3/not-a-project").status_code == 200


# ---- the golden cases ------------------------------------------------------------------------------------------------

GOLDEN = (
    (DEMO_A, "new-person-with-organization"),
    (DEMO_A, "project-no-record"),
    (DEMO_B, "signature-phone"),
)


@pytest.mark.parametrize(("template", "case_id"), GOLDEN)
def test_a_golden_case_for_each_next_step_passes_with_the_ideal_answer_and_scores_the_held_item(
    monkeypatch, template, case_id
):
    case = case_of(template, case_id)
    assert any("held" in e for e in case["expect"])
    assert run_edited(monkeypatch, template, case_id).passed
    # Leaving the held item out fails the case.
    held = next(e["held"] for e in case["expect"] if "held" in e and e["held"] != "who-is")
    without = {**case["stub_answer"], "ops": [o for o in case["stub_answer"]["ops"] if o["op"] != held]}
    result = run_edited(monkeypatch, template, case_id, stub_answer=without)
    assert not result.passed and any(held in m for m in result.missing)


def test_a_case_fails_when_the_detail_is_for_the_wrong_person_or_the_project_is_not_the_one_named(monkeypatch):
    case = case_of(DEMO_B, "signature-phone")
    other = {**case["stub_answer"]["ops"][0], "person": PEOPLE[2]["id"]}
    wrong = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer={**case["stub_answer"], "ops": [other]})
    assert not wrong.passed
    project = case_of(DEMO_A, "project-no-record")
    named = {**project["stub_answer"]["ops"][1], "name": "Something Else"}
    ops = [project["stub_answer"]["ops"][0], named]
    assert not run_edited(monkeypatch, DEMO_A, project["id"], stub_answer={**project["stub_answer"], "ops": ops}).passed
