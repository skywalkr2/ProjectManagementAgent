"""The times to offer when the person proposes another time for an invitation: the free gaps in their working week.

Every calendar entry kept in the workspace blocks its time, except one the person declined or one called off; a
tentative one blocks too. The gaps are found by `engine.free_slots` inside the working hours and days of
`steward.reminders`, in the person's time zone. Each gap offers one slot: its start, as long as the invitation itself.
Nothing here writes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.free_slots import Busy, free_slots
from engine.reminder_lines import rules
from engine.today import zone

#: Length given to a timed entry that names no end, in minutes, when working out what it blocks.
_OPEN_ENDED_MINUTES = 30
_DEFAULT_MINUTES = 30


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


def _moment(text: str, tz: Any) -> datetime | None:
    """A date-time as an aware datetime (no offset means the person's own zone); None for a day or unreadable text."""
    if len(text) <= 10:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=tz)


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def busy_of(entries: list[Any], tz: Any, *, skip: str | None = None) -> list[Busy]:
    """What the calendar entries block: all-day ones (their last day included) and timed ones."""
    found: list[Busy] = []
    for entry in entries:
        data = entry.data
        if entry.id == skip or data.get("cancelled") or data.get("response") == "declined":
            continue
        show_as = "tentative" if data.get("response") == "tentative" else "busy"
        start_text, end_text = str(data["start"]), str(data.get("end") or "")
        if len(start_text) <= 10:
            first = _day(start_text)
            last = _day(end_text) if end_text else first
            if first is not None and last is not None and last >= first:
                found.append(Busy(first, last + timedelta(days=1), show_as, all_day=True))
            continue
        start = _moment(start_text, tz)
        if start is None:
            continue
        end = _moment(end_text, tz) if end_text else None
        if end is None or end <= start:
            end = start + timedelta(minutes=_OPEN_ENDED_MINUTES)
        found.append(Busy(start, end, show_as))
    return found


def length_of(entry: Any, tz: Any) -> timedelta:
    """How long the invitation lasts; half an hour when it names no end or is a day."""
    start = _moment(str(entry.data["start"]), tz)
    end = _moment(str(entry.data.get("end") or ""), tz)
    if start is None or end is None or end <= start:
        return timedelta(minutes=_DEFAULT_MINUTES)
    return end - start


def slots(view: Any, cfg: Any, now: datetime, about: str) -> list[Slot]:
    """Up to `watch.propose_slots` free slots in the next `watch.propose_days` days, earliest first, each as long as the
    entry `about`. Empty when the entry doesn't exist or nothing is free."""
    entry = view.get("event", about)
    if entry is None:
        return []
    tz = zone(cfg)
    working = rules(cfg).working
    length = length_of(entry, tz)
    minutes = max(1, int(length.total_seconds() // 60))
    until = now.astimezone(UTC) + timedelta(days=cfg.watch.propose_days)
    # A slot never starts at an odd moment: the window opens at the next round time after now.
    step = timedelta(minutes=cfg.watch.propose_round_minutes)
    opens = datetime.fromtimestamp(math.ceil(now.timestamp() / step.total_seconds()) * step.total_seconds(), UTC)
    found = free_slots(
        busy_of(view.list("event"), tz, skip=about),
        working.start,
        working.end,
        working.days,
        tz,
        min_minutes=minutes,
        window_start=opens,
        window_end=until,
    )
    return [Slot(gap.start, gap.start + length) for gap in found.intervals[: cfg.watch.propose_slots]]
