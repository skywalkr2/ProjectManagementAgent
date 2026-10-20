"""A meeting added in one line (design 6.7, 7.7): what and when, from the agenda.

It is the person's own calendar entry, made with `event.add` as their own change (with Undo). A meeting that is already
there is merged into, never added twice: one with the same words (alike by `checks.tuning.near_duplicate_meeting`) at
the same time, within the configured minutes, in the person's own entries or in a connected calendar's events. Rules
decide this; no AI run is made. A meeting with no time is an all-day entry, and only another all-day one on the same
day is the same.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from engine.records import entry_time
from engine.storage import StoreError
from engine.today import _dates, zone

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class Added:
    """What adding a meeting did. `merged`: it was already there. `where` says where: `own` (an entry of the person's,
    which is `entry`) or `calendar` (a connected calendar's event, which has no entry here); `merged_with` is its
    title."""

    entry: str | None
    changeset: str | None
    merged: bool
    merged_with: str | None = None
    where: str | None = None


def _words(text: str) -> str:
    from engine.cleaning import normalize

    return " ".join(re.findall(r"\w+", normalize(text)))


def _as_moment(value: str, here: Any) -> date | datetime | None:
    try:
        found = entry_time(value)
    except (TypeError, ValueError):
        return None
    if isinstance(found, datetime) and found.tzinfo is None:
        return found.replace(tzinfo=here)
    return found


def _same_time(a: date | datetime | None, b: date | datetime | None, minutes: int) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, datetime) and isinstance(b, datetime):
        return abs(a - b) <= timedelta(minutes=minutes)
    return not isinstance(a, datetime) and not isinstance(b, datetime) and a == b


def _duplicate(
    store: Any, cfg: Any, what: str, start: date | datetime, here: Any
) -> tuple[str, str, str | None] | None:
    """The meeting already there that this one repeats: where it is (`own` or `calendar`), its title and entry id."""
    from engine.sent_version import alike

    tuning = cfg.checks.tuning.near_duplicate_meeting
    view = store.read()

    def repeats(title: str, begins: str) -> bool:
        return alike(_words(what), _words(title)) >= tuning.similarity and _same_time(
            start, _as_moment(begins, here), tuning.minutes
        )

    for entry in view.list("event"):
        data = entry.data
        if not data.get("key") and not data.get("cancelled") and repeats(data["title"], data["start"]):
            return "own", data["title"], entry.id
    for snap in view.list("snapshot"):
        event = snap.data.get("event")
        if snap.data.get("gone") or not event:
            continue
        for found in _dates(event, snap.data["title"], snap.data["key"]):
            if not found["cancelled"] and repeats(found["title"], found["start"]):
                return "calendar", found["title"], None
    return None


def add_meeting(store: Any, cfg: Any, what: str, day: str, time: str | None = None) -> Added:
    """Add a meeting on a day, at a time of day in the person's time zone or with none (all day), unless it is already
    there. Raises StoreError, in plain words, for what can't be read."""
    from engine.applier import apply_as_person

    title = " ".join((what or "").split())
    if not title:
        raise StoreError("Say what the meeting is.")
    try:
        on = date.fromisoformat((day or "").strip())
    except ValueError:
        raise StoreError("The day isn't one I can read; choose it from the calendar.") from None
    at = (time or "").strip() or None
    if at is not None and not _TIME.match(at):
        raise StoreError("The time isn't one I can read; give it as hours and minutes, such as 15:00.")
    here = zone(cfg)
    start = f"{on.isoformat()}T{at}:00" if at else on.isoformat()
    found = _duplicate(store, cfg, title, _as_moment(start, here) or on, here)
    if found is not None:
        where, was, entry = found
        return Added(entry=entry, changeset=None, merged=True, merged_with=was, where=where)
    line = f"{title}, {on.isoformat()}" + (f" {at}" if at else "")
    op = {"op": "event.add", "title": title, "start": start, "evidence": {"quote": line}}
    changeset = apply_as_person(store, cfg, [op], "Added a meeting", note=line)
    made = next(
        (
            r["id"]
            for o in store.read().get("changeset", changeset).data["ops"]
            for r in o.get("records", [])
            if r["kind"] == "event"
        ),
        None,
    )
    return Added(entry=made, changeset=changeset, merged=False)
