"""Handing something in: the PM's note and any pasted content become a Source and a queued Request.

Pasted content is saved as a file by content hash and marked untrusted. The PM's own note stays on the request and is
trusted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from engine.storage import Store, WriteContext
from engine.workspace import Workspace

_PM = WriteContext(actor="pm", trust="trusted", op="hand-in")


class IntakeError(Exception):
    pass


@dataclass(frozen=True)
class HandedIn:
    request: str
    source: str | None


def hand_in(ws: Workspace, store: Store, *, note: str = "", pasted: str = "", now: datetime | None = None) -> HandedIn:
    note, pasted = note.strip(), pasted.strip()
    if not note and not pasted:
        raise IntakeError("Nothing to hand in: add a note or paste something.")
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
