"""Blocked actions (design 6.9, "On hold"): an action on hold that names its blocker, a person, an action or a question.

Blocked is not a second state. The hold is the state; `OnHold.on` says what it waits on, and this module reads that: who
or what the blocker is by name, whether it still blocks, and how many actions are blocked, by project and in all (the
count Top priorities reads). A hold with only words is on hold, never blocked. Reads only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from engine.names import People
from engine.records import blocker_kind

#: How a blocker stands: still waited on, a question that was answered, or an action that is finished or dropped.
WAITING, ANSWERED, DONE = "waiting", "answered", "done"


@dataclass(frozen=True)
class Blocker:
    """What a hold waits on, for a row to say: its kind (person, action or question), id and name (a person's name, an
    action's text, a question's title), who was asked and when it was sent (a question), how it stands, and the day
    a question was answered."""

    kind: str
    id: str
    name: str
    state: str = WAITING
    who: str | None = None
    sent: date | None = None
    answered: date | None = None

    @property
    def resolved(self) -> bool:
        return self.state != WAITING


def _day(value: Any, here: ZoneInfo | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value)
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                return None
    if here is not None and moment.tzinfo is not None:
        moment = moment.astimezone(here)
    return moment.date()


def answered_on(view: Any, question_id: str, here: ZoneInfo | None = None) -> date | None:
    """The day a question was answered, from the ledger's last change of its status to answered."""
    found = None
    for row in view.ledger(kind="question", record_id=question_id):
        if row.get("field") == "status" and row.get("after") == "answered":
            found = row["at"]
    return _day(found, here)


def blocker_of(view: Any, hold: dict[str, Any] | None, people: People, here: ZoneInfo | None = None) -> Blocker | None:
    """The blocker a hold names, or None for no hold, a hold with only words, or a blocker that no longer exists."""
    target = (hold or {}).get("on")
    kind = blocker_kind(target) if target else None
    if kind is None:
        return None
    record = view.get(kind, target)
    if record is None:
        return None
    if kind == "person":
        return Blocker("person", target, people.name(target))
    data = record.data
    if kind == "action":
        state = DONE if data["status"] in ("done", "dropped") else WAITING
        return Blocker("action", target, data["text"], state)
    asked = data.get("to")
    sent = _day(data.get("sent_at"), here)
    if data["status"] == "answered":
        return Blocker(
            "question",
            target,
            data["title"],
            ANSWERED,
            people.name(asked) if asked else None,
            sent,
            answered_on(view, target, here),
        )
    state = DONE if data["status"] == "dropped" else WAITING
    return Blocker("question", target, data["title"], state, people.name(asked) if asked else None, sent)


def standing_hold(
    view: Any, data: dict[str, Any], people: People | None = None, here: ZoneInfo | None = None
) -> dict[str, Any] | None:
    """The hold an action still stands under, or None. A hold whose blocker is over (an answered question, a finished or
    dropped action) no longer holds: the action is due, chased, reminded and offered again by its own dates. A hold with
    only words, or one whose blocker is gone, stands as written. Every line, list and packet that says "on hold" asks
    this, so they agree."""
    hold = data.get("on_hold")
    if not hold:
        return None
    found = blocker_of(view, hold, people if people is not None else ViewNames(view), here)
    return None if found is not None and found.resolved else hold


def blocker_problem(view: Any, action_id: str, on: str) -> str | None:
    """Why `on` can't be what an action is blocked on, or None: it must be an existing person, action or question, and
    not the action itself."""
    kind = blocker_kind(on)
    if kind is None:
        return "an action can be blocked on a person, an action or a question"
    if on == action_id:
        return "an action can't be blocked on itself"
    if view.get(kind, on) is None:
        return f"there is no {kind} {on}"
    return None


@dataclass
class BlockedCount:
    """How many open actions are blocked: in all, and by the project each belongs to (None for no project)."""

    total: int = 0
    by_project: dict[str | None, int] = field(default_factory=dict)


def blocked_actions(source: Any, people: People | None = None) -> BlockedCount:
    """The open actions whose hold names a blocker that still blocks, counted in all and by project. A hold with only
    words, and one whose blocker is gone, answered, finished or dropped, are not counted. `source` is a store or a
    view. Top priorities reads this."""
    view = source.read() if hasattr(source, "read") else source
    count = BlockedCount()
    if people is None:
        people = ViewNames(view)
    for stored in view.list("action"):
        data = stored.data
        if data.get("status") != "open":
            continue
        found = blocker_of(view, data.get("on_hold"), people)
        if found is None or found.resolved:
            continue
        count.total += 1
        project = data.get("project")
        count.by_project[project] = count.by_project.get(project, 0) + 1
    return count


class ViewNames:
    """Just enough of `People` to name a person from a view alone: for a count that never shows the name, and for the
    words a hold gets from its blocker."""

    def __init__(self, view: Any):
        self._view = view

    def name(self, person_id: str) -> str:
        found = self._view.get("person", person_id)
        return str(found.data.get("full_name", "")) if found is not None else ""
