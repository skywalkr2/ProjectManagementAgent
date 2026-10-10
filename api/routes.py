"""API routes for the launch slice: hand in, What changed, review, Follow-ups, status and live updates.

Responses carry data, not wording: labels for what the assistant did come from the UI's wording sheet.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import (
    ActionState,
    Answer,
    Ask,
    BackupStatus,
    ChangeItem,
    ChangesetView,
    Created,
    FollowupAction,
    FollowupQuestion,
    FollowupSection,
    Handed,
    HandIn,
    Ok,
    Option,
    OpView,
    PersonChoice,
    PersonIn,
    PersonPatch,
    PersonView,
    PluginStatusView,
    ProjectIn,
    ProjectPatch,
    ProjectView,
    ReadVersion,
    RecordView,
    Reply,
    RequestCounts,
    Requeued,
    SendBack,
    SentCounts,
    SentText,
    SourceView,
    StageHistoryEntry,
    StageMove,
    StageMoved,
    StageRequestView,
    StageView,
    Status,
    UndoChoice,
    UndoReport,
    Unmark,
)
from engine.applier import move_stage, pick_owner, release
from engine.backup import run_backup, state
from engine.config import Config
from engine.dispatcher import looks_good, retry, send_back, undo_changeset
from engine.followups import mark_sent, sections, unmark_sent
from engine.intake import IntakeError, hand_in, source_text
from engine.names import People
from engine.ops import StageMoveOp
from engine.prompts import render
from engine.records import referrers
from engine.stages import approve_stage_request, record_status, stage_history
from engine.storage import Store, StoreError, WriteContext
from engine.worker import Events, Worker
from engine.workspace import Workspace

_PM = WriteContext(actor="pm", trust="trusted", op="ui")


def build_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/plugins")
    def plugin_status() -> list[PluginStatusView]:
        return [
            PluginStatusView(name=s.name, state=s.state, version=s.version, reason=s.reason)
            for s in store.plugins.status.values()
        ]

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

    @r.get("/records/{record_id}")
    def record_view(record_id: str, kind: str) -> RecordView:
        need(kind, record_id)
        record = store.read().get(kind, record_id)
        return RecordView(
            kind=kind,
            id=record.id,
            version=record.version,
            data=record.data,
            stages=StageView(**record_status(store, record)),
            stage_history=[StageHistoryEntry(**row) for row in stage_history(store, kind, record.id)],
        )

    @r.get("/records/{record_id}/stage-history")
    def record_stage_history(record_id: str, kind: str) -> list[StageHistoryEntry]:
        need(kind, record_id)
        return [StageHistoryEntry(**row) for row in stage_history(store, kind, record_id)]

    @r.get("/stages/ready")
    def ready_stages() -> list[StageView]:
        result = []
        for kind in store.plugins.stages.types:
            for record in store.read().list(kind):
                status = record_status(store, record)
                if status["ready"]:
                    result.append(StageView(**status))
        return result

    @r.post("/stages/move")
    def stage_move(body: StageMove) -> StageMoved:
        op = StageMoveOp(**body.model_dump())
        cs = guard(lambda: move_stage(store, op))
        record = store.read().get(body.record.kind, body.record.id)
        changed()
        return StageMoved(changeset=cs, stages=StageView(**record_status(store, record)))

    @r.get("/stages/requests")
    def stage_requests() -> list[StageRequestView]:
        return [
            StageRequestView(
                id=r.id,
                version=r.version,
                **{key: r.data[key] for key in ("task", "state", "approval", "waiting", "stage_start")},
            )
            for r in store.read().list("request")
            if r.data.get("stage_start")
        ]

    @r.post("/requests/{request_id}/go")
    def stage_request_go(request_id: str, body: ReadVersion) -> Ok:
        guard(lambda: approve_stage_request(store, request_id, body.read_version))
        worker.poke()
        changed()
        return Ok(ok="queued")

    @r.get("/status")
    def status() -> Status:
        reqs = [x.data for x in store.read().list("request")]
        b = state(ws, cfg)
        counts = {s: sum(x["state"] == s for x in reqs) for s in ("queued", "running", "review", "needs_you")}
        return Status(
            backup=BackupStatus(
                configured=b.configured,
                last_success=b.last_success,
                age_hours=b.age_hours,
                needs_attention=b.needs_attention,
                last_error=b.last_error,
            ),
            requests=RequestCounts(**counts),
            version=events.version,
            restart_needed=worker.restart_needed,
        )

    @r.post("/handin")
    def handin(body: HandIn) -> Handed:
        handed = guard(lambda: hand_in(ws, store, note=body.note, pasted=body.pasted))
        changed()
        worker.poke()
        return Handed(request=handed.request, source=handed.source)

    @r.get("/changes")
    def changes() -> list[ChangeItem]:
        people = People(store, cfg)
        projects = {p.id: p.data["name"] for p in store.read().list("project")}
        sources = {s.id: s.data for s in store.read().list("source")}
        out: list[ChangeItem] = []
        for req in reversed(store.read().list("request")):
            d = req.data
            view = None
            if d.get("changeset"):
                cs = store.read().get("changeset", d["changeset"])
                view = ChangesetView(
                    id=cs.id,
                    summary=cs.data["summary"],
                    status=cs.data["status"],
                    reviewed=cs.data["reviewed"],
                    trust=cs.data["trust"],
                    ops=[_op_view(o, store, people, projects) for o in cs.data["ops"]],
                )
            out.append(
                ChangeItem(
                    id=req.id,
                    state=d["state"],
                    waiting=d.get("waiting"),
                    created_at=str(d["created_at"]),
                    note=d.get("note"),
                    source=d.get("source"),
                    source_title=sources.get(d.get("source"), {}).get("title"),
                    changeset=view,
                )
            )
        return out

    @r.post("/changesets/{cs_id}/looks-good")
    def approve(cs_id: str) -> Ok:
        need("changeset", cs_id)
        guard(lambda: looks_good(store, cs_id))
        changed()
        return Ok(ok=cs_id)

    @r.post("/changesets/{cs_id}/reopen")
    def reopen(cs_id: str) -> Ok:
        need("changeset", cs_id)

        def do() -> None:
            with store.transaction() as tx:
                cs = _existing(tx, "changeset", cs_id)
                tx.update("changeset", cs_id, {"reviewed": False}, _PM, read_version=cs.version)
                req = tx.get("request", cs.data["request"])
                tx.update("request", req.id, {"state": "review"}, _PM, read_version=req.version)

        guard(do)
        changed()
        return Ok(ok=cs_id)

    @r.post("/changesets/{cs_id}/undo")
    def undo(cs_id: str, body: UndoChoice) -> UndoReport:
        need("changeset", cs_id)
        report = guard(lambda: undo_changeset(store, cs_id, body.ops))
        changed()
        return UndoReport(restored=report.restored, skipped=report.skipped)

    @r.post("/changesets/{cs_id}/send-back")
    def sendback(cs_id: str, body: SendBack) -> Requeued:
        need("changeset", cs_id)
        new = guard(lambda: send_back(store, cs_id, body.note))
        changed()
        worker.poke()
        return Requeued(request=new)

    @r.post("/changesets/{cs_id}/ops/{index}/release")
    def release_op(cs_id: str, index: int, body: PersonChoice) -> Ok:
        need("changeset", cs_id)
        guard(lambda: release(store, cfg, cs_id, index, person=body.person))
        changed()
        return Ok(ok=cs_id)

    @r.post("/questions/{qid}/pick-owner")
    def owner(qid: str, body: PersonChoice) -> Ok:
        need("question", qid)
        if not body.person:
            raise HTTPException(status_code=422, detail="Choose a person.")
        guard(lambda: pick_owner(store, qid, body.person))
        changed()
        return Ok(ok=qid)

    @r.post("/questions/{qid}/answer")
    def answer(qid: str, body: Answer) -> Ok:
        """Answer a question to the PM. A question asking who (who a name is, who owns an action) takes a person and
        lets the item it holds go ahead; any other question takes a written answer."""
        need("question", qid)
        q = store.read().get("question", qid)
        resolves = q.data.get("resolves") or {}
        if resolves.get("kind") in ("owner", "held-op") and not body.person:
            raise HTTPException(status_code=422, detail="Choose a person.")
        if body.person:
            need("person", body.person)
        if resolves.get("kind") == "owner":
            guard(lambda: pick_owner(store, qid, body.person))
        elif resolves.get("kind") == "held-op":
            guard(lambda: release(store, cfg, resolves["changeset"], resolves["op"], person=body.person))
        else:
            if not (body.text or "").strip():
                raise HTTPException(status_code=422, detail="Write an answer.")

            def do() -> None:
                with store.transaction() as tx:
                    cur = _existing(tx, "question", qid)
                    tx.update(
                        "question", qid, {"status": "answered", "answer": body.text}, _PM, read_version=cur.version
                    )

            guard(do)
        changed()
        return Ok(ok=qid)

    @r.post("/questions/{qid}/reply")
    def reply(qid: str, body: Reply) -> Handed:
        """Hand in a person's reply to a question that went out, with a note saying which question it answers."""
        need("question", qid)
        q = store.read().get("question", qid)
        if q.data["status"] not in ("open", "sent"):
            raise HTTPException(status_code=409, detail="That question is already answered.")
        values = {"name": People(store, cfg).name(q.data["to"]), "title": q.data["title"], "question": qid}
        note = render("reply", values, ws.root)
        handed = guard(lambda: hand_in(ws, store, note=note, pasted=body.text))
        changed()
        worker.poke()
        return Handed(request=handed.request, source=handed.source)

    @r.post("/actions/{action_id}/status")
    def action_status(action_id: str, body: ActionState) -> Ok:
        need("action", action_id)

        def do() -> None:
            with store.transaction() as tx:
                cur = _existing(tx, "action", action_id)
                if cur.data["status"] == "held":
                    raise ValueError("this action needs an owner first")
                tx.update("action", action_id, {"status": body.status}, _PM, read_version=cur.version)

        guard(do)
        changed()
        return Ok(ok=action_id)

    @r.post("/requests/{request_id}/retry")
    def retry_request(request_id: str) -> Ok:
        need("request", request_id)
        guard(lambda: retry(store, request_id))
        changed()
        worker.poke()
        return Ok(ok=request_id)

    @r.get("/sources/{src_id}")
    def source(src_id: str) -> SourceView:
        need("source", src_id)
        src = store.read().get("source", src_id)
        d = src.data
        return SourceView(
            id=src.id,
            title=d["title"],
            kind=d["kind"],
            trust=d["trust"],
            received_at=str(d["received_at"]),
            url=d.get("url"),
            text=source_text(ws, store, src.id),
        )

    @r.get("/followups")
    def followups() -> list[FollowupSection]:
        people = People(store, cfg)
        return [_section(s, people) for s in sections(store, cfg, date.today())]

    @r.post("/followups/{person}/mark-sent")
    def sent(person: str, body: SentText) -> SentCounts:
        need("person", person)
        counts = guard(lambda: mark_sent(store, cfg, person, sent_text=body.text))
        changed()
        return SentCounts(**counts)

    @r.post("/followups/{person}/unmark-sent")
    def unsent(person: str, body: Unmark) -> Ok:
        need("person", person)
        guard(lambda: unmark_sent(store, person, body.question_ids, body.action_ids))
        changed()
        return Ok(ok=person)

    @r.get("/people")
    def people() -> list[PersonView]:
        pm = cfg.workspace.user.person
        return [
            PersonView(
                id=p.id,
                name=p.data["full_name"],
                role=p.data.get("role"),
                org=p.data.get("org"),
                aliases=p.data.get("aliases", []),
                status=p.data.get("status", "active"),
                is_pm=p.id == pm,
            )
            for p in store.read().list("person")
        ]

    def _same_name(kind: str, field: str, value: str, except_id: str | None = None) -> None:
        for rec in store.read().list(kind):
            if rec.id != except_id and rec.data[field].strip().lower() == value.strip().lower():
                raise HTTPException(status_code=409, detail=f"{value} already exists.")

    @r.post("/people")
    def add_person(body: PersonIn) -> Created:
        _same_name("person", "full_name", body.full_name)

        def do() -> str:
            with store.transaction() as tx:
                return tx.create("person", body.model_dump(), _setup("person.add")).id

        new = guard(do)
        changed()
        return Created(id=new)

    @r.post("/people/{pid}")
    def edit_person(pid: str, body: PersonPatch) -> Ok:
        """Change a person. Records refer to people by id, so a new name shows everywhere at once."""
        need("person", pid)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("full_name"):
            _same_name("person", "full_name", changes["full_name"], except_id=pid)
        guard(lambda: _update(store, "person", pid, changes, _setup("person.edit")))
        changed()
        return Ok(ok=pid)

    @r.post("/people/{pid}/remove")
    def remove_person(pid: str) -> Ok:
        need("person", pid)
        if pid == cfg.workspace.user.person:
            raise HTTPException(status_code=409, detail="That's you; you can't be removed.")
        guard(lambda: _remove(store, "person", pid))
        changed()
        return Ok(ok=pid)

    @r.post("/people/{pid}/restore")
    def restore_person(pid: str) -> Ok:
        guard(lambda: _restore(store, "person", pid))
        changed()
        return Ok(ok=pid)

    @r.get("/projects")
    def projects() -> list[ProjectView]:
        names = People(store, cfg)
        return [
            ProjectView(
                id=p.id,
                name=p.data["name"],
                group=p.data.get("group"),
                status=p.data.get("status"),
                phase=p.data.get("phase"),
                target=str(p.data["target"]) if p.data.get("target") else None,
                owner=p.data.get("owner"),
                owner_name=names.name(p.data["owner"]) if p.data.get("owner") else None,
                summary=p.data.get("summary"),
            )
            for p in store.read().list("project")
        ]

    @r.post("/projects")
    def add_project(body: ProjectIn) -> Created:
        _same_name("project", "name", body.name)
        if body.owner:
            need("person", body.owner)

        def do() -> str:
            with store.transaction() as tx:
                return tx.create("project", body.model_dump(exclude_none=True), _setup("project.add")).id

        new = guard(do)
        changed()
        return Created(id=new)

    @r.post("/projects/{prj}")
    def edit_project(prj: str, body: ProjectPatch) -> Ok:
        need("project", prj)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("name"):
            _same_name("project", "name", changes["name"], except_id=prj)
        if changes.get("owner"):
            need("person", changes["owner"])
        guard(lambda: _update(store, "project", prj, changes, _setup("project.edit")))
        changed()
        return Ok(ok=prj)

    @r.post("/projects/{prj}/remove")
    def remove_project(prj: str) -> Ok:
        need("project", prj)
        guard(lambda: _remove(store, "project", prj))
        changed()
        return Ok(ok=prj)

    @r.post("/projects/{prj}/restore")
    def restore_project(prj: str) -> Ok:
        guard(lambda: _restore(store, "project", prj))
        changed()
        return Ok(ok=prj)

    @r.post("/backup")
    def backup_now() -> Status:
        run_backup(ws, cfg)
        changed()
        return status()

    @r.get("/events")
    async def stream() -> StreamingResponse:
        async def gen() -> Any:
            seen = events.version
            yield f"event: hello\ndata: {seen}\n\n"
            while not events.closed:
                seen_now = await asyncio.to_thread(events.wait, seen, 15.0)
                if events.closed:
                    break
                if seen_now != seen:
                    seen = seen_now
                    yield f"event: changed\ndata: {seen}\n\n"
                else:
                    yield ": keep-alive\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    return r


