"""Calendar entries kept from a calendar source (design 6.2, 6.32).

A calendar connector can ask for each date of its events to be kept as a calendar entry (`EventDetails.entries`): an
entry of its own that names the source and which date of which event it is, so a later read updates that entry and no
other. A repeating event's entries are one series. An entry carries where, who organizes it and who is asked (each
resolved to a person the workspace knows by their address), whether it came as an invitation, and the person's own
answer. A moved date moves its entry, and a promise due at it follows (`follow_event`); a date called off, or skipped
by its series, marks only that entry and tells a promise due at it, once. The rules do all of this; nothing here calls
AI, and nothing reaches the calendar service."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from engine.connectors import EventDetails, SourceItem, moment
from engine.records import canonical_time, entry_problem
from engine.storage import StoreError, WriteContext

log = logging.getLogger(__name__)

_KEEP = WriteContext(actor="engine", trust="untrusted", op="calendar.keep")


def keep(store: Any, cfg: Any, source: Any, items: list[SourceItem], now: datetime) -> list[str]:
    """Bring the entries of one source in line with what it lists now. Returns the ids of the entries made or
    changed. A failure to write leaves the read itself as it was."""
    wanted = [i for i in items if i.event is not None and i.event.entries]
    if not wanted:
        return []
    from engine.names import People
    from engine.reply_lines import my_addresses

    view = store.read()
    people = People(store, cfg)
    mine = {a.email.casefold() for a in my_addresses(view, cfg)}
    me = view.get("person", cfg.workspace.user.person) if cfg.workspace.user.person else None
    names = {n.casefold() for n in [*cfg.workspace.user.accounts, me.data["full_name"] if me else ""] if n}
    made: list[str] = []
    try:
        with store.transaction() as tx:
            have = {e.data["key"]: e for e in tx.find("event", {"source": source.id}) if e.data.get("key")}
            for item in wanted:
                made += _keep_item(tx, source, item, have, people, mine, names, now)
    except StoreError as err:
        log.warning("The calendar entries of %s couldn't be kept: %s", source.id, err)
        return []
    return made


def _known(people: Any, person: dict[str, Any]) -> str | None:
    label = f"{person['name']} <{person['address']}>" if person["name"] and person["address"] else None
    found = people.match_entries([label or person["address"] or person["name"] or ""])
    return next(iter(found)) if len(found) == 1 else None


def _who(people: Any, given: Any) -> dict[str, Any]:
    person = {"address": given.address, "name": given.name, "response": given.response, "person": None}
    person["person"] = _known(people, person)
    return person


def _is_mine(person: dict[str, Any] | None, mine: set[str], names: set[str]) -> bool:
    if person is None:
        return False
    return bool(
        (person["address"] and person["address"].casefold() in mine)
        or (person["name"] and person["name"].casefold() in names)
    )


def _times(details: EventDetails, start: str, end: str | None) -> tuple[str, str | None] | None:
    """An entry's start and end for a date: a day, or a moment; an all-day end is the day after the last, so the entry's
    last day is the day before it. None when the times can't make an entry."""
    try:
        if details.all_day:
            first = moment(start, all_day=True)
            last = moment(end, all_day=True) - timedelta(days=1) if end else None
            last_text = last.isoformat() if isinstance(last, date) and last > first else None
            pair = (first.isoformat(), last_text)
        else:
            pair = (canonical_time(start), canonical_time(end) if end and end != start else None)
        return pair if entry_problem(*pair) is None else None
    except (TypeError, ValueError):
        return None


