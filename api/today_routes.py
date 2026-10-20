"""Top priorities and This week on Today (design 7.7). Both are read from the records each time they are asked for; a
row's actions use the routes the other screens use (`POST /api/actions/{id}/status` to mark done, `POST
/api/records/edit` to reassign), each the person's own change with Undo."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from api.schemas import (
    AgendaItemView,
    ComingView,
    OwnerNameView,
    PriorityLineView,
    PriorityThingView,
    ThisWeekView,
    TopPrioritiesView,
    WeekDueView,
    WeekWaitingView,
)
from engine.config import Config
from engine.names import People, render_owner
from engine.storage import Store
from engine.this_week import this_week
from engine.top_priorities import top_priorities
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_today_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def owners_of(people: People, data: dict[str, Any]) -> list[OwnerNameView]:
        return [
            OwnerNameView(
                person=o["person"],
                name=render_owner(
                    people.owner_format, people.name(o["person"]), people.team_names.get(o.get("team") or "")
                ),
                team=o.get("team"),
            )
            for o in data.get("owners") or []
        ]

    def owner_ids(people: People, ids: list[str]) -> list[OwnerNameView]:
        return [OwnerNameView(person=p, name=people.name(p)) for p in ids]

    @r.get("/today/priorities")
    def priorities() -> TopPrioritiesView:
        """Top priorities: a short ranked list across every project, by rules and never by an AI call. Overdue first,
        then waiting on the person, due within the follow-up window, then at risk; one line for each other person; a
        blocked action only as the question or action that holds it up; the blocked counted; and the dated to-dos of
        the next days after the lines."""
        reader = store.read()
        people = People(store, cfg)
        projects = {p.id: p.data["name"] for p in reader.list("project")}
        found = top_priorities(store, cfg, worker.now())
        lines = []
        for line in found.lines:
            record = reader.get("action", line.action) if line.action else None
            lines.append(
                PriorityLineView(
                    key=line.key,
                    rank=line.rank,  # type: ignore[arg-type]
                    kind=line.kind,  # type: ignore[arg-type]
                    person=line.person,
                    person_name=people.name(line.person) if line.person else None,
                    text=line.text,
                    project=line.project,
                    project_name=projects.get(line.project or ""),
                    due=line.due,
                    days=line.days,
                    action=line.action,
                    question=line.question,
                    version=record.version if record is not None else None,
                    owners=owners_of(people, record.data) if record is not None else [],
                    holds_up=line.holds_up,
                    send=line.send,
                    chase=line.chase,
                    overdue=line.overdue,
                    due_soon=line.due_soon,
                    waiting_days=line.waiting_days,
                    things=[PriorityThingView(**vars(t)) for t in line.things],  # type: ignore[arg-type]
                )
            )
        return TopPrioritiesView(
            lines=lines,
            more=found.more,
            blocked=found.blocked,
            coming=[
                ComingView(
                    action=c.action,
                    text=c.text,
                    due=c.due,
                    project=c.project,
                    project_name=projects.get(c.project or ""),
                    owners=owner_ids(people, c.owners),
                    mine=c.mine,
                )
                for c in found.coming
            ],
        )

    @r.get("/today/week")
    def week() -> ThisWeekView:
        """This week, from today through the configured last working day: what is due, who is waiting on the person and
        the meetings to hold, across projects."""
        people = People(store, cfg)
        projects = {p.id: p.data["name"] for p in store.read().list("project")}
        found = this_week(store, cfg, worker.now())
        return ThisWeekView(
            first=found.first,
            last=found.last,
            due=[
                WeekDueView(
                    action=d.action,
                    text=d.text,
                    due=d.due,
                    project=d.project,
                    project_name=projects.get(d.project or ""),
                    owners=owner_ids(people, d.owners),
                    mine=d.mine,
                )
                for d in found.due
            ],
            waiting=[
                WeekWaitingView(person=w.person, person_name=people.name(w.person), count=w.count, due=w.due)
                for w in found.waiting
            ],
            meetings=[AgendaItemView(**vars(m)) for m in found.meetings],
        )

    return r
