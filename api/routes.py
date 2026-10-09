"""API routes for the launch slice: hand in, What changed, review, Follow-ups, status and live updates.

Responses carry data, not wording: labels for what the assistant did come from the UI's wording sheet.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from engine.applier import pick_owner, release
from engine.backup import run_backup, state
from engine.config import Config
from engine.dispatcher import looks_good, send_back, undo_changeset
from engine.followups import mark_sent, sections
from engine.intake import IntakeError, hand_in
from engine.names import People
from engine.storage import Store, StoreError, WriteContext
from engine.worker import Events, Worker
from engine.workspace import Workspace

_PM = WriteContext(actor="pm", trust="trusted", op="ui")


class HandIn(BaseModel):
    note: str = ""
    pasted: str = ""


class Note(BaseModel):
    note: str


class Indices(BaseModel):
    ops: list[int] | None = None


class PersonChoice(BaseModel):
    person: str | None = None


class SentText(BaseModel):
    text: str | None = None


class Answer(BaseModel):
    text: str


def build_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def changed() -> None:
        events.changed()

    def need(kind: str, record_id: str) -> None:
        if store.read().get(kind, record_id) is None:
            raise HTTPException(status_code=404, detail=f"{kind} {record_id} doesn't exist")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, IntakeError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.get("/status")
    def status() -> dict[str, Any]:
        reqs = [x.data for x in store.read().list("request")]
        backup = state(ws, cfg)
        return {
            "backup": {
                "configured": backup.configured,
                "last_success": backup.last_success,
                "age_hours": backup.age_hours,
                "needs_attention": backup.needs_attention,
                "message": backup.message,
            },
            "requests": {s: sum(x["state"] == s for x in reqs) for s in ("queued", "running", "review", "needs_you")},
            "version": events.version,
        }

    @r.post("/handin")
    def handin(body: HandIn) -> dict[str, Any]:
        handed = guard(lambda: hand_in(ws, store, note=body.note, pasted=body.pasted))
        changed()
        worker.poke()
        return {"request": handed.request, "source": handed.source}

    @r.get("/changes")
    def changes() -> list[dict[str, Any]]:
        people = People(store, cfg)
        projects = {p.id: p.data["name"] for p in store.read().list("project")}
        sources = {s.id: s.data for s in store.read().list("source")}
        out = []
        for req in reversed(store.read().list("request")):
            d = req.data
            item: dict[str, Any] = {
                "id": req.id,
                "state": d["state"],
                "waiting": d.get("waiting"),
                "created_at": d["created_at"],
                "note": d.get("note"),
                "source": sources.get(d.get("source"), {}).get("title"),
                "changeset": None,
            }
            if d.get("changeset"):
                cs = store.read().get("changeset", d["changeset"])
                item["changeset"] = {
                    "id": cs.id,
                    "summary": cs.data["summary"],
                    "status": cs.data["status"],
                    "reviewed": cs.data["reviewed"],
                    "trust": cs.data["trust"],
                    "ops": [_op_view(o, store, people, projects, sources) for o in cs.data["ops"]],
                }
            out.append(item)
        return out

    @r.post("/changesets/{cs_id}/looks-good")
    def approve(cs_id: str) -> dict[str, str]:
        need("changeset", cs_id)
        guard(lambda: looks_good(store, cs_id))
        changed()
        return {"ok": cs_id}

    @r.post("/changesets/{cs_id}/reopen")
    def reopen(cs_id: str) -> dict[str, str]:
        need("changeset", cs_id)

        def do() -> None:
            with store.transaction() as tx:
                cs = _existing(tx, "changeset", cs_id)
                tx.update("changeset", cs_id, {"reviewed": False}, _PM, read_version=cs.version)
                req = tx.get("request", cs.data["request"])
                tx.update("request", req.id, {"state": "review"}, _PM, read_version=req.version)

        guard(do)
        changed()
        return {"ok": cs_id}

    @r.post("/changesets/{cs_id}/undo")
    def undo(cs_id: str, body: Indices) -> dict[str, Any]:
        need("changeset", cs_id)
        report = guard(lambda: undo_changeset(store, cs_id, body.ops))
        changed()
        return {"restored": report.restored, "skipped": report.skipped}

    @r.post("/changesets/{cs_id}/send-back")
    def sendback(cs_id: str, body: Note) -> dict[str, str]:
        need("changeset", cs_id)
        new = guard(lambda: send_back(store, cs_id, body.note))
        changed()
        worker.poke()
        return {"request": new}

    @r.post("/changesets/{cs_id}/ops/{index}/release")
    def release_op(cs_id: str, index: int, body: PersonChoice) -> dict[str, str]:
        need("changeset", cs_id)
        guard(lambda: release(store, cfg, cs_id, index, person=body.person))
        changed()
        return {"ok": cs_id}

    @r.post("/questions/{qid}/pick-owner")
    def owner(qid: str, body: PersonChoice) -> dict[str, str]:
        need("question", qid)
        if not body.person:
            raise HTTPException(status_code=422, detail="Choose a person.")
        guard(lambda: pick_owner(store, qid, body.person))
        changed()
        return {"ok": qid}

    @r.post("/questions/{qid}/answer")
    def answer(qid: str, body: Answer) -> dict[str, str]:
        need("question", qid)

        def do() -> None:
            with store.transaction() as tx:
                q = _existing(tx, "question", qid)
                tx.update("question", qid, {"status": "answered", "answer": body.text}, _PM, read_version=q.version)

        guard(do)
        changed()
        return {"ok": qid}

    @r.get("/followups")
    def followups() -> list[dict[str, Any]]:
        return [s.__dict__ for s in sections(store, cfg, date.today())]

    @r.post("/followups/{person}/mark-sent")
    def sent(person: str, body: SentText) -> dict[str, int]:
        need("person", person)
        counts = guard(lambda: mark_sent(store, cfg, person, sent_text=body.text))
        changed()
        return counts

    @r.get("/people")
    def people() -> list[dict[str, Any]]:
        return [
            {"id": p.id, "name": p.data["full_name"], "role": p.data.get("role")} for p in store.read().list("person")
        ]

    @r.post("/backup")
    def backup_now() -> dict[str, Any]:
        result = run_backup(ws, cfg)
        changed()
        return result

    @r.get("/events")
    async def stream() -> StreamingResponse:
        async def gen() -> Any:
            seen = events.version
            yield f"event: hello\ndata: {seen}\n\n"
            while True:
                seen_now = await asyncio.to_thread(events.wait, seen, 15.0)
                if seen_now != seen:
                    seen = seen_now
                    yield f"event: changed\ndata: {seen}\n\n"
                else:
                    yield ": keep-alive\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    return r


def _existing(tx: Any, kind: str, record_id: str) -> Any:
    rec = tx.get(kind, record_id)
    if rec is None:
        raise StoreError(f"{kind} {record_id} doesn't exist")
    return rec


def _op_view(
    o: dict[str, Any], store: Store, people: People, projects: dict[str, str], sources: dict[str, Any]
) -> dict[str, Any]:
    op = o["op"]
    view: dict[str, Any] = {
        "index": o["index"],
        "op": op["op"],
        "status": o["status"],
        "reason": o.get("reason"),
        "question": o.get("question"),
        "group": o["group"],
        "problems": o.get("problems", []),
    }
    evidence = op.get("evidence")
    if evidence:
        view["evidence"] = {"quote": evidence["quote"]}
    record = None
    for ref in o.get("records", []):
        rec = store.read().get(ref["kind"], ref["id"], include_deleted=True)
        if rec is not None and ref["kind"] in ("action", "question", "fact", "note", "person", "project"):
            record = (ref["kind"], rec)
            break
    title = op.get("text") or op.get("title") or op.get("answer") or op.get("full_name") or ""
    meta: dict[str, Any] = {}
    if record:
        kind, rec = record
        d = rec.data
        title = d.get("text") or d.get("title") or d.get("full_name") or d.get("name") or title
        if kind == "action":
            meta["owners"] = [people.name(x["person"]) for x in d.get("owners", [])]
            meta["due"] = d.get("due")
            meta["project"] = projects.get(d.get("project"))
            meta["action_status"] = d.get("status")
        if kind == "question":
            meta["to"] = people.name(d.get("to"))
        view["record"] = {"kind": kind, "id": rec.id}
    elif op["op"] == "action.add":
        meta["owners"] = op.get("owners", [])
        meta["due"] = op.get("due")
    elif op["op"] == "question.add":
        meta["to"] = op.get("to")
    if op["op"] == "record.set":
        meta["field"] = op["field"]
        meta["value"] = op["value"]
    view["title"] = title
    view["meta"] = meta
    return view


def utc_now() -> datetime:
    return datetime.now(UTC)
