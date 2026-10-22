"""Repeat rules from plain phrases, and rules back to data the screen words from the wording sheet.

`rule_from_phrase` reads a bounded English grammar ("every other Tuesday", "Mondays and Thursdays", "weekdays except
Friday", "the second and fourth Tuesday of each month", "the 1st and 15th", "the last day of each month", "every 3
months on the 15th", "yearly on March 3", "the last Friday in November each year") into an iCalendar RRULE value. A
day of the month past the 28th means that day or the month's last day when the month is shorter, written as the
standard `BYMONTHDAY=28,...,N;BYSETPOS=-1`, so "the 31st" never skips a short month; February 29 likewise falls on the
28th in other years. `rule_shape` turns a supported rule into a `Shape(kind, values)`; nothing here is on-screen text.
Anything outside the grammar ("biweekly", "quarterly", a phrase that carries other words), or a start that doesn't fall
on the rule, is `Unknown` with a reason, never a guess.

Shape kinds and their values: `daily` (interval), `weekdays`, `weekly` (interval, weekday), `weekly_days` (interval,
weekdays), `monthly_day` (interval, day), `monthly_days` (interval, days), `monthly_last_day` (interval), `monthly_nth`
(ordinal, weekday), `monthly_nths` (ordinals, weekday), `monthly_weekday` (position: first or last), `yearly` (month,
day) and `yearly_nth` (month, ordinal, weekday). Weekdays, months and ordinals are English words used as keys.
"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}
NUMBER_WORDS = {
    word: number
    for number, word in enumerate(
        ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"), 1
    )
}
_ABBREVIATIONS = {
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
_SEPARATOR = r"(?:\s*,\s*(?:and\s+)?|\s+and\s+)"
_WORDS = rf"[a-z]+(?:{_SEPARATOR}[a-z]+)*"
_COUNT = rf"(?:\d+|{'|'.join(NUMBER_WORDS)})"
_ORDINAL_WORD = "|".join(ORDINALS)
_ORDINAL_WORDS = rf"(?:{_ORDINAL_WORD})(?:{_SEPARATOR}(?:{_ORDINAL_WORD}))*"
_DAY_NUMBER = r"\d{1,2}(?:st|nd|rd|th)?"
_DAY_NUMBERS = rf"{_DAY_NUMBER}(?:{_SEPARATOR}{_DAY_NUMBER})*"
_SUFFIXED_DAY = r"\d{1,2}(?:st|nd|rd|th)"
_SUFFIXED_DAYS = rf"{_SUFFIXED_DAY}(?:{_SEPARATOR}{_SUFFIXED_DAY})*"
_EACH_MONTH = r"(?:(?:of|in) (?:each|every|the)|each|every) month"
_EVERY_MONTHS = rf"(?:every (?:other |{_COUNT} )?months?|monthly|each month)"
_YEARLY = r"(?:yearly|annually|every year|each year)"
_MONTH_NAME = "|".join(MONTHS)


class StartMismatch(ValueError):
    """A rule the grammar reads, whose first day doesn't fall on it."""


@dataclass(frozen=True)
class Unknown:
    """What the grammar can't say. `status` is `unknown` for words or a rule outside it, and `off_start` for one it
    reads whose given start doesn't fall on the rule, so a caller can look for the first day that does."""

    reason: str
    status: str = "unknown"


@dataclass(frozen=True)
class Shape:
    kind: str  # see the module note for each kind's values
    values: dict[str, Any] = field(default_factory=dict)


def _start_date(start: date | datetime) -> date:
    if isinstance(start, datetime):
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("A timed start must include its time zone")
        if start.astimezone(UTC).astimezone(start.tzinfo).replace(tzinfo=None) != start.replace(tzinfo=None):
            raise ValueError("The start falls in a nonexistent local time")
        return start.date()
    if type(start) is date:
        return start
    raise ValueError("Supply a date or an aware datetime for start")


