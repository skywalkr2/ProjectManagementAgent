"""Propose moving work out of a day without changing any task."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class Todo:
    id: str
    title: str
    estimate_minutes: int
    priority: int
    due: date | None = None
    promised: bool = False
    fixed: bool = False


@dataclass(frozen=True)
class Move:
    todo_id: str
    minutes: int
    reason: str


@dataclass(frozen=True)
class DayPlan:
    status: str
    total_minutes: int | None
    over_minutes: int | None
    remaining_over_minutes: int | None
    moves: tuple[Move, ...]
    reason: str


def plan_day(todos: Sequence[Todo], free_minutes: int, now: datetime) -> DayPlan:
    """Propose whole-task moves until the day's work fits, retaining fixed tasks."""
    entries = tuple(todos)

    def unknown(reason: str) -> DayPlan:
        return DayPlan("unknown", None, None, None, (), reason)

    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return unknown("Supply an aware datetime for now.")
    if now.astimezone(UTC).astimezone(now.tzinfo).replace(tzinfo=None) != now.replace(tzinfo=None):
        return unknown("Now falls in a nonexistent local time.")
    if type(free_minutes) is not int or free_minutes < 0:
        return unknown("Free minutes must be a nonnegative whole number.")
    seen = set()
    for todo in entries:
        if not isinstance(todo, Todo):
            return unknown("Each to-do must include its estimate, priority, and flags.")
        if not isinstance(todo.id, str) or not todo.id.strip() or todo.id in seen:
            return unknown("Each to-do needs a nonempty, unique ID.")
        seen.add(todo.id)
        if not isinstance(todo.title, str) or not todo.title.strip():
            return unknown("Each to-do needs a title.")
        if type(todo.estimate_minutes) is not int or todo.estimate_minutes < 0:
            return unknown("Every to-do needs a nonnegative whole-minute estimate.")
        if type(todo.priority) is not int:
            return unknown("Every to-do needs an integer priority; higher numbers mean higher priority.")
        if todo.due is not None and type(todo.due) is not date:
            return unknown("A due date must be a date or explicitly absent.")
        if type(todo.promised) is not bool or type(todo.fixed) is not bool:
            return unknown("Promised and fixed flags must be explicit booleans.")

    total = sum(todo.estimate_minutes for todo in entries)
    over = max(0, total - free_minutes)
    if not over:
        return DayPlan("known", total, 0, 0, (), "The to-dos fit within the supplied free minutes.")

    today = now.date()

    def rank(todo: Todo) -> tuple[bool, int, bool, bool, int]:
        # Due today or overdue is proposed last; missing dates form an explicit category, not an inferred deadline.
        return (
            todo.due is not None and todo.due <= today,
            todo.priority,
            todo.promised,
            todo.due is not None,
            -todo.due.toordinal() if todo.due is not None else 0,
        )

    candidates = sorted(
        (todo for todo in entries if not todo.fixed and todo.estimate_minutes > 0),
        key=rank,
    )
    remaining = over
    moves = []
    for todo in candidates:
        if remaining <= 0:
            break
        parts = [f"Moving this to-do would free {todo.estimate_minutes} minutes."]
        if todo.promised:
            parts.append("You promised it to someone; review that promise before agreeing to move it.")
        else:
            parts.append("You haven't marked it as promised to someone.")
        if todo.due is None:
            parts.append("It has no stated due date.")
        elif todo.due < today:
            parts.append(
                f"It was due {todo.due.isoformat()}; moving it would leave an overdue promise or task unresolved."
            )
        elif todo.due == today:
            parts.append("It is due today; check the deadline before agreeing to move it.")
        else:
            parts.append(f"It is due {todo.due.isoformat()}.")
        parts.append("It comes next under the priority, promise, and due-date order.")
        moves.append(Move(todo.id, todo.estimate_minutes, " ".join(parts)))
        remaining = max(0, remaining - todo.estimate_minutes)
    # Drop any earlier move a later, larger one made unnecessary, checking the most important first.
    if remaining == 0:
        freed = sum(move.minutes for move in moves)
        for move in reversed(moves[:-1]):
            if freed - move.minutes >= over:
                moves.remove(move)
                freed -= move.minutes
    reason = (
        "These proposed moves would make the remaining work fit. No to-do has been changed."
        if remaining == 0
        else "The day would still be overbooked because fixed to-dos cannot be moved. No to-do has been changed."
    )
    return DayPlan("known", total, over, remaining, tuple(moves), reason)
