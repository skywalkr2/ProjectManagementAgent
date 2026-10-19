"""Unfiled work (design 7.14): the notes, actions, questions and facts the assistant filed under no project, gathered
in one list so each can be filed. An item whose project has since been removed counts as unfiled again. Filing is the
person's own edit of the item's project, so it is recorded as a correction like any other edit (`engine/learn.py`).
Reads only; the ops it builds are applied by the caller as the person."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: What each kind's text is called, the field that holds its project, and the statuses that leave it open.
KINDS: dict[str, tuple[str, str, tuple[str, ...] | None]] = {
    "note": ("text", "project", None),
    "action": ("text", "project", ("open", "held")),
    "question": ("title", "projects", ("open", "sent")),
    "fact": ("text", "project", None),
}

#: Who the ledger names as the maker of what the person wrote themselves.
PERSON = "pm"


@dataclass(frozen=True)
class Unfiled:
    kind: str
    id: str
    version: int
    text: str
    created_at: str
    trust: str


def _projects(kind: str, data: dict[str, Any]) -> list[str]:
    field = KINDS[kind][1]
    value = data.get(field)
    return [value] if isinstance(value, str) and value else list(value or []) if isinstance(value, list) else []


def unfiled(view: Any) -> list[Unfiled]:
    """Every open item the assistant filed that names no project that still exists, newest first."""
    live = {p.id for p in view.list("project")}
    replaced = {f.data["supersedes"] for f in view.list("fact") if f.data.get("supersedes")}
    found: list[Unfiled] = []
    for kind, (text_field, _, open_statuses) in KINDS.items():
        made = view.creators(kind)
        for record in view.list(kind):
            data = record.data
            who, at = made.get(record.id, (PERSON, ""))
            if who == PERSON or (open_statuses and data.get("status") not in open_statuses):
                continue
            if kind == "fact" and record.id in replaced:
                continue
            if any(p in live for p in _projects(kind, data)):
                continue
            found.append(
                Unfiled(
                    kind, record.id, record.version, str(data.get(text_field) or ""), at, data.get("trust", "trusted")
                )
            )
    return sorted(found, key=lambda i: (i.created_at, i.id), reverse=True)


def file_ops(view: Any, items: list[tuple[str, str, int | None]], project: str) -> list[dict[str, Any]]:
    """The edits that file these items under the project, one `record.edit` each, with the version the person saw (the
    current one when none is given). An item that isn't there, or isn't a kind that can be filed, is refused by name."""
    ops = []
    live = {p.id for p in view.list("project")}
    for kind, record_id, seen in items:
        if kind not in KINDS:
            raise ValueError(f"a {kind} can't be filed under a project")
        record = view.get(kind, record_id)
        if record is None:
            raise ValueError(f"there is no {kind} {record_id}")
        if any(p in live for p in _projects(kind, record.data)):
            # Filed meanwhile: the whole filing waits, so it is all of it or none of it.
            raise ValueError(f"{kind} {record_id} was filed under a project meanwhile")
        field = KINDS[kind][1]
        value: Any = [project] if field == "projects" else project
        ops.append(
            {
                "op": "record.edit",
                "record": {"kind": kind, "id": record_id},
                "fields": {field: value},
                "read_version": seen or record.version,
            }
        )
    return ops