def _suffix(number: int) -> str:
    return "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")


def _month_day(number: int) -> dict[str, str]:
    """A day of the month; past the 28th it is that day or the month's last day when the month is shorter."""
    if number <= 28:
        return {"BYMONTHDAY": str(number)}
    return {"BYMONTHDAY": ",".join(str(day) for day in range(28, number + 1)), "BYSETPOS": "-1"}


def _month_days(parts: dict[str, str]) -> list[int]:
    """The days a BYMONTHDAY means, ascending: a list of days up to the 28th, the last day as -1, or the one day a
    clamped run (`28,...,N` with BYSETPOS=-1) stands for."""
    raw = parts["BYMONTHDAY"].split(",")
    if not all(re.fullmatch(r"-?\d{1,2}", item) for item in raw):
        raise ValueError("The month days are malformed")
    numbers = [int(item) for item in raw]
    if "BYSETPOS" in parts:
        if len(numbers) < 2 or numbers != list(range(28, numbers[-1] + 1)) or numbers[-1] > 31:
            raise ValueError("This month-day combination is unsupported")
        if parts["BYSETPOS"] != "-1":
            raise ValueError("This month-day combination is unsupported")
        return [numbers[-1]]
    if numbers == [-1]:
        return numbers
    if len(set(numbers)) != len(numbers) or not all(1 <= number <= 28 for number in numbers):
        raise ValueError("This month-day combination is unsupported")
    return sorted(numbers)


def _check_start(parts: dict[str, str], start: date) -> None:
    last = monthrange(start.year, start.month)[1]
    if "BYMONTH" in parts and start.month != int(parts["BYMONTH"]):
        raise StartMismatch("Start does not match the stated month; choose the first occurrence explicitly")
    if "BYMONTHDAY" in parts:
        wanted = {last if number == -1 else min(number, last) for number in _month_days(parts)}
        if start.day not in wanted:
            raise StartMismatch("Start does not match the stated month day; choose the first occurrence explicitly")
    byday = parts.get("BYDAY")
    if byday is None:
        return
    items = byday.split(",")
    if "BYSETPOS" in parts:
        # The first or last weekday (Monday to Friday) of the month.
        if start.weekday() >= 5:
            raise StartMismatch("Start is not a weekday")
        days = [d for d in range(1, last + 1) if date(start.year, start.month, d).weekday() < 5]
        if start.day != (days[0] if parts["BYSETPOS"] == "1" else days[-1]):
            raise StartMismatch("Start does not match the stated weekday position")
        return
    if all(item in CODES for item in items):
        if CODES[start.weekday()] not in items:
            raise StartMismatch("Start is not on a stated weekday; choose the first occurrence explicitly")
        return
    for item in items:
        match = re.fullmatch(r"(-?\d+)(MO|TU|WE|TH|FR|SA|SU)", item)
        if not match:
            raise ValueError("The ordinal weekday is unsupported")
        ordinal = int(match.group(1))
        in_week = (start.day - 1) // 7 + 1 == ordinal if ordinal > 0 else start.day + 7 > last
        if CODES[start.weekday()] == match.group(2) and in_week:
            return
    raise StartMismatch("Start does not match the stated ordinal weekday")


def _serialize(parts: dict[str, str]) -> str:
    order = ("FREQ", "INTERVAL", "BYMONTH", "BYMONTHDAY", "BYDAY", "BYSETPOS")
    return ";".join(f"{key}={parts[key]}" for key in order if key in parts)


def _ordinal_ok(number: int, suffix: str | None) -> None:
    if suffix and _suffix(number) != suffix:
        raise ValueError("The written ordinal is inconsistent with its number")


