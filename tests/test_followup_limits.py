"""The drafted follow-up message checks a to-do's limit against its owner (design 6.35): what rests on a message limited
to a group is left out of every message to someone outside it, and the screen says so. Names and texts come from the
fixtures through `tests/test_audience.py`."""

from __future__ import annotations

from engine import followups
from tests import test_audience
from tests.test_audience import (
    _TEST,
    INSIDE,
    OPEN_BODY,
    OPEN_WORD,
    OUTSIDE,
    RESTRICTED_BODY,
    RESTRICTED_WORD,
    TODAY,
    hand,
)

env = test_audience.env  # the audience tests' workspace fixture


def action_for(env, owner: str, source: str, raw: str, word: str, quote: str) -> str:
    """An open to-do for `owner` resting on a saved message, the way a run on it records one."""
    _, _, store = env
    with store.transaction() as tx:
        data = {
            "text": f"Check the {word} proof",
            "owners": [{"person": owner}],
            "source": source,
            "evidence": {"source": source, "quote": quote},
        }
        return tx.create("action", data, _TEST).id


def section_of(env, person: str):
    _, cfg, store = env
    return next(s for s in followups.sections(store, cfg, TODAY) if s.person == person)


def test_a_message_leaves_out_what_its_reader_is_outside_of_and_says_so(env):
    _, cfg, store = env
    text, limited = hand(env, RESTRICTED_BODY)
    open_text, open_source = hand(env, OPEN_BODY, subject="Other")
    secret = action_for(env, OUTSIDE["id"], limited, text, RESTRICTED_WORD, "moving the proof date")
    plain = action_for(env, OUTSIDE["id"], open_source, open_text, OPEN_WORD, "The proof date is moving")
    outside = section_of(env, OUTSIDE["id"])
    ids = [a["id"] for a in outside.actions]
    assert plain in ids and secret not in ids
    assert RESTRICTED_WORD not in outside.message and OPEN_WORD in outside.message
    (left,) = outside.limited
    assert (left["kind"], left["id"]) == ("action", secret)
    assert left["limited_to"] == ", ".join(
        [followups.People(store, cfg).name(p) for p in store.read().get("source", limited).data["audience"]["people"]]
    )
    sendable = followups.actions_to_send(store, cfg)
    assert plain in sendable and secret not in sendable  # no message to them carries it, so it isn't marked to send
    assert outside.to_send == len(outside.questions) + sum(a["told"] is None for a in outside.actions)


def test_the_same_to_do_is_in_the_message_to_someone_inside_the_group(env):
    text, limited = hand(env, RESTRICTED_BODY)
    secret = action_for(env, INSIDE["id"], limited, text, RESTRICTED_WORD, "moving the proof date")
    inside = section_of(env, INSIDE["id"])
    assert secret in [a["id"] for a in inside.actions] and inside.limited == []
    assert RESTRICTED_WORD in inside.message


def test_a_question_resting_on_a_limited_message_is_left_out_for_someone_outside_it(env):
    _, cfg, store = env
    _, limited = hand(env, RESTRICTED_BODY)
    with store.transaction() as tx:
        for who in (INSIDE, OUTSIDE):
            tx.create(
                "question",
                {"to": who["id"], "title": f"Is the {RESTRICTED_WORD} file final?", "source": limited},
                _TEST,
            )
    title = f"Is the {RESTRICTED_WORD} file final?"
    assert title in [q["title"] for q in section_of(env, INSIDE["id"]).questions]
    outside = section_of(env, OUTSIDE["id"])
    assert title not in [q["title"] for q in outside.questions] and RESTRICTED_WORD not in outside.message
    assert [x["kind"] for x in outside.limited] == ["question"]


def test_a_follow_up_nudge_does_not_carry_a_limited_to_do_to_someone_outside_it(env):
    _, cfg, store = env
    text, limited = hand(env, RESTRICTED_BODY)
    secret = action_for(env, OUTSIDE["id"], limited, text, RESTRICTED_WORD, "moving the proof date")
    with store.transaction() as tx:  # told long ago, so it is due a follow-up
        found = tx.get("action", secret)
        tx.update("action", secret, {"told": {OUTSIDE["id"]: "2026-01-02"}}, _TEST, read_version=found.version)
    outside = section_of(env, OUTSIDE["id"])
    assert [x["id"] for x in outside.limited] == [secret]
    assert outside.nudge is None or secret not in outside.nudge.action_ids
