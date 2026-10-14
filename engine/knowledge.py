"""Knowledge as records (design 6.22): lessons, glossary entries, routing entries and style notes.

The four kinds share one shape (`engine.records.KnowledgeRecord`). They change only through the ops here, so every
change is in the ledger with Undo. An entry added from the person's own words is active at once. Any other entry is
added as a proposal: a record that changes nothing until the person keeps it. Keep, Discard and Retire are the person's
own acts, built here as the fields they change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from engine.records import REGISTRY, KnowledgeRecord, Person, kind_label, ref_fields, values_at
from engine.storage import StoreError, WriteContext

#: The record kinds that are knowledge, in the order they are listed.
KINDS: tuple[str, ...] = tuple(kind for kind, model in REGISTRY.items() if issubclass(model, KnowledgeRecord))
#: The kind each add or update op writes.
OP_KIND = {
    "lesson.add": "lesson",
    "lesson.update": "lesson",
    "glossary.add": "glossary_entry",
    "glossary.update": "glossary_entry",
    "routing.add": "routing_entry",
    "style.add": "style_note",
}
#: The fields each add op gives beyond the fields every entry has.
OWN_FIELDS = {
    "lesson": ("guard", "signal"),
    "glossary_entry": ("term", "meaning", "confidence", "project", "id_patterns"),
    "routing_entry": ("topic", "person", "team", "negative", "look_up"),
    "style_note": ("audience", "observation"),
}
#: The states an entry can still be changed in.
EDITABLE = ("proposed", "active")

#: The fields of an entry the applier fills in, as stand-ins while a new entry is checked.
_STAND_IN = {"id": "X-1", "origin": "assistant", "learned_at": "2000-01-01T00:00:00Z", "status": "proposed"}
_PERSON_ID = re.compile(rf"^{re.escape(Person.prefix)}-[0-9]+$")


def kind_of(entry_id: str) -> str | None:
    """The knowledge kind an id belongs to, from its prefix; None for an id that is no entry's."""
    prefix, _, number = entry_id.rpartition("-")
    if not number.isdigit():
        return None
    return next((kind for kind in KINDS if REGISTRY[kind].prefix == prefix), None)


def _words(err: ValidationError) -> str:
    first = err.errors()[0]
    return str(first["msg"]).removeprefix("Value error, ")


def references_problem(view: Any, kind: str, data: dict[str, Any], only: set[str] | None = None) -> str | None:
    """Why the records an entry names can't stand, or None: each must exist. With `only`, just the references in
    those top-level fields are checked (a change leaves the others as they were)."""
    for path, target in ref_fields(REGISTRY[kind]):
        if only is not None and path.split(".")[0].removesuffix("[]") not in only:
            continue
        for value in values_at(data, path):
            if value is not None and view.get(target, value) is None:
                return f"there is no {kind_label(REGISTRY.get(target), target)} {value}"
    audience = data.get("audience")
    if (
        kind == "style_note"
        and (only is None or "audience" in only)
        and isinstance(audience, str)
        and _PERSON_ID.match(audience)
        and view.get("person", audience) is None
    ):
        return f"there is no person {audience}"
    return None


def _entry(view: Any, op: Any) -> tuple[Any, str | None]:
    """The entry an update or retire op names, and why it can't be used (None when it can)."""
    kind = OP_KIND.get(op.op) or kind_of(op.id)
    if kind is None:
        return None, f"{op.id} isn't a lesson, glossary entry, routing entry or style note"
    if kind_of(op.id) != kind:
        return None, f"{op.id} isn't a {kind_label(REGISTRY[kind], kind)}"
    found = view.get(kind, op.id)
    if found is None:
        return None, f"there is no {kind_label(REGISTRY[kind], kind)} {op.id}"
    return found, None


