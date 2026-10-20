"""The calendar connector: the events of a calendar published as a calendar file (iCalendar), which most calendar
services offer as a private address, or of a calendar file on this computer. A single event in the window is an item
keyed by its UID. A repeating event is one item for its series, with every date in the window listed on it (the
repeat rules are expanded by `engine.recurrence`); a changed or called-off date, or one the series skips, touches only
that date. An event sent as an invitation carries who invited and who is asked. Events that fall out of the window
aren't treated as gone, so the listing is not complete."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar
from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.connectors import (
    ConnectorContext,
    ConnectorError,
    EventDetails,
    EventOccurrence,
    EventPerson,
    Poll,
    SourceItem,
)
from engine.recurrence import Override, occurrences
from engine.secrets import SecretHint
from engine.windows_zones import iana_zone

#: How much of the start of a file is looked at to tell whether it is a calendar.
_HEAD = 2000


class CalendarSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(
        "",
        description=SecretHint(
            "The calendar's link: a secret reference (env:NAME or file:/path) holding its private "
            "address, since anyone with the address can read the calendar. Give this or a file, not both."
        ),
    )
    file: str = Field(
        "",
        description="A calendar file on this computer, read again each time it changes. Only an app on your own "
        "computer can read one. Give this or a link, not both.",
        json_schema_extra={"picker": "file", "file_types": [".ics"]},
    )
    days_ahead: int = Field(30, ge=1, le=366, description="How far ahead single events are read.")
    days_back: int = Field(1, ge=0, le=31, description="How far back events are read.")
    expand_days: int = Field(
        60,
        ge=1,
        le=366,
        description="How far ahead the dates of a repeating event are listed. Each date in that window shows on its "
        "own day.",
    )
    max_kb: int = Field(5120, ge=1, description="A calendar file larger than this is refused.")

    @model_validator(mode="after")
    def _one_place(self) -> CalendarSettings:
        if bool(self.address.strip()) == bool(self.file.strip()):
            raise ValueError("give the calendar's link or a file on this computer, one of the two")
        return self


# ---- reading values -------------------------------------------------------------------------------------------------


def _first(value: Any) -> Any:
    """A property that appears more than once is read from its first line."""
    return value[0] if isinstance(value, list) and value else value


def _all(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [] if value is None else [value]


def _text(event: Any, name: str) -> str:
    value = _first(event.get(name))
    return str(value).strip() if value is not None else ""


def _zone(name: str | None) -> ZoneInfo | None:
    key = iana_zone(name) if name else None
    try:
        return ZoneInfo(key) if key else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


class _Reading:
    """How one event's times are read: the calendar's default zone, for a time with no zone, and the notes about
    what had to be guessed, each once."""

    def __init__(self, default: tzinfo, name: str):
        self.default, self.name = default, name
        self.notes: list[str] = []

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def moment(self, prop: Any) -> date | datetime | None:
        """A date, or a time with its offset: a UTC time as it is, a zoned one in its zone (a Windows zone name through
        the shipped list, or a zone the calendar defines itself), a time with no zone or an unknown one in the default
        zone."""
        prop = _first(prop)
        value = getattr(prop, "dt", prop)
        if isinstance(value, datetime):
            tzid = str(getattr(prop, "params", {}).get("TZID") or "").strip()
            if tzid:
                zone = _zone(tzid)
                if zone is not None:
                    return value.replace(tzinfo=zone)
                if value.tzinfo is not None:
                    return value
                self.note(f"Its time zone ({tzid}) isn't known here, so its times are read in {self.name}.")
                return value.replace(tzinfo=self.default)
            return value.replace(tzinfo=self.default) if value.tzinfo is None else value
        return value if isinstance(value, date) else None

    def moments(self, prop: Any) -> list[date | datetime]:
        """Every date or time an EXDATE or RDATE property lists, on one line or several; periods are left out."""
        found: list[date | datetime] = []
        for line in _all(prop):
            for each in getattr(line, "dts", [line]):
                value = self.moment(each)
                if value is not None:
                    found.append(value)
        return found


def _person(prop: Any) -> EventPerson | None:
    if prop is None:
        return None
    address = re.sub(r"^mailto:", "", str(prop).strip(), flags=re.I).strip() or None
    params = getattr(prop, "params", {})
    name = str(params.get("CN") or "").strip() or None
    response = str(params.get("PARTSTAT") or "").strip().lower() or None
    return EventPerson(address, name, response) if address or name else None


def _label(person: EventPerson) -> str:
    if person.name and person.address:
        return f"{person.name} <{person.address}>"
    return person.name or person.address or ""


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _instant(value: date | datetime, zone: tzinfo) -> datetime:
    """A date or time as a moment; a date is the start of its day in the zone."""
    return value if isinstance(value, datetime) else datetime.combine(value, time(), zone)


def _same(value: date | datetime) -> date | datetime:
    """A date or time in the one form two spellings of the same moment share."""
    return value.astimezone(UTC) if isinstance(value, datetime) else value


def _shown(when: date | datetime | None) -> str:
    if when is None:
        return "unknown"
    if isinstance(when, datetime):
        return when.strftime("%Y-%m-%d %H:%M %Z").strip()
    return when.isoformat() + " (all day)"


# ---- one event ------------------------------------------------------------------------------------------------------


def _ends(event: Any, begins: date | datetime, reading: _Reading) -> date | datetime | None:
    """An event's end, from its end or its duration; None when it has neither, or the end can't follow the start."""
    ends = reading.moment(event.get("DTEND")) if event.get("DTEND") is not None else None
    if ends is None and event.get("DURATION") is not None:
        length = getattr(_first(event.get("DURATION")), "dt", None)
        if isinstance(length, timedelta):
            ends = begins + length
    if ends is None or isinstance(ends, datetime) != isinstance(begins, datetime) or ends < begins:
        return None
    return ends


def _expand(
    master: Any,
    begins: date | datetime,
    ends: date | datetime | None,
    changes: list[Any],
    reading: _Reading,
    window: tuple[datetime, datetime],
    cancelled: bool,
) -> list[EventOccurrence]:
    """The dates of a repeating event inside the window. A rule the engine doesn't support gives the first date with a
    note, never nothing."""
    rule = _first(master.get("RRULE"))
    text = rule.to_ical().decode() if rule is not None else None
    timed = isinstance(begins, datetime)
    overrides: dict[date | datetime, Override] = {}
    changed: dict[date | datetime, Any] = {}
    for change in changes:
        original = reading.moment(change.get("RECURRENCE-ID"))
        if original is None or isinstance(original, datetime) != timed:
            continue
        moved = reading.moment(change.get("DTSTART")) if change.get("DTSTART") is not None else None
        if moved is not None and isinstance(moved, datetime) != timed:
            moved = None
        finish = _ends(change, moved, reading) if moved is not None else None
        overrides[original] = Override(moved, finish, _text(change, "STATUS").upper() == "CANCELLED")
        changed[_same(original)] = change
        if getattr(_first(change.get("RECURRENCE-ID")), "params", {}).get("RANGE"):
            reading.note("A change to this and later dates is shown for that date only.")
    try:
        found = occurrences(
            begins,
            ends,
            text,
            reading.moments(master.get("EXDATE")),
            reading.moments(master.get("RDATE")),
            overrides,
            window[0],
            window[1],
            reading.default,
        )
    except (ValueError, TypeError):
        reading.note(
            "Its repeat rule isn't one this app can follow, so only its first date is shown."
            if text
            else "Its dates couldn't be worked out, so only its first date is shown."
        )
        found = occurrences(begins, ends, None, [], [], {}, window[0], window[1], reading.default)
        changed = {}
    dates = []
    for occurrence in found:
        original = occurrence.override_id
        change = changed.get(_same(original)) if original is not None else None
        title = _text(change, "SUMMARY") if change is not None else ""
        where = _text(change, "LOCATION") if change is not None else ""
        was = original if original is not None and _same(original) != _same(occurrence.start) else None
        dates.append(
            EventOccurrence(
                start=occurrence.start.isoformat(),
                end=_iso(occurrence.end) if occurrence.end != occurrence.start else None,
                was=_iso(was),
                cancelled=occurrence.cancelled or cancelled,
                title=title or None,
                where=where or None,
            )
        )
    dates += _moved_out(overrides, found, begins, reading, window)
    return dates


def _moved_out(
    overrides: dict[date | datetime, Override],
    found: list[Any],
    begins: date | datetime,
    reading: _Reading,
    window: tuple[datetime, datetime],
) -> list[EventOccurrence]:
    """Dates of the window that were moved to a time beyond it: still the same date of the series, listed where they
    now are, so the date they left isn't taken for one that was skipped."""
    listed = {_same(o.override_id) for o in found if o.override_id is not None}
    moved = []
    for original, change in overrides.items():
        if change.start is None or _same(original) in listed:
            continue
        if window[0] <= _instant(original, reading.default) < window[1]:
            moved.append(
                EventOccurrence(
                    start=change.start.isoformat(),
                    end=_iso(change.end),
                    was=original.isoformat(),
                    cancelled=change.cancelled,
                )
            )
    return moved


