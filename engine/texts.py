"""Long text (design 5.0, 6.7): prose fields stored once per version by content hash, divided into units by a text
format, with authorship by passage.

A record type marks a field `Annotated[str | None, LongText("markdown")]`. The field holds the hash of its current
text; every version is a `text_version` record (its number, status, where it came from, its authorship), and the text
itself lives in the workspace's `texts/` folder under its hash. A version is pending (a draft or a proposal waiting for
review), accepted (it became the field's text) or discarded.

Units are what every passage-level feature works in: a format's `units(text)` divides the text into spans that cover it
exactly, in order, each with a kind and whether it is atomic (never split or merged). Authorship is kept per unit, in
three kinds: written by the person, drafted by the assistant, and the person's text changed by the assistant.

Reviewing a pending version compares it with the version it was made from and the current one (three-way when the
text moved on since): each region where it differs is one change the person accepts or rejects, and accepting writes
one new version whose authorship follows the choices.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AUTHORS = ("person", "assistant", "assistant_edit")


@dataclass(frozen=True)
class LongText:
    """Marks a record field as long text in a format: `Annotated[str | None, LongText("markdown")]`. The field holds
    the hash of the current version; change it only through the text ops or `writer.set_text`."""

    format: str = "plain"


@dataclass(frozen=True)
class Unit:
    """One unit of a text: characters `start` to `end` (the end is exclusive and includes the blank lines after it)."""

    start: int
    end: int
    kind: str = "paragraph"
    atomic: bool = False


def long_text_fields(model: Any) -> dict[str, str]:
    """{field: format} for every field of a record model marked LongText."""
    found = {}
    for name, info in getattr(model, "model_fields", {}).items():
        for meta in info.metadata:
            if isinstance(meta, LongText):
                found[name] = meta.format
    return found


# ---- formats ---------------------------------------------------------------------------------------------------------


def plain_units(text: str) -> list[Unit]:
    """Blank-line separated paragraphs."""
    units, pos, start = [], 0, None
    for line in text.splitlines(keepends=True):
        if line.strip():
            start = pos if start is None else start
        elif start is not None:
            units.append(Unit(start, pos))
            start = None
        pos += len(line)
    if start is not None:
        units.append(Unit(start, pos))
    return _cover(text, units)


_FENCE = re.compile(r"^(```|~~~)")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
_FOOTNOTE = re.compile(r"^\[\^[^\]]+\]:")


def markdown_units(text: str) -> list[Unit]:
    """Markdown blocks: a fenced code block is one atomic unit; a list, or a footnote with its indented paragraphs, is
    one unit; anything else is a paragraph (headings are their own unit)."""
    lines = text.splitlines(keepends=True)
    units: list[Unit] = []
    i, pos = 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            pos += len(line)
            i += 1
            continue
        start = pos
        kind, atomic = "paragraph", False
        if _FENCE.match(line):
            fence = _FENCE.match(line).group(1)
            kind, atomic = "code", True
            pos += len(line)
            i += 1
            while i < len(lines) and not lines[i].startswith(fence):
                pos += len(lines[i])
                i += 1
            if i < len(lines):
                pos += len(lines[i])
                i += 1
        elif line.startswith("#"):
            kind = "heading"
            pos += len(line)
            i += 1
        else:
            if _LIST.match(line):
                kind = "list"
            elif _FOOTNOTE.match(line):
                kind = "footnote"
            while i < len(lines) and lines[i].strip():
                pos += len(lines[i])
                i += 1
            if kind in ("list", "footnote"):
                # Blank lines inside a list or a footnote continue it while the next line is indented or another item.
                while i < len(lines):
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    nxt = lines[j] if j < len(lines) else ""
                    if not nxt or not (nxt.startswith(("  ", "\t")) or (kind == "list" and _LIST.match(nxt))):
                        break
                    while i < j:
                        pos += len(lines[i])
                        i += 1
                    while i < len(lines) and lines[i].strip():
                        pos += len(lines[i])
                        i += 1
        units.append(Unit(start, pos, kind, atomic))
    return _cover(text, units)


def _cover(text: str, units: list[Unit]) -> list[Unit]:
    """Stretch units so they cover the text exactly: leading blank space joins the first unit, and the blank space
    after each unit up to the next joins it."""
    if not units:
        return [Unit(0, len(text), "paragraph")] if text else []
    out = []
    for index, unit in enumerate(units):
        start = 0 if index == 0 else unit.start
        end = units[index + 1].start if index + 1 < len(units) else len(text)
        out.append(Unit(start, end, unit.kind, unit.atomic))
    return out


CORE_FORMATS: dict[str, Callable[[str], list[Unit]]] = {"plain": plain_units, "markdown": markdown_units}


def check_units(text: str, units: list[Unit]) -> None:
    """A format's units must cover the text exactly, in order, with nothing overlapping or empty."""
    pos = 0
    for unit in units:
        if not isinstance(unit, Unit) or unit.start != pos or unit.end <= unit.start:
            raise ValueError("a text format's units must cover the text exactly, in order")
        pos = unit.end
    if pos != len(text):
        raise ValueError("a text format's units must cover the text exactly, in order")


