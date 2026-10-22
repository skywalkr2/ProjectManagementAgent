"""The day's capacity and the attention rules (design 6.32): the proposal of what to move out of today, and "Not now"
on a suggestion line.

The proposal is read only; moving a to-do is the person's own change of its date (POST /api/records/edit), with Undo.
"Not now" records a signal and holds the suggestion back until something about it changes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import CapacityMoveView, CapacityView, NotNowDone, NotNowIn, Ok
from engine import day_capacity, suggestions
from engine.config import Config
from engine.storage import Store
from engine.today_queue import queue_split
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_day_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/capacity")
    def capacity() -> CapacityView:
        """Whether the free time left today holds the to-dos due today or late, and what is proposed to move when it
        doesn't. Nothing is moved or scheduled."""
        held = day_capacity.check(store, cfg, worker.now())
        if held is None:
            return CapacityView(fits=True)
        return CapacityView(
            fits=False,
            free_minutes=held.free_minutes,
            needed_minutes=held.needed_minutes,
            over_minutes=held.over_minutes,
            still_over=held.still_over,
            next_day=held.next_day,
            moves=[
                CapacityMoveView(**vars(m))
                for m in held.moves  # type: ignore[arg-type]
            ],
        )

    @r.post("/suggestions/not-now")
    def not_now(body: NotNowIn) -> NotNowDone:
        """Put a suggestion line off until something about it changes. It records a signal and changes nothing else."""
        now = worker.now()
        split = queue_split(ws, store, cfg, now, handover=worker.handover_state())
        line = next((x for x in [*split.shown, *split.digest] if x.key == body.key), None)
        if line is None or line.kind not in suggestions.KINDS:
            raise HTTPException(status_code=404, detail="That suggestion isn't on Today now.")
        made = suggestions.put_off(store, cfg, line, now)
        events.changed()
        return NotNowDone(signal=made)

    @r.post("/suggestions/not-now/{signal_id}/undo")
    def not_now_undo(signal_id: str) -> Ok:
        """Undo "Not now": the suggestion shows again at once."""
        if not suggestions.take_back(store, signal_id):
            raise HTTPException(status_code=404, detail='There is no "not now" to take back.')
        events.changed()
        return Ok(ok=signal_id)

    return r
