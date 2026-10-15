"""Follow-on runs (design 6.7, follow-on changes): one request when a dated record moves or a fact is replaced.

A save that moves a calendar entry's start or end, moves an open action's due day, or adds a fact that replaces another
(`supersedes`) queues **one** request, in the same transaction as the change, whether the person made it or the
assistant made it from an input. The request names the change in `follows`; what moved, before and after, is read back
from the change's ledger entries. What is tied to the moved record is found here, by code, never by the model: items
that name the calendar entry or its series, and items on the same project whose words give the old day or repeat the
replaced fact. The run answers with changes to the person's own items (applied with Undo, like any change), a drafted
correction for anyone an item already reached (it waits for the person and is never sent) and notes.

One hop: what a follow-on run changes never starts another. Nothing here calls AI except the run itself.
"""

from __future__ import annotations

import calendar
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from engine.storage.store import WriteContext

TASK = "follow-on"
#: The fields of an action a follow-on run may change.
SETTABLE = {"action": ("due", "text")}
#: The kinds of change whose entries can be a move: a person's edit, the assistant's `record.set` and a new fact.
MOVE_OPS = ("record.set", "record.edit", "fact")
#: The dated fields of each record kind whose change is a move.
DATED = {"event": ("start", "end"), "action": ("due",)}

_ENGINE = WriteContext(actor="engine", trust="trusted", op="follow_on.queue")
_CLOSE = WriteContext(actor="engine", trust="trusted", op="follow_on.close")

NOTHING_TIED = "Nothing tied to this needed a change."
STALE = "The date was changed again or the change was undone, so there is nothing to bring in line."


@dataclass(frozen=True)
class Move:
    """One moved date or replaced fact: the record, the field, and its value before and after. For a replaced fact the
    field is `supersedes`, `before` is empty and `after` is the id of the fact it replaced."""

    kind: str
    record: str
    field: str
    before: Any
    after: Any
    actor: str = "pm"


@dataclass
class Tied:
    """A record tied to a move, with why."""

    kind: str
    id: str
    data: Mapping[str, Any]
    why: list[str] = field(default_factory=list)


def is_move(kind: str, version: int, field_name: str | None, before: Any, after: Any, op: str) -> bool:
    """Whether one entry of the change is a move: a dated field that held a value and now holds another, or a new
    fact that replaces another."""
    if op.split("#", 1)[0] not in MOVE_OPS or field_name is None:
        return False
    if kind == "fact":
        return field_name == "supersedes" and version == 1 and after is not None
    return version > 1 and field_name in DATED.get(kind, ()) and before is not None and before != after


def queue(tx: Any, cfg: Any, now: str) -> str | None:
    """Queue the request for the moves this transaction made, inside it. One request however many records moved. Nothing
    is queued when following is off, when nothing moved, when no change wrote the move, or when the change is a
    follow-on run's own (one hop). Returns the request id."""
    if not cfg.dispatch.knowledge.follow_on:
        return None
    if not any(is_move(kind, version, f, before, after, op) for kind, _, version, f, before, after, op in tx.pending):
        return None
    changeset_id = tx.changeset
    changeset = tx.get("changeset", changeset_id) if changeset_id else None
    if changeset is None:
        return None
    request = tx.get("request", changeset.data["request"])
    if request is not None and request.data["task"] == TASK:
        return None
    moves = moves_of(tx, changeset_id)
    if not moves:
        return None
    data = {
        "task": TASK,
        "about": {"kind": moves[0].kind, "id": moves[0].record},
        "origin": "schedule",
        "state": "queued",
        "waiting": "With the assistant, starting now",
        "follows": changeset_id,
        "created_at": now,
    }
    return tx.create("request", data, _ENGINE).id


def moves_of(view: Any, changeset_id: str | None) -> list[Move]:
    """The moves a change made, read from its ledger entries: for each record and field, the first value before and the
    last after; a field back where it began is no move."""
    if not changeset_id:
        return []
    merged: dict[tuple[str, str, str], Move] = {}
    for row in view.changes_of(changeset_id):
        if not is_move(row["kind"], row["version"], row["field"], row["before"], row["after"], row["op"]):
            continue
        key = (row["kind"], row["record_id"], row["field"])
        first = merged.get(key)
        merged[key] = Move(
            row["kind"],
            row["record_id"],
            row["field"],
            first.before if first else row["before"],
            row["after"],
            row["actor"],
        )
    return [m for m in merged.values() if m.before != m.after]


