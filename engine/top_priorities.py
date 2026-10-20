"""Top priorities (design 7.7): a short ranked list across every project, rebuilt from the records each time it is asked
for and ranked by rules, never by an AI call. Reads only.

What ranks, in this order (design 7.7): overdue (a dated to-do whose day has passed and that isn't marked done),
waiting on the person (a question for them to answer, a message to send, an action of theirs that holds up another),
due within the follow-up window (a to-do due that soon, and anything sent to a person that the follow-up rule says is
due a follow-up), at risk (to-dos of a project whose status means at risk). Ties go by the project's priority, then by
date. Something on hold is never due, never chased and never listed here as itself. A blocked action appears only as
its unblocking act: the question or action that holds it up, with how many it holds up, ranked by what it holds up
(overdue when something it holds up is). A hold that waits on the person themselves isn't blocked: it is their own
to-do and is listed as one. Only what the person can act on today is listed.

The person's own things are a line each. Everyone else is one line, however many things they hold ("send 1 question,
follow up on 3 waiting up to 5 days"), so a short list says the whole picture. The follow-up rule is the one the
Follow-ups screen and Today's nudge lines read (`engine.followups.follow_up_due`), through the same sections. The number
of lines and how far ahead the list after them looks are settings. Only the first lines are listed; the count of the
rest is given.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.blocked import blocked_actions, holds_up, standing_hold, waits_on_person
from engine.followups import sections
from engine.lists import projects_at_risk, value_rank
from engine.names import People
from engine.today import zone
from engine.today_queue import shared_project

#: The order things rank in, most pressing first.
RANKS = ("overdue", "waiting", "due_soon", "at_risk")


@dataclass
class Thing:
    """One thing inside a line: an `action` or `question` (its `id` and `text`), why it is there (`why`: overdue,
    due_soon, chase, send, answer, waiting or at_risk), its `due` day when it has one, for something sent how long it
    has waited, and `holds_up`, how many blocked actions it holds up."""

    kind: str
    id: str
    text: str
    why: str
    due: date | None = None
    waiting_days: int | None = None
    holds_up: int = 0


@dataclass
class Line:
    """One line of the list. `kind` is action or question (the person's own, one thing) or person (everything one other
    person holds, in `send`, `chase`, `overdue` and `due_soon` counts and `waiting_days`, the longest wait). `rank` is
    why it is listed, `holds_up` how many blocked actions it holds up, `on` the day it is about (its due day, or when
    the wait began), `days` how many days past that day it is (none when the day is ahead) and `things` every item in
    it, for the line's tooltip."""

    key: str
    rank: str
    kind: str
    person: str | None
    text: str
    project: str | None
    on: date
    due: date | None = None
    days: int | None = None
    action: str | None = None
    question: str | None = None
    holds_up: int = 0
    send: int = 0
    chase: int = 0
    overdue: int = 0
    due_soon: int = 0
    waiting_days: int | None = None
    things: list[Thing] = field(default_factory=list)
    #: The projects of its things, for the ranking by a project's priority; never shown.
    projects: list[str] = field(default_factory=list)


@dataclass
class Coming:
    """A dated to-do that falls due after today, within the configured days, and isn't already on a line."""

    action: str
    text: str
    due: date
    project: str | None
    owners: list[str]
    mine: bool


@dataclass
class TopPriorities:
    """The list: the first `lines` that rank, how many `more` rank beyond them, `blocked` (open actions waiting on a
    person, an action or a question that still blocks them) and `coming`, the dated to-dos of the next days."""

    lines: list[Line] = field(default_factory=list)
    more: int = 0
    blocked: int = 0
    coming: list[Coming] = field(default_factory=list)


