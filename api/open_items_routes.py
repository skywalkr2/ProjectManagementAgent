"""Every open action and open question in one place (design 7.5), and merging a near-duplicate into the action it
repeats.

Editing, closing, reassigning, holding and dropping from a row use the routes the other screens use (`POST
/api/records/edit`, `/api/actions/{id}/status`, `/api/actions/{id}/hold`, `/api/actions/{id}/drop`, `POST
/api/questions/{id}/reword`, `/reroute`, `/drop`); each is the person's own change, with Undo and its signal."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    ActionMergeIn,
    AlikeView,
    Applied,
    BlockerView,
    OpenActionView,
    OpenItemsView,
    OpenQuestionView,
    OwnerNameView,
)
from engine.config import Config
from engine.open_items import OpenAction, OpenQuestion, merge_actions, open_actions, open_questions
from engine.storage import Store, StoreError
from engine.today import zone
from engine.worker import Events, Worker
from engine.workspace import Workspace


def _action(r: OpenAction) -> OpenActionView:
    return OpenActionView(
        id=r.id,
        version=r.version,
        text=r.text,
        state=r.state,  # type: ignore[arg-type]
        owners=[OwnerNameView(person=o.person, name=o.name, team=o.team) for o in r.owners],
        due=r.due,  # type: ignore[arg-type]
        project=r.project,
        project_name=r.project_name,
        parent_name=r.parent_name,
        notes=r.notes,
        since=r.since,
        on_hold=r.on_hold,
        blocker=BlockerView(**asdict(r.blocker)) if r.blocker is not None else None,
        duplicate=AlikeView(**asdict(r.duplicate)) if r.duplicate is not None else None,
        origin=r.origin,  # type: ignore[arg-type]
        untouched_days=r.untouched_days,
        owner_question=r.owner_question,
        to_send=r.to_send,
    )


def _question(r: OpenQuestion) -> OpenQuestionView:
    return OpenQuestionView(**{k: v for k, v in asdict(r).items()})  # type: ignore[arg-type]


def build_open_items_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.get("/open-items")
    def open_items() -> OpenItemsView:
        """Every action still to do, with its owners, due date, project, parent project and where it came from, and
        every
        question still waiting, with who it waits on and since when."""
        now = datetime.now(UTC)
        today = now.astimezone(zone(cfg)).date()
        return OpenItemsView(
            actions=[_action(a) for a in open_actions(store, cfg, today, now=now)],
            questions=[_question(q) for q in open_questions(store, cfg, today)],
            stale_days=cfg.ui.today.stale_after_days,
        )

    @r.post("/actions/{action_id}/merge")
    def merge(action_id: str, body: ActionMergeIn) -> Applied:
        """Keep this action and close the one it nearly repeats, as one change with one Undo. Its notes gain the other's
        words, it takes the earlier date, and the other is dropped, which is a correction the assistant learns from."""
        if store.read().get("action", action_id) is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        done = guard(lambda: merge_actions(store, cfg, action_id, body.other, body.read_version, body.other_version))
        events.changed()
        return Applied(changeset=done)

    return r