def problem(view: Any, op: Any) -> str | None:
    """Why a knowledge op can't apply as it stands, or None: what it names exists, it leaves the entry valid, and an
    entry only changes while it is proposed or active (only an active one can be retired)."""
    if op.op in ("lesson.add", "glossary.add", "routing.add", "style.add"):
        kind = OP_KIND[op.op]
        data = op.model_dump(mode="json", exclude={"op", "group", "evidence"}, by_alias=True)
        if (why := references_problem(view, kind, data)) is not None:
            return why
        try:
            REGISTRY[kind].model_validate({**_STAND_IN, **data})
        except ValidationError as err:
            return _words(err)
        return None
    found, why = _entry(view, op)
    if why is not None:
        return why
    if op.op == "knowledge.retire":
        return None if found.data["status"] == "active" else f"{op.id} isn't active, so there is nothing to retire"
    if found.data["status"] not in EDITABLE:
        return f"{op.id} is {found.data['status']} and can't be changed"
    changes = op.changes()
    kind = found.kind
    try:
        REGISTRY[kind].model_validate({**found.data, **changes})
    except ValidationError as err:
        return _words(err)
    return references_problem(view, kind, {**found.data, **changes}, only=set(changes))


@dataclass(frozen=True)
class Standing:
    """Who an op comes from, as an entry records it: `person` is true for the person's own words or their own act,
    `pm` is the person who acts then, and `origin`, `trust`, `source` and `request` say what the entry came from."""

    person: bool
    pm: str | None
    origin: str
    trust: str
    source: str | None
    request: str | None
    now: str


def _evidence(tx: Any, op: Any, w: WriteContext, st: Standing) -> dict[str, Any] | None:
    quoted = getattr(op, "evidence", None)
    cited = (w.evidence or {}).get("source") or st.source
    signal = getattr(op, "signal", None)
    changeset = None
    if signal is not None and (corrected := tx.get("signal", signal)) is not None:
        changeset = next((ref for ref in corrected.data.get("refs", []) if tx.get("changeset", ref) is not None), None)
    found = {
        "quote": quoted.quote if quoted is not None else None,
        "source": cited if cited and tx.get("source", cited) is not None else None,
        "request": st.request if st.request and tx.get("request", st.request) is not None else None,
        "signal": signal,
        "changeset": changeset,
    }
    return found if any(found.values()) else None


def apply(tx: Any, op: Any, w: WriteContext, st: Standing) -> list[dict[str, Any]]:
    """Apply a knowledge op. Returns the records touched."""
    if (why := problem(tx, op)) is not None:
        raise StoreError(why)
    if op.op == "knowledge.retire":
        current = tx.get(kind_of(op.id), op.id)
        tx.update(current.kind, op.id, {"status": "retired"}, w, read_version=current.version)
        return [{"kind": current.kind, "id": op.id}]
    if op.op in ("lesson.update", "glossary.update"):
        current = tx.get(OP_KIND[op.op], op.id)
        tx.update(current.kind, op.id, op.changes(), w, read_version=current.version)
        return [{"kind": current.kind, "id": op.id}]
    kind = OP_KIND[op.op]
    kept = st.person and st.pm is not None
    data: dict[str, Any] = {
        "text": op.text,
        "evidence": _evidence(tx, op, w, st),
        "origin": st.origin,
        "trust": st.trust,
        "learned_at": st.now,
        "status": "active" if kept else "proposed",
        "kept_by": st.pm if kept else None,
        "kept_at": st.now if kept else None,
        "applies_to": op.applies_to.model_dump(mode="json", by_alias=True),
        **{name: getattr(op, name) for name in OWN_FIELDS[kind]},
    }
    return [{"kind": kind, "id": tx.create(kind, data, w).id}]


# ---- the person's own acts -------------------------------------------------------------------------------------------


def keep_fields(
    found: Any, person: str, now: str, *, text: str | None = None, applies_to: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The fields that keep a proposed entry: it becomes active, with the person as its author. The person may have
    changed its wording or what it applies to, which is then their own wording. Raises StoreError for an entry that
    isn't proposed."""
    if found.data["status"] != "proposed":
        raise StoreError(f"{found.id} isn't waiting to be kept")
    fields: dict[str, Any] = {"status": "active", "kept_by": person, "kept_at": now}
    if text is not None:
        fields["text"] = text
    if applies_to is not None:
        fields["applies_to"] = applies_to
    return fields


def discard_fields(found: Any, reason: str | None) -> dict[str, Any]:
    """The fields that discard a proposed entry, keeping it with the reason. Raises StoreError for an entry that isn't
    proposed."""
    if found.data["status"] != "proposed":
        raise StoreError(f"{found.id} isn't waiting to be kept")
    return {"status": "discarded", "discard_reason": (reason or "").strip() or None}
