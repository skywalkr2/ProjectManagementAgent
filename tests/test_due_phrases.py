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
        # Said on a Wednesday, so it may mean today: read forward and checked.
        ("Wednesday", date(2026, 11, 11), date(2026, 11, 11), None, False),
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


# ---- a leading "on" or "due", ordinals and their kin ---------------------------------------------------------------
# RECEIVED is a Wednesday in a month of 30 days, so "the 31st" is the next month's.


@pytest.mark.parametrize(
    ("phrase", "day", "exact"),
    [
        ("on Nov 20", date(2026, 11, 20), True),
        ("due Nov 20", date(2026, 11, 20), True),
        ("due on Nov 20", date(2026, 11, 20), True),
        ("due by Nov 20", date(2026, 11, 20), True),
        ("on or before Nov 20", date(2026, 11, 20), True),
        ("no later than Nov 20", date(2026, 11, 20), True),
        ("due Nov 20th", date(2026, 11, 20), True),
        ("on Friday", date(2026, 11, 6), True),
        ("due Friday", date(2026, 11, 6), True),
        ("due by Friday", date(2026, 11, 6), True),
        ("due tomorrow", date(2026, 11, 5), True),
        ("on the 25th", date(2026, 11, 25), True),
        ("due the 25th", date(2026, 11, 25), True),
        ("due on the 25th", date(2026, 11, 25), True),
        ("by the 30th", date(2026, 11, 30), True),
        ("the 25th", date(2026, 11, 25), True),
        ("25th", date(2026, 11, 25), True),
        ("by the 25th at noon", date(2026, 11, 25), True),
        ("the 4th", date(2026, 11, 4), True),
        ("on the 22nd", date(2026, 11, 22), True),
        ("by the 1st", date(2026, 12, 1), False),
        ("on the 3rd", date(2026, 12, 3), False),
        ("by the 31st", date(2026, 12, 31), False),
        ("the 25th of November", date(2026, 11, 25), True),
        ("by the 25th of Nov", date(2026, 11, 25), True),
        ("November 25th", date(2026, 11, 25), True),
        ("Nov 25th, 2027", date(2027, 11, 25), True),
        ("25th November", date(2026, 11, 25), True),
        ("Thursday the 5th", date(2026, 11, 5), True),
        ("due Thursday Nov 5", date(2026, 11, 5), True),
    ],
)
def test_a_leading_on_or_due_and_ordinals_are_read(phrase, day, exact):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.end, result.exact) == (day, day, exact)
    assert result.note


def test_an_ordinal_day_already_past_is_read_forward_and_marked_inexact():
    result = resolve("the 3rd", RECEIVED, ZONE)
    assert result.start == date(2026, 12, 3) and not result.exact
    assert "forward" in result.note.lower()


@pytest.mark.parametrize(
    "phrase",
    [
        "due",
        "on",
        "by",
        "due on",
        "the 32nd",
        "the 0th",
        "the 25",
        "the 25th and the 30th",
        "due the 25th if approved",
        "once on the 25th",
        "Friday the 25th",  # the 25th of November 2026 is a Wednesday
        "on the 31st of November",
        "the 25th of Smarch",
    ],
)
def test_words_the_reader_still_cannot_read_give_no_date(phrase):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start is result.end is result.time is None and not result.exact


def test_the_lead_words_and_ordinal_endings_are_settings_of_the_language():
    assert resolve("on Nov 20", RECEIVED, ZONE, lead_words=("by",)).start is None
    assert resolve("on Nov 20", RECEIVED, ZONE, lead_words=("on",)).start == date(2026, 11, 20)
    assert resolve("due Nov 20", RECEIVED, ZONE, lead_words=("due",)).start == date(2026, 11, 20)
    assert resolve("the 25th", RECEIVED, ZONE, ordinal_suffixes=("th",)).start == date(2026, 11, 25)
    assert resolve("the 22nd", RECEIVED, ZONE, ordinal_suffixes=("th",)).start is None
    assert resolve("the 25e", RECEIVED, ZONE, ordinal_suffixes=("e",)).start == date(2026, 11, 25)


