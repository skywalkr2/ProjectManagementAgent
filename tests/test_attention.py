from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.attention import DailyCap, QuietHours, Suggestion, admit


def now():
    return datetime(2027, 1, 5, 12, tzinfo=UTC)


def suggestion(kind="follow_up", importance=5, key="draft-2"):
    return Suggestion(kind, importance, key)


def cap(limit=3, shown=()):
    return DailyCap(limit, date(2027, 1, 5), shown)


def test_show():
    result = admit((suggestion(),), now(), UTC, cap(), None, 3, {})
    assert result[0].disposition == "shown_now"
    assert result[0].index == 0


def test_below_threshold():
    result = admit((suggestion(importance=2),), now(), UTC, cap(), None, 3, {})
    assert result[0].disposition == "held_back"
    assert result[0].reason_code == "below_threshold"


def test_threshold_inclusive():
    assert admit((suggestion(importance=3),), now(), UTC, cap(), None, 3, {})[0].disposition == "shown_now"


def test_highest_importance_first_and_output_input_order():
    items = (suggestion("a", 3), suggestion("b", 9), suggestion("c", 5))
    results = admit(items, now(), UTC, cap(1), None, 3, {})
    assert [item.disposition for item in results] == ["saved_for_digest", "shown_now", "saved_for_digest"]
    assert tuple(item.suggestion for item in results) == items


def test_equal_importance_stable():
    items = (suggestion("a"), suggestion("b"))
    results = admit(items, now(), UTC, cap(1), None, 3, {})
    assert results[0].disposition == "shown_now"
    assert results[1].reason_code == "daily_cap"


@pytest.mark.parametrize("limit", [0, 1, 2])
def test_existing_history_uses_allowance(limit):
    results = admit((suggestion(),), now(), UTC, cap(limit, (now(), now())), None, 3, {})
    assert results[0].reason_code == "daily_cap"


def test_old_history_does_not_count():
    result = admit((suggestion(),), now(), UTC, cap(1, (now() - timedelta(days=1),)), None, 3, {})
    assert result[0].disposition == "shown_now"


def test_future_history_unknown():
    result = admit((suggestion(),), now(), UTC, cap(1, (now() + timedelta(seconds=1),)), None, 3, {})
    assert result[0].reason_code == "unknown"


def test_dismissal_until_changed():
    dismissed = {"follow_up": "draft-2"}
    items = (suggestion(key="draft-2"), suggestion(key="draft-3"))
    results = admit(items, now(), UTC, cap(), None, 3, dismissed)
    assert results[0].reason_code == "dismissed_unchanged"
    assert results[1].disposition == "shown_now"
    assert dismissed == {"follow_up": "draft-2"}


def test_dismissal_does_not_expire_with_time_or_importance():
    later = now() + timedelta(days=100)
    results = admit(
        (suggestion(importance=100),), later, UTC, DailyCap(3, later.date(), ()), None, 3, {"follow_up": "draft-2"}
    )
    assert results[0].reason_code == "dismissed_unchanged"


def test_other_kind_not_suppressed():
    result = admit((suggestion("renewal"),), now(), UTC, cap(), None, 3, {"follow_up": "draft-2"})
    assert result[0].disposition == "shown_now"


@pytest.mark.parametrize(
    "hour,expected",
    [(21, "shown_now"), (22, "saved_for_digest"), (0, "saved_for_digest"), (7, "saved_for_digest"), (8, "shown_now")],
)
def test_overnight_quiet(hour, expected):
    instant = now().replace(hour=hour)
    result = admit((suggestion(),), instant, UTC, cap(), QuietHours(time(22), time(8)), 3, {})
    assert result[0].disposition == expected


def test_same_day_quiet():
    result = admit((suggestion(),), now(), UTC, cap(), QuietHours(time(12), time(13)), 3, {})
    assert result[0].reason_code == "quiet_hours"


def test_dismissed_and_low_importance_do_not_enter_digest():
    result = admit(
        (suggestion(), suggestion("renewal", 1)),
        now(),
        UTC,
        cap(),
        QuietHours(time(11), time(13)),
        3,
        {"follow_up": "draft-2"},
    )
    assert all(item.disposition == "held_back" for item in result)


def test_invalid_item_does_not_use_cap():
    result = admit((suggestion(key=""), suggestion("renewal")), now(), UTC, cap(1), None, 3, {})
    assert result[0].reason_code == "unknown"
    assert result[1].disposition == "shown_now"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "high"])
