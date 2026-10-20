"""A meeting added in one line (design 7.7): `POST /api/calendar/meetings` takes what, the day and the time, and makes
the person's own calendar entry, or says it merged the meeting into one already there. Undo is the usual changeset
undo."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import MeetingAdded, MeetingIn
from engine import add_meeting
from engine.config import Config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_calendar_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.post("/calendar/meetings")
    def add(body: MeetingIn) -> MeetingAdded:
        """Add a meeting, or merge it into the one that is already on the calendar. The person's own act, with Undo."""
        try:
            added = add_meeting.add_meeting(store, cfg, body.what, body.day, body.time)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        if not added.merged:
            events.changed()
            worker.poke()
        return MeetingAdded(**vars(added))  # type: ignore[arg-type]

    return r
