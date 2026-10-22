"""A to-do whose blocker is over is no longer on hold, on every line and in the assistant's packet (design 6.9).

The to-do list and Follow-ups already read it (`tests/test_blocked_actions.py`); the promise, reminder, reply and
overdue lines and the packet's list of open actions read the same rule (`engine.blocked.standing_hold`), so a hold that
still stands keeps its line off and one that is over does not. Names and ids come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine import promises, reply_lines
from engine.blocked import standing_hold
from engine.followups import put_on_hold
from engine.names import People
from engine.packet import _open_actions
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.unblocked-lines")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def other(cfg) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != me(cfg))


def make(store, owners, **more) -> str:
    data = {"text": "Send the floor plan", "owners": [{"person": o} for o in owners], **more}
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def asked_of(store, person) -> str:
    with store.transaction() as tx:
        return tx.create("question", {"to": person, "title": "Can the proofs ship?", "status": "sent"}, _TEST).id


def answer(store, question_id) -> None:
    with store.transaction() as tx:
        found = tx.get("question", question_id)
        tx.update("question", question_id, {"status": "answered", "answer": "Yes"}, _TEST, read_version=found.version)


def blocked_on_a_question(store, action_id, who) -> str:
    asked = asked_of(store, who)
    put_on_hold(store, action_id, on=asked, now=NOW)
    return asked


def data(store, action_id) -> dict:
    return store.read().get("action", action_id).data


def test_a_hold_stands_until_its_blocker_is_over_and_a_hold_of_words_always_stands(env):
    _, cfg, store = env
    mine, who = make(store, [me(cfg)]), other(cfg)
    put_on_hold(store, mine, "the printer's quote", now=NOW)
    assert standing_hold(store.read(), data(store, mine))
    put_on_hold(store, mine, "the printer's quote", now=NOW)
    asked = blocked_on_a_question(store, mine, who)
    assert standing_hold(store.read(), data(store, mine))
    answer(store, asked)
    assert standing_hold(store.read(), data(store, mine)) is None
    assert standing_hold(store.read(), {"text": "no hold"}) is None


def test_a_reminder_for_a_blocked_to_do_waits_until_its_blocker_is_over(env):
    ws, cfg, store = env
    mine = make(store, [me(cfg)], remind_at=(NOW - timedelta(minutes=30)).isoformat())
    asked = blocked_on_a_question(store, mine, other(cfg))
    kept = lambda: [x for x in queue(ws, store, cfg, NOW) if x.kind == "reminder"]  # noqa: E731
    assert kept() == []
    answer(store, asked)
    assert [x.actions for x in kept()] == [[mine]]


def test_a_reply_owed_for_a_blocked_to_do_comes_back_once_its_blocker_is_over(env):
    ws, cfg, store = env
    mine = make(store, [me(cfg)], reply_owed=True, reply="Next week.")
    asked = blocked_on_a_question(store, mine, other(cfg))
    assert [o.action for o in reply_lines.plan(ws, store.read())] == []
    answer(store, asked)
    assert [o.action for o in reply_lines.plan(ws, store.read())] == [mine]


def test_a_promise_someone_owes_is_chased_again_once_the_blocker_of_its_hold_is_over(env):
    _, cfg, store = env
    them = other(cfg)
    long_ago = TODAY - timedelta(days=cfg.ui.followups.undated_after_days + 30)
    store.clock = lambda: f"{long_ago}T09:00:00+00:00"
    theirs = make(store, [them], due=None)
    asked = blocked_on_a_question(store, theirs, them)

    def chase() -> list[str]:
        found = promises.late(store.read(), cfg, me(cfg), TODAY, set(), lambda _id: long_ago)
        return [x.action for x in found if x.action == theirs]

    assert chase() == []
    answer(store, asked)
    assert chase() == [theirs]


def test_an_overdue_to_do_that_was_blocked_is_on_the_overdue_line_again_once_its_blocker_is_over(env):
    ws, cfg, store = env
    mine = make(store, [me(cfg)], due=(TODAY - timedelta(days=3)).isoformat())
    asked = blocked_on_a_question(store, mine, other(cfg))
    overdue = lambda: [x for x in queue(ws, store, cfg, NOW) if x.kind == "overdue" and mine in x.actions]  # noqa: E731
    assert overdue() == []
    answer(store, asked)
    assert len(overdue()) == 1


def test_the_assistants_list_of_open_actions_says_on_hold_only_while_the_hold_stands(env):
    _, cfg, store = env
    mine = make(store, [me(cfg)], text="Confirm the print run")
    asked = blocked_on_a_question(store, mine, other(cfg))
    people = People(store, cfg)
    line = lambda: next(x for x in _open_actions(store, people).splitlines() if "Confirm the print run" in x)  # noqa: E731
    assert "on hold" in line() and "blocked on" in line()
    answer(store, asked)
    assert "on hold" not in line() and "blocked on" not in line()