def test_the_defaults_name_the_words_the_language_settings_start_from():
    from engine import due_phrases

    assert {"on", "due", "by", "due on", "due by"} <= set(due_phrases.DEFAULT_LEAD_WORDS)
    assert set(due_phrases.DEFAULT_ORDINAL_SUFFIXES) == {"st", "nd", "rd", "th"}
    assert {"once", "after", "when", "until", "as soon as"} <= set(due_phrases.DEFAULT_CONDITION_WORDS)


@pytest.mark.parametrize(
    "phrase",
    [
        "once the keys arrive",
        "Once I receive the keys",
        "after the workshop",
        "when the measurements arrive",
        "until you publish it",
        "as soon as I've spoken to the surveyor",
        "within two working days of receiving the files",
        "Friday, once the keys arrive",
        "if the board agrees",
        "sometime soon",
        "soon",
        "whenever I can",
    ],
)
def test_a_condition_or_an_open_ended_time_is_not_a_date(phrase):
    from engine.due_phrases import DEFAULT_CONDITION_WORDS, is_condition

    assert is_condition(phrase, DEFAULT_CONDITION_WORDS)


@pytest.mark.parametrize(
    "phrase",
    [
        "by Tuesday",
        "on the 25th",
        "due Nov 20",
        "by mid-month",
        "the afternoon",
        "Friday",
        "by the end of the week",
        "",
    ],
)
def test_a_date_or_unread_date_words_are_not_a_condition(phrase):
    from engine.due_phrases import DEFAULT_CONDITION_WORDS, is_condition

    assert not is_condition(phrase, DEFAULT_CONDITION_WORDS)


def test_condition_words_are_whole_words_and_come_from_the_setting():
    from engine.due_phrases import is_condition

    assert not is_condition("by Whenham", ("when",)) and not is_condition("afternoon", ("after",))
    assert is_condition("AFTER the workshop", ("after",))
    assert not is_condition("after the workshop", ())


@pytest.mark.parametrize("hour", [9, 22])
def test_a_bare_weekday_said_on_that_weekday_is_read_forward_and_checked(hour):
    """ "By Friday" written on a Friday may mean today or a week later: it is read forward, as every bare weekday is,
    and never firm, so the person is asked to check it."""
    found = resolve("by Friday", datetime(2026, 11, 6, hour, tzinfo=ZONE), ZONE)
    assert (found.start, found.end, found.exact) == (date(2026, 11, 13), date(2026, 11, 13), False)


def test_a_bare_weekday_said_on_another_day_stays_firm():
    found = resolve("by Friday", datetime(2026, 11, 4, 9, tzinfo=ZONE), ZONE)
    assert (found.start, found.exact) == (date(2026, 11, 6), True)


# ---- numeric dates, with the year optional ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "locale", "expected", "exact"),
    [
        ("11/20", "en_US", date(2026, 11, 20), True),
        ("by 11/6", "en_US", date(2026, 11, 6), True),
        ("11/3", "en_US", date(2027, 11, 3), False),  # nearly a year ahead is more likely a date just past
        ("12/4", "en_US", date(2026, 12, 4), True),
        ("20/11", "en_GB", date(2026, 11, 20), True),
        ("4/12", "en_GB", date(2026, 12, 4), True),
        ("11/4", "en_US", date(2026, 11, 4), True),  # the received day itself
    ],
)
def test_a_numeric_date_without_a_year_is_read_in_the_languages_order(phrase, locale, expected, exact):
    result = resolve(phrase, RECEIVED, ZONE, locale=locale)
    assert result.start == result.end == expected
    assert result.exact is exact


def test_a_numeric_date_without_a_year_never_tries_the_other_order():
    assert resolve("20/11", RECEIVED, ZONE, locale="en_US").start is None
    assert resolve("11/20", RECEIVED, ZONE, locale="en_GB").start is None
    assert resolve("2/30", RECEIVED, ZONE).start is None


@pytest.mark.parametrize("phrase", ["11/06/26", "11/6/26", "1/2/3", "11/", "/6", "11/6/", "1.5", "11-6"])
def test_a_two_digit_year_or_a_broken_numeric_date_is_refused(phrase):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start is result.end is result.time is None and not result.exact


