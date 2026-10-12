"""What a record's page shows (design 7.14): its name, its details in the order its type declares them with every
reference resolved to a name, what is still open with it, and what happened to it, newest first. Also the counts the
Projects and People tables show beside each row. Reads only."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, get_args, get_origin

from engine.records import ref_fields, values_at
from engine.texts import long_text_fields

ACTIVITY_MAX = 60
_NAME_FIELDS = ("full_name", "name", "title", "text")
_HIDDEN = {"id", "stage", "ext", "aliases"}


def display_name(data: dict[str, Any]) -> str:
    """The name a record is shown by: its full name, name, title or text (never its id)."""
    for field in _NAME_FIELDS:
        if data.get(field):
            return str(data[field])
    return ""


def _type_of(annotation: Any) -> str:
    """How a field's value is shown: date, number, bool, enum, list, map or text."""
    args = [a for a in get_args(annotation) if a is not type(None)]
    origin = get_origin(annotation)
    if origin is Literal:
        return "enum"
    if origin in (list, tuple, set):
        return "list"
    if origin is dict:
        return "map"
    if args and origin is not None and origin not in (list, dict):
        inner = [_type_of(a) for a in args]
        return next((t for t in inner if t != "text"), "text")
    if annotation in (date, datetime):
        return "date"
    if annotation is bool:
        return "bool"
    if annotation in (int, float):
        return "number"
    return "text"


def page(store: Any, kind: str, record_id: str, *, pm: str | None) -> dict[str, Any] | None:
    view = store.read()
    record = view.get(kind, record_id)
    model = store.plugins.records.get(kind) if hasattr(store, "plugins") else None
    if record is None or model is None:
        return None
    data = record.data
    names: dict[tuple[str, str], str] = {}

    def name_of(ref_kind: str, ref_id: str) -> str:
        key = (ref_kind, ref_id)
        if key not in names:
            target = view.get(ref_kind, ref_id, include_deleted=True)
            names[key] = display_name(target.data) if target is not None else ""
        return names[key]

    refs = ref_fields(model)
    long_text = set(long_text_fields(model))
    details = []
    for field, info in model.model_fields.items():
        if field in _HIDDEN or field in long_text or field not in data:
            continue
        value = data[field]
        if value in (None, "", [], {}) or field in _NAME_FIELDS[:2]:
            continue
        found = []
        for path, target in refs:
            if path.split(".")[0].removesuffix("[]") == field:
                found += [
                    {"kind": target, "id": v, "name": name_of(target, v)}
                    for v in values_at({field: value}, path)
                    if isinstance(v, str)
                ]
        details.append({"field": field, "value": value, "type": _type_of(info.annotation), "refs": found})

    actions, questions = _open_with(view, kind, record_id)
    return {
        "kind": kind,
        "id": record.id,
        "version": record.version,
        "name": display_name(data),
        "details": details,
        "open_actions": [
            {
                "id": a.id,
                "text": a.data["text"],
                "due": str(a.data["due"]) if a.data.get("due") else None,
                "owners": [name_of("person", o["person"]) for o in a.data.get("owners") or []],
                "project": a.data.get("project"),
                "project_name": name_of("project", a.data["project"]) if a.data.get("project") else None,
            }
            for a in actions
        ],
        "open_questions": [
            {
                "id": q.id,
                "title": q.data["title"],
                "to": q.data.get("to"),
                "to_name": name_of("person", q.data["to"]) if q.data.get("to") else None,
                "status": q.data.get("status"),
                "kind": q.data.get("kind"),
            }
            for q in questions
        ],
        "activity": _activity(view, kind, record_id, actions, questions, name_of, pm),
    }


