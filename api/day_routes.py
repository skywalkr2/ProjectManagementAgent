"""The day's capacity and the attention rules (design 6.32): the proposal of what to move out of today, and "Not now"
on a suggestion line.

The proposal is read only; moving a to-do is the person's own change of its date (POST /api/records/edit), with Undo.
"Not now" records a signal and holds the suggestion back until something about it changes. A choice on a pattern or
stale line acts at once with Undo and records its own signal."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import CapacityMoveView, CapacityView, ChooseDone, ChooseIn, NotNowDone, NotNowIn, Ok
from engine import day_capacity, patterns, suggestions
from engine.config import Config
from engine.storage import Store, StoreError
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

    @r.post("/suggestions/choose")
    def choose(body: ChooseIn) -> ChooseDone:
        """Do one of the choices a suggestion line offers, at once, and record it as a signal. A choice that changes a
        to-do is the person's own change with Undo; one that only says leave it, keep or snooze changes nothing."""
        now = worker.now()
        split = queue_split(ws, store, cfg, now, handover=worker.handover_state())
        line = next((x for x in [*split.shown, *split.digest] if x.key == body.key), None)
        if line is None or not line.choices:
            raise HTTPException(status_code=404, detail="That suggestion isn't on Today now.")
        words = patterns.Words(reason=body.reason, waiting=body.waiting, weekly=body.weekly)
        try:
            done = patterns.choose(store, cfg, line, body.choice, words, now, suggestions.change_key(line))
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        return ChooseDone(signal=done.signal, changeset=done.changeset)

    @r.post("/suggestions/choose/{signal_id}/undo")
    def choose_undo(signal_id: str) -> Ok:
        """Take a choice back: what it changed goes back and a suggestion it kept away shows again."""
        try:
            taken = patterns.undo(store, signal_id)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        if not taken:
            raise HTTPException(status_code=404, detail="There is no choice to take back.")
        events.changed()
        return Ok(ok=signal_id)

    return r