# ---- day-and-time words ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "day", "at", "exact"),
    [
        ("day after tomorrow", date(2026, 11, 6), None, True),
        ("the day after tomorrow", date(2026, 11, 6), None, True),
        ("by the day after tomorrow", date(2026, 11, 6), None, True),
        ("day after tomorrow at noon", date(2026, 11, 6), time(12), True),
        ("later today", date(2026, 11, 4), None, True),
        ("tonight", date(2026, 11, 4), None, False),
        ("by 8 tonight", date(2026, 11, 4), time(20), True),
        ("8:30 tonight", date(2026, 11, 4), time(20, 30), True),
        ("tonight at 9", date(2026, 11, 4), time(21), True),
        ("tonight at 9pm", date(2026, 11, 4), time(21), True),
        ("noon tomorrow", date(2026, 11, 5), time(12), True),
        ("by noon tomorrow", date(2026, 11, 5), time(12), True),
        ("5pm Friday", date(2026, 11, 6), time(17), True),
        ("at 5pm on Friday", date(2026, 11, 6), time(17), True),
        ("midday today", date(2026, 11, 4), time(12), True),
        ("midnight Friday", date(2026, 11, 6), time(0), False),
        ("at midnight tomorrow", date(2026, 11, 5), time(0), False),
    ],
)
def test_the_everyday_day_and_time_words_are_read(phrase, day, at, exact):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.end, result.time, result.exact) == (day, day, at, exact)


@pytest.mark.parametrize(
    "phrase", ["midnight tonight", "3 tonight", "13 tonight", "8:75 tonight", "noon noon", "5pm 6pm", "noon maybe"]
)
def test_doubtful_times_of_day_give_no_date(phrase):
    result = resolve(phrase, RECEIVED, ZONE)
    assert result.start is result.end is result.time is None and not result.exact


@pytest.mark.parametrize(
    ("phrase", "day", "exact"),
    [
        ("first thing Monday", date(2026, 11, 9), True),
        ("first thing tomorrow", date(2026, 11, 5), True),
        ("by first thing Friday", date(2026, 11, 6), True),
        ("first thing Wednesday", date(2026, 11, 11), False),  # said on a Wednesday: may mean today
    ],
)
def test_first_thing_is_the_start_of_that_day_with_no_clock_time(phrase, day, exact):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.end, result.time, result.exact) == (day, day, None, exact)


@pytest.mark.parametrize(
    "phrase", ["first thing", "first thing soon", "first thing noon", "first thing in the morning"]
)
def test_first_thing_needs_a_day(phrase):
    assert resolve(phrase, RECEIVED, ZONE).start is None


@pytest.mark.parametrize(
    ("received", "phrase", "expected"),
    [
        (datetime(2026, 11, 10, 10, tzinfo=ZONE), "end of the month", date(2026, 11, 30)),
        (datetime(2026, 11, 30, 10, tzinfo=ZONE), "end of month", date(2026, 11, 30)),
        (datetime(2026, 11, 10, 10, tzinfo=ZONE), "by the end of the month", date(2026, 11, 30)),
        (datetime(2026, 11, 10, 10, tzinfo=ZONE), "end of next month", date(2026, 12, 31)),
        (datetime(2026, 12, 10, 10, tzinfo=ZONE), "end of next month", date(2027, 1, 31)),
        (datetime(2027, 1, 31, 10, tzinfo=ZONE), "end of next month", date(2027, 2, 28)),
        (datetime(2028, 1, 15, 10, tzinfo=ZONE), "end of next month", date(2028, 2, 29)),
    ],
)
def test_the_end_of_a_month_is_its_last_calendar_day(received, phrase, expected):
    result = resolve(phrase, received, ZONE)
    assert result.start == result.end == expected and result.exact


@pytest.mark.parametrize(
    ("day", "hour", "weekend"),
    [
        (4, 14, (date(2026, 11, 7), date(2026, 11, 8))),  # Wednesday
        (6, 9, (date(2026, 11, 7), date(2026, 11, 8))),  # Friday
        (7, 9, (date(2026, 11, 7), date(2026, 11, 8))),  # Saturday: the current one
        (8, 20, (date(2026, 11, 7), date(2026, 11, 8))),  # Sunday: the current one
        (9, 9, (date(2026, 11, 14), date(2026, 11, 15))),  # Monday
    ],
)
def test_this_weekend_is_the_coming_or_current_saturday_and_sunday(day, hour, weekend):
    result = resolve("this weekend", datetime(2026, 11, day, hour, tzinfo=ZONE), ZONE)
    assert (result.start, result.end) == weekend
    assert result.time is None and not result.exact


