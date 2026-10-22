"""Resolve a small, explicit vocabulary of due phrases without inferring context.

Date ranges are inclusive. Weeks run Monday through Sunday. A bare weekday is
strictly future, and inexact when said on that weekday; past this-week dates are read forward and marked
inexact.
Early next week means its first three configured working days. Part-of-day
phrases identify a date but leave the time unset. Explicit times are local wall
times. A leading lead word ("on", "due", "due by") is read past, and an ordinal day ("the 25th") is the next day of the
month with that number. Unknown phrases stay unresolved. The words of the language (lead words, ordinal endings, the
words that make a due a condition, which of those wait for something to happen, which name an entry, the words of the
day-and-time phrases, number words, time zone abbreviations and holiday names) are arguments, with English defaults
here that the language settings override. Holidays come from a dated data file, one calendar per language tag.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DEFAULT_LEAD_WORDS = ("by", "on", "due", "due on", "due by", "on or before", "no later than", "not later than")
DEFAULT_ORDINAL_SUFFIXES = ("st", "nd", "rd", "th")
DEFAULT_CONDITION_WORDS = (
    *("once", "after", "before", "when", "whenever", "until", "till", "if", "unless", "upon", "as soon as"),
    *("of receiving", "of receipt", "sometime", "soon", "eventually"),
)
#: The condition words that wait for something to happen: a due with one is on hold from the start. The rest of the
#: condition words only leave the date open.
DEFAULT_HOLD_WORDS = (
    *("once", "after", "when", "whenever", "until", "till", "if", "unless", "upon", "as soon as"),
    *("of receiving", "of receipt"),
)
#: The condition words after which a calendar entry may be named: a due "before the print sync" is due at that entry.
DEFAULT_BEFORE_WORDS = ("before",)
#: The verbs a task's title starts with: a plain calendar entry whose first word is one is offered as a to-do.
DEFAULT_TASK_VERBS = (
    *("pay", "send", "call", "email", "text", "book", "buy", "order", "renew", "submit", "file", "return", "pick"),
    *("drop", "cancel", "confirm", "schedule", "register", "sign", "review", "write", "finish", "prepare", "collect"),
    *("fix", "clean", "pack", "check", "ask", "remind", "reply", "print", "post", "pickup", "organize", "arrange"),
)
#: The words of the day-and-time phrases the date reader knows, by what they mean. Each is a list of whole phrases; the
#: language settings override any of them.
DEFAULT_PHRASE_WORDS: dict[str, tuple[str, ...]] = {
    "day_after_tomorrow": ("day after tomorrow",),
    "later_today": ("later today",),
    "tonight": ("tonight",),
    "noon": ("noon", "midday"),
    "midnight": ("midnight",),
    "first_thing": ("first thing",),
    "end_of_month": ("end of month", "end of the month", "end of this month"),
    "end_of_next_month": ("end of next month", "end of the next month"),
    "this_weekend": ("this weekend",),
    "within": ("within",),
    "hours": ("hours", "hour"),
    "days": ("days", "day"),
    "working_days": ("working days", "working day", "business days", "business day"),
}
#: The number words read in "within <n> hours".
DEFAULT_NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}
#: Time zone abbreviations and plain names to the zone they name, for a time like "5pm ET" or "5pm Central".
DEFAULT_TIME_ZONES: dict[str, str] = {
    **dict.fromkeys(("ET", "EST", "EDT", "Eastern", "Eastern time"), "America/New_York"),
    **dict.fromkeys(("CT", "CST", "CDT", "Central", "Central time"), "America/Chicago"),
    **dict.fromkeys(("MT", "MST", "MDT", "Mountain", "Mountain time"), "America/Denver"),
    **dict.fromkeys(("PT", "PST", "PDT", "Pacific", "Pacific time"), "America/Los_Angeles"),
    **dict.fromkeys(("UTC", "GMT"), "UTC"),
    "BST": "Europe/London",
}
HOLIDAYS_FILE = Path(__file__).parent / "defaults" / "holidays.yaml"


@dataclass(frozen=True)
class Holiday:
    """A named day of the year: a fixed month and day, or the nth weekday of a month (nth -1 is the last)."""

    names: tuple[str, ...]
    month: int
    day: int | None = None
    weekday: int | None = None
    nth: int | None = None


def _plain(text: str) -> str:
    """Lower case, one space between words, and the typographic apostrophe written plain."""
    return " ".join(text.lower().replace("\u2019", "'").split())


@cache
def _holiday_file() -> dict[str, Any]:
    return (yaml.safe_load(HOLIDAYS_FILE.read_text(encoding="utf-8")) or {}).get("calendars") or {}


def holiday_calendars() -> list[str]:
    """The language tags the shipped holiday data has a calendar for."""
    return sorted(str(tag) for tag in _holiday_file())


@cache
def load_holidays(calendar_tag: str) -> tuple[Holiday, ...]:
    """The holidays of a calendar (a language tag such as en-US) from the shipped data; none for a tag with no
    calendar."""
    entries = _holiday_file().get(calendar_tag.replace("_", "-")) or []
    return tuple(
        Holiday(
            tuple(_plain(str(n)) for n in entry["names"]),
            int(entry["month"]),
            entry.get("day"),
            entry.get("weekday"),
            entry.get("nth"),
        )
        for entry in entries
    )


def holiday_date(holiday: Holiday, year: int) -> date:
    """The day a holiday falls on in a year."""
    if holiday.day is not None:
        return date(year, holiday.month, holiday.day)
    first = date(year, holiday.month, 1)
    if holiday.nth is not None and holiday.nth > 0:
        found = first + timedelta(days=(holiday.weekday - first.weekday()) % 7 + 7 * (holiday.nth - 1))
    else:
        last = date(year, holiday.month, calendar.monthrange(year, holiday.month)[1])
        found = last - timedelta(days=(last.weekday() - holiday.weekday) % 7)
    if found.month != holiday.month:
        raise ValueError("The holiday has no such day in that year.")
    return found


def after_marker(phrase: str, markers: Sequence[str]) -> str | None:
    """The words that follow the first marker found in the phrase (as whole words, ignoring case), or None when no
    marker is there: "before the print sync" gives "the print sync"."""
    value = " ".join(phrase.lower().split())
    found = [
        match
        for marker in markers
        if marker.strip()
        and (match := re.search(rf"(?<![\w'])(?:{re.escape(marker.lower())})(?![\w'])\s*(.*)$", value))
    ]
    return min(found, key=lambda m: m.start())[1] if found else None


def names_title(phrase: str, title: str) -> bool:
    """Whether a title's words appear in the phrase, whole and in order, ignoring case and punctuation."""
    wanted = re.findall(r"[\w']+", title.casefold())
    words = re.findall(r"[\w']+", phrase.casefold())
    return bool(wanted) and any(words[i : i + len(wanted)] == wanted for i in range(len(words) - len(wanted) + 1))


