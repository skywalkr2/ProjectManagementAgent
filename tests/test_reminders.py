from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.reminders import QuietHours, Reminder, WorkingHours, next_fire, snooze


def stamp(day=5, hour=12, minute=0):
    return datetime(2027, 1, day, hour, minute, tzinfo=UTC)


def hours(**kwargs):
    return WorkingHours(time(9), time(17), **kwargs)


def test_future():
    result = next_fire(Reminder((stamp(hour=14),)), stamp(), UTC, None, hours())
    assert result.status == "known"
    assert result.fires[0].at == stamp(hour=14)
    assert not result.fires[0].late


def test_sleep_recovery_overrides_quiet_and_working_hours():
    due = stamp(day=4)
    now = stamp(hour=23)
    result = next_fire(Reminder((due,)), now, UTC, QuietHours(time(22), time(8)), hours())
    assert result.fires[0].at == now
    assert result.fires[0].late
    assert result.fires[0].occurrences == (due,)


@pytest.mark.parametrize("mode,count", [("each", 3), ("summary", 1)])
def test_missed_repeats(mode, count):
    due = (stamp(day=2), stamp(day=3), stamp(day=4))
    result = next_fire(Reminder(due, missed_mode=mode), stamp(), UTC, None, None)
    assert len(result.fires) == count
    assert tuple(value for fire in result.fires for value in fire.occurrences) == due
    assert all(fire.late and fire.at == stamp() for fire in result.fires)


def test_delivered_and_duplicates():
    reminder = Reminder((stamp(day=3), stamp(day=3), stamp(day=4)), delivered=(stamp(day=3),))
    assert next_fire(reminder, stamp(), UTC, None, None).fires[0].occurrences == (stamp(day=4),)


def test_empty():
    assert next_fire(Reminder(()), stamp(), UTC, None, None).status == "empty"


@pytest.mark.parametrize("hour,expected_day,expected_hour", [(22, 6, 8), (23, 6, 8), (6, 5, 8), (8, 5, 8)])
def test_cross_midnight(hour, expected_day, expected_hour):
    now = stamp(hour=hour)
    result = next_fire(Reminder((now,)), now, UTC, QuietHours(time(22), time(8)), None)
    assert result.fires[0].at == stamp(day=expected_day, hour=expected_hour)


def test_same_day_quiet():
    now = stamp()
    result = next_fire(Reminder((now,)), now, UTC, QuietHours(time(12), time(13)), None)
    assert result.fires[0].at == stamp(hour=13)


def test_weekend_and_work_end():
    now = stamp(day=8, hour=17)
    assert next_fire(Reminder((now,)), now, UTC, None, hours()).fires[0].at == stamp(day=11, hour=9)


def test_no_allowed_time():
    now = stamp()
    result = next_fire(Reminder((now,)), now, UTC, QuietHours(time(8), time(18)), hours())
    assert result.status == "unknown"
    assert result.reason


def test_due_now_alongside_missed():
    now = stamp()
    result = next_fire(Reminder((stamp(day=4), now)), now, UTC, None, None)
    assert len(result.fires) == 2
    assert [fire.late for fire in result.fires] == [True, False]


def test_planning_does_not_consume():
    reminder = Reminder((stamp(day=4),))
    first = next_fire(reminder, stamp(), UTC, None, None)
    assert next_fire(reminder, stamp(), UTC, None, None) == first
    assert reminder.delivered == ()


@pytest.mark.parametrize(
    "choice,expected",
    [
        ("in 1 hour", stamp(hour=13)),
        ("later today", stamp(hour=15)),
        ("this evening", stamp(hour=18)),
        ("tomorrow morning", stamp(day=6, hour=9)),
        ("next week", stamp(day=11, hour=9)),
        (stamp(hour=16), stamp(hour=16)),
    ],
)
def test_choices(choice, expected):
    result = snooze(choice, stamp(), UTC, hours(later_today_delay=timedelta(hours=3), evening=time(18)))
    assert result.status == "known"
    assert result.at == expected


@pytest.mark.parametrize("choice", ["later today", "this evening", "tomorrow morning", "next week"])
def test_missing_preferences(choice):
    assert snooze(choice, stamp(), UTC, None).status == "unknown"


@pytest.mark.parametrize("choice", ["later today", "this evening"])
def test_missing_specific_preference(choice):
    assert snooze(choice, stamp(), UTC, hours()).status == "unknown"


def test_later_today_no_time_left():
    assert snooze("later today", stamp(hour=16), UTC, hours(later_today_delay=timedelta(hours=3))).at is None


def test_evening_already_passed():
    assert snooze("this evening", stamp(hour=20), UTC, hours(evening=time(18))).status == "unknown"


def test_tomorrow_morning_on_a_friday_is_saturday_morning():
    assert snooze("tomorrow morning", stamp(day=8), UTC, hours()).at == stamp(day=9, hour=9)


def test_custom_workweek():
    result = snooze("next week", stamp(), UTC, WorkingHours(time(10), time(18), (1, 3)))
    assert result.at == stamp(day=12, hour=10)