def _setup(op: str) -> WriteContext:
    return WriteContext(actor="pm", trust="trusted", op=op)


def _update(store: Store, kind: str, record_id: str, changes: dict[str, Any], ctx: WriteContext) -> None:
    with store.transaction() as tx:
        cur = _existing(tx, kind, record_id)
        tx.update(kind, record_id, changes, ctx, read_version=cur.version)


def _remove(store: Store, kind: str, record_id: str) -> None:
    """Remove a record nothing refers to; otherwise say what still does."""
    with store.transaction() as tx:
        cur = _existing(tx, kind, record_id)
        using = referrers(tx, kind, record_id)
        if using:
            what = ", ".join(sorted({k for k, _ in using}))
            hint = " Mark them as left instead." if kind == "person" else ""
            raise ValueError(f"Still used by {len(using)} record(s) ({what}), so it can't be removed.{hint}")
        tx.delete(kind, record_id, _setup(f"{kind}.remove"), read_version=cur.version)


def _restore(store: Store, kind: str, record_id: str) -> None:
    with store.transaction() as tx:
        cur = tx.get(kind, record_id, include_deleted=True)
        if cur is None:
            raise KeyError(f"{kind} {record_id} doesn't exist")
        tx.undelete(kind, record_id, _setup(f"{kind}.restore"), read_version=cur.version)


