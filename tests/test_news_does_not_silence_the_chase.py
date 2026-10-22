"""News mustn't silence the chase clock (design 6.33; the functional designer's answer F22, B-7).

A reply that doesn't answer is news on the open action (`action.news`, which records it as a non-answer). It restarts
the chase clock once: at the dated window (`ui.followups.action_due_within_days`) for a dated promise, at the undated
wait for an undated one. After a second non-answer the line comes back with the news shown. News of any other kind
(a delivered part, a call-off) still ends the wait for its day. Names, ids and numbers come from the fixtures and the
settings."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from engine import promises
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.news-chase")
PAST = TODAY - timedelta(days=3)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__STEWARD__CHASE_UNDATED_DAYS": "14", "COCKPIT__STEWARD__CHASE_DATED_DAYS": "7"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def other(cfg) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != me(cfg))


def reply(day: date, *, non_answer: bool = True, text: str = "Replied without a date") -> dict:
    return {"on": day.isoformat(), "text": text, "non_answer": non_answer}


def make(store, cfg, *, due: date | None, news: list[dict], made: date | None = None) -> str:
    data = {"text": "Send the floor plan", "owners": [{"person": other(cfg)}], "due": due.isoformat() if due else None}
    store.clock = lambda: f"{made or TODAY - timedelta(days=30)}T09:00:00+00:00"
    with store.transaction() as tx:
        action_id = tx.create("action", data, _TEST).id
    with store.transaction() as tx:
        tx.update("action", action_id, {"news": news}, _TEST, read_version=tx.get("action", action_id).version)
    return action_id


def waiting(env, action_id: str, today: date = TODAY):
    _, cfg, store = env
    return next((x for x in promises.waiting_on(store, cfg, today) if x.action == action_id), None)


# ---- a dated promise ---------------------------------------------------------------------------------------------


def test_an_overdue_waiting_on_with_two_non_answers_gets_its_line_back(env):
    ws, cfg, store = env
    action_id = make(store, cfg, due=PAST, news=[reply(PAST + timedelta(days=1)), reply(TODAY)])
    found = waiting(env, action_id)
    assert found is not None and found.replies == 2
    shown = [x for x in queue(ws, store, cfg, NOW) if x.kind in ("promise", "nudge") and action_id in x.actions]
    assert shown and all(x.replies == 2 for x in shown)


def test_one_non_answer_restarts_the_clock_at_the_dated_window_and_the_line_returns_after_it(env):
    _, cfg, store = env
    window = cfg.ui.followups.action_due_within_days
    action_id = make(store, cfg, due=PAST, news=[reply(TODAY)])
    assert waiting(env, action_id) is None
    assert waiting(env, action_id, TODAY + timedelta(days=window - 1)) is None
    back = waiting(env, action_id, TODAY + timedelta(days=window))
    assert back is not None and back.replies == 1


def test_a_second_non_answer_brings_the_line_back_at_once_even_inside_the_window(env):
    _, cfg, store = env
    action_id = make(store, cfg, due=PAST, news=[reply(TODAY - timedelta(days=2))])
    assert waiting(env, action_id) is None
    update = [reply(TODAY - timedelta(days=2)), reply(TODAY)]
    with store.transaction() as tx:
        tx.update("action", action_id, {"news": update}, _TEST, read_version=tx.get("action", action_id).version)
    assert waiting(env, action_id).replies == 2


def test_a_non_answer_before_the_promises_date_does_not_count_after_it_passes(env):
    _, cfg, store = env
    action_id = make(store, cfg, due=PAST, news=[reply(PAST - timedelta(days=2)), reply(PAST - timedelta(days=1))])
    found = waiting(env, action_id)
    assert found is not None and found.replies == 0


def test_news_of_another_kind_still_ends_the_wait_for_its_day(env):
    _, cfg, store = env
    delivered = make(store, cfg, due=PAST, news=[reply(TODAY, non_answer=False, text="Called off")])
    assert waiting(env, delivered) is None
    twice = make(store, cfg, due=PAST, news=[reply(TODAY - timedelta(days=1), non_answer=False), reply(TODAY)])
    assert waiting(env, twice) is None  # one non-answer, and other news since its day: still quiet


def test_an_old_news_entry_with_no_mark_keeps_the_rule_it_had(env):
    _, cfg, store = env
    action_id = make(store, cfg, due=PAST, news=[{"on": TODAY.isoformat(), "text": "Replied, no date"}])
    assert waiting(env, action_id) is None


# ---- an undated promise ------------------------------------------------------------------------------------------


def test_an_undated_promise_restarts_its_wait_at_one_non_answer_and_returns_at_a_second(env):
    _, cfg, store = env
    wait = cfg.ui.followups.undated_after_days
    once = make(store, cfg, due=None, news=[reply(TODAY - timedelta(days=wait - 1))])
    assert waiting(env, once) is None
    assert waiting(env, once, TODAY + timedelta(days=1)).replies == 1
    twice = make(store, cfg, due=None, news=[reply(TODAY - timedelta(days=2)), reply(TODAY - timedelta(days=1))])
    found = waiting(env, twice)
    assert found is not None and found.replies == 2


# ---- the news op carries it --------------------------------------------------------------------------------------


def test_the_news_op_records_a_non_answer_and_a_part_delivered_does_not(env):
    import json

    from engine.ai.adapters.stub import set_responder
    from engine.ai.router import Router
    from engine.dispatcher import process
    from engine.intake import hand_in

    ws, cfg, store = env
    action_id = make(store, cfg, due=PAST, news=[])
    said = "Thanks for the reminder about the floor plan, I will look into it."
    body = json.dumps(
        {
            "summary": "News.",
            "ops": [{"op": "action.news", "id": action_id, "text": "Replied", "evidence": {"quote": said}}],
        }
    )
    set_responder(lambda task: body)
    try:
        handed = hand_in(ws, store, pasted=said, now=NOW)
        process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    finally:
        set_responder(None)
    (entry,) = store.read().get("action", action_id).data["news"]
    assert entry["non_answer"] is True
    from engine.records import ActionNews

    assert ActionNews(on=TODAY, text="x", delivered=True).non_answer is False
