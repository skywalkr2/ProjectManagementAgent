"""Work the assistant releases on its own keeps the person's hours (design 6.35, S1-3): a line the assistant or a rule
adds to Today whose cause came in outside working hours, or inside quiet hours, waits for the next working-hours
start and then arrives together under one "While you were away" row. A time the person chose, a stop, the person's
own note and their setup in progress are never held. Names, ids and texts come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest

from engine.config.schema import StewardFile
from engine.reminders import QuietHours, WorkingHours, release_at
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

_TEST = WriteContext(actor="pm", trust="trusted", op="test.release-hours")
ZONE = {"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}
HOURS = {
    "COCKPIT__STEWARD__HOLD_OUTSIDE_HOURS": "true",
    "COCKPIT__STEWARD__REMINDERS__WORKING_START": "09:00",
    "COCKPIT__STEWARD__REMINDERS__WORKING_END": "17:30",
    "COCKPIT__STEWARD__REMINDERS__WORKING_FIRST_DAY": "monday",
    "COCKPIT__STEWARD__REMINDERS__WORKING_LAST_DAY": "friday",
    "COCKPIT__STEWARD__REMINDERS__QUIET_START": "21:00",
    "COCKPIT__STEWARD__REMINDERS__QUIET_END": "07:00",
    "COCKPIT__STEWARD__REMINDERS__LATE_AFTER_MINUTES": "5",
}

MONDAY = datetime(2026, 10, 19, tzinfo=UTC)
FRIDAY = MONDAY + timedelta(days=4)


def at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


def build(tmp_path, **env):
    # A workspace of its own with nothing in it, so every line below is one the case made.
    ws = init_workspace(tmp_path / "ws", git=False, you=fixture_records(DEMO_B, "person")[0]["full_name"])
    cfg = ws.config(env={**ZONE, **HOURS, **env})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = build(tmp_path)
    yield ws, cfg, store
    store.close()


def source(store, received: datetime) -> str:
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": received.isoformat(),
                "kind": "watched:mailbox",
                "title": "A message",
                "content_hash": "0" * 64,
                "trust": "untrusted",
            },
            _TEST,
        ).id


def asks_go(store, received: datetime, *, origin: str = "input", created: datetime | None = None) -> str:
    """A run that waits for the person's go, made for an input that came in at `received`."""
    fields = {
        "task": "notes",
        "origin": origin,
        "state": "needs_you",
        "approval": "required",
        "created_at": (created or received).isoformat(),
    }
    if origin == "input":
        fields["source"] = source(store, received)
    with store.transaction() as tx:
        return tx.create("request", fields, _TEST).id


def asks_question(store, cfg, received: datetime, title: str = "Which printer?") -> str:
    """A decision for the person, raised from an input that came in at `received`."""
    origin = source(store, received)
    with store.transaction() as tx:
        return tx.create(
            "question",
            {"to": cfg.workspace.user.person, "title": title, "text": title, "kind": "decision", "source": origin},
            _TEST,
        ).id


def lines(env, now, kinds=None):
    """The queue's lines, leaving out the backup line: whether a backup works is about this computer, not about when
    work is held."""
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, now) if (x.kind in kinds if kinds is not None else x.kind != "backup")]


def keys(env, now, kinds=None):
    return [x.key for x in lines(env, now, kinds)]


# ---- an input that comes in at night waits ----------------------------------------------------------


def test_an_input_at_23_00_adds_no_line_until_09_00_the_next_working_day_then_shows_with_the_away_group(env):
    _, _, store = env
    request = asks_go(store, at(MONDAY, 23))
    for now in (at(MONDAY, 23, 30), at(MONDAY + timedelta(days=1), 3), at(MONDAY + timedelta(days=1), 8, 59)):
        assert keys(env, now) == []
    tuesday = MONDAY + timedelta(days=1)
    found = lines(env, at(tuesday, 9, 1))
    assert [x.key for x in found] == ["away", f"go:{request}"]
    away = found[0]
    assert (away.kind, away.count) == ("away", 1) and datetime.fromisoformat(away.since) == at(tuesday, 9)


def test_an_input_at_10_00_shows_at_once_with_no_away_row(env):
    _, _, store = env
    request = asks_go(store, at(MONDAY, 10))
    assert keys(env, at(MONDAY, 10, 1)) == [f"go:{request}"]
    assert keys(env, at(MONDAY, 14)) == [f"go:{request}"]


