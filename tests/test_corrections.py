"""Correcting what the assistant made (design 6.8, 6.13, 6.20, 7.18): a question's reword, reroute, drop and "already
sent"; "Change this" on a row; the ops the hand-work audit found missing (bring back set-aside mail, merge a list
value); the two question lints; the suggestion on the held "Pick an owner"; and the glossary op offered to notes.

Names, ids and texts come from the fixtures; the few free words are about no one.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, apply_as_person, check, release
from engine.check_text import numbered_questions
from engine.config.schema import ChecksFile
from engine.corrections import request_change
from engine.dispatcher import process, undo_changeset
from engine.followups import mark_sent
from engine.intake import hand_in
from engine.lists import ensure as ensure_lists
from engine.names import People
from engine.ops import CHANGESET, PERSON_ONLY_OPS
from engine.owners import suggest_owner
from engine.packet import build
from engine.records import Question
from engine.storage import Store, WriteContext
from engine.tasks import TASKS
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B, fixture_records
from tests.test_knowledge_records import apply, source
from tests.test_set_aside import LISTS, NOW, WORK, mail, make, requests_in

_TEST = WriteContext(actor="pm", trust="trusted", op="test.corrections")
PEOPLE = fixture_records(DEMO_B, "person")
PROJECT = fixture_records(DEMO_B, "project")[0]
LINK = PROJECT["links"][0]
FIXTURE_DECISION = next(q for q in fixture_records(DEMO_B, "question") if q.get("kind") == "decision")
TODAY = date(2026, 10, 14)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    ensure_lists(store)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def pm_of(cfg) -> str:
    return cfg.workspace.user.person


def other_of(cfg, *, skip: tuple[str, ...] = ()) -> str:
    return next(p["id"] for p in PEOPLE if p["id"] != pm_of(cfg) and p["id"] not in skip)


def signals(store, kind):
    return [s.data for s in store.read().list("signal") if s.data["kind"] == kind]


def question_of(store, qid):
    return store.read().get("question", qid).data


def person_op(env, op, summary="test"):
    _, cfg, store = env
    return apply_as_person(store, cfg, [op], summary)


def asked_by_a_run(env, op):
    """Let the stub answer a handed-in input with this op. Returns the changeset, the run and the question made."""
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"summary": "Asked.", "ops": [op]}))
    handed = hand_in(ws, store, pasted="Notes for the question.", now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    data = store.read().get("changeset", cs_id).data
    (outcome,) = data["ops"]
    assert outcome["status"] == "applied", outcome
    qid = next(r["id"] for r in outcome["records"] if r["kind"] == "question")
    return cs_id, data["run"], qid


def decision_op(cfg, **more):
    return {"op": "question.add", "to": pm_of(cfg), "title": "Which finish for the run?", "kind": "decision", **more}


def question_to_other(cfg, **more):
    return {
        "op": "question.add",
        "to": other_of(cfg),
        "title": "Is the file final?",
        "links": [LINK],
        "matters_for": "The date the file goes out",
        **more,
    }


def problems(env, op, name=None, *, actor="assistant"):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, "", "", "trusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if name is None or p.check == name]


def statuses(store, cs_id):
    return [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


# ---- reword ----------------------------------------------------------------------------------------------------------


def test_reword_changes_the_question_records_a_reworded_signal_naming_its_run_and_undo_restores_it(env):
    _, cfg, store = env
    cs_id, run_id, qid = asked_by_a_run(env, decision_op(cfg, text="Soft touch adds days."))
    done = person_op(env, {"op": "question.update", "id": qid, "title": "Matte or soft-touch?", "text": "Pick one."})
    data = question_of(store, qid)
    assert (data["title"], data["text"]) == ("Matte or soft-touch?", "Pick one.")
    (signal,) = signals(store, "reworded")
    assert signal["refs"] == [qid] and signal["changeset"] == cs_id and signal["run"] == run_id
    assert "Which finish for the run?" in signal["note"] and "Matte or soft-touch?" in signal["note"]
    undo_changeset(store, done)
    restored = question_of(store, qid)
    assert (restored["title"], restored["text"]) == ("Which finish for the run?", "Soft touch adds days.")
    assert (
        not signals(store, "undone") and len(signals(store, "reworded")) == 1
    )  # taking back their own edit teaches nothing


def test_reword_must_name_a_change_and_is_the_persons_alone(env):
    _, cfg, store = env
    qid = FIXTURE_DECISION["id"]
    with pytest.raises(ValidationError):
        CHANGESET.validate_python(
            {"ops": [{"op": "question.update", "id": qid}]}, context={"op_models": store.plugins.ops}
        )
    _, result = apply(store, cfg, [{"op": "question.update", "id": qid, "title": "Changed"}], actor="assistant")
    assert result == ["refused"]
    assert question_of(store, qid)["title"] == FIXTURE_DECISION["title"] and not signals(store, "reworded")


def test_a_question_that_holds_something_or_is_closed_is_not_reworded_moved_or_dropped(env):
    _, cfg, store = env
    with store.transaction() as tx:
        held = tx.create(
            "question",
            {
                "to": pm_of(cfg),
                "title": "Who owns it?",
                "kind": "routing",
                "resolves": {"kind": "owner", "action": "ACT-1"},
            },
            _TEST,
        ).id
        closed = tx.create(
            "question", {"to": pm_of(cfg), "title": "Old", "status": "answered", "answer": "Yes"}, _TEST
        ).id
    for op in ({"op": "question.update", "id": held, "title": "x"}, {"op": "question.drop", "id": held, "reason": "x"}):
        with pytest.raises(Exception, match="waits for the answer"):
            person_op(env, op)
    for op in (
        {"op": "question.update", "id": closed, "title": "x"},
        {"op": "question.move", "id": closed, "to": other_of(cfg)},
        {"op": "question.drop", "id": closed, "reason": "x"},
        {"op": "question.mark_sent", "id": closed},
    ):
        with pytest.raises(Exception, match="already closed"):
            person_op(env, op)
    with pytest.raises(Exception, match="no question"):
        person_op(env, {"op": "question.drop", "id": "Q-999", "reason": "x"})


# ---- reroute ---------------------------------------------------------------------------------------------------------


def test_moving_a_decision_to_someone_else_makes_it_a_question_records_routed_and_undo_sends_it_back(env):
    _, cfg, store = env
    cs_id, run_id, qid = asked_by_a_run(env, decision_op(cfg))
    other = other_of(cfg)
    done = person_op(env, {"op": "question.move", "id": qid, "to": other})
    moved = question_of(store, qid)
    assert (moved["to"], moved["kind"]) == (other, "question")
    (signal,) = signals(store, "routed")
    assert signal["refs"] == [cs_id, qid, other] and signal["changeset"] == cs_id and signal["run"] == run_id
    undo_changeset(store, done)
    back = question_of(store, qid)
    assert (back["to"], back["kind"]) == (pm_of(cfg), "decision")
    assert not signals(store, "undone")


def test_moving_a_sent_question_makes_it_open_for_the_new_person_and_a_name_works_as_well_as_an_id(env):
    _, cfg, store = env
    other = other_of(cfg)
    third = other_of(cfg, skip=(other,))
    with store.transaction() as tx:
        qid = tx.create(
            "question",
            {"to": other, "title": "Is the file final?", "status": "sent", "sent_at": NOW.isoformat()},
            _TEST,
        ).id
    name = next(p["full_name"] for p in PEOPLE if p["id"] == third)
    person_op(env, {"op": "question.move", "id": qid, "to": name})
    moved = question_of(store, qid)
    assert (moved["to"], moved["status"], moved["sent_at"]) == (third, "open", None)


def test_a_reroute_goes_to_one_known_person_other_than_the_one_it_is_for(env):
    _, cfg, store = env
    qid = FIXTURE_DECISION["id"]
    with pytest.raises(Exception, match="isn't one known person"):
        person_op(env, {"op": "question.move", "id": qid, "to": "Nobody Atall"})
    with pytest.raises(Exception, match="already for that person"):
        person_op(env, {"op": "question.move", "id": qid, "to": FIXTURE_DECISION["to"]})
    assert not signals(store, "routed")


# ---- drop ------------------------------------------------------------------------------------------------------------


def test_drop_keeps_the_question_with_its_reason_records_dropped_and_undo_opens_it_again(env):
    _, cfg, store = env
    cs_id, run_id, qid = asked_by_a_run(env, decision_op(cfg))
    done = person_op(env, {"op": "question.drop", "id": qid, "reason": "  Not needed   any more "})
    gone = question_of(store, qid)
    assert (gone["status"], gone["dropped_reason"]) == ("dropped", "Not needed any more")
    (signal,) = signals(store, "dropped")
    assert signal["refs"] == [qid] and signal["changeset"] == cs_id and signal["run"] == run_id
    assert signal["note"] == "Not needed any more"
    undo_changeset(store, done)
    again = question_of(store, qid)
    assert (again["status"], again["dropped_reason"]) == ("open", None)
    with pytest.raises(ValidationError):
        CHANGESET.validate_python(
            {"ops": [{"op": "question.drop", "id": qid, "reason": ""}]}, context={"op_models": store.plugins.ops}
        )


# ---- already sent ----------------------------------------------------------------------------------------------------


def test_mark_sent_records_the_day_undo_makes_it_open_and_it_is_not_a_correction(env):
    _, cfg, store = env
    store.clock = lambda: "2026-10-14T09:00:00+00:00"
    qid = next(q["id"] for q in fixture_records(DEMO_B, "question") if q["to"] != pm_of(cfg))
    done = person_op(env, {"op": "question.mark_sent", "id": qid, "on": "2026-10-12"})
    sent = question_of(store, qid)
    assert sent["status"] == "sent" and str(sent["sent_at"]).startswith("2026-10-12")
    undo_changeset(store, done)
    assert (question_of(store, qid)["status"], question_of(store, qid)["sent_at"]) == ("open", None)
    person_op(env, {"op": "question.mark_sent", "id": qid})
    assert str(question_of(store, qid)["sent_at"]).startswith("2026-10-14")
    assert not store.read().has("signal")


def test_mark_sent_refuses_a_question_already_sent_and_a_day_that_has_not_come(env):
    _, cfg, store = env
    store.clock = lambda: "2026-10-14T09:00:00+00:00"
    qid = next(q["id"] for q in fixture_records(DEMO_B, "question") if q["to"] != pm_of(cfg))
    with pytest.raises(Exception, match="hasn't come"):
        person_op(env, {"op": "question.mark_sent", "id": qid, "on": "2026-10-15"})
    person_op(env, {"op": "question.mark_sent", "id": qid, "on": "2026-10-14"})  # today is as late as it can be
    with pytest.raises(Exception, match="already marked as sent"):
        person_op(env, {"op": "question.mark_sent", "id": qid})


def test_the_question_ops_only_the_person_makes_are_never_offered_to_the_assistant(env):
    _, cfg, store = env
    mine = {"question.update", "question.move", "question.drop", "question.mark_sent"}
    assert mine <= PERSON_ONLY_OPS
    assert not mine & set(TASKS["notes"].ops) and not mine & set(TASKS["ask"].ops)
    for op in (
        {"op": "question.move", "id": FIXTURE_DECISION["id"], "to": other_of(cfg)},
        {"op": "question.drop", "id": FIXTURE_DECISION["id"], "reason": "x"},
        {"op": "question.mark_sent", "id": FIXTURE_DECISION["id"]},
    ):
        assert [p.check for p in problems(env, op, "person-only")] == ["person-only"]


def test_an_edited_message_names_the_question_ids_and_the_run_that_wrote_them(env):
    _, cfg, store = env
    asked_of = {q["to"] for q in fixture_records(DEMO_B, "question")}
    person = next(p["id"] for p in PEOPLE if p["id"] not in asked_of and p["id"] != pm_of(cfg))
    cs_id, run_id, qid = asked_by_a_run(env, question_to_other(cfg, to=person))
    mark_sent(store, cfg, person, sent_text="A message the person wrote instead.")
    (edited,) = signals(store, "draft_edited")
    assert edited["refs"] == [person, qid] and edited["run"] == run_id and edited["changeset"] == cs_id


def test_an_edited_message_over_questions_from_different_runs_or_none_leaves_the_run_empty(env):
    _, cfg, store = env
    fixed = next(q for q in fixture_records(DEMO_B, "question") if q["to"] != pm_of(cfg))
    _, _, made = asked_by_a_run(env, question_to_other(cfg, to=fixed["to"]))
    mark_sent(store, cfg, fixed["to"], sent_text="Rewritten.")
    (edited,) = signals(store, "draft_edited")
    assert edited["refs"] == [fixed["to"], fixed["id"], made]
    assert edited["run"] is None and edited["changeset"] is None


# ---- "Change this" ---------------------------------------------------------------------------------------------------


def make_items(store, cfg) -> dict[str, tuple[str, str]]:
    """One item of each changeable kind: its route kind, its record kind and id."""
    with store.transaction() as tx:
        event = tx.create(
            "event", {"title": "Printer proof due", "start": "2026-10-20", "project": PROJECT["id"]}, _TEST
        ).id
        fact = tx.create("fact", {"text": "The proof is due on the twentieth.", "project": PROJECT["id"]}, _TEST).id
    action = fixture_records(DEMO_B, "action")[0]["id"]
    return {
        "action": ("action", action),
        "question": ("question", next(q["id"] for q in fixture_records(DEMO_B, "question") if q["to"] != pm_of(cfg))),
        "decision": ("question", FIXTURE_DECISION["id"]),
        "event": ("event", event),
        "fact": ("fact", fact),
    }


@pytest.mark.parametrize("kind", ["action", "question", "decision", "event", "fact"])
def test_change_this_records_a_signal_and_queues_a_notes_request_whose_packet_carries_the_item_as_it_is_now(env, kind):
    ws, cfg, store = env
    record_kind, record_id = make_items(store, cfg)[kind]
    note = "Move it a day later"  # a short note is still read
    request, signal_id = request_change(ws, store, cfg, kind, record_id, note)
    queued = store.read().get("request", request).data
    assert queued["task"] == "notes" and queued["state"] == "queued"
    assert queued["about"] == {"kind": record_kind, "id": record_id}
    saved = store.read().get("source", queued["source"]).data
    assert saved["kind"] == "note:change_requested" and saved["trust"] == "trusted"
    (signal,) = signals(store, "change_requested")
    assert store.read().get("signal", signal_id).data == signal
    assert signal["refs"] == [record_id] and signal["note"] == note
    # The record changes before the assistant runs; the packet shows it as it stands then.
    changed = {"action": "text", "question": "title", "decision": "title", "event": "title", "fact": "text"}[kind]
    with store.transaction() as tx:
        current = tx.get(record_kind, record_id)
        tx.update(
            record_kind, record_id, {changed: "Reworded since the note was typed"}, _TEST, read_version=current.version
        )
    packet = build(ws, store, cfg, request, TODAY).task.request
    assert "Reworded since the note was typed" in packet and "asked for this record to be changed" in packet
    assert note in packet


def test_change_this_on_something_a_run_made_names_its_changeset_and_run(env):
    ws, cfg, store = env
    cs_id, run_id, qid = asked_by_a_run(env, decision_op(cfg))
    request_change(ws, store, cfg, "decision", qid, "Ask it as a question to the editor instead")
    (signal,) = signals(store, "change_requested")
    assert signal["changeset"] == cs_id and signal["run"] == run_id


def test_change_this_needs_words_and_a_changeable_item_that_exists(env):
    ws, cfg, store = env
    action = fixture_records(DEMO_B, "action")[0]["id"]
    from engine.intake import IntakeError

    with pytest.raises(IntakeError, match="Say what to change"):
        request_change(ws, store, cfg, "action", action, "   ")
    with pytest.raises(IntakeError, match="no action"):
        request_change(ws, store, cfg, "action", "ACT-999", "Move it")
    with pytest.raises(IntakeError, match="can't be asked"):
        request_change(ws, store, cfg, "person", PEOPLE[0]["id"], "Rename them")
    assert not store.read().has("signal") and not [r for r in store.read().list("request") if r.data.get("about")]


def test_the_notes_prompt_tells_the_assistant_what_a_change_this_note_may_do():
    from engine.prompts import render

    prompt = render("notes", {"assistant_name": "The assistant"}, DEMO_B)
    for words in ("asked for this record to be changed", "reword it", "put it on hold", "split it", "or drop it"):
        assert words in prompt
    assert "Never mark an action done unless the note says it is done" in prompt


# ---- the missing ops -------------------------------------------------------------------------------------------------


def test_list_merge_moves_every_record_to_the_other_value_and_undo_puts_both_back(env):
    _, cfg, store = env
    held = store.read().get("project", PROJECT["id"]).data["status"]
    with store.transaction() as tx:
        into = next(v for v in tx.list("value_list") if v.data["name"] == "project-status").data["values"]
    other = next(v for v in into if v != held)
    done = person_op(env, {"op": "list.merge", "list": "project-status", "value": held, "into": other})
    lst = next(v for v in store.read().list("value_list") if v.data["name"] == "project-status").data
    assert held not in lst["values"] and held not in lst["retired"] and other in lst["values"]
    assert store.read().get("project", PROJECT["id"]).data["status"] == other
    undo_changeset(store, done)
    lst = next(v for v in store.read().list("value_list") if v.data["name"] == "project-status").data
    assert held in lst["values"]
    assert store.read().get("project", PROJECT["id"]).data["status"] == held


def test_list_merge_has_a_check_and_waits_for_the_person_when_the_assistant_proposes_it(env):
    _, cfg, store = env
    values = next(v for v in store.read().list("value_list") if v.data["name"] == "project-status").data["values"]
    first, second = values[0], values[1]
    for op, why in (
        ({"op": "list.merge", "list": "no-such-list", "value": first, "into": second}, "no list called"),
        ({"op": "list.merge", "list": "project-status", "value": "Sideways", "into": second}, "isn't on the list"),
        ({"op": "list.merge", "list": "project-status", "value": first, "into": "Sideways"}, "isn't offered"),
        ({"op": "list.merge", "list": "project-status", "value": first, "into": first}, "into itself"),
    ):
        _, result = apply(store, cfg, [op], actor="pm", origin="pm")
        assert result == ["refused"], op
        (found,) = [p for p in problems(env, op, "targets")]
        assert why in found.message
    op = {"op": "list.merge", "list": "project-status", "value": first, "into": second}
    cs_id, result = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=source(store))
    assert result == ["held"]
    assert (
        first in next(v for v in store.read().list("value_list") if v.data["name"] == "project-status").data["values"]
    )


def set_aside_workspace(tmp_path, *, first_run, hours=1):
    ws, cfg, store = make(tmp_path, [mail("bulk", f"a@{LISTS}", bulk=True, hours=hours)], first_run=first_run)
    from engine.watch import refresh

    refresh(ws, store, cfg, "m", NOW)
    return ws, cfg, store, store.read().list("snapshot")[0].id


def test_mail_restore_proposed_by_the_assistant_waits_then_brings_the_message_back_and_undo_sets_it_aside(tmp_path):
    ws, cfg, store, snap = set_aside_workspace(tmp_path, first_run="all")
    try:
        assert not requests_in(store, "queued")
        cs_id, result = apply(
            store,
            cfg,
            [{"op": "mail.restore", "snapshot": snap}],
            origin="input",
            trust="untrusted",
            source_id=source(store),
        )
        assert result == ["held"] and store.read().get("snapshot", snap).data["set_aside"]
        release(store, cfg, cs_id, 0, ws=ws)
        assert not store.read().get("snapshot", snap).data["set_aside"]
        (queued,) = requests_in(store, "queued")
        assert queued.data["source"]
        from engine.applier import undo

        assert undo(store, cs_id).restored == [0]
        assert store.read().get("snapshot", snap).data["set_aside"]["section"] == "sales"
        assert not requests_in(store, "queued")
        assert not store.read().has("signal")
    finally:
        store.close()


def test_mail_restore_hands_in_a_message_that_was_never_handed_in_and_undo_takes_that_back(tmp_path):
    ws, cfg, store, snap = set_aside_workspace(tmp_path, first_run="recent", hours=500)
    try:
        assert not store.read().list("request")
        done = apply_as_person(store, cfg, [{"op": "mail.restore", "snapshot": snap}], "Brought back")
        assert len(requests_in(store, "queued")) == 1 and not store.read().get("snapshot", snap).data["set_aside"]
        undo_changeset(store, done)
        assert not [r for r in store.read().list("request") if r.data.get("source")]
        assert store.read().get("snapshot", snap).data["set_aside"]
    finally:
        store.close()


def test_mail_restore_refuses_a_message_the_app_does_not_hold_or_one_confirmed_as_rightly_set_aside(tmp_path):
    from engine.set_aside import confirm_items

    ws, cfg, store, snap = set_aside_workspace(tmp_path, first_run="all")
    try:
        with pytest.raises(Exception, match="isn't a message the app is holding"):
            apply_as_person(store, cfg, [{"op": "mail.restore", "snapshot": "SNAP-999"}], "x")
        confirm_items(store, [snap])
        with pytest.raises(Exception, match="confirmed"):
            apply_as_person(store, cfg, [{"op": "mail.restore", "snapshot": snap}], "x")
    finally:
        store.close()


def test_mail_restore_refuses_a_message_that_is_not_in_the_folder(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("work", WORK)], first_run="all")
    try:
        from engine.watch import refresh

        refresh(ws, store, cfg, "m", NOW)
        snap = store.read().list("snapshot")[0].id
        with pytest.raises(Exception, match="isn't set aside"):
            apply_as_person(store, cfg, [{"op": "mail.restore", "snapshot": snap}], "x")
    finally:
        store.close()


# ---- the two question lints ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("1. Which printer? 2. What date?", 2),
        ("1) Which printer?\n2) What date?\n3) Who signs off?", 3),
        ("(1) Which printer? (2) What date?", 2),
        ("1. Which printer? 2. Thanks, that's all.", 1),  # a numbered line that asks nothing isn't a question
        ("Which printer? What date?", 0),  # two questions that aren't numbered
        ("2. Which printer? 3. What date?", 0),  # a list counts up from one
        ("It is 3. Is it ready? Or is the 5. day better?", 0),  # figures in a sentence aren't a list
        ("1. Which printer?", 1),
    ],
)
def test_numbered_questions_counts_the_items_of_a_numbered_list_that_ask(text, count):
    assert numbered_questions(text) == count


def test_several_questions_returns_a_question_or_decision_at_the_configured_number_and_not_below(env):
    _, cfg, store = env
    two = "1. Which printer takes the run? 2. When does the file go?"
    for kind in ("question", "decision"):
        (found,) = problems(env, decision_op(cfg, text=two, kind=kind), "several-questions")
        assert found.severity == "return" and "own question" in found.message
    assert not problems(env, decision_op(cfg, text="1. Which printer takes the run? 2. Thanks."), "several-questions")
    cfg.checks.tuning.several_questions.minimum = 3
    assert not problems(env, decision_op(cfg, text=two), "several-questions")
    three = two + " 3. Who signs it off?"
    assert problems(env, decision_op(cfg, text=three), "several-questions")
    cfg.checks.lints["several-questions"] = "off"
    assert not problems(env, decision_op(cfg, text=three), "several-questions")
    assert ChecksFile().lints["several-questions"] == "return" and ChecksFile().tuning.several_questions.minimum == 2


def test_a_question_to_someone_else_without_a_stake_is_returned_and_then_held_so_it_is_never_sent(env):
    _, cfg, store = env
    bare = question_to_other(cfg)
    del bare["matters_for"]
    (found,) = problems(env, bare, "question-without-stake")
    assert found.severity == "return" and "record it as a fact and say so in the change's note" in found.message
    assert problems(env, {**bare, "matters_for": "   "}, "question-without-stake")  # words, not spaces
    assert not problems(env, question_to_other(cfg), "question-without-stake")  # it says what depends on it
    assert not problems(env, decision_op(cfg), "question-without-stake")  # to the person themselves
    cfg.checks.lints["question-without-stake"] = "off"
    assert not problems(env, bare, "question-without-stake")
    cfg.checks.lints["question-without-stake"] = "return"
    cs_id, result = apply(store, cfg, [bare], origin="pm")
    assert result == ["held"]  # still returned after the fix round: it reaches someone else, so it waits for the person


def test_the_stake_is_kept_on_the_question_and_both_lints_default_to_return_in_both_workspaces(env):
    _, cfg, store = env
    cs_id, result = apply(store, cfg, [question_to_other(cfg)], origin="pm")
    assert result == ["applied"]
    (record,) = store.read().find("question", {"matters_for": "The date the file goes out"})
    assert record.data["to"] == other_of(cfg)
    assert Question.model_fields["matters_for"].default is None
    for template in (DEMO_A, DEMO_B):
        workspace_checks = (template / "config" / "checks.yaml").read_text()
        assert "several-questions: return" in workspace_checks and "question-without-stake: return" in workspace_checks
        assert "several_questions:" in workspace_checks and "owner_suggestion:" in workspace_checks


# ---- an action with no owner ----------------------------------------------------------------------------------------

TOPIC = "printer slot hardcover schedule"
UNOWNED = "Confirm the printer slot for the hardcover run"


def routing(store, cfg, **more):
    op = {
        "op": "routing.add",
        "text": "Printer scheduling goes to the production lead.",
        "topic": TOPIC,
        "person": other_of(cfg),
        **more,
    }
    cs_id, _ = apply(store, cfg, [op], origin="pm")
    return store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]


def unowned_action(store, cfg, text=UNOWNED):
    sid = source(store)
    op = {"op": "action.add", "text": text, "evidence": {"quote": text}}
    cs_id, result = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=sid, raw=text)
    assert result == ["applied"]
    outcome = store.read().get("changeset", cs_id).data["ops"][0]
    return next(r["id"] for r in outcome["records"] if r["kind"] == "action"), outcome["question"]


def test_an_unowned_action_is_held_with_the_owner_a_routing_entry_suggests_and_why(env):
    ws, cfg, store = env
    entry = routing(store, cfg)
    action, qid = unowned_action(store, cfg)
    assert store.read().get("action", action).data["status"] == "held"
    found = suggest_owner(store.read(), cfg, action)
    assert (found.person, found.entry) == (other_of(cfg), entry)
    assert found.why == "Printer scheduling goes to the production lead." and found.fold_into is None
    (line,) = [line for line in queue(ws, store, cfg, NOW) if line.kind == "owner"]
    assert line.question == qid and line.suggestion["person"] == other_of(cfg) and line.suggestion["entry"] == entry
    assert line.suggestion["person_name"] == next(p["full_name"] for p in PEOPLE if p["id"] == other_of(cfg))


def test_the_suggestion_follows_the_configured_share_of_the_topic_and_skips_what_does_not_apply(env):
    _, cfg, store = env
    entry = routing(store, cfg)
    action, _ = unowned_action(store, cfg, "Confirm the printer slot with the plant")  # 2 of the topic's 4 words
    cfg.checks.tuning.owner_suggestion.match = 0.5
    assert suggest_owner(store.read(), cfg, action).entry == entry  # exactly at the setting
    cfg.checks.tuning.owner_suggestion.match = 0.75
    assert suggest_owner(store.read(), cfg, action) is None  # below it
    cfg.checks.tuning.owner_suggestion.match = 0.5
    # A proposal isn't active, an entry for who doesn't answer isn't a suggestion, and another project's isn't either.
    with store.transaction() as tx:
        current = tx.get("routing_entry", entry)
        tx.update("routing_entry", entry, {"negative": True}, _TEST, read_version=current.version)
    assert suggest_owner(store.read(), cfg, action) is None
    with store.transaction() as tx:
        current = tx.get("routing_entry", entry)
        tx.update("routing_entry", entry, {"negative": False, "status": "retired"}, _TEST, read_version=current.version)
    assert suggest_owner(store.read(), cfg, action) is None
    assert suggest_owner(store.read(), cfg, "ACT-999") is None


def test_a_routing_entry_for_other_projects_does_not_suggest_an_owner_for_this_one(env):
    _, cfg, store = env
    with store.transaction() as tx:
        elsewhere = tx.create("project", {"name": "Another list"}, _TEST).id
    routing(store, cfg, applies_to={"projects": [elsewhere]})
    action, _ = unowned_action(store, cfg)
    with store.transaction() as tx:
        current = tx.get("action", action)
        tx.update("action", action, {"project": PROJECT["id"]}, _TEST, read_version=current.version)
    assert suggest_owner(store.read(), cfg, action) is None


def test_the_nearest_open_action_is_offered_to_fold_it_into_at_the_near_duplicate_setting(env):
    ws, cfg, store = env
    with store.transaction() as tx:
        near = tx.create(
            "action",
            {"text": "Confirm printer slot for hardcover run", "owners": [{"person": other_of(cfg)}], "status": "open"},
            _TEST,
        ).id
        tx.create(
            "action",
            {"text": "Confirm printer slot elsewhere", "owners": [{"person": other_of(cfg)}], "status": "done"},
            _TEST,
        )
    action, _ = unowned_action(store, cfg)
    found = suggest_owner(store.read(), cfg, action)
    assert (
        found.person is None
        and found.fold_into == near
        and found.fold_into_text == "Confirm printer slot for hardcover run"
    )
    cfg.checks.tuning.near_duplicate_action.similarity = 1.0
    assert suggest_owner(store.read(), cfg, action).fold_into == near  # the same words, so at the setting
    with store.transaction() as tx:
        current = tx.get("action", near)
        tx.update(
            "action",
            near,
            {"text": "Confirm printer slot for the hardcover proof"},
            _TEST,
            read_version=current.version,
        )
    assert suggest_owner(store.read(), cfg, action) is None


def test_picking_the_owner_still_opens_the_action_at_once_and_a_suggestion_is_only_a_suggestion(env):
    from engine.applier import pick_owner

    _, cfg, store = env
    routing(store, cfg)
    action, qid = unowned_action(store, cfg)
    elsewhere = other_of(cfg, skip=(other_of(cfg),))
    pick_owner(store, qid, elsewhere)
    data = store.read().get("action", action).data
    assert data["status"] == "open" and [o["person"] for o in data["owners"]] == [elsewhere]
    assert len(signals(store, "routed")) == 1


# ---- glossary ops offered to reading notes ---------------------------------------------------------------------------


def test_glossary_add_is_offered_to_reading_notes_and_no_other_knowledge_op_is(env):
    ws, cfg, store = env
    from engine.ops import KNOWLEDGE_OPS

    assert KNOWLEDGE_OPS & set(TASKS["notes"].ops) == {"glossary.add"}
    assert not KNOWLEDGE_OPS & set(TASKS["ask"].ops)
    handed = hand_in(ws, store, note="The brief mentions a system nobody has explained.", now=NOW)
    stable = build(ws, store, cfg, handed.request, TODAY).task.stable
    assert '"glossary.add"' in stable and '"lesson.add"' not in stable and '"routing.add"' not in stable


UNKNOWN_TERM = {
    "op": "glossary.add",
    "text": "Zorbit: not known yet",
    "term": "Zorbit",
    "meaning": "not known yet",
    "confidence": "unknown",
}


def test_an_unknown_term_from_an_input_is_added_as_a_proposal_and_from_the_persons_own_note_as_active(env):
    _, cfg, store = env
    cs_id, result = apply(store, cfg, [UNKNOWN_TERM], origin="input", trust="untrusted", source_id=source(store))
    assert result == ["applied"]
    entry = store.read().find("glossary_entry", {"term": "Zorbit"})[0]
    assert (entry.data["status"], entry.data["confidence"], entry.data["origin"]) == ("proposed", "unknown", "input")
    own = {**UNKNOWN_TERM, "term": "Quillon", "text": "Quillon: not known yet"}
    cs_id, result = apply(store, cfg, [own], origin="pm")
    assert result == ["applied"]
    entry = store.read().find("glossary_entry", {"term": "Quillon"})[0]
    assert (entry.data["status"], entry.data["origin"]) == ("active", "person")


# ---- the routes ------------------------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "corrections-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer corrections-token"}) as client:
        yield client, "/api", application.state.store, cfg


def test_the_question_routes_apply_as_the_person_with_undo_and_the_dropped_view_lists_the_reason(api):
    client, base, store, cfg = api
    qid = FIXTURE_DECISION["id"]
    other = other_of(cfg)
    reworded = client.post(f"{base}/questions/{qid}/reword", json={"title": "Matte or soft-touch, then?"})
    assert reworded.status_code == 200, reworded.text
    assert question_of(store, qid)["title"] == "Matte or soft-touch, then?"
    assert client.post(f"{base}/questions/{qid}/reroute", json={"to": other}).status_code == 200
    assert question_of(store, qid)["to"] == other and question_of(store, qid)["kind"] == "question"
    assert client.post(f"{base}/questions/{qid}/sent", json={}).status_code == 200
    assert question_of(store, qid)["status"] == "sent"
    assert client.post(f"{base}/questions/{qid}/drop", json={"reason": ""}).status_code == 422
    dropped = client.post(f"{base}/questions/{qid}/drop", json={"reason": "The printer decided for us."})
    assert dropped.status_code == 200
    (row,) = client.get(f"{base}/questions/dropped").json()
    assert row["id"] == qid and row["reason"] == "The printer decided for us." and row["to"] == other
    assert row["to_name"] and row["dropped_at"]
    again = client.post(f"{base}/questions/{qid}/reword", json={"title": "Too late"})
    assert again.status_code == 409 and "already closed" in again.text
    undone = client.post(f"{base}/changesets/{dropped.json()['changeset']}/undo", json={})
    assert undone.status_code == 200 and not client.get(f"{base}/questions/dropped").json()
    assert question_of(store, qid)["status"] == "sent"
    assert client.post(f"{base}/questions/Q-999/reword", json={"title": "x"}).status_code == 404


def test_change_this_route_queues_the_request_and_names_the_signal(api):
    client, base, store, cfg = api
    action = fixture_records(DEMO_B, "action")[0]["id"]
    done = client.post(f"{base}/items/action/{action}/change", json={"note": "Make it Friday"})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["ok"] == action
    queued = store.read().get("request", body["request"]).data
    assert queued["about"] == {"kind": "action", "id": action} and queued["state"] in ("queued", "running", "done")
    assert signals(store, "change_requested")[0]["refs"] == [action]
    assert store.read().get("signal", body["signal"]).data["kind"] == "change_requested"
    assert client.post(f"{base}/items/action/{action}/change", json={"note": ""}).status_code == 422
    assert client.post(f"{base}/items/action/ACT-999/change", json={"note": "Make it Friday"}).status_code == 404
    assert client.post(f"{base}/items/person/{PEOPLE[0]['id']}/change", json={"note": "x y z"}).status_code == 404


def test_the_owner_suggestion_is_in_todays_line_and_the_held_items_ask(api):
    client, base, store, cfg = api
    entry = routing(store, cfg)
    action, qid = unowned_action(store, cfg)
    (line,) = [line for line in client.get(f"{base}/today/queue").json() if line["kind"] == "owner"]
    assert line["suggestion"]["entry"] == entry and line["suggestion"]["person"] == other_of(cfg)
    assert line["suggestion"]["why"] == "Printer scheduling goes to the production lead."
    assert line["suggestion"]["fold_into"] is None
    with store.transaction() as tx:
        cs = tx.list("changeset")[-1]
        request = tx.get("request", cs.data["request"])
        tx.update("request", request.id, {"changeset": cs.id}, _TEST, read_version=request.version)
    shown = next(c["changeset"] for c in client.get(f"{base}/changes").json() if c["id"] == request.id)
    ask = next(o["ask"] for o in shown["ops"] if o["ask"] and o["ask"]["id"] == qid)
    assert ask["about"] == "owner" and ask["suggestion"]["entry"] == entry


def test_the_list_merge_route_merges_with_undo(api):
    client, base, store, cfg = api
    held = store.read().get("project", PROJECT["id"]).data["status"]
    values = next(v for v in client.get(f"{base}/lists").json() if v["name"] == "project-status")["values"]
    into = next(v for v in values if v != held)
    merged = client.post(f"{base}/lists/project-status/merge", json={"value": held, "into": into})
    assert merged.status_code == 200, merged.text
    assert store.read().get("project", PROJECT["id"]).data["status"] == into
    assert client.post(f"{base}/lists/project-status/merge", json={"value": held, "into": into}).status_code == 409
    assert client.post(f"{base}/changesets/{merged.json()['changeset']}/undo", json={}).status_code == 200
    assert store.read().get("project", PROJECT["id"]).data["status"] == held


def test_the_new_signal_kind_is_known_to_the_records():
    from engine.records import Signal

    kinds = Signal.model_fields["kind"].annotation.__args__
    assert "change_requested" in kinds and {"reworded", "dropped", "routed", "draft_edited"} <= set(kinds)
