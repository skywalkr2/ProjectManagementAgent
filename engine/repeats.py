"""Repeating to-dos (design 6.32): the repeat on an action, the next occurrence made when one ends, and what the screens
read.

Each occurrence is its own action, and only the next exists at a time. When an action with a repeat ends (done,
dropped, or done by someone else), `make_next` creates the next in the same transaction as the ending, so Undo of the
ending takes both back: same text, owners, project and notes, the same repeat, `occurrence_of` naming the first
occurrence, due on the first date of the rule after the ended one's due date and not before today. An occurrence that is
missed stays open, and nothing makes a second while one is open. Dates come from the same repeat engine the calendar
uses (`engine/recurrence.py`). Reads and the one write here carry no wording; the screens say shapes from the wording
sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from engine.recurrence import occurrences
from engine.repeat_phrases import Shape, rule_from_phrase, rule_shape
from engine.storage import WriteContext

#: How far ahead a phrase is tried for the first day it falls on, when the day it was read from isn't one.
SCAN_DAYS = 400
#: The span of one search for the next date, and how many spans are tried (about twenty years) before giving up.
SPAN_DAYS = 400
SPANS = 20
#: The fields an occurrence carries over from the one that ended.
CARRIED = ("text", "owners", "project", "notes")
_UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class Reading:
    """What a phrase says when read from a day. `ok`: the repeat starts on `start` (the day given, or the first day the
    phrase falls on when none was given). `off_start`: the phrase is clear but the day given isn't one of its days;
    `start` is the first that is. `unclear`: the grammar declines it, and nothing is guessed."""

    status: str
    rule: str | None = None
    shape: Shape | None = None
    start: date | None = None


def read_phrase(phrase: str, start: date | None, today: date) -> Reading:
    """Read the words a person typed for a repeat, from `start` (the to-do's day) or, with none, from today."""
    origin = start or today
    found = rule_from_phrase(phrase, origin)
    if isinstance(found, str):
        shape = rule_shape(found, origin)
        return Reading("ok", found, shape, origin) if isinstance(shape, Shape) else Reading("unclear")
    if found.status != "off_start":
        return Reading("unclear")
    for ahead in range(1, SCAN_DAYS + 1):
        day = origin + timedelta(days=ahead)
        again = rule_from_phrase(phrase, day)
        if isinstance(again, str):
            shape = rule_shape(again, day)
            if not isinstance(shape, Shape):
                return Reading("unclear")
            return Reading("off_start" if start else "ok", again, shape, day)
    return Reading("unclear")


def local_today(store: Any, cfg: Any) -> date:
    """Today on the person's own clock, from the store's clock."""
    from engine.today import zone

    return datetime.fromisoformat(store.clock()).astimezone(zone(cfg)).date()


def next_date(repeat: dict[str, Any], ended_due: date | None, today: date) -> date | None:
    """The first date of the rule after the ended one's due date (after today when it had none) and not before today,
    counting from the repeat's own start so a rule of every other week keeps its weeks. None when the rule has no
    later date."""
    start = date.fromisoformat(str(repeat["start"]))
    lower = max((ended_due or today) + timedelta(days=1), today)
    for span in range(SPANS):
        first = lower + timedelta(days=span * SPAN_DAYS)
        found = occurrences(start, None, repeat["rule"], (), (), {}, first, first + timedelta(days=SPAN_DAYS), _UTC)
        days = sorted(item.start for item in found if not item.cancelled and item.start >= lower)
        if days:
            return days[0]
    return None


def _chain(repeating: Any) -> str:
    return repeating.data.get("occurrence_of") or repeating.id


def _open_sibling(view: Any, ended: Any) -> bool:
    """Whether another occurrence of the same repeat is still open or waiting for an owner."""
    chain = _chain(ended)
    others = [*view.find("action", {"occurrence_of": chain}), view.get("action", chain)]
    return any(
        a is not None and a.id != ended.id and a.data.get("status") in ("open", "held") and a.data.get("repeat")
        for a in others
    )


def make_next(tx: Any, ended: Any, w: WriteContext, today: date) -> str | None:
    """Make the next occurrence of an action that has just ended (read before the ending), in the caller's own
    transaction and write context, and return its id. Nothing is made when the action doesn't repeat, had no owner,
    another occurrence of it is still open, or its rule has no later date."""
    data = ended.data
    repeat = data.get("repeat")
    if not repeat or not data.get("owners") or _open_sibling(tx, ended):
        return None
    due = next_date(repeat, date.fromisoformat(str(data["due"])) if data.get("due") else None, today)
    if due is None:
        return None
    made = {key: data.get(key) for key in CARRIED if data.get(key) is not None}
    made |= {
        "repeat": repeat,
        "occurrence_of": _chain(ended),
        "due": due.isoformat(),
        "due_by_person": True,
        "status": "open",
    }
    return tx.create("action", made, w).id


def take_back_next(tx: Any, reopened: Any, w: WriteContext) -> str | None:
    """A repeating to-do that ended and is reopened (a screen's Undo of Mark done) takes back the next occurrence its
    ending made, when nobody has touched that one since. Returns the id taken back."""
    repeat = reopened.data.get("repeat")
    if not repeat:
        return None
    chain = _chain(reopened)
    due = reopened.data.get("due") or ""
    later = [
        a
        for a in tx.find("action", {"occurrence_of": chain})
        if a.id != reopened.id
        and a.version == 1
        and a.data.get("status") == "open"
        and a.data.get("repeat") == repeat
        and str(a.data.get("due") or "") > str(due)
    ]
    if not later:
        return None
    newest = max(later, key=lambda a: a.id)
    tx.delete("action", newest.id, w, read_version=newest.version)
    return newest.id


def earlier_occurrences(view: Any, action: Any) -> list[dict[str, Any]]:
    """The occurrences of this action's repeat that have ended, oldest first, each with its day and how it ended
    (`done` or `dropped`)."""
    chain = _chain(action)
    members = [*view.find("action", {"occurrence_of": chain}), view.get("action", chain)]
    ended = [a for a in members if a is not None and a.id != action.id and a.data.get("status") in ("done", "dropped")]
    ended.sort(key=lambda a: (str(a.data.get("due") or ""), a.id))
    return [{"id": a.id, "due": a.data.get("due"), "how": a.data["status"]} for a in ended]


def problem(view: Any, op: Any) -> str | None:
    """Why an `action.repeat` can't apply, or None: the action must be open, a rule must be one the grammar can say
    back from its start, and the start must be the action's own day when it has one. Stopping needs a repeat to stop."""
    found = view.get("action", op.id)
    if found is None:
        return f"there is no action {op.id}"
    if found.data["status"] != "open":
        return f"action {op.id} is {found.data['status']}, so it can't be made to repeat"
    if op.rule is None:
        return None if found.data.get("repeat") else f"action {op.id} doesn't repeat"
    shape = rule_shape(op.rule, op.start)
    if not isinstance(shape, Shape):
        return f"the repeat can't be read: {shape.reason}"
    due = found.data.get("due")
    if due and str(due) != op.start.isoformat():
        return f"action {op.id} is due {due}, so the repeat starts on that day"
    return None


def view_of(repeat: dict[str, Any] | None) -> dict[str, Any] | None:
    """A stored repeat with the shape the screen says back; None when it has none or its rule is no longer readable."""
    if not repeat:
        return None
    start = date.fromisoformat(str(repeat["start"]))
    shape = rule_shape(repeat["rule"], start)
    if not isinstance(shape, Shape):
        return None
    return {"phrase": repeat["phrase"], "rule": repeat["rule"], "start": start, "shape": shape_view(shape)}


def shape_view(shape: Shape) -> dict[str, Any]:
    """A shape as the fields the API returns: its kind and its values, each under its own name."""
    return {"kind": shape.kind, **shape.values}
