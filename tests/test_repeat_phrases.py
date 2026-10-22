"""Repeat phrases to rules and rules to shapes, with month-end days that never skip a short month."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine.recurrence import occurrences
from engine.repeat_phrases import Shape, Unknown, rule_from_phrase, rule_shape


def _list(words):
    return ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]


def _day(number):
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


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
    if shape.kind == "weekly_days":
        n = values["interval"]
        days = _list(values["weekdays"])
        return f"every {days}" if n == 1 else f"every {n} weeks on {days}"
    if shape.kind == "monthly_day":
        n = values["interval"]
        return f"every {'month' if n == 1 else f'{n} months'} on the {values['day']}"
    if shape.kind == "monthly_days":
        n = values["interval"]
        days = _list([_day(d) for d in values["days"]])
        return f"every {'month' if n == 1 else f'{n} months'} on the {days}"
    if shape.kind == "monthly_last_day":
        n = values["interval"]
        return f"every {'month' if n == 1 else f'{n} months'} on the last day"
    if shape.kind == "monthly_nth":
        return f"the {values['ordinal']} {values['weekday']} of each month"
    if shape.kind == "monthly_nths":
        return f"the {_list(values['ordinals'])} {values['weekday']} of each month"
    if shape.kind == "monthly_weekday":
        return f"the {values['position']} weekday of each month"
    if shape.kind == "yearly_nth":
        return f"yearly on the {values['ordinal']} {values['weekday']} in {values['month']}"
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
        ("Mondays and Thursdays", date(2027, 1, 4), "FREQ=WEEKLY;BYDAY=MO,TH"),
        ("every Monday, Wednesday, and Friday", date(2027, 1, 4), "FREQ=WEEKLY;BYDAY=MO,WE,FR"),
        ("every 2 weeks on mon and thu", date(2027, 1, 4), "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH"),
        ("weekdays except Friday", date(2027, 1, 4), "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"),
        ("every weekday except Tuesday and Thursday", date(2027, 1, 4), "FREQ=WEEKLY;BYDAY=MO,WE,FR"),
        ("the 1st and 15th", date(2027, 1, 1), "FREQ=MONTHLY;BYMONTHDAY=1,15"),
        ("on the 1st", date(2027, 1, 1), "FREQ=MONTHLY;BYMONTHDAY=1"),
        ("every other month on the 10th", date(2027, 1, 10), "FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=10"),
        ("on the last day of each month", date(2027, 1, 31), "FREQ=MONTHLY;BYMONTHDAY=-1"),
        ("the second and fourth Tuesday", date(2027, 1, 12), "FREQ=MONTHLY;BYDAY=2TU,4TU"),
        ("the last weekday of the month", date(2027, 1, 29), "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1"),
        ("the first weekday each month", date(2027, 1, 1), "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=1"),
        ("annually", date(2027, 1, 5), "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=5"),
        ("every February 29", date(2027, 2, 28), "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=28,29;BYSETPOS=-1"),
        ("the last Friday in November each year", date(2027, 11, 26), "FREQ=YEARLY;BYMONTH=11;BYDAY=-1FR"),
        ("annually on the first Monday in December", date(2027, 12, 6), "FREQ=YEARLY;BYMONTH=12;BYDAY=1MO"),
        ("every other week on Monday", date(2027, 1, 4), "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("every three weeks", date(2027, 1, 5), "FREQ=WEEKLY;INTERVAL=3;BYDAY=TU"),
        ("weekly on Fri", date(2027, 1, 8), "FREQ=WEEKLY;BYDAY=FR"),
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
        "next Tuesday",
        "biweekly",
        "quarterly",
        "bimonthly",
        "twice a month",
        "water the plants every day",
        "monday",
        "weekdays except Saturday",
        "weekdays except every weekday",
        "the 15th and 31st",
        "every other",
        "every 0 weeks",
        "the first Monday and third Friday",
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
        "FREQ=WEEKLY;BYDAY=MO,MO",
        "FREQ=WEEKLY;BYDAY=MO,1FR",
        "FREQ=WEEKLY;WKST=SU",
        "FREQ=MONTHLY;BYMONTHDAY=-2",
        "FREQ=MONTHLY;BYMONTHDAY=31",
        "FREQ=MONTHLY;BYMONTHDAY=1,-1",
        "FREQ=MONTHLY;INTERVAL=2;BYDAY=1MO",
        "FREQ=MONTHLY;BYDAY=1MO,2TU",
        "FREQ=YEARLY;BYMONTH=3;BYDAY=1MO,2MO",
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
        ("Mondays and Thursdays", date(2027, 1, 5)),
        ("the 1st and 15th", date(2027, 1, 2)),
        ("on the last day of each month", date(2027, 1, 30)),
        ("the second and fourth Tuesday", date(2027, 1, 5)),
        ("the last weekday of the month", date(2027, 1, 28)),
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


def test_every_new_reading_is_the_dates_a_person_means():
    """The readings of the wider grammar, as the dates they give, through the calendar's own repeat engine."""
    zone = ZoneInfo("UTC")

    def days(phrase, start, count=4):
        rule = rule_from_phrase(phrase, start)
        assert isinstance(rule, str), rule
        begin = datetime.combine(start, datetime.min.time(), zone)
        found = occurrences(begin, None, rule, (), (), {}, begin, begin.replace(year=begin.year + 5), zone)
        return [item.start.date().isoformat() for item in found][:count]

    assert days("Mondays and Thursdays", date(2026, 11, 2)) == ["2026-11-02", "2026-11-05", "2026-11-09", "2026-11-12"]
    assert days("weekdays except Friday", date(2026, 11, 5)) == ["2026-11-05", "2026-11-09", "2026-11-10", "2026-11-11"]
    assert days("the 1st and 15th", date(2026, 11, 1)) == ["2026-11-01", "2026-11-15", "2026-12-01", "2026-12-15"]
    assert days("the last day of each month", date(2027, 1, 31)) == [
        "2027-01-31",
        "2027-02-28",
        "2027-03-31",
        "2027-04-30",
    ]
    assert days("the second and fourth Tuesday", date(2026, 11, 10)) == [
        "2026-11-10",
        "2026-11-24",
        "2026-12-08",
        "2026-12-22",
    ]
    assert days("the last weekday of the month", date(2026, 11, 30)) == [
        "2026-11-30",
        "2026-12-31",
        "2027-01-29",
        "2027-02-26",
    ]
    assert days("every February 29", date(2027, 2, 28)) == ["2027-02-28", "2028-02-29", "2029-02-28", "2030-02-28"]
    assert days("the last Friday in November each year", date(2026, 11, 27)) == [
        "2026-11-27",
        "2027-11-26",
        "2028-11-24",
        "2029-11-30",
    ]


