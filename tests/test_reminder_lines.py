"""Reminders on Today (design 6.32): a reminder that has reached the person is a line with Done and a snooze menu, one
that came due while the app was not running is marked late and still shown, those that fell in quiet hours arrive
together, and a snooze or a set time is the person's own edit with Undo that records no learning signal. Names, ids and
texts come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.config.schema import RemindersSettings, StewardFile
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

# A Monday afternoon, on the clock the cases below pin to UTC.
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.reminder-lines")
ZONE = {"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}
DEFAULTS = {
    "COCKPIT__STEWARD__REMINDERS__WORKING_START": "09:00",
    "COCKPIT__STEWARD__REMINDERS__WORKING_END": "17:30",
    "COCKPIT__STEWARD__REMINDERS__WORKING_FIRST_DAY": "monday",
    "COCKPIT__STEWARD__REMINDERS__WORKING_LAST_DAY": "friday",
    "COCKPIT__STEWARD__REMINDERS__QUIET_START": "21:00",
    "COCKPIT__STEWARD__REMINDERS__QUIET_END": "07:00",
    "COCKPIT__STEWARD__REMINDERS__MISSED": "each",
    "COCKPIT__STEWARD__REMINDERS__LATER_TODAY_HOURS": "3",
    "COCKPIT__STEWARD__REMINDERS__EVENING": "18:00",
    "COCKPIT__STEWARD__REMINDERS__LATE_AFTER_MINUTES": "5",
}


def build(tmp_path, **env):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={**ZONE, **DEFAULTS, **env})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = build(tmp_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def make(store, cfg, remind_at: datetime | None, text: str = "Send the estimate", **more) -> str:
    owners = [{"person": cfg.workspace.user.person}]
    data = {"text": text, "owners": owners, "remind_at": remind_at.isoformat() if remind_at else None, **more}
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def reminders(env, now=NOW, kind=None):
    ws, cfg, store = env
    return [
        x for x in queue(ws, store, cfg, now) if x.kind in ("reminder", "reminder_digest") and kind in (None, x.kind)
    ]


# ---- a reminder that has reached the person ----------------------------------------------------------


def test_a_reminder_that_just_came_due_is_a_line_with_the_task_and_its_snooze_choices(env):
    _, cfg, store = env
    action = make(store, cfg, NOW - timedelta(minutes=1))
    (line,) = reminders(env)
    assert (line.kind, line.group, line.text, line.actions, line.late) == (
        "reminder",
        "risk",
        "Send the estimate",
        [action],
        False,
    )
    assert datetime.fromisoformat(line.at) == NOW - timedelta(minutes=1)
    assert [s["choice"] for s in line.snoozes] == [
        "in 1 hour",
        "later today",
        "this evening",
        "tomorrow morning",
        "next week",
    ]


def test_a_reminder_not_yet_due_or_for_something_finished_held_or_dropped_is_no_line(env):
    _, cfg, store = env
    make(store, cfg, NOW + timedelta(minutes=30))
    make(store, cfg, NOW - timedelta(minutes=1), status="done")
    make(store, cfg, NOW - timedelta(minutes=1), status="dropped", dropped_reason="No longer needed")
    make(store, cfg, NOW - timedelta(minutes=1), on_hold={"waiting_for": "the proof", "since": "2026-10-18"})
    make(store, cfg, None)
    assert reminders(env) == []


def test_a_reminder_that_came_due_while_the_app_was_not_running_is_a_late_line_shown_at_once(env):
    _, cfg, store = env
    due = NOW - timedelta(hours=3)
    make(store, cfg, due)
    (line,) = reminders(env)
    assert line.kind == "reminder" and line.late is True and datetime.fromisoformat(line.at) == due


def test_a_late_reminder_in_the_evening_is_still_shown_during_quiet_hours(env):
    _, cfg, store = env
    due = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)
    make(store, cfg, due)
    (line,) = reminders(env, now=datetime(2026, 10, 19, 22, 30, tzinfo=UTC))
    assert line.late is True


def test_a_reminder_outside_working_hours_waits_for_the_next_working_start(env):
    _, cfg, store = env
    saturday = datetime(2026, 10, 24, 10, 0, tzinfo=UTC)
    make(store, cfg, saturday)
    assert reminders(env, now=saturday + timedelta(hours=1)) == []
    monday = datetime(2026, 10, 26, 9, 1, tzinfo=UTC)
    (line,) = reminders(env, now=monday)
    assert line.late is False and datetime.fromisoformat(line.at) == saturday


def test_the_reminder_line_follows_the_persons_time_zone(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__WORKSPACE__USER__TIMEZONE="Asia/Tokyo")
    try:
        # Ten in the morning in Tokyo, on a Monday.
        morning = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
        make(store, cfg, morning)
        (line,) = reminders((ws, cfg, store), now=morning + timedelta(minutes=1))
        assert line.at.endswith("+09:00") and all(s["at"].endswith("+09:00") for s in line.snoozes)
    finally:
        store.close()


# ---- quiet hours ----------------------------------------------------------


def test_reminders_that_fell_in_quiet_hours_wait_and_arrive_together_when_they_end(env):
    _, cfg, store = env
    first = make(store, cfg, datetime(2026, 10, 19, 21, 30, tzinfo=UTC), text="Send the estimate")
    second = make(store, cfg, datetime(2026, 10, 20, 5, 0, tzinfo=UTC), text="Call the printer")
    during = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
    assert reminders(env, now=during) == []
    after = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    (digest,) = reminders(env, now=after)
    assert (digest.kind, digest.late, digest.count, digest.actions) == ("reminder_digest", False, 2, [first, second])
    assert [r["text"] for r in digest.reminders] == ["Send the estimate", "Call the printer"]
    assert datetime.fromisoformat(digest.reminders[0]["at"]) == datetime(2026, 10, 19, 21, 30, tzinfo=UTC)


def test_a_quiet_window_across_midnight_and_one_within_a_day_both_hold_reminders(tmp_path):
    ws, cfg, store = build(
        tmp_path, COCKPIT__STEWARD__REMINDERS__QUIET_START="12:00", COCKPIT__STEWARD__REMINDERS__QUIET_END="13:00"
    )
    try:
        make(store, cfg, datetime(2026, 10, 19, 12, 30, tzinfo=UTC))
        env = (ws, cfg, store)
        assert reminders(env, now=datetime(2026, 10, 19, 12, 45, tzinfo=UTC)) == []
        (digest,) = reminders(env, now=datetime(2026, 10, 19, 13, 1, tzinfo=UTC))
        assert digest.kind == "reminder_digest"
    finally:
        store.close()


# ---- missed while asleep: each or one summary ----------------------------------------------------------


def _three_late(store, cfg):
    return [make(store, cfg, NOW - timedelta(hours=h), text=f"Task {h}") for h in (5, 4, 3)]


def test_missed_reminders_are_a_line_each_by_default(env):
    _, cfg, store = env
    ids = _three_late(store, cfg)
    found = reminders(env)
    assert [x.kind for x in found] == ["reminder"] * 3 and all(x.late for x in found)
    assert sorted(a for x in found for a in x.actions) == sorted(ids)


def test_missed_reminders_are_one_summary_line_when_the_person_chose_it(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__REMINDERS__MISSED="summary")
    try:
        ids = _three_late(store, cfg)
        (digest,) = reminders((ws, cfg, store))
        assert (digest.kind, digest.late, digest.count) == ("reminder_digest", True, 3)
        assert sorted(digest.actions) == sorted(ids)
        lone = make(store, cfg, NOW - timedelta(hours=1), text="Only one")
        # One missed reminder is still a line of its own among the others in a summary of the rest.
        assert lone in {a for x in reminders((ws, cfg, store)) for a in x.actions}
    finally:
        store.close()


# ---- snooze choices ----------------------------------------------------------


def choices(env, now):
    from engine import reminder_lines

    return dict(reminder_lines.choices(env[1], now))


def test_each_snooze_choice_resolves_to_a_time_in_the_persons_working_week(env):
    got = choices(env, NOW)
    assert got["in 1 hour"] == NOW + timedelta(hours=1)
    assert got["later today"] == datetime(2026, 10, 19, 17, 0, tzinfo=UTC)
    assert got["this evening"] == datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
    assert got["tomorrow morning"] == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    assert got["next week"] == datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def test_a_choice_with_no_time_today_is_left_out(env):
    late_afternoon = datetime(2026, 10, 19, 16, 0, tzinfo=UTC)
    assert "later today" not in choices(env, late_afternoon)
    night = datetime(2026, 10, 19, 19, 0, tzinfo=UTC)
    assert "this evening" not in choices(env, night) and "tomorrow morning" in choices(env, night)


# ---- settings ----------------------------------------------------------


def test_the_reminder_settings_default_to_a_nine_to_five_thirty_week_and_quiet_nights():
    s = StewardFile().reminders
    assert (s.working_start, s.working_end, s.working_first_day, s.working_last_day) == (
        "09:00",
        "17:30",
        "monday",
        "friday",
    )
    assert (s.quiet_start, s.quiet_end, s.missed) == ("21:00", "07:00", "each")


def test_quiet_hours_may_cross_midnight():
    assert RemindersSettings(quiet_start="22:00", quiet_end="06:30").quiet_start == "22:00"


def test_working_hours_that_end_before_they_start_are_refused_in_plain_words():
    with pytest.raises(ValidationError, match="working hours must end after they start"):
        RemindersSettings(working_start="17:00", working_end="09:00")


def test_quiet_hours_that_start_and_end_together_or_a_time_that_is_not_one_are_refused():
    with pytest.raises(ValidationError, match="can't start and end at the same time"):
        RemindersSettings(quiet_start="21:00", quiet_end="21:00")
    with pytest.raises(ValidationError, match="pick a time of day"):
        RemindersSettings(evening="evening")


def test_the_settings_are_offered_as_lists_and_take_effect_without_a_restart(tmp_path):
    from engine.settings import describe
    from engine.worker import is_live

    ws, cfg, store = build(tmp_path)
    try:
        items = {i.key: i for i in describe(cfg, store.plugins, ws.config_dir)}
        for key in ("working_start", "working_end", "quiet_start", "quiet_end", "evening"):
            item = items[f"steward.reminders.{key}"]
            assert item.type == "choice" and "09:00" in item.options and "21:00" in item.options
        assert items["steward.reminders.missed"].options == ["each", "summary"]
        assert "sunday" in items["steward.reminders.working_first_day"].options
        assert all(is_live(k) for k in items if k.startswith("steward.reminders."))
    finally:
        store.close()


# ---- the persons own edit ----------------------------------------------------------

TOKEN = "reminder-routes-token"


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={**ZONE, **DEFAULTS}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.store = app.state.store
        client.cfg = cfg
        app.state.worker.now = lambda: NOW
        yield client
    set_responder(None)


def remind_at(client, action: str):
    return client.store.read().get("action", action).data.get("remind_at")


def test_snoozing_moves_the_reminder_to_the_choices_time_with_undo_and_records_no_signal(api):
    action = make(api.store, api.cfg, NOW - timedelta(minutes=1))
    (line,) = [x for x in api.get("/api/today/queue").json() if x["kind"] == "reminder"]
    assert line["late"] is False and len(line["snoozes"]) == 5
    done = api.post(f"/api/reminders/{action}", json={"choice": "tomorrow morning"})
    assert done.status_code == 200, done.text
    assert datetime.fromisoformat(remind_at(api, action)) == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    assert [x for x in api.get("/api/today/queue").json() if x["kind"] == "reminder"] == []
    assert [s for s in api.store.read().list("signal")] == []
    assert api.post(f"/api/changesets/{done.json()['changeset']}/undo", json={"ops": None}).status_code == 200
    assert datetime.fromisoformat(remind_at(api, action)) == NOW - timedelta(minutes=1)


def test_a_time_the_person_picks_is_set_and_one_without_a_zone_is_on_their_clock(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(
        env={**ZONE, **DEFAULTS, "COCKPIT__WORKSPACE__USER__TIMEZONE": "Asia/Tokyo"},
        flags={"server.base_path": "/", "storage.backups.automatic": False},
    )
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        app.state.worker.now = lambda: NOW
        action = make(app.state.store, cfg, None)
        got = client.post(f"/api/reminders/{action}", json={"at": "2026-10-21T10:30:00"})
        assert got.status_code == 200, got.text
        stored = app.state.store.read().get("action", action).data["remind_at"]
        assert datetime.fromisoformat(stored) == datetime(2026, 10, 21, 1, 30, tzinfo=UTC)
        [item] = [t for t in client.get("/api/today/todo").json() if t["action"] == action]
        assert item["remind_at"].endswith("+09:00")
    set_responder(None)


def test_picking_a_time_that_has_passed_is_refused_and_a_pick_of_nothing_clears_the_reminder(api):
    action = make(api.store, api.cfg, NOW + timedelta(hours=2))
    past = api.post(f"/api/reminders/{action}", json={"at": (NOW - timedelta(hours=1)).isoformat()})
    assert past.status_code == 409 and past.json()["detail"] == "That time has passed. Pick a time that is still ahead."
    assert (
        api.post(f"/api/reminders/{action}", json={"choice": "later today", "at": NOW.isoformat()}).status_code == 409
    )
    cleared = api.post(f"/api/reminders/{action}", json={})
    assert cleared.status_code == 200 and remind_at(api, action) is None
    assert api.post(f"/api/reminders/{action}", json={}).status_code == 409
    assert api.post("/api/reminders/ACT-NOPE", json={}).status_code == 404


def test_a_choice_with_no_time_left_today_is_refused_in_plain_words(api):
    api.app.state.worker.now = lambda: datetime(2026, 10, 19, 19, 0, tzinfo=UTC)
    action = make(api.store, api.cfg, None)
    got = api.post(f"/api/reminders/{action}", json={"choice": "this evening"})
    assert got.status_code == 409 and got.json()["detail"] == "That choice has no time left. Pick another."


def test_setting_a_reminder_is_not_a_correction_of_the_assistants_work():
    from engine.learn import EDITED_FIELDS

    assert "remind_at" not in EDITED_FIELDS["action"]


def test_a_time_written_without_quotes_in_a_settings_file_is_still_a_time():
    import yaml

    loaded = yaml.safe_load("working_end: 17:30\nevening: 18:00\n")
    assert isinstance(loaded["working_end"], int)  # a settings file reads it as minutes
    s = RemindersSettings.model_validate(loaded)
    assert (s.working_end, s.evening) == ("17:30", "18:00")
