"""Read-only documents a plugin composes (a start-here page, a beat sheet, a timeline), turned from a small Markdown
subset into plain blocks the screens draw as their own elements, so no HTML from a plugin ever reaches the page.

The subset: headings (`#` to `###`), paragraphs, bullet and numbered lists (one level), tables (`| a | b |` with a
`|---|` line under the header), rules (`---`), and inline `**strong**`, `*emphasis*`, `` `code` `` and links. A link is
`[text](record:<kind>/<id>)` to a record the plugin may read, or `[text](https://...)` to a page outside, shown with
its real domain. Anything else is plain text: raw HTML stays as the characters it is.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

#: The most a document may hold, in characters, and in blocks.
MAX_CHARS = 200_000
MAX_BLOCKS = 2_000

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d{1,4}[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_INLINE = re.compile(
    r"\[(?P<ltext>[^\]\n]+)\]\((?P<target>[^)\s]+)\)"
    r"|\*\*(?P<strong>[^*\n]+)\*\*"
    r"|`(?P<code>[^`\n]+)`"
    r"|(?<![*\w])\*(?P<em>[^*\n]+)\*(?![*\w])"
)


class DocumentError(ValueError):
    """A document a plugin built can't be shown: the message says why."""


def blocks(markdown: str, can_link: Any = None) -> list[dict[str, Any]]:
    """The document's blocks. `can_link(kind, id)` says whether a record link may be shown as a link (it names a
    record the plugin may read that exists); a link it refuses shows as its text."""
    if not isinstance(markdown, str):
        raise DocumentError("a document is text")
    if len(markdown) > MAX_CHARS:
        raise DocumentError(f"a document holds at most {MAX_CHARS} characters")
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    found: list[dict[str, Any]] = []
    paragraph: list[str] = []
    i = 0

    def flush() -> None:
        if paragraph:
            found.append({"type": "paragraph", "inlines": inlines(" ".join(p.strip() for p in paragraph), can_link)})
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            flush()
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            found.append(
                {"type": "heading", "level": len(heading.group(1)), "inlines": inlines(heading.group(2), can_link)}
            )
            i += 1
            continue
        if _RULE.match(line) and not paragraph:
            found.append({"type": "rule"})
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush()
            header = _cells(line)
            rows = []
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                cells = _cells(lines[i])
                rows.append([inlines(c, can_link) for c in (cells + [""] * len(header))[: len(header)]])
                i += 1
            found.append({"type": "table", "header": [inlines(c, can_link) for c in header], "rows": rows})
            continue
        for pattern, ordered in ((_BULLET, False), (_NUMBERED, True)):
            if pattern.match(line):
                flush()
                items = []
                while i < len(lines) and pattern.match(lines[i]):
                    items.append(inlines(pattern.match(lines[i]).group(1), can_link))
                    i += 1
                found.append({"type": "list", "ordered": ordered, "items": items})
                break
        else:
            paragraph.append(line)
            i += 1
        if len(found) > MAX_BLOCKS:
            raise DocumentError(f"a document holds at most {MAX_BLOCKS} blocks")
    flush()
    return found


def _cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [c.strip() for c in text.split("|")]


def inlines(text: str, can_link: Any = None) -> list[dict[str, Any]]:
    """A line's runs of text: plain, strong, emphasis, code, or a link (to a record or to a page outside)."""
    runs: list[dict[str, Any]] = []
    at = 0
    for match in _INLINE.finditer(text):
        if match.start() > at:
            runs.append({"text": text[at : match.start()]})
        if match.group("ltext") is not None:
            runs.append(_link(match.group("ltext"), match.group("target"), can_link))
        elif match.group("strong") is not None:
            runs.append({"text": match.group("strong"), "strong": True})
        elif match.group("code") is not None:
            runs.append({"text": match.group("code"), "code": True})
        else:
            runs.append({"text": match.group("em"), "em": True})
        at = match.end()
    if at < len(text):
        runs.append({"text": text[at:]})
    return [r for r in runs if r["text"]]


def _link(text: str, target: str, can_link: Any) -> dict[str, Any]:
    if target.startswith("record:"):
        kind, _, record_id = target[len("record:") :].rpartition("/")
        if kind and record_id and (can_link is None or can_link(kind, record_id)):
            return {"text": text, "record": {"kind": kind, "id": record_id}}
        return {"text": text}
    parts = urlsplit(target)
    if parts.scheme in ("http", "https") and parts.hostname:
        return {"text": text, "url": target, "domain": parts.hostname}
    return {"text": text}
