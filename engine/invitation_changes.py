"""What changed between two versions of a meeting invitation, as data the screen words from the wording sheet.

Each change is a kind and its values; nothing here is on-screen text. Times are compared as instants, so the same time
written in another zone is no change; timed values come back in the person's zone, with `repeated_hour` set when the
clocks show that time twice and the screen must add the offset. An all-day end is exclusive, so `last_day` carries the
day the event actually ends on. A missing or unreadable value gives an `*_unknown` change with a reason code, never a
guess. Order: cancellation, title, start, end, location, organizer, removed attendees, then added or changed ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any


@dataclass(frozen=True)
class Person:
    email: str
    name: str | None = None


@dataclass(frozen=True)
class Attendee:
    email: str
    name: str | None
    status: str | None


@dataclass(frozen=True)
class Invitation:
    summary: str | None
    start: date | datetime | None
    end: date | datetime | None
    location: str | None
    organizer: Person | None
    attendees: tuple[Attendee, ...]
    cancelled: bool | None


@dataclass(frozen=True)
class Change:
    kind: str
    values: dict[str, Any] = field(default_factory=dict)


#: Response statuses (RFC 5545 PARTSTAT) the screen has words for, by the code passed to it.
STATUSES = {
    "ACCEPTED": "accepted",
    "DECLINED": "declined",
    "TENTATIVE": "tentative",
    "NEEDS-ACTION": "no_reply",
    "DELEGATED": "delegated",
}


class _Unknown(ValueError):
    """A value that can't be compared; its argument is the reason code."""


def _instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _Unknown("no_zone")
    instant = value.astimezone(UTC)
    if instant.astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise _Unknown("time_does_not_exist")
    return instant


def _when(value: date | datetime, zone: tzinfo) -> dict[str, Any]:
    """A start or end for the screen: a local time with the repeated-hour flag, or an all-day date."""
    if isinstance(value, datetime):
        local = _instant(value).astimezone(zone)
        repeated = local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset()
        return {"at": local, "repeated_hour": repeated}
    if type(value) is not date:
        raise _Unknown("unsupported_value")
    return {"date": value}


def _same(first: date | datetime | None, second: date | datetime | None) -> bool:
    for value in (first, second):
        if isinstance(value, datetime):
            _instant(value)
    if isinstance(first, datetime) and isinstance(second, datetime):
        return _instant(first) == _instant(second)
    return type(first) is type(second) and first == second


def _email(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.count("@") != 1:
        raise _Unknown("bad_address")
    local, domain = value.strip().rsplit("@", 1)
    if not local or not domain or any(character.isspace() for character in local + domain):
        raise _Unknown("bad_address")
    # The local part's case is kept; a domain's case never matters.
    return local + "@" + domain.casefold()


def _who(value: Person | Attendee) -> dict[str, Any]:
    name = value.name.strip() if isinstance(value.name, str) and value.name.strip() else None
    return {"email": _email(value.email), "name": name}


def describe_change(old: Invitation, new: Invitation, tz: tzinfo) -> list[Change]:
    """Return the changes from `old` to `new` in a stable order; an unchanged invitation gives an empty list."""
    if not isinstance(tz, tzinfo):
        return [Change("unknown", {"reason": "no_zone_given"})]
    if not isinstance(old, Invitation) or not isinstance(new, Invitation):
        return [Change("unknown", {"reason": "not_invitations"})]
    changes: list[Change] = []
    if type(old.cancelled) is not bool or type(new.cancelled) is not bool:
        changes.append(Change("cancelled_unknown", {"reason": "missing"}))
    elif old.cancelled != new.cancelled:
        changes.append(Change("cancelled" if new.cancelled else "restored"))

    if old.summary != new.summary:
        changes.append(Change("title_changed", {"title": new.summary}) if new.summary else Change("title_removed"))

    try:
        for version in (old, new):
            if version.start is not None and version.end is not None:
                if isinstance(version.start, datetime) != isinstance(version.end, datetime):
                    raise _Unknown("mixed_date_and_time")
                if isinstance(version.start, datetime):
                    in_order = _instant(version.end) > _instant(version.start)
                elif type(version.start) is date and type(version.end) is date:
                    in_order = version.end > version.start
                else:
                    raise _Unknown("unsupported_value")
                if not in_order:
                    raise _Unknown("end_not_after_start")
        if not _same(old.start, new.start):
            if old.start is None or new.start is None:
                changes.append(Change("start_unknown", {"reason": "missing"}))
            elif isinstance(old.start, datetime) != isinstance(new.start, datetime):
                kind = "now_timed" if isinstance(new.start, datetime) else "now_all_day"
                changes.append(Change(kind, {"start": _when(new.start, tz)}))
            else:
                changes.append(Change("moved", {"before": _when(old.start, tz), "after": _when(new.start, tz)}))
        if not _same(old.end, new.end):
            if old.end is None or new.end is None:
                changes.append(Change("end_unknown", {"reason": "missing"}))
            else:
                before, after = _when(old.end, tz), _when(new.end, tz)
                for shown, value in ((before, old.end), (after, new.end)):
                    if type(value) is date:
                        shown["last_day"] = value - timedelta(days=1)
                changes.append(Change("end_changed", {"before": before, "after": after}))
    except (_Unknown, OverflowError) as error:
        reason = error.args[0] if isinstance(error, _Unknown) else "out_of_range"
        changes.append(Change("times_unknown", {"reason": reason}))

    if old.location != new.location:
        changes.append(
            Change("location_changed", {"location": new.location}) if new.location else Change("location_removed")
        )

    try:
        old_organizer = _email(old.organizer.email) if old.organizer is not None else None
        new_organizer = _email(new.organizer.email) if new.organizer is not None else None
        if old_organizer != new_organizer:
            changes.append(
                Change("organizer_changed", _who(new.organizer)) if new.organizer else Change("organizer_removed")
            )
        elif new.organizer is not None and old.organizer is not None and old.organizer.name != new.organizer.name:
            changes.append(Change("organizer_renamed", _who(new.organizer)))
    except _Unknown as error:
        changes.append(Change("organizer_unknown", {"reason": error.args[0]}))

    try:

        def indexed(values: tuple[Attendee, ...]) -> dict[str, Attendee]:
            result: dict[str, Attendee] = {}
            for attendee in values:
                key = _email(attendee.email)
                if key in result:
                    raise _Unknown("duplicate_attendee")
                result[key] = attendee
            return result

        before_people, after_people = indexed(old.attendees), indexed(new.attendees)
        for email, attendee in before_people.items():
            if email not in after_people:
                changes.append(Change("attendee_removed", _who(attendee)))
        for email, attendee in after_people.items():
            if email not in before_people:
                changes.append(Change("attendee_added", _who(attendee)))
                continue
            previous = before_people[email]
            if previous.name != attendee.name:
                changes.append(Change("attendee_renamed", {**_who(attendee), "before": _who(previous)["name"]}))
            old_status = previous.status.upper() if isinstance(previous.status, str) else None
            new_status = attendee.status.upper() if isinstance(attendee.status, str) else None
            if old_status != new_status:
                if new_status in STATUSES:
                    changes.append(Change("attendee_replied", {**_who(attendee), "status": STATUSES[new_status]}))
                else:
                    changes.append(Change("attendee_reply_unknown", {**_who(attendee), "reason": "unrecognized"}))
    except (_Unknown, TypeError) as error:
        reason = error.args[0] if isinstance(error, _Unknown) else "unreadable"
        changes.append(Change("attendees_unknown", {"reason": reason}))
    return changes
