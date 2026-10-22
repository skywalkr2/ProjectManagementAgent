"""Today's agenda and what came in, from what the watched sources hold now (design 7.1).

Calendar and mail connectors say what each item is (`EventDetails`, `MessageDetails`); the watcher keeps that on the
item's snapshot. These read the snapshots only: nothing here reaches a service or calls AI. Days are the person's days,
in `workspace.user.timezone`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from engine import agenda as agenda_module
from engine import entry_rules, repeats
from engine.blocked import Blocker, blocker_of, own_wait
from engine.connectors import moment
from engine.firm_due import firm_due
from engine.names import People
from engine.records import entry_time


@dataclass
class AgendaItem:
    snapshot: str
    source: str
    title: str
    start: str
    end: str | None
    all_day: bool
    where: str | None
    link: str | None
    cancelled: bool
    days: list[date] = field(default_factory=list)
    own: bool = False  # an entry in the app's own calendar, not an event read from a connected calendar
    entry: str | None = None  # the calendar entry kept for this date of an event read from a connected calendar
    series: str | None = None  # the series an own entry is one meeting of
    open_items: int = 0  # for such a meeting: how many open actions and questions sit on it
    todo_offer: str | None = None  # a plain entry whose title reads as a task: the to-do it is offered as, in its words
    agenda: list[dict[str, Any]] = field(default_factory=list)  # what is to be taken up at it (engine/agenda.py)


@dataclass
class Arrived:
    snapshot: str
    source: str
    title: str
    sender: str | None
    received: str
    unread: bool | None
    link: str | None


@dataclass
class Inbox:
    items: list[Arrived]
    left_out: int  # closed by a triage rule in the same window: newsletters, automatic replies
    set_aside: int = 0  # put in the Set aside folder in the same window: personal mail, sales and promotions


def zone(cfg: Any) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.workspace.user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def agenda(store: Any, cfg: Any, now: datetime, through: date | None = None) -> list[AgendaItem]:
    """Events on today and the configured days after it (or every day through `through`), earliest first; all-day ones
    first on their day. The app's own calendar entries follow the connected calendars' events, in start order, each on
    every day it covers."""
    here = zone(cfg)
    first = now.astimezone(here).date()
    ahead = cfg.ui.today.agenda_days_ahead if through is None else max(0, (through - first).days)
    days = [first + timedelta(days=n) for n in range(ahead + 1)]
    found = []
    view = store.read()
    kept = {
        (e.data["source"], e.data["key"]): e for e in view.list("event") if e.data.get("key") and e.data.get("source")
    }
    with_todo = {a.data["event"] for a in view.list("action") if a.data.get("event")}
    for snap in view.list("snapshot"):
        data = snap.data
        event = data.get("event")
        if data.get("gone") or not event:
            continue
        for date_ in _dates(event, data["title"], data["key"]):
            on = [d for d in days if _falls_on(date_, d, here)]
            if not on:
                continue
            entry = kept.get((data["source"], date_["key"]))
            found.append(
                AgendaItem(
                    snapshot=snap.id,
                    source=data["source"],
                    title=date_["title"],
                    start=date_["start"],
                    end=date_["end"],
                    all_day=bool(event.get("all_day")),
                    where=date_["where"],
                    link=data.get("link"),
                    cancelled=date_["cancelled"],
                    days=on,
                    entry=entry.id if entry is not None else None,
                    series=entry.data.get("series") if entry is not None else None,
                    open_items=_open_on(view, entry, days[0], here)
                    if entry is not None and entry.data.get("series")
                    else 0,
                    todo_offer=entry_rules.task_offer(entry.data, cfg)
                    if entry is not None and entry.id not in with_todo
                    else None,
                    agenda=agenda_module.for_entry(view, entry, days[0], here) if entry is not None else [],
                )
            )
    found.sort(key=lambda a: (a.days[0], not a.all_day, _sort_key(a, here), a.title))
    return [*found, *_own_entries(store, days, here)]


def _dates(event: dict[str, Any], title: str, key: str) -> list[dict[str, Any]]:
    """The dates an event item stands for: each date of a series the connector expanded, or the one date it has. Each is
    a start, an end, a title, a place, whether it is called off, and the key of the entry kept for it."""
    listed = event.get("occurrences") or []
    if not listed:
        return [
            {
                "start": event["start"],
                "end": event.get("end"),
                "all_day": bool(event.get("all_day")),
                "title": title,
                "where": event.get("where"),
                "cancelled": bool(event.get("cancelled")),
                "key": key,
            }
        ]
    return [
        {
            "start": o["start"],
            "end": o.get("end"),
            "all_day": bool(event.get("all_day")),
            "title": o.get("title") or title,
            "where": o.get("where") or event.get("where"),
            "cancelled": bool(o.get("cancelled")),
            "key": f"{key}#{o.get('was') or o['start']}",
        }
        for o in listed
    ]


def _own_entries(store: Any, days: list[date], here: ZoneInfo) -> list[AgendaItem]:
    """The app's own calendar entries that overlap the listed days, earliest first. A range counts every day from its
    start to its end, both included; an entry with no time of day is all-day."""
    found = []
    view = store.read()
    for entry in view.list("event"):
        data = entry.data
        if data.get("key"):
            continue  # kept from a connected calendar: shown as that calendar's event, not a second time
        try:
            start = entry_time(data["start"])
            end = entry_time(data["end"]) if data.get("end") else start
        except (TypeError, ValueError):
            continue
        all_day = not isinstance(start, datetime)
        first, last = local_day(start, here), local_day(end, here)
        on = [d for d in days if first <= d <= last]
        if not on:
            continue
        found.append(
            AgendaItem(
                snapshot=entry.id,
                source=data.get("source") or "",
                title=data["title"],
                start=_local_text(start, here),
                end=_local_text(end, here) if data.get("end") else None,
                all_day=all_day,
                where=None,
                link=None,
                cancelled=False,
                days=on,
                own=True,
                series=data.get("series"),
                open_items=_open_on(view, entry, days[0], here) if data.get("series") else 0,
                agenda=agenda_module.for_entry(view, entry, days[0], here),
            )
        )
    return sorted(found, key=lambda a: (a.days[0], not a.all_day, _sort_key(a, here), a.title))


def _open_on(view: Any, entry: Any, today: date, here: ZoneInfo) -> int:
    """How many open actions and questions sit on a meeting of a series: those that name it, and, when it is the series'
    next meeting, those on the series that name no meeting, or one that has passed (they roll to the next)."""
    from engine.series import SETTLED, next_instance, span

    series = entry.data["series"]
    upcoming = next_instance(view, series, today, here)
    counted = 0
    for kind, settled in SETTLED.items():
        for item in view.list(kind):
            if item.data.get("series") != series or item.data.get("status") in settled:
                continue
            named = view.get("event", item.data["event"]) if item.data.get("event") else None
            days = span(named.data, here) if named is not None else None
            sits = named.id if named is not None and days is not None and days[1] >= today else None
            if (sits or (upcoming.id if upcoming is not None else None)) == entry.id:
                counted += 1
    return counted


def local_day(value: date | datetime, here: ZoneInfo) -> date:
    """The person's own day for a moment (a stored time is UTC): the day it falls on where they are."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=here)).astimezone(here).date()
    return value


