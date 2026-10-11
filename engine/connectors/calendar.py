"""The calendar connector: the events of a calendar published as a calendar file (iCalendar), which most calendar
services offer as a private address. Each event in the configured window is an item keyed by its UID (and the
occurrence it changes), so a moved meeting, a new invitation or a cancellation is handed in. Events that fall out of
the window aren't treated as gone, so the listing is not complete."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from engine.connectors import ConnectorContext, ConnectorError, EventDetails, Poll, SourceItem

_ESCAPES = {"\\n": "\n", "\\N": "\n", "\\,": ",", "\\;": ";", "\\\\": "\\"}


class CalendarSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(
        min_length=1,
        description="Where the calendar file is: a secret reference (env:NAME or file:/path) holding its private "
        "address, since anyone with the address can read the calendar.",
    )
    days_ahead: int = Field(30, ge=1, le=366, description="How far ahead events are read.")
    days_back: int = Field(1, ge=0, le=31, description="How far back events are read.")


def unfold(text: str) -> list[str]:
    """iCalendar lines with folded continuations joined back."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _value(text: str) -> str:
    return re.sub(r"\\[nN,;\\]", lambda m: _ESCAPES[m.group(0)], text)


def parse_when(value: str, params: dict[str, str]) -> datetime | date | None:
    """A DTSTART or DTEND value: a date, a UTC time, or a floating or zoned local time (read as UTC when the zone is
    unknown, which only shifts the window by hours)."""
    value = value.strip()
    try:
        if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
            return datetime.strptime(value, "%Y%m%d").date()
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        moment = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    zone = params.get("TZID")
    if zone:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            return moment.replace(tzinfo=ZoneInfo(zone))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return moment.replace(tzinfo=UTC)


def events(text: str) -> list[dict[str, Any]]:
    """Each VEVENT's properties: name -> (value, params); repeated names keep the first."""
    found: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    depth = 0
    for line in unfold(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            current, depth = {}, 0
            continue
        if current is None:
            continue
        if upper.startswith("BEGIN:"):
            depth += 1  # an alarm inside the event: its properties aren't the event's
            continue
        if upper.startswith("END:"):
            if upper == "END:VEVENT" and depth == 0:
                found.append(current)
                current = None
            else:
                depth -= 1
            continue
        if depth or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *raw_params = head.split(";")
        params = dict(p.split("=", 1) for p in raw_params if "=" in p)
        current.setdefault(name.upper(), (value, {k.upper(): v.strip('"') for k, v in params.items()}))
    return found


def _shown(when: datetime | date | None) -> str:
    if when is None:
        return "unknown"
    if isinstance(when, datetime):
        return when.strftime("%Y-%m-%d %H:%M %Z").strip()
    return when.isoformat() + " (all day)"


def _details(event: dict[str, Any], begins: datetime | date | None) -> EventDetails | None:
    """When and where, for the agenda; None when the start can't be read."""
    if begins is None:
        return None
    all_day = not isinstance(begins, datetime)
    ends = parse_when(*event["DTEND"]) if "DTEND" in event else None
    if ends is not None and isinstance(ends, datetime) == all_day:
        ends = None  # a start and an end of different kinds can't be compared
    if ends is not None and ends < begins:
        ends = None
    where = _value(event.get("LOCATION", ("", {}))[0]).strip() or None
    return EventDetails(
        start=begins.isoformat(),
        end=ends.isoformat() if ends is not None else None,
        all_day=all_day,
        where=where,
        cancelled=event.get("STATUS", ("", {}))[0].strip().upper() == "CANCELLED",
        repeats=event["RRULE"][0] if "RRULE" in event else None,
    )


def items(text: str, now: datetime, days_back: int, days_ahead: int) -> list[SourceItem]:
    start, end = now - timedelta(days=days_back), now + timedelta(days=days_ahead)
    found = []
    for event in events(text):
        uid = _value(event.get("UID", ("", {}))[0]).strip()
        if not uid:
            continue
        begins = parse_when(*event["DTSTART"]) if "DTSTART" in event else None
        repeats = "RRULE" in event
        moment = (
            datetime(begins.year, begins.month, begins.day, tzinfo=UTC)
            if isinstance(begins, date) and not isinstance(begins, datetime)
            else begins
        )
        if not repeats and (moment is None or not start <= moment <= end):
            continue
        occurrence = event.get("RECURRENCE-ID", ("", {}))[0]
        key = f"{uid}#{occurrence}" if occurrence else uid
        title = _value(event.get("SUMMARY", ("(no title)", {}))[0]).strip() or "(no title)"
        organizer = event.get("ORGANIZER", ("", {}))
        who = organizer[1].get("CN") or organizer[0].removeprefix("mailto:").removeprefix("MAILTO:") or None
        lines = [f"Event: {title}", f"Starts: {_shown(begins)}"]
        if "DTEND" in event:
            lines.append(f"Ends: {_shown(parse_when(*event['DTEND']))}")
        if repeats:
            lines.append(f"Repeats: {event['RRULE'][0]}")
        for name, label in (("LOCATION", "Where"), ("STATUS", "Status")):
            if name in event and event[name][0].strip():
                lines.append(f"{label}: {_value(event[name][0]).strip()}")
        if who:
            lines.append(f"Organizer: {who}")
        description = _value(event.get("DESCRIPTION", ("", {}))[0]).strip()
        if description:
            lines += ["", description]
        changed = event.get("LAST-MODIFIED", event.get("DTSTAMP", ("", {})))[0] or None
        found.append(SourceItem(key, title[:200], "\n".join(lines), who, changed, None, event=_details(event, begins)))
    return found


def read_calendar(settings: CalendarSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
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
    text = response.text
    if "BEGIN:VCALENDAR" not in text[:2000].upper():
        raise ConnectorError("outage", "that address doesn't hold a calendar file")
    found = items(text, datetime.now(UTC), settings.days_back, settings.days_ahead)
    return Poll(found, state, complete=False)
