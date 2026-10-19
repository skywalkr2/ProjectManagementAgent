"""What a record's page shows (design 7.14): its name, its details in the order its type declares them with every
reference resolved to a name, what is still open with it, and what happened to it, newest first. Also the counts the
Projects and People tables show beside each row. Reads only."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, get_args, get_origin
from zoneinfo import ZoneInfo

from engine.names import render_owner
from engine.origin import origins
from engine.records import ref_fields, values_at
from engine.texts import long_text_fields

ACTIVITY_MAX = 60
COMPLETED_MAX = 50
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


def page(
    store: Any,
    kind: str,
    record_id: str,
    *,
    pm: str | None,
    owner_format: str = "{full_name}",
    today: date | None = None,
    here: ZoneInfo | None = None,
) -> dict[str, Any] | None:
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

    def owner_of(entry: dict[str, Any]) -> str:
        person = view.get("person", entry["person"], include_deleted=True)
        team = entry.get("team") or (person.data.get("team") if person is not None else None)
        return render_owner(owner_format, name_of("person", entry["person"]), name_of("team", team) if team else None)

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
    action_origin = origins(view, "action", [a.id for a in actions])
    question_origin = origins(view, "question", [q.id for q in questions])

    def meeting(entry: dict[str, Any]) -> dict[str, Any]:
        return _meeting(view, entry, today, here)

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
                "owners": [owner_of(o) for o in a.data.get("owners") or []],
                "project": a.data.get("project"),
                "project_name": name_of("project", a.data["project"]) if a.data.get("project") else None,
                "origin": action_origin[a.id],
                **meeting(a.data),
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
                "origin": question_origin[q.id],
                **meeting(q.data),
            }
            for q in questions
        ],
        "completed_actions": _completed(view, kind, record_id, name_of),
        "fact_source": _fact_source(view, record) if kind == "fact" else None,
        "activity": _activity(view, kind, record_id, actions, questions, name_of, pm),
    }


def _meeting(view: Any, data: dict[str, Any], today: date | None, here: ZoneInfo | None) -> dict[str, Any]:
    """The meeting an item is for: its series and the day of the instance it sits on (the series' next one when it
    names none), for the "for Thursday's print sync" label. Empty for an item on no series."""
    from engine.series import next_instance, span

    series = view.get("series", data["series"]) if data.get("series") else None
    entry = view.get("event", data["event"]) if data.get("event") else None
    if entry is None and series is not None and today is not None and here is not None:
        entry = next_instance(view, series.id, today, here)
    days = span(entry.data, here or ZoneInfo("UTC")) if entry is not None else None
    if series is None and entry is not None and entry.data.get("series"):
        series = view.get("series", entry.data["series"])
    return {
        "series": series.id if series is not None else None,
        "series_title": series.data["title"] if series is not None else None,
        "meeting_on": days[0].isoformat() if days else None,
    }


def _completed(view: Any, kind: str, record_id: str, name_of: Any) -> list[dict[str, Any]]:
    """The finished actions credited to this person (or in this project, or to this organization's people), newest
    first, each with who did the work and who said it was done. The one who only reported it is not credited."""
    if kind not in ("person", "project", "organization"):
        return []
    people = {record_id} if kind == "person" else set()
    if kind == "organization":
        people = {p.id for p in view.list("person") if p.data.get("org") == record_id}
    found = []
    for a in view.list("action"):
        d = a.data
        if d.get("status") != "done":
            continue
        if not ((people & set(d.get("done_by") or [])) or (kind == "project" and d.get("project") == record_id)):
            continue
        closed = [
            row
            for row in view.ledger(kind="action", record_id=a.id)
            if row["field"] == "status" and row["after"] == "done"
        ]
        found.append(
            {
                "id": a.id,
                "text": d["text"],
                "project": d.get("project"),
                "project_name": name_of("project", d["project"]) if d.get("project") else None,
                "done_by": [name_of("person", p) for p in d.get("done_by") or []],
                "reported_by": name_of("person", d["reported_by"]) if d.get("reported_by") else None,
                "done_on": str(closed[-1]["at"])[:10] if closed else None,
            }
        )
    found.sort(key=lambda c: (c["done_on"] or "", c["id"]), reverse=True)
    return found[:COMPLETED_MAX]


def _fact_source(view: Any, record: Any) -> dict[str, Any]:
    """Who a fact rests on and where it came from, for the label in its meta line: the basis (the person, someone
    else, or the assistant's inference), who said it and who reported it, the input and the day. The day is the one the
    person confirmed it when they did, else the day it was true as of, else the day it was filed."""
    from engine.origin import origins

    data = record.data
    source = view.get("source", data["source"]) if data.get("source") else None
    said = view.get("person", data["said_by"], include_deleted=True) if data.get("said_by") else None
    author = (
        view.get("person", source.data["author"], include_deleted=True)
        if source and source.data.get("author")
        else None
    )
    rows = view.ledger(kind="fact", record_id=record.id)
    confirmed = [r for r in rows if r["field"] == "basis" and r["version"] > 1]
    filed = str(rows[0]["at"])[:10] if rows else None
    on = str(confirmed[-1]["at"])[:10] if confirmed else (str(data["as_of"]) if data.get("as_of") else filed)
    reported_by = author.data["full_name"] if author is not None and (said is None or author.id != said.id) else None
    return {
        "basis": data.get("basis"),
        "by": said.data["full_name"] if said is not None else None,
        "reported_by": reported_by if data.get("basis") == "said" else None,
        "input": source.data["title"] if source is not None else None,
        "on": on,
        "origin": origins(view, "fact", [record.id])[record.id],
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
