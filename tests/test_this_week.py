"""This week (design 7.7): what is due by the configured last working day, who is waiting on the person and which
meetings to hold, across projects. Names, ids and days come from the fixtures and the settings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.followups import put_on_hold
from engine.storage import Store, WriteContext
from engine.this_week import this_week, week_end
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

# A Monday afternoon; the working week ends on the configured last day (Friday by default).
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.this-week")


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(
        env={
            "COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC",
            "COCKPIT__STEWARD__REMINDERS__WORKING_LAST_DAY": "friday",
        }
    )
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def make(store, kind, **data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def me(cfg) -> str:
    return cfg.workspace.user.person


def test_the_week_runs_through_the_configured_last_working_day(env):
    _, cfg, _ = env
    assert week_end(cfg, TODAY).isoformat() == day(4)  # Monday to Friday
    assert week_end(cfg, TODAY + timedelta(days=4)).isoformat() == day(4)  # on the last day itself
    assert week_end(cfg, TODAY + timedelta(days=5)).isoformat() == day(11)  # after it, the next week's


def test_the_week_follows_the_setting_for_its_last_day(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__STEWARD__REMINDERS__WORKING_LAST_DAY": "thursday"})
    assert week_end(cfg, TODAY).isoformat() == day(3)


def test_what_is_due_by_the_end_of_the_week_is_listed_soonest_first_and_nothing_else(env):
    _, cfg, store = env
    them = next(p.id for p in store.read().list("person") if p.id != me(cfg))
    late = make(store, "action", text="Send it Friday", owners=[{"person": them}], due=day(4))
    early = make(store, "action", text="Send it today", owners=[{"person": me(cfg)}], due=day(0))
    after = make(store, "action", text="Send it next week", owners=[{"person": me(cfg)}], due=day(5))
    passed = make(store, "action", text="Sent last week", owners=[{"person": me(cfg)}], due=day(-1))
    held = make(store, "action", text="Waiting on a quote", owners=[{"person": me(cfg)}], due=day(2))
    put_on_hold(store, held, "the quote", now=NOW)
    week = this_week(store, cfg, NOW)
    mine = [x for x in week.due if x.action in {late, early, after, passed, held}]
    assert [x.action for x in mine] == [early, late]
    assert [x.mine for x in mine] == [True, False] and week.first == TODAY and week.last.isoformat() == day(4)


def test_who_is_waiting_on_the_person_is_counted_by_what_they_were_promised_or_asked(env):
    _, cfg, store = env
    asker = make(store, "person", full_name="Quinn Fictional")
    make(store, "action", text="Send the draft", owners=[{"person": me(cfg)}], due=day(2), promised_to=[asker])
    make(store, "action", text="Answer the question", owners=[{"person": me(cfg)}], reply_owed=True, asker=asker)
    make(store, "action", text="Send the cover later", owners=[{"person": me(cfg)}], due=day(9), promised_to=[asker])
    found = next(w for w in this_week(store, cfg, NOW).waiting if w.person == asker)
    assert found.count == 2 and found.due.isoformat() == day(2)


def test_the_meetings_of_the_week_include_the_apps_own_entries_through_the_last_day(env):
    _, cfg, store = env
    inside = make(store, "event", trust="trusted", title="Print sync", start=f"{day(3)}T10:00:00+00:00")
    outside = make(store, "event", trust="trusted", title="Next week's sync", start=f"{day(8)}T10:00:00+00:00")
    found = {m.snapshot for m in this_week(store, cfg, NOW).meetings}
    assert inside in found and outside not in found