def top_priorities(store: Any, cfg: Any, now: datetime) -> TopPriorities:
    """Top priorities as of `now`. Empty when the workspace doesn't say which person record is the person's own."""
    people = People(store, cfg)
    pm = people.pm
    if pm is None:
        return TopPriorities()
    reader = store.read()
    today = now.astimezone(zone(cfg)).date()
    window = cfg.ui.followups.action_due_within_days
    at_risk = set(projects_at_risk(reader))
    held_up = holds_up(reader, people)
    found: list[Line] = []

    def project_of(record_id: str) -> str | None:
        found_action = reader.get("action", record_id)
        return found_action.data.get("project") if found_action is not None else None

    def state(due: date | None, project: str | None) -> str | None:
        """Why a to-do that isn't on hold is listed, or None when it isn't."""
        if due is not None and due < today:
            return "overdue"
        if due is not None and (due - today).days <= window:
            return "due_soon"
        return "at_risk" if project in at_risk else None

    for section in sections(store, cfg, today):
        if section.is_pm:
            for a in section.actions:
                due = date.fromisoformat(str(a["due"])) if a.get("due") else None
                if a["on_hold"]:
                    # Blocked on a question or another action: the blocker is the act, never this. Waiting on the
                    # person themselves is their own to-do.
                    stored = reader.get("action", a["id"])
                    if stored is None or not waits_on_person(reader, stored.data.get("on_hold"), pm):
                        continue
                    if (a.get("blocker") or {}).get("kind") != "person":
                        continue
                    why = "waiting"
                else:
                    why = state(due, a["project"])
                    if why is None and held_up.get(a["id"]):
                        why = "waiting"  # it holds up other actions, so it is something the person does today
                    if why is None:
                        continue
                holding = len(held_up.get(a["id"], []))
                found.append(
                    Line(
                        key=f"action:{a['id']}",
                        rank=why,
                        kind="action",
                        person=pm,
                        text=a["text"],
                        project=a["project"],
                        on=due or today,
                        due=due,
                        days=(today - due).days if due and due <= today else None,
                        action=a["id"],
                        holds_up=holding,
                        things=[Thing("action", a["id"], a["text"], why, due, None, holding)],
                        projects=[a["project"]] if a["project"] else [],
                    )
                )
            continue
        # Someone else: everything they hold is one line, ranked by the most pressing of it.
        things: list[Thing] = []
        counts = {"overdue": 0, "due_soon": 0, "chase": 0}
        holding_overdue = 0
        waited: list[int] = []
        dates: list[date] = []
        for a in section.actions:
            if a["on_hold"]:
                continue
            due = date.fromisoformat(str(a["due"])) if a.get("due") else None
            if due is not None and due < today:
                counts["overdue"] += 1
                things.append(Thing("action", a["id"], a["text"], "overdue", due, a["told_days"]))
                dates.append(due)
            elif due is not None and (due - today).days <= window:
                counts["due_soon"] += 1
                things.append(Thing("action", a["id"], a["text"], "due_soon", due, a["told_days"]))
                dates.append(due)
            elif a["chase_due"]:
                counts["chase"] += 1
                things.append(Thing("action", a["id"], a["text"], "chase", due, a["told_days"], a["holds_up"]))
                holding_overdue += a["holds_overdue"]
            else:
                continue
            if a["told_days"] is not None:
                waited.append(a["told_days"])
        for q in section.questions:
            if q["chase_due"]:
                counts["chase"] += 1
                things.append(Thing("question", q["id"], q["title"], "chase", None, q["waiting_days"], q["holds_up"]))
                holding_overdue += q["holds_overdue"]
                waited.append(q["waiting_days"] or 0)
        # Something to send is what the Follow-ups screen counts to send for this person.
        send = section.to_send
        for q in section.questions:
            if q["status"] == "open":
                things.append(Thing("question", q["id"], q["title"], "send", None, None, q["holds_up"]))
        listed = {t.id for t in things}
        for a in section.actions:
            if a["told"] is None and a["id"] not in listed:
                things.append(Thing("action", a["id"], a["text"], "send", None))
        if not (counts["overdue"] or counts["due_soon"] or counts["chase"] or send):
            continue
        overdue_rank = counts["overdue"] or holding_overdue
        rank = "overdue" if overdue_rank else "due_soon" if counts["due_soon"] or counts["chase"] else "waiting"
        longest = max(waited) if waited else None
        began = min(dates) if dates else today - timedelta(days=longest or 0)
        question_ids = [t.id for t in things if t.kind == "question"]
        action_ids = [t.id for t in things if t.kind == "action"]
        found.append(
            Line(
                key=f"person:{section.person}",
                rank=rank,
                kind="person",
                person=section.person,
                text=section.name,
                project=shared_project(reader, question_ids, action_ids),
                on=began,
                due=min(dates) if dates else None,
                days=(today - began).days if began <= today else None,
                send=send,
                chase=counts["chase"],
                overdue=counts["overdue"],
                due_soon=counts["due_soon"],
                waiting_days=longest,
                holds_up=sum(t.holds_up for t in things),
                things=things,
                projects=sorted({p for p in (project_of(t.id) for t in things if t.kind == "action") if p}),
            )
        )

    # Waiting on the person: a question for them to answer.
    for q in reader.list("question"):
        d = q.data
        if d.get("to") != pm or d.get("status") != "open":
            continue
        entries = reader.ledger(kind="question", record_id=q.id)
        raised = _local_day(str(entries[0]["at"]), zone(cfg)) if entries else today
        project = (d.get("projects") or [None])[0]
        holding = len(held_up.get(q.id, []))
        found.append(
            Line(
                key=f"question:{q.id}",
                rank="waiting",
                kind="question",
                person=pm,
                text=d["title"],
                project=project,
                on=raised,
                days=(today - raised).days,
                question=q.id,
                holds_up=holding,
                things=[Thing("question", q.id, d["title"], "answer", None, (today - raised).days, holding)],
                projects=[project] if project else [],
            )
        )

    def order(line: Line) -> tuple[Any, ...]:
        priority = min(
            (value_rank(reader, "project-priority", _priority(reader, p)) for p in line.projects), default=99
        )
        return (RANKS.index(line.rank), priority, line.on, line.text.lower(), line.key)

    found.sort(key=order)
    limit = cfg.ui.today.top_priorities_lines
    shown = found[:limit]
    return TopPriorities(
        lines=shown,
        more=len(found) - len(shown),
        blocked=blocked_actions(store, people).total,
        coming=_coming(reader, cfg, people, today, {t.id for line in shown for t in line.things}),
    )


def _local_day(stamp: str, here: Any) -> date:
    """The day a stored time falls on, on the person's own clock."""
    at = datetime.fromisoformat(stamp)
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(here).date()


def _priority(reader: Any, project_id: str) -> str | None:
    found = reader.get("project", project_id)
    return found.data.get("priority") if found is not None else None


def _coming(reader: Any, cfg: Any, people: People, today: date, listed: set[str]) -> list[Coming]:
    """The dated, open to-dos that fall due after today and within the configured days, soonest first, leaving out
    what a line already holds and what is on hold."""
    ahead = cfg.ui.today.top_priorities_ahead_days
    if ahead <= 0:
        return []
    last = today + timedelta(days=ahead)
    found: list[Coming] = []
    for record in reader.list("action"):
        d = record.data
        if d.get("status") != "open" or not d.get("due") or record.id in listed or standing_hold(reader, d, people):
            continue
        due = date.fromisoformat(str(d["due"]))
        if not today < due <= last:
            continue
        owners = [o["person"] for o in d.get("owners") or [] if o.get("person")]
        found.append(
            Coming(record.id, d["text"], due, d.get("project"), owners, people.pm is not None and people.pm in owners)
        )
    return sorted(found, key=lambda c: (c.due, c.text.lower(), c.action))
