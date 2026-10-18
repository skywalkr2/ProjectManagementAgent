from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine.capacity import Todo, plan_day


def now():
    return datetime(2027, 1, 5, 10, tzinfo=UTC)


def todo(identifier="outline", minutes=30, priority=1, due=None, promised=False, fixed=False):
    return Todo(identifier, "Prepare an outline", minutes, priority, due, promised, fixed)


def moved(plan):
    return tuple(move.todo_id for move in plan.moves)


def test_fits():
    result = plan_day((todo(),), 45, now())
    assert result.status == "known"
    assert result.total_minutes == 30
    assert result.over_minutes == result.remaining_over_minutes == 0
    assert not result.moves


def test_exact_fit():
    assert not plan_day((todo(),), 30, now()).moves


def test_empty():
    result = plan_day((), 0, now())
    assert result.total_minutes == result.over_minutes == 0


def test_overage_and_whole_task_move():
    result = plan_day((todo(), todo("review", 45, 5)), 60, now())
    assert result.total_minutes == 75
    assert result.over_minutes == 15
    assert result.remaining_over_minutes == 0
    assert moved(result) == ("outline",)
    assert result.moves[0].minutes == 30
    assert result.moves[0].due_state == "none"


def test_lowest_priority_first():
    items = (todo("high", priority=8), todo("low", priority=1), todo("middle", priority=4))
    assert moved(plan_day(items, 60, now())) == ("low",)


def test_unpromised_first_at_equal_priority():
    items = (todo("promise", due=date(2027, 12, 1), promised=True), todo("other", due=date(2027, 1, 6)))
    assert moved(plan_day(items, 30, now())) == ("other",)


def test_latest_due_first_at_equal_priority_and_promise_status():
    items = (todo("soon", due=date(2027, 1, 6)), todo("later", due=date(2027, 2, 1)))
    assert moved(plan_day(items, 30, now())) == ("later",)


def test_no_due_date_is_explicit_first_category():
    items = (todo("dated", due=date(2027, 12, 1)), todo("undated"))
    assert moved(plan_day(items, 30, now())) == ("undated",)
    assert plan_day(items, 30, now()).moves[0].due_state == "none"


def test_stable_ties():
    assert moved(plan_day((todo("first"), todo("second")), 30, now())) == ("first",)


def test_priority_precedes_promise_flag():
    items = (todo("low", priority=1, promised=True), todo("high", priority=5))
    result = plan_day(items, 30, now())
    assert moved(result) == ("low",)
    assert result.moves[0].promised


def test_fixed_never_moved():
    items = (todo("fixed", minutes=80, priority=0, fixed=True), todo("other", minutes=20, priority=9))
    result = plan_day(items, 50, now())
    assert moved(result) == ("other",)
    assert result.over_minutes == 50
    assert result.remaining_over_minutes == 30
    assert result.reason == "still_over_fixed"


def test_all_fixed():
    result = plan_day((todo(fixed=True),), 0, now())
    assert not result.moves
    assert result.remaining_over_minutes == 30


def test_zero_estimate_not_pointlessly_moved():
    result = plan_day((todo("zero", 0), todo("actual", 30)), 0, now())
    assert moved(result) == ("actual",)


def test_move_several():
    result = plan_day((todo("a"), todo("b"), todo("c")), 10, now())
    assert moved(result) == ("a", "b", "c")
    assert result.over_minutes == 80 and result.remaining_over_minutes == 0


@pytest.mark.parametrize(
    "due,state", [(date(2027, 1, 4), "overdue"), (date(2027, 1, 5), "today"), (date(2027, 2, 1), "later")]
)
def test_deadline_warning(due, state):
    move = plan_day((todo(due=due),), 0, now()).moves[0]
    assert (move.due_state, move.due) == (state, due)


def test_local_date_controls_due_today():
    local = datetime(2027, 1, 4, 23, tzinfo=ZoneInfo("America/New_York"))
    result = plan_day((todo(due=date(2027, 1, 4)),), 0, local)
    assert result.moves[0].due_state == "today"


@pytest.mark.parametrize("free", [-1, 1.5, True, None])
def test_invalid_free_minutes(free):
    result = plan_day((todo(),), free, now())
    assert result.status == "unknown" and result.over_minutes is None
    assert result.reason and not result.moves


@pytest.mark.parametrize("minutes", [-1, 1.5, True, None])
def test_invalid_estimate(minutes):
    assert plan_day((todo(minutes=minutes),), 0, now()).status == "unknown"


@pytest.mark.parametrize("priority", [None, True, 1.5, "high"])
def test_invalid_priority(priority):
    assert plan_day((todo(priority=priority),), 0, now()).status == "unknown"


def test_duplicate_ids_unknown():
    assert plan_day((todo(), todo()), 0, now()).status == "unknown"


def test_naive_now_unknown():
    instant = datetime(2027, 1, 5)  # noqa: DTZ001 -- A floating now must be rejected.
    assert plan_day((todo(),), 0, instant).status == "unknown"


def test_gap_now_unknown():
    instant = datetime(2027, 3, 14, 2, 30, tzinfo=ZoneInfo("America/New_York"))
    assert plan_day((todo(),), 0, instant).status == "unknown"


def test_datetime_is_not_a_due_date():
    assert plan_day((todo(due=now()),), 0, now()).status == "unknown"


@pytest.mark.parametrize("field", ["promised", "fixed"])
def test_flags_not_inferred(field):
    assert plan_day((todo(**{field: None}),), 0, now()).status == "unknown"


def test_deterministic_no_mutation():
    items = [todo("a"), todo("b")]
    before = items.copy()
    first = plan_day(items, 30, now())
    assert items == before
    assert plan_day(items, 30, now()) == first
    with pytest.raises(FrozenInstanceError):
        first.moves[0].minutes = 0


def test_year_end_order():
    items = (todo("december", due=date(2027, 12, 31)), todo("january", due=date(2028, 1, 1)))
    assert moved(plan_day(items, 30, now())) == ("january",)


def test_due_today_and_overdue_are_proposed_last():
    items = (
        todo("today", priority=1, due=date(2027, 1, 5)),
        todo("late", priority=1, due=date(2027, 1, 3)),
        todo("next-month", priority=3, due=date(2027, 2, 5)),
    )
    assert moved(plan_day(items, 60, now())) == ("next-month",)


def test_small_moves_made_unnecessary_by_a_larger_one_are_dropped():
    items = (todo("a", 10, 1), todo("b", 10, 1), todo("big", 120, 2), todo("keep", 30, 9))
    result = plan_day(items, 100, now())
    assert result.over_minutes == 70
    assert moved(result) == ("big",)
    assert result.remaining_over_minutes == 0


def test_reasons_are_codes_not_sentences():
    over = plan_day((todo("a", 60), todo("b", 30, 5)), 30, now())
    assert over.reason == "fits_after_moves" and plan_day((todo(),), 60, now()).reason == "fits"
    assert plan_day((todo(minutes=-1),), 0, now()).reason == "bad_estimate"
