"""Blocked actions (design 6.9, "On hold"): an action on hold that names its blocker, a person, an action or a question.

Blocked is not a second state. The hold is the state; `OnHold.on` says what it waits on, and this module reads that: who
or what the blocker is by name, whether it still blocks, and how many actions are blocked, by project and in all (the
count Top priorities reads). A hold with only words is on hold, never blocked. A hold that waits on the person
themselves (a question for them, an action of theirs, themselves named) isn't blocked either: it is their own to-do.
The chase of a blocked action moves to its blocker, so `holds_up` says which questions and actions hold up which
actions. Reads only.
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
    view: Any,
    data: dict[str, Any],
    people: People | None = None,
    here: ZoneInfo | None = None,
    pm: str | None = None,
) -> dict[str, Any] | None:
    """The hold an action still stands under, or None. A hold whose blocker is over (an answered question, a finished or
    dropped action) no longer holds: the action is due, chased, reminded and offered again by its own dates. A hold on
    the person's own action that waits on the person themselves (`people` or `pm` says who they are) isn't blocked
    anywhere: it is their own to-do, so it doesn't stand either. A hold with only words, or one whose blocker is gone,
    stands as written. Every line, list and packet that says "on hold" asks this, so they agree."""
    hold = data.get("on_hold")
    if not hold:
        return None
    if own_wait(view, data, pm or getattr(people, "pm", None)):
        return None
    found = blocker_of(view, hold, people if people is not None else ViewNames(view), here)
    return None if found is not None and found.resolved else hold


def owed_by(view: Any, target: str | None) -> tuple[str, ...]:
    """The people a blocker waits on: the person named, whoever owns the action, or whoever the question was asked of.
    Empty for a blocker that is gone."""
    kind = blocker_kind(target) if target else None
    record = view.get(kind, target) if kind is not None and target else None
    if record is None:
        return ()
    if kind == "person":
        return (str(target),)
    if kind == "action":
        return tuple(o["person"] for o in record.data.get("owners") or [] if o.get("person"))
    return (record.data["to"],) if record.data.get("to") else ()


def waits_on_person(view: Any, hold: dict[str, Any] | None, pm: str | None) -> bool:
    """Whether a hold that names its blocker waits on the person themselves: they are the person named, the one the
    question was asked of, or an owner of the action. Such a hold isn't blocked: it is the person's own to-do."""
    target = (hold or {}).get("on")
    return bool(pm) and pm in owed_by(view, target)


def own_wait(view: Any, data: dict[str, Any], pm: str | None) -> bool:
    """Whether an action is the person's own and its hold waits on the person themselves (they are the person named,
    the one a question was asked of, or an owner of the action it waits on). That isn't blocked: it is their own to-do,
    by its own dates. An action someone else owns that waits on the person stays on hold: it is theirs to wait for."""
    owners = [o.get("person") for o in data.get("owners") or []]
    return bool(pm) and pm in owners and waits_on_person(view, data.get("on_hold"), pm)


def holds_up(view: Any, people: People | None = None) -> dict[str, list[str]]:
    """The open actions each question and action still holds up, by the blocker's id: every open action whose hold names
    that question or action and whose blocker hasn't ended. A person as a blocker isn't listed (it has no chase of its
    own), and neither is a blocker that is over. The one reading of "what it holds up" that the chase, the Follow-ups
    rows and Top priorities share."""
    found: dict[str, list[str]] = {}
    names = people if people is not None else ViewNames(view)
    for stored in view.list("action"):
        data = stored.data
        if data.get("status") != "open":
            continue
        hold = data.get("on_hold") or {}
        target = hold.get("on")
        if not target or blocker_kind(target) not in ("question", "action"):
            continue
        blocker = blocker_of(view, hold, names)
        if blocker is None or blocker.resolved:
            continue
        found.setdefault(str(target), []).append(stored.id)
    return found


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
    words, one whose blocker is gone, answered, finished or dropped, and one that waits on the person themselves are not
    counted (`people` says who the person is). `source` is a store or a view. Top priorities reads this."""
    view = source.read() if hasattr(source, "read") else source
    count = BlockedCount()
    if people is None:
        people = ViewNames(view)
    pm = getattr(people, "pm", None)
    for stored in view.list("action"):
        data = stored.data
        if data.get("status") != "open":
            continue
        found = blocker_of(view, data.get("on_hold"), people)
        if found is None or found.resolved or waits_on_person(view, data.get("on_hold"), pm):
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
