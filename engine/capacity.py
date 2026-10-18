"""Propose moving work out of a day without changing any task.

Results are data the screen words from the wording sheet: a move says whether the to-do was promised and where its
due date stands (none, overdue, today or later), and the plan's `reason` is a code.
"""

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
    promised: bool
    due: date | None
    due_state: str  # none, overdue, today or later


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
        return unknown("no_zone")
    if now.astimezone(UTC).astimezone(now.tzinfo).replace(tzinfo=None) != now.replace(tzinfo=None):
        return unknown("time_does_not_exist")
    if type(free_minutes) is not int or free_minutes < 0:
        return unknown("bad_free_minutes")
    seen = set()
    for todo in entries:
        if not isinstance(todo, Todo):
            return unknown("bad_todo")
        if not isinstance(todo.id, str) or not todo.id.strip() or todo.id in seen:
            return unknown("bad_id")
        seen.add(todo.id)
        if not isinstance(todo.title, str) or not todo.title.strip():
            return unknown("no_title")
        if type(todo.estimate_minutes) is not int or todo.estimate_minutes < 0:
            return unknown("bad_estimate")
        if type(todo.priority) is not int:
            return unknown("bad_priority")
        if todo.due is not None and type(todo.due) is not date:
            return unknown("bad_due")
        if type(todo.promised) is not bool or type(todo.fixed) is not bool:
            return unknown("bad_flags")

    total = sum(todo.estimate_minutes for todo in entries)
    over = max(0, total - free_minutes)
    if not over:
        return DayPlan("known", total, 0, 0, (), "fits")

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
        if todo.due is None:
            due_state = "none"
        else:
            due_state = "overdue" if todo.due < today else "today" if todo.due == today else "later"
        moves.append(Move(todo.id, todo.estimate_minutes, todo.promised, todo.due, due_state))
        remaining = max(0, remaining - todo.estimate_minutes)
    # Drop any earlier move a later, larger one made unnecessary, checking the most important first.
    if remaining == 0:
        freed = sum(move.minutes for move in moves)
        for move in reversed(moves[:-1]):
            if freed - move.minutes >= over:
                moves.remove(move)
                freed -= move.minutes
    reason = "fits_after_moves" if remaining == 0 else "still_over_fixed"
    return DayPlan("known", total, over, remaining, tuple(moves), reason)