def _keep_item(
    tx: Any,
    source: Any,
    item: SourceItem,
    have: dict[str, Any],
    people: Any,
    mine: set[str],
    names: set[str],
    now: datetime,
) -> list[str]:
    details = item.event
    series_item = bool(details.repeats and details.occurrences)
    dates = list(details.occurrences) if series_item else [None]
    organizer = _who(people, details.organizer) if details.organizer is not None else None
    attendees = [_who(people, a) for a in details.attendees]
    invited = details.method == "REQUEST" or (
        organizer is not None and not _is_mine(organizer, mine, names) and (organizer["address"] or organizer["name"])
    )
    own = next((a for a in attendees if _is_mine(a, mine, names)), None)
    existing = [e for k, e in have.items() if k.startswith(f"{item.key}#")] if series_item else []
    series = next((e.data["series"] for e in existing if e.data.get("series")), None)
    if series_item and series is None and len(dates) > 1:
        series = tx.create(
            "series", {"title": item.title, "project": source.project, "source": source.id, "trust": "untrusted"}, _KEEP
        ).id
    made: list[str] = []
    seen: set[str] = set()
    for date_ in dates:
        start, end = (date_.start, date_.end) if date_ is not None else (details.start, details.end)
        key = f"{item.key}#{date_.was or date_.start}" if date_ is not None else item.key
        times = _times(details, start, end)
        if times is None:
            continue
        seen.add(key)
        gone = bool(date_.cancelled if date_ is not None else details.cancelled)
        wanted = {
            "title": ((date_.title if date_ is not None else None) or item.title)[:200],
            "start": times[0],
            "end": times[1],
            "series": series,
            "where": (date_.where if date_ is not None else None) or details.where,
            "cancelled": gone,
            "invitation": bool(invited),
            "organizer": organizer,
            "attendees": attendees,
            "response": own["response"] if own is not None else None,
            "notes": list(details.notes),
        }
        current = have.get(key)
        if current is None:
            if gone:
                continue  # called off before it was ever kept: nothing to take back
            made.append(tx.create("event", {**wanted, "source": source.id, "key": key, "trust": "untrusted"}, _KEEP).id)
            continue
        made += _update(tx, current, wanted, source, now)
    if series_item and seen:
        made += _skipped(tx, existing, seen, source, now)
    return made


def _update(tx: Any, current: Any, wanted: dict[str, Any], source: Any, now: datetime) -> list[str]:
    changes = {k: v for k, v in wanted.items() if current.data.get(k) != v}
    if not changes:
        return []
    from engine.applier import follow_event

    tx.update("event", current.id, changes, _KEEP, read_version=current.version)
    if "start" in changes:
        follow_event(tx, current.id, _KEEP)
    if changes.get("cancelled") is True:
        _tell(tx, current.id, {**current.data, **changes}, source, now)
    return [current.id]


def _skipped(tx: Any, existing: list[Any], seen: set[str], source: Any, now: datetime) -> list[str]:
    """The dates the series no longer lists between its first and last date now listed: skipped, so called off."""
    listed = [e for e in existing if e.data["key"] in seen]
    if not listed:
        return []
    low = min(e.data["start"] for e in listed)
    high = max(e.data["start"] for e in listed)
    made = []
    for entry in existing:
        if entry.data["key"] in seen or entry.data.get("cancelled") or not low <= entry.data["start"] <= high:
            continue
        tx.update("event", entry.id, {"cancelled": True}, _KEEP, read_version=entry.version)
        _tell(tx, entry.id, {**entry.data, "cancelled": True}, source, now)
        made.append(entry.id)
    return made


def _tell(tx: Any, entry_id: str, entry: dict[str, Any], source: Any, now: datetime) -> None:
    """Say, once, on each open promise due at an entry that it was called off. Its date stays: the person decides."""
    day = str(entry["start"])[:10]
    text = f"{entry['title']} on {day} was called off"
    for action in tx.find("action", {"due_event": entry_id}):
        if action.data["status"] not in ("open", "held"):
            continue
        heard = {"on": now.date().isoformat(), "text": text, "quote": None, "source": source.id, "delivered": False}
        tx.update(
            "action", action.id, {"news": [*action.data.get("news", []), heard]}, _KEEP, read_version=action.version
        )