@pytest.mark.parametrize(
    ("phrase", "end"),
    [
        ("within 48 hours", date(2026, 11, 6)),
        ("within 24 hours", date(2026, 11, 5)),
        ("within 1 hour", date(2026, 11, 4)),
        ("within 12 hours", date(2026, 11, 5)),
        ("within two hours", date(2026, 11, 4)),
        ("within 3 days", date(2026, 11, 7)),
        ("within five days", date(2026, 11, 9)),
        ("within 1 day", date(2026, 11, 5)),
        ("within 3 working days", date(2026, 11, 9)),  # Wednesday: Thursday, Friday, Monday
        ("within three business days", date(2026, 11, 9)),
        ("within two working days", date(2026, 11, 6)),
    ],
)
def test_within_a_span_is_a_range_from_the_received_day(phrase, end):
    result = resolve(phrase, RECEIVED, ZONE)
    assert (result.start, result.end, result.time, result.exact) == (date(2026, 11, 4), end, None, False)


def test_within_hours_counts_from_the_received_instant_in_the_local_zone():
    late = datetime(2026, 11, 4, 22, 30, tzinfo=ZONE)
    assert resolve("within 2 hours", late, ZONE).end == date(2026, 11, 5)
    assert resolve("within 1 hour", late, ZONE).end == date(2026, 11, 4)
    # The same instant, seen from Tokyo, is already the next morning.
    assert resolve("within 1 hour", late, "Asia/Tokyo").start == date(2026, 11, 5)


def test_within_days_counts_calendar_days_unless_it_says_working_days():
    friday = datetime(2026, 11, 6, 10, tzinfo=ZONE)
    assert resolve("within 3 days", friday, ZONE).end == date(2026, 11, 9)
    assert resolve("within 3 working days", friday, ZONE).end == date(2026, 11, 11)


@pytest.mark.parametrize(
    "phrase",
    [
        "within",
        "within days",
        "within 0 days",
        "within 1001 days",
        "within 2 weeks",
        "within a couple of days",
        "within 2 days of receiving the files",
        "within two",
        "within 2.5 hours",
    ],
)
def test_a_span_the_rules_cannot_count_gives_no_date(phrase):
    assert resolve(phrase, RECEIVED, ZONE).start is None


# ---- time zone abbreviations -----------------------------------------------------------------------------------------

NOW_IN_NEW_YORK = datetime(2026, 11, 4, 14, 30, tzinfo=ZONE)


@pytest.mark.parametrize(
    ("phrase", "zone", "day", "at"),
    [
        ("by 5pm ET", "America/Los_Angeles", date(2026, 11, 4), time(14)),
        ("5pm EST", "America/Chicago", date(2026, 11, 4), time(16)),
        ("noon ET", "America/Los_Angeles", date(2026, 11, 4), time(9)),
        ("tomorrow at 9am PT", "America/New_York", date(2026, 11, 5), time(12)),
        ("tomorrow 11pm PT", "America/New_York", date(2026, 11, 6), time(2)),  # the date moves with the zone
        ("5pm ET", "America/New_York", date(2026, 11, 4), time(17)),
        ("5:30pm et", "America/New_York", date(2026, 11, 4), time(17, 30)),
        ("noon UTC", "Europe/London", date(2026, 11, 4), time(12)),
    ],
)
def test_a_time_with_a_zone_abbreviation_is_given_in_the_persons_zone(phrase, zone, day, at):
    got = resolve(phrase, NOW_IN_NEW_YORK, zone)
    assert (got.start, got.end, got.time, got.exact) == (day, day, at, True)


def test_a_zone_abbreviation_follows_the_daylight_saving_rules_of_the_date():
    # Before the US clocks change (1 November) New York is four hours behind UTC, after it five; London stays at UTC.
    before = datetime(2026, 10, 30, 9, tzinfo=ZONE)
    assert resolve("noon ET", before, "Europe/London").time == time(16)
    assert resolve("noon ET", NOW_IN_NEW_YORK, "Europe/London").time == time(17)


