"""Searching the workspace's own knowledge (design 6.22): plain, deterministic functions over the store and the saved
texts of past inputs.

A run asks for a search with a request (words, ids, a project, the kinds to look in); the engine answers it with
`search` and puts the rendered results in front of the run again. The same functions back the check that a question or
a report is not about something the workspace already answers (`known_answer`).

Ranking is by overlap with the words and the ids. A word shared by many entries counts for less than a rare one, so no
list of common words is needed. Only active knowledge is searched. A fact that a later fact replaced is included and
marked with what replaced it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from engine import proposals
from engine.ai.router import LEVELS
from engine.cleaning import normalize
from engine.knowledge import KINDS as KNOWLEDGE_KINDS
from engine.storage import Store
from engine.workspace import Workspace

#: The kinds of place a search can look in, in the order results are listed.
KINDS: tuple[str, ...] = ("facts", "inputs", "records", "knowledge")

#: The ops that ask a person or a maintainer for something, and so are checked against what the workspace already
#: knows, with the subject of each. An op that looks something up outside the workspace is added here when it exists.
ASKING_OPS: dict[str, Callable[[Any], str]] = {
    "question.add": lambda op: op.title,
    "report.draft": lambda op: op.title,
}

#: The record kinds the "records" place covers.
RECORD_KINDS: tuple[str, ...] = ("action", "question", "event", "note", "project")

#: Words shorter than this are not matched.
MIN_WORD = 4
#: The most past inputs read for one search, newest first.
MAX_INPUTS = 500
#: The longest passage of a past input shown in a result, in characters.
PASSAGE_CHARS = 400
#: The longest text of any other result shown, in characters.
TEXT_CHARS = 300

_WORD = re.compile(r"[a-z0-9]+")
_ID = re.compile(r"[A-Za-z]+-[0-9]+")


@dataclass(frozen=True)
class Query:
    """What a run asked to find."""

    words: str = ""
    ids: tuple[str, ...] = ()
    project: str | None = None
    kinds: tuple[str, ...] = KINDS


@dataclass(frozen=True)
class Hit:
    """One result: what it is, its text, and how well it matched."""

    kind: str  # the place it was found: facts, inputs, records or knowledge
    record_kind: str
    id: str
    text: str
    score: float
    coverage: float  # the share of the query's weight the text holds, 0 to 1
    matched: int  # how many distinct words of the query it holds
    project: str | None = None
    untrusted: bool = False  # it came from an outside input
    replaced_by: str | None = None  # for a fact a later one replaced, the newest fact that replaced it
    replaced_text: str | None = None
    discarded: str | None = None  # for an input whose proposal the person discarded: what was discarded, and the day


@dataclass
class _Doc:
    kind: str
    record_kind: str
    id: str
    text: str  # what is matched
    shown: str  # what a result shows
    project: str | None
    untrusted: bool
    level: str
    replaced_by: str | None = None
    replaced_text: str | None = None
    discarded: str | None = None
    words: set[str] = field(default_factory=set)


def query_from(value: Any) -> Query | None:
    """A search request from an answer's `search` value: an object with words, ids, a project and kinds, or just the
    words as text. Unknown kinds are dropped and none given means every kind. None when the value is no request."""
    if isinstance(value, str):
        return Query(words=value)
    if not isinstance(value, dict):
        return None
    words = value.get("words", "")
    if isinstance(words, list):
        words = " ".join(str(w) for w in words)
    ids = value.get("ids") or []
    ids = [ids] if isinstance(ids, str) else ids
    kinds = value.get("kinds") or []
    kinds = [kinds] if isinstance(kinds, str) else kinds
    project = value.get("project")
    chosen = tuple(k for k in KINDS if k in [str(x).lower() for x in kinds]) or KINDS
    return Query(
        words=str(words).strip(),
        ids=tuple(str(i).strip() for i in ids if str(i).strip()),
        project=str(project).strip() if project else None,
        kinds=chosen,
    )


def words_of(text: str) -> set[str]:
    return {w for w in _WORD.findall(normalize(text)) if len(w) >= MIN_WORD}


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _allowed(level: str, ceiling: str) -> bool:
    return level not in LEVELS or ceiling not in LEVELS or LEVELS.index(level) <= LEVELS.index(ceiling)


def _kind_level(store: Store, kind: str) -> str:
    return getattr(store.plugins.records.get(kind), "data_level", "internal")


def _source_trust(view: Any, data: dict[str, Any]) -> bool:
    """Whether a record rests on an outside input: it says so, or the source it came from is not the person's own."""
    if data.get("trust") == "untrusted":
        return True
    source = view.get("source", data["source"]) if isinstance(data.get("source"), str) else None
    return source is not None and source.data["trust"] != "trusted"


def _highest(*levels: str) -> str:
    known = [lv for lv in levels if lv in LEVELS]
    return max(known, key=LEVELS.index) if known else "internal"


