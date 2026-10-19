"""API routes for the walkthrough's first result (design 7.8): where the look back over the person's own mail stands,
the one go that starts it, and the promises found with one follow-up ready to copy. The look back is the quiet intake of
the sources a sign-in brought (6.32); the follow-up is copied through the Follow-ups screen's own route."""

from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from api.schemas import FirstPromisesView, IntakeStarted
from engine import first_promises
from engine.config import Config, ConfigError, load_config
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_first_promises_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def current() -> Config:
        """The settings as the files hold them now, so the number of promises shown applies at once."""
        try:
            return load_config(ws.config_dir, env=dict(os.environ))
        except ConfigError:
            return cfg

    @r.get("/setup/first-promises")
    def first_result() -> FirstPromisesView:
        """Where the first result stands: the look back offered with its estimate, under way, or done with the
        promises found and one follow-up ready. Writes nothing."""
        return FirstPromisesView(**asdict(first_promises.view(ws, store, current())))

    @r.post("/setup/first-promises/go")
    def first_result_go() -> IntakeStarted:
        """The person's go for the look back: everything it counted starts, as the go on Today's line does."""
        try:
            started = first_promises.go(ws, store, current())
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        if started:
            worker.poke()
            events.changed()
        return IntakeStarted(started=started)

    return r
