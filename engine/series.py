"""Series of calendar entries (design 6.7, follow-on changes): an entry can be one instance of a series, and an item
(an action or a question) on a series sits on its next instance. When an instance has passed with the item still open,
the item moves to the next instance, and the move is a ledger entry like any other change. Nothing here calls AI."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from engine.records import entry_time
from engine.storage.store import WriteContext

#: Who writes the move of an item from a passed instance to the next one.
ROLL = WriteContext(actor="engine", trust="trusted", op="series.roll")

#: The kinds an item on a series can be, with the statuses that settle them: a settled item never moves.
SETTLED: dict[str, tuple[str, ...]] = {"action": ("done", "dropped"), "question": ("answered", "dropped")}


def _local_day(value: date | datetime, here: ZoneInfo) -> date:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=here)).astimezone(here).date()
    return value


def span(entry: dict[str, Any], here: ZoneInfo) -> tuple[date, date] | None:
    """The first and last day an entry covers, in the person's days; None when its times can't be read."""
    try:
        start = entry_time(entry["start"])
        end = entry_time(entry["end"]) if entry.get("end") else start
    except (KeyError, TypeError, ValueError):
        return None
    return _local_day(start, here), _local_day(end, here)


def instances(view: Any, series: str, here: ZoneInfo) -> list[Any]:
    """The entries that are instances of the series, earliest first."""
    found = []
    for entry in view.list("event"):
        days = span(entry.data, here) if entry.data.get("series") == series else None
        if days is not None:
            found.append((days, entry))
    found.sort(key=lambda pair: (pair[0], pair[1].id))
    return [entry for _, entry in found]


def next_instance(view: Any, series: str, today: date, here: ZoneInfo) -> Any | None:
    """The first instance of the series that hasn't ended before `today` (one on `today` counts); None when there is
    none."""
    for entry in instances(view, series, here):
        days = span(entry.data, here)
        if days is not None and days[1] >= today:
            return entry
    return None


def placement(view: Any, event: str | None, series: str | None, today: date, here: ZoneInfo) -> str | None:
    """The entry an item sits on when it is made: the one it names, else the series' next instance, else none."""
    if event is not None or series is None:
        return event
    found = next_instance(view, series, today, here)
    return found.id if found is not None else None


def item_problem(view: Any, event: str | None, series: str | None) -> str | None:
    """Why an item can't name this entry and series, in plain words; None when it can. Each must exist, and an entry
    that belongs to a series must be named with that series, not another."""
    entry = None
    if event is not None:
        entry = view.get("event", event)
        if entry is None:
            return f"there is no calendar entry {event}"
    if series is not None and view.get("series", series) is None:
        return f"there is no series {series}"
    if entry is not None and series is not None and entry.data.get("series") != series:
        return f"calendar entry {event} isn't an instance of series {series}"
    return None


def link_problem(view: Any, event: str, series: str | None) -> str | None:
    """Why an entry can't join this series (or leave its own), or None. An entry is in one series at most."""
    entry = view.get("event", event)
    if entry is None:
        return f"there is no calendar entry {event}"
    if series is None:
        return None if entry.data.get("series") else f"calendar entry {event} isn't part of a series"
    if view.get("series", series) is None:
        return f"there is no series {series}"
    held = entry.data.get("series")
    if held and held != series:
        return f"calendar entry {event} is already part of series {held}; take it out of that one first"
    return None


def roll_items(store: Any, today: date, here: ZoneInfo, changed: Callable[[], None] | None = None) -> list[str]:
    """Move every open item on a series that sits on no entry, or on one that has passed, to the series' next
    instance. An item whose series has no later instance stays where it is: it never rolls to nowhere. Running it
    again changes nothing. Returns the ids moved."""
    view = store.read()
    moves: list[tuple[str, str, str]] = []
    for kind, settled in SETTLED.items():
        for item in view.list(kind):
            series = item.data.get("series")
            if not series or item.data.get("status") in settled:
                continue
            current = view.get("event", item.data["event"]) if item.data.get("event") else None
            days = span(current.data, here) if current is not None else None
            if days is not None and days[1] >= today:
                continue
            target = next_instance(view, series, today, here)
            if target is not None and target.id != item.data.get("event"):
                moves.append((kind, item.id, target.id))
    if not moves:
        return []
    with store.transaction() as tx:
        for kind, item_id, target in moves:
            cur = tx.get(kind, item_id)
            if cur is not None:
                tx.update(kind, item_id, {"event": target}, ROLL, read_version=cur.version)
    if changed is not None:
        changed()
    return [item_id for _, item_id, _ in moves]
