"""The timed calendar entries of the coming days as intervals, for the checks that need to know when the person is busy.

Both the capacity check (`engine/day_capacity.py`) and the clash finder's callers (`engine/day_clashes.py`) read the
person's agenda the same way: every connected calendar's events and the app's own entries, with the entries called off
or declined left out and an entry the person hasn't accepted marked tentative. All-day entries take no time. Reads only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from engine.connectors import moment
from engine.today import AgendaItem, agenda

#: The length given to an entry that names no end, in minutes.
OPEN_ENDED_MINUTES = 30


@dataclass(frozen=True)
class Timed:
    """One timed entry: the agenda item, when it starts and ends, and whether the person is only tentatively going."""

    item: AgendaItem
    start: datetime
    end: datetime
    tentative: bool = False


def _record(view: Any, item: AgendaItem) -> Any | None:
    """The calendar entry record kept for an agenda item: the entry itself for the app's own, the one kept for a date of
    a connected event, or none when nothing was kept."""
    found = item.snapshot if item.own else item.entry
    return view.get("event", found) if found else None


def timed(store: Any, cfg: Any, now: datetime, through: date) -> list[Timed]:
    """The timed entries on today and every day through `through`, earliest first."""
    view = store.read()
    found = []
    for item in agenda(store, cfg, now, through=through):
        if item.cancelled or item.all_day:
            continue
        try:
            start = moment(item.start)
            end = moment(item.end) if item.end else None
        except ValueError:
            continue
        if not isinstance(start, datetime):
            continue
        if not isinstance(end, datetime) or end <= start:
            end = start + timedelta(minutes=OPEN_ENDED_MINUTES)
        kept = _record(view, item)
        response = kept.data.get("response") if kept is not None else None
        if response == "declined":
            continue
        found.append(Timed(item, start, end, response == "tentative"))
    return sorted(found, key=lambda t: (t.start, t.item.title))