def units_of(store: Any, fmt: str, text: str) -> list[Unit]:
    """The units of a text in a format, core or a running plugin's; checked to cover the text exactly."""
    split = store.plugins.text_formats().get(fmt)
    if split is None:
        raise ValueError(f"there is no text format called {fmt}")
    units = list(split(text))
    check_units(text, units)
    return units


# ---- the text store --------------------------------------------------------------------------------------------------


def texts_dir(store: Any) -> Path:
    return store.path.parent / "texts"


def text_path(store: Any, sha256: str) -> Path:
    return texts_dir(store) / sha256[:2] / f"{sha256}.txt"


def store_text(store: Any, text: str) -> str:
    """Keep a text under its hash (once, however often it is stored). Returns the hash."""
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    path = text_path(store, digest)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return digest


def read_text(store: Any, sha256: str) -> str:
    """A stored text, checked against the hash it was stored under."""
    data = text_path(store, sha256).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("a stored text doesn't match its hash")
    return data.decode("utf-8")


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


# ---- authorship and changes ------------------------------------------------------------------------------------------


def _texts(text: str, units: list[Unit]) -> list[str]:
    """Each unit's text with its surrounding blank space removed, for aligning units of two texts."""
    return [text[u.start : u.end].strip() for u in units]


def unit_authors(spans: list[dict[str, Any]], units: list[Unit]) -> list[dict[str, Any]]:
    """The author of each unit ({kind, run}), from authorship spans over the same text; unknown is the person."""
    out = []
    for unit in units:
        hit = next((s for s in spans if s["start"] <= unit.start < s["end"]), None)
        out.append({"kind": hit["kind"], "run": hit.get("run")} if hit else {"kind": "person", "run": None})
    return out