def _current(view: Any, move: Move) -> bool:
    """Whether the move still stands: the record holds the value it moved to (a fact: it is there)."""
    found = view.get(move.kind, move.record)
    if found is None:
        return False
    return move.kind == "fact" or found.data.get(move.field) == move.after


def skip_reason(store: Any, cfg: Any, request: Mapping[str, Any]) -> str | None:
    """Why a follow-on request has nothing to do any more, in plain words, or None: following is off, the change is
    gone, or none of its moves still stands."""
    if not cfg.dispatch.knowledge.follow_on:
        return "Following moves is switched off."
    view = store.read()
    moves = moves_of(view, request.get("follows"))
    if not moves:
        return "The change this was for is gone."
    if not any(_current(view, m) for m in moves):
        return STALE
    return None


def close(store: Any, request_id: str, why: str) -> None:
    """Finish a follow-on request that has nothing to do, saying why."""
    with store.transaction() as tx:
        current = tx.get("request", request_id)
        if current is not None and (current.data["state"], current.data.get("waiting")) != ("done", why):
            tx.update(
                "request",
                request_id,
                {"state": "done", "waiting": why, "cause": None},
                _CLOSE,
                read_version=current.version,
            )


def finish(store: Any, request_id: str, changeset_id: str) -> None:
    """A follow-on run was applied. An answer with no change in it needs no review: the request is done."""
    with store.transaction() as tx:
        found = tx.get("changeset", changeset_id)
        current = tx.get("request", request_id)
        if found is None or current is None or found.data["ops"]:
            return
        tx.update(
            "request", request_id, {"state": "done", "waiting": NOTHING_TIED}, _CLOSE, read_version=current.version
        )


# ---- what is tied ----------------------------------------------------------------------------------------------------


def _day(value: Any, here: ZoneInfo) -> date | None:
    """The day a stored date or date-time falls on, in the person's days; None when it can't be read."""
    from engine.series import span

    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    days = span({"start": str(value)}, here)
    return days[0] if days else None


def date_regexes(patterns: Iterable[str], day: date) -> list[re.Pattern[str]]:
    """The patterns for how a day is written in running text, filled in for this day."""
    names = [calendar.month_name[day.month], calendar.month_abbr[day.month]]
    month = "(?:" + "|".join(re.escape(n) for n in sorted(set(names), key=len, reverse=True) if n) + ")"
    found = []
    for pattern in patterns:
        filled = (
            pattern.replace("{iso}", re.escape(day.isoformat()))
            .replace("{day}", f"0?{day.day}")
            .replace("{month}", month)
            .replace("{year}", str(day.year))
        )
        found.append(re.compile(filled, re.IGNORECASE))
    return found


def _words(kind: str, data: Mapping[str, Any]) -> str:
    """The words of an item a date or a fact can be cited in."""
    if kind == "action":
        return f"{data.get('text') or ''} {data.get('notes') or ''}"
    if kind == "question":
        return f"{data.get('title') or ''} {data.get('text') or ''}"
    return str(data.get("text") or "")


def _open(kind: str, data: Mapping[str, Any]) -> bool:
    return data.get("status") not in {"action": ("done", "dropped"), "question": ("answered", "dropped")}.get(kind, ())


def _on_project(kind: str, data: Mapping[str, Any], project: str | None) -> bool:
    if project is None:
        return False
    return project in (data.get("projects") or []) if kind == "question" else data.get("project") == project


def reached(view: Any, kind: str, data: Mapping[str, Any]) -> list[str]:
    """The ids of the people an action or question already reached: those an action's notice told or a chase followed
    up, and the person a sent question went to."""
    if kind == "action":
        return list(dict.fromkeys([*(data.get("told") or {}), *(data.get("followed_up") or {})]))
    if kind == "question" and (data.get("status") == "sent" or data.get("sent_at")):
        return [data["to"]]
    return []