@pytest.mark.parametrize("choice", [stamp(hour=11), stamp(), "maybe later", "picked time"])
def test_invalid_choice(choice):
    result = snooze(choice, stamp(), UTC, hours())
    assert result.status == "unknown" and result.reason


def test_naive_picked_time():
    picked = datetime(2027, 1, 5, 16)  # noqa: DTZ001 -- Floating picked times must be rejected.
    assert snooze(picked, stamp(), UTC, hours()).status == "unknown"


def test_hour_is_elapsed_across_spring_change():
    zone = ZoneInfo("America/New_York")
    now = datetime(2027, 3, 14, 1, 30, tzinfo=zone)
    result = snooze("in 1 hour", now, zone, None)
    assert result.at.hour == 3
    assert result.at.minute == 30
    assert result.at.astimezone(UTC) - now.astimezone(UTC) == timedelta(hours=1)


def test_hour_is_elapsed_across_fall_change():
    zone = ZoneInfo("America/New_York")
    now = datetime(2027, 11, 7, 1, 30, tzinfo=zone, fold=0)
    result = snooze("in 1 hour", now, zone, None)
    assert result.at.hour == 1 and result.at.fold == 1


def test_generated_gap_unknown():
    now = datetime(2027, 3, 13, 12, tzinfo=UTC)
    result = snooze("tomorrow morning", now, ZoneInfo("America/New_York"), WorkingHours(time(2, 30), time(17), (6,)))
    assert result.status == "unknown"


def test_generated_fold_unknown():
    now = datetime(2027, 11, 6, 12, tzinfo=UTC)
    result = snooze("tomorrow morning", now, ZoneInfo("America/New_York"), WorkingHours(time(1, 30), time(17), (6,)))
    assert result.status == "unknown"


def test_year_boundary():
    now = datetime(2027, 12, 31, 12, tzinfo=UTC)
    assert snooze("next week", now, UTC, hours()).at == datetime(2028, 1, 3, 9, tzinfo=UTC)


@pytest.mark.parametrize("quiet", [QuietHours(time(8), time(8))])
def test_ambiguous_quiet_configuration(quiet):
    assert next_fire(Reminder((stamp(),)), stamp(), UTC, quiet, None).status == "unknown"


def test_unknown_zone():
    assert snooze("in 1 hour", stamp(), "Unknown/Nowhere", None).status == "unknown"


def test_invalid_repeat_mode():
    assert next_fire(Reminder((stamp(),), missed_mode="skip"), stamp(), UTC, None, None).status == "unknown"


def test_morning_stays_local_across_clock_change():
    zone = ZoneInfo("America/New_York")
    now = datetime(2027, 3, 13, 12, tzinfo=zone)
    result = snooze("tomorrow morning", now, zone, WorkingHours(time(9), time(17), (6,)))
    assert result.at == datetime(2027, 3, 14, 9, tzinfo=zone)
    assert result.at.utcoffset() == timedelta(hours=-4)


def test_picked_fold_is_preserved():
    zone = ZoneInfo("America/New_York")
    now = datetime(2027, 11, 7, 0, tzinfo=zone)
    picked = datetime(2027, 11, 7, 1, 30, tzinfo=zone, fold=1)
    result = snooze(picked, now, zone, None)
    assert result.status == "known"
    assert result.at.fold == 1


def test_gap_reason_is_specific():
    zone = ZoneInfo("America/New_York")
    now = datetime(2027, 3, 13, 12, tzinfo=zone)
    result = snooze("tomorrow morning", now, zone, WorkingHours(time(2, 30), time(17), (6,)))
    assert "gap" in result.reason


@pytest.mark.parametrize("configured", [WorkingHours(time(17), time(9)), WorkingHours(time(9), time(17), ())])
def test_invalid_working_hours(configured):
    result = next_fire(Reminder((stamp(),)), stamp(), UTC, None, configured)
    assert result.status == "unknown" and result.reason


def test_acknowledgment_by_instant_in_another_zone():
    due = stamp()
    delivered = due.astimezone(ZoneInfo("America/New_York"))
    assert next_fire(Reminder((due,), (delivered,)), stamp(), UTC, None, None).status == "empty"


def test_naive_now_rejected():
    now = datetime(2027, 1, 5, 12)  # noqa: DTZ001 -- Verify that a floating now is rejected.
    assert next_fire(Reminder((stamp(),)), now, UTC, None, None).status == "unknown"


def test_a_zone_whose_clocks_skip_midnight_still_plans():
    # In this zone the clocks jump from midnight to one o'clock on the night the reminder is moved across.
    zone = ZoneInfo("America/Santiago")
    due = datetime(2026, 9, 5, 18, tzinfo=zone)
    result = next_fire(
        Reminder((due,)), datetime(2026, 9, 5, 12, tzinfo=zone), zone, None, hours(days=(0, 1, 2, 3, 4, 5, 6))
    )
    assert result.status == "known", result.reason
    assert result.fires[0].at == datetime(2026, 9, 6, 9, tzinfo=zone)
