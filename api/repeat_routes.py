"""Repeating to-dos (design 6.32): checking the words typed for a repeat, setting it, and stopping it.

Checking reads the words and answers what they were understood as, so the form can say it back before anything is kept.
Setting and stopping are the person's own `action.repeat`, applied as theirs with Undo; neither is a correction of the
assistant's work."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import Applied, RepeatCheckIn, RepeatCheckView, RepeatSetIn, RepeatShapeView
from engine import repeats
from engine.applier import apply_as_person
from engine.config import Config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker


def build_repeat_router(cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.post("/repeats/check")
    def check(body: RepeatCheckIn) -> RepeatCheckView:
        """What the words typed for a repeat are read as, from the to-do's day (or today). Nothing is kept."""
        found = repeats.read_phrase(body.phrase, body.start, repeats.local_today(store, cfg))
        return RepeatCheckView(
            status=found.status,  # type: ignore[arg-type]
            rule=found.rule,
            shape=RepeatShapeView(**repeats.shape_view(found.shape)) if found.shape else None,
            start=found.start,
        )

    @r.post("/actions/{action_id}/repeat")
    def set_repeat(action_id: str, body: RepeatSetIn) -> Applied:
        """Make an open to-do repeat as the words say, with Undo. A to-do with no day is due on the first day the words
        fall on; words that aren't clear, or a day that isn't one of theirs, are refused in plain words."""
        record = store.read().get("action", action_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        start = body.start
        if start is None and record.data.get("due"):
            start = date.fromisoformat(str(record.data["due"]))
        found = repeats.read_phrase(body.phrase, start, repeats.local_today(store, cfg))
        if found.status == "unclear":
            raise HTTPException(status_code=409, detail="That repeat isn't clear. Try something like 'every Tuesday'.")
        if found.status == "off_start":
            raise HTTPException(
                status_code=409, detail=f"The to-do's day isn't one of those days. The first that is: {found.start}."
            )
        op = {
            "op": "action.repeat",
            "id": action_id,
            "rule": found.rule,
            "phrase": body.phrase,
            "start": found.start.isoformat(),
        }
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Set how a to-do repeats"))
        events.changed()
        return Applied(changeset=cs_id)

    @r.post("/actions/{action_id}/repeat/stop")
    def stop_repeat(action_id: str) -> Applied:
        """Stop an open to-do repeating, with Undo. It stays as it is; no next one is made when it ends."""
        if store.read().get("action", action_id) is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        op = {"op": "action.repeat", "id": action_id}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Stopped a to-do repeating"))
        events.changed()
        return Applied(changeset=cs_id)

    return r