def tied_records(view: Any, cfg: Any, moves: list[Move]) -> list[Tied]:
    """The records tied to the moves, at most the configured number: those that name the moved entry or its series
    first, then those on the moved record's project whose words give the old day (or repeat the replaced fact). Each
    comes with why, once; the moved records themselves are never among them."""
    from engine.knowledge_section import topic_share
    from engine.today import zone

    settings = cfg.dispatch.knowledge
    here = zone(cfg)
    moved = {(m.kind, m.record) for m in moves}
    replaced_ids = {f.data["supersedes"] for f in view.list("fact") if f.data.get("supersedes")}
    items = [
        (kind, s)
        for kind in ("action", "question", "fact")
        for s in view.list(kind)
        if (kind, s.id) not in moved and _open(kind, s.data) and s.id not in replaced_ids
    ]
    found: dict[tuple[str, str], Tied] = {}
    linked: list[tuple[str, str]] = []

    def add(kind: str, stored: Any, why: str, *, link: bool) -> None:
        key = (kind, stored.id)
        if key not in found:
            found[key] = Tied(kind, stored.id, stored.data)
            if link:
                linked.append(key)
        if why not in found[key].why:
            found[key].why.append(why)

    for move in moves:
        entry = view.get(move.kind, move.record)
        if entry is None:
            continue
        old: list[date] = []
        project = entry.data.get("project")
        series = entry.data.get("series") if move.kind == "event" else None
        if move.kind == "event":
            for kind, stored in items:
                data = stored.data
                if data.get("event") == entry.id:
                    add(kind, stored, f"is on calendar entry {entry.id}", link=True)
                elif series and data.get("series") == series and not data.get("event"):
                    add(kind, stored, f"belongs to series {series}", link=True)
        if move.kind in DATED:
            before, after = _day(move.before, here), _day(move.after, here)
            if before is not None and before != after:
                old.append(before)
        replaced = view.get("fact", move.after) if move.kind == "fact" else None
        if replaced is not None:
            project = project or replaced.data.get("project")
            for kind, stored in items:
                data = stored.data
                if replaced.data.get("event") and data.get("event") == replaced.data["event"] and kind != "fact":
                    add(kind, stored, f"is on the same calendar entry as the replaced fact {replaced.id}", link=True)
        for kind, stored in items:
            data = stored.data
            if kind == "fact" or not _on_project(kind, data, project):
                continue
            words = _words(kind, data)
            for day in old:
                if any(rx.search(words) for rx in date_regexes(cfg.language.date_patterns, day)):
                    add(kind, stored, f"its words give the old day, {day.isoformat()}", link=False)
            if replaced is not None and topic_share(replaced.data["text"], words) >= settings.follow_on_match:
                add(kind, stored, f"its words repeat the replaced fact {replaced.id}", link=False)
    ordered = [*linked, *(key for key in found if key not in linked)]
    return [found[key] for key in ordered[: settings.follow_on_max_tied]]


def reach_problem(view: Any, cfg: Any, request: Mapping[str, Any], op: Any, people: Any) -> str | None:
    """Why an op of a follow-on answer can't stand, or None. It may change the day or words of an action tied to the
    move that nobody was told about; it may draft a correction only for someone a tied item already reached; and a
    note is always fine."""
    moves = moves_of(view, request.get("follows"))
    tied = {(t.kind, t.id): t for t in tied_records(view, cfg, moves)}
    name = getattr(op, "op", None)
    if name == "record.set":
        target = tied.get((op.kind, op.id))
        if target is None:
            return f"{op.kind} {op.id} isn't tied to what moved, so this run doesn't change it"
        if op.field not in SETTABLE.get(op.kind, ()):
            return f"this run changes only the day or words of an action, not {op.kind}.{op.field}"
        if reached(view, op.kind, target.data):
            return f"{op.id} already reached someone: draft a correction for them instead of changing it"
    elif name == "question.add":
        recipients = {p for t in tied.values() for p in reached(view, t.kind, t.data)}
        if people.resolve(op.to).person not in recipients:
            return "a correction goes only to someone a tied item already reached"
    return None


# ---- the packet ------------------------------------------------------------------------------------------------------


def _marked(text: str) -> str:
    """Text that can't close the marking it sits in."""
    return text.replace("</untrusted", "</ untrusted")


