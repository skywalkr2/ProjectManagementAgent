"""This week (design 7.7): what is due by the end of the week, who is waiting on the person and which meetings to hold,
across every project, from today through the configured last working day. Reads only.

The week's end is the last working day the reminders settings name (`steward.reminders.working_last_day`); on a day
after it, the week is the next one. Something on hold is never due, so it is not listed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from engine.blocked import standing_hold
from engine.config.schema import WEEKDAYS
from engine.firm_due import firm_due
from engine.names import People
from engine.today import AgendaItem, agenda, zone


@dataclass
class Due:
    """An open to-do due from today through the week's end (or overdue), with its owners' ids and whether it is the
    person's own."""

    action: str
    text: str
    due: date
    project: str | None
    owners: list[str]
    mine: bool


@dataclass
class Waiting:
    """Someone waiting on the person: `count` of the person's open to-dos promised to them or replies owed to them that
    are due by the week's end or overdue, and the earliest `due` of them (none when none has a day)."""

    person: str
    count: int
    due: date | None = None


@dataclass
class Week:
    """The week as of a day: `first` and `last` day, what is `due`, who is `waiting` and the `meetings`."""

    first: date
    last: date
    due: list[Due] = field(default_factory=list)
    waiting: list[Waiting] = field(default_factory=list)
    meetings: list[AgendaItem] = field(default_factory=list)


def week_end(cfg: Any, today: date) -> date:
    """The configured last working day on or after `today`."""
    target = WEEKDAYS.index(cfg.steward.reminders.working_last_day)
    return today + timedelta(days=(target - today.weekday()) % 7)


def this_week(store: Any, cfg: Any, now: datetime) -> Week:
    """This week as of `now`."""
    today = now.astimezone(zone(cfg)).date()
    last = week_end(cfg, today)
    people = People(store, cfg)
    pm = people.pm
    reader = store.read()
    due: list[Due] = []
    waiting: dict[str, Waiting] = {}
    for record in reader.list("action"):
        d = record.data
        if d.get("status") != "open" or standing_hold(reader, d, people):
            continue
        day = firm_due(d)
        owners = [o["person"] for o in d.get("owners") or [] if o.get("person")]
        mine = pm is not None and pm in owners
        if day is not None and today <= day <= last:
            due.append(Due(record.id, d["text"], day, d.get("project"), owners, mine))
        if not mine or (day is not None and day > last):
            continue
        asked = [d["asker"]] if d.get("reply_owed") and d.get("asker") else []
        for person in {*(d.get("promised_to") or []), *asked}:
            if person == pm:
                continue
            found = waiting.setdefault(person, Waiting(person, 0))
            found.count += 1
            if day is not None and (found.due is None or day < found.due):
                found.due = day
    due.sort(key=lambda x: (x.due, x.text.lower(), x.action))
    meetings = [m for m in agenda(store, cfg, now, through=last) if not m.cancelled]
    return Week(
        today,
        last,
        due,
        sorted(waiting.values(), key=lambda w: (w.due is None, w.due or last, people.name(w.person).lower())),
        meetings,
    )
