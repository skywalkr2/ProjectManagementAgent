"""Calculate local working-time availability from explicit calendar intervals."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo


@dataclass(frozen=True)
class Busy:
    start: date | datetime
    end: date | datetime
    show_as: str = "busy"
    all_day: bool = False


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Availability:
    intervals: tuple[Interval, ...]
    free_minutes: dict[date, float]


def free_slots(
    busy: Iterable[Busy],
    day_start: time,
    day_end: time,
    workdays: Iterable[int],
    tz: tzinfo,
    *,
    min_minutes: int = 30,
    buffer_minutes: int = 0,
    window_start: datetime,
    window_end: datetime,
    tentative_as_free: bool = False,
) -> Availability:
    """Return minimum-length gaps and total unfiltered free minutes per workday.

    All intervals and the window are half-open. All-day values must be dates,
    with exclusive ends. Busy, tentative (by default) and out-of-office entries
    block elapsed time, all-day or timed; free entries never block. Buffers
    apply only to blocking timed entries, including outside-window ones.
    Each day's total includes short gaps omitted by min_minutes. Dates with no
    working time inside the window are absent; fully blocked workdays have zero.
    Local boundaries use fold 0 and resolve forward through gaps by UTC round-trip.
    """
    if not isinstance(tz, tzinfo):
        raise ValueError("tz must be an already-created time zone object")
    if any(not isinstance(value, time) or value.tzinfo is not None for value in (day_start, day_end)):
        raise ValueError("Working hours must be local time values without a time zone")
    if day_end <= day_start:
        raise ValueError("Working hours must start and end on the same day with end after start")
    days = tuple(workdays)
    if any(type(day) is not int or not 0 <= day <= 6 for day in days) or len(set(days)) != len(days):
        raise ValueError("workdays must contain unique integers from 0 through 6")
    if type(min_minutes) is not int or min_minutes <= 0:
        raise ValueError("min_minutes must be a positive integer")
    if type(buffer_minutes) is not int or buffer_minutes < 0:
        raise ValueError("buffer_minutes must be a nonnegative integer")
    if type(tentative_as_free) is not bool:
        raise ValueError("tentative_as_free must be boolean")

    def instant(value: datetime) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timed values must be aware datetimes")
        return value.astimezone(UTC)

    def boundary(day: date, wall_time: time) -> datetime:
        local = datetime.combine(day, wall_time.replace(fold=0), tz)
        return local.astimezone(UTC)

    lower, upper = instant(window_start), instant(window_end)
    if upper <= lower:
        raise ValueError("window_end must be later than window_start")
    padding = timedelta(minutes=buffer_minutes)
    blocked = []
    for entry in busy:
        show_as = entry.show_as.strip().lower().replace("_", " ").replace("-", " ")
        if show_as not in {"busy", "tentative", "free", "out of office"}:
            raise ValueError("Unknown show-as value")
        if entry.all_day:
            if not all(
                isinstance(value, date) and not isinstance(value, datetime) for value in (entry.start, entry.end)
            ):
                raise ValueError("All-day entries require dates")
            if entry.end <= entry.start:
                raise ValueError("All-day end must follow start")
            left, right = boundary(entry.start, time()), boundary(entry.end, time())
        else:
            left, right = instant(entry.start), instant(entry.end)
            if right <= left:
                raise ValueError("Busy interval end must follow start")
            left, right = left - padding, right + padding
        blocks = show_as in {"busy", "out of office"} or (show_as == "tentative" and not tentative_as_free)
        if blocks and left < upper and right > lower:
            blocked.append((max(left, lower), min(right, upper)))
    blocked.sort()
    merged = []
    for left, right in blocked:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))

    intervals = []
    totals = {}
    day = lower.astimezone(tz).date()
    last = upper.astimezone(tz).date()
    while day <= last:
        if day.weekday() in days:
            left = max(lower, boundary(day, day_start))
            right = min(upper, boundary(day, day_end))
            if left < right:
                cursor = left
                gaps = []
                for block_start, block_end in merged:
                    if block_end <= cursor:
                        continue
                    if block_start >= right:
                        break
                    if block_start > cursor:
                        gaps.append((cursor, min(block_start, right)))
                    cursor = max(cursor, block_end)
                    if cursor >= right:
                        break
                if cursor < right:
                    gaps.append((cursor, right))
                totals[day] = sum((end - start).total_seconds() / 60 for start, end in gaps)
                intervals.extend(
                    Interval(start.astimezone(tz), end.astimezone(tz))
                    for start, end in gaps
                    if (end - start).total_seconds() >= min_minutes * 60
                )
        if day == last:
            break
        day += timedelta(days=1)
    return Availability(tuple(intervals), totals)
