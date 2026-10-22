"""Who a reply goes to, read from the saved message it answers: its sender, and for a reply to everyone also the others
on its To and Cc lines, never the person's own addresses. Addresses only: the act turns an address a known person holds
back into that person. Nothing here writes."""

from __future__ import annotations

from email.utils import parseaddr
from typing import Any

from engine.reply_lines import my_addresses, read_message


def of_message(ws: Any, view: Any, cfg: Any, source_id: str, action: str) -> list[dict[str, str]]:
    """The recipients of a `reply` or `reply_all` to a saved message, as the draft takes them; empty when the saved text
    has no readable header lines (the person then names who it goes to)."""
    source = view.get("source", source_id)
    path = ws.sources_dir / f"{source.data['content_hash']}.txt" if source is not None else None
    read = read_message(path.read_text(encoding="utf-8")) if path is not None and path.exists() else None
    if read is None:
        return []
    mine = {a.email.casefold() for a in my_addresses(view, cfg)}
    wanted = [(read.sender, "to")]
    if action == "reply_all":
        wanted += [(entry, "to") for entry in read.to] + [(entry, "cc") for entry in read.cc]
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry, role in wanted:
        address = parseaddr(entry)[1].strip()
        key = address.casefold()
        if address.count("@") != 1 or key in mine or key in seen:
            continue
        seen.add(key)
        found.append({"address": address, "role": role})
    return found
