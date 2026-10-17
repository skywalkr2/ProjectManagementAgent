"""Resolve a small, explicit vocabulary of due phrases without inferring context.

Date ranges are inclusive. Weeks run Monday through Sunday. A bare weekday is
strictly future; past this-week dates are read forward and marked inexact.
Early next week means its first three configured working days. Part-of-day
phrases identify a date but leave the time unset. Explicit times are local wall
times. Unknown phrases stay unresolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo


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
) -> Due:
    """Resolve against the received instant converted to tz, never the clock.

    locale must be en_US or en_GB (hyphens are also accepted). Numeric dates
    require four-digit years; ambiguous dates are not retried in another order.
    end_of_day is a local wall time, defaulting to 17:00. Working-day counts
    exclude the received day and weekends defined by workweek, but not holidays.
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
    value = " ".join(phrase.strip().lower().split())
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

    def unknown(note: str) -> Due:
        return Due(None, None, None, False, note)

    def single(day: date, note: str, at: time | None = None, exact: bool = True) -> Due:
        return Due(day, day, at, exact, note)

    # Resolve time and part-of-day suffixes only when their date is understood.
    base = value.removeprefix("by ").replace("the end of the day", "end of day")
    suffix = re.fullmatch(
        r"(?:(.*?) (?:at |by )?)?(noon|midday|end of day|close of business|"
        r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?))",
        base.removeprefix("at "),
    )
    if suffix:
        day_text, clock = suffix.groups()
        if clock in {"noon", "midday"}:
            at = time(12)
        elif clock in {"end of day", "close of business"}:
            at = end_of_day
        else:
            clock_match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", clock)
            hour, minute, period = clock_match.groups()
            if not 1 <= int(hour) <= 12 or int(minute or 0) > 59:
                return unknown("Invalid clock time; no time was guessed.")
            at = time(int(hour) % 12 + 12 * int(period == "p"), int(minute or 0))
        resolved = resolve(day_text or "today", received, zone, workweek, locale=locale, end_of_day=end_of_day)
        if resolved.start is None or resolved.start != resolved.end:
            return unknown("The clock time needs a single understood date; no date was guessed.")
        return Due(resolved.start, resolved.end, at, resolved.exact, resolved.note + " Explicit local clock time.")
    if match := re.fullmatch(r"(?:end of day|close of business) (.+)", base):
        return resolve(match[1] + " end of day", received, zone, workweek, locale=locale, end_of_day=end_of_day)
    if match := re.fullmatch(r"(.+) (morning|evening)", base):
        resolved = resolve(match[1], received, zone, workweek, locale=locale, end_of_day=end_of_day)
        if resolved.start is None or resolved.start != resolved.end or resolved.time is not None:
            return unknown("Part of day needs a single understood date; no date was guessed.")
        return Due(resolved.start, resolved.end, None, False, resolved.note + " Part of day has no exact clock time.")
    value = base
    if match := re.fullmatch(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday),? (.+)", value):
        dated = resolve(match[2], received, zone, workweek, locale=locale, end_of_day=end_of_day)
        weekday_names = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        if dated.start is not None and dated.start == dated.end:
            if weekday_names[dated.start.weekday()] == match[1]:
                return dated
            return unknown("The weekday and the date disagree; no date was guessed.")

    if value in {"today", "tomorrow"}:
        day = today + timedelta(days=int(value == "tomorrow"))
        return single(day, "Calendar date in the message's local time zone.")
    if value in {"tonight", "tomorrow morning", "tomorrow evening", "today morning", "today evening"}:
        day = today + timedelta(days=int(value.startswith("tomorrow")))
        return single(day, "Part of day stated; no exact clock time was supplied.", exact=False)
    if value in {"by end of day", "end of day", "by the end of the day", "close of business", "by close of business"}:
        return single(today, "Uses the configured local end-of-day time; does not roll to another day.", end_of_day)

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
    if value in {"within two working days", "within 2 working days"}:
        deadline = today
        remaining = 2
        while remaining:
            deadline += timedelta(days=1)
            if deadline.weekday() in weekdays:
                remaining -= 1
        return Due(
            today, deadline, None, False, "Inclusive range ending after two working days; holidays are not known."
        )

    explicit = value.removeprefix("by ")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", explicit):
            return single(date.fromisoformat(explicit), "Explicit ISO date.")
        if match := re.fullmatch(r"(\d{1,2})([/.-])(\d{1,2})\2(\d{4})", explicit):
            first, _, second, year = match.groups()
            month, day = (int(first), int(second)) if locale == "en_US" else (int(second), int(first))
            return single(date(int(year), month, day), f"Explicit numeric date interpreted using {locale}.")
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
        if match := re.fullmatch(r"([a-z]+)\.? (\d{1,2})(?:,? (\d{4}))?", explicit):
            month_name, day, year = match.groups()
        elif match := re.fullmatch(r"(\d{1,2}) ([a-z]+)\.?(?:,? (\d{4}))?", explicit):
            day, month_name, year = match.groups()
        else:
            return unknown("No supported definite date; vague or event-relative phrases require clarification.")
        if month_name in months:
            month = months[month_name]
            if year is not None:
                return single(date(int(year), month, int(day)), "Explicit date with a written month.")
            # A leap year validates the month/day before seeking the next occurrence.
            date(2000, month, int(day))
            for candidate_year in range(today.year, min(today.year + 9, 10000)):
                try:
                    candidate = date(candidate_year, month, int(day))
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
    except ValueError:
        return unknown("Invalid date for the selected locale; no alternative order was guessed.")
    return unknown("Unrecognized month; no date was guessed.")
