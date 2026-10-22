"""A message to send says since when it has been ready (design 7.13): the day its oldest ask became ready to send, kept
by the server from the ledger, so a stale batch shows. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.followups import hold_question, mark_sent, sections
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

_PM = WriteContext("pm", "trusted", "test")
ASKED = next(q for q in fixture_records(DEMO_B, "question") if q["to"] != "")["to"]
START = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)  # a Monday, long after anything the fixtures hold


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> str:
        return self.now.isoformat(timespec="seconds")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    clock = Clock()
    store = Store(ws.db_path, cfg=cfg, clock=clock)
    yield cfg, store, clock
    store.close()


def _mine(store, cfg, today):
    return next(s for s in sections(store, cfg, today) if s.person == ASKED)


def test_a_question_is_ready_since_the_day_it_was_made_and_the_message_since_its_oldest(env):
    cfg, store, clock = env
    clock.now = START + timedelta(days=2, hours=3)
    with store.transaction() as tx:
        first = tx.create("question", {"to": ASKED, "title": "Which cover is final?"}, _PM).id
    clock.now = START + timedelta(days=4)
    with store.transaction() as tx:
        second = tx.create("question", {"to": ASKED, "title": "Who signs off the proof?"}, _PM).id
    today = (START + timedelta(days=5)).date()
    section = _mine(store, cfg, today)
    ready = {q["id"]: q["ready_since"] for q in section.questions}
    assert ready[first] == (START + timedelta(days=2)).date().isoformat()
    assert ready[second] == (START + timedelta(days=4)).date().isoformat()
    # Whatever the fixtures left ready is older still or equal: the message is ready since its oldest ask.
    assert section.ready_since == min(x for x in ready.values() if x)
    assert section.ready_since <= ready[first]


def test_a_question_held_for_a_day_is_ready_again_from_that_day(env):
    cfg, store, clock = env
    with store.transaction() as tx:
        q = tx.create("question", {"to": ASKED, "title": "Which cover is final?"}, _PM).id
    monday = (START + timedelta(days=7)).date()
    assert hold_question(store, q, {"on": monday.isoformat()}, today=START.date()) is None
    # While held it is in Later and is not what the message waits on.
    held = _mine(store, cfg, START.date())
    assert q not in [x["id"] for x in held.questions] and q in [x["id"] for x in held.later]
    back = _mine(store, cfg, monday + timedelta(days=1))
    assert next(x["ready_since"] for x in back.questions if x["id"] == q) == monday.isoformat()


def test_an_action_is_ready_from_the_day_it_was_made_and_again_after_it_changes_once_told(env):
    cfg, store, clock = env
    clock.now = START + timedelta(days=1)
    with store.transaction() as tx:
        action = tx.create("action", {"text": "Tell the printer", "owners": [{"person": ASKED}]}, _PM).id
    day = (START + timedelta(days=1)).date()
    mine = lambda today: next(a for a in _mine(store, cfg, today).actions if a["id"] == action)  # noqa: E731
    assert mine(day)["ready_since"] == day.isoformat()
    clock.now = START + timedelta(days=2)
    mark_sent(store, cfg, ASKED, now=START + timedelta(days=2))
    assert mine(day)["told"] is not None and mine(day)["ready_since"] is None
    clock.now = START + timedelta(days=6)
    rec = store.read().get("action", action)
    with store.transaction() as tx:
        tx.update("action", action, {"text": "Tell the printer about the proof"}, _PM, read_version=rec.version)
    changed = mine((START + timedelta(days=6)).date())
    assert changed["told"] is None and changed["ready_since"] == (START + timedelta(days=6)).date().isoformat()
