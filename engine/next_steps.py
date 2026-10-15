"""The obvious next step from what came in, as one click (design 6.7, 6.9).

A name the assistant couldn't place can be answered with a new person, saved as the person's own. A project it found
that the workspace lacks can be added, filed under an existing project, or set aside as not a project; the last two are
kept as glossary entries the person wrote. Each is one change with Undo, and each answer that corrects the assistant
records a signal through the one place signals are written.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from engine import knowledge, learn
from engine.applier import (
    OpOutcome,
    _made_by,
    _same_name,
    apply_as_person,
    contact_kind,
    release,
    undo,
)
from engine.config import Config
from engine.intake import source_text
from engine.names import People, entry_parts, input_entries
from engine.ops import GlossaryAddOp
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import Workspace

PART_OF = "project.part_of"
NOT_A_PROJECT = "project.not_a_project"

#: Ops whose own `project` field names the project the work is filed under, and the records they create with the field
#: that holds it (a question holds a list).
_FILED_OPS = ("note", "fact", "event.add", "action.add", "question.add")
_FILED_FIELDS = {"note": "project", "fact": "project", "event": "project", "action": "project", "question": "projects"}


@dataclass
class NewPersonForm:
    """What the person typed on the "Add a new person" form. Only the full name is required."""

    full_name: str
    first_name: str | None = None
    org: str | None = None
    role: str | None = None
    contact_kind: str | None = None
    contact_value: str | None = None


@dataclass
class NewPersonPrefill:
    """What the form starts with: the name as written and what the input says about the person."""

    full_name: str = ""
    first_name: str = ""
    org: str = ""
    role: str = ""
    contact_kind: str = ""
    contact_value: str = ""
    contact_kinds: list[str] = field(default_factory=list)


@dataclass
class NewPersonDone:
    """What adding a person made: the person, the changes to undo (newest first) and the held ops that went ahead."""

    person: str
    name: str
    changesets: list[str]
    changeset: str | None
    released: list[int]


def _words(text: str | None) -> str:
    return " ".join((text or "").split())


def _routing_question(store: Store, question_id: str) -> tuple[Any, dict[str, Any]]:
    q = store.read().get("question", question_id)
    if q is None:
        raise StoreError(f"there is no question {question_id}")
    resolves = q.data.get("resolves") or {}
    if q.data["status"] != "open" or resolves.get("kind") != "held-op":
        raise StoreError("that question isn't asking who someone is")
    return q, resolves


def new_person_prefill(store: Store, cfg: Config, ws: Workspace, question_id: str) -> NewPersonPrefill:
    """The "Add a new person" form for a "Who is this?" question: the name as written, the organization and role a
    proposed person.add for the same name gives, and an address the input's header lines give for that name."""
    _, resolves = _routing_question(store, question_id)
    name = _words(resolves.get("name"))
    found = NewPersonPrefill(
        full_name=name, first_name=name.split()[0] if name else "", contact_kinds=list(cfg.workspace.contact_kinds)
    )
    cs = store.read().get("changeset", resolves["changeset"])
    if cs is None:
        return found
    for outcome in cs.data["ops"]:
        op = outcome["op"]
        if op.get("op") == "person.add" and _same_name(op.get("full_name"), name):
            found.org, found.role = _words(op.get("org")), _words(op.get("role"))
            break
    text = source_text(ws, store, (store.read().get("request", cs.data["request"]).data or {}).get("source"))
    mail = next((k for k in cfg.workspace.contact_kinds if "mail" in k.casefold()), None)
    if mail is not None:
        for entry in input_entries(store, cs.data["request"], text):
            label, address = entry_parts(entry)
            if address and "@" in address and _same_name(label, name):
                found.contact_kind, found.contact_value = mail, address.strip()
                break
    return found


