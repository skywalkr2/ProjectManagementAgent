"""What the assistant knows about one project (design 7.18): the sources it reads and the last input from each, the
facts and who each rests on, the glossary terms used there, who answers what, and what is still unknown with the
question asked for it. Reads only: nothing here is worked out by an AI, and nothing is asked or changed."""

from __future__ import annotations

from typing import Any

from engine import areas
from engine.config import Config
from engine.knowledge_section import (
    _active,
    _id_key,
    _in_scope_of_projects,
    _key,
    _scope,
    _uses,
    with_ancestors,
)
from engine.record_page import fact_source

#: The project's own fields that stay blank until someone says them, in the order they are listed as unknown.
UNKNOWN_FIELDS: tuple[str, ...] = ("status", "phase", "target", "owner", "summary")


def _sources(view: Any, cfg: Config, project_id: str) -> list[dict[str, Any]]:
    """The project's inputs grouped by where they came from: a watched source (named as set up, else by its id) or the
    way the input arrived. Each group has how many inputs it gave and the latest, newest group first."""
    labels = {s.id: s.label or s.id for s in cfg.watch.sources}
    groups: dict[str, dict[str, Any]] = {}
    for stored in view.list("source"):
        data = stored.data
        if project_id not in (data.get("projects") or []):
            continue
        watched = data.get("watched") or {}
        key = f"watch:{watched['source']}" if watched.get("source") else f"kind:{data['kind']}"
        group = groups.setdefault(
            key,
            {
                "key": key,
                "label": labels.get(watched["source"], watched["source"]) if watched.get("source") else None,
                "kind": None if watched.get("source") else data["kind"],
                "inputs": 0,
                "last": None,
            },
        )
        group["inputs"] += 1
        received = str(data["received_at"])
        if group["last"] is None or (received, stored.id) > (group["last"]["_at"], group["last"]["id"]):
            group["last"] = {
                "id": stored.id,
                "title": data["title"],
                "received_at": data["received_at"],
                "_at": received,
            }
    for group in groups.values():
        group["last"].pop("_at")
    return sorted(groups.values(), key=lambda g: (str(g["last"]["received_at"]), g["key"]), reverse=True)


def _facts(view: Any, project_id: str, chain: list[str]) -> list[dict[str, Any]]:
    """The project's facts that no newer fact replaces, key facts first, then newest. A fact of a project above it
    is here only when it says it holds for the projects inside."""
    all_facts = view.list("fact")
    replaced = {f.data["supersedes"] for f in all_facts if f.data.get("supersedes")}
    above = set(chain) - {project_id}
    rows = []
    for fact in all_facts:
        project = fact.data.get("project")
        if fact.id in replaced or not (
            project == project_id or (project in above and fact.data.get("reaches_children"))
        ):
            continue
        rows.append(
            {
                "id": fact.id,
                "version": fact.version,
                "text": fact.data["text"],
                "key": bool(fact.data.get("key")),
                "source": fact_source(view, fact),
            }
        )
    rows.sort(key=lambda r: _id_key(r["id"])[1], reverse=True)
    rows.sort(key=lambda r: str(r["source"]["on"] or ""), reverse=True)
    rows.sort(key=lambda r: not r["key"])
    return rows


def _words(view: Any, project_id: str, facts: list[dict[str, Any]]) -> str:
    """What is written about the project, for telling which terms are used there."""
    project = view.get("project", project_id)
    parts = [project.data.get("summary") or "", *(f["text"] for f in facts)]
    for kind, field in (("action", "text"), ("question", "title"), ("question", "text")):
        parts += [
            str(s.data.get(field) or "")
            for s in view.list(kind)
            if project_id in (s.data.get("projects") or [s.data.get("project")])
        ]
    return "\n".join(parts)


