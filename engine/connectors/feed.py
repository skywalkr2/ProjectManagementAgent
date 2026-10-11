"""The feed connector: the entries of an RSS or Atom feed, each an item keyed by its id or link. A feed lists only its
latest entries, so an entry that drops off isn't treated as gone. Documents that declare their own entities are
refused rather than parsed."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field

from engine.connectors import ConnectorContext, ConnectorError, Poll, SourceItem

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t]+")


class FeedSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, description="The feed's address.")
    max_items: int = Field(50, ge=1, le=500, description="The most entries read from it.")


def plain(text: str | None) -> str:
    """Text from an entry's HTML: tags dropped, entities decoded, blank lines collapsed."""
    if not text:
        return ""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = html.unescape(_TAGS.sub("", text))
    lines = [_SPACE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _local(tag: str) -> str:
    """A tag's own name, without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _child(element: ElementTree.Element, *names: str) -> ElementTree.Element | None:
    """The first child whose own name is one of `names`, in that order of preference."""
    for name in names:
        for child in element:
            if _local(child.tag) == name:
                return child
    return None


def _text(element: ElementTree.Element, *names: str) -> str | None:
    found = _child(element, *names)
    return found.text if found is not None else None


def parse(content: bytes, limit: int) -> list[SourceItem]:
    head = content[:4096].decode("utf-8", errors="replace").upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise ConnectorError("no_access", "the feed declares its own entities, which aren't read")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as err:
        raise ConnectorError("outage", f"the feed isn't readable: {err}") from None
    items: list[SourceItem] = []
    if _local(root.tag) == "feed":
        for entry in [e for e in root if _local(e.tag) == "entry"][:limit]:
            link = _child(entry, "link")
            href = link.get("href") if link is not None else None
            key = (_text(entry, "id") or href or "").strip()
            author = _child(entry, "author")
            name = _text(author, "name") if author is not None else None
            if key:
                title = plain(_text(entry, "title")) or key
                body = plain(_text(entry, "content", "summary"))
                items.append(SourceItem(key, title[:200], body, name, _text(entry, "updated", "published"), href))
        return items
    channel = _child(root, "channel")
    if channel is None:
        raise ConnectorError("outage", "that address doesn't hold an RSS or Atom feed")
    for entry in [e for e in channel if _local(e.tag) == "item"][:limit]:
        link = _text(entry, "link")
        key = (_text(entry, "guid") or link or "").strip()
        if key:
            title = plain(_text(entry, "title")) or key
            author = _text(entry, "author", "creator")
            body = plain(_text(entry, "description", "encoded"))
            items.append(SourceItem(key, title[:200], body, author, _text(entry, "pubDate"), link))
    return items


def read_feed(settings: FeedSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    from engine.net import WebClient

    host = urlsplit(settings.url).hostname or ""
    client = context.web or WebClient([host])
    try:
        response = client.get(settings.url, headers={"Accept": "application/rss+xml, application/atom+xml, */*"})
    finally:
        if context.web is None:
            client.close()
    return Poll(parse(response.content, settings.max_items), state, complete=False)
