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


def test_a_promise_that_holds_only_once_something_happens_starts_on_hold(env):
    _, _, store = env
    owner = someone()
    said = "Once the keys arrive I will send the floor plan."
    answer(
        {
            "op": "action.add",
            "text": "Send the floor plan",
            "owners": [owner["id"]],
            "promised_to": [owner["id"]],
            "waiting_for": "the keys  arrive",
            "evidence": {"quote": said},
        }
    )
    (outcome,), _ = run(env, pasted=said)
    made = made_action(store, outcome)
    assert made["on_hold"]["waiting_for"] == "the keys arrive"
    assert made["status"] == "open" and made["due"] is None


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


# ---- on hold, meetings, the message's own day, one owner per promise, several sources, credit, aliases ------------


def event(store, start: str, title: str = "Planning meeting") -> str:
    with store.transaction() as tx:
        return tx.create("event", {"title": title, "start": start, "trust": "trusted"}, _SETUP).id


def test_taking_a_promise_off_hold_with_its_new_date_is_one_step_the_person_keeps(env):
    _, cfg, store = env
    target = open_action(store)
    with store.transaction() as tx:
        current = tx.get("action", target)
        hold = {"waiting_for": "the vendor confirms", "since": "2026-10-01"}
        tx.update("action", target, {"on_hold": hold}, _SETUP, read_version=current.version)
    said = "The vendor confirmed, so the floor plan can go to the printer by Tuesday."
    answer({"op": "action.unhold", "id": target, "due_words": "by Tuesday", "evidence": {"quote": said}})
    (outcome,), cs_id = run(env, pasted=said)
    assert outcome["status"] == "held"
    release(store, cfg, cs_id, 0)
    kept = action(store, target)
    assert kept["on_hold"] is None and kept["due"] == "2026-10-13" and kept["due_words"] == "by Tuesday"


def test_a_promise_due_at_a_meeting_moves_with_it_and_the_move_is_not_news(env):
    from engine.applier import apply_as_person

    _, cfg, store = env
    meeting = event(store, "2026-10-15T15:00")
    said = "I will bring the floor plan to Thursday's meeting."
    answer(
        {
            "op": "action.add",
            "text": "Bring the floor plan",
            "owners": [someone()["id"]],
            "event": meeting,
            "due_at_event": True,
            "due_words": "by Thursday's meeting",
            "evidence": {"quote": said},
        }
    )
    (outcome,), _ = run(env, pasted=said)
    made = made_action(store, outcome)
    assert (made["due"], made["due_event"]) == ("2026-10-15", meeting)
    # The person moves the meeting on screen; the promise due at it moves with it, with no news line.
    version = store.read().get("event", meeting).version
    edit = {"op": "record.edit", "record": {"kind": "event", "id": meeting}, "fields": {"start": "2026-10-20T15:00"}}
    apply_as_person(store, cfg, [{**edit, "read_version": version}], "Moved the meeting")
    moved = action(store, next(r["id"] for r in outcome["records"] if r["kind"] == "action"))
    assert moved["due"] == "2026-10-20" and moved["news"] == []


def test_relative_dates_read_against_the_message_and_its_senders_zone_whenever_it_is_read(env):
    ws, cfg, store = env
    said = "I will send the floor plan tomorrow."
    dues = []
    for read_on in (NOW, NOW.replace(day=19)):
        answer(
            {
                "op": "action.add",
                "text": "Send the floor plan",
                "owners": [someone()["id"]],
                "due_words": "tomorrow",
                "evidence": {"quote": said},
            }
        )
        handed = hand_in(ws, store, pasted=said, now=read_on)
        with store.transaction() as tx:
            saved = tx.get("source", handed.source)
            # Sent late in the evening on the 9th where the sender was, already the 10th in the workspace's zone.
            tx.update(
                "source", handed.source, {"sent_at": "2026-10-09T23:30:00-07:00"}, _SETUP, read_version=saved.version
            )
        cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=read_on)
        (outcome,) = store.read().get("changeset", cs_id).data["ops"]
        dues.append(made_action(store, outcome)["due"])
    assert dues == ["2026-10-10", "2026-10-10"]