def test_a_day_word_said_across_a_date_line_with_a_zone_is_doubtful():
    # 14:30 in New York is already the next day in Tokyo, where "today" is the 5th and 15:30 UTC is the 6th there.
    got = resolve("3:30pm UTC", NOW_IN_NEW_YORK, "Asia/Tokyo")
    assert (got.start, got.time, got.exact) == (date(2026, 11, 6), time(0, 30), False)


@pytest.mark.parametrize(
    "phrase", ["5pm XYZ", "Friday ET", "ET", "end of day ET", "after 5pm ET", "5pm ET if approved"]
)
def test_a_zone_without_a_clock_time_or_an_unknown_abbreviation_gives_no_date(phrase):
    assert resolve(phrase, NOW_IN_NEW_YORK, ZONE).start is None


def test_the_zone_abbreviations_are_a_setting_of_the_language():
    assert resolve("5pm ET", NOW_IN_NEW_YORK, ZONE, time_zones={"PT": "America/Los_Angeles"}).start is None
    got = resolve("5pm CET", NOW_IN_NEW_YORK, ZONE, time_zones={"cet": "Europe/Paris"})
    assert (got.start, got.time) == (date(2026, 11, 4), time(11))
    assert resolve("5pm ET", NOW_IN_NEW_YORK, ZONE, time_zones={"ET": "Not/AZone"}).start is None


# ---- holidays by name ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "calendar", "day"),
    [
        ("Thanksgiving", "en_US", date(2026, 11, 26)),
        ("by Thanksgiving", "en_US", date(2026, 11, 26)),
        ("by Thanksgiving Day", "en_US", date(2026, 11, 26)),
        ("Christmas", "en_US", date(2026, 12, 25)),
        ("by Christmas Eve", "en_US", date(2026, 12, 24)),
        ("by New Year\u2019s Day", "en_US", date(2027, 1, 1)),
        ("Labor Day", "en_US", date(2027, 9, 6)),
        ("by Boxing Day", "en_GB", date(2026, 12, 26)),
        ("the spring bank holiday", "en_GB", date(2027, 5, 31)),
    ],
)
def test_a_holiday_named_is_its_day_by_the_calendar_of_the_language(phrase, calendar, day):
    got = resolve(phrase, RECEIVED, ZONE, locale=calendar)
    assert got.start == got.end == day


def test_a_holiday_far_ahead_may_mean_one_just_past():
    got = resolve("by Labor Day", RECEIVED, ZONE)
    assert got.start == date(2027, 9, 6) and not got.exact
    assert resolve("by Thanksgiving", RECEIVED, ZONE).exact


def test_a_holiday_that_is_today_is_today_and_one_that_passed_is_next_years():
    assert resolve("Thanksgiving", datetime(2026, 11, 26, 8, tzinfo=ZONE), ZONE).start == date(2026, 11, 26)
    assert resolve("Thanksgiving", datetime(2026, 11, 27, 8, tzinfo=ZONE), ZONE).start == date(2027, 11, 25)


def test_a_holiday_is_dated_by_its_rule_in_every_year():
    from engine.due_phrases import holiday_date, load_holidays

    by_name = {name: day for day in load_holidays("en-US") for name in day.names}
    assert [holiday_date(by_name["thanksgiving"], y) for y in (2026, 2027, 2028)] == [
        date(2026, 11, 26),
        date(2027, 11, 25),
        date(2028, 11, 23),
    ]
    assert [holiday_date(by_name["memorial day"], y) for y in (2026, 2027)] == [date(2026, 5, 25), date(2027, 5, 31)]
    assert holiday_date(by_name["labor day"], 2026) == date(2026, 9, 7)


def test_a_holiday_calendar_belongs_to_a_language_and_a_language_without_one_reads_none():
    from engine.due_phrases import holiday_calendars, load_holidays

    assert {"en-US", "en-GB"} <= set(holiday_calendars())
    assert load_holidays("en-AU") == () and load_holidays("xx") == ()
    assert resolve("by Boxing Day", RECEIVED, ZONE, locale="en_US").start is None
    assert resolve("by Thanksgiving", RECEIVED, ZONE, locale="en_GB").start is None