def _line(view: Any, move: Move) -> str:
    """One move, in words, with who made it."""
    found = view.get(move.kind, move.record)
    label = {"event": "calendar entry", "action": "action", "fact": "fact"}[move.kind]
    title = ""
    if found is not None:
        title = found.data.get("title") or found.data.get("text") or ""
    who = "The person changed" if move.actor == "pm" else "The assistant changed, from an input,"
    head = f'{who} {label} {move.record} "{" ".join(str(title).split())[:120]}"'
    if move.kind == "fact":
        old = view.get("fact", move.after)
        said = " ".join(str(old.data["text"]).split())[:200] if old is not None else "(gone)"
        return f'{head}: it replaces {move.after}, which said "{said}".'
    return f"{head}: {move.field} was {move.before}, now {move.after}."


def _shown(view: Any, people: Any, tied: Tied) -> dict[str, Any]:
    """A tied record as it is now, for the packet."""
    data = tied.data
    shown: dict[str, Any] = {"kind": tied.kind, "id": tied.id, "why": tied.why}
    if tied.kind == "action":
        shown |= {
            "text": data["text"],
            "due": str(data["due"]) if data.get("due") else None,
            "status": data["status"],
            "owners": [people.name(o["person"]) for o in data.get("owners", [])],
            "notes": data.get("notes"),
        }
    elif tied.kind == "question":
        shown |= {
            "title": data["title"],
            "text": data.get("text") or None,
            "to": people.name(data["to"]),
            "status": data["status"],
            "links": [link["url"] for link in data.get("links", [])],
        }
    else:
        shown["text"] = data["text"]
    for key in ("event", "series"):
        if data.get(key):
            shown[key] = data[key]
    ids = reached(view, tied.kind, data)
    shown["already_reached"] = [f"{people.name(p)} ({p})" for p in ids] or "nobody"
    return {k: v for k, v in shown.items() if v not in (None, "", [])}


def build(ws: Any, store: Any, cfg: Any, req: Any, kind: Any, today: date) -> Any:
    """The packet for one follow-on run. Stable first: the instructions, the op reference, the practice, what has been
    learned, the people and the projects. Then the request: what moved, before and after, and each tied record as it
    is now with why it is tied and who it already reached. Records are data: marked as from outside."""
    from dataclasses import replace

    from engine.cleaning import Cleaned
    from engine.dispatcher import _data_level
    from engine.names import People
    from engine.ops import reach_choices, reference_for
    from engine.packet import Packet, PacketRefused, _guidance, _learned, _people, _projects, _task
    from engine.prompts import render

    view = store.read()
    moves = moves_of(view, req.data.get("follows"))
    if not moves:
        raise PacketRefused("the change this was for is gone")
    people = People(store, cfg)
    tied = tied_records(view, cfg, moves)
    lines = "\n".join(f"- {_line(view, m)}" for m in moves)
    project = next(
        (p for m in moves if (f := view.get(m.kind, m.record)) is not None and (p := f.data.get("project"))), None
    )
    learned = _learned(
        store,
        cfg,
        kind,
        people,
        projects=[project] if project else [],
        source=None,
        text=lines,
        today=today,
    )
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        part
        for part in (
            "# Op reference\n" + reference_for(list(kind.ops), store.plugins.ops, reach=reach_choices(store.plugins)),
            "# Practice\n" + _guidance(kind),
            learned.stable,
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    shown = json.dumps([_shown(view, people, t) for t in tied], ensure_ascii=False, indent=1) if tied else "(none)"
    parts = [
        f"Today is {today.isoformat()} ({today.strftime('%A')}).",
        learned.per_input,
        f'# What moved\n<untrusted source="records">\n{_marked(lines)}\n</untrusted>',
        f'# What is tied to it, as it is now\n<untrusted source="records">\n{_marked(shown)}\n</untrusted>',
    ]
    request = "\n\n".join(p for p in parts if p)
    task = replace(_task(cfg, store, kind, instructions, stable, request), knowledge=learned.log.model_dump())
    return Packet(
        task,
        request,
        Cleaned("", 0, 0, False, 0),
        "",
        too_long=False,
        untrusted_material=True,
        cites=f"follow-on:{req.id}",
        data_level=_data_level(store, req.data),
        knowledge=learned.log,
    )
