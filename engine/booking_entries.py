"""Calendar entries from booking confirmations (design 6.32, "What arrives").

An input that carries a booking as structured data (a flight, a stay, a table, a rental car, a train or an event; see
`engine.bookings`) becomes an entry in the app's own calendar: a local record, never a message to any calendar service.
The rules make the entries; the assistant's own reading of the same input adds no second one. Each entry carries the
exact words of the confirmation that show it (the confirmation code, else the provider's or the place's name), because
claims carry evidence; a booking none of those words can be found for is reported and made no entry. A start with no
time zone stays in the person's own, and an offset the markup states is kept. Nothing is guessed: a booking with no
start makes no entry.

Everything here is plain rules over the input's text; no AI runs."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from engine.bookings import Booking, read_bookings
from engine.records import canonical_time
from engine.sides import word


@dataclass(frozen=True)
class Made:
    """What a read of an input's bookings gives: the `event.add` ops to apply, and what could not be made, each with
    its reason, for the person to read."""

    ops: tuple[dict[str, Any], ...]
    skipped: tuple[str, ...]


def looks_structured(text: str) -> bool:
    """Whether a text might carry booking markup at all, so plain mail is never parsed."""
    lowered = text.lower()
    return "application/ld+json" in lowered or "itemscope" in lowered


def _moment(value: date | datetime | None, zone_name: str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None and zone_name:
            with contextlib.suppress(ZoneInfoNotFoundError, ValueError):
                value = value.replace(tzinfo=ZoneInfo(zone_name))
        return canonical_time(value.isoformat())
    return value.isoformat()


def _title(cfg: Any, booking: Booking) -> str:
    kind = word(cfg, f"booking.kind.{booking.kind}")
    place = booking.place.name if booking.place and booking.place.name else None
    destination = booking.destination.name if booking.destination and booking.destination.name else None
    if place and destination:
        detail = word(cfg, "booking.route").format(place=place, destination=destination)
    else:
        detail = place or destination or booking.provider
    return word(cfg, "booking.title").format(kind=kind, detail=detail) if detail else kind


def _evidence(booking: Booking, text: str) -> str | None:
    """The first of the confirmation code, the provider's name and the place's name that is in the text exactly."""
    place = booking.place.name if booking.place else None
    for candidate in (booking.confirmation_code, booking.provider, place):
        if candidate and len(candidate) >= 3 and candidate in text:
            return candidate
    return None


def entries(cfg: Any, text: str) -> Made:
    """The calendar entries an input's bookings make, and what was left out."""
    if not cfg.steward.dates.bookings_to_calendar or not looks_structured(text):
        return Made((), ())
    read = read_bookings(text)
    ops: list[dict[str, Any]] = []
    skipped = [f"{issue.field}: {issue.note}" for issue in read.issues]
    for booking in read.bookings:
        title = _title(cfg, booking)
        start = _moment(booking.start, booking.time_zone)
        if start is None:
            skipped.append(f"{title}: no start was stated, so no entry was made")
            continue
        quote = _evidence(booking, text)
        if quote is None:
            skipped.append(f"{title}: nothing in the confirmation to quote, so no entry was made")
            continue
        end = _moment(booking.end, booking.time_zone)
        op: dict[str, Any] = {"op": "event.add", "title": title, "start": start, "evidence": {"quote": quote}}
        if end is not None and end != start:
            op["end"] = end
        ops.append(op)
    return Made(tuple(ops), tuple(skipped))


def add_to(changeset: Any, cfg: Any, view: Any, text: str) -> Any:
    """The changeset with the entries the input's bookings make added, and without an `event.add` of the assistant's
    own that starts at the same moment as one of them (the same booking read twice). An entry that is already in the
    calendar with the same title and start is not made again. Returns the changeset unchanged when the input carries
    no booking."""
    made = entries(cfg, text)
    if made.skipped:
        said = [" ".join(reason.split())[:200] for reason in made.skipped]
        missing = list(dict.fromkeys([*changeset.missing, *said]))[:20]
        changeset = changeset.model_copy(update={"missing": missing})
    if not made.ops:
        return changeset
    from engine.ops import EventAddOp

    have = {(e.data["title"], e.data["start"]) for e in view.list("event")}
    fresh = [EventAddOp.model_validate(o) for o in made.ops if (o["title"], canonical_time(o["start"])) not in have]
    if not fresh:
        return changeset
    starts = {op.start for op in fresh}
    kept = [op for op in changeset.ops if not (getattr(op, "op", None) == "event.add" and op.start in starts)]
    return changeset.model_copy(update={"ops": [*kept, *fresh]})
