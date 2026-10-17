"""Fictional date schedules and explicit holiday calendars."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from engine.bill_dates import BillRule, bill_due_dates


def expand(rule, start=date(2026, 1, 1), end=date(2027, 1, 1), holidays=()):
    return bill_due_dates(rule, start, end, holidays)


def test_monthly_day_31_clamps():
    result = expand(BillRule("monthly", day=31, reminder_days=()))
    assert [item.due.day for item in result] == [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    assert all(item.scheduled == item.due for item in result)


def test_last_day_and_leap_february():
    result = expand(BillRule("last_day"), date(2028, 2, 1), date(2028, 3, 1))
    assert result[0].due == date(2028, 2, 29)


@pytest.mark.parametrize("nth,weekday,expected", [(1, 0, 5), (2, 0, 12), (-1, 4, 30), (-2, 4, 23), (5, 3, 29)])
def test_nth_weekday(nth, weekday, expected):
    result = expand(BillRule("nth_weekday", nth=nth, weekday=weekday), end=date(2026, 2, 1))
    assert result[0].due == date(2026, 1, expected)


@pytest.mark.parametrize("nth", [5, -5])
def test_missing_fifth_weekday_is_skipped(nth):
    assert not expand(BillRule("nth_weekday", weekday=0, nth=nth), date(2026, 2, 1), date(2026, 3, 1))


def test_every_two_weeks_anchored_across_year_end():
    result = expand(BillRule("weeks", anchor=date(2025, 12, 26), interval=2), end=date(2026, 2, 1))
    assert [item.due for item in result] == [date(2026, 1, 9), date(2026, 1, 23)]


def test_weekly_never_before_anchor_and_far_window():
    rule = BillRule("weeks", anchor=date(2026, 1, 5), interval=3)
    assert not expand(rule, date(2025, 1, 1), date(2026, 1, 1))
    assert expand(rule, date(2030, 1, 1), date(2030, 2, 1))


def test_yearly_and_leap_day_clamping():
    result = expand(BillRule("yearly", month=2, day=29), date(2026, 1, 1), date(2029, 1, 1))
    assert [item.due for item in result] == [date(2026, 2, 28), date(2027, 2, 28), date(2028, 2, 29)]


@pytest.mark.parametrize(
    "mode,expected", [("none", date(2026, 1, 31)), ("previous", date(2026, 1, 30)), ("next", date(2026, 2, 2))]
)
def test_weekend_adjustment(mode, expected):
    result = expand(BillRule("monthly", day=31, business_day=mode), end=date(2026, 2, 3))
    assert result[0].scheduled == date(2026, 1, 31)
    assert result[0].due == expected


def test_holiday_and_weekend_chain():
    holidays = [date(2026, 2, 2), date(2026, 2, 3)]
    rule = BillRule("last_day", business_day="next")
    result = expand(rule, date(2026, 2, 1), date(2026, 2, 5), holidays)
    assert result[0].scheduled == date(2026, 1, 31)
    assert result[0].due == date(2026, 2, 4)


def test_previous_adjustment_from_after_window():
    result = expand(BillRule("monthly", day=1, business_day="previous"), date(2026, 1, 30), date(2026, 1, 31))
    assert result[0].scheduled == date(2026, 2, 1)
    assert result[0].due == date(2026, 1, 30)


def test_next_adjustment_from_before_window_across_year():
    holidays = [date(2027, 1, 1)]
    result = expand(
        BillRule("yearly", month=12, day=31, business_day="next"),
        date(2027, 1, 1),
        date(2027, 1, 5),
        holidays=[date(2026, 12, 31), *holidays],
    )
    assert result[0].scheduled == date(2026, 12, 31)
    assert result[0].due == date(2027, 1, 4)


def test_long_holiday_run_does_not_use_fixed_padding():
    holidays = [date(2026, 1, day) for day in range(1, 31)]
    result = expand(BillRule("monthly", day=1, business_day="next"), date(2026, 2, 1), date(2026, 2, 3), holidays)
    assert [item.scheduled for item in result] == [date(2026, 1, 1), date(2026, 2, 1)]
    assert all(item.due == date(2026, 2, 2) for item in result)


def test_reminders_use_adjusted_due_and_can_leave_window():
    result = expand(
        BillRule("last_day", business_day="next", reminder_days=(7, 1, 1, 0)), date(2026, 2, 1), date(2026, 2, 3)
    )
    assert result[0].reminders == (date(2026, 1, 26), date(2026, 2, 1), date(2026, 2, 2))


def test_custom_workweek():
    result = expand(
        BillRule("monthly", day=30, business_day="next", workdays=(6, 0, 1, 2, 3)), date(2026, 1, 1), date(2026, 2, 2)
    )
    assert result[0].due == date(2026, 2, 1)


def test_anchor_is_lower_bound_before_adjustment():
    rule = BillRule("monthly", day=1, anchor=date(2026, 2, 2))
    assert [item.due for item in expand(rule, end=date(2026, 4, 1))] == [date(2026, 3, 1)]


def test_half_open_window():
    rule = BillRule("monthly", day=10)
    assert len(expand(rule, date(2026, 1, 10), date(2026, 2, 10))) == 1
    assert not expand(rule, date(2026, 1, 11), date(2026, 2, 10))


def test_no_holiday_inference():
    assert expand(BillRule("yearly", month=1, day=1, business_day="next"))[0].due == date(2026, 1, 1)


@pytest.mark.parametrize(
    "rule",
    [
        BillRule("unknown"),
        BillRule("monthly"),
        BillRule("monthly", day=0),
        BillRule("monthly", day=32),
        BillRule("monthly", day=True),
        BillRule("yearly", month=13, day=1),
        BillRule("yearly", day=1),
        BillRule("weeks"),
        BillRule("weeks", anchor=date(2026, 1, 1), interval=0),
        BillRule("monthly", day=1, interval=2),
        BillRule("nth_weekday", weekday=0, nth=0),
        BillRule("nth_weekday", weekday=7, nth=1),
        BillRule("last_day", day=31),
        BillRule("last_day", workdays=()),
        BillRule("last_day", workdays=(0, 0)),
        BillRule("last_day", reminder_days=(-1,)),
        BillRule("last_day", reminder_days=(True,)),
        BillRule("last_day", business_day="nearest"),
    ],
)
def test_invalid_rules(rule):
    with pytest.raises(ValueError):
        expand(rule)


def test_invalid_date_inputs():
    rule = BillRule("last_day")
    with pytest.raises(ValueError):
        expand(rule, date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        expand(rule, datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        expand(rule, holidays=[datetime(2026, 1, 1, tzinfo=UTC)])


def test_frozen_repeatable_and_inputs_unchanged():
    rule = BillRule("monthly", day=10)
    holidays = [date(2026, 1, 10)]
    result = expand(rule, holidays=holidays)
    assert result == expand(rule, holidays=holidays)
    assert holidays == [date(2026, 1, 10)]
    with pytest.raises(FrozenInstanceError):
        result[0].due = date(2026, 1, 11)


def test_date_boundary_overflow_is_explicit():
    with pytest.raises(ValueError):
        expand(BillRule("monthly", day=1, reminder_days=(7,)), date.min, date(1, 2, 1))


@pytest.mark.parametrize(
    "rule",
    [
        BillRule("monthly", day=31, business_day="next"),
        BillRule("monthly", day=1, business_day="previous"),
        BillRule("last_day", business_day="previous"),
        BillRule("nth_weekday", weekday=5, nth=-1, business_day="next"),
        BillRule("weeks", anchor=date(2026, 1, 3), interval=2, business_day="next"),
        BillRule("yearly", month=12, day=31, business_day="next"),
    ],
)
def test_split_windows_give_the_same_dates_as_one_window(rule):
    holidays = [date(2026, 1, 1), date(2026, 5, 25), date(2026, 12, 25), date(2027, 1, 1)]
    whole = expand(rule, date(2026, 1, 1), date(2027, 3, 1), holidays)
    for split in (date(2026, 2, 1), date(2026, 3, 2), date(2026, 8, 1), date(2027, 1, 1), date(2027, 1, 4)):
        parts = expand(rule, date(2026, 1, 1), split, holidays) + expand(rule, split, date(2027, 3, 1), holidays)
        assert parts == whole
