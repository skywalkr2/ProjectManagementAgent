"""Work the assistant releases on its own keeps the person's hours (design 6.35).

A line the assistant or a rule adds to Today by itself, whose cause came in outside working hours or inside quiet
hours, is held back until the next moment that is inside the one and outside the other. What waited arrives together:
the lines keep their place, and one row says how many of them waited. Reads only; nothing here changes a record.

Never held: a reminder the person set (it fires at the time chosen, held only by quiet hours, `engine.reminder_lines`),
anything made from the person's own note (they are present), the person's own setup in progress, lines that report a
stop (a restart waiting, a paused account, a failed run), and lines with no moment of arrival (a date passing, a count
that builds over days). A line is held only when its kind is in `HELD_KINDS`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from engine import reminder_lines
from engine.plugin_api import TODAY_GROUPS
from engine.reminders import release_at

#: The lines the assistant or a rule adds on its own, each with an arrival time (see `cause`).
HELD_KINDS = frozenset(
    {
        "decision",
        "question",
        "who_is",
        "owner",
        "moved",
        "held",
        "go",
        "refused",
        "review",
        "reply",
        "learned",
        "unfiled",
        "since_yesterday",
    }
)

#: The line that says how many lines waited for the person's hours.
AWAY = "away"


def _moment(stamp: Any) -> datetime | None:
    """A stored time with a time of day as a moment with a zone; a day alone, or anything else, is none."""
    if not isinstance(stamp, str) or "T" not in stamp:
        return None
    try:
        at = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _from_request(req: Any, sources: dict[str, Any]) -> datetime | None:
    """When the cause of a line made for a request came in: the input's own received time, else when the request was
    made. None for the person's own note, whose line is never held."""
    d = req.data
    if d.get("origin") == "pm":
        return None
    source = sources.get(d.get("source") or "") or {}
    if d.get("origin") == "input":
        received = _moment(source.get("received_at"))
        if received is not None:
            return received
    return _moment(d.get("created_at"))


def causes(
    lines: list[Any],
    reader: Any,
    requests: dict[str, Any],
    by_changeset: dict[str, Any],
    sources: dict[str, Any],
) -> dict[str, datetime]:
    """The moment each line's cause came in, by the line's key, for the lines the assistant added on its own."""
    mine = {r.data["source"] for r in requests.values() if r.data.get("origin") == "pm" and r.data.get("source")}
    found: dict[str, datetime] = {}
    for line in lines:
        if line.kind not in HELD_KINDS:
            continue
        request = requests.get(line.request or "") or by_changeset.get(line.changeset or "")
        if request is not None:
            at = _from_request(request, sources)
        else:
            source = None
            if line.question:
                question = reader.get("question", line.question)
                data = question.data if question is not None else {}
                source = data.get("source")
                if not source and (data.get("resolves") or {}).get("action"):
                    action = reader.get("action", data["resolves"]["action"])
                    source = action.data.get("source") if action is not None else None
            if source in mine:
                continue
            received = _moment((sources.get(source or "") or {}).get("received_at")) if source else None
            at = received or _moment(line.since)
        if at is not None:
            found[line.key] = at
    return found


def keep_hours(
    lines: list[Any], caused: dict[str, datetime], cfg: Any, now: datetime, make_row: Callable[..., Any]
) -> list[Any]:
    """The lines whose hours have come, and one `away` row counting those that waited and were released today (the
    person's day, so the row goes with it). A line is held while its cause's release moment is still ahead."""
    r = reminder_lines.rules(cfg)
    today = now.astimezone(r.tz).date()
    shown: list[Any] = []
    arrived: list[datetime] = []
    groups: list[str] = []
    for line in lines:
        cause = caused.get(line.key)
        if cause is None:
            shown.append(line)
            continue
        released = release_at(cause, r.tz, r.quiet, r.working)
        if released > now:
            continue
        shown.append(line)
        if released > cause and released.astimezone(r.tz).date() == today:
            arrived.append(released)
            groups.append(line.group)
    if arrived:
        # The row sits at the top of the first group any of them is in, below only what reports a stop.
        first = min(groups, key=TODAY_GROUPS.index)
        shown.append(make_row(key=AWAY, group=first, kind=AWAY, count=len(arrived), since=min(arrived).isoformat()))
    return shown