def add_new_person(
    store: Store,
    cfg: Config,
    ws: Workspace,
    question_id: str,
    form: NewPersonForm,
    *,
    now: datetime | None = None,
) -> NewPersonDone:
    """Answer a "Who is this?" question with a new person saved as the person's own: the person is added (with their
    organization, made in the same change when no record has that name), the contact detail is set, and every held op
    waiting on the name goes ahead with the new person, recording that the person said who it is. Returns what to
    undo. Nothing is kept when the held work can't go ahead."""
    now = now or datetime.now(UTC)
    q, resolves = _routing_question(store, question_id)
    name = _words(form.full_name)
    if not name:
        raise StoreError("Write the person's name.")
    if any(_same_name(p.data["full_name"], name) for p in store.read().list("person")):
        raise StoreError(f"{name} is already on file; choose them from the list.")
    value = _words(form.contact_value)
    kind = None
    if value:
        kind = contact_kind(cfg, form.contact_kind or "")
        if kind is None:
            raise StoreError("Choose what kind of contact detail it is.")
    changesets: list[str] = []
    person_op = {
        "op": "person.add",
        "full_name": name,
        "first_name": _words(form.first_name) or None,
        "role": _words(form.role) or None,
        "org": _words(form.org) or None,
    }
    person_cs = apply_as_person(store, cfg, [_without_none(person_op)], "Added a new person")
    changesets.append(person_cs)
    person_id = _made(store, person_cs, "person")
    try:
        if value and kind:
            contact = {"op": "person.contact", "person": person_id, "kind": kind, "value": value}
            changesets.append(apply_as_person(store, cfg, [contact], "Added a contact detail"))
        held = store.read().get("changeset", resolves["changeset"])
        first = held.data["ops"][resolves["op"]] if held is not None else None
        ahead = (
            [
                o["index"]
                for o in held.data["ops"]
                if o["status"] == "held" and o.get("question") == (first or {}).get("question")
            ]
            if held is not None
            else []
        )
        release(store, cfg, resolves["changeset"], resolves["op"], person=person_id, now=now, ws=ws)
    except StoreError:
        for cs in reversed(changesets):
            undo(store, cs)
        raise
    return NewPersonDone(
        person=person_id,
        name=name,
        changesets=list(reversed(changesets)),
        changeset=resolves["changeset"],
        released=ahead,
    )


def _without_none(op: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in op.items() if v is not None}


def _made(store: Store, changeset_id: str, kind: str) -> str:
    cs = store.read().get("changeset", changeset_id)
    for outcome in cs.data["ops"] if cs is not None else []:
        for record in outcome.get("records", []):
            if record["kind"] == kind:
                return record["id"]
    raise StoreError("the change made nothing")


# ---- a project the assistant found --------------------------------------------------------------------------------


def _held_project(store: Store, changeset_id: str, index: int) -> tuple[Any, dict[str, Any]]:
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    outcome = outcomes[index] if 0 <= index < len(outcomes) else None
    if outcome is None or outcome["op"].get("op") != "project.add" or outcome["status"] != "held":
        raise StoreError("that item isn't a project waiting for you")
    return cs, outcome


def file_under(
    store: Store, cfg: Config, changeset_id: str, index: int, into: str, *, now: datetime | None = None
) -> str:
    """The held project is part of an existing one: the work of the same change that has no project goes under it,
    the words become a glossary entry naming that project (the person's own, active at once), the proposal is set
    aside and a `held_declined` signal says so, as one change with Undo. Returns the new change."""
    return _set_aside(store, cfg, changeset_id, index, into, now or datetime.now(UTC))


def not_a_project(store: Store, cfg: Config, changeset_id: str, index: int, *, now: datetime | None = None) -> str:
    """The held project isn't a project: the proposal is set aside and the words become a glossary entry saying so (the
    person's own, active at once), with a `held_declined` signal, as one change with Undo. Returns the new change."""
    return _set_aside(store, cfg, changeset_id, index, None, now or datetime.now(UTC))