def _open_with(view: Any, kind: str, record_id: str) -> tuple[list[Any], list[Any]]:
    """Open actions and questions with this person, in this project (or organization's people)."""
    people = {record_id} if kind == "person" else set()
    if kind == "organization":
        people = {p.id for p in view.list("person") if p.data.get("org") == record_id}
    actions, questions = [], []
    for a in view.list("action"):
        d = a.data
        if d.get("status") not in ("open", "held"):
            continue
        owners = {o.get("person") for o in d.get("owners") or []}
        if (people & owners) or (kind == "project" and d.get("project") == record_id):
            actions.append(a)
    for q in view.list("question"):
        d = q.data
        if d.get("status") not in ("open", "sent"):
            continue
        if d.get("to") in people or (kind == "project" and record_id in (d.get("projects") or [])):
            questions.append(q)
    actions.sort(key=lambda a: (a.data.get("due") is None, str(a.data.get("due") or ""), a.data["text"]))
    return actions, questions


def _activity(
    view: Any, kind: str, record_id: str, actions: list[Any], questions: list[Any], name_of: Any, pm: str | None
) -> list[dict[str, Any]]:
    """What happened to the record and to what is open with it: one entry per change, newest first."""
    entries = []
    related = [("action", a.id) for a in actions] + [("question", q.id) for q in questions]
    if kind == "project":
        related += [("note", n.id) for n in view.list("note") if n.data.get("project") == record_id]
    for ref_kind, ref_id in [(kind, record_id), *related]:
        for row in view.ledger(kind=ref_kind, record_id=ref_id):
            entries.append(
                {
                    "at": str(row["at"]),
                    "kind": ref_kind,
                    "id": ref_id,
                    "name": name_of(ref_kind, ref_id),
                    "op": row["op"],
                    "field": row.get("field"),
                    "actor": row["actor"],
                    "by_assistant": row["actor"] not in ("pm",),
                    "seq": row["seq"],
                }
            )
    entries.sort(key=lambda e: e["seq"], reverse=True)
    # One entry per record and change, not per field written in it.
    seen: set[tuple[str, str, str, str]] = set()
    unique = []
    for entry in entries:
        key = (entry["kind"], entry["id"], entry["op"], entry["at"][:16])
        if key in seen:
            continue
        seen.add(key)
        unique.append({k: v for k, v in entry.items() if k != "seq"})
    return unique[:ACTIVITY_MAX]


def counts(view: Any) -> dict[str, dict[str, Any]]:
    """For the tables: per person, open items with them and when they were last contacted; per project, open
    actions, open questions and when it last changed."""
    people: dict[str, dict[str, Any]] = {}
    projects: dict[str, dict[str, Any]] = {}

    def person(pid: str) -> dict[str, Any]:
        return people.setdefault(pid, {"open_items": 0, "last_contact": None})

    def project(pid: str) -> dict[str, Any]:
        return projects.setdefault(pid, {"open_actions": 0, "open_questions": 0, "last_change": None})

    for a in view.list("action"):
        d = a.data
        if d.get("status") not in ("open", "held"):
            continue
        for owner in d.get("owners") or []:
            entry = person(owner["person"])
            entry["open_items"] += 1
            told = (d.get("told") or {}).get(owner["person"])
            if told and (entry["last_contact"] is None or str(told) > entry["last_contact"]):
                entry["last_contact"] = str(told)
        if d.get("project"):
            project(d["project"])["open_actions"] += 1
    for q in view.list("question"):
        d = q.data
        if d.get("status") in ("open", "sent") and d.get("to"):
            person(d["to"])["open_items"] += 1
            for pid in d.get("projects") or []:
                project(pid)["open_questions"] += 1
        if d.get("sent_at") and d.get("to"):
            entry = person(d["to"])
            sent = str(d["sent_at"])[:10]
            if entry["last_contact"] is None or sent > entry["last_contact"]:
                entry["last_contact"] = sent
    for row in view.ledger(kind="project"):
        entry = project(row["record_id"])
        if entry["last_change"] is None or str(row["at"]) > entry["last_change"]:
            entry["last_change"] = str(row["at"])
    return {"people": people, "projects": projects}
