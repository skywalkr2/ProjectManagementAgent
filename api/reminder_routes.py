"""API routes for reminders on actions (design 6.32): setting one, snoozing one, and clearing one.

A reminder is an action's `remind_at`. Changing it is the person's own `record.edit` applied as theirs with Undo; it is
not a correction of the assistant's work, so it records no learning signal."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import Applied, ReminderIn
from engine import reminder_lines
from engine.applier import apply_as_person
from engine.config import Config
from engine.intake import IntakeError
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_reminder_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, IntakeError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.post("/reminders/{action_id}")
    def remind(action_id: str, body: ReminderIn) -> Applied:
        """Set an action's reminder to a snooze choice or to a time the person picked, with Undo; with neither, clear
        it. A time that has passed, or a choice with no time left, is refused in plain words."""
        record = store.read().get("action", action_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        if body.choice is not None and body.at is not None:
            raise HTTPException(status_code=409, detail="Pick a choice or a time, not both.")
        value: str | None = None
        if body.choice is not None or body.at is not None:
            found = reminder_lines.resolve(cfg, worker.now(), choice=body.choice, at=body.at)
            if found.status != "known" or found.at is None:
                raise HTTPException(
                    status_code=409,
                    detail="That time has passed. Pick a time that is still ahead."
                    if body.at is not None
                    else "That choice has no time left. Pick another.",
                )
            value = found.at.isoformat()
        elif record.data.get("remind_at") is None:
            raise HTTPException(status_code=409, detail="nothing to change")
        op = {
            "op": "record.edit",
            "record": {"kind": "action", "id": action_id},
            "fields": {"remind_at": value},
            "read_version": body.read_version or record.version,
        }
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Changed on screen"))
        events.changed()
        return Applied(changeset=cs_id)

    return r
