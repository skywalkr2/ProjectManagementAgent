"""Repeat phrases to rules and rules to shapes, with month-end days that never skip a short month."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine.recurrence import occurrences
from engine.repeat_phrases import Shape, Unknown, rule_from_phrase, rule_shape


def phrase_of(shape):
    """The grammar's own phrase for a shape, so a round trip can be checked; screens word shapes themselves."""
    values = shape.values
    if shape.kind == "daily":
        return "every day" if values["interval"] == 1 else f"every {values['interval']} days"
    if shape.kind == "weekdays":
        return "weekdays"
    if shape.kind == "weekly":
        n = values["interval"]
        return f"every {values['weekday']}" if n == 1 else f"every {n} weeks on {values['weekday']}"
    if shape.kind == "monthly_day":
        n = values["interval"]
        return f"every {'month' if n == 1 else f'{n} months'} on the {values['day']}"
    if shape.kind == "monthly_nth":
        return f"the {values['ordinal']} {values['weekday']} of each month"
    return f"yearly on {values['month']} {values['day']}"


def describe_rule(rule, start):
    shape = rule_shape(rule, start)
    return phrase_of(shape) if isinstance(shape, Shape) else shape


@pytest.mark.parametrize(
    "phrase,start,rule",
    [
        ("every other Tuesday", date(2027, 1, 5), "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"),
        ("the first Monday of each month", date(2027, 1, 4), "FREQ=MONTHLY;BYDAY=1MO"),
        ("weekdays", date(2027, 1, 5), "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("every 3 months on the 15th", date(2027, 1, 15), "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=15"),
        ("yearly on March 3", date(2027, 3, 3), "FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=3"),
        ("daily", date(2027, 1, 5), "FREQ=DAILY"),
        ("every 3 days", date(2027, 1, 5), "FREQ=DAILY;INTERVAL=3"),
        ("every Friday", date(2027, 1, 8), "FREQ=WEEKLY;BYDAY=FR"),
        ("every 3 weeks on Tuesday", date(2027, 1, 5), "FREQ=WEEKLY;INTERVAL=3;BYDAY=TU"),
        ("the last Friday of each month", date(2027, 1, 29), "FREQ=MONTHLY;BYDAY=-1FR"),
        ("the fifth Monday of each month", date(2027, 3, 29), "FREQ=MONTHLY;BYDAY=5MO"),
        ("every month on the 31st", date(2027, 1, 31), "FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1"),
        ("yearly on February 29", date(2028, 2, 29), "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=28,29;BYSETPOS=-1"),
        ("weekly", date(2027, 1, 5), "FREQ=WEEKLY;BYDAY=TU"),
        ("monthly", date(2027, 1, 5), "FREQ=MONTHLY;BYMONTHDAY=5"),
        ("yearly", date(2027, 1, 5), "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=5"),
    ],
)
def test_phrase_round_trip(phrase, start, rule):
    assert rule_from_phrase(phrase, start) == rule
    description = describe_rule(rule, start)
    assert isinstance(description, str)
    assert rule_from_phrase(description, start) == rule


@pytest.mark.parametrize(
    "rule,start",
    [
        ("FREQ=DAILY;INTERVAL=1", date(2027, 1, 5)),
        ("RRULE:FREQ=WEEKLY;BYDAY=TU;INTERVAL=2;WKST=MO", date(2027, 1, 5)),
        ("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1", date(2027, 1, 4)),
        ("FREQ=WEEKLY;BYDAY=FR,TH,WE,TU,MO", date(2027, 1, 5)),
        ("FREQ=MONTHLY", date(2027, 1, 5)),
        ("FREQ=YEARLY", date(2027, 1, 5)),
    ],
)
def test_canonical_semantic_round_trip(rule, start):
    description = describe_rule(rule, start)
    assert isinstance(description, str)
    canonical = rule_from_phrase(description, start)
    assert isinstance(canonical, str)
    assert describe_rule(canonical, start) == description


@pytest.mark.parametrize(
    "phrase",
    [
        "sometimes",
        "after approval",
        "every other week",
        "next Tuesday",
        "every 0 months on the 15th",
        "every month on the 32nd",
        "yearly on February 30",
        "every month on the 15st",
        "yearly on March 3th",
        "every 0 days",
        "",
    ],
)
def test_unknown_phrase(phrase):
    result = rule_from_phrase(phrase, date(2027, 1, 15))
    assert isinstance(result, Unknown) and result.status == "unknown" and result.reason


@pytest.mark.parametrize(
    "rule",
    [
        "",
        "FREQ=HOURLY",
        "FREQ=DAILY;COUNT=5",
        "FREQ=DAILY;UNTIL=20280101",
        "FREQ=DAILY;FREQ=WEEKLY",
        "FREQ=DAILY;INTERVAL=0",
        "FREQ=DAILY;INTERVAL=-1",
        "FREQ=WEEKLY;BYDAY=MO,FR",
        "FREQ=WEEKLY;WKST=SU",
        "FREQ=MONTHLY;BYMONTHDAY=-1",
        "FREQ=YEARLY;BYMONTH=13",
        "FREQ=DAILY;BYHOUR=9",
        "FREQ=MONTHLY;BYSETPOS=1",
        "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=6",
        "FREQ=DAILY;",
        "FREQ=DAILY;INTERVAL=x",
    ],
)
def test_unknown_rule(rule):
    result = describe_rule(rule, date(2027, 1, 5))
    assert isinstance(result, Unknown) and result.reason


@pytest.mark.parametrize(
    "phrase,start",
    [
        ("every other Tuesday", date(2027, 1, 6)),
        ("weekdays", date(2027, 1, 9)),
        ("the first Monday of each month", date(2027, 1, 11)),
        ("yearly on March 3", date(2027, 3, 4)),
    ],
)
def test_start_must_match(phrase, start):
    assert isinstance(rule_from_phrase(phrase, start), Unknown)


def test_aware_start():
    start = datetime(2027, 1, 5, 9, tzinfo=UTC)
    assert rule_from_phrase("every other Tuesday", start) == "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"


def test_naive_start():
    start = datetime(2027, 1, 5, 9)  # noqa: DTZ001 -- Floating start is rejected.
    assert isinstance(rule_from_phrase("daily", start), Unknown)


def test_case_and_whitespace():
    assert rule_from_phrase("  EVERY   OTHER Tuesday ", date(2027, 1, 5)) == "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"


def test_deterministic():
    start = date(2027, 1, 5)
    assert rule_from_phrase("daily", start) == rule_from_phrase("daily", start)


def test_the_31st_falls_on_the_last_day_of_short_months():
    zone = ZoneInfo("UTC")
    start = datetime(2027, 1, 31, 9, tzinfo=zone)
    rule = rule_from_phrase("every month on the 31st", start)
    found = occurrences(start, None, rule, (), (), {}, start, datetime(2027, 7, 1, tzinfo=zone), zone)
    assert [item.start.day for item in found] == [31, 28, 31, 30, 31, 30]


def test_a_month_end_start_in_a_short_month_matches_the_rule():
    assert rule_from_phrase("every month on the 30th", date(2027, 2, 28)) == (
        "FREQ=MONTHLY;BYMONTHDAY=28,29,30;BYSETPOS=-1"
    )


def test_shapes_are_data():
    assert rule_shape("FREQ=WEEKLY;INTERVAL=2;BYDAY=TU", date(2027, 1, 5)) == Shape(
        "weekly", {"interval": 2, "weekday": "tuesday"}
    )
    assert rule_shape("FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1", date(2027, 1, 31)) == Shape(
        "monthly_day", {"interval": 1, "day": 31}
    )