def _item(
    event: Any,
    key: str,
    changes: list[Any],
    default: tzinfo,
    default_name: str,
    window: tuple[datetime, datetime],
    singles: tuple[datetime, datetime],
    method: str | None,
) -> SourceItem | None:
    reading = _Reading(default, default_name)
    begins = reading.moment(event.get("DTSTART"))
    if begins is None:
        return None
    ends = _ends(event, begins, reading)
    all_day = not isinstance(begins, datetime)
    rule = _first(event.get("RRULE"))
    repeating = rule is not None or event.get("RDATE") is not None
    cancelled = _text(event, "STATUS").upper() == "CANCELLED" or method == "CANCEL"
    dates: list[EventOccurrence] = []
    if repeating:
        dates = _expand(event, begins, ends, changes, reading, window, cancelled)
        if not dates:
            return None  # a series with no date left in the window (one that ended years ago) is not read
    else:
        left = _instant(begins, default)
        right = _instant(ends if ends is not None else begins, default)
        if right < singles[0] or left > singles[1] or (right == left and left < singles[0]):
            return None
    first = dates[0] if dates else None
    start = first.start if first else begins.isoformat()
    end = (first.end if first else _iso(ends)) if first or ends is not None else None
    title = _text(event, "SUMMARY") or "(no title)"
    organizer = _person(_first(event.get("ORGANIZER")))
    people = tuple(p for p in map(_person, _all(event.get("ATTENDEE"))) if p is not None)
    who = (organizer.name or organizer.address) if organizer is not None else None
    where = _text(event, "LOCATION") or None
    lines = [f"Event: {title}", f"Starts: {_shown(begins)}"]
    if ends is not None:
        lines.append(f"Ends: {_shown(ends)}")
    if rule is not None:
        lines.append(f"Repeats: {rule.to_ical().decode()}")
    for name, label in (("LOCATION", "Where"), ("STATUS", "Status")):
        if _text(event, name):
            lines.append(f"{label}: {_text(event, name)}")
    if who:
        lines.append(f"Organizer: {who}")
    if people:
        lines.append("Attendees: " + ", ".join(_label(p) for p in people))
    lines += [f"Note: {n}" for n in reading.notes]
    description = _text(event, "DESCRIPTION")
    if description:
        lines += ["", description]
    stamp = _first(event.get("LAST-MODIFIED") or event.get("DTSTAMP"))
    changed = stamp.to_ical().decode() if hasattr(stamp, "to_ical") else None
    details = EventDetails(
        start=start,
        end=end,
        all_day=all_day,
        where=where,
        cancelled=cancelled,
        repeats=rule.to_ical().decode() if rule is not None else None,
        occurrences=tuple(dates),
        organizer=organizer,
        attendees=people,
        method=method,
        notes=tuple(reading.notes),
        entries=True,
    )
    return SourceItem(key, title[:200], "\n".join(lines), who, changed, None, event=details)