def _fact_docs(store: Store, view: Any) -> list[_Doc]:
    facts = view.list("fact")
    newer = {f.data["supersedes"]: f for f in facts if f.data.get("supersedes")}
    docs = []
    for fact in facts:
        source = view.get("source", fact.data["source"]) if fact.data.get("source") else None
        level = _highest(_kind_level(store, "fact"), source.data.get("sensitivity", "") if source else "")
        replacement, seen = newer.get(fact.id), {fact.id}
        while replacement is not None and replacement.id in newer and replacement.id not in seen:
            seen.add(replacement.id)
            replacement = newer[replacement.id]
        docs.append(
            _Doc(
                "facts",
                "fact",
                fact.id,
                fact.data["text"],
                _cut(fact.data["text"], TEXT_CHARS),
                fact.data.get("project"),
                _source_trust(view, fact.data),
                level,
                replacement.id if replacement is not None else None,
                _cut(replacement.data["text"], TEXT_CHARS) if replacement is not None else None,
            )
        )
    return docs


def _knowledge_text(kind: str, data: dict[str, Any]) -> str:
    if kind == "rule":
        return f"{data['name']}: {data.get('text', '')}"
    if kind == "glossary_entry":
        return f"{data['term']}: {data['meaning']}"
    if kind == "routing_entry":
        return f"{data['topic']}: {data['text']}"
    if kind == "style_note":
        return f"{data['audience']}: {data['observation']}"
    return f"{data['text']} {data.get('guard') or ''}".strip()


def _knowledge_docs(store: Store, view: Any) -> list[_Doc]:
    docs = []
    for kind in ("rule", *KNOWLEDGE_KINDS):
        for entry in view.list(kind):
            if entry.data.get("status") != "active":
                continue
            text = _knowledge_text(kind, entry.data)
            scope = entry.data.get("applies_to") or {}
            project = scope["projects"][0] if scope.get("scope") == "projects" and scope.get("projects") else None
            docs.append(
                _Doc(
                    "knowledge",
                    kind,
                    entry.id,
                    text,
                    _cut(text, TEXT_CHARS),
                    project,
                    entry.data.get("trust") == "untrusted",
                    _kind_level(store, kind),
                )
            )
    return docs


def _record_text(kind: str, data: dict[str, Any]) -> str:
    if kind == "action":
        return f"{data['text']} {data.get('notes') or ''}".strip()
    if kind == "question":
        return " ".join(part for part in (data["title"], data.get("text"), data.get("answer")) if part)
    if kind == "event":
        return f"{data['title']} {data['start']}"
    if kind == "project":
        return f"{data['name']} {data.get('summary') or ''}".strip()
    return data["text"]


def _record_docs(store: Store, view: Any) -> list[_Doc]:
    docs = []
    for kind in RECORD_KINDS:
        level = _kind_level(store, kind)
        for record in view.list(kind):
            data = record.data
            text = _record_text(kind, data)
            project = record.id if kind == "project" else data.get("project")
            if project is None and data.get("projects"):
                project = data["projects"][0]
            docs.append(
                _Doc(
                    "records", kind, record.id, text, _cut(text, TEXT_CHARS), project, _source_trust(view, data), level
                )
            )
    return docs


def _passages(text: str) -> list[str]:
    parts = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    return [p for p in parts if p]


def _input_docs(ws: Workspace, store: Store, view: Any, exclude: Iterable[str]) -> list[_Doc]:
    skip = set(exclude)
    sources = sorted((s for s in view.list("source") if s.id not in skip), key=lambda s: s.data["received_at"])
    discards = proposals.discarded_inputs(view)
    docs = []
    for source in sources[-MAX_INPUTS:]:
        path = ws.sources_dir / f"{source.data['content_hash']}.txt"
        if not path.exists():
            continue
        level = _highest(source.data.get("sensitivity", "internal"))
        projects = source.data.get("projects") or []
        discarded = None
        if source.id in discards:
            kind, day = discards[source.id]
            discarded = f"{proposals.DISCARDED_WORDS[kind]} proposal discarded on {day.date().isoformat()}"
        for passage in _passages(path.read_text(encoding="utf-8")):
            docs.append(
                _Doc(
                    "inputs",
                    "source",
                    source.id,
                    f"{source.data['title']} {passage}",
                    _cut(passage, PASSAGE_CHARS),
                    projects[0] if projects else None,
                    source.data["trust"] != "trusted",
                    level,
                    discarded=discarded,
                )
            )
    return docs


def _weights(docs: list[_Doc], wanted: set[str]) -> dict[str, float]:
    """How much each wanted word counts: less the more of the entries hold it."""
    held = dict.fromkeys(wanted, 0)
    for doc in docs:
        for word in doc.words & wanted:
            held[word] += 1
    return {word: math.log(1 + (len(docs) + 1) / (count + 1)) for word, count in held.items()}


