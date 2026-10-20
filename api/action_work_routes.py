"""Handing an action to the assistant (design 7.5): `POST /api/actions/{id}/hand-over` queues the request for the work
the action stands for, and `GET /api/actions/handed` lists the actions the assistant has in hand. The request goes the
usual way (estimate, the person's go above the configured amount); its draft is reviewed with the text-version
routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import HandedActionView, HandedOver, HandOverIn
from engine import action_work
from engine.config import Config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_action_work_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.post("/actions/{action_id}/hand-over")
    def hand_over(action_id: str, body: HandOverIn) -> HandedOver:
        """Ask the assistant to draft the work an open action stands for. The action stays the person's."""
        if store.read().get("action", action_id) is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        try:
            request = action_work.hand_over(store, action_id, body.note)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        worker.poke()
        return HandedOver(request=request)

    @r.get("/actions/handed")
    def handed() -> list[HandedActionView]:
        return [HandedActionView(**vars(h)) for h in action_work.handed(store.read())]  # type: ignore[arg-type]

    return r
