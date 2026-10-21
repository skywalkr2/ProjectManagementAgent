"""API route for Send feedback (design 7, Help): the last failures the person may add to a message, masked."""

from __future__ import annotations

import os

from fastapi import APIRouter

from api.schemas import FeedbackProblem, FeedbackProblems
from engine import problems
from engine.config import Config, ConfigError, load_config
from engine.storage import Store
from engine.today import zone
from engine.worker import Worker
from engine.workspace import Workspace


def build_feedback_router(ws: Workspace, cfg: Config, store: Store, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def current() -> Config:
        """The settings as the files hold them now, so a change to how far back or how many applies at once."""
        try:
            return load_config(ws.config_dir, env=dict(os.environ))
        except ConfigError:
            return cfg

    @r.get("/feedback/problems")
    def feedback_problems() -> FeedbackProblems:
        """The failures of the last `ui.feedback_problem_days` days, newest first and at most `ui.feedback_problem_max`:
        failed AI calls, account checks and source reads, and errors in the app. Each has when, what was being done,
        the account's service, adapter and program version, the request's settings, the status, the error kind and the
        service's own error text. Secrets, addresses, paths and the names of the workspace's own people, projects and
        files are masked; nothing the person wrote or read is in it. The app sends nothing: the person sends it."""
        live = current()
        here = zone(live)
        found = problems.recent(ws, store, live, worker.now())
        return FeedbackProblems(
            problems=[
                FeedbackProblem(
                    at=p.at.astimezone(here),
                    doing=p.doing,
                    what=p.what,
                    service=p.service,
                    adapter=p.adapter,
                    program_version=p.program_version,
                    params=p.params,
                    status=p.status,
                    error_kind=p.error_kind,
                    text=p.text,
                )
                for p in found
            ]
        )

    return r