def _calendar(text: str) -> Any:
    try:
        return Calendar.from_ical(text)
    except Exception:
        raise ConnectorError("outage", "that calendar can't be read") from None


def items(
    text: str, now: datetime, days_back: int, days_ahead: int, expand_days: int = 60, zone: str | None = None
) -> list[SourceItem]:
    """The items of a calendar file: single events within `days_back` before and `days_ahead` after `now`, and each
    repeating event once, with its dates within `days_back` and `expand_days`. `zone`: the person's time zone, for
    times the calendar gives no zone."""
    calendar = _calendar(text)
    named = _zone(str(calendar.get("X-WR-TIMEZONE") or "").strip())
    person = _zone(zone) if zone else None
    chosen = named or person or ZoneInfo("UTC")
    name = (str(calendar.get("X-WR-TIMEZONE")).strip() if named else zone if person else "UTC") or "UTC"
    method = str(calendar.get("METHOD") or "").strip().upper() or None
    back = now - timedelta(days=days_back)
    window = (back, now + timedelta(days=expand_days))
    singles = (back, now + timedelta(days=days_ahead))
    masters: dict[str, Any] = {}
    changes: dict[str, list[Any]] = {}
    order: list[tuple[str, Any]] = []
    for event in calendar.walk("VEVENT"):
        uid = _text(event, "UID")
        if not uid:
            continue
        if event.get("RECURRENCE-ID") is not None:
            changes.setdefault(uid, []).append(event)
        elif uid not in masters:
            masters[uid] = event
            order.append((uid, event))
    reading = _Reading(chosen, name)
    for uid, group in changes.items():
        if uid in masters:
            continue
        for event in group:  # a change to one date of a series the calendar doesn't hold: an event of its own
            original = reading.moment(event.get("RECURRENCE-ID"))
            order.append((f"{uid}#{_iso(original)}", event))
    found = []
    for key, event in order:
        uid = key.split("#", 1)[0]
        own = changes.get(uid, []) if key == uid else []
        item = _item(event, key, own, chosen, name, window, singles, method)
        if item is not None:
            found.append(item)
    return found


