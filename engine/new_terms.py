"""The scan for new terms (design 6.22): after an input has been read, a plain function with no AI lists the words in it
that look like the name of a system or an acronym and that the workspace doesn't know, and proposes a glossary entry
for each, marked as not known yet. The entries wait for the person like any proposal from an input.

What looks like a term is set by patterns in the language settings, with a list of everyday abbreviations to leave
alone. A word the glossary, the people, the projects, the organizations or the teams already have is known, and so is
one close to a glossary entry the person recently discarded. At most `dispatch.knowledge.new_terms_per_input` are
proposed for one input, counting what was already proposed from it.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from engine import knowledge, proposals
from engine.config import Config
from engine.names import People
from engine.ops import GlossaryAddOp
from engine.storage import StoreError, WriteContext

UNKNOWN_MEANING = "not known yet"
QUOTE_MAX = 300
_ADDRESSES = re.compile(r"https?://\S+|www\.\S+|\S+@\S+")
_QUOTED = ("[quoted]", ">")
_ID_TAIL = re.compile(r"-\d")
_WORDS = re.compile(r"[^\W_]+")
_STATUSES = ("active", "proposed")


def candidates(text: str, patterns: list[str], ignore: list[str]) -> list[tuple[str, str]]:
    """The terms in a text that match one of the patterns, each once (case ignored) in the order they first appear,
    with the line each was found on. Quoted lines, web and mail addresses, the first part of a record id, and the words
    in `ignore` are left out."""
    skipped = {word.lower() for word in ignore}
    found: list[tuple[int, int, str, str]] = []
    for number, line in enumerate(text.splitlines()):
        if line.lstrip().startswith(_QUOTED):
            continue
        clean = _ADDRESSES.sub(lambda m: " " * len(m.group(0)), line)
        for pattern in patterns:
            for match in re.finditer(pattern, clean):
                word = match.group(0)
                if word.lower() in skipped or _ID_TAIL.match(clean[match.end() :]):
                    continue
                found.append((number, match.start(), word, line.strip()[:QUOTE_MAX]))
    found.sort(key=lambda item: (item[0], item[1]))
    seen: set[str] = set()
    terms: list[tuple[str, str]] = []
    for _, _, word, line in found:
        if word.lower() not in seen:
            seen.add(word.lower())
            terms.append((word, line))
    return terms


def known_names(view: Any) -> set[str]:
    """The names the workspace already has, lowercased: each glossary term that is active or proposed, and each name
    of a person, project, organization or team, whole and word by word."""
    names: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            names.add(" ".join(_WORDS.findall(value.lower())))
            names.update(w.lower() for w in _WORDS.findall(value))

    for entry in view.list("glossary_entry"):
        if entry.data.get("status") in _STATUSES:
            names.add(" ".join(_WORDS.findall(str(entry.data["term"]).lower())))
    for person in view.list("person"):
        for key in ("full_name", "first_name"):
            add(person.data.get(key))
        for alias in person.data.get("aliases") or []:
            add(alias)
    for project in view.list("project"):
        add(project.id)
        add(project.data.get("name"))
        for tag in project.data.get("tags") or []:
            add(tag)
    for kind in ("organization", "team"):
        for record in view.list(kind):
            add(record.data.get("name"))
    return names


def _already_proposed(view: Any, source: str | None) -> int:
    """How many glossary entries were proposed from this input, whoever made them."""
    if source is None:
        return 0
    return sum(1 for e in view.list("glossary_entry") if (e.data.get("evidence") or {}).get("source") == source)


def scan(store: Any, cfg: Config, request_id: str, text: str, now: datetime, *, trust: str = "untrusted") -> list[str]:
    """Propose a glossary entry for each new term in `text`, the input of a request that has been read, and return the
    ids of the entries made. Nothing is made when the limit is 0 or reached, and an entry that merges into one waiting
    is not counted as new."""
    limit = cfg.dispatch.knowledge.new_terms_per_input
    view = store.read()
    request = view.get("request", request_id)
    source = request.data.get("source") if request is not None else None
    room = limit - _already_proposed(view, source)
    if room <= 0:
        return []
    known = known_names(view)
    hold_days, alike = cfg.dispatch.knowledge.discards_hold_days, cfg.dispatch.knowledge.discard_similarity
    chosen: list[tuple[str, str]] = []
    for word, line in candidates(text, cfg.language.new_term_patterns, cfg.language.new_term_ignore):
        data = {"term": word, "applies_to": {}}
        if (
            " ".join(_WORDS.findall(word.lower())) in known
            or proposals.near_discard(view, "glossary_entry", data, now, hold_days, alike) is not None
        ):
            continue
        chosen.append((word, line))
        if len(chosen) == room:
            break
    if not chosen:
        return []
    standing = knowledge.Standing(
        person=False,
        pm=People(store, cfg).pm,
        origin="input",
        trust=trust,
        source=source,
        request=request_id,
        now=store.clock(),
        hold_days=hold_days,
        alike=alike,
    )
    made: list[str] = []
    with store.transaction() as tx:
        for word, line in chosen:
            op = GlossaryAddOp(
                text=f"{word}: {UNKNOWN_MEANING}",
                term=word,
                meaning=UNKNOWN_MEANING,
                confidence="unknown",
                evidence={"quote": line},
            )
            write = WriteContext(
                actor="engine", trust=trust, op="terms.scan", request=request_id, evidence={"source": source}
            )
            tx.sql("SAVEPOINT new_term")
            pending = len(tx.pending)
            try:
                made += [r["id"] for r in knowledge.apply(tx, op, write, standing)]
            except StoreError:
                tx.sql("ROLLBACK TO new_term")
                del tx.pending[pending:]
    return made