def test_new_shapes_are_data():
    start = date(2026, 11, 2)
    assert rule_shape("FREQ=WEEKLY;BYDAY=TH,MO", start) == Shape(
        "weekly_days", {"interval": 1, "weekdays": ["monday", "thursday"]}
    )
    assert rule_shape("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH", start) == Shape(
        "weekly_days", {"interval": 1, "weekdays": ["monday", "tuesday", "wednesday", "thursday"]}
    )
    assert rule_shape("FREQ=MONTHLY;BYMONTHDAY=15,1", date(2026, 11, 1)) == Shape(
        "monthly_days", {"interval": 1, "days": [1, 15]}
    )
    assert rule_shape("FREQ=MONTHLY;BYMONTHDAY=-1", date(2026, 11, 30)) == Shape("monthly_last_day", {"interval": 1})
    assert rule_shape("FREQ=MONTHLY;BYDAY=4TU,2TU", date(2026, 11, 10)) == Shape(
        "monthly_nths", {"ordinals": ["second", "fourth"], "weekday": "tuesday"}
    )
    assert rule_shape("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", date(2026, 11, 30)) == Shape(
        "monthly_weekday", {"position": "last"}
    )
    assert rule_shape("FREQ=YEARLY;BYMONTH=11;BYDAY=-1FR", date(2026, 11, 27)) == Shape(
        "yearly_nth", {"month": "november", "ordinal": "last", "weekday": "friday"}
    )
    assert rule_shape("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=28,29;BYSETPOS=-1", date(2027, 2, 28)) == Shape(
        "yearly", {"month": "february", "day": 29}
    )