def test_what_waited_arrives_together_in_its_order_under_one_row_that_counts_them(env):
    _, cfg, store = env
    first = asks_go(store, at(MONDAY, 22))
    question = asks_question(store, cfg, at(MONDAY, 23, 30))
    second = asks_go(store, at(MONDAY + timedelta(days=1), 5))
    assert keys(env, at(MONDAY + timedelta(days=1), 8)) == []
    found = lines(env, at(MONDAY + timedelta(days=1), 9, 30))
    # The row first, then the lines as Today ranks them (a decision before a run waiting for its go).
    assert [x.key for x in found] == ["away", f"question:{question}", f"go:{first}", f"go:{second}"]
    assert found[0].count == 3
    # One that arrived in hours the same morning joins the lines but is not one of those that waited.
    fresh = asks_go(store, at(MONDAY + timedelta(days=1), 9, 15))
    again = lines(env, at(MONDAY + timedelta(days=1), 9, 30))
    assert again[0].count == 3 and f"go:{fresh}" in [x.key for x in again]


def test_the_away_row_is_for_the_day_the_hours_started(env):
    _, _, store = env
    asks_go(store, at(MONDAY, 23))
    tuesday = MONDAY + timedelta(days=1)
    assert [x.kind for x in lines(env, at(tuesday, 16))] == ["away", "go"]
    assert [x.kind for x in lines(env, at(tuesday + timedelta(days=1), 10))] == ["go"]


def test_friday_nights_line_waits_until_monday(env):
    _, _, store = env
    request = asks_go(store, at(FRIDAY, 18))
    assert keys(env, at(FRIDAY, 19)) == []
    assert keys(env, at(FRIDAY + timedelta(days=1), 11)) == []
    assert keys(env, at(FRIDAY + timedelta(days=2), 11)) == []
    monday = FRIDAY + timedelta(days=3)
    assert keys(env, at(monday, 8, 59)) == []
    assert keys(env, at(monday, 9, 1)) == ["away", f"go:{request}"]


def test_a_decision_raised_from_a_message_that_came_in_at_night_waits_the_same_way(env):
    _, cfg, store = env
    question = asks_question(store, cfg, at(MONDAY, 21, 30))
    assert keys(env, at(MONDAY, 22)) == []
    assert f"question:{question}" in keys(env, at(MONDAY + timedelta(days=1), 9, 5))


def test_the_cause_is_the_inputs_received_time_not_when_it_was_taken_in(env):
    _, _, store = env
    # Received at 10:00, taken in at 22:00: its cause arrived in working hours, so it shows at once.
    request = asks_go(store, at(MONDAY, 10), created=at(MONDAY, 22))
    assert keys(env, at(MONDAY, 22, 5)) == [f"go:{request}"]
    # Received at 23:00 but taken in at 10:00 the next day: it waited, so it shows with the row.
    later = asks_go(store, at(MONDAY, 23), created=at(MONDAY + timedelta(days=1), 10))
    assert f"go:{later}" in keys(env, at(MONDAY + timedelta(days=1), 10, 5))


def test_quiet_hours_inside_the_working_day_hold_a_line_until_they_end(tmp_path):
    ws, cfg, store = build(
        tmp_path, COCKPIT__STEWARD__REMINDERS__QUIET_START="12:00", COCKPIT__STEWARD__REMINDERS__QUIET_END="13:00"
    )
    try:
        request = asks_go(store, at(MONDAY, 12, 30))
        assert keys((ws, cfg, store), at(MONDAY, 12, 45)) == []
        assert keys((ws, cfg, store), at(MONDAY, 13, 1)) == ["away", f"go:{request}"]
    finally:
        store.close()


# ---- what is never held ----------------------------------------------------------


def test_the_persons_own_note_at_night_shows_at_once(env):
    _, _, store = env
    request = asks_go(store, at(MONDAY, 23), origin="pm")
    assert keys(env, at(MONDAY, 23, 1)) == [f"go:{request}"]


