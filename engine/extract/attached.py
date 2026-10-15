"""The files a source item carries, read as text and added to the item's own text.

A connector hands files as bytes and never parses them; the core reads each with its readers (a plugin's reader for
the type first), cuts the text at the configured size with a mark, and appends it after the item's text, one block per
file. The item's text is what the assistant reads as outside content, so the files' words are marked like the rest.
A file that can't be read is named in its block with the reason, and is an issue about its reader on Today; a type no
reader takes is named the same way and flagged to the person once, as a question they can drop.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from engine.connectors import SourceItem
from engine.extract import Unsupported, health, read_file
from engine.extract.core import ExtractError
from engine.storage import WriteContext

_FLAGGER = WriteContext(actor="watcher", trust="trusted", op="watch.unsupported_file")
MB = 1024 * 1024


def with_files_read(ws: Any, store: Any, cfg: Any, item: SourceItem, where: str) -> SourceItem:
    """The item with its files' text added after its own and its files taken out (they are read now, once)."""
    if not item.files:
        return item
    limits = cfg.storage.files
    blocks = []
    for file in item.files:
        name = " ".join(file.name.split()) or "unnamed file"
        try:
            read = read_file(
                file.data,
                name,
                file.media_type,
                max_chars=limits.read_max_chars,
                max_bytes=int(limits.read_max_mb * MB),
                plugin=store.plugins.read_with_plugins,
            )
        except Unsupported as err:
            blocks.append(f"Attached file: {name} (not read: {err.reason})")
            if health.flag_unsupported(ws, err.media_type):
                _tell_once(store, cfg, name, where)
        except ExtractError as err:
            blocks.append(f"Attached file: {name} (not read: {err.reason})")
            if err.kind is not None:
                health.note_read(ws, err.kind, err.reason)
        else:
            health.note_read(ws, read.kind, None)
            blocks.append(f"Attached file: {name}\n{read.text}\nEnd of attached file: {name}")
    text = "\n\n".join(part for part in (item.text.strip(), *blocks) if part)
    return replace(item, text=text, files=())


def _tell_once(store: Any, cfg: Any, name: str, where: str) -> None:
    """One question to the person that files like this one can't be read yet. It says nothing is needed from them."""
    person = cfg.workspace.user.person
    if not person or store.read().get("person", person) is None:
        return
    with store.transaction() as tx:
        tx.create(
            "question",
            {
                "to": person,
                "title": f"Files like {name} can't be read yet",
                "text": (
                    f"A file named {name} came in with {where}, and this app can't read that kind of file yet. "
                    "The rest of what came in was read. You won't be asked again about this kind of file."
                ),
                "kind": "question",
                "resolves": {"kind": "unread_file_kind"},
            },
            _FLAGGER,
        )
