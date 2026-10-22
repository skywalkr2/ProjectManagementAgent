"""Reminders on Today: which open actions have a reminder that has reached the person, and the times a snooze can go to.

An action's `remind_at` is the moment the person asked to be reminded. When it reaches them is decided by the rules in
`engine.reminders` from the settings in `steward.reminders` (working hours, quiet hours, how missed ones arrive).
Everything here reads: setting a reminder or snoozing one is the person's own `record.edit` of `remind_at`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import Any

from engine import running
from engine.blocked import standing_hold
from engine.config.schema import WEEKDAYS
from engine.reminders import QuietHours, Reminder, Snooze, WorkingHours, in_quiet_hours, next_fire, snooze
from engine.today import zone

#: The snooze choices a menu offers, in order; "Pick a time" is the person's own time, not one of these.
SNOOZE_CHOICES = ("in 1 hour", "later today", "this evening", "tomorrow morning", "next week")


@dataclass(frozen=True)
class Due:
    """An open action whose reminder has reached the person: its `action`, `text` and `project`, the moment it was set
    for (`due`) and when it was to reach them (`at`, after quiet and working hours), both on the person's clock."""

    action: str
    text: str
    project: str | None
    due: datetime
    at: datetime
    #: A gap in the time the app was running covers `due`: the app knows it was not running then.
    away: bool = False


@dataclass(frozen=True)
class Plan:
    """What reminders show now. `now`: came due and reach the person at once. `late`: came due a while ago without
    being shown, one line each (`away` says whether the app knows it was not running when it came due). `missed`:
    the same, when the person chose one summary and there is more than one. `kept`: fell in quiet hours and arrive
    together now that they have ended."""

    now: list[Due] = field(default_factory=list)
    late: list[Due] = field(default_factory=list)
    missed: list[Due] = field(default_factory=list)
    kept: list[Due] = field(default_factory=list)


@dataclass(frozen=True)
class Rules:
    working: WorkingHours
    quiet: QuietHours
    missed: str
    grace: timedelta
    tz: tzinfo


def rules(cfg: Any) -> Rules:
    """The reminder settings as the rules module takes them."""
    s = cfg.steward.reminders
    first, last = WEEKDAYS.index(s.working_first_day), WEEKDAYS.index(s.working_last_day)
    days = tuple(range(first, last + 1)) if first <= last else (*range(first, 7), *range(0, last + 1))
    return Rules(
        working=WorkingHours(
            time.fromisoformat(s.working_start),
            time.fromisoformat(s.working_end),
            days,
            later_today_delay=timedelta(hours=s.later_today_hours),
            evening=time.fromisoformat(s.evening),
        ),
        quiet=QuietHours(time.fromisoformat(s.quiet_start), time.fromisoformat(s.quiet_end)),
        missed=s.missed,
        grace=timedelta(minutes=s.late_after_minutes),
        tz=zone(cfg),
    )


def _scheduled(due: datetime, r: Rules) -> datetime:
    """When a reminder set for `due` was to reach the person: `due` itself, as chosen, or the end of the quiet hours it
    fell in. Working hours never move it: a time the person picked is theirs. The rules are asked as of a moment
    before it, as they were when the person set it."""
    before = due.astimezone(UTC) - timedelta(seconds=1)
    plan = next_fire(Reminder((due,)), before, r.tz, r.quiet, None)
    return plan.fires[0].at if plan.status == "known" and plan.fires else due


def plan(reader: Any, cfg: Any, now: datetime, gaps: list[running.Gap] | None = None) -> Plan:
    """The reminders that have reached the person and are still waiting for them: actions that are open and not on
    hold, with a `remind_at` whose time has come. `gaps` are the times the app is known not to have been running."""
    r = rules(cfg)
    found = Plan()
    waiting: list[Due] = []
    for action in reader.list("action"):
        d = action.data
        if d.get("status") != "open" or standing_hold(reader, d) or not d.get("remind_at"):
            continue
        due = datetime.fromisoformat(str(d["remind_at"])).astimezone(r.tz)
        at = _scheduled(due, r)
        if at > now:
            continue
        item = Due(
            action.id, str(d["text"]), d.get("project"), due, at.astimezone(r.tz), running.covers(gaps or [], due)
        )
        if in_quiet_hours(due, r.quiet):
            found.kept.append(item)
        elif now - at > r.grace:
            waiting.append(item)
        else:
            found.now.append(item)
    found.kept.sort(key=lambda x: (x.due, x.action))
    found.now.sort(key=lambda x: (x.due, x.action))
    if r.missed == "summary" and len(waiting) > 1:
        # Many late ones arrive as one summary: the rules say how they group.
        by_time: dict[datetime, list[Due]] = {}
        for item in waiting:
            by_time.setdefault(item.due.astimezone(UTC), []).append(item)
        result = next_fire(Reminder(tuple(by_time), missed_mode="summary"), now, r.tz, r.quiet, r.working)
        if result.status == "known" and len(result.fires) == 1:
            found.missed.extend(sorted(waiting, key=lambda x: (x.due, x.action)))
            return found
    found.late.extend(sorted(waiting, key=lambda x: (x.due, x.action)))
    return found


def choices(cfg: Any, now: datetime) -> list[tuple[str, datetime]]:
    """The snooze choices that have a time still to come, each with the moment it resolves to on the person's clock. A
    choice with no time left today (Later today after working hours, This evening once it has passed) is left out."""
    r = rules(cfg)
    out = []
    for choice in SNOOZE_CHOICES:
        result = snooze(choice, now, r.tz, r.working)
        if result.status == "known" and result.at is not None:
            out.append((choice, result.at.astimezone(r.tz)))
    return out


def resolve(cfg: Any, now: datetime, *, choice: str | None = None, at: datetime | None = None) -> Snooze:
    """A snooze choice, or a time the person picked, as the moment the reminder moves to. A time without a zone is on
    the person's own clock."""
    r = rules(cfg)
    if at is not None:
        return snooze(at if at.tzinfo is not None else at.replace(tzinfo=r.tz), now, r.tz, r.working)
    return snooze(choice or "", now, r.tz, r.working)
