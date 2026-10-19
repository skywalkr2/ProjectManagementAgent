"""API routes for promises (design 6.33): why one exists, and the corrections the person makes to it.

A promise is an action. A correction is the person's own `record.edit`, applied as theirs with Undo; a correction to a
field the assistant set records its signal (design 6.22), as every edit on screen does."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import Applied, PromiseCorrection, PromiseView
from engine import promises
from engine.applier import apply_as_person
from engine.config import Config
from engine.intake import IntakeError
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_promise_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, IntakeError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.get("/promises/{action_id}")
    def promise(action_id: str) -> PromiseView:
        """Why a promise exists and what is known of it: its words, who owes it to whom, its day and the words it came
        from, where it came from, how it is known, and what was heard since."""
        found = promises.view(store, cfg, action_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        return PromiseView(**found)

    @r.post("/promises/{action_id}/correct")
    def correct(action_id: str, body: PromiseCorrection) -> Applied:
        """Correct who owes a promise, to whom, how it is known or its day, with Undo. Records an edited correction
        for what the assistant had set."""
        record = store.read().get("action", action_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        for person in [body.owner, *(body.promised_to or [])]:
            if person is not None and store.read().get("person", person) is None:
                raise HTTPException(status_code=404, detail=f"person {person} doesn't exist")
        fields = promises.correction(
            record.data, owner=body.owner, promised_to=body.promised_to, basis=body.basis, due=body.due
        )
        if not fields:
            raise HTTPException(status_code=409, detail="nothing to change")
        op = {
            "op": "record.edit",
            "record": {"kind": "action", "id": action_id},
            "fields": fields,
            "read_version": body.read_version,
        }
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Changed on screen"))
        events.changed()
        return Applied(changeset=cs_id)

    return r