def _items(text: str) -> list[str]:
    """The words of a list written with commas and "and"."""
    return [item for item in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", text) if item]


def _weekday_of(token: str, plural: bool | None = None) -> int | None:
    """The weekday a word means (full name, plural or abbreviation), None for anything else. `plural` True takes only
    a full name's plural, False only the singular forms."""
    if token in WEEKDAYS:
        return WEEKDAYS.index(token) if plural is not True else None
    if token.endswith("s") and token[:-1] in WEEKDAYS:
        return WEEKDAYS.index(token[:-1]) if plural is not False else None
    return _ABBREVIATIONS.get(token) if plural is not True else None


def _weekday_list(text: str, plural: bool | None = None) -> list[int] | None:
    """The distinct weekdays of a written list, in week order, or None when a word isn't a weekday."""
    found = [_weekday_of(item, plural) for item in _items(text)]
    if not found or None in found or len(set(found)) != len(found):
        return None
    return sorted(found)  # type: ignore[type-var]


def _count(token: str) -> int:
    number = int(token) if token.isdigit() else NUMBER_WORDS[token]
    if number < 1:
        raise ValueError("The interval must be at least one")
    return number


def _interval(other: str | None, count: str | None = None) -> str:
    return "2" if other else str(_count(count)) if count else "1"


def _days_of_month(text: str) -> list[int]:
    days = []
    for item in _items(text):
        match = re.fullmatch(r"(\d{1,2})(st|nd|rd|th)?", item)
        number = int(match.group(1))
        if not 1 <= number <= 31:
            raise ValueError("The written day of the month is not a day")
        _ordinal_ok(number, match.group(2))
        days.append(number)
    if len(set(days)) != len(days):
        raise ValueError("A day of the month is named twice")
    if len(days) > 1 and max(days) > 28:
        raise ValueError("A list of days of the month can't include the 29th to the 31st")
    return sorted(days)


def _month_day_parts(days: list[int]) -> dict[str, str]:
    return _month_day(days[0]) if len(days) == 1 else {"BYMONTHDAY": ",".join(str(d) for d in days)}


def _code_list(days: list[int]) -> str:
    return ",".join(CODES[d] for d in days)


def _ordinal_weekdays(ordinals: str, weekday: str) -> str:
    named = _items(ordinals)
    day = _weekday_of(weekday, False)
    if day is None or len(set(named)) != len(named):
        raise ValueError("The ordinal weekday is not clear")
    numbers = sorted((ORDINALS[name] for name in named), key=lambda n: (n < 0, n))
    return ",".join(f"{number}{CODES[day]}" for number in numbers)


def _from_words(text: str, day: date) -> dict[str, str]:
    """The rule parts a phrase in the grammar means; raises ValueError for anything else."""
    weekdays = list(range(5))
    if match := re.fullmatch(rf"(?:every |each |on )?weekdays?(?: except ({_WORDS}))?", text):
        left = weekdays
        if match.group(1):
            gone = _weekday_list(match.group(1))
            if gone is None or max(gone) > 4:
                raise ValueError("Only weekdays can be left out of the weekdays")
            left = [d for d in weekdays if d not in gone]
            if not left:
                raise ValueError("Every weekday is left out")
        return {"FREQ": "WEEKLY", "BYDAY": _code_list(left)}
    if match := re.fullmatch(rf"daily|every day|each day|every (?:(other) |({_COUNT}) )?days?", text):
        return {"FREQ": "DAILY", "INTERVAL": _interval(match.group(1), match.group(2))}
    if match := re.fullmatch(rf"(?:weekly|every week|each week)(?: on ({_WORDS}))?", text):
        listed = _weekday_list(match.group(1)) if match.group(1) else [day.weekday()]
        if listed is None:
            raise ValueError("The written weekday is not clear")
        return {"FREQ": "WEEKLY", "BYDAY": _code_list(listed)}
    if match := re.fullmatch(rf"every (?:(other)|({_COUNT})) weeks?(?: on ({_WORDS}))?", text):
        listed = _weekday_list(match.group(3)) if match.group(3) else [day.weekday()]
        if listed is None:
            raise ValueError("The written weekday is not clear")
        return {"FREQ": "WEEKLY", "INTERVAL": _interval(match.group(1), match.group(2)), "BYDAY": _code_list(listed)}
    match = re.fullmatch(rf"(?:every|each) (?:(other) )?({_WORDS})", text)
    if match and (listed := _weekday_list(match.group(2))) is not None:
        return {"FREQ": "WEEKLY", "INTERVAL": _interval(match.group(1)), "BYDAY": _code_list(listed)}
    match = re.fullmatch(rf"(?:on )?({_WORDS})", text)
    if match and (listed := _weekday_list(match.group(1), plural=True)) is not None:
        return {"FREQ": "WEEKLY", "BYDAY": _code_list(listed)}
    if match := re.fullmatch(
        rf"(?:every (?:(other) |({_COUNT}) )?months?|monthly|each month) on the last day"
        rf"|(?:on )?the last day of (?:each|every|the) month",
        text,
    ):
        return {"FREQ": "MONTHLY", "INTERVAL": _interval(match.group(1), match.group(2)), "BYMONTHDAY": "-1"}
    if match := re.fullmatch(rf"the (first|last) weekday {_EACH_MONTH}", text) or re.fullmatch(
        rf"(?:{_EVERY_MONTHS}) on the (first|last) weekday", text
    ):
        return {
            "FREQ": "MONTHLY",
            "BYDAY": _code_list(weekdays),
            "BYSETPOS": "1" if match.group(1) == "first" else "-1",
        }
    if match := re.fullmatch(rf"the ({_ORDINAL_WORDS}) ([a-z]+) {_EACH_MONTH}", text) or re.fullmatch(
        rf"(?:every month|each month|monthly) on the ({_ORDINAL_WORDS}) ([a-z]+)", text
    ):
        return {"FREQ": "MONTHLY", "BYDAY": _ordinal_weekdays(match.group(1), match.group(2))}
    if match := re.fullmatch(rf"the ((?:{_ORDINAL_WORD}){_SEPARATOR}{_ORDINAL_WORDS}) ([a-z]+)", text):
        # Two or more positions of one weekday can only mean each month; one position alone could be a single day.
        return {"FREQ": "MONTHLY", "BYDAY": _ordinal_weekdays(match.group(1), match.group(2))}
    if match := re.fullmatch(rf"every (?:(other) |({_COUNT}) )?months?|monthly|each month", text):
        return {"FREQ": "MONTHLY", "INTERVAL": _interval(match.group(1), match.group(2)), **_month_day(day.day)}
    if match := re.fullmatch(rf"every (?:(other) |({_COUNT}) )?months? on (?:the )?({_DAY_NUMBERS})", text) or (
        re.fullmatch(rf"(monthly|each month) on (?:the )?({_DAY_NUMBERS})", text)
    ):
        groups = match.groups()
        every_other, count = (groups[0], groups[1]) if len(groups) == 3 else (None, None)
        return {
            "FREQ": "MONTHLY",
            "INTERVAL": _interval(every_other, count),
            **_month_day_parts(_days_of_month(groups[-1])),
        }
    if match := re.fullmatch(rf"(?:on )?(?:the )?({_SUFFIXED_DAYS})(?: of (?:each|every|the) month)?", text):
        return {"FREQ": "MONTHLY", **_month_day_parts(_days_of_month(match.group(1)))}
    if match := re.fullmatch(rf"{_YEARLY} on the ({_ORDINAL_WORD}) ([a-z]+) (?:in|of) ({_MONTH_NAME})", text) or (
        re.fullmatch(rf"the ({_ORDINAL_WORD}) ([a-z]+) (?:in|of) ({_MONTH_NAME}) (?:each|every) year", text)
    ):
        weekday = _weekday_of(match.group(2), False)
        if weekday is None:
            raise ValueError("The written weekday is not clear")
        return {
            "FREQ": "YEARLY",
            "BYMONTH": str(MONTHS.index(match.group(3)) + 1),
            "BYDAY": f"{ORDINALS[match.group(1)]}{CODES[weekday]}",
        }
    if match := re.fullmatch(rf"(?:{_YEARLY} on|every) ({_MONTH_NAME}) (\d{{1,2}})(st|nd|rd|th)?", text):
        month, number = MONTHS.index(match.group(1)) + 1, int(match.group(2))
        date(2000, month, number)
        _ordinal_ok(number, match.group(3))
        return {"FREQ": "YEARLY", "BYMONTH": str(month), **_month_day(number)}
    if re.fullmatch(_YEARLY, text):
        return {"FREQ": "YEARLY", "BYMONTH": str(day.month), **_month_day(day.day)}
    raise ValueError("The phrase is outside the supported grammar")


def rule_from_phrase(phrase: str, start: date | datetime) -> str | Unknown:
    """Return an RRULE value (without the `RRULE:` prefix) or `Unknown`."""
    try:
        day = _start_date(start)
        if not isinstance(phrase, str):
            raise ValueError("The phrase must be text")
        text = " ".join(phrase.strip().casefold().rstrip(".").split())
        parts = _from_words(text, day)
        if parts.get("INTERVAL") == "1":
            del parts["INTERVAL"]
        _check_start(parts, day)
        return _serialize(parts)
    except StartMismatch as error:
        return Unknown(str(error), status="off_start")
    except (ValueError, OverflowError, KeyError) as error:
        return Unknown(str(error))


def _weekday_names(byday: str) -> list[str]:
    listed = byday.split(",")
    if not all(item in CODES for item in listed) or len(set(listed)) != len(listed):
        raise ValueError("This weekday combination is unsupported")
    return sorted(listed, key=CODES.index)


def rule_shape(rrule: str, start: date | datetime) -> Shape | Unknown:
    """Describe a supported rule as data; any restriction outside the grammar makes it `Unknown`, never dropped."""
    try:
        day = _start_date(start)
        if not isinstance(rrule, str):
            raise ValueError("The rule must be text")
        text = rrule.strip().upper().removeprefix("RRULE:")
        parts: dict[str, str] = {}
        for component in text.split(";"):
            if component.count("=") != 1:
                raise ValueError("A rule component is malformed")
            key, value = component.split("=")
            if key in parts or not value:
                raise ValueError("A rule component is duplicated or empty")
            parts[key] = value
        if set(parts) - {"FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST", "BYSETPOS"}:
            raise ValueError("The rule contains unsupported restrictions; none were discarded")
        frequency = parts.get("FREQ")
        if frequency not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}:
            raise ValueError("The frequency is missing or unsupported")
        raw_interval = parts.pop("INTERVAL", "1")
        if not re.fullmatch(r"[1-9]\d*", raw_interval):
            raise ValueError("INTERVAL must be a positive integer")
        interval = int(raw_interval)
        if parts.pop("WKST", "MO") != "MO":
            raise ValueError("Only the default Monday week start is supported")
        position = None
        if "BYSETPOS" in parts and "BYMONTHDAY" not in parts:
            if frequency != "MONTHLY" or parts["BYSETPOS"] not in {"1", "2", "3", "4", "5", "-1"}:
                raise ValueError("This BYSETPOS combination is unsupported")
            if parts.get("BYDAY") == _code_list(list(range(5))) and parts["BYSETPOS"] in {"1", "-1"}:
                # The first or last weekday of the month.
                position = "first" if parts["BYSETPOS"] == "1" else "last"
            elif parts.get("BYDAY") in CODES:
                # A single weekday with a position is the same as an ordinal weekday.
                parts["BYDAY"] = parts.pop("BYSETPOS") + parts["BYDAY"]
            else:
                raise ValueError("This BYSETPOS combination is unsupported")
        keys = set(parts) - {"FREQ"}
        if frequency == "DAILY" and not keys:
            shape = Shape("daily", {"interval": interval})
        elif frequency == "WEEKLY" and keys <= {"BYDAY"}:
            names = _weekday_names(parts.setdefault("BYDAY", CODES[day.weekday()]))
            parts["BYDAY"] = ",".join(names)
            if names == list(CODES[:5]) and interval == 1:
                shape = Shape("weekdays")
            elif len(names) == 1:
                shape = Shape("weekly", {"interval": interval, "weekday": WEEKDAYS[CODES.index(names[0])]})
            else:
                weekdays = [WEEKDAYS[CODES.index(name)] for name in names]
                shape = Shape("weekly_days", {"interval": interval, "weekdays": weekdays})
        elif frequency == "MONTHLY" and position is not None and interval == 1 and keys == {"BYDAY", "BYSETPOS"}:
            shape = Shape("monthly_weekday", {"position": position})
        elif frequency == "MONTHLY" and keys <= {"BYMONTHDAY", "BYSETPOS"}:
            parts.setdefault("BYMONTHDAY", str(day.day))
            days = _month_days(parts)
            if days == [-1]:
                shape = Shape("monthly_last_day", {"interval": interval})
            elif len(days) == 1:
                shape = Shape("monthly_day", {"interval": interval, "day": days[0]})
            else:
                shape = Shape("monthly_days", {"interval": interval, "days": days})
        elif frequency == "MONTHLY" and interval == 1 and keys == {"BYDAY"}:
            shape = _ordinal_shape(parts)
        elif frequency == "YEARLY" and interval == 1 and keys <= {"BYMONTH", "BYMONTHDAY", "BYSETPOS"}:
            parts.setdefault("BYMONTH", str(day.month))
            parts.setdefault("BYMONTHDAY", str(day.day))
            month, days = int(parts["BYMONTH"]), _month_days(parts)
            if len(days) != 1 or days[0] == -1:
                raise ValueError("The yearly day is unsupported")
            date(2000, month, days[0])
            shape = Shape("yearly", {"month": MONTHS[month - 1], "day": days[0]})
        elif frequency == "YEARLY" and interval == 1 and keys == {"BYMONTH", "BYDAY"}:
            month = int(parts["BYMONTH"])
            date(2000, month, 1)
            found = _ordinal_shape(parts)
            if found.kind != "monthly_nth":
                raise ValueError("The yearly weekday is unsupported")
            shape = Shape("yearly_nth", {"month": MONTHS[month - 1], **found.values})
        else:
            raise ValueError("The rule combination is outside the supported grammar")
        _check_start(parts, day)
        return shape
    except StartMismatch as error:
        return Unknown(str(error), status="off_start")
    except (ValueError, OverflowError, KeyError) as error:
        return Unknown(str(error))


def _ordinal_shape(parts: dict[str, str]) -> Shape:
    """The shape of `BYDAY` with one or more ordinals of one weekday (the same list, in a fixed order, goes back into
    `parts`)."""
    found = []
    for item in parts["BYDAY"].split(","):
        match = re.fullmatch(r"(1|2|3|4|5|-1)(MO|TU|WE|TH|FR|SA|SU)", item)
        if not match:
            raise ValueError("The ordinal weekday is unsupported")
        found.append((int(match.group(1)), match.group(2)))
    if len({code for _, code in found}) != 1 or len({number for number, _ in found}) != len(found):
        raise ValueError("The ordinal weekdays are unsupported")
    found.sort(key=lambda item: (item[0] < 0, item[0]))
    parts["BYDAY"] = ",".join(f"{number}{code}" for number, code in found)
    names = [next(name for name, value in ORDINALS.items() if value == number) for number, _ in found]
    weekday = WEEKDAYS[CODES.index(found[0][1])]
    if len(names) == 1:
        return Shape("monthly_nth", {"ordinal": names[0], "weekday": weekday})
    return Shape("monthly_nths", {"ordinals": names, "weekday": weekday})
