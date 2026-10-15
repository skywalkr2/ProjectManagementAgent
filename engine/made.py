"""What a change made for the person to open: each draft the assistant wrote and each file a program wrote, read from
the records a change's applied ops touched (design 6.7, 7.3). A change's card links them without opening its details."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

#: Record fields that name a record, in the order they are tried.
_NAME_FIELDS = ("title", "name", "full_name", "text")


@dataclass(frozen=True)
class Made:
    kind: Literal["draft", "file"]
    id: str  # the draft's version, or the file
    label: str  # what it is for: the name of the record the draft is for, or the file's name
    record: tuple[str, str]  # (kind, id) of the record the person opens to see it


def _name_of(record: Any) -> str:
    for key in _NAME_FIELDS:
        value = record.data.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:120]
    return record.id


def made_by(view: Any, outcomes: list[dict[str, Any]]) -> list[Made]:
    """The drafts and files that the applied ops of a change made and that still exist, in the order they were made,
    each once. A draft the person set aside, and anything an op that was held, refused or undone would have made, is
    not listed."""
    found: list[Made] = []
    seen: set[tuple[str, str]] = set()
    for outcome in outcomes:
        if outcome.get("status") != "applied":
            continue
        for ref in outcome.get("records") or []:
            key = (ref["kind"], ref["id"])
            if key in seen:
                continue
            record = view.get(*key)
            if record is None:
                continue
            if (
                ref["kind"] == "text_version"
                and record.data["source"] == "draft"
                and record.data["status"] != "discarded"
            ):
                owner = view.get(record.data["owner_kind"], record.data["owner_id"])
                label = _name_of(owner) if owner is not None else record.data["owner_id"]
                found.append(Made("draft", record.id, label, (record.data["owner_kind"], record.data["owner_id"])))
            elif ref["kind"] == "file":
                found.append(Made("file", record.id, record.data["name"], ("file", record.id)))
            else:
                continue
            seen.add(key)
    return found
