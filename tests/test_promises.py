"""Promises are actions (design 6.33): dates read by rules first, endings as ops with evidence, and an ending read from
what came in waits for the person."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import ENDING_WAITS, release
from engine.dispatcher import process
from engine.intake import hand_in
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

#: A Friday afternoon: "by Tuesday" is the 13th, "next Friday" is read with doubt.
NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
_SETUP = WriteContext(actor="pm", trust="trusted", op="test.promises")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def someone() -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role"))


def answer(*ops: dict) -> None:
    body = json.dumps({"summary": "Promises.", "ops": list(ops)})
    set_responder(lambda task: body)


def run(env, *, pasted: str = "", note: str = ""):
    ws, cfg, store = env
    handed = hand_in(ws, store, note=note, pasted=pasted, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    return store.read().get("changeset", cs_id).data["ops"], cs_id


def open_action(store, text: str = "Send the floor plan to the printer") -> str:
    with store.transaction() as tx:
        return tx.create("action", {"text": text, "owners": [{"person": someone()["id"]}]}, _SETUP).id


def action(store, action_id: str) -> dict:
    return store.read().get("action", action_id).data


def made_action(store, outcome: dict) -> dict:
    ref = next(r for r in outcome["records"] if r["kind"] == "action")
    return action(store, ref["id"])


def test_a_promise_keeps_who_it_is_owed_to_how_it_is_known_and_its_date_from_the_rules(env):
    _, _, store = env
    owner = someone()
    said = "I will send the floor plan by Tuesday."
    answer(
        {
            "op": "action.add",
            "text": "Send the floor plan",
            "owners": [owner["id"]],
            "promised_to": [owner["id"]],
            "basis": "said",
            "said_by": owner["id"],
            "due_words": "by Tuesday",
            "due": "2026-12-01",
            "evidence": {"quote": said},
        }
    )
    (outcome,), _ = run(env, pasted=said)
    made = made_action(store, outcome)
    assert made["due"] == date(2026, 10, 13).isoformat()  # the rules' reading wins over the model's date
    assert (made["due_words"], made["due_check"]) == ("by Tuesday", False)
    assert (made["promised_to"], made["basis"], made["said_by"]) == ([owner["id"]], "said", owner["id"])


@pytest.mark.parametrize(
    ("words", "due", "check"),
    [("next Friday", "2026-10-16", True), ("sometime soon", None, False), ("early next week", "2026-10-14", False)],
)
def test_doubtful_words_are_checked_and_vague_words_give_no_date(env, words, due, check):
    _, _, store = env
    said = f"They will get back to us {words}."
    answer(
        {
            "op": "action.add",
            "text": "Get back to us",
            "owners": [someone()["id"]],
            "due_words": words,
            "evidence": {"quote": said},
        }
    )
    (outcome,), _ = run(env, pasted=said)
    made = made_action(store, outcome)
    assert (made["due"], made["due_check"]) == (due, check)


@pytest.mark.parametrize(
    "ending",
    [
        {"op": "action.close"},
        {"op": "action.drop", "reason": "The printer no longer needs it"},
        {"op": "action.move", "due_words": "by Tuesday"},
        {"op": "action.part", "delivered": "The first floor plan", "left": "Send the second floor plan"},
    ],
)
def test_an_ending_read_from_what_came_in_waits_for_the_person(env, ending):
    _, _, store = env
    target = open_action(store)
    said = "The floor plan was sent over to the printer this morning."
    answer({**ending, "id": target, "evidence": {"quote": said}})
    (outcome,), _ = run(env, pasted=said)
    assert outcome["status"] == "held" and ENDING_WAITS in outcome["reason"]
    assert action(store, target)["status"] == "open" and action(store, target)["due"] is None


def test_the_person_keeping_an_ending_applies_it(env):
    _, cfg, store = env
    target = open_action(store)
    said = "The first floor plan went to the printer; the second is still to come by Tuesday."
    answer(
        {
            "op": "action.part",
            "id": target,
            "delivered": "The first floor plan",
            "left": "Send the second floor plan",
            "evidence": {"quote": said},
        }
    )
    _, cs_id = run(env, pasted=said)
    release(store, cfg, cs_id, 0)
    kept = action(store, target)
    assert kept["status"] == "open" and kept["text"] == "Send the second floor plan"
    assert [(n["text"], n["delivered"], n["quote"]) for n in kept["news"]] == [("The first floor plan", True, said)]


def test_an_ending_in_the_persons_own_note_applies_at_once(env):
    _, _, store = env
    target = open_action(store)
    note = "I sent the floor plan to the printer."
    answer({"op": "action.close", "id": target, "evidence": {"quote": note}})
    (outcome,), _ = run(env, note=note)
    assert outcome["status"] == "applied" and action(store, target)["status"] == "done"


def test_news_that_does_not_end_a_promise_applies_and_it_stays_open(env):
    _, _, store = env
    target = open_action(store)
    said = "Thanks for the reminder about the floor plan, I will look into it."
    answer({"op": "action.news", "id": target, "text": "Replied without saying when", "evidence": {"quote": said}})
    (outcome,), _ = run(env, pasted=said)
    assert outcome["status"] == "applied"
    kept = action(store, target)
    assert kept["status"] == "open" and [n["text"] for n in kept["news"]] == ["Replied without saying when"]


def test_news_and_moves_need_an_open_action(env):
    _, _, store = env
    said = "The floor plan is late."
    answer({"op": "action.news", "id": "ACT-999", "text": "Late", "evidence": {"quote": said}})
    (outcome,), _ = run(env, pasted=said)
    assert outcome["status"] == "refused"