def _set_aside(store: Store, cfg: Config, changeset_id: str, index: int, into: str | None, now: datetime) -> str:
    _, held = _held_project(store, changeset_id, index)
    name = _words(held["op"]["name"])
    words = cfg.language.messages
    pm = People(store, cfg).pm
    op_name = PART_OF if into else NOT_A_PROJECT
    with store.transaction() as tx:
        cs = tx.get("changeset", changeset_id)
        outcomes = copy.deepcopy(cs.data["ops"])
        if outcomes[index]["status"] != "held":
            raise StoreError("that project isn't waiting for you any more")
        target = tx.get("project", into) if into else None
        if into and target is None:
            raise StoreError(f"there is no project {into}")
        meaning = (
            words.part_of_meaning.format(project=target.data["name"])
            if target is not None
            else words.not_a_project_meaning
        )
        reason = (
            words.part_of_reason.format(project=target.data["name"])
            if target is not None
            else words.not_a_project_reason
        )
        summary = "Filed under another project" if into else "Set aside: not a project"
        cs_id = tx.new_id("changeset")
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "pm",
                "state": "done",
                "note": summary,
                "created_at": store.clock(),
                "changeset": cs_id,
            },
            WriteContext("pm", "trusted", "screen.request"),
        )
        w = WriteContext("pm", "trusted", f"{op_name}#0", cs_id, request.id)
        touched: list[dict[str, str]] = []
        if into:
            _file_work(tx, outcomes, held["index"], changeset_id, into, w, touched)
        outcomes[index].update(status="refused", reason=reason, question=None)
        status = "held" if any(o["status"] == "held" for o in outcomes) else "applied"
        tx.update("changeset", changeset_id, {"ops": outcomes, "status": status}, w, read_version=cs.version)
        entry = GlossaryAddOp(
            text=f"{name}: {meaning}",
            term=name,
            meaning=meaning,
            confidence="confirmed",
            project=into,
        )
        standing = knowledge.Standing(
            person=True,
            pm=pm,
            origin="person",
            trust="trusted",
            source=None,
            request=request.id,
            now=store.clock(),
            hold_days=cfg.dispatch.knowledge.discards_hold_days,
            alike=cfg.dispatch.knowledge.discard_similarity,
        )
        touched += knowledge.apply(tx, entry, w, standing)
        learn.record(
            tx,
            cfg,
            {
                "kind": "held_declined",
                "refs": [changeset_id, *([into] if into else [])],
                "changeset": changeset_id,
                "run": cs.data.get("run"),
                "note": f"part of {into}: {name}" if into else f"not a project: {name}",
                "at": now.isoformat(),
            },
            WriteContext(actor="pm", trust="trusted", op="held_declined"),
            now,
        )
        done = OpOutcome(
            0,
            {"op": op_name, "name": name, "from": changeset_id, **({"into": into} if into else {})},
            "applied",
            "op0",
            records=touched,
        )
        tx.create(
            "changeset",
            {
                "request": request.id,
                "summary": summary,
                "ops": [asdict(done)],
                "status": "applied",
                "trust": "trusted",
                "reviewed": True,
                "created_at": store.clock(),
            },
            WriteContext("engine", "trusted", "changeset.record"),
            record_id=cs_id,
        )
    store.plugins.publish("changeset.applied", {"id": cs_id}, follows=cs_id)
    return cs_id


def _file_work(
    tx: Any,
    outcomes: list[dict[str, Any]],
    skip: int,
    changeset_id: str,
    into: str,
    w: WriteContext,
    touched: list[dict[str, str]],
) -> None:
    """Put the work of a change that has no project under one: the records it made and the held ops that will make
    some. Only what the change itself created is moved, never a record it merely touched."""
    for outcome in outcomes:
        if outcome["index"] == skip:
            continue
        if outcome["status"] == "held":
            op = outcome["op"]
            if op.get("op") in _FILED_OPS and not op.get("project"):
                op["project"] = into
            continue
        if outcome["status"] != "applied":
            continue
        for record in outcome.get("records", []):
            field_name = _FILED_FIELDS.get(record["kind"])
            if field_name is None or _made_by(tx, record["kind"], record["id"])[0] != changeset_id:
                continue
            current = tx.get(record["kind"], record["id"])
            if current is None or current.data.get(field_name):
                continue
            value = [into] if field_name == "projects" else into
            tx.update(record["kind"], record["id"], {field_name: value}, w, read_version=current.version)
            if record not in touched:
                touched.append({"kind": record["kind"], "id": record["id"]})
