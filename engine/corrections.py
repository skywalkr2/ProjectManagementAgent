"""Asking for a change to something the assistant made (design 6.8, 6.20, 7.18).

The person types a note on the row of an action, a question, a decision, a calendar entry or a fact. It records one
correction signal naming the item, and the changeset and run that made it when there was one, and queues the usual
notes work about the item, whose packet carries the item as it stands now. What the assistant makes of the note is
reviewed and undone like any other work of its own.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from engine.config import Config
from engine.intake import IntakeError, missed_note, note_as_input
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


def missed_one(ws: Workspace, store: Store, cfg: Config, text: str, now: datetime | None = None) -> tuple[str, str]:
    """Record that the person said, in a plain sentence, what the assistant missed (design 6.32): their words go in as
    their own note marked as a miss, so the run adds what they name, and one `missed` signal counts it for the person
    and teaches at once. No record and no run is named, because the sentence is all the person knows. Returns the
    request made and the signal's id."""
    from engine.dispatcher import signal
    from engine.names import People

    words = " ".join(text.split())
    if not words:
        raise IntakeError("Say what the assistant missed.")
    request = missed_note(ws, store, cfg, text=text, now=now)
    signal_id = signal(store, "missed", [], note=words, now=now, person=People(store, cfg).pm)
    return request, signal_id


def answered_assistant(store: Store, cfg: Config, question_id: str, text: str) -> str | None:
    """Record that the person wrote an answer to a question the assistant asked them, so the assistant learns from it at
    once. The signal names the question, and the changeset and run that made it when there was one. A bare
    confirmation, which says nothing to learn from, records nothing. Returns the signal's id."""
    from engine.dispatcher import signal
    from engine.intake import is_bare_confirmation

    words = " ".join(text.split())
    if not words or is_bare_confirmation(words, cfg.language.bare_confirmation_words):
        return None
    first: dict[str, Any] | None = next(iter(store.read().ledger(kind="question", record_id=question_id)), None)
    made = first["changeset"] if first is not None else None
    return signal(store, "answered_assistant", [question_id], note=words, changeset=made)