def test_the_holidays_can_be_passed_in():
    from engine.due_phrases import Holiday

    own = (Holiday(("founders day",), month=3, day=3),)
    assert resolve("by founders day", RECEIVED, ZONE, holidays=own).start == date(2027, 3, 3)
    assert resolve("by Thanksgiving", RECEIVED, ZONE, holidays=own).start is None
    assert resolve("by Thanksgiving", RECEIVED, ZONE, holidays=()).start is None


@pytest.mark.parametrize(
    "phrase", ["before Thanksgiving", "after Christmas", "Thanksgiving week", "by Easter", "Thanksgiving Friday"]
)
def test_words_around_a_holiday_that_say_more_than_its_day_give_no_date(phrase):
    assert resolve(phrase, RECEIVED, ZONE).start is None


# ---- the words are settings of the language --------------------------------------------------------------------------


def test_the_day_and_time_words_come_from_the_language_settings():
    words = {
        "day_after_tomorrow": ["overmorrow"],
        "first_thing": ["at dawn"],
        "end_of_month": [],
        "noon": ["high noon"],
    }
    assert resolve("overmorrow", RECEIVED, ZONE, phrase_words=words).start == date(2026, 11, 6)
    assert resolve("day after tomorrow", RECEIVED, ZONE, phrase_words=words).start is None
    assert resolve("at dawn Friday", RECEIVED, ZONE, phrase_words=words).start == date(2026, 11, 6)
    assert resolve("end of the month", RECEIVED, ZONE, phrase_words=words).start is None
    assert resolve("high noon tomorrow", RECEIVED, ZONE, phrase_words=words).time == time(12)
    # A meaning left out of the setting keeps its default.
    assert resolve("later today", RECEIVED, ZONE, phrase_words=words).start == date(2026, 11, 4)


def test_the_number_words_and_units_come_from_the_language_settings():
    assert resolve("within couple hours", RECEIVED, ZONE, number_words={"couple": 2}).end == date(2026, 11, 4)
    assert resolve("within two hours", RECEIVED, ZONE, number_words={}).start is None
    assert resolve("within 3 jours", RECEIVED, ZONE, phrase_words={"days": ["jours"]}).end == date(2026, 11, 7)
    assert resolve("within 3 days", RECEIVED, ZONE, phrase_words={"days": ["jours"]}).start is None


def test_the_language_settings_accept_only_known_meanings_and_real_zones():
    from pydantic import ValidationError

    from engine.config.schema import LanguageFile

    assert LanguageFile(due_phrase_words={"noon": ["noon"]}).due_phrase_words == {"noon": ["noon"]}
    with pytest.raises(ValidationError):
        LanguageFile(due_phrase_words={"nonn": ["noon"]})
    with pytest.raises(ValidationError):
        LanguageFile(time_zone_abbreviations={"ET": "Nowhere/Land"})
    defaults = LanguageFile()
    assert defaults.holiday_calendar is None
    assert defaults.time_zone_abbreviations["ET"] == "America/New_York"
    assert defaults.due_number_words["two"] == 2


def test_the_demo_workspaces_language_settings_read_the_new_words(tmp_path):
    from engine.due_phrases import load_holidays
    from engine.workspace import init_workspace
    from tests.conftest import DEMO_A, DEMO_B

    for template in (DEMO_A, DEMO_B):
        settings = init_workspace(tmp_path / template.name, template=template, git=False).config(env={}).language
        assert settings.holiday_calendar and load_holidays(settings.holiday_calendar)
        read = resolve(
            "by 5pm ET",
            NOW_IN_NEW_YORK,
            "America/Los_Angeles",
            phrase_words=settings.due_phrase_words,
            number_words=settings.due_number_words,
            time_zones=settings.time_zone_abbreviations,
            holidays=load_holidays(settings.holiday_calendar),
        )
        assert (read.start, read.time, read.exact) == (date(2026, 11, 4), time(14), True)
        assert resolve("within two days", NOW_IN_NEW_YORK, ZONE, number_words=settings.due_number_words).end == date(
            2026, 11, 6
        )
