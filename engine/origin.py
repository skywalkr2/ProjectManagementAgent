"""Where an item came from (design 7.5): the one place that decides what a "where it came from" link opens.

In order of what exists: the original page, when the input the item came from has an address a browser can open; else
the saved text of that input; else the change that created the item, with the request behind it. An item is made from
an input by its `source`; a piece of knowledge names it in its evidence. An item none of those
reach (made by the engine itself, or imported without its history) has no origin, and the screen shows no link.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from engine.knowledge import KINDS as KNOWLEDGE_KINDS

LINK, SOURCE, CHANGE = "link", "source", "change"


def _openable(url: object) -> bool:
    """Whether an address is a web page a person can open: a web scheme and a host."""
    if not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _source_id(kind: str, data: dict[str, Any]) -> str | None:
    """The input a record was made from: its own `source`; for a piece of knowledge, the one its evidence cites."""
    if kind in KNOWLEDGE_KINDS:
        return (data.get("evidence") or {}).get("source") or None
    return data.get("source") or None


def source_origin(source: Any) -> dict[str, Any] | None:
    """The origin an input itself gives: its original page when it has an address a browser can open, else its saved
    text; None for no input."""
    if source is None:
        return None
    if _openable(source.data.get("url")):
        return {"kind": LINK, "url": source.data["url"].strip(), "source": source.id}
    return {"kind": SOURCE, "source": source.id}


def origins(view: Any, kind: str, ids: Iterable[str]) -> dict[str, dict[str, Any] | None]:
    """The origin of each record of `kind` named in `ids`, by id: a dict with `kind` (link, source or change) and the
    address, source, change and request it needs, or None. Reads only."""
    wanted = list(ids)
    if not wanted:
        return {}
    created: dict[str, tuple[str | None, str | None]] | None = None
    out: dict[str, dict[str, Any] | None] = {}
    for record_id in wanted:
        record = view.get(kind, record_id, include_deleted=True)
        source_id = _source_id(kind, record.data) if record is not None else None
        source = view.get("source", source_id) if source_id else None
        found = source_origin(source)
        if found is not None:
            out[record_id] = found
            continue
        if created is None:
            created = view.creations(kind)
        changeset, request = created.get(record_id, (None, None))
        if changeset and view.get("changeset", changeset) is not None:
            out[record_id] = {"kind": CHANGE, "changeset": changeset, "request": request}
        else:
            out[record_id] = None
    return out
