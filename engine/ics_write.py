"""Write a single-event calendar with bounded, explicit time zone transitions."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

#: The calendar product identifier written into every file; the product's name changes here only.
PRODID = "-//PM Cockpit//Calendar Writer//EN"


def event_ics(
    uid: str,
    summary: str,
    start: date | datetime,
    end: date | datetime | None,
    all_day: bool,
    tz: str | ZoneInfo,
    description: str,
    location: str,
    alarms: list[timedelta],
    organizer: str | None = None,
    attendees: Iterable[str] = (),
    method: str | None = None,
    sequence: int = 0,
    *,
    dtstamp: datetime,
) -> str:
    """Return CRLF iCalendar text, folding physical lines at 75 UTF-8 octets.

    dtstamp is a caller-supplied creation/revision instant, keeping the writer
    pure. Organizer and attendees are bare email addresses or mailto URIs.
    Alarms are signed offsets from DTSTART: negative values fire beforehand.
    All-day ends are exclusive. Missing DTEND is omitted, using RFC defaults.
    Timed values are converted to tz; naive values represent local wall times.
    VTIMEZONE covers the event years plus one year on each side. This writer
    does not create recurring events or indefinitely valid time zone definitions.
    """
    if not uid or not uid.strip():
        raise ValueError("uid must not be empty")
    if type(sequence) is not int or sequence < 0:
        raise ValueError("sequence must be a nonnegative integer")
    if dtstamp.tzinfo is None or dtstamp.utcoffset() is None:
        raise ValueError("dtstamp must be an aware datetime")
    if method is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", method):
        raise ValueError("method must be a single calendar method token")
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    if not isinstance(zone, ZoneInfo):
        raise ValueError("tz must be an IANA zone name or ZoneInfo")
    if not re.fullmatch(r"[A-Za-z0-9_+./-]+", zone.key):
        raise ValueError("Unsafe TZID")

    def escaped(value: str) -> str:
        if any(ord(char) < 32 and char not in "\t\r\n" for char in value):
            raise ValueError("Text contains an invalid control character")
        return (
            value.replace("\\", "\\\\")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace(",", "\\,")
        )

    def address(value: str) -> str:
        email = value[7:] if value.lower().startswith("mailto:") else value
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", email):
            raise ValueError("Calendar addresses must be bare email addresses or mailto URIs")
        return "mailto:" + email

    def local(value: date | datetime) -> date | datetime:
        if all_day:
            if not isinstance(value, date) or isinstance(value, datetime):
                raise ValueError("All-day events require date values")
            return value
        if not isinstance(value, datetime):
            raise ValueError("Timed events require datetime values")
        if value.microsecond:
            raise ValueError("iCalendar timestamps require whole seconds")
        result = value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
        restored = result.astimezone(UTC).astimezone(zone)
        if restored.replace(tzinfo=None) != result.replace(tzinfo=None):
            raise ValueError("Nonexistent local time; supply an existing instant")
        # Local DATE-TIME cannot represent the second fold unambiguously.
        if result.fold and result.utcoffset() != result.replace(fold=0).utcoffset():
            raise ValueError("The second occurrence of an ambiguous local time cannot use TZID safely")
        return result

    def stamp(value: datetime) -> str:
        return value.strftime("%Y%m%dT%H%M%S")

    def offset(value: timedelta) -> str:
        seconds = int(value.total_seconds())
        sign = "-" if seconds < 0 else "+"
        hours, seconds = divmod(abs(seconds), 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{sign}{hours:02d}{minutes:02d}" + (f"{seconds:02d}" if seconds else "")

    begins = local(start)
    ends = local(end) if end is not None else None
    if ends is not None:
        valid = ends > begins if all_day else ends.astimezone(UTC) > begins.astimezone(UTC)
        if not valid:
            raise ValueError("DTEND must be later than DTSTART")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:" + PRODID, "CALSCALE:GREGORIAN"]
    if method:
        lines.append("METHOD:" + method.upper())
    if not all_day:
        first_year = begins.year - 1
        last_year = (ends or begins).year + 1
        if first_year < 1 or last_year > 9998:
            raise ValueError("Event years must allow one year of time zone padding")
        lower = datetime(first_year, 1, 1, tzinfo=UTC)
        upper = datetime(last_year + 1, 1, 1, tzinfo=UTC)
        initial = lower.astimezone(zone)
        kind = "DAYLIGHT" if initial.dst() else "STANDARD"
        lines.extend(
            [
                "BEGIN:VTIMEZONE",
                "TZID:" + escaped(zone.key),
                f"BEGIN:{kind}",
                "DTSTART:" + stamp(initial),
                "TZOFFSETFROM:" + offset(initial.utcoffset()),
                "TZOFFSETTO:" + offset(initial.utcoffset()),
                "TZNAME:" + escaped(initial.tzname() or zone.key),
                f"END:{kind}",
            ]
        )
        # Find offset changes in UTC, then locate each change to the second.
        cursor = lower
        previous = initial.utcoffset()
        transitions = {}
        while cursor < upper:
            probe = min(cursor + timedelta(hours=6), upper)
            current = probe.astimezone(zone).utcoffset()
            if current != previous:
                left, right = cursor, probe
                while (right - left).total_seconds() > 1:
                    middle = left + timedelta(seconds=int((right - left).total_seconds()) // 2)
                    if middle.astimezone(zone).utcoffset() == previous:
                        left = middle
                    else:
                        right = middle
                after = right.astimezone(zone)
                # DTSTART is the transition's local wall time before the change.
                before_wall = right + previous
                kind = "DAYLIGHT" if after.dst() else "STANDARD"
                identity = (kind, previous, current, after.tzname() or zone.key)
                transitions.setdefault(identity, []).append(stamp(before_wall))
            cursor, previous = probe, current
        for (kind, before, after, name), dates in transitions.items():
            lines.extend(
                [
                    f"BEGIN:{kind}",
                    "DTSTART:" + dates[0],
                    "TZOFFSETFROM:" + offset(before),
                    "TZOFFSETTO:" + offset(after),
                    "TZNAME:" + escaped(name),
                ]
            )
            if len(dates) > 1:
                lines.append("RDATE:" + ",".join(dates[1:]))
            lines.append(f"END:{kind}")
        lines.append("END:VTIMEZONE")
    lines.extend(
        [
            "BEGIN:VEVENT",
            "UID:" + escaped(uid),
            "DTSTAMP:" + stamp(dtstamp.astimezone(UTC)) + "Z",
            "SEQUENCE:" + str(sequence),
            "SUMMARY:" + escaped(summary),
        ]
    )
    for property_name, value in (("DTSTART", begins), ("DTEND", ends)):
        if value is not None:
            if all_day:
                lines.append(f"{property_name};VALUE=DATE:{value.strftime('%Y%m%d')}")
            else:
                lines.append(f"{property_name};TZID={zone.key}:" + stamp(value))
    lines.extend(["DESCRIPTION:" + escaped(description), "LOCATION:" + escaped(location)])
    if organizer is not None:
        lines.append("ORGANIZER:" + address(organizer))
    for attendee in attendees:
        lines.append("ATTENDEE:" + address(attendee))
    for alarm in alarms:
        if not isinstance(alarm, timedelta) or alarm.microseconds:
            raise ValueError("Alarms must be whole-second timedeltas")
        total = int(alarm.total_seconds())
        days, remaining = divmod(abs(total), 86400)
        hours, remaining = divmod(remaining, 3600)
        minutes, seconds = divmod(remaining, 60)
        duration = ("-" if total < 0 else "") + "P"
        if days:
            duration += str(days) + "D"
        if hours or minutes or seconds or not days:
            duration += "T"
            if hours:
                duration += str(hours) + "H"
            if minutes:
                duration += str(minutes) + "M"
            if seconds or not (hours or minutes):
                duration += str(seconds) + "S"
        lines.extend(
            [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                "TRIGGER;RELATED=START:" + duration,
                "DESCRIPTION:" + escaped(summary or "Reminder"),
                "END:VALARM",
            ]
        )
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    folded = []
    for line in lines:
        physical = ""
        octets = 0
        for char in line:
            size = len(char.encode("utf-8"))
            if octets + size > 75:
                folded.append(physical)
                physical, octets = " ", 1
            physical += char
            octets += size
        folded.append(physical)
    return "\r\n".join(folded) + "\r\n"
