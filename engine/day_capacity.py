"""Does the rest of today hold the to-dos due today? The capacity check (design 6.32), by rules and never AI.

The free time left today comes from the calendars (`engine.free_slots`, inside the working hours and days of
`steward.reminders`, with `steward.capacity` for the buffer around meetings and whether a tentative one is free). It is
set against the effort of the person's own open to-dos that are due today or late and not on hold; a to-do with no
effort counts as no time. When there is more than the day holds, `engine.capacity` proposes which whole to-dos to move,
and the next working day is offered as where. Nothing is moved here: the person moves each one, or none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from engine import capacity as capacity_rules
from engine.day_calendar import timed
from engine.free_slots import Busy, free_slots
from engine.lists import value_rank
from engine.reminder_lines import rules
from engine.today import todo as todays_todos
from engine.today import zone


@dataclass
class Move:
    """A to-do proposed to move out of today: its words, its effort, whether it was promised to someone, where its
    date stands (none, overdue, today or later), the version the person's edit states it read and its own date."""

    action: str
    text: str
    minutes: int
    promised: bool
    due: date | None
    due_state: str
    version: int


@dataclass
class DayCapacity:
    """The check as of a moment: the free minutes left today, the effort due today, how far over that is, what is
    proposed to move (`moves`), how much would still be over once those moved (`still_over`: the rest is fixed to a
    meeting) and the day to offer for each (`next_day`, the next working day)."""

    free_minutes: int
    needed_minutes: int
    over_minutes: int
    still_over: int
    next_day: date
    moves: list[Move] = field(default_factory=list)


def next_workday(cfg: Any, today: date) -> date:
    """The next working day after `today`, in the person's working week."""
    days = rules(cfg).working.days
    found = today + timedelta(days=1)
    for _ in range(7):
        if found.weekday() in days:
            return found
        found += timedelta(days=1)
    return today + timedelta(days=1)


def free_minutes(store: Any, cfg: Any, now: datetime) -> int | None:
    """The working minutes left today that no meeting takes, or None when there are none to count: today isn't a working
    day, or the working day is over."""
    here = zone(cfg)
    local = now.astimezone(here)
    today = local.date()
    working = rules(cfg).working
    if today.weekday() not in working.days:
        return None
    end = datetime.combine(today, working.end, here)
    if local >= end:
        return None
    settings = cfg.steward.capacity
    busy = [
        Busy(t.start, t.end, "tentative" if t.tentative else "busy")
        for t in timed(store, cfg, now, through=today + timedelta(days=1))
    ]
    found = free_slots(
        busy,
        working.start,
        working.end,
        working.days,
        here,
        buffer_minutes=settings.buffer_minutes,
        window_start=now,
        window_end=datetime.combine(today + timedelta(days=1), time(), here),
        tentative_as_free=settings.tentative_is_free,
    )
    return int(round(found.free_minutes.get(today, 0)))


def check(store: Any, cfg: Any, now: datetime) -> DayCapacity | None:
    """The day's capacity as of `now`, or None when the person's own record isn't set, the day has no time left to count
    or the to-dos with an effort fit what is free. A to-do tied to a meeting is fixed and never proposed."""
    me = cfg.workspace.user.person
    if not me:
        return None
    free = free_minutes(store, cfg, now)
    if free is None:
        return None
    here = zone(cfg)
    today = now.astimezone(here).date()
    view = store.read()
    todos = []
    kept = {}
    for item in todays_todos(store, cfg, now):
        if item.on_hold or item.due is None or item.due_check or item.due > today:
            continue
        found = view.get("action", item.action)
        minutes = found.data.get("effort_minutes") if found is not None else None
        if not minutes:
            continue
        kept[item.action] = found
        rank = value_rank(view, "project-priority", _priority(view, found.data.get("project")))
        todos.append(
            capacity_rules.Todo(
                item.action,
                item.text,
                int(minutes),
                # A larger number matters more: the first value of the priority list is the most important.
                100 - rank,
                item.due,
                promised=bool(found.data.get("promised_to")),
                fixed=bool(found.data.get("due_event")),
            )
        )
    plan = capacity_rules.plan_day(todos, free, now.astimezone(here))
    if plan.status != "known" or not plan.over_minutes:
        return None
    moves = [
        Move(
            m.todo_id,
            kept[m.todo_id].data["text"],
            m.minutes,
            m.promised,
            m.due,
            m.due_state,
            kept[m.todo_id].version,
        )
        for m in plan.moves
    ]
    return DayCapacity(
        free,
        plan.total_minutes or 0,
        plan.over_minutes,
        plan.remaining_over_minutes or 0,
        next_workday(cfg, today),
        moves,
    )


def _priority(view: Any, project: str | None) -> str | None:
    found = view.get("project", project) if project else None
    return found.data.get("priority") if found is not None else None
