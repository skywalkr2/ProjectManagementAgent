"""A promise past its date with no news is a line with its choices (design 6.33): the person's own and the ones they
wait on, never twice on Today, and the held ending that would settle one is its own line. Names, ids and texts come
from the fixtures."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from engine import held_ask
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import process
from engine.intake import hand_in
from engine.names import People
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.promise-lines")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    # The defaults, whatever the fictional workspace sets: the cases below name their days.
    cfg = ws.config(env={"COCKPIT__STEWARD__CHASE_UNDATED_DAYS": "14", "COCKPIT__STEWARD__CHASE_DATED_DAYS": "7"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def me(cfg) -> str:
    return cfg.workspace.user.person


def other(cfg) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != me(cfg))


def make(
    store, owners: list[str], *, due: date | None, text: str = "Send the floor plan", made: date | None = None, **more
) -> str:
    """An action, made on the day `made` (a week before the test's today when not said)."""
    data = {"text": text, "owners": [{"person": o} for o in owners], "due": due.isoformat() if due else None, **more}
    store.clock = lambda: f"{made or TODAY - timedelta(days=7)}T09:00:00+00:00"
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def lines(env, **match):
    ws, cfg, store = env
    return [line for line in queue(ws, store, cfg, NOW) if all(getattr(line, k) == v for k, v in match.items())]


def promise_lines(env, action_id: str):
    """The lines that chase or wait on an action: its own promise line, or the person's one follow-up line (6.33)."""
    ws, cfg, store = env
    return [
        line for line in queue(ws, store, cfg, NOW) if line.kind in ("promise", "nudge") and action_id in line.actions
    ]


def update(store, action_id: str, changes: dict) -> None:
    with store.transaction() as tx:
        tx.update("action", action_id, changes, _TEST, read_version=tx.get("action", action_id).version)


PAST = TODAY - timedelta(days=3)


def test_a_promise_someone_else_owes_past_its_date_is_on_that_persons_follow_up_line(env):
    _, cfg, store = env
    them = other(cfg)
    action = make(store, [them], due=PAST, promised_to=[me(cfg)], basis="said")
    (line,) = promise_lines(env, action)
    assert (line.kind, line.group, line.person, line.key) == ("nudge", "send", them, f"nudge:{them}")
    assert action in line.actions and line.overdue >= 1 and line.due <= PAST.isoformat()
    # It is not a line of its own as well.
    assert [x for x in lines(env, kind="promise") if action in x.actions] == []


def test_any_dated_action_someone_else_owns_is_waited_on_even_with_no_promise_fields(env):
    _, cfg, store = env
    action = make(store, [other(cfg)], due=PAST)
    (line,) = promise_lines(env, action)
    assert line.person == other(cfg)


def test_the_persons_own_promise_has_the_same_line_with_nobody_to_chase(env):
    _, cfg, store = env
    action = make(store, [me(cfg)], due=PAST, promised_to=[other(cfg)], basis="said")
    (line,) = promise_lines(env, action)
    assert (line.group, line.person, line.due) == ("risk", None, PAST.isoformat())


def test_a_promise_is_never_on_the_overdue_line_as_well_but_a_plain_to_do_still_is(env):
    _, cfg, store = env
    promise = make(store, [me(cfg)], due=PAST, promised_to=[other(cfg)], basis="inferred")
    plain = make(store, [me(cfg)], due=PAST, text="Water the plants")
    overdue = [line for line in lines(env, kind="overdue")]
    held_by_overdue = {a for line in overdue for a in line.actions}
    assert plain in held_by_overdue and promise not in held_by_overdue
    assert len(promise_lines(env, promise)) == 1 and promise_lines(env, plain) == []


def test_news_since_its_date_a_held_ending_a_hold_or_a_future_date_leave_no_line(env):
    _, cfg, store = env
    them = other(cfg)
    news = make(store, [them], due=PAST, news=[{"on": TODAY.isoformat(), "text": "Replied, no date"}])
    old_news = make(store, [them], due=PAST, news=[{"on": (PAST - timedelta(days=2)).isoformat(), "text": "Early"}])
    held = make(store, [them], due=PAST, on_hold={"waiting_for": "the proof", "since": TODAY.isoformat()})
    future = make(store, [them], due=TODAY + timedelta(days=cfg.steward.chase_dated_days + 2))
    undated = make(store, [them], due=None)
    done = make(store, [them], due=PAST, status="done")
    assert promise_lines(env, news) == [] and promise_lines(env, held) == []
    assert promise_lines(env, future) == [] and promise_lines(env, undated) == [] and promise_lines(env, done) == []
    assert len(promise_lines(env, old_news)) == 1  # news from before the date is not news since


def test_a_held_ending_is_its_own_line_and_the_promise_waits_for_the_answer(env):
    ws, cfg, store = env
    action = make(store, [other(cfg)], due=PAST)
    said = "The floor plan went out this morning."
    body = json.dumps(
        {"summary": "Closed.", "ops": [{"op": "action.close", "id": action, "evidence": {"quote": said}}]}
    )
    set_responder(lambda task: body)
    handed = hand_in(ws, store, pasted=said, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "held"
    (held,) = lines(env, kind="held")
    assert held.held["ask"] == "close" and held.held["record"] == action and held.held["quote"] == said
    assert promise_lines(env, action) == []  # the held ending is the one line for it


def test_a_chase_hides_the_action_until_the_follow_up_wait_is_over_and_it_is_then_on_one_line_only(env):
    ws, cfg, store = env
    them = other(cfg)
    wait = cfg.ui.followups.question_after_days
    action = make(store, [them], due=PAST, told={them: (TODAY - timedelta(days=wait - 1)).isoformat()})
    assert promise_lines(env, action) == []  # chased a day ago: it waits
    update(store, action, {"told": {them: (TODAY - timedelta(days=wait)).isoformat()}})
    # Due a nudge and late as a promise, Today carries it once, on the person's follow-up line.
    assert [line.kind for line in lines(env) if action in line.actions] == ["nudge"]


def test_a_chased_promise_with_news_since_its_date_keeps_its_place_on_the_follow_up_line(env):
    _, cfg, store = env
    them = other(cfg)
    wait = cfg.ui.followups.question_after_days
    action = make(
        store,
        [them],
        due=PAST,
        told={them: (TODAY - timedelta(days=wait)).isoformat()},
        news=[{"on": TODAY.isoformat(), "text": "Replied, no date"}],
    )
    assert [x for x in lines(env, kind="promise") if action in x.actions] == []
    assert action in {a for line in lines(env, kind="nudge") for a in line.actions}


# ---- when the person's waiting-ons get a line: the clock for each case (settings steward.*) -----------------------


def test_an_undated_waiting_on_gets_a_line_after_the_undated_days_and_not_a_day_before(env):
    _, cfg, store = env
    them, days = other(cfg), 14
    assert cfg.steward.chase_undated_days == days
    early = make(store, [them], due=None, made=TODAY - timedelta(days=13))
    due = make(store, [them], due=None, made=TODAY - timedelta(days=days))
    assert promise_lines(env, early) == []
    (line,) = promise_lines(env, due)
    assert (line.kind, line.person, line.group) == ("nudge", them, "send") and line.waiting_days >= days


def test_news_or_a_chase_restarts_the_undated_clock(env):
    _, cfg, store = env
    them, days = other(cfg), cfg.steward.chase_undated_days
    old = TODAY - timedelta(days=days + 5)
    heard = make(
        store,
        [them],
        due=None,
        made=old,
        news=[{"on": (TODAY - timedelta(days=days - 1)).isoformat(), "text": "Replied"}],
    )
    chased = make(store, [them], due=None, made=old, told={them: (TODAY - timedelta(days=days - 1)).isoformat()})
    quiet = make(store, [them], due=None, made=old)
    own = lambda action: [x for x in lines(env, kind="promise") if action in x.actions]  # noqa: E731
    assert own(heard) == [] and own(chased) == [] and promise_lines(env, heard) == []
    assert promise_lines(env, quiet)[0].waiting_days >= days + 5


def test_a_dated_waiting_on_gets_a_line_only_within_the_dated_days_before_its_date(env):
    _, cfg, store = env
    them, days = other(cfg), 7
    assert cfg.steward.chase_dated_days == days
    too_far = make(store, [them], due=TODAY + timedelta(days=8))
    in_window = make(store, [them], due=TODAY + timedelta(days=days))
    assert promise_lines(env, too_far) == []
    (line,) = promise_lines(env, in_window)
    assert line.kind == "nudge" and in_window in line.actions


def test_a_waiting_on_on_hold_never_gets_a_line_dated_or_not(env):
    _, cfg, store = env
    them = other(cfg)
    hold = {"waiting_for": "the proof", "since": TODAY.isoformat()}
    dated = make(store, [them], due=PAST, on_hold=hold)
    undated = make(
        store, [them], due=None, made=TODAY - timedelta(days=cfg.steward.chase_undated_days + 30), on_hold=hold
    )
    assert promise_lines(env, dated) == [] and promise_lines(env, undated) == []


def test_the_persons_own_undated_or_upcoming_promise_has_no_line_before_its_date(env):
    _, cfg, store = env
    upcoming = make(store, [me(cfg)], due=TODAY + timedelta(days=1), promised_to=[other(cfg)], basis="said")
    undated = make(store, [me(cfg)], due=None, made=TODAY - timedelta(days=60), promised_to=[other(cfg)], basis="said")
    assert promise_lines(env, upcoming) == [] and promise_lines(env, undated) == []


def test_a_held_ending_is_described_as_what_the_input_says_happened(env):
    _, cfg, store = env
    them = other(cfg)
    people = People(store, cfg)
    action = make(store, [them], due=PAST)
    view = store.read()
    quote = "it went out this morning"
    close = held_ask.describe(
        view, people, {"op": "action.close", "id": action, "evidence": {"quote": quote}}, reporter=them
    )
    assert close["ask"] == "close" and close["record"] == action and close["quote"] == quote
    assert close["owners"] == [people.owner({"person": them})] and close["reporter"] == people.name(them)
    moved = held_ask.describe(
        view, people, {"op": "action.move", "id": action, "due_words": "next Tuesday", "evidence": {"quote": quote}}
    )
    assert moved["ask"] == "move" and moved["due_words"] == "next Tuesday" and moved["value"] is None
    part = held_ask.describe(
        view,
        people,
        {"op": "action.part", "id": action, "delivered": "the draft", "left": "Send the final", "evidence": None},
    )
    assert (part["ask"], part["delivered"], part["left"]) == ("part", "the draft", "Send the final")
    dropped = held_ask.describe(
        view, people, {"op": "action.drop", "id": action, "reason": "no longer needed", "evidence": None}
    )
    assert dropped["ask"] == "drop" and dropped["reason"] == "no longer needed" and dropped["record"] == action
