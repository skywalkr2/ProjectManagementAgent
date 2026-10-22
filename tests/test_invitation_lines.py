"""An invitation waiting for an answer is a line on Today that opens the entry's page (design 6.32, 7.7). The line is
worked out by rules from the calendar entry's own answer, and goes once the person has answered or an answer is drafted.
Names, ids and times come from the fixtures or are made up here."""

from __future__ import annotations

from datetime import timedelta

from engine import invitation_lines
from engine.today_queue import queue
from tests import test_meetings_people as base
from tests.test_meetings_people import _TEST, NOW, at, entry, person, update

env = base.env  # the meetings tests' workspace fixture


def invitation(store, who: str, **more) -> str:
    organizer = {"name": who, "address": f"{who.split()[0].lower()}@example.com"}
    return entry(store, "Planning session", invitation=True, organizer=organizer, response="needs-action", **more)


def lines(env):
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, NOW) if x.kind == "invitation"]


def test_an_unanswered_invitation_is_a_line_in_decide_that_names_the_entry_and_who_invited(env):
    _, cfg, store = env
    who = "Mira Fictional"
    found = invitation(store, who, start=at(days=2))
    (line,) = lines(env)
    assert (line.group, line.event, line.text, line.subject) == ("decide", found, "Planning session", who)
    assert line.at is not None and line.key == f"invitation:{found}"


def test_an_answered_called_off_past_or_far_off_invitation_has_no_line(env):
    _, cfg, store = env
    who = "Mira Fictional"
    for answer in ("accepted", "tentative", "declined"):
        update(store, "event", invitation(store, who, start=at(days=1)), {"response": answer})
    update(store, "event", invitation(store, who, start=at(days=1)), {"cancelled": True})
    invitation(store, who, start=at(days=-1))  # already begun
    invitation(store, who, start=at(days=cfg.steward.meetings.invitation_days_ahead + 1))
    entry(store, "Not an invitation", start=at(days=1), response="needs-action")
    assert lines(env) == []


def test_the_days_ahead_are_a_setting_and_zero_turns_the_line_off(env):
    _, cfg, store = env
    invitation(store, "Mira Fictional", start=at(days=5))
    cfg.steward.meetings.invitation_days_ahead = 4
    assert lines(env) == []
    cfg.steward.meetings.invitation_days_ahead = 6
    assert len(lines(env)) == 1
    cfg.steward.meetings.invitation_days_ahead = 0
    assert invitation_lines.waiting(env[2], cfg, NOW) == []


def test_a_drafted_answer_ends_the_line_until_it_is_taken_back(env):
    ws, cfg, store = env
    found = invitation(store, "Mira Fictional", start=at(days=1))
    assert len(lines(env)) == 1
    with store.transaction() as tx:
        act = tx.create(
            "act",
            {
                "channel": "copy",
                "status": "draft",
                "target": {"kind": "calendar", "action": "answer", "about": [found], "answer": "accepted"},
            },
            _TEST,
        ).id
    assert lines(env) == []
    update(store, "act", act, {"status": "withdrawn"})
    assert len(lines(env)) == 1


def test_the_soonest_invitation_comes_first(env):
    _, cfg, store = env
    later = invitation(store, "Mira Fictional", start=at(days=3))
    sooner = invitation(store, "Mira Fictional", start=at(days=1, hours=1))
    assert [x.event for x in invitation_lines.waiting(env[2], cfg, NOW)] == [sooner, later]
    assert NOW + timedelta(days=1) < invitation_lines.waiting(env[2], cfg, NOW)[0].start


def test_a_person_is_not_needed_to_name_the_organizer(env):
    _, cfg, store = env
    person(store, "Mira Fictional")
    entry(
        store,
        "Sync",
        start=at(days=1),
        invitation=True,
        response="needs-action",
        organizer={"address": "x@example.com"},
    )
    (line,) = lines(env)
    assert line.subject == "x@example.com"
