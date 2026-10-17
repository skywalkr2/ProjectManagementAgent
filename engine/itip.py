"""Parse individual iTIP events, prepare replies, and compare revisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from icalendar import Calendar, Event, vCalAddress

type When = date | datetime

PRODID = "-//PM Cockpit//Invitation Reply//EN"


@dataclass(frozen=True)
class Attendee:
    email: str
    status: str = "NEEDS-ACTION"
    name: str | None = None
    role: str = "REQ-PARTICIPANT"


@dataclass(frozen=True)
class Invitation:
    method: str
    uid: str
    sequence: int
    summary: str
    start: When | None
    end: When | None
    organizer: str
    attendees: tuple[Attendee, ...]
    cancelled: bool
    dtstamp: datetime
    recurrence_id: When | None = None
    recurrence_range: str | None = None


def _email(value: str) -> str:
    """Accept a mailto calendar address without display-name syntax."""
    email = value[7:] if value.lower().startswith("mailto:") else value
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", email):
        raise ValueError("Expected a bare email address or mailto URI")
    return email


def read_invitation(ics_text: str) -> Invitation:
    """Read exactly one VEVENT with METHOD REQUEST, CANCEL, or REPLY.

    Unknown/custom TZIDs without a usable VTIMEZONE are rejected rather than
    silently interpreted as floating. Bare floating times remain naive. A CANCEL
    or REPLY can omit DTSTART. Missing SEQUENCE defaults to zero. Authentication
    of the organizer and transport is the caller's responsibility.
    """
    try:
        calendar = Calendar.from_ical(ics_text)
    except Exception as error:
        raise ValueError("Invalid iCalendar text") from error
    if calendar.name != "VCALENDAR" or str(calendar.get("VERSION", "")) != "2.0":
        raise ValueError("Expected a VERSION 2.0 VCALENDAR")
    method = str(calendar.get("METHOD", "")).upper()
    if method not in {"REQUEST", "CANCEL", "REPLY"}:
        raise ValueError("Supported methods are REQUEST, CANCEL, and REPLY")
    events = calendar.walk("VEVENT")
    if len(events) != 1:
        raise ValueError("Expected exactly one VEVENT; split recurrence instances before reading")
    event = events[0]
    if event.errors:
        raise ValueError("VEVENT contains malformed properties")

    def one(name: str, required: bool = False):
        value = event.get(name)
        if isinstance(value, list):
            raise ValueError(f"Duplicate {name}")
        if value is None and required:
            raise ValueError(f"Missing {name}")
        return value

    def when(name: str, required: bool = False) -> When | None:
        value = one(name, required)
        if value is None:
            return None
        result = getattr(value, "dt", None)
        if not isinstance(result, date):
            raise ValueError(f"Invalid {name}")
        if isinstance(result, datetime) and value.params.get("TZID") and result.tzinfo is None:
            raise ValueError(f"Unresolved TZID in {name}")
        return result

    uid = str(one("UID", True))
    if not uid.strip():
        raise ValueError("Empty UID")
    raw_sequence = str(one("SEQUENCE") or "0")
    if not re.fullmatch(r"\d+", raw_sequence) or int(raw_sequence) > 2147483647:
        raise ValueError("SEQUENCE must be a nonnegative 32-bit integer")
    stamp = when("DTSTAMP", True)
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() != timedelta():
        raise ValueError("DTSTAMP must be a UTC DATE-TIME")
    start = when("DTSTART", method == "REQUEST")
    end = when("DTEND")
    duration = one("DURATION")
    if end is not None and duration is not None:
        raise ValueError("DTEND and DURATION cannot coexist")
    if duration is not None:
        delta = getattr(duration, "dt", None)
        if start is None or not isinstance(delta, timedelta) or delta <= timedelta():
            raise ValueError("Invalid event DURATION")
        if not isinstance(start, datetime) and delta.seconds:
            raise ValueError("All-day DURATION must contain whole days")
        end = start + timedelta(days=delta.days)
        seconds = timedelta(seconds=delta.seconds)
        if isinstance(end, datetime) and end.tzinfo is not None:
            end = (end.astimezone(UTC) + seconds).astimezone(end.tzinfo)
        else:
            end += seconds
    if end is not None:
        if start is None or isinstance(start, datetime) != isinstance(end, datetime):
            raise ValueError("DTSTART and DTEND must have matching value types")
        if isinstance(start, datetime):
            if (start.tzinfo is None) != (end.tzinfo is None):
                raise ValueError("DTSTART and DTEND must both be floating or aware")
            left = start.astimezone(UTC) if start.tzinfo else start
            right = end.astimezone(UTC) if end.tzinfo else end
        else:
            left, right = start, end
        if right <= left:
            raise ValueError("DTEND must be later than DTSTART")
    organizer = _email(str(one("ORGANIZER", True)))
    raw_attendees = event.get("ATTENDEE", [])
    if not isinstance(raw_attendees, list):
        raw_attendees = [raw_attendees]
    attendees = tuple(
        Attendee(
            email=_email(str(value)),
            status=str(value.params.get("PARTSTAT", "NEEDS-ACTION")).upper(),
            name=str(value.params["CN"]) if "CN" in value.params else None,
            role=str(value.params.get("ROLE", "REQ-PARTICIPANT")).upper(),
        )
        for value in raw_attendees
    )
    if method in {"REQUEST", "REPLY"} and not attendees:
        raise ValueError("REQUEST and REPLY require an attendee")
    if method == "REPLY" and len(attendees) != 1:
        raise ValueError("REPLY must contain exactly one responding attendee")
    if len({person.email.casefold() for person in attendees}) != len(attendees):
        raise ValueError("Duplicate attendee address")
    recurrence = one("RECURRENCE-ID")
    return Invitation(
        method,
        uid,
        int(raw_sequence),
        str(one("SUMMARY") or ""),
        start,
        end,
        organizer,
        attendees,
        method == "CANCEL" or str(one("STATUS") or "").upper() == "CANCELLED",
        stamp.astimezone(UTC),
        when("RECURRENCE-ID"),
        str(recurrence.params["RANGE"]) if recurrence and "RANGE" in recurrence.params else None,
    )


def reply_ics(
    invitation: Invitation,
    attendee_email: str,
    status: Literal["ACCEPTED", "DECLINED", "TENTATIVE"],
    comment: str | None = None,
    *,
    dtstamp: datetime,
) -> str:
    """Prepare a REPLY containing only the responding attendee; never send it.

    Supply the reply creation instant explicitly to avoid reading the clock.
    Echo the organizer's UID, SEQUENCE, and optional RECURRENCE-ID. Convert aware
    times to UTC so replies do not depend on copying a VTIMEZONE definition.
    Floating and all-day values retain their value types.
    """
    if invitation.method != "REQUEST" or invitation.cancelled:
        raise ValueError("Only an active REQUEST can be answered")
    if status not in {"ACCEPTED", "DECLINED", "TENTATIVE"}:
        raise ValueError("Unsupported participation status")
    if dtstamp.tzinfo is None or dtstamp.utcoffset() is None:
        raise ValueError("dtstamp must be aware")
    email = _email(attendee_email)
    person = next((entry for entry in invitation.attendees if entry.email.casefold() == email.casefold()), None)
    if person is None:
        raise ValueError("The responding address is not an invited attendee")
    calendar = Calendar()
    calendar.add("PRODID", PRODID)
    calendar.add("VERSION", "2.0")
    calendar.add("METHOD", "REPLY")
    event = Event()
    event.add("UID", invitation.uid)
    event.add("SEQUENCE", invitation.sequence)
    event.add("DTSTAMP", dtstamp.astimezone(UTC))
    event.add("ORGANIZER", vCalAddress("mailto:" + invitation.organizer))
    attendee = vCalAddress("mailto:" + person.email)
    attendee.params["PARTSTAT"] = status
    attendee.params["ROLE"] = person.role
    if person.name:
        attendee.params["CN"] = person.name
    event.add("ATTENDEE", attendee)
    if invitation.summary:
        event.add("SUMMARY", invitation.summary)
    for name, value in (("DTSTART", invitation.start), ("RECURRENCE-ID", invitation.recurrence_id)):
        if value is not None:
            if isinstance(value, datetime) and value.tzinfo is not None:
                value = value.astimezone(UTC)
            event.add(name, value)
            if name == "RECURRENCE-ID" and invitation.recurrence_range:
                event[name].params["RANGE"] = invitation.recurrence_range
    if comment is not None:
        event.add("COMMENT", comment)
    calendar.add_component(event)
    return calendar.to_ical().decode("utf-8")


def newer(a: Invitation, b: Invitation) -> Invitation:
    """Return the higher SEQUENCE, then later DTSTAMP; exact ties keep a.

    Compare only organizer revisions of the same UID and recurrence instance.
    REPLY timestamps update attendee participation, not the organizer's event,
    so replies cannot compete with REQUEST/CANCEL or another attendee's reply.
    """
    if a.uid != b.uid or a.recurrence_id != b.recurrence_id:
        raise ValueError("Versions must identify the same UID and recurrence instance")
    if a.organizer.casefold() != b.organizer.casefold():
        raise ValueError("Versions have different organizers")
    if (a.method == "REPLY" or b.method == "REPLY") and (
        a.method != b.method
        or {person.email.casefold() for person in a.attendees} != {person.email.casefold() for person in b.attendees}
    ):
        raise ValueError("Replies must be compared separately for the same attendee")
    return b if (b.sequence, b.dtstamp) > (a.sequence, a.dtstamp) else a