def _local_text(value: date | datetime, here: ZoneInfo) -> str:
    """A day as its ISO text; a time with its offset, in the person's time zone when it was written without one."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=here)).isoformat()
    return value.isoformat()


def _falls_on(event: dict[str, Any], day: date, here: ZoneInfo) -> bool:
    try:
        start = moment(event["start"], all_day=bool(event.get("all_day")))
        end = moment(event["end"], all_day=bool(event.get("all_day"))) if event.get("end") else None
    except (TypeError, ValueError):
        return False
    if event.get("all_day"):
        last = (end - timedelta(days=1)) if end is not None and end > start else start
        return start <= day <= last
    begins = datetime.combine(day, time.min, here)
    ends = begins + timedelta(days=1)
    finish = end if end is not None and end > start else start
    return start < ends and (finish > begins or start >= begins)


def _sort_key(item: AgendaItem, here: ZoneInfo) -> str:
    if item.all_day:
        return ""
    try:
        return moment(item.start).astimezone(here).isoformat()
    except (TypeError, ValueError):
        return item.start


def arrived(store: Any, cfg: Any, now: datetime) -> Inbox:
    """Messages received within the configured hours, newest first, leaving out what a triage rule closed or set
    aside; each is counted. Set-aside mail counts only while it is in the Set aside folder, not once confirmed."""
    since = now - timedelta(hours=cfg.ui.today.mail_hours)
    found, left_out, set_aside = [], 0, 0
    for snap in store.read().list("snapshot"):
        data = snap.data
        message = data.get("message")
        if data.get("gone") or not message or not message.get("received"):
            continue
        try:
            received = moment(message["received"])
        except (TypeError, ValueError):
            continue
        if not since <= received <= now + timedelta(minutes=5):
            continue
        mark = data.get("set_aside")
        if mark:
            # The count is what the Set aside folder lists: an item the person confirmed has left it.
            if not mark.get("confirmed_at") and not data.get("deleted"):
                set_aside += 1
            continue
        if data.get("closed_by"):
            left_out += 1
            continue
        found.append(
            Arrived(
                snapshot=snap.id,
                source=data["source"],
                title=data["title"],
                sender=message.get("sender"),
                received=message["received"],
                unread=message.get("unread"),
                link=data.get("link"),
            )
        )
    found.sort(key=lambda a: moment(a.received), reverse=True)
    return Inbox(items=found[: cfg.ui.today.mail_max], left_out=left_out, set_aside=set_aside)


@dataclass
class Todo:
    action: str
    text: str
    project: str | None
    due: date | None
    overdue: bool
    on_hold: str | None = None
    remind_at: datetime | None = None
    #: What its hold is blocked on, when the hold names a blocker (a person, an action or a question). A blocker that is
    #: over (an answered question, a finished action) leaves the to-do unblocked: `on_hold` is None and it is due again.
    blocker: Blocker | None = None
    #: Its date is one the rules couldn't read for certain: shown to be checked, never a deadline.
    due_check: bool = False
    #: How it repeats, when it does: the words, the rule, the first day and the shape the screen says back.
    repeat: dict[str, Any] | None = None
    #: About how long it takes, in minutes, when it says.
    effort_minutes: int | None = None


def todo(store: Any, cfg: Any, now: datetime) -> list[Todo]:
    """The person's own open actions: overdue first, then due today, then the rest with no date or a later one,
    earliest first. An action on hold is never overdue; it says what it waits for and keeps its due date.
    Empty when the workspace doesn't say which person record is theirs."""
    me = cfg.workspace.user.person
    if not me:
        return []
    here = zone(cfg)
    today_here = now.astimezone(here).date()
    view = store.read()
    people = People(store, cfg)
    found = []
    for action in view.list("action"):
        data = action.data
        if data.get("status") != "open" or not any(o.get("person") == me for o in data.get("owners") or []):
            continue
        due = date.fromisoformat(str(data["due"])) if data.get("due") else None
        firm = firm_due(data)
        hold = data.get("on_hold")
        blocker = blocker_of(view, hold, people, here)
        if blocker is not None and blocker.resolved:
            hold = None  # what it waited on is over: it is due again by its own date, and goes first
        elif own_wait(view, data, people.pm):
            hold, blocker = None, None  # it waits on the person themselves: their own to-do, not blocked
        found.append(
            Todo(
                action=action.id,
                text=data["text"],
                project=data.get("project"),
                due=due,
                overdue=firm is not None and firm < today_here and not hold,
                on_hold=hold["waiting_for"] if hold else None,
                remind_at=datetime.fromisoformat(str(data["remind_at"])).astimezone(here)
                if data.get("remind_at")
                else None,
                blocker=blocker,
                due_check=bool(data.get("due_check")) and due is not None,
                repeat=repeats.view_of(data.get("repeat")),
                effort_minutes=data.get("effort_minutes"),
            )
        )
    unblocked = lambda t: not (t.blocker is not None and t.blocker.resolved)  # noqa: E731
    # A date to be checked sorts as no date: it isn't a deadline.
    dated = lambda t: None if t.due_check else t.due  # noqa: E731
    return sorted(found, key=lambda t: (unblocked(t), dated(t) is None, dated(t) or today_here, t.text))
