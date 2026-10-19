"""API routes for learning from the sent version (design 6.35): keeping the drafted reply the person copied, and
their answer to "Did your message go out?".

A follow-up's copy is kept by `POST /api/followups/{person}/mark-sent`. A reply's is kept here, when the person
copies the draft. The answers settle a copy the sent folder never matched; each is undone by `unsettle` with what the
answer returned."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import Copied, CopyAnswer, CopySettled, Ok
from engine import sent_version
from engine.config import Config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker


def build_sent_router(cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, sent_version.CopyError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    def need_copy(copy_id: str) -> None:
        if store.read().get("copy", copy_id) is None:
            raise HTTPException(status_code=404, detail=f"copy {copy_id} doesn't exist")

    @r.post("/replies/{action_id}/copied")
    def reply_copied(action_id: str) -> Copied:
        """Keep the drafted reply of a reply owed exactly as the person copied it, so the message they then send can be
        matched to it. Copying it again moves the same copy forward."""
        record = store.read().get("action", action_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        if not record.data.get("reply_owed"):
            raise HTTPException(status_code=409, detail="That isn't a reply you owe.")
        draft = record.data.get("reply")
        if not draft:
            raise HTTPException(status_code=409, detail="There is no reply to copy.")
        made = sent_version.record_copy(
            store, "reply", record.data.get("asker"), draft, actions=[action_id], now=worker.now()
        )
        events.changed()
        return Copied(id=made)

    @r.post("/copies/{copy_id}/settle")
    def settle(copy_id: str, body: CopyAnswer) -> CopySettled:
        """The person's answer to whether a message they copied went out. Returns what Undo takes."""
        need_copy(copy_id)
        previous = guard(lambda: sent_version.settle(store, cfg, copy_id, body.how, worker.now()))
        events.changed()
        return CopySettled(**previous)

    @r.post("/copies/{copy_id}/unsettle")
    def unsettle(copy_id: str, body: CopySettled) -> Ok:
        """Undo an answer: the copy is asked about again as before, and a Not sent is marked as sent again."""
        need_copy(copy_id)
        guard(
            lambda: sent_version.unsettle(
                store,
                copy_id,
                {
                    "settled": body.settled,
                    "ask_again_at": body.ask_again_at.isoformat() if body.ask_again_at else None,
                    "sent_at": body.sent_at,
                    "told": body.told,
                },
            )
        )
        events.changed()
        return Ok(ok=copy_id)

    return r
