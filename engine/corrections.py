"""Asking for a change to something the assistant made (design 6.8, 6.20, 7.18).

The person types a note on the row of an action, a question, a decision, a calendar entry or a fact. It records one
correction signal naming the item, and the changeset and run that made it when there was one, and queues the usual
notes work about the item, whose packet carries the item as it stands now. What the assistant makes of the note is
reviewed and undone like any other work of its own.
"""

from __future__ import annotations

from typing import Any

from engine.config import Config
from engine.intake import IntakeError, note_as_input
from engine.storage import Store
from engine.workspace import Workspace

#: The kinds of item a change can be asked for, and the record kind each is. A decision is a question to the person.
CHANGEABLE: dict[str, str] = {
    "action": "action",
    "question": "question",
    "decision": "question",
    "event": "event",
    "fact": "fact",
}


def request_change(
    ws: Workspace, store: Store, cfg: Config, kind: str, record_id: str, note: str
) -> tuple[str | None, str]:
    """Record the correction and queue the work for the note. Returns the request made and the signal's id."""
    from engine.dispatcher import signal

    record_kind = CHANGEABLE.get(kind)
    if record_kind is None:
        raise IntakeError(f"A change can't be asked for on a {kind}.")
    if not note.strip():
        raise IntakeError("Say what to change.")
    view = store.read()
    if view.get(record_kind, record_id) is None:
        raise IntakeError(f"There is no {kind} {record_id}.")
    request = note_as_input(ws, store, cfg, item=(record_kind, record_id), text=note, route="change_requested")
    first: dict[str, Any] | None = next(iter(view.ledger(kind=record_kind, record_id=record_id)), None)
    made = first["changeset"] if first is not None else None
    signal_id = signal(store, "change_requested", [record_id], note=" ".join(note.split()), changeset=made)
    return request, signal_id
