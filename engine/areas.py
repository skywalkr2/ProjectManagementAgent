"""Areas of life under the personal project (design 6.32, "Personal life").

An area (`Project.area`) is ongoing and has no end day; a project under it has a goal and an end. Three things are
decided here, all by rules over the records and the settings, with no AI:

- **Reach.** What a draft about a project in an area may draw on stops at that area: the area, the projects inside
  it and the projects above it (the personal project), never a sibling area's facts, open items or knowledge.
- **Reading.** Which accounts may read an area's material (its content levels, and the ones above it) and whether
  reading it sends anything away from this computer.
- **Proposals.** When enough items filed under the personal project itself share a word, one area is offered for
  them. Words are matched whole, case aside, and a word the language uses every day never counts. Nothing is moved
  until the person says yes, and what they keep is their own edit, so a move is recorded as a correction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from engine import sides
from engine.ai.router import accounts
from engine.ai.smoke import where_of


def area_of(view: Any, project_id: str | None) -> str | None:
    """The area a project is in: itself when it is one, else the nearest project above it that is. None for a project
    in no area, or one that isn't there. A chain that loops stops where it began."""
    seen: set[str] = set()
    current = project_id
    while current and current not in seen:
        seen.add(current)
        record = view.get("project", current)
        if record is None:
            return None
        if record.data.get("area"):
            return current
        current = record.data.get("parent")
    return None


def _inside(view: Any, top: str) -> set[str]:
    """The project and every project inside it, at any depth."""
    children: dict[str, list[str]] = {}
    for project in view.list("project"):
        if parent := project.data.get("parent"):
            children.setdefault(parent, []).append(project.id)
    found, todo = {top}, [top]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def _above(view: Any, project_id: str) -> set[str]:
    found: set[str] = set()
    current = project_id
    while current and current not in found:
        found.add(current)
        record = view.get("project", current)
        current = record.data.get("parent") if record is not None else None
    return found


def reach(view: Any, projects: Iterable[str | None]) -> frozenset[str] | None:
    """The projects whose records a draft about `projects` may draw on, when any of them is in an area: each such
    area, the projects inside it and the projects above it. None when none is, which is no limit. A record that
    names no project is never an area's own and is not limited."""
    found: set[str] | None = None
    for project in projects:
        area = area_of(view, project)
        if area is not None:
            found = (found or set()) | _inside(view, area) | _above(view, area)
    return frozenset(found) if found is not None else None


def outside(allowed: frozenset[str] | None) -> Callable[[Mapping[str, Any]], bool]:
    """A test for the records a draft about an area leaves out: true for a record filed under a project outside its
    reach. With no limit nothing is left out."""

    def out(data: Mapping[str, Any]) -> bool:
        if allowed is None:
            return False
        named = [p for p in sides.projects_of(dict(data)) if p]
        return bool(named) and not any(p in allowed for p in named)

    return out


def either(first: Callable[[Mapping[str, Any]], bool] | None, second: Callable[[Mapping[str, Any]], bool]):
    """One test that is true when either is."""
    return second if first is None else lambda data: first(data) or second(data)


# ---- who reads an area ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reader:
    account: str
    name: str
    leaves: bool


@dataclass(frozen=True)
class Reading:
    """Who may read a project's material. `levels`: the content levels it carries (its own and those above it).
    `readers`: the accounts that may read it, in tier order, each saying whether reading sends it away from this
    computer (an address that isn't on this computer or its own network, or a program that talks to its own
    service). `state`: none (no account may), local (every one that may runs here) or away (at least one sends it
    away)."""

    levels: tuple[str, ...]
    readers: tuple[Reader, ...]
    state: str


def levels_of(view: Any, project_id: str) -> tuple[str, ...]:
    """The content levels a project's material carries: its own and those of every project above it."""
    found: dict[str, None] = {}
    for pid in sorted(_above(view, project_id), key=lambda p: p != project_id):
        record = view.get("project", pid)
        for level in (record.data.get("content_levels") if record is not None else None) or []:
            found[level] = None
    return tuple(found)


def reading(view: Any, cfg: Any, project_id: str) -> Reading:
    """Which accounts may read a project's material, from its content levels and what each account takes, and whether
    anything leaves this computer to reach them."""
    levels = levels_of(view, project_id)
    readers = []
    for ref in accounts(cfg, "internal", frozenset(levels)):
        provider_name = ref.partition("/")[0]
        provider = cfg.ai.providers[provider_name]
        if any(r.account == provider_name for r in readers):
            continue
        readers.append(Reader(provider_name, provider.label or provider_name, where_of(provider) != "local"))
    state = "none" if not readers else "away" if any(r.leaves for r in readers) else "local"
    return Reading(levels, tuple(readers), state)


