"""The meetings that clash from today onward, for Today's at-risk lines and the brief (design 6.32), by rules.

`engine.clashes` compares the timed entries of every calendar (`engine.day_calendar`) through the configured days ahead
(`steward.clashes.days_ahead`): two that overlap, and two in different places with less than
`steward.clashes.travel_minutes`
between them (an online meeting needs none). A meeting the person hasn't accepted never makes one, and a clash that has
already ended today is left out. Reads only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from engine import clashes as clash_rules
from engine.day_calendar import Timed, timed
from engine.today import zone


@dataclass(frozen=True)
class Found:
    """A clash: the two entries (`first` starts first), `state` (overlap or travel), `minutes` (how long they overlap,
    or how many minutes short the travel time is), and the day and moment the later one starts, on the person's
    clock."""

    first: Timed
    second: Timed
    state: str
    minutes: int
    day: date
    at: datetime

    @property
    def key(self) -> str:
        return f"clash:{self.first.item.snapshot}:{self.second.item.snapshot}:{self.day.isoformat()}"

    @property
    def link(self) -> tuple[str, str] | None:
        item = self.first.item
        found = item.entry or (item.snapshot if item.own else None)
        return ("event", found) if found else None


def upcoming(store: Any, cfg: Any, now: datetime) -> list[Found]:
    """Every clash from today through the configured days ahead whose later entry hasn't ended, earliest first."""
    here = zone(cfg)
    today = now.astimezone(here).date()
    settings = cfg.steward.clashes
    entries = [
        t for t in timed(store, cfg, now, through=today + timedelta(days=settings.days_ahead)) if not t.tentative
    ]
    by_id: dict[str, Timed] = {}
    events = []
    for entry in entries:
        key = f"{entry.item.snapshot}#{entry.item.start}"
        by_id[key] = entry
        events.append(
            clash_rules.Event(key, entry.item.source or "own", entry.start, entry.end, "busy", entry.item.where)
        )
    report = clash_rules.clashes(events, float(settings.travel_minutes))
    found = []
    for clash in report.blocking:
        first, second = by_id[clash.first.id], by_id[clash.second.id]
        if first.start > second.start:
            first, second = second, first
        if max(first.end, second.end) <= now:
            continue
        later = second.start.astimezone(here)
        overlap = clash.overlap_minutes > 0
        minutes = clash.overlap_minutes if overlap else clash.travel_shortfall_minutes or 0
        found.append(Found(first, second, "overlap" if overlap else "travel", round(minutes), later.date(), later))
    return sorted(found, key=lambda f: (f.at, f.key))