# ---- reading the calendar ---------------------------------------------------------------------------------------


def _read_file(settings: CalendarSettings, state: dict[str, Any], context: ConnectorContext) -> tuple[str, dict]:
    if context.hosted:
        raise ConnectorError(
            "no_access", "A hosted app can't read a file on a computer. Use the calendar's link instead."
        )
    path = Path(settings.file.strip()).expanduser()
    if not path.is_absolute():
        path = context.workspace_root / path
    try:
        stat = path.stat()
        if stat.st_size > settings.max_kb * 1024:
            raise ConnectorError("no_access", f"the calendar file is larger than {settings.max_kb} KB")
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise ConnectorError("not_found", f"the calendar file {path} isn't there") from None
    except OSError as err:
        raise ConnectorError("no_access", f"the calendar file can't be opened: {err.strerror or err}") from None
    modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
    return text, {**state, "modified": modified}


def _read_link(settings: CalendarSettings, context: ConnectorContext) -> str:
    from engine.net import WebClient
    from engine.secrets import SecretError, resolve_secret

    try:
        address = resolve_secret(settings.address)
    except SecretError as err:
        raise ConnectorError("auth", f"the calendar's address isn't set: {err}") from None
    if not address:
        raise ConnectorError("auth", "the calendar's address is empty")
    address = re.sub(r"^webcal://", "https://", address.strip(), flags=re.I)
    host = urlsplit(address).hostname or ""
    client = context.web or WebClient([host])
    try:
        response = client.get(address, headers={"Accept": "text/calendar, */*"})
    finally:
        if context.web is None:
            client.close()
    return response.text


def read_calendar(settings: CalendarSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    if settings.file.strip():
        text, state = _read_file(settings, state, context)
        problem = ("no_access", "that file doesn't hold a calendar")
    else:
        text = _read_link(settings, context)
        problem = ("outage", "that address doesn't hold a calendar file")
    if "BEGIN:VCALENDAR" not in text[:_HEAD].upper():
        raise ConnectorError(*problem)
    found = items(
        text,
        context.now or datetime.now(UTC),
        settings.days_back,
        settings.days_ahead,
        settings.expand_days,
        context.timezone,
    )
    return Poll(found, state, complete=False)
