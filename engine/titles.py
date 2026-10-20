"""Titles for items: what a person scans a list by (design 7.14).

A title is "{kind} from {person} · {topic}": the kind of input, who it came from, and a few words on what it is about.
Each part comes from structured fields first (a watched item's kind, author and subject; a pasted message's own header
lines), then from the assistant's short topic for the input, and only then from the first meaningful line of the text,
skipping greetings, quoted headers and sign-offs (`language.title_skip`). A topic from the assistant with fewer words
than `language.title_min_words` is passed over for the input's own words. The screen puts the parts into words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.names import People

# How far into an input its header lines and first meaningful line are looked for.
_HEAD_CHARS = 4000
_HEAD_LINES = 40
TOPIC_WORDS = 8

_HEADER = re.compile(r"^\s*(from|subject)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_ADDRESS = re.compile(r"\s*<[^>]*>\s*|\s*\([^)]*\)\s*")
_REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*:\s*)+", re.IGNORECASE)


@dataclass(frozen=True)
class Title:
    """`kind`: email, calendar, change (another watched item), note (the person's own words), pasted, or task (work
    the app started, such as a stage's task). `person`: the id of who it came from, when known. `sender`: who it came
    from as written, when that isn't a known person. `topic`: a few words on what it is about; may be empty."""

    kind: str
    person: str | None
    sender: str | None
    topic: str


def title_for(
    request: dict[str, Any],
    source: dict[str, Any] | None,
    changeset: dict[str, Any] | None,
    *,
    people: People,
    skip: list[str],
    head: str = "",
    watched_kind: str | None = None,
    min_words: int = 1,
) -> Title:
    """The title of one request: `source` is its input's record (if any), `changeset` the assistant's answer (if any),
    `head` the beginning of the input's text, and `watched_kind` "email" or "calendar" when the watched item said what
    it was. A topic from the assistant with fewer than `min_words` words (a bare "Noted.") is not used while the input's
    own words can give one."""
    skipping = [re.compile(p, re.IGNORECASE) for p in skip]
    assistant_topic = (changeset or {}).get("topic") or ""
    short = assistant_topic and len(assistant_topic.split()) < min_words
    held = assistant_topic if short else ""
    if short:
        assistant_topic = ""
    if source is None:
        note = request.get("note") or ""
        kind = "note" if request.get("origin") == "pm" else "task"
        return Title(kind, None, None, assistant_topic or first_words(note, skipping) or held)
    watched = source.get("watched")
    if watched:
        sender = watched.get("author")
        person, shown = _who(sender, people)
        topic = _clean_subject(source.get("title") or "") or assistant_topic or first_words(head, skipping) or held
        return Title(watched_kind or "change", person, shown, topic)
    if source.get("trust") == "trusted":
        return Title("note", None, None, assistant_topic or first_words(head, skipping) or held)
    headers = _headers(head)
    if "from" in headers or "subject" in headers:
        person, shown = _who(headers.get("from"), people)
        topic = _clean_subject(headers.get("subject", "")) or assistant_topic or first_words(head, skipping) or held
        return Title("email", person, shown, topic)
    return Title("pasted", None, None, assistant_topic or first_words(head, skipping) or held)


def source_kind(source: dict[str, Any], *, watched_kind: str | None = None) -> str:
    """What kind of input a source is, in one word: email or calendar (a watched item that said which, else change),
    note (the person's own words), or pasted. A pasted message whose first line is a header line (From or Subject) is an
    email."""
    if source.get("watched"):
        return watched_kind or "change"
    if source.get("trust") == "trusted":
        return "note"
    return "email" if _HEADER.match(source.get("title") or "") else "pasted"


def first_words(text: str, skipping: list[re.Pattern[str]]) -> str:
    """The first meaningful line of `text`, cut to a few words at a word boundary: greetings, quoted header lines,
    sign-offs and blank lines are passed over."""
    for line in text.splitlines()[:_HEAD_LINES]:
        stripped = line.strip()
        if not stripped or any(p.match(stripped) for p in skipping):
            continue
        words = stripped.split()
        cut = words[:TOPIC_WORDS]
        shown = " ".join(cut).rstrip(" ,;:-")
        return shown + ("…" if len(words) > TOPIC_WORDS else "")
    return ""


def _headers(head: str) -> dict[str, str]:
    """From and Subject lines at the top of a pasted message, before its first blank line after them."""
    found: dict[str, str] = {}
    for line in head.splitlines()[:_HEAD_LINES]:
        if not line.strip():
            if found:
                break
            continue
        match = _HEADER.match(line)
        if match:
            found.setdefault(match.group(1).lower(), match.group(2))
        elif found:
            continue
        else:
            break
    return found


def _who(sender: str | None, people: People) -> tuple[str | None, str | None]:
    """The person id a sender names when it is one known person, else the sender's name as written (address parts
    removed)."""
    if not sender:
        return None, None
    name = _ADDRESS.sub(" ", sender).strip().strip('"').strip() or sender.strip()
    resolved = people.resolve(name)
    if resolved.status == "ok" and resolved.person:
        return resolved.person, None
    return None, name


def _clean_subject(subject: str) -> str:
    return _REPLY_PREFIX.sub("", " ".join(subject.split())).strip()


@lru_cache(maxsize=2048)
def _head_of(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(_HEAD_CHARS)
    except OSError:
        return ""


def head_of(sources_dir: Path, content_hash: str | None) -> str:
    """The beginning of a saved input's text (inputs never change, so it is kept once read)."""
    if not content_hash:
        return ""
    return _head_of(str(sources_dir / f"{content_hash}.txt"))
