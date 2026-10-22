"""Capture folders (design 6.32, "What arrives"): a folder the person drops notes, documents and voice notes into.

A source of the core's capture kind is read like any folder, but what lands in it is the person's own: a note or a
document is handed in as their words (a trusted source authored by the person, like a note they type), and a sound
file is a voice note, stored and turned into text by an account that takes speech (`engine/transcribe.py`), whose words
are then read the same way. Nothing in it is triaged, set aside or read as outside content, and everything already in
the folder when the source is added is taken in the first time. A file that changes is handed in again; one that is
gone is only marked gone. Reads and writes only through the usual hand-in functions, so the usual cost rules apply."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from engine import intake, transcribe
from engine.connectors import CAPTURE, SourceItem
from engine.extract.attached import with_files_read
from engine.storage import StoreError, WriteContext

log = logging.getLogger(__name__)

_WATCHER = WriteContext(actor="watcher", trust="untrusted", op="watch.read")
#: How a connector says it listed a file it did not read; such an item is noted, never handed in as words.
NOT_READ = "(not read"


def is_capture(source: Any) -> bool:
    return source.connector == CAPTURE


def _sound(item: SourceItem) -> tuple[list[Any], SourceItem]:
    """The sound files an item carries, and the item without them."""
    sound = [f for f in item.files if f.media_type.startswith("audio/")]
    return sound, replace(item, files=tuple(f for f in item.files if f not in sound))


def compare(ws: Any, store: Any, cfg: Any, source: Any, poll: Any, now: datetime) -> Any:
    """Hand in what is new or changed in a capture folder, as the person's own words or voice notes. Returns the
    watcher's result (the requests handed in, new and changed)."""
    from engine.watch import Result, _keep_text, data_level_of

    result = Result(source.id, "ok")
    seen = {s.data["key"]: s for s in store.read().find("snapshot", {"source": source.id}) if not s.data["gone"]}
    level = data_level_of(cfg, source)
    for polled in poll.items:
        sound, item = _sound(polled)
        item = with_files_read(ws, store, cfg, item, source.label or source.id)
        words = item.text.strip()
        voices = [hashlib.sha256(f.data).hexdigest() for f in sound]
        marker = words if not voices else "\n".join([words, *(f"voice:{v}" for v in voices)]).strip()
        digest = _keep_text(ws, marker or item.title)
        before = seen.get(item.key)
        if before is not None and before.data["content_hash"] == digest:
            continue
        handed: list[str] = []
        try:
            if words and not words.startswith(NOT_READ):
                handed.append(
                    intake.own_words_in(
                        ws,
                        store,
                        cfg,
                        text=words,
                        title=item.title,
                        kind="folder",
                        project=source.project,
                        data_level=level,
                        now=now,
                    ).request
                )
            for file in sound:
                handed.append(
                    transcribe.hand_in(
                        store,
                        cfg,
                        file.data,
                        name=file.name,
                        media_type=file.media_type,
                        project=source.project,
                        data_level=level,
                        origin="input",
                        now=now,
                    )
                )
        except (StoreError, intake.IntakeError) as err:
            # One file that can't be handed in (too large, a kind of file not accepted) is left for the next read; the
            # rest of the folder is still taken in.
            log.warning("Capture folder %s: %s couldn't be handed in: %s", source.id, item.key, err)
            continue
        data = {
            "source": source.id,
            "key": item.key,
            "title": item.title,
            "content_hash": digest,
            "author": None,
            "seen_at": now.isoformat(),
            "closed_by": None,
            "set_aside": None,
        }
        with store.transaction() as tx:
            if before is None:
                tx.create("snapshot", data, _WATCHER)
            else:
                tx.update("snapshot", before.id, data, _WATCHER, read_version=before.version)
        (result.new if before is None else result.changed).extend(handed)
    listed = {p.key for p in poll.items}
    gone = [k for k in seen if k not in listed] if poll.complete else [k for k in poll.removed if k in seen]
    for key in gone:
        with contextlib.suppress(StoreError), store.transaction() as tx:
            tx.update("snapshot", seen[key].id, {"gone": True}, _WATCHER, read_version=seen[key].version)
    return result
