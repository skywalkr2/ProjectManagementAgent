"""One click makes the to-do a plain calendar entry is offered as (design 6.32).

A plain entry whose title starts with a task verb (`engine.entry_rules.task_offer`) is offered as a to-do. Making it is
the person's own change: an `action.add` owned by the person, in the entry's words, on the entry (so it is due on the
entry's day and moves when the entry moves), undone like any change. Nothing is sent and no assistant reads anything."""

from __future__ import annotations

from typing import Any

from engine import entry_rules
from engine.applier import apply_as_person
from engine.storage import StoreError


def offered(store: Any, cfg: Any, entry_id: str) -> str | None:
    """The words of the to-do the entry is offered as, or None when it isn't offered one now: it isn't plain or reads as
    no task, or a to-do already sits on it."""
    view = store.read()
    entry = view.get("event", entry_id)
    if entry is None or any(a.data.get("event") == entry_id for a in view.list("action")):
        return None
    return entry_rules.task_offer(entry.data, cfg)


def make(store: Any, cfg: Any, entry_id: str) -> tuple[str, str]:
    """Make the offered to-do for the person. Returns its id and the change's id, which Undo takes. Raises `StoreError`
    saying why when the entry isn't offered one."""
    words = offered(store, cfg, entry_id)
    if words is None:
        raise StoreError("That calendar entry isn't offered as a to-do.")
    person = cfg.workspace.user.person
    if not person:
        raise StoreError("Say who you are in the settings first.")
    op = {
        "op": "action.add",
        "text": words,
        "owners": [person],
        "event": entry_id,
        "due_at_event": True,
        "evidence": {"quote": words},
    }
    changeset = apply_as_person(store, cfg, [op], f"Added a to-do from the calendar: {words}", note=words)
    outcome = store.read().get("changeset", changeset).data["ops"][0]
    action = next(r["id"] for r in outcome["records"] if r["kind"] == "action")
    return action, changeset
