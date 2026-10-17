"""Choose which suggestions may interrupt a person using explicit inputs."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, tzinfo


@dataclass(frozen=True)
class Suggestion:
    kind: str
    importance: float
    change_key: str
    #: What the suggestion is about (a record id), so dismissing one doesn't overwrite another of the same kind.
    subject: str = ""


@dataclass(frozen=True)
class DailyCap:
    limit: int
    day: date
    shown_at: tuple[datetime, ...]


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time


@dataclass(frozen=True)
class Decision:
    index: int
    suggestion: Suggestion
    disposition: str
    reason_code: str
    reason: str


def _instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware datetime is required")
    instant = value.astimezone(UTC)
    if instant.astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("A datetime falls in a nonexistent local time")
    return instant


def _number(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value)
    )


def admit(
    suggestions: Sequence[Suggestion],
    now: datetime,
    tz: tzinfo,
    daily_cap: DailyCap,
    quiet_hours: QuietHours | None,
    threshold: float,
    dismissals: Mapping[str | tuple[str, str], str],
) -> tuple[Decision, ...]:
    """Return decisions in input order without consuming allowance or changing history.

    Dismissals map (kind, subject) to the change key the person dismissed; a bare kind stands for (kind, "").
    """
    entries = tuple(suggestions)

    def decision(index: int, disposition: str, code: str, reason: str) -> Decision:
        return Decision(index, entries[index], disposition, code, reason)

    try:
        if not isinstance(tz, tzinfo):
            raise ValueError("Supply a time-zone object, not a zone name")
        instant = _instant(now)
        local = now.astimezone(tz)
        if not isinstance(daily_cap, DailyCap):
            raise ValueError("The daily cap needs a limit, local date, and explicit shown history")
        if isinstance(daily_cap.limit, bool) or not isinstance(daily_cap.limit, int) or daily_cap.limit < 0:
            raise ValueError("The daily limit must be a nonnegative integer")
        if type(daily_cap.day) is not date or daily_cap.day != local.date():
            raise ValueError("The daily cap history must cover today's date in the supplied zone")
        if not _number(threshold):
            raise ValueError("The importance threshold must be a finite number")
        if not isinstance(dismissals, Mapping):
            raise ValueError("Dismissals must map a kind and subject to the dismissed change key")
        dismissed: dict[tuple[str, str], str] = {}
        for where, key in dismissals.items():
            kind, subject = (where, "") if isinstance(where, str) else where
            if (
                not isinstance(kind, str)
                or not kind.strip()
                or not isinstance(subject, str)
                or not isinstance(key, str)
                or not key.strip()
            ):
                raise ValueError("Dismissals must map a nonempty kind and a subject to a nonempty change key")
            dismissed[(kind, subject)] = key
        shown = []
        for value in daily_cap.shown_at:
            shown_instant = _instant(value)
            if shown_instant > instant:
                raise ValueError("Shown history contains a future timestamp")
            if value.astimezone(tz).date() == local.date():
                shown.append(shown_instant)
        remaining = max(0, daily_cap.limit - len(shown))
        quiet = False
        if quiet_hours is not None:
            start, end = quiet_hours.start, quiet_hours.end
            if start.tzinfo is not None or end.tzinfo is not None or start == end:
                raise ValueError("Quiet hours need distinct plain local clock times")
            clock = local.time()
            quiet = start <= clock < end if start < end else clock >= start or clock < end
    except (ValueError, OverflowError) as error:
        return tuple(decision(index, "held_back", "unknown", str(error)) for index in range(len(entries)))

    results: dict[int, Decision] = {}
    eligible = []
    for index, suggestion in enumerate(entries):
        if (
            not isinstance(suggestion, Suggestion)
            or not isinstance(suggestion.kind, str)
            or not suggestion.kind.strip()
            or not isinstance(suggestion.change_key, str)
            or not suggestion.change_key.strip()
            or not isinstance(suggestion.subject, str)
            or not _number(suggestion.importance)
        ):
            results[index] = decision(
                index, "held_back", "unknown", "The suggestion needs a kind, finite importance, and change key."
            )
        elif dismissed.get((suggestion.kind, suggestion.subject)) == suggestion.change_key:
            results[index] = decision(
                index, "held_back", "dismissed_unchanged", "This kind was dismissed with the same change key."
            )
        elif suggestion.importance < threshold:
            results[index] = decision(
                index, "held_back", "below_threshold", "Importance is below the supplied threshold."
            )
        elif quiet:
            results[index] = decision(index, "saved_for_digest", "quiet_hours", "Quiet hours are active.")
        else:
            eligible.append(index)
    # Spend the remaining allowance on the most important suggestions, keeping ties stable.
    eligible.sort(key=lambda index: entries[index].importance, reverse=True)
    for rank, index in enumerate(eligible):
        if rank < remaining:
            results[index] = decision(
                index, "shown_now", "within_cap", "Importance meets the threshold and today's allowance remains."
            )
        else:
            results[index] = decision(
                index, "saved_for_digest", "daily_cap", "Today's allowance for immediate suggestions is exhausted."
            )
    return tuple(results[index] for index in range(len(entries)))
