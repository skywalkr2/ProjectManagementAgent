"""Expand date-only payment reminders without financial account information."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal


@dataclass(frozen=True)
class BillRule:
    kind: Literal["monthly", "last_day", "nth_weekday", "weeks", "yearly"]
    day: int | None = None
    weekday: int | None = None
    nth: int | None = None
    anchor: date | None = None
    interval: int = 1
    month: int | None = None
    business_day: Literal["none", "previous", "next"] = "none"
    reminder_days: tuple[int, ...] = (7, 1)
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)


@dataclass(frozen=True)
class BillDue:
    scheduled: date
    due: date
    reminders: tuple[date, ...]


def bill_due_dates(
    rule: BillRule,
    window_start: date,
    window_end: date,
    holidays: Iterable[date],
) -> tuple[BillDue, ...]:
    """Return occurrences whose adjusted due dates lie in [start, end).

    Day 31 and yearly dates such as February 29 clamp to the last valid day.
    An absent fifth weekday is skipped; negative nth values count from month end.
    Every-N-weeks recurrence requires an anchor and never precedes it. An optional
    anchor on other rules is a lower bound on scheduled dates, not a phase shift.
    Reminders are calendar days before the adjusted due date, even outside the
    query window. Distinct scheduled dates that adjust to one due date stay distinct.
    """

    def is_date(value) -> bool:
        return isinstance(value, date) and not isinstance(value, datetime)

    def integer(value, minimum: int, maximum: int | None = None) -> bool:
        return type(value) is int and value >= minimum and (maximum is None or value <= maximum)

    def shifted(value: date, days: int) -> date:
        try:
            return value + timedelta(days=days)
        except OverflowError as error:
            raise ValueError("Calculation extends beyond representable dates") from error

    if not is_date(window_start) or not is_date(window_end) or window_end <= window_start:
        raise ValueError("Use date-only bounds with window_end later than window_start")
    if rule.kind not in {"monthly", "last_day", "nth_weekday", "weeks", "yearly"}:
        raise ValueError("Unsupported recurrence kind")
    if rule.business_day not in {"none", "previous", "next"}:
        raise ValueError("Unsupported business-day adjustment")
    if rule.anchor is not None and not is_date(rule.anchor):
        raise ValueError("anchor must be a date")
    if not integer(rule.interval, 1) or (rule.kind != "weeks" and rule.interval != 1):
        raise ValueError("interval must be positive and is only configurable for weeks")
    if rule.kind in {"monthly", "yearly"} and not integer(rule.day, 1, 31):
        raise ValueError("day must be between 1 and 31")
    if rule.kind == "yearly" and not integer(rule.month, 1, 12):
        raise ValueError("yearly rules require a month between 1 and 12")
    if rule.kind == "nth_weekday" and (
        not integer(rule.weekday, 0, 6) or type(rule.nth) is not int or rule.nth == 0 or not -5 <= rule.nth <= 5
    ):
        raise ValueError("nth_weekday requires weekday 0–6 and nth -5 through -1 or 1 through 5")
    if rule.kind == "weeks" and rule.anchor is None:
        raise ValueError("weeks requires an anchor")
    allowed = {
        "monthly": {"day"},
        "last_day": set(),
        "nth_weekday": {"weekday", "nth"},
        "weeks": set(),
        "yearly": {"day", "month"},
    }[rule.kind]
    if any(getattr(rule, name) is not None for name in {"day", "weekday", "nth", "month"} - allowed):
        raise ValueError("Rule contains fields that do not apply to its kind")
    if not rule.workdays or any(not integer(day, 0, 6) for day in rule.workdays):
        raise ValueError("workdays must contain at least one weekday from 0 through 6")
    if len(set(rule.workdays)) != len(rule.workdays):
        raise ValueError("workdays must not contain duplicates")
    if any(not integer(days, 0) for days in rule.reminder_days):
        raise ValueError("reminder_days must contain nonnegative integers")
    holiday_set = frozenset(holidays)
    if any(not is_date(day) for day in holiday_set):
        raise ValueError("holidays must contain dates only")

    def business(value: date, direction: int) -> date:
        while value.weekday() not in rule.workdays or value in holiday_set:
            value = shifted(value, direction)
        return value

    # Include nominal dates outside the window that can move inside it: for "next", the non-business run just before
    # window_start (the day after the last business day before it); for "previous", the run from window_end on.
    lower = shifted(business(shifted(window_start, -1), -1), 1) if rule.business_day == "next" else window_start
    upper = shifted(business(window_end, 1), 1) if rule.business_day == "previous" else window_end
    if rule.anchor is not None:
        lower = max(lower, rule.anchor)
    scheduled = []
    if rule.kind == "weeks":
        step = rule.interval * 7
        distance = (lower - rule.anchor).days
        count = max(0, (distance + step - 1) // step)
        while True:
            offset = count * step
            if offset > (date.max - rule.anchor).days:
                break
            value = shifted(rule.anchor, offset)
            if value >= upper:
                break
            scheduled.append(value)
            count += 1
    else:
        year, month = lower.year, lower.month
        while (year, month) <= (upper.year, upper.month):
            last = monthrange(year, month)[1]
            value = None
            if rule.kind == "last_day":
                value = date(year, month, last)
            elif rule.kind == "nth_weekday":
                if rule.nth > 0:
                    number = 1 + (rule.weekday - date(year, month, 1).weekday()) % 7 + (rule.nth - 1) * 7
                else:
                    number = last - (date(year, month, last).weekday() - rule.weekday) % 7 + (rule.nth + 1) * 7
                if 1 <= number <= last:
                    value = date(year, month, number)
            elif rule.kind == "monthly" or month == rule.month:
                value = date(year, month, min(rule.day, last))
            if value is not None and lower <= value < upper:
                scheduled.append(value)
            if (year, month) == (upper.year, upper.month):
                break
            year, month = year + int(month == 12), month % 12 + 1
    result = []
    for value in scheduled:
        due = value
        if rule.business_day != "none":
            due = business(value, -1 if rule.business_day == "previous" else 1)
        if window_start <= due < window_end:
            reminders = tuple(sorted({shifted(due, -days) for days in rule.reminder_days}))
            result.append(BillDue(value, due, reminders))
    return tuple(sorted(result, key=lambda item: (item.due, item.scheduled)))
