"""Expand one parsed iCalendar event without changing its source records.

Inputs are date objects for all-day events or datetime objects for timed events.
Floating datetimes are interpreted in tz. RRULE is a single value, optionally
prefixed with RRULE:. EXDATE and RDATE contain parsed values, not property text.
Overrides map original RECURRENCE-ID values to Override objects. Only individual
overrides are supported; RANGE=THISANDFUTURE and RDATE periods are not supported.
The window is half-open and includes events that overlap it, not just starts.
All-day DTEND is exclusive. Cancelled overrides are returned as tombstones.
EXDATE takes precedence, including over overrides with the same original ID.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from dateutil.tz import resolve_imaginary

type When = date | datetime


@dataclass(frozen=True)
class Occurrence:
    start: When
    end: When
    all_day: bool
    cancelled: bool = False
    override_id: When | None = None


@dataclass(frozen=True)
class Override:
    start: When | None = None
    end: When | None = None
    cancelled: bool = False


def occurrences(
    start: When,
    end: When | None,
    rrule: str | None,
    exdates: Iterable[When],
    rdates: Iterable[When],
    overrides: Mapping[When, Override],
    window_start: When,
    window_end: When,
    tz: str | tzinfo,
) -> list[Occurrence]:
    """Return overlapping occurrences sorted by actual start, then original ID.

    Timed results retain DTSTART's zone; floating inputs use tz. A supplied
    DTEND defines an exact elapsed duration, including across DST transitions.
    Missing DTEND means one day for DATE and zero duration for DATE-TIME.
    Nonexistent wall times use the offset before the gap and count normally;
    ambiguous times use the first occurrence. DTSTART consumes the first count,
    including when it does not match the rule. UNTIL accepts DATE or DATE-TIME;
    floating limits use the event zone, and all-day limits use the written date.
    Moved overrides are examined independently so moves into the window work.
    Callers must supply valid recurrence IDs belonging to this event.
    """
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    if not isinstance(zone, tzinfo):
        raise TypeError("tz must be a time zone or IANA zone name")
    all_day = not isinstance(start, datetime)
    event_zone = (start.tzinfo or zone) if isinstance(start, datetime) else zone

    def normalized(value: When) -> When:
        if isinstance(value, datetime):
            if all_day:
                raise ValueError("All-day event values must be dates")
            local = value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(event_zone)
            return resolve_imaginary(local)
        if not isinstance(value, date):
            raise TypeError("Event values must be dates or datetimes")
        if not all_day:
            raise ValueError("Timed event values must be datetimes")
        return value

    def instant(value: When) -> datetime:
        if isinstance(value, datetime):
            return (value.replace(tzinfo=zone) if value.tzinfo is None else value).astimezone(UTC)
        return datetime.combine(value, time(), zone).astimezone(UTC)

    def key(value: When) -> date | datetime:
        return instant(value) if isinstance(value, datetime) else value

    def finish(value: When, duration: timedelta) -> When:
        if isinstance(value, datetime):
            return (value.astimezone(UTC) + duration).astimezone(event_zone)
        return value + duration

    begins = normalized(start)
    ends = normalized(end) if end is not None else finish(begins, timedelta(days=int(all_day)))
    duration = ends - begins if all_day else instant(ends) - instant(begins)
    if duration < timedelta():
        raise ValueError("DTEND must not precede DTSTART")
    lower, upper = instant(window_start), instant(window_end)
    if upper <= lower:
        raise ValueError("The window end must be after its start")
    excluded = {key(normalized(value)) for value in exdates}
    replacements = {key(normalized(value)): (normalized(value), change) for value, change in overrides.items()}
    candidates = {key(begins): begins}
    for value in rdates:
        value = normalized(value)
        candidates[key(value)] = value

    if rrule:
        text = rrule.strip().upper().removeprefix("RRULE:")
        if "\n" in text or "\r" in text:
            raise ValueError("Pass one RRULE value, not an iCalendar document")
        parts = {}
        for part in text.split(";"):
            name, separator, value = part.partition("=")
            if not separator or not value or name in parts:
                raise ValueError("Invalid or duplicate RRULE part")
            parts[name] = value
        supported = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "BYSETPOS", "WKST"}
        if parts.keys() - supported or parts.get("FREQ") not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}:
            raise ValueError("Unsupported RRULE part or frequency")
        if "COUNT" in parts and "UNTIL" in parts:
            raise ValueError("COUNT and UNTIL cannot be combined")
        count = int(parts.pop("COUNT")) if "COUNT" in parts else None
        if (count is not None and count < 1) or int(parts.get("INTERVAL", "1")) < 1:
            raise ValueError("COUNT and INTERVAL must be positive")
        numeric_day = re.search(r"[+-]?\d", parts.get("BYDAY", ""))
        if numeric_day and parts["FREQ"] not in {"MONTHLY", "YEARLY"}:
            raise ValueError("Ordinal BYDAY requires MONTHLY or YEARLY")
        if "BYMONTHDAY" in parts and parts["FREQ"] == "WEEKLY":
            raise ValueError("BYMONTHDAY cannot be used with WEEKLY")
        until = None
        if raw_until := parts.pop("UNTIL", None):
            if not re.fullmatch(r"\d{8}(?:T\d{6}Z?)?", raw_until):
                raise ValueError("UNTIL must be a basic DATE or DATE-TIME")
            if "T" in raw_until:
                parsed = datetime.strptime(raw_until.removesuffix("Z"), "%Y%m%dT%H%M%S").replace(
                    tzinfo=UTC if raw_until.endswith("Z") else event_zone
                )
            else:
                parsed = datetime.strptime(raw_until, "%Y%m%d").replace(tzinfo=event_zone)
            until = parsed.date() if all_day else resolve_imaginary(parsed)
        parts.setdefault("WKST", "MO")
        # Preserve the requested wall time even if DTSTART itself is in a gap.
        wall_start = start.replace(tzinfo=None) if isinstance(start, datetime) else datetime.combine(start, time())
        rule = rrulestr(";".join(f"{name}={value}" for name, value in parts.items()), dtstart=wall_start)
        accepted = 1
        stop = upper.astimezone(event_zone).replace(tzinfo=None) + timedelta(days=2)
        for wall in rule:
            if count is not None and accepted >= count:
                break
            if wall > stop:
                break
            if wall == wall_start:
                continue
            value = wall.date() if all_day else resolve_imaginary(wall.replace(tzinfo=event_zone, fold=0))
            if until is not None and key(value) > key(until):
                break
            accepted += 1
            candidates[key(value)] = value

    result = []

    def append(value: When, value_end: When, cancelled: bool = False, original: When | None = None) -> None:
        left, right = instant(value), instant(value_end)
        if right < left:
            raise ValueError("Override end must not precede its start")
        if (left < upper and right > lower) or (left == right and lower <= left < upper):
            result.append(Occurrence(value, value_end, all_day, cancelled, original))

    for identity, value in candidates.items():
        if identity not in excluded and identity not in replacements:
            append(value, finish(value, duration))
    for identity, (original, change) in replacements.items():
        if identity in excluded:
            continue
        value = normalized(change.start) if change.start is not None else original
        value_end = normalized(change.end) if change.end is not None else finish(value, duration)
        append(value, value_end, change.cancelled, original)
    return sorted(result, key=lambda item: (instant(item.start), instant(item.override_id or item.start)))
