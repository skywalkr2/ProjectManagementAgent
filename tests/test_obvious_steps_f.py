"""L3b part F: taking an action off hold, the person's own edit in a watched source, a recipient that is never guessed,
and a calendar entry that carries its input's project (design 6.7, "How each is recorded"). Names, ids and texts come
from the fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, check
from engine.dispatcher import process, undo_changeset
from engine.evaluate import _hand_in_watched, evaluate
from engine.followups import put_on_hold
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, TIERS
from engine.packet import build
from engine.storage import Store, WriteContext
from engine.unnamed_recipient import guessed_recipient, names_in, sentence_saying_sent
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_knowledge_records import apply, source

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
ACTIONS = fixture_records(DEMO_B, "action")
OPEN = [a for a in ACTIONS if a.get("status", "open") == "open" and a.get("owners")]
DONE = next(a for a in ACTIONS if a.get("status") == "done")
HELD = next(a for a in ACTIONS if a.get("status") == "held")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
LINK = fixture_records(DEMO_B, "project")[0]["links"][0]["url"]
PEOPLE = fixture_records(DEMO_B, "person")
TYPESETTER = next(p for p in PEOPLE if p.get("role") == "Typesetter")
NAME = TYPESETTER["full_name"]
FIRST, LAST = NAME.split()[0], NAME.split()[-1]
ALIASED = next(p for p in PEOPLE if p.get("aliases"))
RAW = "The proof sign-off came through this morning, so the printer can go ahead."
QUOTE = "The proof sign-off came through this morning"
WAITING = "the proof sign-off"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def unhold_op(action_id, quote=QUOTE):
    return {"op": "action.unhold", "id": action_id, "evidence": {"quote": quote}}


def on_hold(store, action_id=None) -> str:
    """An open fixture action, put on hold for the proof sign-off; returns its id."""
    target = action_id or OPEN[0]["id"]
    put_on_hold(store, target, WAITING, now=NOW)
    return target


def hold_of(store, action_id):
    return store.read().get("action", action_id).data.get("on_hold")


def problems(env, op, text="", *, actor="assistant", note=""):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, text, note or text, "untrusted"),
        actor=actor,
    )
    return check(cs, ctx)


# ---- action.unhold ---------------------------------------------------------------------------------------------------


def test_action_unhold_takes_the_action_off_hold_as_data_and_undo_puts_the_hold_back(env):
    _, cfg, store = env
    assert "action.unhold" in OP_MODELS and TIERS["action.unhold"] == "data"
    target = on_hold(store)
    before = hold_of(store, target)
    signals = len(store.read().list("signal"))
    cs_id, result = apply(
        store, cfg, [unhold_op(target)], origin="input", trust="untrusted", source_id=source(store), raw=RAW
    )
    assert result == ["applied"]
    assert hold_of(store, target) is None and store.read().get("action", target).data["status"] == "open"
    assert len(store.read().list("signal")) == signals, "what the assistant applies is not a correction"
    assert undo_changeset(store, cs_id).restored == [0]
    assert hold_of(store, target) == before


def test_action_unhold_is_refused_for_an_action_not_on_hold_or_not_open_or_missing(env):
    on_hold(store=env[2], action_id=OPEN[0]["id"])
    free = OPEN[1]["id"]  # open, never put on hold
    for op, why in (
        (unhold_op(free), "isn't on hold"),
        (unhold_op(DONE["id"]), "already done"),
        (unhold_op(HELD["id"]), "waiting for an owner"),
        (unhold_op("ACT-999"), "no action ACT-999"),
    ):
        found = [p for p in problems(env, op, QUOTE, actor="pm") if p.severity == "refuse"]
        assert [p.check for p in found] == ["targets"] and why in found[0].message
    assert not [p for p in problems(env, unhold_op(OPEN[0]["id"]), RAW) if p.severity == "refuse"]


def test_action_unhold_needs_the_inputs_words_from_the_assistant_but_not_from_the_person(env):
    target = on_hold(env[2])
    bare = {"op": "action.unhold", "id": target}
    assert [p.check for p in problems(env, bare, RAW) if p.severity == "refuse"] == ["evidence"]
    assert not [p for p in problems(env, bare, RAW, actor="pm") if p.severity == "refuse"]
    found = [p for p in problems(env, unhold_op(target, "never said anywhere"), RAW) if p.severity == "refuse"]
    assert [p.check for p in found] == ["evidence"]


def test_action_unhold_is_offered_to_reading_notes_and_the_quote_must_fit_what_it_waited_for(env):
    ws, cfg, store = env
    target = on_hold(store)
    handed = hand_in(ws, store, pasted=RAW, now=NOW)
    offered = build(ws, store, cfg, handed.request, NOW.date()).task.stable
    assert "action.unhold" in offered and f"on hold, waiting for {WAITING}" in offered
    elsewhere = "Parking is free after six, so the shop can open the doors early."
    fits = [p.check for p in problems(env, unhold_op(target, "Parking is free after six"), elsewhere)]
    assert "evidence-fit" in fits
    assert "evidence-fit" not in [p.check for p in problems(env, unhold_op(target), RAW)]


# ---- the person's own edit in a watched source -----------------------------------------------------------------------


def watched_case(**watched):
    return {
        "id": "case",
        "pasted": "Changed in the checklist: Launch\n\n+ Back-cover copy: approved",
        "watched": watched,
    }


def test_a_watched_change_by_one_of_the_persons_own_accounts_is_marked_in_the_packet(env):
    ws, cfg, store = env
    mine = _hand_in_watched(ws, store, watched_case(by_us=True, author="somebody"), NOW)
    theirs = _hand_in_watched(ws, store, watched_case(by_us=False, author="somebody"), NOW)
    pasted = hand_in(ws, store, pasted="Back-cover copy: approved", now=NOW).request
    marked = build(ws, store, cfg, mine, NOW.date()).task.request
    assert '<untrusted source="SRC-' in marked and ' by_us="yes">' in marked
    assert "by_us" not in build(ws, store, cfg, theirs, NOW.date()).task.request
    assert "by_us" not in build(ws, store, cfg, pasted, NOW.date()).task.request
    # The mark is made by the app from the source's own record; it is still outside content, never an instruction.
    assert "<untrusted" in marked and "<note" not in marked


def test_the_prompt_tells_the_assistant_what_the_mark_means(env):
    ws, cfg, store = env
    handed = hand_in(ws, store, pasted=RAW, now=NOW)
    instructions = build(ws, store, cfg, handed.request, NOW.date()).task.instructions
    assert 'by_us="yes"' in instructions and "action.close" in instructions and "action.unhold" in instructions


# ---- a recipient is never guessed ------------------------------------------------------------------------------------


PHRASES = ["I sent", "I've sent", "I emailed"]


def test_the_sentence_that_says_something_was_sent_is_found_by_the_configured_phrases():
    text = "Meeting ran long. I’ve sent the brief this morning! Next up is the proof."
    assert sentence_saying_sent(text, PHRASES) == "i've sent the brief this morning"
    assert sentence_saying_sent("They sent the brief.", PHRASES) is None
    assert sentence_saying_sent("I sent the brief.", []) is None


def test_a_person_is_in_the_text_by_full_name_alias_or_a_word_of_their_name():
    assert names_in(f"I sent it to {NAME}.", [NAME])
    assert names_in(f"I sent it to {LAST}.", [NAME])
    alias = ALIASED["aliases"][0]
    assert names_in(f"I sent it to {alias}.", [ALIASED["full_name"], alias])
    assert not names_in("I sent it to the printer.", [NAME])


def test_a_recipient_is_a_guess_only_when_the_input_says_sent_names_no_one_and_the_op_is_about_what_was_sent():
    said = "I sent the brief this morning."
    sam = [[NAME]]
    ask = f"Did {FIRST} get the brief?"
    assert guessed_recipient(said, ask, sam, PHRASES)
    assert not guessed_recipient(f"{said} {FIRST} has it.", ask, sam, PHRASES)
    assert not guessed_recipient(said, ask, [], PHRASES)  # no one is named by the op
    assert not guessed_recipient(said, "Book the photographer", sam, PHRASES)  # about something else
    assert not guessed_recipient("The brief is ready.", ask, sam, PHRASES)  # nothing was sent


def question_to(person: str, **more) -> dict:
    return {
        "op": "question.add",
        "to": person,
        "title": "Did you get the brief?",
        "text": "The brief went out this morning.",
        "matters_for": "the cover schedule",
        "links": [{"label": "Brief", "url": LINK}],
        **more,
    }


def recipient_findings(env, op, text, note=""):
    return [p for p in problems(env, op, text, note=note) if p.check == "unnamed-recipient"]


def test_a_question_or_action_naming_a_recipient_nobody_gave_is_returned(env):
    _, cfg, store = env
    typesetter = TYPESETTER
    pm = cfg.workspace.user.person
    said = "I sent the brief this morning."
    (found,) = recipient_findings(env, question_to(typesetter["full_name"]), "", note=said)
    assert found.severity == "return" and "Ask the person who it went to" in found.message
    action = {
        "op": "action.add",
        "text": "Chase the brief",
        "owners": [typesetter["full_name"]],
        "evidence": {"quote": said},
    }
    assert recipient_findings(env, action, said)
    # The person's own name, a recipient the input names, and the person's own act are not guesses.
    assert not recipient_findings(env, question_to(pm, kind="decision"), said)
    assert not recipient_findings(
        env, question_to(typesetter["full_name"]), said + f" {typesetter['full_name']} has it."
    )
    assert not [
        p
        for p in problems(env, question_to(typesetter["full_name"]), said, actor="pm")
        if p.check == "unnamed-recipient"
    ]
    cfg.checks.lints["unnamed-recipient"] = "off"
    assert not recipient_findings(env, question_to(typesetter["full_name"]), said)


def test_the_persons_decision_asking_who_it_went_to_applies(env):
    _, cfg, store = env
    said = "I sent the brief this morning."
    op = {
        "op": "question.add",
        "to": cfg.workspace.user.person,
        "kind": "decision",
        "title": "Who did you send this to?",
        "text": "You said you sent the brief but not who received it.",
    }
    assert recipient_findings(env, op, "", note=said) == []
    _, result = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=source(store), raw=said)
    assert result == ["applied"]


# ---- a calendar entry carries its input's project --------------------------------------------------------------------


def entry_op(**more) -> dict:
    return {
        "op": "event.add",
        "title": "Launch reading walkthrough",
        "start": "2026-11-16T14:00:00+00:00",
        "evidence": {"quote": "walkthrough on Monday, November 16 at 2:00 pm UTC"},
        **more,
    }


MAIL = "You are invited to the launch reading walkthrough on Monday, November 16 at 2:00 pm UTC, at the shop."


def run_with(env, op, **hand):
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"ops": [op]}))
    handed = hand_in(ws, store, pasted=MAIL, now=NOW, **hand)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    assert cs_id is not None
    return store.read().list("event")


def test_an_entry_made_from_an_input_the_person_filed_under_a_project_carries_that_project(env):
    [entry] = run_with(env, entry_op(), project=PROJECT)  # the assistant left the project out
    assert entry.data["project"] == PROJECT


def test_an_entry_keeps_the_project_the_assistant_named_and_has_none_when_the_input_has_none(env):
    [entry] = run_with(env, entry_op(project=PROJECT), project=PROJECT)
    assert entry.data["project"] == PROJECT
    ws, cfg, store = env
    for record in store.read().list("event"):
        with store.transaction() as tx:
            tx.delete("event", record.id, WriteContext("pm", "trusted", "test"), read_version=record.version)
    [bare] = run_with(env, entry_op())
    assert bare.data["project"] is None


# ---- the golden cases ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    ["blocker-gone-unhold", "invitation-event", "own-edit-closes-action", "sent-without-recipient"],
)
def test_the_golden_case_passes_with_its_ideal_answer(case):
    report = evaluate(DEMO_B, stub=True, env={}, only=[case])
    assert [(r.case, r.passed, r.missing, r.forbidden, r.extra) for r in report.results] == [(case, True, [], [], [])]


def test_each_case_fails_when_the_answer_does_the_obvious_wrong_thing(tmp_path):
    """The exact scoring catches a close instead of an unhold, and a guessed recipient instead of the question."""
    import shutil
    from pathlib import Path

    import yaml

    template = tmp_path / "ws"
    shutil.copytree(DEMO_B, template)
    for name, ops in (
        (
            "blocker-gone-unhold",
            [{"op": "action.close", "id": "ACT-90", "evidence": {"quote": "The proof sign-off came through"}}],
        ),
        (
            "sent-without-recipient",
            [
                {
                    "op": "question.add",
                    "to": NAME,
                    "title": "Did you get the brief?",
                    "matters_for": "the cover schedule",
                    "links": [{"label": "Brief", "url": LINK}],
                }
            ],
        ),
    ):
        path = Path(template) / "evals" / f"{name}.yaml"
        case = yaml.safe_load(path.read_text())
        case["stub_answer"] = {"summary": "Wrong.", "ops": ops}
        path.write_text(yaml.safe_dump(case))
    report = evaluate(template, stub=True, env={}, only=["blocker-gone-unhold", "sent-without-recipient"])
    assert [r.passed for r in report.results] == [False, False]
