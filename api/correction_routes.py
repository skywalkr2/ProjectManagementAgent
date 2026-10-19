"""API routes for correcting what the assistant made (design 6.8, 6.13, 6.20): a question's own menu (reword, ask
someone else, drop, mark as already sent), "Change this" on any row, and merging a value of a list into another.

The corrections of a question are the person's own ops, applied as theirs with Undo (`POST /api/changesets/{id}/undo`);
each records its signal. "Change this" records a signal and hands the person's note to the assistant."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    ActionDropIn,
    ActionReplyIn,
    Applied,
    ChangeIn,
    ChangeRequested,
    DroppedQuestionView,
    FoldIn,
    ListMergeIn,
    MissedIn,
    MissedSent,
    NewPersonDone,
    NewPersonIn,
    NewPersonPrefillView,
    PartOfIn,
    QuestionDropIn,
    QuestionRerouteIn,
    QuestionRewordIn,
    QuestionSentIn,
)
from engine.applier import apply_as_person, fold_unowned
from engine.config import Config
from engine.corrections import CHANGEABLE, missed_one, request_change
from engine.intake import IntakeError
from engine.names import People
from engine.next_steps import (
    NewPersonForm,
    add_new_person,
    file_under,
    new_person_prefill,
    not_a_project,
)
from engine.origin import origins
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_correction_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, IntakeError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    def need(kind: str, record_id: str) -> None:
        if store.read().get(kind, record_id) is None:
            raise HTTPException(status_code=404, detail=f"{kind} {record_id} doesn't exist")

    def person_op(op: dict[str, Any], summary: str) -> Applied:
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], summary))
        events.changed()
        return Applied(changeset=cs_id)

    @r.post("/questions/{qid}/reword")
    def reword(qid: str, body: QuestionRewordIn) -> Applied:
        """Reword a question, with Undo. Records a reworded correction."""
        need("question", qid)
        op = {"op": "question.update", "id": qid, **body.model_dump(exclude_none=True)}
        return person_op(op, "Reworded a question")

    @r.post("/questions/{qid}/reroute")
    def reroute(qid: str, body: QuestionRerouteIn) -> Applied:
        """Ask someone else instead, with Undo. Records a routed correction; a decision stays a decision for the new
        person."""
        need("question", qid)
        return person_op({"op": "question.move", "id": qid, "to": body.to}, "Asked someone else instead")

    @r.post("/questions/{qid}/drop")
    def drop(qid: str, body: QuestionDropIn) -> Applied:
        """Drop a question with a reason, with Undo. It stays on record, listed at GET /api/questions/dropped."""
        need("question", qid)
        return person_op({"op": "question.drop", "id": qid, "reason": body.reason}, "Dropped a question")

    @r.post("/actions/{action_id}/drop")
    def drop_action(action_id: str, body: ActionDropIn) -> Applied:
        """Drop an action that is no longer needed, with a reason and Undo. It is never done or credited, and it leaves
        every list. Records a dropped correction naming the change and run that made it, when there was one."""
        need("action", action_id)
        return person_op({"op": "action.drop", "id": action_id, "reason": body.reason}, "Dropped a to-do")

    @r.post("/actions/{action_id}/reply")
    def review_reply(action_id: str, body: ActionReplyIn) -> Applied:
        """Approve the reply the assistant drafted for an action as it is, or replace it with the person's own words;
        either marks it reviewed, with Undo. Rewording a draft records a draft_edited correction naming the change and
        run that made the action, with the text as the person used it."""
        need("action", action_id)
        op = {"op": "action.reply", "id": action_id, **body.model_dump(exclude_none=True)}
        return person_op(op, "Approved a reply" if body.text is None else "Reworded a reply")

    @r.post("/changesets/{cs_id}/ops/{index}/fold")
    def fold(cs_id: str, index: int, body: FoldIn) -> Applied:
        """Add an action waiting for an owner to the open action it nearly repeats, as one change with Undo. The
        waiting action closes as dropped, its words are kept in the other action's notes, and a declined correction is
        recorded naming the action it went into."""
        need("changeset", cs_id)
        need("action", body.into)
        done = guard(lambda: fold_unowned(store, cfg, cs_id, index, body.into, body.read_version))
        events.changed()
        return Applied(changeset=done)

    @r.get("/questions/{qid}/new-person")
    def new_person_form(qid: str) -> NewPersonPrefillView:
        """What "Add a new person" starts with for a "Who is this?" question: the name as written and what the input
        says about them."""
        need("question", qid)
        found = guard(lambda: new_person_prefill(store, cfg, ws, qid))
        return NewPersonPrefillView(**vars(found))

    @r.post("/questions/{qid}/new-person")
    def new_person(qid: str, body: NewPersonIn) -> NewPersonDone:
        """Answer a "Who is this?" question with a new person, saved as the person's own with Undo. An organization no
        record has is added with them, the held items waiting on the name go ahead, and a routed correction is
        recorded naming the new person. Undo the released items first, then the changes in `undo`."""
        need("question", qid)
        done = guard(lambda: add_new_person(store, cfg, ws, qid, NewPersonForm(**body.model_dump())))
        events.changed()
        return NewPersonDone(
            person=done.person, name=done.name, undo=done.changesets, changeset=done.changeset, released=done.released
        )

    @r.post("/changesets/{cs_id}/ops/{index}/part-of")
    def project_part_of(cs_id: str, index: int, body: PartOfIn) -> Applied:
        """A project the assistant found is part of an existing one: the work of that change goes under it, the words
        are kept as a glossary entry naming it, and the proposal is set aside, as one change with Undo. Records a
        declined correction."""
        need("changeset", cs_id)
        need("project", body.project)
        done = guard(lambda: file_under(store, cfg, cs_id, index, body.project))
        events.changed()
        return Applied(changeset=done)

    @r.post("/changesets/{cs_id}/ops/{index}/not-a-project")
    def project_not_a_project(cs_id: str, index: int) -> Applied:
        """A project the assistant found isn't one: the proposal is set aside and the words are kept as a glossary
        entry saying so, as one change with Undo. Records a declined correction."""
        need("changeset", cs_id)
        done = guard(lambda: not_a_project(store, cfg, cs_id, index))
        events.changed()
        return Applied(changeset=done)

    @r.post("/questions/{qid}/sent")
    def sent(qid: str, body: QuestionSentIn) -> Applied:
        """Record that the person already sent this question themselves, with Undo."""
        need("question", qid)
        op: dict[str, Any] = {"op": "question.mark_sent", "id": qid}
        if body.on is not None:
            op["on"] = body.on.isoformat()
        return person_op(op, "Marked a question as sent")

    @r.get("/questions/dropped")
    def dropped() -> list[DroppedQuestionView]:
        """The questions closed as dropped, newest first, with the reason the person gave."""
        view = store.read()
        people = People(store, cfg)
        found = [q for q in view.list("question") if q.data["status"] == "dropped" and not q.data.get("resolves")]
        when: dict[str, str] = {}
        for entry in view.ledger(kind="question"):
            if entry["field"] == "status" and entry["after"] == "dropped":
                when[entry["record_id"]] = str(entry["at"])
        origin = origins(view, "question", [q.id for q in found])
        rows = [
            DroppedQuestionView(
                id=q.id,
                title=q.data["title"],
                text=q.data.get("text", ""),
                to=q.data["to"],
                to_name=people.name(q.data["to"]),
                reason=q.data.get("dropped_reason"),
                dropped_at=datetime.fromisoformat(when[q.id]) if q.id in when else None,
                projects=q.data.get("projects", []),
                origin=origin.get(q.id),
            )
            for q in found
        ]
        return sorted(rows, key=lambda row: (row.dropped_at is not None, row.dropped_at, row.id), reverse=True)

    @r.post("/items/{kind}/{id}/change")
    def change_this(kind: str, id: str, body: ChangeIn) -> ChangeRequested:
        """ "Change this" on a row the assistant made: an action, question, decision, calendar entry (kind `event`)
        or fact. Records a correction and queues the assistant's work on the note; the packet carries the item as it
        is now."""
        record_kind = CHANGEABLE.get(kind)
        if record_kind is None:
            raise HTTPException(status_code=404, detail=f"A change can't be asked for on a {kind}.")
        need(record_kind, id)
        request, signal_id = guard(lambda: request_change(ws, store, cfg, kind, id, body.note))
        if request is not None:
            worker.poke()
        events.changed()
        return ChangeRequested(ok=id, request=request, signal=signal_id)

    @r.post("/missed")
    def missed(body: MissedIn) -> MissedSent:
        """ "Missed one" (design 6.32): the person says in a plain sentence what the assistant missed. Records a missed
        correction for them and hands the words in as their own note, marked as a miss, so the run adds what was
        missed. The request's own changes have their own Undo."""
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="Say what the assistant missed.")
        request, signal_id = guard(lambda: missed_one(ws, store, cfg, body.text))
        worker.poke()
        events.changed()
        return MissedSent(request=request, signal=signal_id)

    @r.post("/lists/{name:path}/merge")
    def list_merge(name: str, body: ListMergeIn) -> Applied:
        """Merge one value of a list into another: records that hold the first hold the second, and the first leaves
        the list. With Undo."""
        return person_op(
            {"op": "list.merge", "list": name, "value": body.value, "into": body.into}, "Merged values on a list"
        )

    return r