def test_a_stop_line_shows_at_once_at_night(env):
    from engine.worker import RESTART_NEEDED

    _, _, store = env
    with store.transaction() as tx:
        tx.create(
            "request",
            {
                "task": "notes",
                "origin": "input",
                "state": "queued",
                "waiting": RESTART_NEEDED,
                "created_at": at(MONDAY, 23).isoformat(),
            },
            _TEST,
        )
    assert keys(env, at(MONDAY, 23, 30)) == ["restart"]


def test_the_persons_own_setup_lines_are_never_held(env):
    from engine.dispatcher import FIRST_GO

    _, _, store = env
    with store.transaction() as tx:
        tx.create(
            "request",
            {
                "task": "notes",
                "origin": "input",
                "state": "needs_you",
                "waiting": FIRST_GO,
                "approval": "required",
                "created_at": at(MONDAY, 23).isoformat(),
            },
            _TEST,
        )
    assert keys(env, at(MONDAY, 23, 30)) == ["first_go"]


# ---- a time the person chose is kept ----------------------------------------------------------


def remind(store, cfg, when: datetime, text: str = "Call the printer") -> str:
    data = {"text": text, "owners": [{"person": cfg.workspace.user.person}], "remind_at": when.isoformat()}
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def test_a_reminder_the_person_set_for_06_30_fires_at_06_30_before_working_hours(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__REMINDERS__QUIET_END="06:00")
    try:
        action = remind(store, cfg, at(MONDAY, 6, 30))
        found = lines((ws, cfg, store), at(MONDAY, 6, 31))
        assert [(x.kind, x.actions) for x in found] == [("reminder", [action])]
    finally:
        store.close()


def test_a_reminder_set_for_a_weekend_day_is_kept_as_chosen(env):
    _, cfg, store = env
    saturday = at(MONDAY + timedelta(days=5), 10)
    action = remind(store, cfg, saturday)
    found = lines(env, saturday + timedelta(minutes=1))
    assert [(x.kind, x.actions) for x in found] == [("reminder", [action])]


def test_only_quiet_hours_hold_a_reminder_the_person_set(env):
    _, cfg, store = env
    remind(store, cfg, at(MONDAY, 21, 30))
    assert keys(env, at(MONDAY, 22)) == []
    (digest,) = lines(env, at(MONDAY + timedelta(days=1), 7, 1))
    assert digest.kind == "reminder_digest"


def test_work_held_until_an_event_that_ends_at_night_waits_for_working_hours():
    working = WorkingHours(time(9), time(17, 30), (0, 1, 2, 3, 4))
    quiet = QuietHours(time(21), time(7))
    meeting_ends = at(MONDAY, 22, 15)
    assert release_at(meeting_ends, UTC, quiet, working) == at(MONDAY + timedelta(days=1), 9)
    assert release_at(at(MONDAY, 11), UTC, quiet, working) == at(MONDAY, 11)
    assert release_at(at(FRIDAY, 18), UTC, quiet, working) == at(FRIDAY + timedelta(days=3), 9)


# ---- the setting ----------------------------------------------------------


def test_the_setting_turns_holding_off(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__HOLD_OUTSIDE_HOURS="false")
    try:
        request = asks_go(store, at(MONDAY, 23))
        assert keys((ws, cfg, store), at(MONDAY, 23, 30)) == [f"go:{request}"]
    finally:
        store.close()


def test_holding_is_on_by_default():
    assert StewardFile().hold_outside_hours is True


def test_a_line_with_a_day_but_no_moment_of_arrival_is_never_held(env):
    from engine import release_hours

    assert release_hours._moment("2026-10-19") is None
    assert release_hours._moment("lena") is None
    assert release_hours._moment(at(MONDAY, 23).isoformat()) == at(MONDAY, 23)
    # A promise, an overdue day or a send line is built from days passing, so it shows whenever the person looks.
    assert not {"promise", "overdue", "send", "nudge", "reminder", "restart", "paused"} & release_hours.HELD_KINDS


def test_work_the_person_gave_their_go_to_shows_when_it_is_done_even_at_night(env):
    _, _, store = env
    request = asks_go(store, at(MONDAY, 23))
    with store.transaction() as tx:
        cur = tx.get("request", request)
        tx.update("request", request, {"approval": "granted"}, _TEST, read_version=cur.version)
    assert [x.request for x in lines(env, at(MONDAY, 23, 30))] == [request]