def _existing(tx: Any, kind: str, record_id: str) -> Any:
    rec = tx.get(kind, record_id)
    if rec is None:
        raise StoreError(f"{kind} {record_id} doesn't exist")
    return rec


def _ask(store: Store, people: People, qid: str | None) -> Ask | None:
    q = store.read().get("question", qid) if qid else None
    if q is None:
        return None
    resolves = q.data.get("resolves") or {}
    about = resolves.get("kind") if resolves.get("kind") in ("held-op", "owner") else "other"
    return Ask(
        id=q.id,
        status=q.data["status"],
        about=about,
        name=resolves.get("name"),
        options=[Option(id=pid, name=people.name(pid)) for pid in q.data.get("options", [])],
    )


def _op_view(o: dict[str, Any], store: Store, people: People, projects: dict[str, str]) -> OpView:
    op = o["op"]
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
    elif op["op"] == "action.add":
        meta["owners"] = op.get("owners", [])
        meta["due"] = op.get("due")
    elif op["op"] == "question.add":
        meta["to"] = op.get("to")
    if op["op"] == "record.set":
        meta["field"] = op["field"]
        meta["value"] = op["value"]
    evidence = op.get("evidence")
    return OpView(
        index=o["index"],
        op=op["op"],
        status=o["status"],
        reason=o.get("reason"),
        group=o["group"],
        title=title,
        meta=meta,
        evidence={"quote": evidence["quote"]} if evidence else None,
        record={"kind": record[0], "id": record[1].id} if record else None,
        ask=_ask(store, people, o.get("question")),
    )


def _section(s: Any, people: People) -> FollowupSection:
    questions = []
    for q in s.questions:
        resolves = q.get("resolves") or {}
        questions.append(
            FollowupQuestion(
                id=q["id"],
                title=q["title"],
                text=q["text"],
                links=q["links"],
                kind=q["kind"],
                status=q["status"],
                waiting_days=q["waiting_days"],
                about=resolves.get("kind"),
                options=[Option(id=pid, name=people.name(pid)) for pid in q["options"]],
            )
        )
    actions = [
        FollowupAction(
            id=a["id"],
            text=a["text"],
            due=a["due"],
            project_name=a["project_name"],
            told=a["told"],
            told_days=a["told_days"],
        )
        for a in s.actions
    ]
    return FollowupSection(
        person=s.person,
        name=s.name,
        is_pm=s.is_pm,
        questions=questions,
        actions=actions,
        message=s.message,
        to_send=s.to_send,
    )