def named_entry(entries: Iterable[Any], phrase: str, today: str) -> Any | None:
    """The one calendar entry still ahead that the phrase names, or None when it names none or several. An entry is
    named when its title's words appear in the phrase whole and in order; a title that is part of a longer matching one
    is the same meeting named less fully; of several entries with the same title the soonest is the one meant. Entries
    called off, or that started before `today` (an ISO day), are not named."""
    titles: dict[str, list[Any]] = {}
    for entry in entries:
        data = entry.data
        if data.get("cancelled") or str(data.get("start") or "")[:10] < today:
            continue
        if names_title(phrase, str(data["title"])):
            titles.setdefault(str(data["title"]).casefold(), []).append(entry)
    kept = [t for t in titles if not any(t != o and names_title(o, t) for o in titles)]
    if len(kept) != 1:
        return None
    return min(titles[kept[0]], key=lambda e: (str(e.data["start"]), e.id))


def is_condition(phrase: str, markers: Sequence[str]) -> bool:
    """Whether the words tie a due to something that happens, or leave it open ("once the keys arrive", "after the
    workshop", "soon"): a marker, as whole words and ignoring case, appears in them. Such a due has no date."""
    value = " ".join(phrase.lower().split())
    return any(
        re.search(rf"(?<![\w'])(?:{re.escape(marker.lower())})(?![\w'])", value) for marker in markers if marker.strip()
    )


