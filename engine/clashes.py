"""Find pairwise calendar conflicts without changing events or external state."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Event:
    id: str
    calendar_id: str
    start: datetime
    end: datetime
    show_as: str
    location: str | None = None


@dataclass(frozen=True)
class Clash:
    first: Event
    second: Event
    overlap_minutes: float
    travel_shortfall_minutes: float | None
    reason: str


@dataclass(frozen=True)
class UnknownPair:
    first: Event
    second: Event
    status: str
    reason: str


@dataclass(frozen=True)
class Issue:
    index: int
    status: str
    reason: str


@dataclass(frozen=True)
class ClashReport:
    status: str
    blocking: tuple[Clash, ...]
    tentative: tuple[Clash, ...]
    unknown_pairs: tuple[UnknownPair, ...]
    issues: tuple[Issue, ...]
    reason: str


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Event times must be aware datetimes")
    instant = value.astimezone(UTC)
    if instant.astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("An event time falls in a nonexistent local time")
    return instant


def _location(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    return normalized or None


def _online(location: str) -> bool:
    """A web link as the location is an online meeting: no travel to or from it."""
    return "://" in location or location.startswith("www.")


def clashes(events: Sequence[Event], travel_minutes: float = 0) -> ClashReport:
    """Return firm and tentative conflicts, plus explicit uncertainty and invalid inputs."""
    if (
        not isinstance(travel_minutes, (int, float))
        or isinstance(travel_minutes, bool)
        or (isinstance(travel_minutes, float) and not math.isfinite(travel_minutes))
        or travel_minutes < 0
    ):
        return ClashReport("unknown", (), (), (), (), "Travel minutes must be a finite nonnegative number.")
    valid = []
    issues = []
    seen = set()
    for index, event in enumerate(events):
        try:
            if not isinstance(event, Event):
                raise ValueError("Each event must supply its calendar, ID, times, and show-as value")
            if not isinstance(event.id, str) or not event.id.strip():
                raise ValueError("An event needs a nonempty ID")
            if not isinstance(event.calendar_id, str) or not event.calendar_id.strip():
                raise ValueError("An event needs a nonempty calendar ID")
            identity = (event.calendar_id, event.id)
            if identity in seen:
                raise ValueError("An event identity appears more than once; remove the duplicate before comparing")
            seen.add(identity)
            start, end = _instant(event.start), _instant(event.end)
            if end <= start:
                raise ValueError("An event must end after it starts")
            show_as = (
                event.show_as.strip().lower().replace("_", " ").replace("-", " ")
                if isinstance(event.show_as, str)
                else None
            )
            if show_as not in {"busy", "out of office", "tentative", "free"}:
                raise ValueError("The show-as value is unknown")
            if event.location is not None and not isinstance(event.location, str):
                raise ValueError("The location must be text or explicitly absent")
            if show_as != "free":
                valid.append((start, end, index, event, show_as == "tentative"))
        except ValueError as error:
            issues.append(Issue(index, "unknown", str(error)))
    valid.sort(key=lambda entry: (entry[0], entry[2]))
    blocking = []
    tentative = []
    unknown_pairs = []
    for position, (first_start, first_end, _, first, first_tentative) in enumerate(valid):
        for second_start, second_end, _, second, second_tentative in valid[position + 1 :]:
            # Sorted by start: once a later event starts past the travel allowance, none after it can clash.
            if (second_start - first_end).total_seconds() / 60 >= travel_minutes and second_start >= first_end:
                break
            overlap = (min(first_end, second_end) - max(first_start, second_start)).total_seconds() / 60
            travel_shortfall = None
            if overlap > 0:
                reason = "The events overlap in time."
            else:
                gap = (second_start - first_end).total_seconds() / 60
                if gap >= travel_minutes:
                    continue
                first_location, second_location = _location(first.location), _location(second.location)
                if (first_location and _online(first_location)) or (second_location and _online(second_location)):
                    continue
                if first_location is None or second_location is None:
                    unknown_pairs.append(
                        UnknownPair(first, second, "unknown", "A location is missing, so travel cannot be assessed.")
                    )
                    continue
                if first_location == second_location:
                    continue
                travel_shortfall = travel_minutes - gap
                overlap = 0.0
                reason = "Different stated locations leave less than the supplied travel time between events."
            item = Clash(first, second, overlap, travel_shortfall, reason)
            if first_tentative or second_tentative:
                tentative.append(item)
            else:
                blocking.append(item)
    # A pair with no location is listed for review but doesn't make the whole report unknown: most events have none.
    status = "unknown" if issues else "known"
    reason = (
        "Some events couldn't be read; confirmed clashes are still included."
        if status == "unknown"
        else "All supplied event pairs were assessed under the stated time and location rules."
    )
    return ClashReport(status, tuple(blocking), tuple(tentative), tuple(unknown_pairs), tuple(issues), reason)
