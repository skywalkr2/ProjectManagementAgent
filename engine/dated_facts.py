"""Dated facts and the reminders proposed for them (design 6.32, "What arrives").

A deadline, renewal, expiry, warranty end or bill that an input states with a full date becomes a fact carrying that
day (`on`) and its kind (`on_kind`). The rules then propose a reminder for it: a `record.set` of `remind_at` that waits
for the person's yes, because only the person sets a reminder. The same is proposed for a to-do whose day is one of the
labeled days of its input. Nothing is worked out from words that are not a full date, and a bill is a reminder only:
no amount, balance or account is kept anywhere.

Everything here is plain rules over explicit inputs; no AI runs and nothing is written."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from engine.document_dates import explicit_dates, find_dates

#: The kinds of day a fact can carry, in the order the settings list them.
KINDS = ("deadline", "renewal", "expiry", "warranty", "bill")

#: What a labeled day in a document (`engine.document_dates`) means as a kind of dated fact. A check-in or an
#: appointment is a calendar entry's business, not a fact's, so it has no kind here.
FROM_LABEL = {
    "warranty_end": "warranty",
    "cancel_by": "deadline",
    "valid_until": "expiry",
    "payment_due": "bill",
    "renewal": "renewal",
    "expiry": "expiry",
}


def locale_of(cfg: Any) -> str | None:
    """The numeric-date order the workspace's language reads (en-US or en-GB); none for a language these rules don't
    read, in which case a quote's date is not checked against the day written beside it."""
    language = (cfg.workspace.language or "en-US").replace("_", "-").lower()
    if not language.startswith("en"):
        return None
    return "en-us" if language.startswith("en-us") else "en-gb"


def states_the_day(cfg: Any, quote: str, day: date) -> bool:
    """Whether a quote states `day` as a full date. A workspace whose language the rules don't read accepts any."""
    locale = locale_of(cfg)
    return True if locale is None else day in explicit_dates(quote, locale)


def lead_days(cfg: Any, kind: str) -> int:
    return int(getattr(cfg.steward.dates.lead_days, kind))


def reminder_moment(cfg: Any, day: date, kind: str, now: datetime) -> datetime | None:
    """When to offer to remind the person of a day: the morning their working hours start, `lead_days` before it (the
    working day before when that one is not a working day). When that moment has passed and the day is still ahead,
    the next working morning, up to the day itself. None for a day that is today or past, and for a setting that
    turns the offer off."""
    from engine.reminder_lines import rules
    from engine.today import zone

    if not cfg.steward.dates.suggest_reminders:
        return None
    here = zone(cfg)
    working = rules(cfg).working
    today = now.astimezone(here).date()
    if day <= today:
        return None

    def morning(on: date) -> datetime:
        return datetime.combine(on, working.start, here)

    start = day - timedelta(days=lead_days(cfg, kind))
    while start.weekday() not in working.days and start > today:
        start -= timedelta(days=1)
    moment = morning(start)
    if moment > now:
        return moment
    following = today + timedelta(days=1)
    while following.weekday() not in working.days and following < day:
        following += timedelta(days=1)
    return morning(following) if following <= day and morning(following) > now else None


def fact_reminder(cfg: Any, fact: dict[str, Any], fact_id: str, now: datetime) -> dict[str, Any] | None:
    """The `record.set` that proposes a reminder for a dated fact just made, as the op's own fields, or None when no
    reminder is offered (no day, the offer is off, the day has come, or the fact already has one)."""
    day, kind = fact.get("on"), fact.get("on_kind")
    if day is None or kind not in KINDS or fact.get("remind_at"):
        return None
    moment = reminder_moment(cfg, day if isinstance(day, date) else date.fromisoformat(str(day)), kind, now)
    if moment is None:
        return None
    return {
        "op": "record.set",
        "kind": "fact",
        "id": fact_id,
        "field": "remind_at",
        "value": moment.isoformat(),
        "evidence": {"quote": fact["quote"]},
    }


def labeled_day(cfg: Any, text: str, day: date, now: datetime) -> tuple[str, str] | None:
    """For a to-do due on `day`: the kind of day and the exact words of the input that label that same day, when the
    input states one in a labeled sentence (a renewal date, an expiry, a warranty end, a cancel-by day, a bill's due
    day) and is sure of it. None when no sentence labels that day, or it is stated with doubt."""
    from engine.today import zone

    locale = locale_of(cfg)
    if locale is None or not text.strip():
        return None
    for found in find_dates(text, now, zone(cfg), locale):
        kind = FROM_LABEL.get(found.kind)
        if kind and found.certain and found.date == day and found.evidence:
            return kind, found.evidence
    return None


def action_reminder(
    cfg: Any, text: str, action_id: str, due: date | None, remind_at: Any, now: datetime
) -> dict[str, Any] | None:
    """The `record.set` that proposes a reminder for a to-do just made whose day an input labels, or None."""
    if due is None or remind_at:
        return None
    labeled = labeled_day(cfg, text, due, now)
    if labeled is None:
        return None
    kind, quote = labeled
    moment = reminder_moment(cfg, due, kind, now)
    if moment is None:
        return None
    return {
        "op": "record.set",
        "kind": "action",
        "id": action_id,
        "field": "remind_at",
        "value": moment.isoformat(),
        "evidence": {"quote": quote},
    }


def coming(reader: Any, cfg: Any, now: datetime) -> list[Any]:
    """The dated facts whose reminder has come: a `remind_at` that has passed while the day it is for has not, newest
    reminder first by their day. A fact a newer one replaced is left out."""
    from engine.facts import superseded_by
    from engine.today import zone

    here = zone(cfg)
    today = now.astimezone(here).date()
    found = []
    for fact in reader.list("fact"):
        d = fact.data
        if not d.get("on") or not d.get("remind_at"):
            continue
        if datetime.fromisoformat(str(d["remind_at"])) > now or date.fromisoformat(str(d["on"])) < today:
            continue
        if superseded_by(reader, fact.id) is not None:
            continue
        found.append(fact)
    return sorted(found, key=lambda f: (str(f.data["on"]), f.id))
