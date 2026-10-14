"""Where an item came from (design 7.5): the one place that decides what a "where it came from" link opens.

In order of what exists: the original page, when the input the item came from has an address a browser can open; else
the saved text of that input; else the change that created the item, with the request behind it. An item none of those
reach (made by the engine itself, or imported without its history) has no origin, and the screen shows no link.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

LINK, SOURCE, CHANGE = "link", "source", "change"


def _openable(url: object) -> bool:
    """Whether an address is a web page a person can open: a web scheme and a host."""
    if not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


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
        source = view.get("source", record.data["source"]) if record is not None and record.data.get("source") else None
        if source is not None and _openable(source.data.get("url")):
            out[record_id] = {"kind": LINK, "url": source.data["url"].strip(), "source": source.id}
            continue
        if source is not None:
            out[record_id] = {"kind": SOURCE, "source": source.id}
            continue
        if created is None:
            created = view.creations(kind)
        changeset, request = created.get(record_id, (None, None))
        if changeset and view.get("changeset", changeset) is not None:
            out[record_id] = {"kind": CHANGE, "changeset": changeset, "request": request}
        else:
            out[record_id] = None
    return out