def _terms(view: Any, project_id: str, chain: list[str], text: str, *, kinds: tuple[str, ...]) -> list[Any]:
    """The glossary entries that matter here: those for this project or one above it, those for some projects that
    include it, and workspace-wide ones the project's words use. Only entries with a status in `kinds`."""
    found = []
    for entry in view.list("glossary_entry"):
        if entry.data.get("status") not in kinds:
            continue
        scope, own = _scope(entry), entry.data.get("project")
        if own is not None:
            wanted = own in chain
        elif scope.scope == "projects":
            wanted = bool(set(scope.projects) & set(chain))
        else:
            wanted = _in_scope_of_projects(scope, set(chain)) and _uses(entry.data["term"], text)
        if wanted:
            found.append(entry)
    return sorted(found, key=_key)


def _routing(view: Any, chain: list[str]) -> list[dict[str, Any]]:
    names: dict[tuple[str, str], str] = {}

    def named(kind: str, record_id: str) -> str:
        if (kind, record_id) not in names:
            record = view.get(kind, record_id, include_deleted=True)
            field = "full_name" if kind == "person" else "name"
            names[(kind, record_id)] = record.data[field] if record is not None else record_id
        return names[(kind, record_id)]

    rows = []
    for entry in _active(view, "routing_entry"):
        if not _in_scope_of_projects(_scope(entry), set(chain)):
            continue
        data = entry.data
        who = named("person", data["person"]) if data.get("person") else named("team", data["team"])
        rows.append(
            {
                "id": entry.id,
                "topic": data["topic"],
                "who": who,
                "negative": bool(data.get("negative")),
                "look_up": data.get("look_up"),
            }
        )
    return rows


def _question_for(view: Any, project_id: str, term: str) -> dict[str, Any] | None:
    """The oldest open or sent question about this project that uses the term, with who it was asked of."""
    asked = [
        q
        for q in view.list("question")
        if q.data.get("status") in ("open", "sent")
        and project_id in (q.data.get("projects") or [])
        and _uses(term, f"{q.data['title']}\n{q.data.get('text') or ''}")
    ]
    if not asked:
        return None
    q = min(asked, key=_key)
    person = view.get("person", q.data["to"], include_deleted=True)
    return {
        "id": q.id,
        "title": q.data["title"],
        "to": q.data["to"],
        "to_name": person.data["full_name"] if person is not None else q.data["to"],
        "status": q.data["status"],
    }


def _reading(view: Any, cfg: Config, project_id: str) -> dict[str, Any]:
    """Which accounts may read the project's material and whether reading it sends anything away from this computer."""
    found = areas.reading(view, cfg, project_id)
    return {
        "state": found.state,
        "levels": list(found.levels),
        "readers": [{"account": r.account, "name": r.name, "leaves": r.leaves} for r in found.readers],
    }


def knows(view: Any, project_id: str, cfg: Config) -> dict[str, Any] | None:
    """What is known about the project, or None when there is no such project."""
    project = view.get("project", project_id)
    if project is None:
        return None
    chain = with_ancestors(view, [project_id])
    facts = _facts(view, project_id, chain)
    text = _words(view, project_id, facts)
    glossary = _terms(view, project_id, chain, text, kinds=("active",))
    unknown_terms = [
        e
        for e in _terms(view, project_id, chain, text, kinds=("active", "proposed"))
        if e.data.get("confidence") == "unknown"
    ]
    unknown: list[dict[str, Any]] = [
        {"kind": "field", "field": f, "term": None, "entry": None, "question": None}
        for f in UNKNOWN_FIELDS
        if project.data.get(f) in (None, "") and not (f == "target" and project.data.get("area"))
    ]
    unknown += [
        {
            "kind": "term",
            "field": None,
            "term": e.data["term"],
            "entry": e.id,
            "question": _question_for(view, project_id, e.data["term"]),
        }
        for e in unknown_terms
    ]
    return {
        "id": project_id,
        "name": project.data["name"],
        "sources": _sources(view, cfg, project_id),
        "facts": facts,
        "terms": [
            {"id": e.id, "term": e.data["term"], "meaning": e.data["meaning"], "confidence": e.data["confidence"]}
            for e in glossary
        ],
        "routing": _routing(view, chain),
        "unknown": unknown,
        "area": bool(project.data.get("area")),
        "reading": _reading(view, cfg, project_id),
    }