@dataclass(frozen=True)
class Due:
    start: date | None
    end: date | None
    time: time | None
    exact: bool
    note: str


def resolve(
    phrase: str,
    received: datetime,
    tz: str | tzinfo,
    workweek: tuple[int, ...] = (0, 1, 2, 3, 4),
    *,
    locale: str = "en_US",
    end_of_day: time = time(17),
    lead_words: Sequence[str] = DEFAULT_LEAD_WORDS,
    ordinal_suffixes: Sequence[str] = DEFAULT_ORDINAL_SUFFIXES,
    phrase_words: Mapping[str, Sequence[str]] | None = None,
    number_words: Mapping[str, int] | None = None,
    time_zones: Mapping[str, str] | None = None,
    sender_zone: str | tzinfo | None = None,
    holidays: Sequence[Holiday] | None = None,
) -> Due:
    """Resolve against the received instant converted to tz, never the clock.

    locale must be en_US or en_GB (hyphens are also accepted); it sets the order of a numeric date. A numeric date
    may leave the year out (the next occurrence is read); a two-digit year is refused. ambiguous dates are not
    retried in another order.
    end_of_day is a local wall time, defaulting to 17:00. Working-day counts
    exclude the received day and weekends defined by workweek, but not holidays. "Within <n> days" counts calendar
    days; only "within <n> working days" skips weekends. phrase_words, number_words, time_zones (abbreviation or
    plain name to zone name) and holidays default to the English words, and to the shipped calendar of the locale.
    sender_zone is the zone the message's sender is known to be in: a short zone word the time_zones setting doesn't
    name is read in it when it goes by that word on the date, and otherwise the words are left to check.
    Invalid configuration raises ValueError; unsupported phrases return Due
    with no dates. exact is true only for one definite date, optionally a time.
    """
    if received.tzinfo is None or received.utcoffset() is None:
        raise ValueError("received must be an aware datetime")
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    if not isinstance(zone, tzinfo):
        raise ValueError("tz must be a time zone or IANA zone name")
    locale = locale.replace("-", "_")
    if locale not in {"en_US", "en_GB"}:
        raise ValueError("locale must be en_US or en_GB")
    if not workweek or any(type(day) is not int or not 0 <= day <= 6 for day in workweek):
        raise ValueError("workweek must contain weekdays numbered 0 through 6")
    if len(set(workweek)) != len(workweek):
        raise ValueError("workweek must not contain duplicate days")
    if not isinstance(end_of_day, time) or end_of_day.tzinfo is not None:
        raise ValueError("end_of_day must be a local time without a time zone")
    weekdays = sorted(workweek)
    today = received.astimezone(zone).date()
    monday = today - timedelta(days=today.weekday())
    value = _plain(" ".join(phrase.strip().split()))
    words = {
        concept: {_plain(w) for w in (phrase_words or {}).get(concept, default) if w.strip()}
        for concept, default in DEFAULT_PHRASE_WORDS.items()
    }
    numbers = {_plain(w): n for w, n in (DEFAULT_NUMBER_WORDS if number_words is None else number_words).items()}
    zones = {_plain(a): z for a, z in (DEFAULT_TIME_ZONES if time_zones is None else time_zones).items() if a.strip()}
    calendar_days = load_holidays(locale) if holidays is None else tuple(holidays)
    named_days = {name: day for day in calendar_days for name in day.names}

    def sub(text: str) -> Due:
        """The same reading of other words."""
        return resolve(
            text,
            received,
            zone,
            workweek,
            locale=locale,
            end_of_day=end_of_day,
            lead_words=lead_words,
            ordinal_suffixes=ordinal_suffixes,
            phrase_words=phrase_words,
            number_words=number_words,
            time_zones=time_zones,
            sender_zone=sender_zone,
            holidays=holidays,
        )

    def named(concept: str, text: str) -> bool:
        return text in words[concept] or text.removeprefix("the ") in words[concept]

    # Common short forms read as their full words.
    value = re.sub(r"\b(?:eod|cob)\b", "end of day", value)
    value = re.sub(
        r"\b(mon|tues?|wed|thur?s?|fri|sat|sun)\.?(?=$|[ ,])",
        lambda found: {
            "mon": "monday",
            "tue": "tuesday",
            "tues": "tuesday",
            "wed": "wednesday",
            "thu": "thursday",
            "thur": "thursday",
            "thurs": "thursday",
            "fri": "friday",
            "sat": "saturday",
            "sun": "sunday",
        }[found[1]],
        value,
    )

    # A lead word or two ("on", "due", "due by") says only that a date follows.
    leads = sorted({" ".join(w.lower().split()) for w in lead_words if w.strip()}, key=len, reverse=True)
    for _ in range(2):
        lead = next((w for w in leads if value.startswith(w + " ")), None)
        if lead is None:
            break
        value = value[len(lead) :].lstrip()
    suffixes = "|".join(re.escape(s.lower()) for s in ordinal_suffixes if s.strip())
    ordinal = rf"(\d{{1,2}})(?:{suffixes})" if suffixes else None

    def unknown(note: str) -> Due:
        return Due(None, None, None, False, note)

    def single(day: date, note: str, at: time | None = None, exact: bool = True) -> Due:
        return Due(day, day, at, exact, note)

    def next_occurrence(month: int, day: int) -> Due:
        """The next month-and-day on or after the received date, with the year left out."""
        date(2000, month, day)  # a leap year validates the month and day before seeking the occurrence
        for candidate_year in range(today.year, min(today.year + 9, 10000)):
            try:
                candidate = date(candidate_year, month, day)
            except ValueError:
                continue
            if candidate >= today:
                note = "Year omitted; read as the next occurrence on or after the received date."
                if (candidate - today).days > 180:
                    # A date that has just passed is more likely meant than one most of a year away.
                    return single(
                        candidate, note + " It is far ahead, so it may mean a date already past.", exact=False
                    )
                return single(candidate, note)
        return unknown("No representable future occurrence exists.")

    noon = "|".join(re.escape(w) for w in sorted(words["noon"], key=len, reverse=True)) or "(?!)"
    midnight = "|".join(re.escape(w) for w in sorted(words["midnight"], key=len, reverse=True)) or "(?!)"
    clock_text = rf"{noon}|{midnight}|\d{{1,2}}(?::\d{{2}})?\s*(?:a\.?m\.?|p\.?m\.?)"
    base = value.removeprefix("by ").replace("the end of the day", "end of day")

    # A time with a zone name ("5pm ET", "5pm Central time") is read in that zone and given in the person's own. A
    # short word the setting doesn't name is read in the sender's zone when that zone goes by it on that date.
    words_in_base = base.split(" ")
    zone_key = next(
        (
            key
            for count in (3, 2, 1)
            if len(words_in_base) > count and (key := " ".join(words_in_base[-count:])) in zones
        ),
        None,
    )
    unnamed = (
        words_in_base[-1]
        if zone_key is None
        and sender_zone is not None
        and len(words_in_base) > 1
        and re.fullmatch(r"[a-z]{2,5}", words_in_base[-1])
        else None
    )
    label = zone_key or unnamed or ""
    text_before = " ".join(words_in_base[: len(words_in_base) - len(label.split())]) if label else ""
    if label and re.search(rf"(?:{clock_text})$", text_before):
        inner = sub(text_before)
        if zone_key is not None:
            try:
                stated = ZoneInfo(zones[zone_key])
            except (ZoneInfoNotFoundError, ValueError):
                return unknown("The time zone abbreviation names no known zone; no date was guessed.")
        else:
            try:
                theirs = ZoneInfo(sender_zone) if isinstance(sender_zone, str) else sender_zone
            except (ZoneInfoNotFoundError, ValueError):
                theirs = None
            if inner.start is None or inner.time is None or theirs is None:
                return unknown("A time zone needs a single understood date and clock time; no date was guessed.")
            if (datetime.combine(inner.start, inner.time, tzinfo=theirs).tzname() or "").lower() != label:
                return unknown("The time zone abbreviation names no known zone; no date was guessed.")
            stated = theirs
        if inner.start is None or inner.start != inner.end or inner.time is None:
            return unknown("A time zone needs a single understood date and clock time; no date was guessed.")
        there = datetime.combine(inner.start, inner.time, tzinfo=stated).astimezone(zone)
        # A day word means the day where the person is; another day in the stated zone makes the reading doubtful.
        same_day = received.astimezone(stated).date() == today
        return Due(
            there.date(),
            there.date(),
            there.time().replace(second=0, microsecond=0),
            inner.exact and same_day,
            inner.note + " Clock time given in a named time zone, converted to the local one.",
        )
    # A clock time before its day ("noon tomorrow", "5pm Friday") is the same words in the order read below.
    clock_first = re.fullmatch(rf"(?:at )?({clock_text}) (?:on )?(.+)", base)
    if clock_first and not re.search(rf"(?:{clock_text})$", clock_first[2]):
        return sub(f"{clock_first[2]} {clock_first[1]}")
    # A bare hour with "tonight" is that evening ("8 tonight", "tonight at 8").
    tonight = "|".join(re.escape(w) for w in sorted(words["tonight"], key=len, reverse=True)) or "(?!)"
    if match := re.fullmatch(
        rf"(?:at )?(\d{{1,2}})(?::(\d{{2}}))? ({tonight})|({tonight}) (?:at )?(\d{{1,2}})(?::(\d{{2}}))?", base
    ):
        hour, minute = (match[1], match[2]) if match[1] else (match[5], match[6])
        if not 5 <= int(hour) <= 11 or int(minute or 0) > 59:
            return unknown("A bare hour is not read as an evening time here; no time was guessed.")
        return sub(f"today {hour}{':' + minute if minute else ''}pm")

    # Resolve time and part-of-day suffixes only when their date is understood.
    suffix = re.fullmatch(
        rf"(?:(.*?) (?:at |by )?)?({clock_text}|end of day|close of business)", base.removeprefix("at ")
    )
    if suffix:
        day_text, clock = suffix.groups()
        if clock in words["noon"]:
            at = time(12)
        elif clock in words["midnight"]:
            at = time(0)
        elif clock in {"end of day", "close of business"}:
            at = end_of_day
        else:
            clock_match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", clock)
            hour, minute, period = clock_match.groups()
            if not 1 <= int(hour) <= 12 or int(minute or 0) > 59:
                return unknown("Invalid clock time; no time was guessed.")
            at = time(int(hour) % 12 + 12 * int(period == "p"), int(minute or 0))
        if day_text in words["tonight"]:
            # A clock time settles which part of the day "tonight" means; midnight tonight is the start or the end.
            if clock in words["midnight"]:
                return unknown("Midnight tonight may mean the start or the end of the day; no date was guessed.")
            day_text = "today"
        resolved = sub(day_text or "today")
        if resolved.start is None or resolved.start != resolved.end or resolved.time is not None:
            return unknown("The clock time needs a single understood date; no date was guessed.")
        note = resolved.note + " Explicit local clock time."
        if clock in words["midnight"]:
            return Due(
                resolved.start, resolved.end, at, False, note + " Midnight may mean the start or the end of the day."
            )
        return Due(resolved.start, resolved.end, at, resolved.exact, note)
    if match := re.fullmatch(r"(?:end of day|close of business) (.+)", base):
        return sub(match[1] + " end of day")
    if match := re.fullmatch(r"(.+) (morning|evening)", base):
        resolved = sub(match[1])
        if resolved.start is None or resolved.start != resolved.end or resolved.time is not None:
            return unknown("Part of day needs a single understood date; no date was guessed.")
        return Due(resolved.start, resolved.end, None, False, resolved.note + " Part of day has no exact clock time.")
    value = base
    if match := re.fullmatch(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday),? (.+)", value):
        dated = sub(match[2])
        weekday_names = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        if dated.start is not None and dated.start == dated.end:
            if weekday_names[dated.start.weekday()] == match[1]:
                return dated
            return unknown("The weekday and the date disagree; no date was guessed.")

    if value in {"today", "tomorrow"}:
        day = today + timedelta(days=int(value == "tomorrow"))
        return single(day, "Calendar date in the message's local time zone.")
    if value in words["tonight"] or value in {"tomorrow morning", "tomorrow evening", "today morning", "today evening"}:
        day = today + timedelta(days=int(value.startswith("tomorrow")))
        return single(day, "Part of day stated; no exact clock time was supplied.", exact=False)
    if named("day_after_tomorrow", value):
        return single(today + timedelta(days=2), "Two calendar days after the local received date.")
    if named("later_today", value):
        return single(today, "Stays on the received date; no clock time was supplied.")
    for first in sorted(words["first_thing"], key=len, reverse=True):
        if value.startswith(first + " "):
            # The start of a day: the day is read as it would be alone, with no clock time.
            resolved = sub(value[len(first) :])
            if resolved.start is None or resolved.start != resolved.end or resolved.time is not None:
                return unknown("The start of a day needs a single understood date; no date was guessed.")
            return Due(resolved.start, resolved.end, None, resolved.exact, resolved.note + " Start of that day.")
    if value in {"by end of day", "end of day", "by the end of the day", "close of business", "by close of business"}:
        return single(today, "Uses the configured local end-of-day time; does not roll to another day.", end_of_day)

    if ordinal and (match := re.fullmatch(rf"(?:the )?{ordinal}", value)):
        number = int(match[1])
        if not 1 <= number <= 31:
            return unknown("Not a day of the month; no date was guessed.")
        for step in range(14):
            month_index = today.month - 1 + step
            try:
                candidate = date(today.year + month_index // 12, month_index % 12 + 1, number)
            except ValueError:
                continue  # that month has no such day
            if candidate >= today:
                if candidate.month == today.month:
                    return single(candidate, "The day of the month named, in the received month.")
                return single(
                    candidate,
                    "Read forward to the next month with that day of the month; it may mean a day already past.",
                    exact=False,
                )
        return unknown("No representable occurrence exists.")

    names = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    if match := re.fullmatch(r"(?:(this|next) )?([a-z]+)", value):
        qualifier, name = match.groups()
        if name in names:
            weekday = names[name]
            if qualifier:
                day = monday + timedelta(days=weekday + 7 * int(qualifier == "next"))
                note = "This means the current Monday–Sunday week; next means the following week."
                if qualifier == "next":
                    return single(
                        day, note + " People use next weekday both ways; following week was selected.", exact=False
                    )
                if day < today:
                    return single(
                        day + timedelta(days=7), note + " Read forward to the coming occurrence.", exact=False
                    )
            else:
                day = today + timedelta(days=(weekday - today.weekday()) % 7 or 7)
                note = "A bare weekday means its strictly next occurrence, not today."
                if weekday == today.weekday():
                    return single(day, note + " It was said on that weekday, so it may mean today.", exact=False)
            return single(day, note)

    if value in {"this week", "next week"}:
        offset = 7 * int(value == "next week")
        days = [monday + timedelta(days=offset + weekday) for weekday in weekdays]
        if value == "this week":
            days = [day for day in days if day >= today]
        if not days:
            return unknown("No configured working days remain this week; no rollover was inferred.")
        return Due(
            days[0], days[-1], None, False, "Working-day range; nonworking dates inside the bounds are excluded."
        )
    if value in {
        "end of the week",
        "the end of the week",
        "end of week",
        "by end of the week",
        "by the end of the week",
        "end of next week",
        "end of the next week",
    }:
        day = monday + timedelta(days=weekdays[-1] + 7 * int("next" in value))
        if day < today:
            return single(
                day + timedelta(days=7),
                "Read forward to the coming last working day; no clock time inferred.",
                exact=False,
            )
        return single(day, "Last configured working day of the stated week; no clock time inferred.")
    if named("end_of_month", value) or named("end_of_next_month", value):
        month_index = today.month - 1 + int(named("end_of_next_month", value))
        year, month = today.year + month_index // 12, month_index % 12 + 1
        return single(
            date(year, month, calendar.monthrange(year, month)[1]),
            "Last calendar day of the stated month; no clock time inferred.",
        )
    if named("this_weekend", value):
        return Due(
            monday + timedelta(days=5),
            monday + timedelta(days=6),
            None,
            False,
            "Saturday and Sunday of the current Monday–Sunday week; some count Friday evening as part of it.",
        )
    if value == "early next week":
        days = [monday + timedelta(days=7 + weekday) for weekday in weekdays[:3]]
        return Due(days[0], days[-1], None, False, "First three configured working days next week, or all if fewer.")
    if value == "next month":
        first = date(today.year + int(today.month == 12), today.month % 12 + 1, 1)
        following = date(first.year + int(first.month == 12), first.month % 12 + 1, 1)
        return Due(
            first, following - timedelta(days=1), None, False, "Whole next calendar month, not one month from now."
        )
    if value in {"in two weeks", "in 2 weeks"}:
        return single(today + timedelta(days=14), "Fourteen calendar days after the local received date.")
    within = "|".join(re.escape(w) for w in sorted(words["within"], key=len, reverse=True)) or "(?!)"
    count = "|".join(re.escape(w) for w in sorted(numbers, key=len, reverse=True))
    units = {
        unit: "|".join(re.escape(w) for w in sorted(words[unit], key=len, reverse=True)) or "(?!)"
        for unit in ("hours", "days", "working_days")
    }
    unit_text = "|".join(f"(?P<{unit}>{text})" for unit, text in units.items())
    if match := re.fullmatch(rf"(?:{within}) (\d+{'|' + count if count else ''}) (?:{unit_text})", value):
        amount = int(match[1]) if match[1].isdigit() else numbers[match[1]]
        if not 1 <= amount <= 1000:
            return unknown("That span is not read; no date was guessed.")
        if match["working_days"]:
            deadline = today
            remaining = amount
            while remaining:
                deadline += timedelta(days=1)
                if deadline.weekday() in weekdays:
                    remaining -= 1
            return Due(
                today,
                deadline,
                None,
                False,
                f"Inclusive range ending after {amount} working days; holidays are not known.",
            )
        if match["hours"]:
            deadline = (received.astimezone(zone) + timedelta(hours=amount)).date()
            return Due(
                today, deadline, None, False, f"From the received time to {amount} hours later, as a range of days."
            )
        return Due(
            today,
            today + timedelta(days=amount),
            None,
            False,
            f"Inclusive range ending {amount} calendar days after the received date.",
        )
    if value.removeprefix("the ") in named_days:
        holiday = named_days[value.removeprefix("the ")]
        for candidate_year in range(today.year, today.year + 3):
            try:
                candidate = holiday_date(holiday, candidate_year)
            except ValueError:
                continue
            if candidate >= today:
                note = "A named holiday, read as its next occurrence on or after the received date."
                if (candidate - today).days > 180:
                    return single(
                        candidate, note + " It is far ahead, so it may mean a date already past.", exact=False
                    )
                return single(candidate, note)
        return unknown("No representable occurrence exists.")

    explicit = value.removeprefix("by ")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", explicit):
            return single(date.fromisoformat(explicit), "Explicit ISO date.")
        if match := re.fullmatch(r"(\d{1,2})([/.-])(\d{1,2})\2(\d{4})", explicit):
            first, _, second, year = match.groups()
            month, day = (int(first), int(second)) if locale == "en_US" else (int(second), int(first))
            return single(date(int(year), month, day), f"Explicit numeric date interpreted using {locale}.")
        if match := re.fullmatch(r"(\d{1,2})/(\d{1,2})", explicit):
            first, second = match.groups()
            month, day = (int(first), int(second)) if locale == "en_US" else (int(second), int(first))
            return next_occurrence(month, day)
        months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        months.update({name[:3]: number for name, number in list(months.items())})
        months["sept"] = 9
        optional_ending = f"(?:{suffixes})?"
        if match := re.fullmatch(rf"([a-z]+)\.? (\d{{1,2}}){optional_ending}(?:,? (\d{{4}}))?", explicit):
            month_name, day, year = match.groups()
        elif match := re.fullmatch(
            rf"(?:the )?(\d{{1,2}}){optional_ending}(?: of)? ([a-z]+)\.?(?:,? (\d{{4}}))?", explicit
        ):
            day, month_name, year = match.groups()
        else:
            return unknown("No supported definite date; vague or event-relative phrases require clarification.")
        if month_name in months:
            month = months[month_name]
            if year is not None:
                return single(date(int(year), month, int(day)), "Explicit date with a written month.")
            return next_occurrence(month, int(day))
    except ValueError:
        return unknown("Invalid date for the selected locale; no alternative order was guessed.")
    return unknown("Unrecognized month; no date was guessed.")
