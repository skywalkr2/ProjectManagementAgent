"""API routes for asking the assistant (design 6.25): a question becomes an ask, answered from the user guide, the
settings, what the install can do and the records; a suggested setting is applied by the person, a drafted report is
theirs to send."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AnswerView,
    AskIn,
    AskView,
    CiteView,
    Created,
    ProposalApply,
    ReadVersion,
    ReportView,
    SettingChangeView,
    SettingProposalView,
    SettingsSaved,
)
from engine import settings as config_screens
from engine.config import Config
from engine.storage import Store, StoreError, WriteContext
from engine.worker import Events, Worker
from engine.workspace import Workspace

_PM = WriteContext("pm", "trusted", "ui")
LISTED = 50


def build_ask_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.post("/ask")
    def ask(body: AskIn) -> Created:
        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Ask a question.")
        with store.transaction() as tx:
            request = tx.create(
                "request",
                {
                    "task": "ask",
                    "note": question,
                    "origin": "pm",
                    "state": "queued",
                    "waiting": "With the assistant, starting now",
                    "created_at": worker.now().isoformat(),
                },
                _PM,
            )
        worker.poke()
        events.changed()
        return Created(id=request.id)

    @r.get("/asks")
    def asks() -> list[AskView]:
        view = store.read()
        asked = [q for q in view.list("request") if q.data["task"] == "ask"]
        asked.sort(key=lambda q: str(q.data.get("created_at", "")), reverse=True)

        def of(kind: str, request_id: str) -> list[Any]:
            return view.find(kind, {"request": request_id})

        out = []
        for q in asked[:LISTED]:
            answers = of("answer", q.id)
            answer = None
            if answers:
                found = answers[-1].data
                answer = AnswerView(text=found["text"], cites=[CiteView(**c) for c in found.get("cites", [])])
            out.append(
                AskView(
                    id=q.id,
                    question=q.data.get("note") or "",
                    state=q.data["state"],
                    waiting=q.data.get("waiting"),
                    created_at=str(q.data["created_at"]),
                    changeset=q.data.get("changeset"),
                    answer=answer,
                    proposals=[
                        SettingProposalView(
                            id=p.id, version=p.version, **_pick(p.data, "key", "value", "why", "status")
                        )
                        for p in of("setting_proposal", q.id)
                    ],
                    reports=[
                        ReportView(id=x.id, version=x.version, **_pick(x.data, "title", "text", "status"))
                        for x in of("report", q.id)
                    ],
                )
            )
        return out

    def mark(kind: str, record_id: str, read_version: int, status: str) -> None:
        try:
            with store.transaction() as tx:
                if tx.get(kind, record_id) is None:
                    raise HTTPException(status_code=404, detail=f"there is no {kind} {record_id}")
                tx.update(kind, record_id, {"status": status}, _PM, read_version=read_version)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()

    @r.post("/setting-proposals/{proposal_id}/apply")
    def apply_proposal(proposal_id: str, body: ProposalApply) -> SettingsSaved:
        proposal = store.read().get("setting_proposal", proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail=f"there is no suggestion {proposal_id}")
        if proposal.data["status"] != "open" or proposal.version != body.read_version:
            raise HTTPException(status_code=409, detail="That suggestion changed since you saw it.")
        try:
            saved = config_screens.save(
                ws,
                cfg,
                store,
                changes={proposal.data["key"]: proposal.data["value"]},
                reset=[],
                read_fingerprint=body.fingerprint,
                env=dict(os.environ),
            )
        except config_screens.SettingsConflict as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        except StoreError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        mark("setting_proposal", proposal_id, proposal.version, "applied")
        return SettingsSaved(
            changes=[SettingChangeView(**c) for c in saved.changes],
            fingerprint=saved.fingerprint,
            needs_restart=bool(saved.changes) and worker.needs_restart(),
        )

    @r.post("/setting-proposals/{proposal_id}/dismiss")
    def dismiss_proposal(proposal_id: str, body: ReadVersion) -> Created:
        mark("setting_proposal", proposal_id, body.read_version, "dismissed")
        return Created(id=proposal_id)

    @r.post("/reports/{report_id}/sent")
    def report_sent(report_id: str, body: ReadVersion) -> Created:
        mark("report", report_id, body.read_version, "sent")
        return Created(id=report_id)

    @r.post("/reports/{report_id}/dismiss")
    def report_dismiss(report_id: str, body: ReadVersion) -> Created:
        mark("report", report_id, body.read_version, "dismissed")
        return Created(id=report_id)

    return r


def _pick(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: data.get(k) for k in keys}