def test_one_promise_per_owner(env):
    _, _, store = env
    people = [p["id"] for p in fixture_records(DEMO_B, "person")[:2]]
    said = "Sam and I will draft the floor plan."
    answer(
        {
            "op": "action.add",
            "text": "Draft the floor plan",
            "owners": people,
            "promised_to": [people[0]],
            "evidence": {"quote": said},
        }
    )
    (outcome,), _ = run(env, pasted=said)
    assert outcome["status"] == "refused" and "one promise per owner" in outcome["reason"]


def test_the_same_promise_from_two_sources_is_one_record_with_both_quotes_and_a_shown_disagreement(env):
    _, _, store = env
    owner, person = someone()["id"], env[1].workspace.user.person
    first = "I will send the floor plan by Tuesday."
    later = "Following up from the meeting: I will send the floor plan by Wednesday."
    for quote, words in ((first, "by Tuesday"), (later, "by Wednesday")):
        answer(
            {
                "op": "action.add",
                "text": "Send the floor plan",
                "owners": [owner],
                "promised_to": [person],
                "due_words": words,
                "evidence": {"quote": quote},
            }
        )
        run(env, pasted=quote)
    (promise,) = [a.data for a in store.read().list("action") if a.data["text"] == "Send the floor plan"]
    assert promise["due"] == "2026-10-14"  # the newest wins when the person said neither
    assert [e["quote"] for e in promise["also_said"]] == [later]
    assert any("by Tuesday" in n["text"] for n in promise["news"])


def test_the_persons_own_date_wins_over_a_later_source(env):
    _, _, store = env
    owner, person = someone()["id"], env[1].workspace.user.person
    mine = "Sam will send me the floor plan by Tuesday."
    answer(
        {
            "op": "action.add",
            "text": "Send the floor plan",
            "owners": [owner],
            "promised_to": [person],
            "due_words": "by Tuesday",
            "evidence": {"quote": mine},
        }
    )
    run(env, note=mine)
    theirs = "I will send the floor plan by Friday."
    answer(
        {
            "op": "action.add",
            "text": "Send the floor plan",
            "owners": [owner],
            "promised_to": [person],
            "due_words": "by Friday",
            "evidence": {"quote": theirs},
        }
    )
    run(env, pasted=theirs)
    (promise,) = [a.data for a in store.read().list("action") if a.data["text"] == "Send the floor plan"]
    assert promise["due"] == "2026-10-13" and any("your date stays" in n["text"] for n in promise["news"])


def test_chasing_is_news_and_a_reported_done_is_credited_to_its_owner(env):
    _, cfg, store = env
    target = open_action(store)
    owner = someone()["id"]
    note = "I pinged them about the floor plan."
    answer({"op": "action.news", "id": target, "text": "Pinged about it", "evidence": {"quote": note}})
    run(env, note=note)
    assert action(store, target)["status"] == "open"
    note = "They sent the floor plan to the printer."
    answer({"op": "action.close", "id": target, "evidence": {"quote": note}})
    run(env, note=note)
    done = action(store, target)
    assert done["status"] == "done" and done["done_by"] == [owner] and done["reported_by"] == cfg.workspace.user.person


def test_a_second_spelling_the_person_confirms_becomes_an_alias_so_one_person_keeps_one_list(env):
    _, cfg, store = env
    known = someone()
    first, last = known["full_name"].split()[0], known["full_name"].split()[-1]
    spelled = f"{first} Q. {last}"
    said = f"{spelled} will send the floor plan."
    answer({"op": "action.add", "text": "Send the floor plan", "owners": [spelled], "evidence": {"quote": said}})
    (outcome,), cs_id = run(env, pasted=said)
    assert outcome["status"] == "held"
    release(store, cfg, cs_id, 0, person=known["id"])
    assert spelled in store.read().get("person", known["id"]).data["aliases"]
    answer({"op": "action.add", "text": "Send the cover file", "owners": [spelled], "evidence": {"quote": said}})
    (again,), _ = run(env, pasted=said)
    assert again["status"] == "applied" and [o["person"] for o in made_action(store, again)["owners"]] == [known["id"]]
