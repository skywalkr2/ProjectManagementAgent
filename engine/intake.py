"""Handing something in: the PM's note and any pasted content become a Source and a queued Request.

Pasted content is saved as a file by content hash and marked untrusted. The PM's own note stays on the request and is
trusted.

A note typed on a button of an action or a question (Mark done, They finished it, Followed up, an answer) is an input
too: `note_as_input` saves it as a trusted source with the item as its context and its author, and queues the usual
notes work, unless it is a bare confirmation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from engine.config import Config
from engine.names import People
from engine.storage import Store, WriteContext
from engine.workspace import Workspace

_PM = WriteContext(actor="pm", trust="trusted", op="hand-in")


class IntakeError(Exception):
    pass


@dataclass(frozen=True)
class HandedIn:
    request: str
    source: str | None


def hand_in(
    ws: Workspace,
    store: Store,
    *,
    note: str = "",
    pasted: str = "",
    now: datetime | None = None,
    data_level: str | None = None,
    project: str | None = None,
) -> HandedIn:
    note, pasted = note.strip(), pasted.strip()
    if not note and not pasted:
        raise IntakeError("Nothing to hand in: add a note or paste something.")
    if project is not None and store.read().get("project", project) is None:
        raise IntakeError(f"There is no project {project}.")
    now = now or datetime.now(UTC)
    source_id = None
    with store.transaction() as tx:
        if pasted:
            digest = hashlib.sha256(pasted.encode("utf-8")).hexdigest()
            ws.sources_dir.mkdir(parents=True, exist_ok=True)
            path = ws.sources_dir / f"{digest}.txt"
            if not path.exists():
                path.write_text(pasted, encoding="utf-8")
            title = next((line.strip() for line in pasted.splitlines() if line.strip()), "Pasted content")[:120]
            source_id = tx.create(
                "source",
                {
                    "received_at": now.isoformat(),
                    "kind": "pasted",
                    "title": title,
                    "content_hash": digest,
                    "trust": "untrusted",
                    "sensitivity": data_level or "internal",
                },
                _PM,
            ).id
        request = tx.create(
            "request",
            {
                "task": "notes",
                "note": note or None,
                "source": source_id,
                "origin": "pm",
                "state": "queued",
                "waiting": "With the assistant, starting now",
                "created_at": now.isoformat(),
                **({"sensitivity": data_level} if data_level else {}),
                **({"project": project} if project else {}),
            },
            _PM,
        )
    return HandedIn(request.id, source_id)


def source_text(ws: Workspace, store: Store, source_id: str | None) -> str:
    if source_id is None:
        return ""
    src = store.read().get("source", source_id)
    if src is None:
        return ""
    path = ws.sources_dir / f"{src.data['content_hash']}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


#: The buttons a note can be typed on, each with the words the assistant is told it was typed under.
NOTE_ROUTES = {
    "mark_done": "marked the action done",
    "reopened": "reopened the action",
    "they_finished": "said the person it waits on finished the action",
    "followed_up": "chased the person the action waits on",
    "owner_picked": "picked the owner of the action",
    "notes_edited": "added to the notes of the record",
    "answered": "answered the question",
    "answered_for": "recorded the answer of the person the question was asked of",
}

#: The buttons whose note is content the person reports, not their own words: what someone else did or said, as the
#: person tells it. Such a note is authored by that other person, and nothing it says changes how the product behaves
#: until the person confirms it.
REPORTED_ROUTES = frozenset({"they_finished", "followed_up", "answered_for"})
NOTE_KIND = "note:"


def is_reported_note(source_kind: str | None) -> bool:
    """Whether a source's kind is a note typed on a button that relays someone else's words."""
    kind = source_kind or ""
    return kind.startswith(NOTE_KIND) and kind.removeprefix(NOTE_KIND) in REPORTED_ROUTES


_LINK = re.compile(r"(?i)(?:[a-z][a-z0-9+.-]*://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)+/\S*")


def is_bare_confirmation(text: str, words: int) -> bool:
    """Whether a note says too little to be worth the assistant's time: fewer than `words` words and no link."""
    note = text.strip()
    return len(note.split()) < words and not _LINK.search(note)


def note_as_input(
    ws: Workspace,
    store: Store,
    cfg: Config,
    *,
    item: tuple[str, str],
    text: str,
    route: str,
    author: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Hand in the note typed on a button of `item` (a kind and an id), once the button's own change is saved. A bare
    confirmation is kept with the change and makes no request. Otherwise the note is saved as a trusted source whose
    context is the item and its project, and the usual notes work is queued about the item, under the usual cost rules.
    Returns the request's id, or None for a bare confirmation. Undoing the button's change never takes the note back:
    it is kept, and what the assistant makes of it is reviewed and undone on its own.

    Whose words it is follows the button. Most buttons record the person's own words, authored by the person running
    the app. A button that relays someone else (`REPORTED_ROUTES`) records that other person as `author`, which the
    caller names, and the source counts as reported content."""
    if route not in NOTE_ROUTES:
        raise ValueError(f"unknown route {route}")
    if route in REPORTED_ROUTES and not author:
        raise ValueError(f"a note on {route} names the person it is reported about")
    note = text.strip()
    if not note or is_bare_confirmation(note, cfg.language.bare_confirmation_words):
        return None
    record = store.read().get(*item)
    if record is None:
        raise IntakeError(f"There is no {item[0]} {item[1]}.")
    project = record.data.get("project")
    if not isinstance(project, str) or store.read().get("project", project) is None:
        project = None
    now = now or datetime.now(UTC)
    author = author if route in REPORTED_ROUTES else People(store, cfg).pm
    digest = hashlib.sha256(note.encode("utf-8")).hexdigest()
    ws.sources_dir.mkdir(parents=True, exist_ok=True)
    path = ws.sources_dir / f"{digest}.txt"
    if not path.exists():
        path.write_text(note, encoding="utf-8")
    ctx = WriteContext(actor="pm", trust="trusted", op=f"note.{route}")
    with store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": now.isoformat(),
                "kind": f"note:{route}",
                "title": " ".join(note.split())[:120],
                "content_hash": digest,
                "trust": "trusted",
                "projects": [project] if project else [],
                **({"author": author} if author else {}),
            },
            ctx,
        )
        request = tx.create(
            "request",
            {
                "task": "notes",
                "source": source.id,
                "about": {"kind": item[0], "id": item[1]},
                "origin": "pm",
                "state": "queued",
                "waiting": "With the assistant, starting now",
                "created_at": now.isoformat(),
                **({"project": project} if project else {}),
            },
            ctx,
        )
    return request.id
