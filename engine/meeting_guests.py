"""Who is on a calendar entry and when it takes place, read by rules for the prep, the capture and the people pages
(design 6.32). A guest the workspace knows is a person id; one it doesn't is kept as written, never guessed at. Reads
only; nothing here calls AI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from engine import entry_rules
from engine.records import entry_time


@dataclass(frozen=True)
class Guest:
    """Someone else on an entry: `person` is their id when the workspace knows them, else none and `name` or `address`
    say who it is as the calendar wrote it. `response` is their answer to the invitation, as the calendar says it."""

    person: str | None
    name: str | None
    address: str | None
    response: str | None


def window(data: dict[str, Any], here: ZoneInfo) -> tuple[datetime, datetime] | None:
    """When an entry starts and ends, as moments: a day is all of that day on the person's own clock, a time with no
    offset is on it too. An entry with no end ends when it starts (an all-day one, when its last day ends). None when
    its times can't be read."""
    try:
        first = entry_time(data["start"])
        last = entry_time(data["end"]) if data.get("end") else first
    except (KeyError, TypeError, ValueError):
        return None

    def at(value: date | datetime, closing: bool) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=here)
        return datetime.combine(value + timedelta(days=1 if closing else 0), time.min, tzinfo=here)

    start = at(first, False)
    end = at(last, isinstance(last, date) and not isinstance(last, datetime))
    return start, max(start, end)


def declined(guest: dict[str, Any] | None) -> bool:
    return str((guest or {}).get("response") or "").strip().casefold() == "declined"


def guests(view: Any, cfg: Any, data: dict[str, Any], *, mine: tuple[set[str], set[str]] | None = None) -> list[Guest]:
    """The others on an entry who haven't declined: its organizer and attendees, without the person themselves, and the
    known people its title names when it is a plain entry. Each person once, the organizer first."""
    me = cfg.workspace.user.person
    addresses, names = mine if mine is not None else entry_rules.identity(view, cfg)
    found: list[Guest] = []
    seen: set[str] = set()
    for given in [data.get("organizer"), *(data.get("attendees") or [])]:
        if not given or declined(given) or entry_rules.is_mine(given, addresses, names):
            continue
        person = given.get("person")
        if person == me:
            continue
        key = person or str(given.get("address") or given.get("name") or "").casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(Guest(person, given.get("name"), given.get("address"), given.get("response")))
    for person in data.get("people") or []:
        if person != me and person not in seen:
            seen.add(person)
            found.append(Guest(person, None, None, None))
    return found


def with_others(view: Any, cfg: Any, entry: Any, *, mine: tuple[set[str], set[str]] | None = None) -> list[Guest]:
    """The guests of an entry that is on with other people: none for a cancelled entry, one the person declined, or one
    nobody else is on."""
    data = entry.data
    if data.get("cancelled") or str(data.get("response") or "").strip().casefold() == "declined":
        return []
    return guests(view, cfg, data, mine=mine)
