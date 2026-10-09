"""Input cleaning before any AI call (design 6.6).

Quoted history that matches text already saved is removed; quoted text that doesn't match is kept and marked. A line
that starts a signature ends the message. Paragraphs matching a disclaimer pattern are removed. The result only ever
removes text (and adds markers), so a quote from the cleaned text is still found in the saved original.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from engine.config.schema import CleaningSettings

QUOTED_MARK = "[quoted] "
_WROTE = re.compile(r"^\s*On .{3,200} wrote:\s*$")


@dataclass(frozen=True)
class Cleaned:
    text: str
    removed_quoted_lines: int
    marked_quoted_lines: int
    removed_signature: bool
    removed_paragraphs: int


def normalize(text: str) -> str:
    """Lowercase, straighten quotes and collapse whitespace, for comparing quotes with sources."""
    table = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
    return re.sub(r"\s+", " ", text.translate(table)).strip().lower()


def clean(text: str, settings: CleaningSettings, known_texts: Iterable[str] = ()) -> Cleaned:
    known = [normalize(t) for t in known_texts if t.strip()]
    lines = text.replace("\r\n", "\n").split("\n")

    kept: list[str] = []
    signature = False
    for line in lines:
        if any(line.startswith(marker) for marker in settings.signature_markers):
            signature = True
            break
        kept.append(line)

    out: list[str] = []
    removed_quoted = marked_quoted = 0
    i = 0
    while i < len(kept):
        line = kept[i]
        if line.lstrip().startswith(">") or _WROTE.match(line):
            block: list[str] = []
            while i < len(kept) and (kept[i].lstrip().startswith(">") or _WROTE.match(kept[i]) or not kept[i].strip()):
                block.append(kept[i])
                i += 1
            quoted = [b.lstrip()[1:].lstrip() if b.lstrip().startswith(">") else "" for b in block]
            body = normalize(" ".join(q for q in quoted if q))
            if settings.remove_quoted and body and any(body in k for k in known):
                removed_quoted += len(block)
                continue
            for b in block:
                if b.lstrip().startswith(">"):
                    out.append(QUOTED_MARK + b.lstrip()[1:].lstrip())
                    marked_quoted += 1
                elif b.strip():
                    out.append(b)
            continue
        out.append(line)
        i += 1

    paragraphs = re.split(r"\n\s*\n", "\n".join(out))
    patterns = [re.compile(p) for p in settings.remove_patterns]
    kept_paragraphs = [p for p in paragraphs if not any(pat.match(p.strip()) for pat in patterns)]
    result = "\n\n".join(p.strip("\n") for p in kept_paragraphs if p.strip()).strip()
    return Cleaned(
        text=result,
        removed_quoted_lines=removed_quoted,
        marked_quoted_lines=marked_quoted,
        removed_signature=signature,
        removed_paragraphs=len(paragraphs) - len(kept_paragraphs),
    )
