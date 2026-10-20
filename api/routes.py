"""API routes for the launch slice: hand in, What changed, review, Follow-ups, status and live updates.

Responses carry data, not wording: labels for what the assistant did come from the UI's wording sheet.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any, Literal
from urllib.parse import quote

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
    AppliedEntryView,
    ArrivedView,
    Ask,
    AssistantAccountRuns,
    AssistantChain,
    AssistantPaused,
    AssistantStatus,
    AuthorSpan,
    BackupStatus,
    BlockerView,
    ChangeItem,
    ChangesetView,
    ChoiceOption,
    Created,
    DocumentBlock,
    DocumentView,
    FieldView,
    FileKindView,
    FileView,
    FirstGoSorting,
    FirstGoStarted,
    FollowedUp,
    FollowupAction,
    FollowupQuestion,
    FollowupSection,
    GenericRecordView,
    Handed,
    HandIn,
    HandoverChoice,
    HandoverSideView,
    HandoverView,
    HeldChanged,
    HeldIn,
    HoldChanged,
    HoldIn,
    HoldRestore,
    InboxCheckView,
    InboxView,
    ItemTitle,
    JobView,
    KindView,
    LeftOutView,
    ListRenameIn,
    ListSuggestionView,
    ListValueIn,
    MadeView,
    NetworkWait,
    Noted,
    NoteIn,
    NoteView,
    NudgeRecorded,
    NudgeSent,
    NudgeUnsent,
    NudgeView,
    Ok,
    Option,
    OpView,
    OrganizationIn,
    OrganizationPatch,
    OrganizationView,
    OutsideEditView,
    OwnerPick,
    OwnerSuggestionView,
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
    ProjectRoleIn,
    ProjectView,
    ProposedFile,
    ProposedOp,
    QueueLineView,
    ReadVersion,
    RecordEdit,
    RecordPageView,
    RecordRef,
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
    SourceLimit,
    SourceLimitPerson,
    SourceView,
    SourceWiden,
    SpendStatus,
    StageHistoryEntry,
    StageMove,
    StageMoved,
    StageRequestView,
    StageView,
    Status,
    StopCauseView,
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
    Unfollow,
    Unmark,
    ValueListView,
    WorkingCopyFormatView,
    WorkingCopyOut,
    WorkingCopyView,
)
from engine import actions as person_actions
from engine import catch_up, learned, source_intake
from engine.ai.smoke import ai_state
from engine.applier import move_stage, pick_owner, release
from engine.assistant_status import assistant_state
from engine.backup import run_backup, state
from engine.config import Config
from engine.corrections import answered_assistant
from engine.dispatcher import (
    dismiss,
    grant_first_go,
    is_waiting_for_network,
    looks_good,
    retry,
    send_back,
    spent_by_request,
    undismiss,
    undo_changeset,
    waits_on_first_go,
)
from engine.followups import (
    follow_up,
    hold_question,
    mark_followed_up,
    mark_sent,
    put_on_hold,
    restore_hold,
    sections,
    take_off_hold,
    they_finished,
    undo_follow_up,
    unmark_followed_up,
    unmark_sent,
)
from engine.intake import IntakeError, hand_in, note_as_input, source_text
from engine.made import made_by
from engine.names import People
from engine.next_steps import add_project as add_held_project
from engine.next_steps import unfile_missing
from engine.ops import StageMoveOp
from engine.origin import origins
from engine.owners import suggest_owner
from engine.plugin_api import CORE_LINE_ACTIONS
from engine.plugin_host import check_about
from engine.promises import ENDING_NAMES
from engine.prompts import render
from engine.records import Scope, referrers
from engine.stages import approve_stage_request, record_status, stage_history
from engine.storage import Store, StoreError, WriteContext
from engine.texts import text_presence
from engine.usage import spend
from engine.worker import Events, Worker
from engine.workspace import Workspace

log = logging.getLogger(__name__)
_PM = WriteContext(actor="pm", trust="trusted", op="ui")


def content_disposition(kind: str, name: str) -> str:
    """A Content-Disposition value: an ASCII-only fallback name plus the full name in UTF-8 (RFC 6266)."""
    ascii_name = "".join(c for c in name if c.isascii() and (c.isalnum() or c in " ._-")).strip() or "file"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


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

    def hand_note(item: tuple[str, str], text: str | None, route: str, author: str | None = None) -> str | None:
        """Hand the note typed with a change to the assistant once the change is saved: the person's own words, or,
        on a button that relays someone else, content reported about `author`."""
        request = guard(lambda: note_as_input(ws, store, cfg, item=item, text=text or "", route=route, author=author))
        if request is not None:
            worker.poke()
        return request

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
            data_level=record.data.get("sensitivity", "internal"),
        )

    def _last_refused(request_id: str) -> bool:
        runs = store.read().find("run", {"request": request_id})
        return bool(runs) and runs[-1].data["outcome"] == "refused"

    def _summary_of(changeset_id: str | None) -> str | None:
        found = store.read().get("changeset", changeset_id) if changeset_id else None
        return found.data.get("summary") if found is not None else None

    def _applied_views(ids: list[str]) -> list[AppliedEntryView]:
        """The entries a run said it applied that still exist, in plain words."""
        found = []
        for kind, stored in learned.applied_entries(store.read(), ids):
            scope = stored.data.get("applies_to")
            found.append(
                AppliedEntryView(
                    id=stored.id,
                    kind=kind,
                    version=stored.version,
                    text=stored.data.get("text", ""),
                    status=stored.data.get("status", "active"),
                    applies_to=Scope.model_validate(scope) if scope else None,
                )
            )
        return found

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
            origin=origins(store.read(), kind, [id]).get(id) if kind in ("action", "question") else None,
        )

    @r.get("/lists")
    def value_lists() -> list[ValueListView]:
        """Every value list, with the fields that use it."""
        from engine.lists import is_status_list
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
                status=is_status_list(store.read(), r.data["name"]),
                tones=r.data.get("tones") or {},
                meanings=r.data.get("meanings") or {},
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
        op = {"op": "list.add", "list": name, "value": body.value}
        op |= {k: v for k, v in (("tone", body.tone), ("meaning", body.meaning)) if v}
        return list_op(op, "Added to a list")

    @r.get("/list-suggestion")
    def list_suggestion(list: str, value: str) -> ListSuggestionView:
        """The tone, and for a status list the meaning, offered for a value being added; the person can change both."""
        from engine.lists import is_status_list, suggest

        offered = suggest(value)
        status = is_status_list(store.read(), list)
        return ListSuggestionView(tone=offered["tone"], meaning=offered["meaning"] if status else None)

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
        before = store.read().get(body.kind, body.id)
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Changed on screen"))
        saved = store.read().get("changeset", cs_id).data["ops"][0]["status"] == "applied"
        if saved and body.kind == "action" and "notes" in body.fields and before is not None:
            added = _added_text(before.data.get("notes"), body.fields["notes"])
            hand_note(("action", body.id), added, "notes_edited")
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
            shared=cfg.storage.sync.shared,
            handover=(worker.handover_state() or (None,))[0],  # type: ignore[arg-type]
        )

    def handover_view() -> HandoverView:
        """Why the folder isn't being used and what the person can choose; the sides come from comparing the two
        histories, which only reads."""
        from engine import handover
        from engine.today import zone

        here = zone(cfg)
        state = worker.handover_state()
        if state is None:
            return HandoverView(state="clear")
        found = handover.situation(ws, cfg)

        def side(entry: Any) -> HandoverSideView | None:
            if entry is None:
                return None
            latest = datetime.fromisoformat(entry.latest).astimezone(here) if entry.latest else None
            return HandoverSideView(computer=entry.computer, changes=entry.changes, latest=latest)

        view = HandoverView(state=state[0], computer=state[1], chosen=handover.chosen(ws))  # type: ignore[arg-type]
        if found is not None and found.kind == "diverged":
            view.here, view.folder = side(found.here), side(found.folder)
        elif found is not None and found.kind == "elsewhere":
            view.computer = found.computer
            view.last_seen = datetime.fromisoformat(found.last_seen).astimezone(here) if found.last_seen else None
            view.minutes_left = found.minutes_left
        return view

    @r.get("/sync/handover")
    def sync_handover() -> HandoverView:
        return handover_view()

    @r.post("/sync/handover")
    def sync_handover_choose(body: HandoverChoice) -> HandoverView:
        """Note which copy to keep. It is carried out at the next start, before the database is opened, through the
        same checks the command line has; nothing about the workspace changes until then."""
        from engine import handover

        if not worker.sync_held:
            raise HTTPException(status_code=409, detail="Nothing is waiting for a choice between the two copies.")
        try:
            handover.choose(ws, cfg, body.which)
        except handover.Refused as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        changed()
        return handover_view()

    @r.delete("/sync/handover")
    def sync_handover_unchoose() -> HandoverView:
        """Take the choice back before the restart carries it out."""
        from engine import handover

        handover.clear_choice(ws)
        changed()
        return handover_view()

    @r.get("/today/agenda")
    def today_agenda() -> list[AgendaItemView]:
        """Events from watched calendars, then the app's own calendar entries, on today and the next configured days,
        in the person's time zone."""
        from engine import today

        return [AgendaItemView(**vars(a)) for a in today.agenda(store, cfg, datetime.now(UTC))]

    @r.get("/today/todo")
    def today_todo() -> list[TodoView]:
        """The person's own open actions: overdue, due today, then the rest."""
        from engine import today

        found = today.todo(store, cfg, datetime.now(UTC))
        origin = origins(store.read(), "action", [t.action for t in found])
        return [
            TodoView(
                **{k: v for k, v in vars(t).items() if k != "blocker"},
                blocker=BlockerView(**asdict(t.blocker)) if t.blocker is not None else None,
                origin=origin[t.action],
            )
            for t in found
        ]

    @r.get("/today/arrived")
    def today_arrived() -> InboxView:
        """Messages from watched mailboxes received within the configured hours, newest first."""
        from engine import today

        inbox = today.arrived(store, cfg, datetime.now(UTC))
        return InboxView(
            items=[ArrivedView(**vars(a)) for a in inbox.items], left_out=inbox.left_out, set_aside=inbox.set_aside
        )

    @r.post("/today/arrived/check")
    def today_arrived_check() -> InboxCheckView:
        """Read every source that is on, now, and return Came in as it stands. A source that can't be read never
        stops the others; its problem shows on the source as after any read."""
        from engine import today, watch

        read = failed = busy = handed = 0
        problems: list[str] = []
        for source in [s for s in cfg.watch.sources if s.enabled]:
            name = source.label or source.id
            try:
                result = watch.refresh(ws, store, cfg, source.id)
            except Exception:  # one source's failure must not stop the rest
                log.exception("reading a source failed")
                failed += 1
                problems.append(f"{name} couldn't be read just now. It is tried again by itself.")
                continue
            if result.outcome == "busy":
                busy += 1
                continue
            if result.outcome in ("failed", "offline", "throttled"):
                failed += 1
                why = watch.problem_text(store, source.id)
                if result.outcome == "failed" and why:
                    problems.append(f"{name} can't be read: {why}")
                elif result.outcome == "offline":
                    problems.append(
                        f"{name} couldn't be checked without an internet connection. It will retry automatically."
                    )
                else:
                    problems.append(f"{name} couldn't be read just now. It is tried again by itself.")
            else:
                read += 1
            handed += len(result.new) + len(result.changed) + len(result.removed) + len(result.taken_in)
        events.changed()
        if handed:
            worker.poke()
        inbox = today.arrived(store, cfg, datetime.now(UTC))
        return InboxCheckView(
            items=[ArrivedView(**vars(a)) for a in inbox.items],
            left_out=inbox.left_out,
            set_aside=inbox.set_aside,
            new_items=handed,
            sources_read=read,
            sources_failed=failed,
            sources_busy=busy,
            problems=problems,
        )

    @r.get("/today/queue")
    def today_queue() -> list[QueueLineView]:
        """What needs the person, ranked: decide, then risk, review, and send and follow up (design 7.7)."""
        from engine.today import zone
        from engine.today_queue import queue

        people = People(store, cfg)
        projects = {p.id: p.data["name"] for p in store.read().list("project")}
        here = zone(cfg)
        out = []
        for line in queue(ws, store, cfg, worker.now(), handover=worker.handover_state()):
            data = {k: v for k, v in vars(line).items() if k not in ("title", "since")}
            if line.until:
                # A time of the person's own clock, so the screen shows it as they would say it.
                data["until"] = datetime.fromisoformat(line.until).astimezone(here)
            if line.waiting_since:
                data["waiting_since"] = datetime.fromisoformat(line.waiting_since).astimezone(here)
            out.append(
                QueueLineView(
                    **data,
                    title=_title_view(line.title, people),
                    person_name=people.name(line.person) if line.person else None,
                    project_name=projects.get(line.project or ""),
                )
            )
        return out

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
                    group=line.group,
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

    @r.get("/panels/{name:path}/document")
    def panel_document(name: str, project: str | None = None) -> DocumentView:
        """A document panel's blocks for the project in view, or the workspace."""
        found = guard(lambda: store.plugins.panel_document(name, project))
        return DocumentView(blocks=None if found is None else [DocumentBlock(**b) for b in found])

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
        data_level: Literal["open", "internal", "restricted"] | None = None,
    ) -> FileView:
        """Add a file: the request body is the file's bytes, its Content-Type the media type, details as JSON. Without
        a `data_level` the file takes its kind's level (internal unless the kind says otherwise)."""
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
                data_level=data_level,
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
        disposition = content_disposition("inline" if inline else "attachment", record.data["name"])
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

    @r.get("/record-pages/{record_id}")
    def record_page(record_id: str, kind: str) -> RecordPageView:
        """Any record's page: core or a plugin's, by its kind."""
        from engine.record_page import page
        from engine.today import zone

        here = zone(cfg)
        found = page(
            store,
            kind,
            record_id,
            pm=cfg.workspace.user.person,
            owner_format=cfg.workspace.owner_format,
            today=datetime.now(UTC).astimezone(here).date(),
            here=here,
        )
        if found is None:
            raise HTTPException(status_code=404, detail=f"There is no {kind} {record_id}.")
        return RecordPageView(**found)

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

    @r.get("/runs/first-go")
    def first_go_sorting() -> FirstGoSorting:
        """What the first go's sorting run would add to the estimate of the runs waiting for it, so the person approves
        the whole spend. Nothing when no run waits for the go or no mail needs sorting."""
        from engine import watch

        if not any(waits_on_first_go(x.data) for x in store.read().list("request")):
            return FirstGoSorting(runs=0)
        runs, estimate, unpriced = watch.first_go_sorting(ws, store, cfg)
        return FirstGoSorting(runs=runs, estimate_usd=estimate, unpriced=unpriced)

    @r.post("/runs/first-go")
    def first_go() -> FirstGoStarted:
        """The person's first go: the mail handed in unsorted while it was pending is sorted first (the go covers that
        run), then every run still waiting for it starts, and no run waits for it again."""
        from engine import watch

        aside = watch.sort_before_first_go(ws, store, cfg)
        started = grant_first_go(store)
        if started or aside:
            worker.poke()
            changed()
        return FirstGoStarted(started=started)

    @r.get("/status")
    def status() -> Status:
        reqs = [x.data for x in store.read().list("request")]
        b = state(ws, cfg)
        counts = {s: sum(x["state"] == s for x in reqs) for s in ("queued", "running", "review", "needs_you")}
        ai, detail = ai_state(ws, cfg, store)
        spent = spend(store, cfg)
        waiting = [x["cause"]["since"] for x in reqs if is_waiting_for_network(x)]
        alive = assistant_state(store, cfg)
        return Status(
            ai=AiState(state=ai, detail=detail),
            assistant=AssistantStatus(
                last_run_at=alive.last_run_at,
                last_run_failed=alive.last_run_failed,
                runs_today=[AssistantAccountRuns(**vars(x)) for x in alive.runs_today],
                queued=alive.queued,
                oldest_queued_since=alive.oldest_queued_since,
                chains=[AssistantChain(**vars(x)) for x in alive.chains],
                paused=[AssistantPaused(**vars(x)) for x in alive.paused],
            ),
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
                encrypted=b.encrypted,
            ),
            requests=RequestCounts(**counts),
            network_wait=NetworkWait(count=len(waiting), since=min(waiting)) if waiting else None,
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
                ws,
                store,
                note=body.note,
                pasted=body.pasted,
                data_level=body.data_level,
                project=body.project,
                cfg=cfg,
            )
        )
        changed()
        worker.poke()
        return Handed(request=handed.request, source=handed.source)

    @r.get("/changes")
    def changes() -> list[ChangeItem]:
        from engine.titles import head_of, title_for
        from engine.today_queue import watched_kinds

        people = People(store, cfg)
        projects = {p.id: p.data["name"] for p in store.read().list("project")}
        sources = {s.id: s.data for s in store.read().list("source")}
        kinds = watched_kinds(store.read())
        spent = spent_by_request(store.read())
        mail = {
            (s.data["source"], s.data["key"]): s.id
            for s in store.read().list("snapshot")
            if s.data.get("message") and not s.data.get("deleted") and not s.data.get("gone")
        }
        out: list[ChangeItem] = []
        for req in reversed(store.read().list("request")):
            d = req.data
            if d.get("set_aside"):
                continue  # mail set aside as not work is listed in the Set aside folder
            if catch_up.waits_on_go(d) or source_intake.waits_on_go(d):
                continue  # learning runs held for the catch-up list's go, and a new source's intake, are one line
            view = None
            cs = None
            source = sources.get(d.get("source") or "")
            watched = (source or {}).get("watched") or {}
            if d.get("changeset"):
                cs = store.read().get("changeset", d["changeset"])
                view = ChangesetView(
                    id=cs.id,
                    summary=cs.data["summary"],
                    status=cs.data["status"],
                    reviewed=cs.data["reviewed"],
                    trust=cs.data["trust"],
                    ops=[_op_view(o, store, people, projects, cfg) for o in cs.data["ops"]],
                    made=[
                        MadeView(
                            kind=m.kind, id=m.id, label=m.label, record=RecordRef(kind=m.record[0], id=m.record[1])
                        )
                        for m in made_by(store.read(), cs.data["ops"])
                    ],
                    second_opinion=_independence(cs),
                    applied=_applied_views(cs.data.get("applied") or []),
                    first_on_account=cs.data.get("first_on_account"),
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
                    first_go=waits_on_first_go(d),
                    estimate_usd=d.get("estimate_usd"),
                    range_usd=d.get("range_usd"),
                    spent_usd=spent.get(req.id),
                    refused=d["state"] == "needs_you" and _last_refused(req.id),
                    cause=_cause_view(d),
                    follows=d.get("follows"),
                    follows_summary=_summary_of(d.get("follows")),
                    redoes=learned.request_changeset(store.read(), d.get("previous")),
                    changeset=view,
                    mail_item=mail.get((watched.get("source"), watched.get("key"))) if watched else None,
                    intake=d.get("intake"),
                    title=_title_view(
                        title_for(
                            d,
                            source,
                            cs.data if cs is not None else None,
                            people=people,
                            skip=list(cfg.language.title_skip),
                            head=head_of(ws.sources_dir, (source or {}).get("content_hash")),
                            watched_kind=kinds.get((watched.get("source"), watched.get("key"))),
                        ),
                        people,
                    ),
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
        if report.restored:
            guard(lambda: unfile_missing(store, cs_id))
        changed()
        return UndoReport(restored=report.restored, skipped=report.skipped)

    @r.post("/changesets/{cs_id}/send-back")
    def sendback(cs_id: str, body: SendBack) -> Requeued:
        need("changeset", cs_id)
        new = guard(lambda: send_back(store, cs_id, body.note, undo_first=body.undo_first))
        changed()
        worker.poke()
        return Requeued(request=new)

    @r.post("/changesets/{cs_id}/ops/{index}/release")
    def release_op(cs_id: str, index: int, body: PersonChoice) -> Ok:
        need("changeset", cs_id)
        held = store.read().get("changeset", cs_id).data["ops"]
        if 0 <= index < len(held) and held[index]["op"].get("op") == "project.add" and held[index]["status"] == "held":
            guard(lambda: add_held_project(store, cfg, cs_id, index, ws=ws))
        else:
            guard(lambda: release(store, cfg, cs_id, index, person=body.person, ws=ws))
        changed()
        return Ok(ok=cs_id)

    @r.post("/changesets/{cs_id}/ops/{index}/decline")
    def decline_op(cs_id: str, index: int) -> Ok:
        """Keep things as they are for a held item: it isn't applied and leaves the list, and the choice is a
        correction the assistant learns from."""
        from engine.applier import decline_held

        need("changeset", cs_id)
        guard(lambda: decline_held(store, cs_id, index))
        changed()
        return Ok(ok=cs_id)

    @r.post("/changesets/{cs_id}/ops/{index}/undecline")
    def undecline_op(cs_id: str, index: int) -> Ok:
        """Take back keeping a held item as it was: it waits for the person again."""
        from engine.applier import undecline_held

        need("changeset", cs_id)
        guard(lambda: undecline_held(store, cs_id, index))
        changed()
        return Ok(ok=cs_id)

    @r.post("/questions/{qid}/pick-owner")
    def owner(qid: str, body: OwnerPick) -> Noted:
        need("question", qid)
        if not body.person:
            raise HTTPException(status_code=422, detail="Choose a person.")
        guard(lambda: pick_owner(store, qid, body.person))
        action = store.read().get("question", qid).data["resolves"]["action"]
        request = hand_note(("action", action), body.note, "owner_picked")
        changed()
        return Noted(ok=qid, request=request)

    @r.post("/questions/{qid}/answer")
    def answer(qid: str, body: Answer) -> Noted:
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
            guard(lambda: release(store, cfg, resolves["changeset"], resolves["op"], person=body.person, ws=ws))
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
        asked = q.data.get("to")
        for_someone_else = bool(asked) and asked != People(store, cfg).pm
        if not for_someone_else and resolves.get("kind") not in ("owner", "held-op"):
            # What the answer teaches is learned at once.
            guard(lambda: answered_assistant(store, cfg, qid, body.text or ""))
        request = hand_note(
            ("question", qid),
            body.text,
            "answered_for" if for_someone_else else "answered",
            author=asked if for_someone_else else None,
        )
        changed()
        return Noted(ok=qid, request=request)

    @r.post("/questions/{qid}/reply")
    def reply(qid: str, body: Reply) -> Handed:
        """Hand in a person's reply to a question that went out, with a note saying which question it answers."""
        need("question", qid)
        q = store.read().get("question", qid)
        if q.data["status"] not in ("open", "sent"):
            raise HTTPException(status_code=409, detail="That question is already answered.")
        values = {"name": People(store, cfg).name(q.data["to"]), "title": q.data["title"], "question": qid}
        note = render("reply", values, ws.root)
        handed = guard(lambda: hand_in(ws, store, note=note, pasted=body.text, cfg=cfg))
        changed()
        worker.poke()
        return Handed(request=handed.request, source=handed.source)

    @r.post("/actions/{action_id}/status")
    def action_status(action_id: str, body: ActionState) -> Noted:
        need("action", action_id)

        def do() -> None:
            with store.transaction() as tx:
                cur = _existing(tx, "action", action_id)
                if cur.data["status"] == "held":
                    raise ValueError("this action needs an owner first")
                if cur.data["status"] == "dropped":
                    raise ValueError("this action was dropped; undo the drop to bring it back")
                change: dict[str, Any] = {"status": body.status}
                if body.status == "open":
                    change |= {"done_by": [], "reported_by": None}  # reopening takes the credit back
                elif body.status == "done":
                    # The work is credited to its owners; the person who ticked it is the one who said it was done.
                    owners = [o["person"] for o in cur.data.get("owners", [])]
                    change |= {"done_by": owners, "reported_by": cfg.workspace.user.person}
                tx.update("action", action_id, change, _PM, read_version=cur.version)

        guard(do)
        request = hand_note(("action", action_id), body.note, "mark_done" if body.status == "done" else "reopened")
        changed()
        return Noted(ok=action_id, request=request)

    @r.post("/actions/{action_id}/hold")
    def action_put_on_hold(action_id: str, body: HoldIn) -> HoldChanged:
        """Put an open action on hold, waiting for something. It is never due, overdue or chased while it is."""
        need("action", action_id)
        previous = guard(lambda: put_on_hold(store, action_id, body.waiting_for, on=body.on))
        changed()
        return HoldChanged(ok=action_id, previous=previous)

    @r.post("/actions/{action_id}/unhold")
    def action_taken_off_hold(action_id: str) -> HoldChanged:
        """Take an action off hold; it is due again by its own due date."""
        need("action", action_id)
        previous = guard(lambda: take_off_hold(store, action_id))
        changed()
        return HoldChanged(ok=action_id, previous=previous)

    @r.post("/actions/{action_id}/hold/restore")
    def action_hold_restored(action_id: str, body: HoldRestore) -> Ok:
        """Undo a put on hold or a take off hold: the hold goes back to what it was, and no signal is recorded."""
        need("action", action_id)
        guard(lambda: restore_hold(store, action_id, body.hold.model_dump() if body.hold else None))
        changed()
        return Ok(ok=action_id)

    @r.post("/questions/{question_id}/held-for")
    def question_held_for(question_id: str, body: HeldIn) -> HeldChanged:
        """Hold an unsent question for a meeting, a series or a day (it waits in Later, out of To send, until that
        day), or send it now (no hold). Undo puts back what `previous` says."""
        need("question", question_id)
        held = body.held_for.model_dump(exclude_none=True) if body.held_for else None
        previous = guard(lambda: hold_question(store, question_id, held))
        changed()
        return HeldChanged(ok=question_id, previous=previous)

    @r.post("/followups/{person}/actions/{action_id}/followed-up")
    def action_followed_up(person: str, action_id: str, body: NoteIn | None = None) -> FollowedUp:
        """Record that the PM chased a person about an open action: it stays open and counts as told again. A note
        typed with it goes to the assistant."""
        need("person", person)
        need("action", action_id)
        done = guard(lambda: follow_up(store, action_id, person))
        request = hand_note(("action", action_id), body.note if body else "", "followed_up", person)
        changed()
        return FollowedUp(**done, request=request)

    @r.post("/followups/{person}/actions/{action_id}/unfollow")
    def action_unfollowed(person: str, action_id: str, body: Unfollow) -> Ok:
        need("person", person)
        need("action", action_id)
        guard(lambda: undo_follow_up(store, action_id, person, body.on, body.previous_told))
        changed()
        return Ok(ok=action_id)

    @r.post("/followups/{person}/actions/{action_id}/finished")
    def action_they_finished(person: str, action_id: str, body: NoteIn | None = None) -> Noted:
        """Close an action because the person it waits on finished it: credited to them, reported by the PM. A note
        typed with it goes to the assistant."""
        need("person", person)
        need("action", action_id)
        guard(lambda: they_finished(store, cfg, action_id, person))
        request = hand_note(("action", action_id), body.note if body else "", "they_finished", person)
        changed()
        return Noted(ok=action_id, request=request)

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
            limit=_limit_view(d.get("audience")),
        )

    def _limit_view(found: dict[str, Any] | None) -> SourceLimit | None:
        if not found:
            return None
        who = People(store, cfg)
        return SourceLimit(
            people=[SourceLimitPerson(id=p if p in who.records else None, name=who.name(p)) for p in found["people"]],
            marking=found.get("marking"),
            why=found.get("why"),
            group=found.get("group"),
            widened_by=who.name(found["widened_by"]) if found.get("widened_by") else None,
        )

    @r.post("/sources/{src_id}/widen")
    def source_widen(src_id: str, body: SourceWiden) -> Applied:
        """The person widens who may see a limited message, or removes the limit, with Undo."""
        from engine.applier import apply_as_person

        need("source", src_id)
        op = {"op": "source.widen", "id": src_id, "people": body.people, "open": body.open}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Widened who may see a message"))
        changed()
        return Applied(changeset=cs_id)

    @r.get("/followups")
    def followups() -> list[FollowupSection]:
        people = People(store, cfg)
        found = sections(store, cfg, date.today())
        view = store.read()
        action_origin = origins(view, "action", [a["id"] for s in found for a in s.actions])
        question_origin = origins(view, "question", [q["id"] for s in found for q in (*s.questions, *s.later)])
        return [_section(s, people, action_origin, question_origin) for s in found]

    @r.post("/followups/{person}/mark-sent")
    def sent(person: str, body: SentText) -> SentCounts:
        need("person", person)
        counts = guard(lambda: mark_sent(store, cfg, person, sent_text=body.text))
        changed()
        return SentCounts(**counts)

    @r.post("/followups/{person}/followed-up")
    def nudge_sent(person: str, body: NudgeSent) -> NudgeRecorded:
        """Record that the follow-up message went to a person: each question and action it listed counts as chased
        today, and the wait for an answer starts again."""
        need("person", person)
        done = guard(
            lambda: mark_followed_up(store, cfg, person, body.question_ids, body.action_ids, sent_text=body.text)
        )
        changed()
        return NudgeRecorded(**done)

    @r.post("/followups/{person}/unfollow")
    def nudge_unsent(person: str, body: NudgeUnsent) -> Ok:
        """Undo a follow-up marked as sent."""
        need("person", person)
        guard(
            lambda: unmark_followed_up(
                store,
                person,
                body.question_ids,
                body.action_ids,
                on=body.on,
                previous_told=body.previous_told,
                signal_at=body.signal_at,
            )
        )
        changed()
        return Ok(ok=person)

    @r.post("/followups/{person}/unmark-sent")
    def unsent(person: str, body: Unmark) -> Ok:
        need("person", person)
        guard(lambda: unmark_sent(store, person, body.question_ids, body.action_ids))
        changed()
        return Ok(ok=person)

    @r.get("/people")
    def people() -> list[PersonView]:
        from engine.record_page import counts

        pm = cfg.workspace.user.person
        orgs = {o.id: o.data["name"] for o in store.read().list("organization")}
        seen = counts(store.read())["people"]
        return [
            PersonView(
                id=p.id,
                name=p.data["full_name"],
                first_name=p.data.get("first_name"),
                role=p.data.get("role"),
                org=p.data.get("org"),
                org_name=orgs.get(p.data.get("org") or ""),
                aliases=p.data.get("aliases", []),
                status=p.data.get("status", "active"),
                is_pm=p.id == pm,
                track_only=bool(p.data.get("track_only")),
                how_to_reach=p.data.get("how_to_reach") or {},
                **seen.get(p.id, {}),
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
                return tx.create("person", {**body.model_dump(), "name_verified": True}, _setup("person.add")).id

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
        if {"full_name", "first_name", "aliases"} & changes.keys():
            changes["name_verified"] = True  # the person wrote the spelling
        guard(lambda: _edit_on_screen(store, cfg, "person", pid, changes))
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
        guard(lambda: _edit_on_screen(store, cfg, "organization", oid, changes))
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
        from engine.lists import describe, status_rank
        from engine.projects import language_for, spent_on
        from engine.record_page import counts
        from engine.scope import role_of

        names = People(store, cfg)
        view = store.read()
        seen = counts(view)["projects"]
        done = cfg.workspace.project.completed_status.strip().casefold()
        meant = {p.id: describe(view, "project-status", p.data.get("status")) for p in view.list("project")}
        return [
            ProjectView(
                parent=p.data.get("parent"),
                language=language_for(view, cfg.workspace.language, p),
                language_own=bool(p.data.get("language")),
                role=role_of(view, p.id, names.pm),
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
                completed=meant[p.id].meaning == "done"
                or (bool(done) and (p.data.get("status") or "").strip().casefold() == done),
                status_tone=meant[p.id].tone,
                status_meaning=meant[p.id].meaning,
                status_rank=status_rank(view, "project-status", p.data.get("status")),
                **seen.get(p.id, {}),
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
        guard(lambda: _edit_on_screen(store, cfg, "project", prj, changes))
        changed()
        return Ok(ok=prj)

    @r.post("/projects/{prj}/role")
    def set_project_role(prj: str, body: ProjectRoleIn) -> Applied:
        """The person's own part in a project, with Undo."""
        from engine.applier import apply_as_person

        need("project", prj)
        person = cfg.workspace.user.person
        if person is None:
            raise HTTPException(status_code=409, detail="Say who you are before setting your part in a project.")
        op = {"op": "project.role", "project": prj, "person": person, "role": body.role}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Set a role on screen"))
        changed()
        return Applied(changeset=cs_id)

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
            # Each change says which kinds of records were written since the last one, so the screen refreshes only
            # what they affect; a change with none (a setting, a source's status) refreshes everything.
            seen = events.version
            position, _ = store.read().changed_kinds(0)
            yield f"event: hello\ndata: {seen}\n\n"
            while not events.closed:
                seen_now = await asyncio.to_thread(events.wait, seen, 15.0)
                if events.closed:
                    break
                if seen_now != seen:
                    seen = seen_now
                    position, kinds = store.read().changed_kinds(position)
                    yield f"event: changed\ndata: {json.dumps({'version': seen, 'kinds': kinds})}\n\n"
                else:
                    yield ": keep-alive\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    return r


def _added_text(before: Any, after: Any) -> str:
    """What an edit added to a text: the part after the old text when the edit kept it, else the whole new text."""
    old = str(before or "").strip()
    new = str(after or "").strip()
    return new[len(old) :].strip() if old and new.startswith(old) else new


def _setup(op: str) -> WriteContext:
    return WriteContext(actor="pm", trust="trusted", op=op)


def _edit_on_screen(store: Store, cfg: Config, kind: str, record_id: str, changes: dict[str, Any]) -> None:
    """The person's edit of a core record on screen, as a `record.edit` op through the applier, so the checks and
    every running plugin's validators on that op see it like any other edit."""
    from engine.applier import apply_as_person

    if not changes:
        return
    current = _existing(store.read(), kind, record_id)
    op = {
        "op": "record.edit",
        "record": {"kind": kind, "id": record_id},
        "fields": changes,
        "read_version": current.version,
    }
    apply_as_person(store, cfg, [op], "Changed on screen")


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


def _cause_view(request: dict[str, Any]) -> StopCauseView | None:
    """A stopped request's cause for the screen: for a data level, the account the tier would use first."""
    cause = request.get("cause")
    if not cause or request.get("state") not in ("needs_you", "failed"):
        return None
    accounts = cause.get("accounts") or []
    return StopCauseView(
        kind=cause["kind"],
        level=cause.get("level"),
        account=accounts[0].partition("/")[0] if accounts else None,
    )


def _title_view(title: Any, people: People) -> ItemTitle | None:
    if title is None:
        return None
    return ItemTitle(
        kind=title.kind,
        person=title.person,
        person_name=people.name(title.person) if title.person else None,
        sender=title.sender,
        topic=title.topic,
    )


def _ask(store: Store, people: People, qid: str | None, cfg: Config | None = None) -> Ask | None:
    q = store.read().get("question", qid) if qid else None
    if q is None:
        return None
    resolves = q.data.get("resolves") or {}
    about = resolves.get("kind") if resolves.get("kind") in ("held-op", "owner") else "other"
    suggestion = None
    if about == "owner" and cfg is not None:
        found = suggest_owner(store.read(), cfg, resolves.get("action", ""))
        suggestion = OwnerSuggestionView(**found.shown(people)) if found is not None else None
    return Ask(
        id=q.id,
        status=q.data["status"],
        about=about,
        name=resolves.get("name"),
        options=[Option(id=pid, name=people.name(pid)) for pid in q.data.get("options", [])],
        suggestion=suggestion,
    )


def _op_view(
    o: dict[str, Any], store: Store, people: People, projects: dict[str, str], cfg: Config | None = None
) -> OpView:
    op = o["op"]
    record = None
    for ref in o.get("records", []):
        rec = store.read().get(ref["kind"], ref["id"], include_deleted=True)
        if rec is not None and ref["kind"] in ("action", "question", "fact", "event", "note", "person", "project"):
            record = (ref["kind"], rec)
            break
    if record is None and op["op"] in ENDING_NAMES:
        # An ending that waits for the person has made nothing yet, so it is about the action it would end.
        rec = store.read().get("action", op.get("id", ""))
        record = ("action", rec) if rec is not None else None
    title = o.get("label") or op.get("text") or op.get("title") or op.get("answer") or op.get("full_name") or ""
    if op["op"] == "answer":
        title = op["text"]  # the whole answer is what the person reads, not its one-line label
    meta: dict[str, Any] = {}
    if record:
        kind, rec = record
        d = rec.data
        title = d.get("text") or d.get("title") or d.get("full_name") or d.get("name") or title
        if kind == "action":
            meta["owners"] = [people.owner(x) for x in d.get("owners", [])]
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
    if op["op"] == "project.add":
        meta["name"] = op["name"]
    if op["op"] == "project.role":
        meta["role"] = op["role"]
    if op["op"] == "person.stance":
        meta["stance"] = op["stance"]
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
        ask=_ask(store, people, o.get("question"), cfg),
    )


def _nudge_view(n: Any) -> NudgeView:
    return NudgeView(
        text=n.text,
        round=n.round,
        question_ids=n.question_ids,
        action_ids=n.action_ids,
        left_out=[LeftOutView(**vars(x)) for x in n.left_out],
    )


def _section(s: Any, people: People, action_origin: dict[str, Any], question_origin: dict[str, Any]) -> FollowupSection:
    def question_views(rows: list[dict[str, Any]]) -> list[FollowupQuestion]:
        return [_followup_question(q, people, question_origin) for q in rows]

    questions = question_views(s.questions)
    later = question_views(s.later)
    actions = [
        FollowupAction(
            id=a["id"],
            text=a["text"],
            due=a["due"],
            project_name=a["project_name"],
            links=a["links"],
            told=a["told"],
            told_days=a["told_days"],
            followed_up=a["followed_up"],
            chases=a["chases"],
            on_hold=a["on_hold"],
            blocker=BlockerView(**a["blocker"]) if a.get("blocker") else None,
            chase_due=a["chase_due"],
            origin=action_origin.get(a["id"]),
        )
        for a in s.actions
    ]
    return FollowupSection(
        person=s.person,
        name=s.name,
        is_pm=s.is_pm,
        questions=questions,
        later=later,
        actions=actions,
        message=s.message,
        to_send=s.to_send,
        nudge=_nudge_view(s.nudge) if s.nudge is not None else None,
    )


def _followup_question(q: dict[str, Any], people: People, question_origin: dict[str, Any]) -> FollowupQuestion:
    resolves = q.get("resolves") or {}
    return FollowupQuestion(
        id=q["id"],
        title=q["title"],
        text=q["text"],
        links=q["links"],
        kind=q["kind"],
        status=q["status"],
        project_name=q["project_name"],
        sent=q["sent"],
        followed_up=q["followed_up"],
        chases=q["chases"],
        waiting_days=q["waiting_days"],
        chase_due=q["chase_due"],
        held_until=q.get("held_until"),
        held_for_name=q.get("held_for_name"),
        about=resolves.get("kind"),
        options=[Option(id=pid, name=people.name(pid)) for pid in q["options"]],
        origin=question_origin.get(q["id"]),
    )
