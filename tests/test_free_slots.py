"""Fictional calendar intervals checked without clocks, files, or network."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.free_slots import Busy, Interval, free_slots

ZONE = ZoneInfo("America/New_York")


def moment(day=2, hour=9, minute=0, *, month=11, year=2026, fold=0):
    return datetime(year, month, day, hour, minute, tzinfo=ZONE, fold=fold)


def slots(busy=(), **changes):
    options = dict(
        day_start=time(9),
        day_end=time(17),
        workdays=(0, 1, 2, 3, 4),
        tz=ZONE,
        window_start=moment(hour=0),
        window_end=moment(3, 0),
    )
    options.update(changes)
    return free_slots(busy, **options)


def test_empty_calendar():
    result = slots()
    assert result.intervals == (Interval(moment(), moment(hour=17)),)
    assert result.free_minutes == {date(2026, 11, 2): 480}


def test_overlap_nested_duplicate_and_adjacent_calendars():
    busy = [
        Busy(moment(hour=10), moment(hour=12)),
        Busy(moment(hour=11), moment(hour=13)),
        Busy(moment(hour=10), moment(hour=12)),
        Busy(moment(hour=13), moment(hour=14)),
        Busy(moment(hour=11), moment(hour=12)),
    ]
    result = slots(busy)
    assert result.intervals == (
        Interval(moment(), moment(hour=10)),
        Interval(moment(hour=14), moment(hour=17)),
    )
    assert result.free_minutes[date(2026, 11, 2)] == 240
    assert slots(reversed(busy)) == result


@pytest.mark.parametrize(
    "show,expected",
    [
        ("busy", 420),
        ("tentative", 420),
        ("free", 480),
        ("out of office", 420),
        ("OUT_OF_OFFICE", 420),
        ("out-of-office", 420),
    ],
)
def test_timed_show_as(show, expected):
    assert slots([Busy(moment(hour=10), moment(hour=11), show)]).free_minutes[date(2026, 11, 2)] == expected


def test_tentative_as_free():
    result = slots([Busy(moment(hour=10), moment(hour=11), "tentative")], tentative_as_free=True)
    assert result.free_minutes[date(2026, 11, 2)] == 480


@pytest.mark.parametrize(
    "show,tentative_as_free,expected",
    [
        ("busy", False, 0),
        ("out of office", False, 0),
        ("tentative", False, 0),
        ("tentative", True, 480),
        ("free", False, 480),
    ],
)
def test_all_day_follows_show_as_like_timed_entries(show, tentative_as_free, expected):
    result = slots([Busy(date(2026, 11, 2), date(2026, 11, 3), show, True)], tentative_as_free=tentative_as_free)
    assert result.free_minutes[date(2026, 11, 2)] == expected


def test_all_day_exclusive_end_and_multiple_days():
    result = slots(
        [Busy(date(2026, 11, 2), date(2026, 11, 4), all_day=True)],
        window_end=moment(5, 0),
    )
    assert result.free_minutes == {
        date(2026, 11, 2): 0,
        date(2026, 11, 3): 0,
        date(2026, 11, 4): 480,
    }


def test_buffer_merges_meetings():
    result = slots(
        [
            Busy(moment(hour=10), moment(hour=11)),
            Busy(moment(hour=11, minute=20), moment(hour=12)),
        ],
        buffer_minutes=15,
    )
    assert result.intervals == (
        Interval(moment(), moment(hour=9, minute=45)),
        Interval(moment(hour=12, minute=15), moment(hour=17)),
    )
    assert result.free_minutes[date(2026, 11, 2)] == 330


def test_buffer_does_not_apply_to_free_or_all_day_entries():
    result = slots(
        [
            Busy(date(2026, 11, 1), date(2026, 11, 2), all_day=True),
            Busy(moment(hour=10), moment(hour=11), "free"),
        ],
        buffer_minutes=120,
    )
    assert result.free_minutes[date(2026, 11, 2)] == 480


def test_outside_window_meeting_buffer_can_overlap():
    result = slots(
        [Busy(moment(1, 23, 30), moment(2, 0))],
        day_start=time(0),
        day_end=time(2),
        buffer_minutes=45,
    )
    assert result.intervals == (Interval(moment(2, 0, 45), moment(2, 2)),)
    assert result.free_minutes[date(2026, 11, 2)] == 75


def test_short_gaps_are_counted_but_not_returned():
    result = slots([Busy(moment(hour=9, minute=20), moment(hour=16, minute=40))])
    assert not result.intervals
    assert result.free_minutes[date(2026, 11, 2)] == 40


def test_exact_minimum_length_is_included():
    result = slots([Busy(moment(hour=9, minute=30), moment(hour=17))])
    assert result.intervals == (Interval(moment(), moment(hour=9, minute=30)),)


def test_partial_window_and_touching_boundaries():
    result = slots(
        [Busy(moment(hour=9), moment(hour=10)), Busy(moment(hour=12), moment(hour=13))],
        window_start=moment(hour=10),
        window_end=moment(hour=12),
    )
    assert result.intervals == (Interval(moment(hour=10), moment(hour=12)),)


def test_weekends_omitted_and_custom_workdays():
    assert not slots(window_start=moment(7, 0), window_end=moment(9, 0)).free_minutes
    result = slots(workdays=(6,), window_start=moment(7, 0), window_end=moment(9, 0))
    assert result.free_minutes == {date(2026, 11, 8): 480}
    assert not slots(workdays=()).intervals


def test_window_in_utc_uses_local_day():
    result = slots(
        window_start=datetime(2026, 11, 3, 0, tzinfo=UTC),
        window_end=datetime(2026, 11, 3, 1, tzinfo=UTC),
        day_start=time(18),
        day_end=time(22),
    )
    assert result.free_minutes == {date(2026, 11, 2): 60}


@pytest.mark.parametrize(("day", "month", "hours"), [(8, 3, 3), (1, 11, 5)])
def test_dst_working_hours_use_elapsed_minutes(day, month, hours):
    result = slots(
        day_start=time(0),
        day_end=time(4),
        workdays=(6,),
        window_start=moment(day, 0, month=month),
        window_end=moment(day + 1, 0, month=month),
    )
    assert result.free_minutes[date(2026, month, day)] == hours * 60
    assert result.intervals[0].start.hour == 0
    assert result.intervals[0].end.hour == 4


def test_dst_gap_boundary_resolves_forward():
    result = slots(
        day_start=time(2, 30),
        day_end=time(4),
        workdays=(6,),
        window_start=moment(8, 0, month=3),
        window_end=moment(9, 0, month=3),
    )
    assert result.intervals[0].start == moment(8, 3, 30, month=3)
    assert result.free_minutes[date(2026, 3, 8)] == 30


def test_fold_busy_interval_uses_instants():
    busy = [Busy(moment(1, 1, 30, fold=0), moment(1, 1, 30, fold=1))]
    result = slots(
        busy,
        day_start=time(0),
        day_end=time(4),
        workdays=(6,),
        window_start=moment(1, 0),
        window_end=moment(2, 0),
    )
    assert result.free_minutes[date(2026, 11, 1)] == 240
    assert len(result.intervals) == 2


def test_busy_from_different_zone():
    entry = Busy(datetime(2026, 11, 2, 15, tzinfo=UTC), datetime(2026, 11, 2, 16, tzinfo=UTC))
    assert slots([entry]).free_minutes[date(2026, 11, 2)] == 420


def test_year_end_and_midnight_exclusive_window():
    result = slots(
        window_start=moment(31, 0, month=12),
        window_end=moment(2, 0, month=1, year=2027),
    )
    assert result.free_minutes == {date(2026, 12, 31): 480, date(2027, 1, 1): 480}


@pytest.mark.parametrize(
    "changes",
    [
        {"min_minutes": 0},
        {"min_minutes": 1.5},
        {"buffer_minutes": -1},
        {"buffer_minutes": True},
        {"workdays": (7,)},
        {"workdays": (0, 0)},
        {"workdays": (False,)},
        {"day_start": time(18)},
        {"day_end": time(9)},
        {"day_start": time(9, tzinfo=UTC)},
        {"window_start": moment().replace(tzinfo=None)},
        {"window_end": moment(1)},
        {"tz": "America/New_York"},
        {"tentative_as_free": 1},
    ],
)
def test_invalid_configuration(changes):
    with pytest.raises(ValueError):
        slots(**changes)


@pytest.mark.parametrize(
    "entry",
    [
        Busy(moment(), moment(hour=8)),
        Busy(moment(), moment()),
        Busy(moment(), moment(hour=10), "unknown"),
        Busy(moment().replace(tzinfo=None), moment(hour=10)),
        Busy(moment(), moment(3), all_day=True),
        Busy(date(2026, 11, 2), date(2026, 11, 2), all_day=True),
    ],
)
def test_invalid_busy_entries(entry):
    with pytest.raises(ValueError):
        slots([entry])


def test_no_mutation_and_repeatable_results():
    entries = [Busy(moment(hour=10), moment(hour=11))]
    original = entries.copy()
    assert slots(entries) == slots(entries)
    assert entries == original


def test_subminute_gap_totals_preserve_precision():
    result = slots([Busy(moment() + timedelta(seconds=30), moment(hour=17))])
    assert result.free_minutes[date(2026, 11, 2)] == 0.5
    assert not result.intervals