# ---- offering an area ----------------------------------------------------------------------------------------------

#: What each kind's words are called and the statuses that leave it open (an item that has ended is no pattern).
_ITEMS: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "action": ("text", ("open", "held")),
    "question": ("title", ("open", "sent")),
    "fact": ("text", None),
    "event": ("title", None),
}


@dataclass(frozen=True)
class Proposal:
    """An area offered for items that share a word: the `word` they share (also the proposed name, capitalized),
    and the `items` (kind, id, read version, words) it would take, most recent first."""

    word: str
    name: str
    items: tuple[tuple[str, str, int, str], ...]


def _own_items(view: Any, cfg: Any, personal: str) -> list[tuple[str, str, int, str]]:
    replaced = {f.data["supersedes"] for f in view.list("fact") if f.data.get("supersedes")}
    found = []
    for kind, (field, open_statuses) in _ITEMS.items():
        for record in view.list(kind):
            data = record.data
            if sides.projects_of(data) != [personal]:
                continue
            if open_statuses and data.get("status") not in open_statuses:
                continue
            if kind == "fact" and record.id in replaced:
                continue
            found.append((kind, record.id, record.version, str(data.get(field) or "")))
    return found


def proposals(view: Any, cfg: Any) -> list[Proposal]:
    """The areas to offer now. None when the setting is zero or there is no personal project. The word shared by the
    most items goes first (ties by the word), and an item is offered once: it goes with the first word that takes
    it. A word already naming a project under the personal project, or a project of the same name, is not offered."""
    from engine.knowledge_section import _overlap_words

    needed = cfg.steward.areas.propose_after
    personal = sides.personal_project(view, cfg)
    if needed <= 0 or personal is None:
        return []
    everyday = {w.strip().lower() for w in cfg.language.everyday_words}
    named = {
        _stem(word)
        for project in view.list("project")
        if project.id in _inside(view, personal) and project.id != personal
        for word in _overlap_words(str(project.data["name"]))
    } | {str(p.data["name"]).strip().lower() for p in view.list("project")}
    items = _own_items(view, cfg, personal)
    words: dict[str, set[str]] = {}
    for _kind, record_id, _, text in items:
        for word in _overlap_words(text):
            if word.isalpha() and word not in everyday and _stem(word) not in everyday and word not in named:
                words.setdefault(word, set()).add(record_id)
    taken: set[str] = set()
    out: list[Proposal] = []
    for word, ids in sorted(words.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        mine = [i for i in items if i[1] in ids and i[1] not in taken]
        if len(mine) < needed or word.capitalize().lower() in named:
            continue
        taken |= {i[1] for i in mine}
        out.append(Proposal(word, word.capitalize(), tuple(sorted(mine, key=lambda i: i[1], reverse=True))))
    return out


def _stem(word: str) -> str:
    from engine.knowledge_section import _stem as stem

    return stem(word)


def find(view: Any, cfg: Any, word: str) -> Proposal | None:
    """The offer for a word as it stands now, or None when it no longer stands (fewer items share it, or the area
    exists)."""
    return next((p for p in proposals(view, cfg) if p.word == word), None)


@dataclass(frozen=True)
class Kept:
    """What keeping an offer did: the area made and the two changes to undo, the filing first."""

    project: str
    filed: str
    started: str


def keep(store: Any, cfg: Any, word: str) -> Kept:
    """Start the area offered for a word under the personal project and file its items under it, each filing the
    person's own edit of the item's project (so a move from the personal project is a correction the assistant learns
    from). Two changes, so the screen can undo both. Raises `StoreError` when the offer no longer stands or an item
    changed since it was offered."""
    from engine.applier import apply_as_person
    from engine.storage import StoreError

    view = store.read()
    offer = find(view, cfg, word)
    if offer is None:
        raise StoreError("That offer no longer stands: fewer items share the word now, or the area is already there.")
    personal = sides.personal_project(view, cfg)
    started = apply_as_person(
        store,
        cfg,
        [{"op": "project.add", "name": offer.name, "parent": personal, "area": True}],
        f"Started the area {offer.name}",
    )
    project = store.read().get("changeset", started).data["ops"][0]["records"][0]["id"]
    ops = [
        {
            "op": "record.edit",
            "record": {"kind": kind, "id": record_id},
            "fields": {("projects" if kind == "question" else "project"): [project] if kind == "question" else project},
            "read_version": version,
        }
        for kind, record_id, version, _ in offer.items
    ]
    filed = apply_as_person(store, cfg, ops, f"Filed {len(ops)} items under the area {offer.name}")
    return Kept(project, filed, started)
