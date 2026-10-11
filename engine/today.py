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


def zone(cfg: Any) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.workspace.user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def agenda(store: Any, cfg: Any, now: datetime) -> list[AgendaItem]:
    """Events on today and the configured days after it, earliest first; all-day ones first on their day."""
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
    return sorted(found, key=lambda a: (a.days[0], not a.all_day, _sort_key(a, here), a.title))


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
    """Messages received within the configured hours, newest first, leaving out what a triage rule closed."""
    since = now - timedelta(hours=cfg.ui.today.mail_hours)
    found, left_out = [], 0
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
    return Inbox(items=found[: cfg.ui.today.mail_max], left_out=left_out)


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
