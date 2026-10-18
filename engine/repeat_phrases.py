"""Repeat rules from plain phrases, and rules back to data the screen words from the wording sheet.

`rule_from_phrase` reads a bounded English grammar ("every other Tuesday", "the first Monday of each month",
"weekdays", "every 3 months on the 15th", "yearly on March 3") into an iCalendar RRULE value. A day of the month past
the 28th means that day or the month's last day when the month is shorter, written as the standard
`BYMONTHDAY=28,...,N;BYSETPOS=-1`, so "the 31st" never skips a short month; February 29 likewise falls on the 28th in
other years. `rule_shape` turns a supported rule into a `Shape(kind, values)`; nothing here is on-screen text.
Anything outside the grammar, or a start that doesn't fall on the rule, is `Unknown` with a reason, never a guess.
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
_WEEKDAY = "(" + "|".join(WEEKDAYS) + ")"


@dataclass(frozen=True)
class Unknown:
    reason: str
    status: str = "unknown"


@dataclass(frozen=True)
class Shape:
    kind: str  # daily, weekdays, weekly, monthly_day, monthly_nth, yearly
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


def _day_of(parts: dict[str, str]) -> int:
    """The day a BYMONTHDAY means: the single day, or the last of a clamped run with BYSETPOS=-1."""
    days = parts["BYMONTHDAY"].split(",")
    if len(days) == 1 and "BYSETPOS" not in parts:
        return int(days[0])
    expected = [str(day) for day in range(28, int(days[-1]) + 1)]
    if days != expected or parts.get("BYSETPOS") != "-1" or int(days[-1]) > 31:
        raise ValueError("This month-day combination is unsupported")
    return int(days[-1])


def _check_start(parts: dict[str, str], start: date) -> None:
    if "BYMONTH" in parts and start.month != int(parts["BYMONTH"]):
        raise ValueError("Start does not match the stated month; choose the first occurrence explicitly")
    if "BYMONTHDAY" in parts:
        wanted = _day_of(parts)
        if start.day != min(wanted, monthrange(start.year, start.month)[1]):
            raise ValueError("Start does not match the stated month day; choose the first occurrence explicitly")
    byday = parts.get("BYDAY")
    if byday is None or byday == "MO,TU,WE,TH,FR":
        if byday and start.weekday() >= 5:
            raise ValueError("Start is not a weekday")
        return
    match = re.fullmatch(r"(-?\d+)?(MO|TU|WE|TH|FR|SA|SU)", byday)
    if not match or CODES[start.weekday()] != match.group(2):
        raise ValueError("Start does not match the stated weekday; choose the first occurrence explicitly")
    if match.group(1):
        ordinal = int(match.group(1))
        last = monthrange(start.year, start.month)[1]
        if not ((start.day - 1) // 7 + 1 == ordinal if ordinal > 0 else start.day + 7 > last):
            raise ValueError("Start does not match the stated ordinal weekday")


def _serialize(parts: dict[str, str]) -> str:
    order = ("FREQ", "INTERVAL", "BYMONTH", "BYMONTHDAY", "BYDAY", "BYSETPOS")
    return ";".join(f"{key}={parts[key]}" for key in order if key in parts)


def _ordinal_ok(number: int, suffix: str | None) -> None:
    if suffix and _suffix(number) != suffix:
        raise ValueError("The written ordinal is inconsistent with its number")


def rule_from_phrase(phrase: str, start: date | datetime) -> str | Unknown:
    """Return an RRULE value (without the `RRULE:` prefix) or `Unknown`."""
    try:
        day = _start_date(start)
        if not isinstance(phrase, str):
            raise ValueError("The phrase must be text")
        text = " ".join(phrase.strip().casefold().split())
        if text in {"weekdays", "every weekday"}:
            parts = {"FREQ": "WEEKLY", "BYDAY": "MO,TU,WE,TH,FR"}
        elif text in {"daily", "every day"}:
            parts = {"FREQ": "DAILY"}
        elif match := re.fullmatch(r"every ([1-9]\d*) days?", text):
            parts = {"FREQ": "DAILY", "INTERVAL": match.group(1)}
        elif match := re.fullmatch(rf"every (?:(other|[1-9]\d* weeks? on) )?{_WEEKDAY}", text):
            interval = "2" if match.group(1) == "other" else (match.group(1).split()[0] if match.group(1) else "1")
            parts = {"FREQ": "WEEKLY", "INTERVAL": interval, "BYDAY": CODES[WEEKDAYS.index(match.group(2))]}
        elif text in {"weekly", "every week"}:
            parts = {"FREQ": "WEEKLY", "BYDAY": CODES[day.weekday()]}
        elif match := re.fullmatch(rf"the ({'|'.join(ORDINALS)}) {_WEEKDAY} of each month", text):
            parts = {"FREQ": "MONTHLY", "BYDAY": f"{ORDINALS[match.group(1)]}{CODES[WEEKDAYS.index(match.group(2))]}"}
        elif match := re.fullmatch(r"every (?:(\d+) months?|month) on (?:the )?(\d{1,2})(st|nd|rd|th)?", text):
            interval, number = int(match.group(1) or "1"), int(match.group(2))
            if interval < 1 or not 1 <= number <= 31:
                raise ValueError("The month interval or day is invalid")
            _ordinal_ok(number, match.group(3))
            parts = {"FREQ": "MONTHLY", "INTERVAL": str(interval), **_month_day(number)}
        elif text in {"monthly", "every month"}:
            parts = {"FREQ": "MONTHLY", **_month_day(day.day)}
        elif match := re.fullmatch(r"(?:yearly|every year) on ([a-z]+) (\d{1,2})(st|nd|rd|th)?", text):
            if match.group(1) not in MONTHS:
                raise ValueError("The written month is not supported")
            month, number = MONTHS.index(match.group(1)) + 1, int(match.group(2))
            date(2000, month, number)
            _ordinal_ok(number, match.group(3))
            parts = {"FREQ": "YEARLY", "BYMONTH": str(month), **_month_day(number)}
        elif text in {"yearly", "every year"}:
            parts = {"FREQ": "YEARLY", "BYMONTH": str(day.month), **_month_day(day.day)}
        else:
            raise ValueError("The phrase is outside the supported grammar")
        if parts.get("INTERVAL") == "1":
            del parts["INTERVAL"]
        _check_start(parts, day)
        return _serialize(parts)
    except (ValueError, OverflowError) as error:
        return Unknown(str(error))


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
        if "BYSETPOS" in parts and "BYMONTHDAY" not in parts:
            # A single weekday with a position is the same as an ordinal weekday.
            if frequency != "MONTHLY" or parts.get("BYDAY") not in CODES:
                raise ValueError("This BYSETPOS combination is unsupported")
            if parts["BYSETPOS"] not in {"1", "2", "3", "4", "5", "-1"}:
                raise ValueError("The ordinal position is unsupported")
            parts["BYDAY"] = parts.pop("BYSETPOS") + parts["BYDAY"]
        keys = set(parts) - {"FREQ"}
        if frequency == "DAILY" and not keys:
            shape = Shape("daily", {"interval": interval})
        elif frequency == "WEEKLY" and keys <= {"BYDAY"}:
            byday = parts.setdefault("BYDAY", CODES[day.weekday()])
            listed = byday.split(",")
            if sorted(listed, key=CODES.index) == list(CODES[:5]) and interval == 1:
                parts["BYDAY"] = "MO,TU,WE,TH,FR"
                shape = Shape("weekdays")
            elif byday in CODES:
                shape = Shape("weekly", {"interval": interval, "weekday": WEEKDAYS[CODES.index(byday)]})
            else:
                raise ValueError("This weekday combination is unsupported")
        elif frequency == "MONTHLY" and keys <= {"BYMONTHDAY", "BYSETPOS"}:
            parts.setdefault("BYMONTHDAY", str(day.day))
            number = _day_of(parts)
            if not 1 <= number <= 31:
                raise ValueError("The month day is unsupported")
            shape = Shape("monthly_day", {"interval": interval, "day": number})
        elif frequency == "MONTHLY" and interval == 1 and keys == {"BYDAY"}:
            match = re.fullmatch(r"(1|2|3|4|5|-1)(MO|TU|WE|TH|FR|SA|SU)", parts["BYDAY"])
            if not match:
                raise ValueError("The ordinal weekday is unsupported")
            ordinal = next(name for name, value in ORDINALS.items() if value == int(match.group(1)))
            shape = Shape("monthly_nth", {"ordinal": ordinal, "weekday": WEEKDAYS[CODES.index(match.group(2))]})
        elif frequency == "YEARLY" and interval == 1 and keys <= {"BYMONTH", "BYMONTHDAY", "BYSETPOS"}:
            parts.setdefault("BYMONTH", str(day.month))
            parts.setdefault("BYMONTHDAY", str(day.day))
            month, number = int(parts["BYMONTH"]), _day_of(parts)
            date(2000, month, number)
            shape = Shape("yearly", {"month": MONTHS[month - 1], "day": number})
        else:
            raise ValueError("The rule combination is outside the supported grammar")
        _check_start(parts, day)
        return shape
    except (ValueError, OverflowError, KeyError) as error:
        return Unknown(str(error))
