"""The line about a promise gone quiet can be snoozed to a day it offers, with Undo, and a promise someone owes the
person can be followed up from it as a drafted act (design 6.32, 7.7). Names and ids come from the fixtures or are made
up here."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from engine import quiet_follow_up, suggestions
from engine.today_queue import queue
from tests import test_meetings_people as base
from tests.test_meetings_people import NOW, TODAY, me, person, promise

env = base.env  # the meetings tests' workspace fixture
client = base.client  # and its API client


def line_of(env):
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, NOW) if x.kind == "quiet_promise"]


def quiet_from(env, who="Ana Guest", days=8):
    """A promise someone owes the person, quiet for `days`: long enough for the quiet line and short of the follow-up
    line's own wait, so the quiet line is the one Today shows."""
    _, cfg, store = env
    ana = person(store, who)
    store.clock = lambda: f"{TODAY - timedelta(days=days)}T09:00:00+00:00"
    return ana, promise(store, cfg, ana, me(cfg), "Return the contract")


def test_the_line_offers_the_configured_days_each_with_the_day_it_comes_back(env):
    _, cfg, _ = env
    quiet_from(env)
    (line,) = line_of(env)
    assert [x["days"] for x in line.snooze_days] == cfg.steward.people.snooze_days
    assert [x["on"] for x in line.snooze_days] == [(TODAY + timedelta(days=n)).isoformat() for n in (1, 3, 7, 14)]
    cfg.steward.people.snooze_days = [2, 0, 2]
    assert [x["days"] for x in line_of(env)[0].snooze_days] == [2]


def test_a_snoozed_line_stays_off_until_its_day_and_taking_it_back_shows_it_again(env):
    ws, cfg, store = env
    _, action = quiet_from(env)
    (line,) = line_of(env)
    until = TODAY + timedelta(days=1)
    made = suggestions.snooze(store, cfg, line.key, line.actions, until, NOW)
    assert line_of(env) == [] and suggestions.snoozed(store.read(), TODAY) == {line.key: until}
    assert suggestions.snoozed(store.read(), until) == {}  # its day has come
    assert len([x for x in queue(ws, store, cfg, NOW + timedelta(days=1)) if x.kind == "quiet_promise"]) == 1
    assert suggestions.take_back(store, made) is True
    assert len(line_of(env)) == 1 and action in line_of(env)[0].actions


def test_a_snooze_is_not_a_not_now_and_does_not_use_up_the_days_cap(env):
    ws, cfg, store = env
    quiet_from(env)
    (line,) = line_of(env)
    suggestions.snooze(store, cfg, line.key, line.actions, TODAY + timedelta(days=1), NOW)
    view = store.read()
    assert suggestions.dismissed(view) == {} and suggestions._put_off_today(view, cfg, NOW) == ()


def test_the_follow_up_is_written_from_the_wording_sheet_for_whoever_owes_the_promise(env):
    _, cfg, store = env
    ana, action = quiet_from(env)
    found = quiet_follow_up.draft(store, cfg, action, TODAY)
    words = cfg.language.messages
    assert found is not None and found.person == ana
    assert found.subject == words.quiet_subject.format(text="Return the contract")
    assert found.body.splitlines()[0] == words.greeting.format(first_name="Ana")
    assert words.quiet_intro in found.body and "Return the contract" in found.body and words.closing in found.body


def test_a_promise_the_person_made_has_no_follow_up_to_send(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    store.clock = lambda: f"{TODAY - timedelta(days=8)}T09:00:00+00:00"
    mine = promise(store, cfg, me(cfg), ana, "Send Ana the cover")
    assert len(line_of(env)) == 1
    assert quiet_follow_up.draft(store, cfg, mine, TODAY) is None


def test_the_routes_snooze_with_undo_and_write_the_follow_up(client):
    http, store, cfg = client
    ana = person(store, "Ana Guest")
    today = datetime.now(UTC).date()
    store.clock = lambda: f"{today - timedelta(days=8)}T09:00:00+00:00"
    action = promise(store, cfg, ana, me(cfg), "Return the contract")
    found = next(x for x in http.get("/api/today/queue").json() if x["kind"] == "quiet_promise")
    assert [x["days"] for x in found["snooze_days"]] == [1, 3, 7, 14]
    written = http.get(f"/api/quiet-promises/{action}/follow-up").json()
    assert written["person"] == ana and written["person_name"] == "Ana Guest"
    assert written["parts"]["subject"] == "Checking in: Return the contract"
    assert "Return the contract" in written["parts"]["body"]
    refused = http.post(f"/api/quiet-promises/{action}/snooze", json={"until": (today + timedelta(days=2)).isoformat()})
    assert refused.status_code == 422  # not one of the days the line offers
    until = found["snooze_days"][1]["on"]
    done = http.post(f"/api/quiet-promises/{action}/snooze", json={"until": until})
    assert done.status_code == 200 and done.json()["until"] == until
    assert not [x for x in http.get("/api/today/queue").json() if x["kind"] == "quiet_promise"]
    assert http.post(f"/api/suggestions/not-now/{done.json()['signal']}/undo").status_code == 200
    assert [x for x in http.get("/api/today/queue").json() if x["kind"] == "quiet_promise"]
    gone = http.post("/api/quiet-promises/ACT-9999/snooze", json={"until": until})
    assert gone.status_code == 404 and http.get("/api/quiet-promises/ACT-9999/follow-up").status_code == 404
