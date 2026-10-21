"""Titles for items: what a person scans a list by (design 7.14).

A title is "{kind} from {person} · {topic}": the kind of input, who it came from, and a few words on what it is about.
Each part comes from structured fields first (a watched item's kind, author and subject; a pasted message's own header
lines), then from the assistant's short topic for the input. A topic from the assistant with fewer words than
`language.title_min_words` gives way to the first meaningful line of the text (skipping greetings, quoted headers and
sign-offs, `language.title_skip`) only when that line fits whole: a title never ends in a piece of a sentence. With no
whole line, a short topic of at least two words stays; with nothing usable the topic is empty and the screen says it is
missing. Work the app started carries its kind of task and what it is about, which the screen puts into words.
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
    #: For work the app started: its kind of task (an AI task kind id) and what it is about, in the record's own words.
    task: str | None = None
    subject: str = ""


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
    subject: str = "",
) -> Title:
    """The title of one request: `source` is its input's record (if any), `changeset` the assistant's answer (if any),
    `head` the beginning of the input's text, `watched_kind` "email" or "calendar" when the watched item said what
    it was, and `subject` the words of the record work the app started is about. A topic from the assistant with fewer
    than `min_words` words (a bare "Noted.") gives way to the input's first line only when that line is whole."""
    skipping = [re.compile(p, re.IGNORECASE) for p in skip]
    assistant = (changeset or {}).get("topic") or ""

    def topic_from(text: str) -> str:
        return _topic(assistant, text, skipping, min_words)

    if source is None:
        note = request.get("note") or ""
        if request.get("origin") == "pm":
            return Title("note", None, None, topic_from(note))
        return Title("task", None, None, assistant, request.get("task") or None, subject)
    watched = source.get("watched")
    if watched:
        sender = watched.get("author")
        person, shown = _who(sender, people)
        return Title(
            watched_kind or "change", person, shown, _clean_subject(source.get("title") or "") or topic_from(head)
        )
    if source.get("trust") == "trusted":
        return Title("note", None, None, topic_from(head))
    headers = _headers(head)
    if "from" in headers or "subject" in headers:
        person, shown = _who(headers.get("from"), people)
        return Title("email", person, shown, _clean_subject(headers.get("subject", "")) or topic_from(head))
    return Title("pasted", None, None, topic_from(head))


def _topic(assistant: str, text: str, skipping: list[re.Pattern[str]], min_words: int) -> str:
    """The topic of an input: the assistant's when it has enough words; else the input's first meaningful line when that
    fits whole; else the assistant's short topic when it is more than a bare word; else none."""
    words = len(assistant.split())
    if words >= max(min_words, 1):
        return assistant
    return first_line(text, skipping) or (assistant if words >= 2 else "")


def subject_of(view: Any, request: dict[str, Any]) -> str:
    """The words of the record work the app started is about (the record the request names, or the one its stage entry
    belongs to), or nothing when it is about none or the record has no words of its own."""
    about = request.get("about") or {}
    kind, record_id = about.get("kind"), about.get("id")
    if not kind and request.get("stage_start"):
        kind, record_id = request["stage_start"].get("kind"), request["stage_start"].get("record")
    found = view.get(kind, record_id) if kind and record_id else None
    if found is None:
        return ""
    for key in ("title", "name", "full_name", "text"):
        if found.data.get(key):
            return " ".join(str(found.data[key]).split())
    return ""


def source_kind(source: dict[str, Any], *, watched_kind: str | None = None) -> str:
    """What kind of input a source is, in one word: email or calendar (a watched item that said which, else change),
    note (the person's own words), or pasted. A pasted message whose first line is a header line (From or Subject) is an
    email."""
    if source.get("watched"):
        return watched_kind or "change"
    if source.get("trust") == "trusted":
        return "note"
    return "email" if _HEADER.match(source.get("title") or "") else "pasted"


def first_line(text: str, skipping: list[re.Pattern[str]]) -> str:
    """The first meaningful line of `text` when it fits in a title whole (at most `TOPIC_WORDS` words); a longer one is
    never cut, so there is none. Greetings, quoted header lines, sign-offs and blank lines are passed over."""
    for line in text.splitlines()[:_HEAD_LINES]:
        stripped = line.strip()
        if not stripped or any(p.match(stripped) for p in skipping):
            continue
        words = stripped.split()
        return " ".join(words) if len(words) <= TOPIC_WORDS else ""
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
    # An address a person can be reached at says who on its own, whatever title or spelling the name is written with.
    if "@" in sender and (by_address := people.resolve(sender)).status == "ok" and by_address.person:
        return by_address.person, None
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
