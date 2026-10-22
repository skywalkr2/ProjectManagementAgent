"""Adding a to-do by hand (design 6.32): reading the day typed for it, and adding it as the person's own change.

Reading answers what the words were understood as, so the form can say it back before anything is kept. Adding applies
at once and answers with the changes made, in order, so Undo takes them back last first."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import TodoAdded, TodoAddIn, TodoDayCheckIn, TodoDayView
from engine import add_todo
from engine.config import Config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker


def build_todo_router(cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.post("/todos/day")
    def check_day(body: TodoDayCheckIn) -> TodoDayView:
        """What the words typed for a to-do's day are read as, from today on the person's own clock. Nothing is kept."""
        found = add_todo.read_day(store, cfg, body.words)
        return TodoDayView(status=found.status, day=found.day)  # type: ignore[arg-type]

    @r.post("/todos")
    def add(body: TodoAddIn) -> TodoAdded:
        """Add a to-do as the person's own, with Undo. Words, a day or a repeat that aren't clear, or a repeat that
        doesn't fall on the day, are refused in plain words and nothing is kept."""
        try:
            action, changesets = add_todo.add(
                store,
                cfg,
                text=body.text,
                when=body.when,
                owners=body.owners,
                project=body.project,
                repeat=body.repeat,
            )
        except (add_todo.TodoProblem, StoreError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        return TodoAdded(action=action, changesets=changesets)

    return r
