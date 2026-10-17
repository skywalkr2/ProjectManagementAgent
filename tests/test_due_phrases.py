"""Fictional message dates covering due-phrase boundaries."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from engine.due_phrases import resolve

ZONE = ZoneInfo("America/New_York")
RECEIVED = datetime(2026, 11, 4, 14, 30, tzinfo=ZONE)


@pytest.mark.parametrize(
    ("phrase", "start", "end", "at", "exact"),
    [
        ("today", date(2026, 11, 4), date(2026, 11, 4), None, True),
        ("tonight", date(2026, 11, 4), date(2026, 11, 4), None, False),
        ("tomorrow", date(2026, 11, 5), date(2026, 11, 5), None, True),
        ("tomorrow morning", date(2026, 11, 5), date(2026, 11, 5), None, False),
        ("tomorrow evening", date(2026, 11, 5), date(2026, 11, 5), None, False),
        ("by end of day", date(2026, 11, 4), date(2026, 11, 4), time(17), True),
        ("close of business", date(2026, 11, 4), date(2026, 11, 4), time(17), True),
        ("by close of business", date(2026, 11, 4), date(2026, 11, 4), time(17), True),
        ("by the end of the day", date(2026, 11, 4), date(2026, 11, 4), time(17), True),
        ("Monday", date(2026, 11, 9), date(2026, 11, 9), None, True),
        ("Tuesday", date(2026, 11, 10), date(2026, 11, 10), None, True),
        ("Wednesday", date(2026, 11, 11), date(2026, 11, 11), None, True),
        ("Thursday", date(2026, 11, 5), date(2026, 11, 5), None, True),
        ("Friday", date(2026, 11, 6), date(2026, 11, 6), None, True),
        ("Saturday", date(2026, 11, 7), date(2026, 11, 7), None, True),
        ("Sunday", date(2026, 11, 8), date(2026, 11, 8), None, True),
        ("this Friday", date(2026, 11, 6), date(2026, 11, 6), None, True),
        ("next Friday", date(2026, 11, 13), date(2026, 11, 13), None, False),
        ("end of the week", date(2026, 11, 6), date(2026, 11, 6), None, True),
        ("early next week", date(2026, 11, 9), date(2026, 11, 11), None, False),
        ("next month", date(2026, 12, 1), date(2026, 12, 31), None, False),
        ("in two weeks", date(2026, 11, 18), date(2026, 11, 18), None, True),
        ("in 2 weeks", date(2026, 11, 18), date(2026, 11, 18), None, True),
        ("within two working days", date(2026, 11, 4), date(2026, 11, 6), None, False),
        ("within 2 working days", date(2026, 11, 4), date(2026, 11, 6), None, False),
        ("  TOMORROW   MORNING  ", date(2026, 11, 5), date(2026, 11, 5), None, False),
    ],
)
def test_supported_phrases(phrase, start, end, at, exact):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.end, result.time, result.exact) == (start, end, at, exact)
    assert result.note
    assert resolve(phrase, RECEIVED, ZONE) == result


@pytest.mark.parametrize(
    ("day", "phrase", "expected"),
    [
        (6, "Friday", date(2026, 11, 13)),
        (6, "this Friday", date(2026, 11, 6)),
        (6, "next Friday", date(2026, 11, 13)),
        (7, "Friday", date(2026, 11, 13)),
        (7, "this Friday", date(2026, 11, 13)),
        (7, "next Friday", date(2026, 11, 13)),
        (8, "Monday", date(2026, 11, 9)),
        (8, "this Monday", date(2026, 11, 9)),
        (8, "next Monday", date(2026, 11, 9)),
        (6, "end of the week", date(2026, 11, 6)),
        (7, "end of the week", date(2026, 11, 13)),
        (8, "end of the week", date(2026, 11, 13)),
    ],
)
def test_friday_and_weekend_conventions(day, phrase, expected):
    assert resolve(phrase, datetime(2026, 11, day, 22, tzinfo=ZONE), ZONE).start == expected


@pytest.mark.parametrize("day", [5, 6, 7, 8])
def test_two_working_days_skips_weekend(day):
    result = resolve("within two working days", datetime(2026, 11, day, 18, tzinfo=ZONE), ZONE)
    assert result.end == date(2026, 11, 9 if day == 5 else 10)
    assert result.start == date(2026, 11, day)
    assert result.exact is False


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("tomorrow", date(2027, 1, 1)),
        ("Friday", date(2027, 1, 1)),
        ("next Friday", date(2027, 1, 8)),
        ("in two weeks", date(2027, 1, 14)),
    ],
)
def test_year_end(phrase, expected):
    assert resolve(phrase, datetime(2026, 12, 31, 23, 59, tzinfo=ZONE), ZONE).start == expected


def test_next_month_across_year_end():
    result = resolve("next month", datetime(2026, 12, 31, tzinfo=UTC), UTC)
    assert (result.start, result.end) == (date(2027, 1, 1), date(2027, 1, 31))


def test_leap_year_month_range():
    result = resolve("next month", datetime(2028, 1, 31, tzinfo=UTC), UTC)
    assert (result.start, result.end) == (date(2028, 2, 1), date(2028, 2, 29))


@pytest.mark.parametrize(
    ("received", "phrase", "expected"),
    [
        (datetime(2026, 11, 5, 0, 1, tzinfo=UTC), "today", date(2026, 11, 4)),
        (datetime(2026, 11, 5, 0, 1, tzinfo=UTC), "tomorrow", date(2026, 11, 5)),
        (datetime(2026, 11, 5, 4, 59, tzinfo=UTC), "tonight", date(2026, 11, 4)),
        (datetime(2026, 11, 5, 5, 1, tzinfo=UTC), "today", date(2026, 11, 5)),
        (datetime(2027, 1, 1, 0, 1, tzinfo=UTC), "today", date(2026, 12, 31)),
        (datetime(2026, 11, 4, 23, 59, tzinfo=ZONE), "tomorrow", date(2026, 11, 5)),
    ],
)
def test_received_near_midnight(received, phrase, expected):
    assert resolve(phrase, received, "America/New_York").start == expected


@pytest.mark.parametrize(
    ("phrase", "locale", "expected"),
    [
        ("11/06/2026", "en_US", date(2026, 11, 6)),
        ("11/06/2026", "en_GB", date(2026, 6, 11)),
        ("06.11.2026", "en-GB", date(2026, 11, 6)),
        ("11-06-2026", "en-US", date(2026, 11, 6)),
        ("2026-11-06", "en_GB", date(2026, 11, 6)),
        ("November 6, 2026", "en_US", date(2026, 11, 6)),
        ("6 November 2026", "en_GB", date(2026, 11, 6)),
        ("by 6 November 2026", "en_US", date(2026, 11, 6)),
        ("by 11/06/2026", "en_GB", date(2026, 6, 11)),
    ],
)
def test_explicit_dates(phrase, locale, expected):
    result = resolve(phrase, RECEIVED, ZONE, locale=locale)
    assert result.start == result.end == expected
    assert result.exact


@pytest.mark.parametrize(
    "phrase",
    [
        "after the workshop",
        "when the files arrive",
        "soon",
        "sometime Friday",
        "maybe Friday",
        "ASAP",
        "later",
        "next quarter",
        "",
        "Friday or Monday",
        "11/06",
        "11/06/26",
        "13/06/2026",
        "02/30/2026",
        "2026-02-29",
        "6 Smarch 2026",
        "next Friday if approved",
        "tomorrowish",
    ],
)
def test_vague_event_relative_or_invalid_dates(phrase):
    result = resolve(phrase, RECEIVED, ZONE, locale="en_US")
    assert result.start is result.end is result.time is None
    assert result.exact is False
    assert result.note


def test_uk_invalid_date_does_not_fall_back_to_us():
    assert resolve("06/13/2026", RECEIVED, ZONE, locale="en_GB").start is None


def test_configurable_close_of_business_stays_on_received_day():
    result = resolve("close of business", RECEIVED.replace(hour=23), ZONE, end_of_day=time(16, 30))
    assert result.time == time(16, 30)
    assert result.start == date(2026, 11, 4)


def test_custom_workweek_and_early_range():
    result = resolve("early next week", RECEIVED, ZONE, workweek=(6, 0, 1, 2, 3))
    assert (result.start, result.end) == (date(2026, 11, 9), date(2026, 11, 11))
    assert resolve("end of the week", RECEIVED, ZONE, workweek=(0, 1, 2, 3)).start == date(2026, 11, 5)
    assert resolve("within two working days", RECEIVED, ZONE, workweek=(6, 0, 1, 2, 3)).end == date(2026, 11, 8)


def test_short_workweek_early_range():
    result = resolve("early next week", RECEIVED, ZONE, workweek=(2,))
    assert result.start == result.end == date(2026, 11, 11)
    assert not result.exact


@pytest.mark.parametrize("workweek", [(), (0, 0), (-1, 0), (7,), (True,), ("Monday",)])
def test_invalid_workweek(workweek):
    with pytest.raises(ValueError):
        resolve("today", RECEIVED, ZONE, workweek=workweek)


def test_invalid_configuration():
    with pytest.raises(ValueError):
        resolve("today", RECEIVED.replace(tzinfo=None), ZONE)
    with pytest.raises(ValueError):
        resolve("today", RECEIVED, ZONE, locale="guess")
    with pytest.raises(ValueError):
        resolve("today", RECEIVED, ZONE, end_of_day=time(17, tzinfo=UTC))


@pytest.mark.parametrize("day", [7, 8, 9])
def test_calendar_days_across_dst(day):
    result = resolve("tomorrow", datetime(2026, 3, day, 23, 59, tzinfo=ZONE), ZONE)
    assert result.start == date(2026, 3, day + 1)


@pytest.mark.parametrize(
    ("phrase", "day", "at", "exact"),
    [
        ("at noon", 4, time(12), True),
        ("midday", 4, time(12), True),
        ("at 3pm", 4, time(15), True),
        ("by 5pm", 4, time(17), True),
        ("by 5:30 p.m.", 4, time(17, 30), True),
        ("Friday at noon", 6, time(12), True),
        ("by Friday at noon", 6, time(12), True),
        ("tomorrow at 3pm", 5, time(15), True),
        ("Friday end of day", 6, time(17), True),
        ("Friday by end of day", 6, time(17), True),
        ("end of day Friday", 6, time(17), True),
        ("Friday at midday", 6, time(12), True),
        ("tomorrow at 12am", 5, time(0), True),
        ("tomorrow at 12pm", 5, time(12), True),
        ("Friday at 5:30 p.m.", 6, time(17, 30), True),
        ("Monday morning", 9, None, False),
        ("this Friday evening", 6, None, False),
        ("next Friday at noon", 13, time(12), False),
        ("by tomorrow evening", 5, None, False),
    ],
)
def test_time_expressions(phrase, day, at, exact):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start == result.end == date(2026, 11, day)
    assert result.time == at
    assert result.exact is exact


@pytest.mark.parametrize("phrase", ["November 20", "Nov 20", "Nov. 20", "20 Nov", "20 Nov.", "20 November"])
def test_written_dates_without_year(phrase):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start == date(2026, 11, 20)
    assert result.exact
    assert "Year omitted" in result.note


@pytest.mark.parametrize("phrase", ["Jan 2", "Jan. 2", "2 Jan", "2 Jan."])
def test_yearless_date_rolls_across_year_end(phrase):
    result = resolve(phrase, datetime(2026, 12, 31, 23, 59, tzinfo=ZONE), ZONE)
    assert result.start == date(2027, 1, 2)


@pytest.mark.parametrize("phrase", ["Sept 20", "Sept. 20", "Sep 20", "September 20"])
def test_yearless_past_date_moves_to_next_year(phrase):
    assert resolve(phrase, RECEIVED, ZONE).start == date(2027, 9, 20)


@pytest.mark.parametrize("phrase", ["Feb. 29", "29 Feb", "February 29"])
def test_yearless_leap_day_finds_next_valid_occurrence(phrase):
    assert resolve(phrase, RECEIVED, ZONE).start == date(2028, 2, 29)


@pytest.mark.parametrize("phrase", ["Nov 4", "4 Nov."])
def test_yearless_today_does_not_roll_after_clock_time(phrase):
    assert resolve(phrase, RECEIVED.replace(hour=23), ZONE).start == date(2026, 11, 4)


@pytest.mark.parametrize("phrase", ["Nov. 20, 2026", "20 Nov 2026", "Sept. 20, 2027"])
def test_abbreviations_with_explicit_year(phrase):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start is not None
    assert result.exact


@pytest.mark.parametrize("phrase", ["this Friday", "end of the week"])
def test_past_weekday_is_read_forward_and_marked_inexact(phrase):
    result = resolve(phrase, datetime(2026, 11, 7, 1, tzinfo=ZONE), ZONE)
    assert result.start == date(2026, 11, 13)
    assert not result.exact
    assert "read forward" in result.note.lower()


def test_read_forward_with_time_keeps_uncertainty():
    result = resolve("this Friday at noon", datetime(2026, 11, 7, tzinfo=ZONE), ZONE)
    assert result.start == date(2026, 11, 13)
    assert result.time == time(12)
    assert not result.exact
    assert "read forward" in result.note.lower()


@pytest.mark.parametrize("day", [4, 6, 7, 8])
def test_next_weekday_marks_ambiguity(day):
    result = resolve("next Friday", datetime(2026, 11, day, tzinfo=ZONE), ZONE)
    assert result.start == date(2026, 11, 13)
    assert not result.exact
    assert "both ways" in result.note


@pytest.mark.parametrize(
    ("phrase", "start", "end"),
    [
        ("this week", date(2026, 11, 4), date(2026, 11, 6)),
        ("next week", date(2026, 11, 9), date(2026, 11, 13)),
        ("end of next week", date(2026, 11, 13), date(2026, 11, 13)),
    ],
)
def test_week_ranges(phrase, start, end):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.end) == (start, end)
    assert result.time is None
    assert result.exact is (phrase == "end of next week")


def test_this_week_on_weekend_has_no_remaining_workdays():
    result = resolve("this week", datetime(2026, 11, 7, tzinfo=ZONE), ZONE)
    assert result.start is None
    assert not result.exact
    assert "No configured working days remain" in result.note


def test_week_ranges_with_custom_workweek():
    result = resolve("next week", RECEIVED, ZONE, workweek=(0, 2, 6))
    assert (result.start, result.end) == (date(2026, 11, 9), date(2026, 11, 15))
    assert "nonworking" in result.note
    assert resolve("end of next week", RECEIVED, ZONE, workweek=(0, 2, 6)).start == date(2026, 11, 15)


def test_next_week_across_year_end():
    result = resolve("next week", datetime(2026, 12, 31, tzinfo=ZONE), ZONE)
    assert (result.start, result.end) == (date(2027, 1, 4), date(2027, 1, 8))


def test_custom_eod_combined_with_day():
    assert resolve("Friday end of day", RECEIVED, ZONE, end_of_day=time(18, 30)).time == time(18, 30)


@pytest.mark.parametrize(
    "phrase",
    [
        "at 13pm",
        "by 0am",
        "at 5:99pm",
        "at 3",
        "at 15:00",
        "November 31",
        "31 Nov.",
        "11/20",
        "after the workshop at noon",
        "when the files arrive at 3pm",
        "next week at noon",
        "maybe Friday at noon",
        "sometime tomorrow morning",
    ],
)
def test_new_ambiguous_or_invalid_forms_stay_unresolved(phrase):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start is result.end is result.time is None
    assert not result.exact


def test_yearless_date_uses_local_received_date():
    result = resolve("Nov 4", datetime(2026, 11, 5, 0, 1, tzinfo=UTC), ZONE)
    assert result.start == date(2026, 11, 4)


def test_time_only_does_not_roll_when_time_has_passed():
    result = resolve("by 5pm", RECEIVED.replace(hour=23), ZONE)
    assert result.start == date(2026, 11, 4)
    assert result.time == time(17)


@pytest.mark.parametrize(
    ("phrase", "day", "at"),
    [("EOD", 4, time(17)), ("by COB Friday", 6, time(17)), ("Fri", 6, None), ("by Thurs at 3pm", 5, time(15))],
)
def test_short_forms(phrase, day, at):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.time) == (date(2026, 11, day), at)


def test_weekday_with_a_date_must_agree():
    assert resolve("Friday, Nov 6", RECEIVED, ZONE).start == date(2026, 11, 6)
    assert resolve("Thursday, Nov 6", RECEIVED, ZONE).start is None


def test_a_yearless_date_far_ahead_is_not_certain():
    result = resolve("by Oct 30", RECEIVED, ZONE)
    assert result.start == date(2027, 10, 30)
    assert result.exact is False
    assert resolve("Nov 20", RECEIVED, ZONE).exact is True
