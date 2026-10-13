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

from engine.connectors import moment
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


def agenda(store: Any, cfg: Any, now: datetime) -> list[AgendaItem]:
    """Events on today and the configured days after it, earliest first; all-day ones first on their day. The app's own
    calendar entries follow the connected calendars' events, in start order, each on every day it covers."""
    here = zone(cfg)
    first = now.astimezone(here).date()
    days = [first + timedelta(days=n) for n in range(cfg.ui.today.agenda_days_ahead + 1)]
    found = []
    for snap in store.read().list("snapshot"):
        data = snap.data
        event = data.get("event")
        if data.get("gone") or not event:
            continue
        on = [d for d in days if _falls_on(event, d, here)]
        if not on:
            continue
        found.append(
            AgendaItem(
                snapshot=snap.id,
                source=data["source"],
                title=data["title"],
                start=event["start"],
                end=event.get("end"),
                all_day=bool(event.get("all_day")),
                where=event.get("where"),
                link=data.get("link"),
                cancelled=bool(event.get("cancelled")),
                days=on,
            )
        )
    found.sort(key=lambda a: (a.days[0], not a.all_day, _sort_key(a, here), a.title))
    return [*found, *_own_entries(store, days, here)]


def _own_entries(store: Any, days: list[date], here: ZoneInfo) -> list[AgendaItem]:
    """The app's own calendar entries that overlap the listed days, earliest first. A range counts every day from its
    start to its end, both included; an entry with no time of day is all-day."""
    found = []
    for entry in store.read().list("event"):
        data = entry.data
        try:
            start = entry_time(data["start"])
            end = entry_time(data["end"]) if data.get("end") else start
        except (TypeError, ValueError):
            continue
        all_day = not isinstance(start, datetime)
        first, last = _local_day(start, here), _local_day(end, here)
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
            )
        )
    return sorted(found, key=lambda a: (a.days[0], not a.all_day, _sort_key(a, here), a.title))


def _local_day(value: date | datetime, here: ZoneInfo) -> date:
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


def todo(store: Any, cfg: Any, now: datetime) -> list[Todo]:
    """The person's own open actions: overdue first, then due today, then the rest with no date or a later one,
    earliest first. Empty when the workspace doesn't say which person record is theirs."""
    me = cfg.workspace.user.person
    if not me:
        return []
    today_here = now.astimezone(zone(cfg)).date()
    found = []
    for action in store.read().list("action"):
        data = action.data
        if data.get("status") != "open" or not any(o.get("person") == me for o in data.get("owners") or []):
            continue
        due = date.fromisoformat(str(data["due"])) if data.get("due") else None
        found.append(
            Todo(
                action=action.id,
                text=data["text"],
                project=data.get("project"),
                due=due,
                overdue=due is not None and due < today_here,
            )
        )
    return sorted(found, key=lambda t: (t.due is None, t.due or today_here, t.text))
