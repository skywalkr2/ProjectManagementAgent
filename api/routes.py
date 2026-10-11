"""API routes for the launch slice: hand in, What changed, review, Follow-ups, status and live updates.

Responses carry data, not wording: labels for what the assistant did come from the UI's wording sheet.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from api.schemas import (
    AccountChoice,
    ActionApplied,
    ActionApply,
    ActionChoice,
    ActionGroup,
    ActionItem,
    ActionPreviewItem,
    ActionProposalView,
    ActionRequestView,
    ActionRun,
    ActionState,
    AgendaItemView,
    AiState,
    Answer,
    Applied,
    ArrivedView,
    Ask,
    AuthorSpan,
    BackupStatus,
    ChangeItem,
    ChangesetView,
    ChoiceOption,
    Created,
    FieldView,
    FileKindView,
    FileView,
    FollowupAction,
    FollowupQuestion,
    FollowupSection,
    GenericRecordView,
    Handed,
    HandIn,
    InboxView,
    JobView,
    KindView,
    ListRenameIn,
    ListValueIn,
    NoteView,
    Ok,
    Option,
    OpView,
    OrganizationIn,
    OrganizationPatch,
    OrganizationView,
    OutsideEditView,
    PanelRow,
    PanelView,
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
    RecordEdit,
    RecordReference,
    RecordView,
    Reply,
    RequestChanged,
    RequestCounts,
    Requeued,
    RetryRequest,
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
    SyncView,
    TakenBack,
    TaskKindView,
    TaskStart,
    TaskStarted,
    TextChoices,
    TextEdit,
    TextFieldView,
    TextRegion,
    TextReview,
    TextVersionView,
    TodayLineView,
    TodoView,
    UndoChoice,
    UndoReport,
    Unmark,
    ValueListView,
    WorkingCopyFormatView,
    WorkingCopyOut,
    WorkingCopyView,
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
from engine.plugin_api import CORE_LINE_ACTIONS
from engine.plugin_host import check_about
from engine.prompts import render
from engine.records import referrers
from engine.stages import approve_stage_request, record_status, stage_history
from engine.storage import Store, StoreError, WriteContext
from engine.texts import text_presence
from engine.usage import spend
from engine.worker import Events, Worker
from engine.workspace import Workspace

_PM = WriteContext(actor="pm", trust="trusted", op="ui")


def _field_type(annotation: Any) -> tuple[str, list[str]]:
    """What kind of value a field's annotation holds, and a choice's options."""
    import datetime as dt
    import types
    from typing import Annotated, Literal, Union, get_args, get_origin

    origin = get_origin(annotation)
    if origin is Annotated:
        return _field_type(get_args(annotation)[0])
    if origin is Union or isinstance(annotation, types.UnionType):
        inner = [a for a in get_args(annotation) if a is not type(None)]
        return _field_type(inner[0]) if len(inner) == 1 else ("other", [])
    if origin is Literal:
        return "choice", [str(v) for v in get_args(annotation)]
    if origin in (list, tuple, set):
        return "list", []
    if annotation is bool:
        return "yes_no", []
    if annotation in (int, float):
        return "number", []
    if annotation in (dt.date, dt.datetime):
        return "date", []
    if annotation is str:
        return "text", []
    return "other", []


def build_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/plugins")
    def plugin_status() -> list[PluginStatusView]:
        return [
            PluginStatusView(
                name=s.name, state=s.state, version=s.version, reason=s.reason, tools=s.tools, notes=s.notes
            )
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

    def _last_refused(request_id: str) -> bool:
        runs = store.read().find("run", {"request": request_id})
        return bool(runs) and runs[-1].data["outcome"] == "refused"

    def _summary_of(changeset_id: str | None) -> str | None:
        found = store.read().get("changeset", changeset_id) if changeset_id else None
        return found.data.get("summary") if found is not None else None

    def _independence(cs: Any) -> str | None:
        run = store.read().get("run", cs.data["run"]) if cs.data.get("run") else None
        return run.data.get("independence") if run is not None else None

    def shown_kinds() -> set[str]:
        """Kinds a screen may show any record of: those written to the synced folder, running plugins' own, and
        the kinds of their panels."""
        kinds = {k for k, m in store.plugins.records.items() if getattr(m, "layout", None) or k == "project"}
        for plugin, registrar in store.plugins.registrars.items():
            if store.plugins.active(plugin):
                kinds |= set(registrar.records) | {p.kind for p in registrar.panels.values()}
        return kinds

    @r.get("/kinds/{kind:path}")
    def kind_view(kind: str) -> KindView:
        from engine.records import list_fields, ref_fields
        from engine.texts import long_text_fields

        if kind not in shown_kinds():
            raise HTTPException(status_code=404, detail="not found")
        model = store.plugins.records[kind]
        texts, refs = long_text_fields(model), dict(ref_fields(model))
        bound = {field: name for field, name, _ in list_fields(model)}
        offered = {r.data["name"]: r.data["values"] for r in store.read().list("value_list")}
        fields = []
        for name, info in model.model_fields.items():
            if name == "ext":
                continue
            value_type, options = _field_type(info.annotation)
            if name in texts:
                value_type = "long_text"
            elif name in refs:
                value_type = "reference"
            elif name in bound:
                value_type, options = "choice", list(offered.get(bound[name], []))
            fields.append(
                FieldView(
                    name=name,
                    description=info.description or "",
                    long_text=texts.get(name),
                    refers_to=refs.get(name),
                    type=value_type,
                    options=options,
                    value_list=bound.get(name),
                    required=info.is_required(),
                    editable=name not in ("id", "stage") and name not in texts,
                )
            )
        return KindView(kind=kind, fields=fields)

    @r.get("/record")
    def generic_record(kind: str, id: str) -> GenericRecordView:
        from engine.texts import long_text_fields

        if kind not in shown_kinds():
            raise HTTPException(status_code=404, detail="not found")
        need(kind, id)
        record = store.read().get(kind, id)
        texts = long_text_fields(store.plugins.records[kind])
        return GenericRecordView(
            kind=kind,
            id=record.id,
            version=record.version,
            fields={k: v for k, v in record.data.items() if k not in texts and k != "ext"},
            long_text=list(texts),
        )

    @r.get("/lists")
    def value_lists() -> list[ValueListView]:
        """Every value list, with the fields that use it."""
        from engine.records import list_fields

        users: dict[str, list[str]] = {}
        for kind, model in store.plugins.records.items():
            for field, name, _ in list_fields(model):
                users.setdefault(name, []).append(f"{kind}.{field}")
        return [
            ValueListView(
                id=r.id,
                name=r.data["name"],
                label=r.data["label"],
                values=r.data["values"],
                retired=r.data["retired"],
                used_by=users.get(r.data["name"], []),
            )
            for r in sorted(store.read().list("value_list"), key=lambda r: r.data["label"].casefold())
        ]

    def list_op(op: dict[str, Any], summary: str) -> Applied:
        from engine.applier import apply_as_person

        cs_id = guard(lambda: apply_as_person(store, cfg, [op], summary))
        changed()
        return Applied(changeset=cs_id)

    @r.post("/lists/{name:path}/add")
    def list_add(name: str, body: ListValueIn) -> Applied:
        """Add a value to a list (or offer a retired one again), with Undo."""
        return list_op({"op": "list.add", "list": name, "value": body.value}, "Added to a list")

    @r.post("/lists/{name:path}/rename")
    def list_rename(name: str, body: ListRenameIn) -> Applied:
        """Rename a value on a list and on every record that holds it, with Undo."""
        return list_op({"op": "list.rename", "list": name, "value": body.value, "to": body.to}, "Renamed on a list")

    @r.post("/lists/{name:path}/retire")
    def list_retire(name: str, body: ListValueIn) -> Applied:
        """Stop offering a value; records that hold it keep it. Undo offers it again."""
        return list_op({"op": "list.retire", "list": name, "value": body.value}, "Retired from a list")

    @r.post("/records/edit")
    def record_edit(body: RecordEdit) -> Applied:
        """The person's own change to fields of a shown record, with Undo."""
        from engine.applier import apply_as_person

        if body.kind not in shown_kinds():
            raise HTTPException(status_code=404, detail="not found")
        op = {
            "op": "record.edit",
            "record": {"kind": body.kind, "id": body.id},
            "fields": body.fields,
            "read_version": body.read_version,
        }
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Changed on screen"))
        changed()
        return Applied(changeset=cs_id)

    @r.get("/sync")
    def sync_status() -> SyncView:
        from engine import outside
        from engine.handover import conflict_copies
        from engine.sync import folder_problem

        folder = cfg.storage.sync.folder.strip()
        result = worker.sync_result
        problem = worker.sync_problem or (folder_problem(ws, cfg) if folder else None)
        edits, copies = [], []
        if folder and problem is None:
            from pathlib import Path

            edits = [
                OutsideEditView(
                    path=path, proposal=note.get("changeset"), version=note.get("version"), problem=note.get("problem")
                )
                for path, note in sorted(outside.pending(cfg).items())
            ]
            copies = conflict_copies(Path(folder).expanduser().resolve())
        return SyncView(
            folder=folder,
            problem=problem,
            stopped=worker.sync_lost,
            changed_outside=list(result.changed_outside) if result else [],
            removed_outside=list(result.removed_outside) if result else [],
            rebuilt=list(result.rebuilt) if result else [],
            outside_edits=edits,
            conflict_copies=copies,
        )

    @r.get("/today/agenda")
    def today_agenda() -> list[AgendaItemView]:
        """Events from watched calendars on today and the next configured days, in the person's time zone."""
        from engine import today

        return [AgendaItemView(**vars(a)) for a in today.agenda(store, cfg, datetime.now(UTC))]

    @r.get("/today/todo")
    def today_todo() -> list[TodoView]:
        """The person's own open actions: overdue, due today, then the rest."""
        from engine import today

        return [TodoView(**vars(t)) for t in today.todo(store, cfg, datetime.now(UTC))]

    @r.get("/today/arrived")
    def today_arrived() -> InboxView:
        """Messages from watched mailboxes received within the configured hours, newest first."""
        from engine import today

        inbox = today.arrived(store, cfg, datetime.now(UTC))
        return InboxView(items=[ArrivedView(**vars(a)) for a in inbox.items], left_out=inbox.left_out)

    @r.get("/plugin-today")
    def plugin_today() -> list[TodayLineView]:
        """Lines running plugins add to Today."""
        lines = []
        for plugin, line in store.plugins.today():
            registrar = store.plugins.registrars[plugin]
            action_is = None
            if line.action in CORE_LINE_ACTIONS:
                action_is = "core"
            elif line.action is not None:
                action_is = "action" if line.action in registrar.actions else "task"
            lines.append(
                TodayLineView(
                    plugin=plugin,
                    id=line.id,
                    text=line.text,
                    about=RecordReference(kind=line.about[0], id=line.about[1]) if line.about else None,
                    action=line.action,
                    action_is=action_is,
                    why=line.why,
                    until=line.until,
                )
            )
        return lines

    @r.get("/panels")
    def panels(project: str | None = None) -> list[PanelView]:
        """The screens running plugins add; with a project, only those its add-on lists on that project."""
        found = []
        for plugin, registrar in sorted(store.plugins.registrars.items()):
            if store.plugins.active(plugin):
                found += [
                    PanelView(
                        name=p.name,
                        title=p.title,
                        tab=p.tab,
                        kind=p.kind,
                        view=p.view,
                        columns=list(p.columns),
                        primary_action=p.primary_action,
                        row_actions=list(p.row_actions),
                        new_action=p.new_action,
                    )
                    for p in registrar.panels.values()
                    if project is None or store.plugins.panel_shown_for(p, project)
                ]
        return found

    @r.get("/panels/{name:path}/rows")
    def panel_rows(name: str, project: str | None = None) -> list[PanelRow]:
        rows = guard(lambda: store.plugins.panel_rows(name, project))
        return [PanelRow(**row) for row in rows]

    @r.get("/jobs")
    def jobs() -> list[JobView]:
        """Plugins' scheduled work: whether it runs, how often, and how its last run went."""
        found = []
        for plugin, registrar in sorted(store.plugins.registrars.items()):
            if not store.plugins.active(plugin):
                continue
            for name in sorted(registrar.jobs):
                enabled, every = store.plugins.job_settings(name)
                last = store.plugins.last_job_run(name)
                found.append(
                    JobView(
                        name=name,
                        plugin=plugin,
                        enabled=enabled,
                        every_minutes=every,
                        last_run_at=str(last.data["started_at"]) if last else None,
                        last_outcome=last.data["outcome"] if last else None,
                        last_error=last.data.get("error") if last else None,
                    )
                )
        return found

    @r.get("/task-kinds")
    def task_kinds(kind: str | None = None, id: str | None = None) -> list[TaskKindView]:
        """Plugin AI work the person can start on a record of `kind` (or on the workspace with no kind); with `id`,
        only the work offered on that record."""
        record = store.read().get(kind, id) if kind and id else None
        if kind and id and record is None:
            raise HTTPException(status_code=404, detail=f"{kind} {id} doesn't exist")
        found = [
            k
            for name, k in store.plugins.tasks.items()
            if "/" in name
            and store.plugins.active(name.split("/", 1)[0])
            and k.on == kind
            and (record is None or k.startable_on(record, text_presence(store, store.read(), record)))
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
                check_about(tx, kind, about, store, starting=True)
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

    def _version_view(v: Any) -> TextVersionView:
        return TextVersionView(
            id=v.id,
            number=v.data["number"],
            version=v.version,
            status=v.data["status"],
            source=v.data["source"],
            words=v.data["words"],
            base=v.data.get("base"),
            note=v.data.get("note"),
            unmapped=v.data.get("unmapped") or [],
            questions=v.data.get("questions") or [],
            created_at=str(v.data["created_at"]),
        )

    @r.get("/texts")
    def text_field(kind: str, id: str, field: str) -> TextFieldView:
        from engine import texts

        view = store.read()
        if view.get(kind, id) is None:
            raise HTTPException(status_code=404, detail=f"{kind} {id} doesn't exist")
        every = texts.versions(view, kind, id, field)
        now = texts.current(view, kind, id, field)
        return TextFieldView(
            text=texts.read_text(store, now.data["sha256"]) if now else "",
            current=now.data["number"] if now else None,
            authorship=[
                AuthorSpan(**{k: s[k] for k in ("start", "end", "kind")}, words=s.get("words", 0))
                for s in (now.data["authorship"] if now else [])
            ],
            versions=[_version_view(v) for v in every],
        )

    @r.get("/text-versions/{version_id}/review")
    def text_review(version_id: str) -> TextReview:
        from engine import texts

        found = guard(lambda: texts.review(store, store.read(), version_id))
        b_text, b_units, _ = found["texts"]["base"]
        c_text, c_units, _ = found["texts"]["current"]
        p_text, p_units, _ = found["texts"]["pending"]

        def stretch(text: str, units: list, start: int, end: int) -> str:
            return "".join(text[u.start : u.end] for u in units[start:end]).strip()

        base, now = found["base"], found["current"]
        return TextReview(
            version=_version_view(found["pending"]),
            current=now.data["number"] if now else None,
            three_way=(base.id if base else None) != (now.id if now else None),
            regions=[
                TextRegion(
                    id=g.id,
                    side=g.side,
                    base=stretch(b_text, b_units, g.b1, g.b2),
                    current=stretch(c_text, c_units, g.c1, g.c2),
                    pending=stretch(p_text, p_units, g.p1, g.p2),
                )
                for g in found["regions"]
            ],
            pending_text=p_text,
        )

    @r.post("/text-versions/{version_id}/accept")
    def text_accept(version_id: str, body: TextChoices) -> Applied:
        from engine.applier import apply_as_person

        op = {"op": "text.accept", "version": version_id, "read_version": body.read_version, "choices": body.choices}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Accepted text changes"))
        changed()
        return Applied(changeset=cs_id)

    @r.post("/text-versions/{version_id}/discard")
    def text_discard(version_id: str, body: TextChoices) -> Applied:
        from engine.applier import apply_as_person

        op = {"op": "text.discard", "version": version_id, "read_version": body.read_version}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Set a text version aside"))
        changed()
        return Applied(changeset=cs_id)

    @r.post("/texts/edit")
    def text_edit(body: TextEdit) -> Applied:
        from engine.applier import apply_as_person

        op = {"op": "text.edit", "record": {"kind": body.kind, "id": body.id}, "field": body.field, "text": body.text}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Edited text"))
        changed()
        return Applied(changeset=cs_id)

    def _copy_view(c: Any) -> WorkingCopyView:
        from engine import working

        try:
            label = working._format(store, c.data["format"])[1].label
        except StoreError:
            label = c.data["format"]
        return WorkingCopyView(
            id=c.id,
            format=c.data["format"],
            label=label,
            field=c.data["field"],
            base=c.data.get("base"),
            status=c.data["status"],
            stale=working.stale(store, c),
            file=c.data["file"],
            proposal=c.data.get("proposal"),
            handed_at=str(c.data["handed_at"]),
            returned_at=str(c.data["returned_at"]) if c.data.get("returned_at") else None,
        )

    @r.get("/working-copies/formats")
    def working_copy_formats(kind: str, field: str) -> list[WorkingCopyFormatView]:
        from engine import working

        return [
            WorkingCopyFormatView(name=w.name, label=w.label, extension=w.extension)
            for w in working.formats_for(store, kind, field)
        ]

    @r.get("/working-copies")
    def working_copies(kind: str, id: str) -> list[WorkingCopyView]:
        found = [
            c for c in store.read().list("working_copy") if (c.data["owner_kind"], c.data["owner_id"]) == (kind, id)
        ]
        return [_copy_view(c) for c in sorted(found, key=lambda c: str(c.data["handed_at"]), reverse=True)]

    @r.post("/working-copies")
    def working_copy_out(body: WorkingCopyOut) -> WorkingCopyView:
        from engine import working

        copy = guard(lambda: working.hand_out(store, cfg, body.format, body.kind, body.id, body.field))
        changed()
        return _copy_view(copy)

    @r.post("/working-copies/{copy_id}/return")
    async def working_copy_return(copy_id: str, request: Request, name: str | None = None) -> TakenBack:
        """Bring a working copy back: the request body is the file's bytes."""
        from engine import working

        data = await request.body()
        result = guard(lambda: working.take_back(store, cfg, copy_id, data, name))
        changed()
        return TakenBack(**result)

    @r.post("/working-copies/{copy_id}/drop")
    def working_copy_drop(copy_id: str) -> Ok:
        from engine import working

        guard(lambda: working.drop(store, copy_id))
        changed()
        return Ok(ok=copy_id)

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
            requests=[
                ActionRequestView(
                    id=r["id"],
                    task=r["task"],
                    label=store.plugins.task_kind(r["task"]).label or r["task"],
                    about=RecordReference(**r["about"]) if r["about"] and "kind" in r["about"] else None,
                    note=r["note"],
                    kept=r["kept"],
                    group=r["group"],
                    item=(r["about"] or {}).get("item"),
                )
                for r in pending.requests
            ],
            ops=[ProposedOp(**o) for o in guard(lambda: person_actions.labels(store, pending))],
            items=[
                ActionItem(
                    id=i["id"],
                    label=i["label"],
                    group=i["group"],
                    kept=i["kept"],
                    ops=[ProposedOp(**o) for o in guard(lambda i=i: person_actions.labels(store, pending, i["ops"]))],
                    refused=i.get("refused"),
                )
                for i in pending.items
            ],
            groups=[ActionGroup(**g) for g in pending.groups],
            problems=pending.problems,
            files=[
                ProposedFile(**{k: f[k] for k in ("name", "media_type", "size", "file_kind")}) for f in pending.files
            ],
            previews=[
                ActionPreviewItem(
                    name=p["name"],
                    media_type=p["media_type"],
                    caption=p["caption"],
                    alt=p.get("alt") or p["caption"],
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
                    text=c.get("text", False),
                    max_length=c.get("max_length", 200),
                )
                for c in pending.choice_list
            ],
            notes=pending.notes,
            expires_at=pending.expires_at,
        )

    @r.post("/plugin-actions/apply")
    def person_action_apply(body: ActionApply) -> ActionApplied:
        cs_id = guard(lambda: person_actions.apply(store, cfg, body.token, body.kept, body.kept_requests))
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
            can_restart=worker.can_restart,
            restart_for=list(worker.restart_for),
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
        handed = guard(
            lambda: hand_in(
                ws, store, note=body.note, pasted=body.pasted, data_level=body.data_level, project=body.project
            )
        )
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
                    second_opinion=_independence(cs),
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
                    refused=d["state"] == "needs_you" and _last_refused(req.id),
                    follows=d.get("follows"),
                    follows_summary=_summary_of(d.get("follows")),
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

    @r.get("/requests/{request_id}/accounts")
    def request_accounts(request_id: str) -> list[AccountChoice]:
        """The accounts that may take this request's material, for sending it somewhere else after a refusal."""
        from engine.ai.router import accounts
        from engine.dispatcher import _data_level, content_levels

        need("request", request_id)
        req = store.read().get("request", request_id)
        tiers = {ref: name for name, t in cfg.ai.tiers.items() for ref in [t.use, *t.fallback] if ref}
        return [
            AccountChoice(use=ref, label=f"{ref.partition('/')[0]} ({tiers.get(ref, '')})".replace(" ()", ""))
            for ref in accounts(cfg, _data_level(store, req.data), content_levels(store, req.data))
        ]

    @r.post("/requests/{request_id}/retry")
    def retry_request(request_id: str, body: RetryRequest | None = None) -> Ok:
        need("request", request_id)
        guard(lambda: retry(store, request_id, body.use if body else None))
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
        orgs = {o.id: o.data["name"] for o in store.read().list("organization")}
        return [
            PersonView(
                id=p.id,
                name=p.data["full_name"],
                role=p.data.get("role"),
                org=p.data.get("org"),
                org_name=orgs.get(p.data.get("org") or ""),
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
        if body.org:
            need("organization", body.org)

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
        if changes.get("org"):
            need("organization", changes["org"])
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

    @r.get("/organizations")
    def organizations() -> list[OrganizationView]:
        """The organizations people work for, by name."""
        count: dict[str, int] = {}
        for p in store.read().list("person"):
            if p.data.get("org"):
                count[p.data["org"]] = count.get(p.data["org"], 0) + 1
        found = [
            OrganizationView(
                id=o.id,
                name=o.data["name"],
                aliases=o.data.get("aliases", []),
                notes=o.data.get("notes"),
                people=count.get(o.id, 0),
            )
            for o in store.read().list("organization")
        ]
        return sorted(found, key=lambda o: o.name.casefold())

    @r.post("/organizations")
    def add_organization(body: OrganizationIn) -> Created:
        _same_name("organization", "name", body.name)

        def do() -> str:
            with store.transaction() as tx:
                return tx.create("organization", body.model_dump(), _setup("organization.add")).id

        new = guard(do)
        changed()
        return Created(id=new)

    @r.post("/organizations/{oid}")
    def edit_organization(oid: str, body: OrganizationPatch) -> Ok:
        """Rename or change an organization. People refer to it by id, so a new name shows everywhere at once."""
        need("organization", oid)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("name"):
            _same_name("organization", "name", changes["name"], except_id=oid)
        guard(lambda: _update(store, "organization", oid, changes, _setup("organization.edit")))
        changed()
        return Ok(ok=oid)

    @r.post("/organizations/{oid}/remove")
    def remove_organization(oid: str) -> Ok:
        need("organization", oid)
        guard(lambda: _remove(store, "organization", oid))
        changed()
        return Ok(ok=oid)

    @r.post("/organizations/{oid}/restore")
    def restore_organization(oid: str) -> Ok:
        guard(lambda: _restore(store, "organization", oid))
        changed()
        return Ok(ok=oid)

    @r.get("/projects")
    def projects() -> list[ProjectView]:
        from engine.projects import language_for, spent_on

        names = People(store, cfg)
        view = store.read()
        return [
            ProjectView(
                parent=p.data.get("parent"),
                language=language_for(view, cfg.workspace.language, p),
                language_own=bool(p.data.get("language")),
                content_levels=p.data.get("content_levels") or [],
                budget_usd=p.data.get("budget_usd"),
                spent_usd=round(spent_on(store, p.id), 4),
                id=p.id,
                name=p.data["name"],
                group=p.data.get("group"),
                status=p.data.get("status"),
                phase=p.data.get("phase"),
                priority=p.data.get("priority"),
                target=str(p.data["target"]) if p.data.get("target") else None,
                owner=p.data.get("owner"),
                owner_name=names.name(p.data["owner"]) if p.data.get("owner") else None,
                summary=p.data.get("summary"),
            )
            for p in store.read().list("project")
        ]

    def _project_fields(changes: dict, prj: str | None = None) -> None:
        """Refuse a parent that would put a project inside itself, and content levels the AI settings don't have."""
        from engine.applier import parent_problem

        if changes.get("parent"):
            why = parent_problem(store.read(), prj, changes["parent"])
            if why:
                raise HTTPException(status_code=409, detail=why)
        unknown = sorted(set(changes.get("content_levels") or []) - set(cfg.ai.content_levels))
        if unknown:
            detail = f"{', '.join(unknown)} isn't a content level in the AI settings"
            raise HTTPException(status_code=409, detail=detail)

    @r.post("/projects")
    def add_project(body: ProjectIn) -> Created:
        _same_name("project", "name", body.name)
        if body.owner:
            need("person", body.owner)
        _project_fields(body.model_dump())

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
        _project_fields(changes, prj)
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