def test_invalid_importance(value):
    assert admit((suggestion(importance=value),), now(), UTC, cap(), None, 3, {})[0].reason_code == "unknown"


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_invalid_limit(value):
    assert admit((suggestion(),), now(), UTC, cap(value), None, 3, {})[0].reason_code == "unknown"


def test_bare_cap_does_not_assume_empty_history():
    assert admit((suggestion(),), now(), UTC, 3, None, 3, {})[0].reason_code == "unknown"


def test_stale_history_unknown():
    result = admit((suggestion(),), now(), UTC, DailyCap(3, date(2027, 1, 4), ()), None, 3, {})
    assert result[0].reason_code == "unknown"


def test_local_midnight_and_history_dates():
    zone = ZoneInfo("America/New_York")
    instant = datetime(2027, 1, 6, 1, tzinfo=UTC)
    history = (datetime(2027, 1, 5, 23, tzinfo=UTC),)
    result = admit((suggestion(),), instant, zone, DailyCap(1, date(2027, 1, 5), history), None, 3, {})
    assert result[0].reason_code == "daily_cap"


@pytest.mark.parametrize("fold", [0, 1])
def test_both_repeated_hours_are_quiet(fold):
    zone = ZoneInfo("America/New_York")
    instant = datetime(2027, 11, 7, 1, 30, tzinfo=zone, fold=fold)
    result = admit(
        (suggestion(),), instant, zone, DailyCap(3, instant.date(), ()), QuietHours(time(22), time(8)), 3, {}
    )
    assert result[0].reason_code == "quiet_hours"


def test_nonexistent_now_unknown():
    instant = datetime(2027, 3, 14, 2, 30, tzinfo=ZoneInfo("America/New_York"))
    result = admit((suggestion(),), instant, UTC, DailyCap(3, date(2027, 3, 14), ()), None, 3, {})
    assert result[0].reason_code == "unknown"


def test_equal_quiet_boundaries_unknown():
    assert admit((suggestion(),), now(), UTC, cap(), QuietHours(time(8), time(8)), 3, {})[0].reason_code == "unknown"


def test_bad_dismissal_unknown():
    assert admit((suggestion(),), now(), UTC, cap(), None, 3, {"follow_up": ""})[0].reason_code == "unknown"


def test_empty():
    assert admit((), now(), UTC, cap(), None, 3, {}) == ()


def test_deterministic_and_frozen():
    items = (suggestion(),)
    first = admit(items, now(), UTC, cap(), None, 3, {})
    assert admit(items, now(), UTC, cap(), None, 3, {}) == first
    with pytest.raises(FrozenInstanceError):
        first[0].disposition = "held_back"


def test_naive_now_unknown():
    instant = datetime(2027, 1, 5, 12)  # noqa: DTZ001 -- Verify rejection of a floating now.
    assert admit((suggestion(),), instant, UTC, cap(), None, 3, {})[0].reason_code == "unknown"


def test_bad_threshold_unknown():
    assert admit((suggestion(),), now(), UTC, cap(), None, float("nan"), {})[0].reason_code == "unknown"


def test_large_integer_importance_does_not_overflow():
    result = admit((suggestion(importance=10**1000),), now(), UTC, cap(), None, 3, {})
    assert result[0].disposition == "shown_now"


def test_daily_reset_requires_new_explicit_snapshot():
    tomorrow = now() + timedelta(days=1)
    result = admit((suggestion(),), tomorrow, UTC, DailyCap(1, tomorrow.date(), (now(),)), None, 3, {})
    assert result[0].disposition == "shown_now"


def test_kind_and_change_key_match_exactly():
    result = admit((suggestion("Follow_up"),), now(), UTC, cap(), None, 3, {"follow_up": "draft-2"})
    assert result[0].disposition == "shown_now"


def test_dismissals_of_one_kind_about_different_things_all_stick():
    oren = Suggestion("follow_up", 5, "draft-2", subject="promise-oren")
    mira = Suggestion("follow_up", 5, "draft-7", subject="promise-mira")
    dismissed = {("follow_up", "promise-oren"): "draft-2", ("follow_up", "promise-mira"): "draft-7"}
    results = admit((oren, mira), now(), UTC, cap(), None, 3, dismissed)
    assert [item.reason_code for item in results] == ["dismissed_unchanged", "dismissed_unchanged"]
    changed = Suggestion("follow_up", 5, "draft-3", subject="promise-oren")
    assert admit((changed,), now(), UTC, cap(), None, 3, dismissed)[0].disposition == "shown_now"
