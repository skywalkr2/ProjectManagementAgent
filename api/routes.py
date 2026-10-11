"""API routes for the launch slice: hand in, What changed, review, Follow-ups, status and live updates.

Responses carry data, not wording: labels for what the assistant did come from the UI's wording sheet.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from api.schemas import (
    ActionApplied,
    ActionApply,
    ActionChoice,
    ActionGroup,
    ActionItem,
    ActionPreviewItem,
    ActionProposalView,
    ActionRun,
    ActionState,
    AiState,
    Answer,
    Ask,
    BackupStatus,
    ChangeItem,
    ChangesetView,
    ChoiceOption,
    Created,
    FileKindView,
    FileView,
    FollowupAction,
    FollowupQuestion,
    FollowupSection,
    Handed,
    HandIn,
    NoteView,
    Ok,
    Option,
    OpView,
    PersonActionView,
    PersonChoice,
    PersonIn,
    PersonPatch,
    PersonView,
    PluginStatusView,
    ProjectIn,
    ProjectPatch,
    ProjectView,
    ProposedFile,
    ProposedOp,
    ReadVersion,
    RecordView,
    Reply,
    RequestChanged,
    RequestCounts,
    Requeued,
    SendBack,
    SentCounts,
    SentText,
    SourceView,
    SpendStatus,
    StageHistoryEntry,
    StageMove,
    StageMoved,
    StageRequestView,
    StageView,
    Status,
    TaskKindView,
    TaskStart,
    TaskStarted,
    UndoChoice,
    UndoReport,
    Unmark,
)
from engine import actions as person_actions
from engine.ai.smoke import ai_state
from engine.applier import move_stage, pick_owner, release
from engine.backup import run_backup, state
from engine.config import Config
from engine.dispatcher import dismiss, looks_good, retry, send_back, undismiss, undo_changeset
from engine.followups import mark_sent, sections, unmark_sent
from engine.intake import IntakeError, hand_in, source_text
from engine.names import People
from engine.ops import StageMoveOp
from engine.plugin_host import check_about
from engine.prompts import render
from engine.records import referrers
from engine.stages import approve_stage_request, record_status, stage_history
from engine.storage import Store, StoreError, WriteContext
from engine.usage import spend
from engine.worker import Events, Worker
from engine.workspace import Workspace

_PM = WriteContext(actor="pm", trust="trusted", op="ui")


def build_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/plugins")
    def plugin_status() -> list[PluginStatusView]:
        return [
            PluginStatusView(name=s.name, state=s.state, version=s.version, reason=s.reason, tools=s.tools)
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

    def file_view(record: Any) -> FileView:
        kinds = store.plugins.file_kinds()
        kind = kinds.get(record.data["file_kind"])
        label = (kind.label if kind else "") or record.data["file_kind"].rsplit("/", 1)[-1].replace(
            "-", " "
        ).capitalize()
        return FileView(
            id=record.id,
            version=record.version,
            kind_label=label,
            **{
                k: record.data.get(k)
                for k in (
                    "name",
                    "media_type",
                    "size",
                    "file_kind",
                    "project",
                    "meta",
                    "origin",
                    "replaces",
                    "added_at",
                )
            },
        )

    @r.get("/task-kinds")
    def task_kinds(kind: str | None = None) -> list[TaskKindView]:
        """Plugin AI work the person can start on a record of `kind` (or on the workspace with no kind)."""
        found = [
            k
            for name, k in store.plugins.tasks.items()
            if "/" in name and store.plugins.active(name.split("/", 1)[0]) and k.on == kind
        ]
        return [
            TaskKindView(
                name=k.name, label=k.label or k.name.rsplit("/", 1)[-1].replace("-", " ").capitalize(), on=k.on
            )
            for k in sorted(found, key=lambda k: k.label or k.name)
        ]

    @r.post("/task-kinds/{name:path}/start")
    def task_start(name: str, body: TaskStart) -> TaskStarted:
        about = body.about.model_dump() if body.about else None

        def start() -> str:
            if "/" not in name:
                raise StoreError("start a plugin's kind of work here; hand things in for the core's")
            kind = store.plugins.task_kind(name)
            with store.transaction() as tx:
                check_about(tx, kind, about)
                return tx.create(
                    "request",
                    {
                        "task": name,
                        "note": body.note.strip() or None,
                        "about": about,
                        "origin": "pm",
                        "state": "queued",
                        "waiting": "With the assistant, starting now",
                        "created_at": store.clock(),
                    },
                    _PM,
                ).id

        request_id = guard(start)
        worker.poke()
        changed()
        return TaskStarted(request=request_id)

    @r.get("/plugin-actions")
    def plugin_actions(kind: str | None = None, id: str | None = None) -> list[PersonActionView]:
        found = person_actions.available(store, kind, id)
        return [PersonActionView(name=a.name, label=a.label, on=a.on) for a in found]

    @r.post("/plugin-actions/{name:path}/preview")
    def person_action_preview(name: str, body: ActionRun) -> ActionProposalView:
        target = body.target.model_dump() if body.target else None
        pending = guard(
            lambda: person_actions.preview(
                store, cfg, name, target, body.choices, previous=body.previous, kept=body.kept
            )
        )
        return ActionProposalView(
            token=pending.token,
            action=pending.action,
            summary=pending.summary,
            ops=[ProposedOp(**o) for o in guard(lambda: person_actions.labels(store, pending))],
            items=[
                ActionItem(
                    id=i["id"],
                    label=i["label"],
                    group=i["group"],
                    kept=i["kept"],
                    ops=[ProposedOp(**o) for o in guard(lambda i=i: person_actions.labels(store, pending, i["ops"]))],
                )
                for i in pending.items
            ],
            groups=[ActionGroup(**g) for g in pending.groups],
            files=[
                ProposedFile(**{k: f[k] for k in ("name", "media_type", "size", "file_kind")}) for f in pending.files
            ],
            previews=[
                ActionPreviewItem(
                    name=p["name"],
                    media_type=p["media_type"],
                    caption=p["caption"],
                    data_base64=base64.b64encode(p["data"]).decode("ascii"),
                )
                for p in pending.previews
            ],
            choices=[
                ActionChoice(
                    id=c["id"],
                    label=c["label"],
                    value=c["value"],
                    options=[ChoiceOption(**o) for o in c["options"]],
                    help=c["help"],
                    group=c["group"],
                )
                for c in pending.choice_list
            ],
            notes=pending.notes,
            expires_at=pending.expires_at,
        )

    @r.post("/plugin-actions/apply")
    def person_action_apply(body: ActionApply) -> ActionApplied:
        cs_id = guard(lambda: person_actions.apply(store, cfg, body.token, body.kept))
        ops = store.read().get("changeset", cs_id).data["ops"]
        changed()
        return ActionApplied(
            changeset=cs_id,
            **{status: sum(o["status"] == status for o in ops) for status in ("applied", "held", "refused")},
        )

    @r.get("/file-kinds")
    def file_kinds() -> list[FileKindView]:
        limits = cfg.storage.files
        return [
            FileKindView(
                name=k.name,
                label=k.label or k.name.rsplit("/", 1)[-1].replace("-", " ").capitalize(),
                accept=[t for t in k.accept if t in limits.accepted_types] if k.accept else list(limits.accepted_types),
                max_mb=min(limits.max_file_mb, k.max_mb or limits.max_file_mb),
                details_schema=k.details.model_json_schema(),
            )
            for k in store.plugins.file_kinds().values()
        ]

    @r.get("/files")
    def files(project: str | None = None, kind: str | None = None) -> list[FileView]:
        out = [f for f in store.read().list("file") if project is None or f.data.get("project") == project]
        out = [f for f in out if kind is None or f.data["file_kind"] == kind]
        return [file_view(f) for f in sorted(out, key=lambda f: f.data["added_at"], reverse=True)]

    @r.post("/files")
    async def add_file_route(
        request: Request,
        name: str,
        kind: str = "attachment",
        project: str | None = None,
        meta: str = "{}",
        replaces: str | None = None,
    ) -> FileView:
        """Add a file: the request body is the file's bytes, its Content-Type the media type, details as JSON."""
        import json

        from engine.files import add_file

        cap = cfg.storage.files.max_file_mb * 1024 * 1024
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            raise HTTPException(status_code=413, detail=f"{name} is larger than {cfg.storage.files.max_file_mb:g} MB")
        data = await request.body()
        try:
            details = json.loads(meta)
        except ValueError:
            raise HTTPException(status_code=422, detail="the file's details aren't valid JSON") from None
        media_type = (request.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
        record = guard(
            lambda: add_file(
                store,
                cfg,
                data,
                name=name,
                media_type=media_type,
                file_kind=kind,
                project=project,
                meta=details,
                replaces=replaces,
            )
        )
        changed()
        return file_view(record)

    @r.get("/files/{file_id}/content")
    def file_content(file_id: str) -> Response:
        """A file's bytes. Images may show in the app; everything else downloads; nothing is rendered as a page."""
        from engine.files import read_bytes

        need("file", file_id)
        record, data = guard(lambda: read_bytes(store, file_id))
        media = record.data["media_type"]
        inline = media in ("image/png", "image/jpeg", "image/gif", "image/webp")
        safe = "".join(c for c in record.data["name"] if c.isalnum() or c in " ._-").strip() or "file"
        disposition = f'{"inline" if inline else "attachment"}; filename="{safe}"'
        headers = {"Content-Disposition": disposition, "X-Content-Type-Options": "nosniff"}
        return Response(content=data, media_type=media if inline else "application/octet-stream", headers=headers)

    def staged(kind: str) -> None:
        # Only kinds that move through stages are served here; bookkeeping records have their own routes.
        if kind not in store.plugins.stages.types:
            raise HTTPException(status_code=404, detail="not found")

    @r.get("/records/{record_id}")
    def record_view(record_id: str, kind: str) -> RecordView:
        staged(kind)
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
        staged(kind)
        need(kind, record_id)
        return [StageHistoryEntry(**row) for row in stage_history(store, kind, record_id)]

    @r.get("/stages/ready")
    def ready_stages() -> list[StageView]:
        result = []
        for kind in store.plugins.stages.types:
            for record in store.read().list(kind):
                status = record_status(store, record)
                # Only an item already in a stage is suggested a move; starting one is the Stages view's job.
                if status["ready"] and status["current"] is not None:
                    result.append(StageView(**status))
        return result

    @r.get("/stages/records")
    def stage_records() -> list[StageView]:
        result = []
        for kind in store.plugins.stages.types:
            if "/" in kind and not store.plugins.active(kind.split("/")[0]):
                continue
            for record in store.read().list(kind):
                result.append(StageView(**record_status(store, record)))
        return sorted(result, key=lambda view: (view.record.kind, view.title.casefold(), view.record.id))

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
                estimate_usd=r.data.get("estimate_usd"),
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
        ai, detail = ai_state(ws, cfg, store)
        spent = spend(store, cfg)
        return Status(
            ai=AiState(state=ai, detail=detail),
            spend=SpendStatus(
                today_usd=spent.today_usd,
                month_usd=spent.month_usd,
                per_day_usd=spent.per_day_usd,
                per_month_usd=spent.per_month_usd,
                warn=spent.warn,
                warn_today=spent.warn_today,
                warn_month=spent.warn_month,
            ),
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

    @r.get("/notes")
    def notes() -> list[NoteView]:
        """Every filed note, newest first, with the project it was filed under (if any)."""
        projects = {p.id: p.data["name"] for p in store.read().list("project")}
        filed: dict[str, str] = {}
        for entry in store.read().ledger(kind="note"):
            filed.setdefault(entry["record_id"], str(entry["at"]))
        rows = [
            NoteView(
                id=n.id,
                text=n.data["text"],
                project=n.data.get("project"),
                project_name=projects.get(n.data.get("project")),
                created_at=filed.get(n.id),
                trust=n.data.get("trust", "trusted"),
            )
            for n in store.read().list("note")
        ]
        return sorted(rows, key=lambda n: (n.created_at or "", n.id), reverse=True)

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
                    version=req.version,
                    state=d["state"],
                    dismissed=bool(d.get("dismissed")),
                    waiting=d.get("waiting"),
                    created_at=str(d["created_at"]),
                    note=d.get("note"),
                    source=d.get("source"),
                    source_title=sources.get(d.get("source"), {}).get("title"),
                    approval=d.get("approval"),
                    stage_task=bool(d.get("stage_start")),
                    estimate_usd=d.get("estimate_usd"),
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

    @r.post("/requests/{request_id}/dismiss")
    def dismiss_request(request_id: str, body: ReadVersion) -> RequestChanged:
        need("request", request_id)
        guard(lambda: dismiss(store, request_id, body.read_version))
        changed()
        return RequestChanged(ok=request_id, version=store.read().get("request", request_id).version)

    @r.post("/requests/{request_id}/undismiss")
    def undismiss_request(request_id: str, body: ReadVersion) -> RequestChanged:
        need("request", request_id)
        guard(lambda: undismiss(store, request_id, body.read_version))
        changed()
        worker.poke()
        return RequestChanged(ok=request_id, version=store.read().get("request", request_id).version)

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
    title = o.get("label") or op.get("text") or op.get("title") or op.get("answer") or op.get("full_name") or ""
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
        if kind == "note":
            meta["project"] = projects.get(d.get("project"))
    elif op["op"] == "action.add":
        meta["owners"] = op.get("owners", [])
        meta["due"] = op.get("due")
    elif op["op"] == "question.add":
        meta["to"] = op.get("to")
    elif op["op"] == "note":
        meta["project"] = projects.get(op.get("project"))
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
                sent=q["sent"],
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
