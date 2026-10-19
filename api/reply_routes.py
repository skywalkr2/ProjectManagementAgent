"""API routes for replies owed (design 6.35): closing one because it was answered another way.

Copying or editing the drafted reply is `POST /api/actions/{id}/reply`, and saying no reply is needed is
`POST /api/actions/{id}/drop`; both already exist and are the person's own change with Undo. This one closes the action
as done, credited to the person, with their words (when they give any) as the evidence."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import AnsweredAnotherWayIn, Applied
from engine.applier import apply_as_person
from engine.config import Config
from engine.intake import IntakeError
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_reply_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, IntakeError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.post("/replies/{action_id}/answered")
    def answered_another_way(action_id: str, body: AnsweredAnotherWayIn) -> Applied:
        """Close a reply owed because it was answered another way (a call, a chat), credited to the person, with their
        words as the evidence when they give any, and Undo. It is the person's own act, so it teaches nothing."""
        record = store.read().get("action", action_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        if not record.data.get("reply_owed") or record.data.get("status") != "open":
            raise HTTPException(status_code=409, detail="That isn't a reply you still owe.")
        words = " ".join((body.note or "").split())
        op: dict[str, Any] = {"op": "action.close", "id": action_id}
        if words:
            op["evidence"] = {"quote": words}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Answered another way", note=words))
        events.changed()
        return Applied(changeset=cs_id)

    return r
