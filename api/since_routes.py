"""API routes for what changed since yesterday (design 6.32, 6.35): the list, and marking it seen when it is opened.

Reading writes nothing. The undo of an entry is the route its `undo` names (an op of a change, a rule's close taken a
closer look at, or mail put back from the Set aside folder); none of them is repeated here."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import Ok, RecordRef, SinceEntryView, SinceSeen, SinceYesterdayView
from engine import since_yesterday
from engine.config import Config
from engine.names import People
from engine.storage import Store
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_since_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/since-yesterday")
    def since() -> SinceYesterdayView:
        """What the assistant or a rule did since the start of yesterday (or the last time the list was opened, when
        that is later), newest first, one entry for each record."""
        people = People(store, cfg)
        plan = since_yesterday.build(ws, store.read(), cfg, people, worker.now())
        return SinceYesterdayView(
            as_of=plan.until,
            since=plan.since,
            unseen=len(plan.unseen),
            entries=[
                SinceEntryView(
                    **{k: v for k, v in vars(e).items() if k != "record"},
                    record=RecordRef(kind=e.record[0], id=e.record[1]) if e.record else None,
                )
                for e in plan.entries
            ],
        )

    @r.post("/since-yesterday/seen")
    def seen(body: SinceSeen) -> Ok:
        """The person opened the list as it was drawn at `until`: everything made up to then counts as seen, and Today's
        line goes until something new happens."""
        since_yesterday.mark_seen(store, cfg, body.until)
        events.changed()
        return Ok(ok="seen")

    return r