def _rank(docs: list[_Doc], query: Query, subject: str | None = None) -> list[Hit]:
    """The docs that hold some of the query's words or ids, best first. The subject, when given, replaces the query's
    words (a question's own title)."""
    wanted = words_of(subject if subject is not None else query.words)
    ids = {i.lower() for i in query.ids}
    for doc in docs:
        doc.words = words_of(doc.text)
    weight = _weights(docs, wanted)
    total = sum(weight.values())
    hits = []
    for doc in docs:
        if query.project and doc.project not in (None, query.project):
            continue
        common = doc.words & wanted
        found = sum(weight[w] for w in common)
        lowered = doc.text.lower()
        bonus = 0.0
        if doc.id.lower() in ids:
            bonus += 1000.0
        bonus += sum(
            100.0
            for i in ids
            if i != doc.id.lower() and re.search(rf"(?<![a-z0-9-]){re.escape(i)}(?![a-z0-9])", lowered)
        )
        if not found and not bonus:
            continue
        hits.append(
            Hit(
                doc.kind,
                doc.record_kind,
                doc.id,
                doc.shown,
                found + bonus,
                found / total if total else 0.0,
                len(common),
                doc.project,
                doc.untrusted,
                doc.replaced_by,
                doc.replaced_text,
                doc.discarded,
            )
        )
    order = {kind: n for n, kind in enumerate(KINDS)}
    hits.sort(key=lambda h: (-h.score, order[h.kind], h.id))
    return hits


def _docs(ws: Workspace | None, store: Store, kinds: Iterable[str], level: str, exclude: Iterable[str]) -> list[_Doc]:
    view = store.read()
    docs: list[_Doc] = []
    for kind in kinds:
        if kind == "facts":
            docs += _fact_docs(store, view)
        elif kind == "knowledge":
            docs += _knowledge_docs(store, view)
        elif kind == "records":
            docs += _record_docs(store, view)
        elif kind == "inputs" and ws is not None:
            docs += _input_docs(ws, store, view, exclude)
    return [d for d in docs if _allowed(d.level, level)]


def search(
    ws: Workspace,
    store: Store,
    query: Query,
    *,
    limit: int,
    level: str = "restricted",
    exclude_sources: Iterable[str] = (),
) -> list[Hit]:
    """The best `limit` results for a query. Material above `level` is left out, and so are the inputs named in
    `exclude_sources` (the one the run is reading already)."""
    ranked = _rank(_docs(ws, store, query.kinds, level, exclude_sources), query)
    seen: set[tuple[str, str]] = set()
    results = []
    for hit in ranked:
        # One result per record; a past input counts once, by its best passage.
        if (hit.record_kind, hit.id) in seen:
            continue
        seen.add((hit.record_kind, hit.id))
        results.append(hit)
        if len(results) >= limit:
            break
    return results


def known_answer(
    store: Store, subject: str, *, similarity: float, level: str = "restricted", min_words: int = 2
) -> Hit | None:
    """The fact or active knowledge entry that already answers a subject, if one does: it holds at least `similarity`
    of the subject's weight, in at least `min_words` of its words. A fact that was replaced is not offered; the one that
    replaced it is searched instead."""
    if len(words_of(subject)) < min_words:
        return None
    docs = [d for d in _docs(None, store, ("facts", "knowledge"), level, ()) if d.replaced_by is None]
    for hit in _rank(docs, Query(), subject=subject):
        if hit.matched >= min_words and hit.coverage >= similarity:
            return hit
    return None


def render(hits: list[Hit], query: Query, number: int, left: int) -> str:
    """Results as the request part of the next run: one line per result, outside material marked, and what is left."""
    where = ", ".join(query.kinds)
    what = " ".join(part for part in (f"“{query.words}”" if query.words else "", " ".join(query.ids)) if part)
    lines = [f"# Search results (search {number})", f"You searched for {what or 'nothing in particular'} in {where}."]
    if not hits:
        lines.append("Nothing in the workspace matches.")
    for hit in hits:
        label = f"{hit.id} ({_label(hit)})"
        body = f"{label}: {hit.text}"
        if hit.replaced_by:
            body += f" Replaced by {hit.replaced_by}: {hit.replaced_text}"
        if hit.discarded:
            body += f" ({hit.discarded})"
        lines.append(f'- <untrusted source="{hit.id}">{body}</untrusted>' if hit.untrusted else f"- {body}")
    lines.append(
        f"You may search {left} more time{'s' if left != 1 else ''}, or answer."
        if left
        else "You have searched as often as is allowed for this input. Answer now with the JSON object of ops. Do not "
        "ask to search again."
    )
    return "\n".join(lines)


def _label(hit: Hit) -> str:
    names = {"source": "past input", "glossary_entry": "glossary entry", "routing_entry": "routing entry"}
    label = names.get(hit.record_kind, hit.record_kind.replace("_", " "))
    return f"{label}, project {hit.project}" if hit.project else label
