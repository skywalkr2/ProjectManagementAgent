"""A date marked "check this" is never a deadline (design 6.32, "Dependability"): until the person confirms it, the
action is not overdue, not at risk, not due this week, not chased by it and not said overdue in a message to someone
else. Confirming it (setting the date, as the person's own edit) makes it a deadline again. Names, ids and dates come
from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from engine import promises
from engine.firm_due import firm_due
from engine.followups import compose_nudge, sections
from engine.names import People
from engine.open_items import open_actions
from engine.storage import Store, WriteContext
from engine.this_week import this_week
from engine.today import todo
from engine.today_queue import queue
from engine.top_priorities import top_priorities
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.due-check")
PAST = TODAY - timedelta(days=3)
SOON = TODAY + timedelta(days=2)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC", "COCKPIT__UI__TODAY__TOP_PRIORITIES_LINES": "50"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def other(cfg) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != me(cfg))


def make(store, owner: str, text: str, due: date, *, check: bool, **more) -> str:
    data = {
        "text": text,
        "owners": [{"person": owner}],
        "due": due.isoformat(),
        "due_words": "the 3rd",
        "due_check": check,
        **more,
    }
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def confirm(store, action_id: str) -> None:
    """The person confirms the date: the same edit as setting a date, which clears the doubt (`promises.correction`)."""
    with store.transaction() as tx:
        record = tx.get("action", action_id)
        fields = promises.correction({**record.data}, due=date.fromisoformat(str(record.data["due"])))
        assert fields == {"due_words": None, "due_check": False}
        tx.update("action", action_id, fields, _TEST, read_version=record.version)


def test_a_date_to_check_has_no_deadline_and_a_confirmed_one_does():
    assert firm_due({"due": PAST.isoformat(), "due_check": True}) is None
    assert firm_due({"due": PAST.isoformat(), "due_check": False}) == PAST
    assert firm_due({"due": PAST.isoformat()}) == PAST
    assert firm_due({"due": None, "due_check": False}) is None


def test_an_action_with_a_date_to_check_is_never_overdue_at_risk_or_due_this_week_until_confirmed(env):
    ws, cfg, store = env
    late = make(store, me(cfg), "Send the proofs", PAST, check=True)
    soon = make(store, me(cfg), "Book the room", SOON, check=True)

    rows = {r.id: r for r in open_actions(store, cfg, TODAY, now=NOW)}
    assert (rows[late].state, rows[late].due, rows[late].due_check) == ("open", PAST.isoformat(), True)
    items = {t.action: t for t in todo(store, cfg, NOW)}
    assert (items[late].overdue, items[late].due_check, items[late].due) == (False, True, PAST)
    assert items[soon].overdue is False
    assert not [line for line in queue(ws, store, cfg, NOW) if line.kind == "overdue" and late in line.actions]
    assert not [line for line in top_priorities(store, cfg, NOW).lines if line.action in (late, soon)]
    assert not [c for c in top_priorities(store, cfg, NOW).coming if c.action == soon]
    assert not [d for d in this_week(store, cfg, NOW).due if d.action == soon]

    confirm(store, late)
    confirm(store, soon)

    rows = {r.id: r for r in open_actions(store, cfg, TODAY, now=NOW)}
    assert (rows[late].state, rows[late].due_check) == ("overdue", False)
    assert {t.action: t.overdue for t in todo(store, cfg, NOW)}[late] is True
    (overdue,) = [line for line in queue(ws, store, cfg, NOW) if line.kind == "overdue" and late in line.actions]
    assert overdue.actions.count(late) == 1
    assert [line.rank for line in top_priorities(store, cfg, NOW).lines if line.action == late] == ["overdue"]
    assert [line.rank for line in top_priorities(store, cfg, NOW).lines if line.action == soon] == ["due_soon"]
    assert [d.action for d in this_week(store, cfg, NOW).due if d.action == soon] == [soon]


def test_a_date_to_check_on_someone_elses_action_is_chased_as_undated_and_never_said_overdue_in_the_message(env):
    _, cfg, store = env
    them = other(cfg)
    asked = (TODAY - timedelta(days=cfg.ui.followups.undated_after_days + 2)).isoformat()
    checked = make(store, them, "Send the floor plan", PAST, check=True, told={them: asked})
    sure = make(store, them, "Send the quote", PAST, check=False, told={them: asked})

    section = next(s for s in sections(store, cfg, TODAY) if s.person == them)
    rows = {a["id"]: a for a in section.actions}
    assert (rows[checked]["due"], rows[checked]["due_check"], rows[checked]["chase_due"]) == (
        PAST.isoformat(),
        True,
        True,
    )
    assert rows[sure]["chase_due"] is True

    nudge = compose_nudge(section, cfg, People(store, cfg), TODAY)
    assert nudge is not None and {checked, sure} <= set(nudge.action_ids)
    said = [line for line in nudge.text.splitlines() if "was due" in line]
    assert any("Send the quote" in line for line in said)
    assert not any("Send the floor plan" in line for line in said), "a date to check is not said as a fact"

    confirm(store, checked)
    section = next(s for s in sections(store, cfg, TODAY) if s.person == them)
    nudge = compose_nudge(section, cfg, People(store, cfg), TODAY)
    assert any("Send the floor plan" in line and "was due" in line for line in nudge.text.splitlines())


def test_a_date_to_check_is_not_counted_late_on_the_persons_follow_up_line(env):
    ws, cfg, store = env
    them = other(cfg)
    asked = (TODAY - timedelta(days=cfg.ui.followups.undated_after_days + 2)).isoformat()
    checked = make(store, them, "Send the floor plan", PAST, check=True, told={them: asked})

    def late_count() -> int:
        (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "nudge" and x.person == them]
        assert checked in line.actions
        return line.overdue

    before = late_count()
    confirm(store, checked)
    assert late_count() == before + 1