def spans_for(units: list[Unit], authors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Authorship spans from per-unit authors, joining neighbours with the same author."""
    spans: list[dict[str, Any]] = []
    for unit, author in zip(units, authors, strict=True):
        if spans and spans[-1]["kind"] == author["kind"] and spans[-1].get("run") == author.get("run"):
            spans[-1]["end"] = unit.end
        else:
            spans.append({"start": unit.start, "end": unit.end, "kind": author["kind"], "run": author.get("run")})
    return spans


def derive_authors(
    base: str,
    base_units: list[Unit],
    base_authors: list[dict[str, Any]],
    new: str,
    new_units: list[Unit],
    by: str,
    run: str | None = None,
) -> list[dict[str, Any]]:
    """Authors of a new text's units made from a base: unchanged units keep theirs; changed units are the person's
    when `by` is "person", and for the assistant, "assistant_edit" where they replace the person's own text and
    "assistant" otherwise."""
    authors: list[dict[str, Any]] = [{"kind": "person", "run": None} for _ in new_units]
    matcher = difflib.SequenceMatcher(None, _texts(base, base_units), _texts(new, new_units), autojunk=False)
    for tag, b1, b2, n1, n2 in matcher.get_opcodes():
        for offset, n in enumerate(range(n1, n2)):
            if tag == "equal":
                authors[n] = base_authors[b1 + offset]
            elif by == "person":
                authors[n] = {"kind": "person", "run": None}
            else:
                replaced = base_authors[b1:b2]
                edits_person = tag == "replace" and any(a["kind"] == "person" for a in replaced)
                authors[n] = {"kind": "assistant_edit" if edits_person else "assistant", "run": run}
    return authors


@dataclass(frozen=True)
class Region:
    """A stretch of the base text where the pending text, the current text, or both differ from it: base units
    [b1, b2) correspond to current units [c1, c2) and pending units [p1, p2). `side` is "pending" (only the proposal
    changed it: the person accepts or rejects it), "current" (only the current text changed it since the base: kept)
    or "both" (a conflict: accepting takes the proposal's version of the stretch, rejecting keeps the current one)."""

    id: str
    side: str
    b1: int
    b2: int
    c1: int
    c2: int
    p1: int
    p2: int


def _opcodes(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


def _start(codes: list[tuple[str, int, int, int, int]], r: int, size: int) -> int:
    """The other text's unit index where a region starting at base unit `r` starts."""
    for _, i1, i2, j1, _j2 in codes:
        if i1 == r:
            return j1
        if i1 < r < i2:
            return j1 + (r - i1)
    return size


def _end(codes: list[tuple[str, int, int, int, int]], r: int) -> int:
    """The other text's unit index where a region ending at base unit `r` ends (after any insertion there)."""
    found = 0
    for _, i1, i2, j1, j2 in codes:
        if i2 == r:
            found = j2
        elif i1 < r < i2:
            return j1 + (r - i1)
    return found


def regions(
    base: str, base_units: list[Unit], current: str, current_units: list[Unit], pending: str, pending_units: list[Unit]
) -> list[Region]:
    """Where a pending text and the current text differ from their common base. Changes on the two sides whose base
    stretches overlap or touch form one region. With the current text still at the base, every region is the pending
    side's."""
    b = _texts(base, base_units)
    p_codes = _opcodes(b, _texts(pending, pending_units))
    c_codes = _opcodes(b, _texts(current, current_units))
    changes_ = sorted(
        [(i1, i2, "pending") for tag, i1, i2, _, _ in p_codes if tag != "equal"]
        + [(i1, i2, "current") for tag, i1, i2, _, _ in c_codes if tag != "equal"]
    )
    grouped: list[list[Any]] = []
    for i1, i2, side in changes_:
        if grouped and i1 <= grouped[-1][1]:
            grouped[-1][1] = max(grouped[-1][1], i2)
            grouped[-1][2].add(side)
        else:
            grouped.append([i1, i2, {side}])
    found, number = [], 0
    for r1, r2, sides in grouped:
        side = "both" if len(sides) == 2 else next(iter(sides))
        if side != "current":
            number += 1
        found.append(
            Region(
                f"c{number}" if side != "current" else "",
                side,
                r1,
                r2,
                _start(c_codes, r1, len(current_units)),
                _end(c_codes, r2) if r2 or c_codes else 0,
                _start(p_codes, r1, len(pending_units)),
                _end(p_codes, r2) if r2 or p_codes else 0,
            )
        )
    return found


def merge(
    base: str,
    base_units: list[Unit],
    current: str,
    current_units: list[Unit],
    current_authors: list[dict[str, Any]],
    pending: str,
    pending_units: list[Unit],
    pending_authors: list[dict[str, Any]],
    choices: dict[str, str],
) -> tuple[str, list[dict[str, Any]], bool]:
    """The text that results from the person's choices on a pending text (unlisted regions are accepted), its per-unit
    authors, and whether anything of the pending text was taken. The current text's own changes since the base are
    always kept; in a conflict, accepting takes the pending side."""
    found = regions(base, base_units, current, current_units, pending, pending_units)
    pieces: list[tuple[str, dict[str, Any]]] = []
    took = False
    c = 0
    for region in found:
        pieces += [
            (current[u.start : u.end], a)
            for u, a in zip(current_units[c : region.c1], current_authors[c : region.c1], strict=True)
        ]
        take = region.side != "current" and choices.get(region.id, "accept") == "accept"
        if take:
            took = True
            chosen = zip(pending_units[region.p1 : region.p2], pending_authors[region.p1 : region.p2], strict=True)
            pieces += [(pending[u.start : u.end], a) for u, a in chosen]
        else:
            kept = zip(current_units[region.c1 : region.c2], current_authors[region.c1 : region.c2], strict=True)
            pieces += [(current[u.start : u.end], a) for u, a in kept]
        c = region.c2
    pieces += [(current[u.start : u.end], a) for u, a in zip(current_units[c:], current_authors[c:], strict=True)]
    every = all(r.side != "current" and choices.get(r.id, "accept") == "accept" for r in found)
    if found and every and base == current:
        return pending, list(pending_authors), True
    parts = [_with_break(text, last=index == len(pieces) - 1) for index, (text, _) in enumerate(pieces)]
    return "".join(parts), [a for _, a in pieces], took


def _with_break(piece: str, *, last: bool) -> str:
    """A unit taken from either text ends with a blank line before the next, whatever it had at its end."""
    return piece if last else piece.rstrip("\n") + "\n\n"


def authorship_summary(text: str, spans: list[dict[str, Any]]) -> dict[str, int]:
    """Words per kind of author."""
    counts = dict.fromkeys(AUTHORS, 0)
    for span in spans:
        counts[span["kind"]] = counts.get(span["kind"], 0) + words(text[span["start"] : span["end"]])
    return counts


# ---- versions --------------------------------------------------------------------------------------------------------


def versions(view: Any, kind: str, record_id: str, field: str, *, include_deleted: bool = False) -> list[Any]:
    """Every version of a long text field, oldest first."""
    rows = view.list("text_version", include_deleted=include_deleted) if include_deleted else view.list("text_version")
    mine = [v for v in rows if (v.data["owner_kind"], v.data["owner_id"], v.data["field"]) == (kind, record_id, field)]
    return sorted(mine, key=lambda v: v.data["number"])


def current(view: Any, kind: str, record_id: str, field: str) -> Any | None:
    """The field's current version: its latest accepted one."""
    accepted = [v for v in versions(view, kind, record_id, field) if v.data["status"] == "accepted"]
    return accepted[-1] if accepted else None


def new_version(
    store: Any,
    tx: Any,
    context: Any,
    kind: str,
    record_id: str,
    field: str,
    text: str,
    *,
    source: str,
    by: str,
    run: str | None = None,
    base: int | None = None,
    note: str | None = None,
    accept: bool = False,
    authors: list[dict[str, Any]] | None = None,
    paragraph_map: list[dict[str, Any]] | None = None,
) -> Any:
    """Write a version of a long text field: stored by hash, with authorship derived from its base (unchanged units
    keep theirs). An accepted version becomes the field's text; anything else waits for review."""
    from engine.storage import StoreError

    owner = tx.get(kind, record_id)
    if owner is None:
        raise StoreError(f"there is no {kind} {record_id}")
    model = store.plugins.records.get(kind)
    fmt = long_text_fields(model).get(field) if model is not None else None
    if fmt is None:
        raise StoreError(f"{kind}.{field} isn't a long text field")
    every = versions(tx, kind, record_id, field, include_deleted=True)
    live = {v.data["number"]: v for v in every if not v.deleted}
    now = current(tx, kind, record_id, field)
    base = base if base is not None else (now.data["number"] if now else None)
    if base is not None and base not in live:
        raise StoreError(f"{kind}.{field} has no version {base}")
    units = units_of(store, fmt, text)
    if authors is None and paragraph_map and base is not None and len(paragraph_map) == len(units):
        base_version = live[base]
        base_text = read_text(store, base_version.data["sha256"])
        base_units = units_of(store, fmt, base_text)
        base_authors = unit_authors(base_version.data["authorship"], base_units)
        paragraphs = [text[u.start : u.end] for u in units]
        authors = anchored_authors(base_text, base_units, base_authors, paragraphs, paragraph_map, run)
    if authors is None:
        if base is None:
            kind_of = "person" if by == "person" else "assistant"
            authors = [{"kind": kind_of, "run": run if by != "person" else None} for _ in units]
        else:
            base_version = live[base]
            base_text = read_text(store, base_version.data["sha256"])
            base_units = units_of(store, fmt, base_text)
            base_authors = unit_authors(base_version.data["authorship"], base_units)
            authors = derive_authors(base_text, base_units, base_authors, text, units, by, run)
    digest = store_text(store, text)
    number = max((v.data["number"] for v in every), default=0) + 1
    version = tx.create(
        "text_version",
        {
            "owner_kind": kind,
            "owner_id": record_id,
            "field": field,
            "number": number,
            "sha256": digest,
            "format": fmt,
            "words": words(text),
            "source": source,
            "status": "accepted" if accept else "pending",
            "base": base,
            "replaces": now.data["number"] if accept and now else None,
            "authorship": [
                {**span, "words": words(text[span["start"] : span["end"]])} for span in spans_for(units, authors)
            ],
            "paragraph_map": list(paragraph_map or []),
            "note": note,
            "run": run,
            "created_at": store.clock(),
        },
        context,
    )
    if accept:
        tx.update(kind, record_id, {field: digest}, context, read_version=owner.version)
    return version


def _loaded(store: Any, version: Any) -> tuple[str, list[Unit], list[dict[str, Any]]]:
    text = read_text(store, version.data["sha256"])
    units = units_of(store, version.data["format"], text)
    return text, units, unit_authors(version.data["authorship"], units)


def review(store: Any, view: Any, version_id: str) -> dict[str, Any]:
    """What reviewing a pending version needs: it, the version it was made from, the current one, and the regions
    where they differ (three-way when the current text moved on since its base)."""
    from engine.storage import StoreError

    pending = view.get("text_version", version_id)
    if pending is None or pending.data["status"] != "pending":
        raise StoreError(f"{version_id} isn't a version waiting for review")
    key = (pending.data["owner_kind"], pending.data["owner_id"], pending.data["field"])
    every = {v.data["number"]: v for v in versions(view, *key)}
    now = current(view, *key)
    base = every.get(pending.data["base"]) if pending.data["base"] is not None else None
    empty: tuple[str, list[Unit], list[dict[str, Any]]] = ("", [], [])
    base_loaded = _loaded(store, base) if base else empty
    current_loaded = _loaded(store, now) if now else empty
    pending_loaded = _loaded(store, pending)
    found = regions(
        base_loaded[0], base_loaded[1], current_loaded[0], current_loaded[1], pending_loaded[0], pending_loaded[1]
    )
    return {
        "pending": pending,
        "base": base,
        "current": now,
        "texts": {"base": base_loaded, "current": current_loaded, "pending": pending_loaded},
        "regions": found,
    }


def accept(store: Any, tx: Any, context: Any, version_id: str, read_version: int, choices: dict[str, str]) -> Any:
    """Apply the person's choices on a pending version. Accepting everything (with the text not moved on since its
    base) makes the pending version current; a mix writes a merged version; rejecting everything discards it."""
    from engine.storage import StoreError

    found = review(store, tx, version_id)
    pending = found["pending"]
    if pending.version != read_version:
        raise StoreError(f"{version_id} changed since it was reviewed")
    unknown = sorted(set(choices) - {r.id for r in found["regions"] if r.id})
    if unknown:
        raise StoreError(f"there is no change {unknown[0]} in this version")
    base, now = found["base"], found["current"]
    b_text, b_units, _ = found["texts"]["base"]
    c_text, c_units, c_authors = found["texts"]["current"]
    p_text, p_units, p_authors = found["texts"]["pending"]
    text, authors, took = merge(b_text, b_units, c_text, c_units, c_authors, p_text, p_units, p_authors, choices)
    kind, record_id, field = (pending.data[k] for k in ("owner_kind", "owner_id", "field"))
    if not took:
        return tx.update("text_version", pending.id, {"status": "discarded"}, context, read_version=pending.version)
    same_base = (base.id if base else None) == (now.id if now else None)
    if same_base and text == p_text:
        owner = tx.get(kind, record_id)
        tx.update(kind, record_id, {field: pending.data["sha256"]}, context, read_version=owner.version)
        changes = {"status": "accepted", "replaces": now.data["number"] if now else None}
        return tx.update("text_version", pending.id, changes, context, read_version=pending.version)
    merged = new_version(
        store,
        tx,
        context,
        kind,
        record_id,
        field,
        text,
        source="merge",
        by="person",
        base=now.data["number"] if now else None,
        accept=True,
        authors=authors,
        note=f"changes accepted from version {pending.data['number']}",
    )
    tx.update("text_version", pending.id, {"status": "merged"}, context, read_version=pending.version)
    return merged


def discard(tx: Any, context: Any, version_id: str, read_version: int) -> Any:
    from engine.storage import StoreError

    pending = tx.get("text_version", version_id)
    if pending is None or pending.data["status"] != "pending":
        raise StoreError(f"{version_id} isn't a version waiting for review")
    if pending.version != read_version:
        raise StoreError(f"{version_id} changed since it was reviewed")
    return tx.update("text_version", pending.id, {"status": "discarded"}, context, read_version=pending.version)


# ---- anchored drafts -------------------------------------------------------------------------------------------------

ANCHOR_RULE = (
    "The text below has an id before each paragraph, such as [p3]. Start every paragraph you write with the ids of "
    "the paragraphs it comes from, in brackets: [p3] for a kept or rewritten paragraph, [p3,p4] when you merge two, "
    "the same id on two paragraphs when you split one, and [new] for a paragraph you add. Paragraphs marked atomic "
    "are never split or merged. End with one line listing the paragraphs you removed, `Removed: p5, p7`, or "
    "`Removed: none`."
)
_MARK = re.compile(r"^\[(new|p\d+(?:\s*,\s*p\d+)*)\][ \t]*", re.M)
_REMOVED = re.compile(r"^\s*Removed:\s*(none|p\d+(?:\s*,\s*p\d+)*)\s*\.?\s*$", re.M | re.I)


class AnchorProblem(ValueError):
    """An anchored draft's paragraph ids don't account for the text; the message is for the fix round."""


def anchored_text(text: str, units: list[Unit]) -> str:
    """The base text with each unit's id before it, as the run sees it."""
    parts = []
    for index, unit in enumerate(units, start=1):
        mark = f"[p{index}{' atomic' if unit.atomic else ''}] "
        parts.append(mark + text[unit.start : unit.end].strip())
    return "\n\n".join(parts)


def parse_anchored(answer: str, units: list[Unit]) -> tuple[str, list[dict[str, Any]]]:
    """The draft's text without its ids, and its paragraph map ([{"from": ["p3"], ...}] per paragraph, in order).
    Raises AnchorProblem when a base paragraph is unaccounted for, an id is unknown, or an atomic paragraph was split
    or merged."""
    removed_match = None
    for match in _REMOVED.finditer(answer):
        removed_match = match
    body = answer[: removed_match.start()] if removed_match else answer
    removed = set()
    if removed_match and removed_match.group(1).lower() != "none":
        removed = {x.strip() for x in removed_match.group(1).split(",")}
    marks = list(_MARK.finditer(body))
    if not marks:
        raise AnchorProblem("no paragraph starts with its ids; start each one with [p1], [p2], [new] and so on")
    if body[: marks[0].start()].strip():
        raise AnchorProblem("there is text before the first paragraph's ids; start the answer with an id")
    known = {f"p{i}" for i in range(1, len(units) + 1)}
    atomic = {f"p{i}" for i, u in enumerate(units, start=1) if u.atomic}
    paragraphs, mapping = [], []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        ids = [] if mark.group(1) == "new" else [x.strip() for x in mark.group(1).split(",")]
        paragraphs.append(body[mark.end() : end].strip())
        mapping.append({"from": ids})
    used = [i for entry in mapping for i in entry["from"]]
    problems = []
    unknown = sorted((set(used) | removed) - known, key=lambda x: int(x[1:]))
    if unknown:
        problems.append(f"{', '.join(unknown)} isn't a paragraph of the text")
    missing = sorted(known - set(used) - removed, key=lambda x: int(x[1:]))
    if missing:
        problems.append(f"{', '.join(missing)} is neither in the draft nor listed as removed")
    for pid in sorted(atomic, key=lambda x: int(x[1:])):
        if used.count(pid) > 1:
            problems.append(f"{pid} is atomic and was split")
        if any(pid in e["from"] and len(e["from"]) > 1 for e in mapping):
            problems.append(f"{pid} is atomic and was merged with another paragraph")
    if problems:
        raise AnchorProblem("; ".join(problems))
    return "\n\n".join(paragraphs) + "\n", mapping


def anchored_authors(
    base: str,
    base_units: list[Unit],
    base_authors: list[dict[str, Any]],
    paragraphs: list[str],
    mapping: list[dict[str, Any]],
    run: str | None,
) -> list[dict[str, Any]]:
    """Per-paragraph authors from a paragraph map: a paragraph kept word for word keeps its author; one rewritten from
    the person's text is "assistant_edit"; one from the assistant's own text, or new, is "assistant"."""
    authors = []
    for text, entry in zip(paragraphs, mapping, strict=True):
        sources = [int(i[1:]) - 1 for i in entry["from"]]
        if (
            len(sources) == 1
            and base[base_units[sources[0]].start : base_units[sources[0]].end].strip() == text.strip()
        ):
            authors.append(base_authors[sources[0]])
        elif any(base_authors[i]["kind"] == "person" for i in sources):
            authors.append({"kind": "assistant_edit", "run": run})
        else:
            authors.append({"kind": "assistant", "run": run})
    return authors
