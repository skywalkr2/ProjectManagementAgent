"""Follow-on runs (design 6.7, follow-on changes): one request when a dated record moves or a fact is replaced.

A save that moves a calendar entry's start or end, moves an open action's due day, or adds a fact that replaces another
(`supersedes`) queues **one** request, in the same transaction as the change, whether the person made it or the
assistant made it from an input. The request names the change in `follows`; what moved, before and after, is read back
from the change's ledger entries. What is tied to the moved record is found here, by code, never by the model: items
that name the calendar entry or its series, and items on the same project whose words give the old day or repeat the
replaced fact. The run answers with questions about what the move may have left out of line, a drafted correction
for anyone an item already reached (it waits for the person and is never sent) and notes.

A decided action's date or wording is never changed by the run. For each tied action whose date the move affects, it
asks whoever decides (the action's owner, the person when nobody is named or no link can be carried to the owner)
whether the date should change; when the moved entry or replaced fact carried more than one dated action (an agenda
item, a question, a fact, notes, several actions), it asks the person to confirm the plan still holds. Which questions
are needed, and to whom, is decided here by code; the run words them.

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
    #: The ids of the moved records it is tied to.
    by: list[str] = field(default_factory=list)
    #: Whether its dated words (not only a link) tie it to the move.
    cites: bool = False


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
    first, then those on the moved record's project whose words give the old day (or repeat the replaced fact), then
    open actions on an entry's project due between its old and new day (the new day included). Each comes with why,
    once, and the moved records it is tied to; the moved records themselves are never among them."""
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
    between: list[tuple[str, str]] = []

    def add(
        move: Move, kind: str, stored: Any, why: str, *, link: bool, cites: bool = False, late: bool = False
    ) -> None:
        key = (kind, stored.id)
        if key not in found:
            found[key] = Tied(kind, stored.id, stored.data)
            if link:
                linked.append(key)
            elif late:
                between.append(key)
        tied = found[key]
        if why not in tied.why:
            tied.why.append(why)
        if move.record not in tied.by:
            tied.by.append(move.record)
        tied.cites = tied.cites or cites

    for move in moves:
        entry = view.get(move.kind, move.record)
        if entry is None:
            continue
        old: list[date] = []
        window: tuple[date, date] | None = None
        project = entry.data.get("project")
        series = entry.data.get("series") if move.kind == "event" else None
        if move.kind == "event":
            for kind, stored in items:
                data = stored.data
                if data.get("event") == entry.id:
                    add(move, kind, stored, f"is on calendar entry {entry.id}", link=True)
                elif series and data.get("series") == series and not data.get("event"):
                    add(move, kind, stored, f"belongs to series {series}", link=True)
        if move.kind in DATED:
            before, after = _day(move.before, here), _day(move.after, here)
            if before is not None and before != after:
                old.append(before)
                if move.kind == "event" and after is not None:
                    window = (before, after)
        replaced = view.get("fact", move.after) if move.kind == "fact" else None
        if replaced is not None:
            project = project or replaced.data.get("project")
            for kind, stored in items:
                data = stored.data
                if replaced.data.get("event") and data.get("event") == replaced.data["event"] and kind != "fact":
                    why = f"is on the same calendar entry as the replaced fact {replaced.id}"
                    add(move, kind, stored, why, link=True)
        for kind, stored in items:
            data = stored.data
            if kind == "fact" or not _on_project(kind, data, project):
                continue
            words = _words(kind, data)
            for day in old:
                if any(rx.search(words) for rx in date_regexes(cfg.language.date_patterns, day)):
                    add(move, kind, stored, f"its words give the old day, {day.isoformat()}", link=False, cites=True)
            if replaced is not None and topic_share(replaced.data["text"], words) >= settings.follow_on_match:
                add(move, kind, stored, f"its words repeat the replaced fact {replaced.id}", link=False, cites=True)
        if window is not None:
            low, high = sorted(window)
            for kind, stored in items:
                due = _day(stored.data.get("due"), here) if kind == "action" else None
                if due is None or not low <= due <= high or due == window[0]:
                    continue
                if _on_project(kind, stored.data, project):
                    why = (
                        f"is due {due.isoformat()}, between the old day {window[0].isoformat()} and the new day "
                        f"{window[1].isoformat()}"
                    )
                    add(move, kind, stored, why, link=False, late=True)
    ordered = [*linked, *(key for key in found if key not in linked and key not in between), *between]
    return [found[key] for key in ordered[: settings.follow_on_max_tied]]


def asks_date(tied: Tied) -> bool:
    """Whether a tied record is an action whose date the move may affect: it has a due day, or its words give the old
    day. An agenda item with no day of its own is placed on the meeting's next instance, not asked about."""
    return tied.kind == "action" and (bool(tied.data.get("due")) or tied.cites)


def date_asker(view: Any, people: Any, data: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Who a question about an action's date goes to, and the owner it stands in for. The action's first owner; the
    person when the owner is the person or nobody is named; and the person, saying who to ask, when the owner would need
    a link to what it is about and the project holds none they can open."""
    from engine.applier import _openable

    owners = [o["person"] for o in data.get("owners") or []]
    first, pm = (owners[0] if owners else None), people.pm
    if first is None or first == pm:
        return pm, None
    project = view.get("project", data["project"]) if data.get("project") else None
    if pm is None or any(_openable(link["url"]) for link in (project.data.get("links") if project else None) or []):
        return first, None
    return pm, first


def plans_to_confirm(moves: list[Move], tied: list[Tied]) -> list[tuple[Move, list[Tied]]]:
    """The moved entries and replaced facts that carried more than one dated action: what is tied to them includes an
    agenda item, a question, a fact, an action with notes, or several actions. Each comes with what is tied."""
    found = []
    for move in moves:
        if move.kind not in ("event", "fact"):
            continue
        items = [t for t in tied if move.record in t.by]
        more = len([t for t in items if t.kind == "action"]) > 1 or any(
            t.kind != "action" or not t.data.get("due") or str(t.data.get("notes") or "").strip() for t in items
        )
        if more:
            found.append((move, items))
    return found


def _names(text: str, record_id: str) -> bool:
    """Whether a record id stands in the words, as a whole word."""
    return re.search(rf"(?<![\w-]){re.escape(record_id)}(?![\w-])", text) is not None


def reach_problem(view: Any, cfg: Any, request: Mapping[str, Any], op: Any, people: Any) -> str | None:
    """Why an op of a follow-on answer can't stand, or None. It never changes an action's day or words; it may draft a
    correction only for someone a tied item already reached, ask a tied action's owner (or the person) whether its
    date should change, and ask the person whether a moved plan still holds; and a note is always fine."""
    name = getattr(op, "op", None)
    if name == "record.set":
        return (
            f"a follow-on run never changes {op.kind} {op.id}'s {op.field}: ask whoever decides whether it should "
            "change instead"
        )
    if name != "question.add":
        return None
    moves = moves_of(view, request.get("follows"))
    tied = tied_records(view, cfg, moves)
    to = people.resolve(op.to).person
    if to in {p for t in tied for p in reached(view, t.kind, t.data)}:
        return None
    named = op.matters_for or ""
    if op.kind == "decision":
        for t in tied:
            if asks_date(t) and _names(named, t.id) and to in (date_asker(view, people, t.data)[0], people.pm):
                return None
        if to == people.pm and any(_names(named, m.record) for m, _ in plans_to_confirm(moves, tied)):
            return None
    return (
        "a question from this run is a correction to someone a tied item already reached, a decision asking the "
        "person an action's date belongs to (or the person) whether it should change, with that action's id in "
        "matters_for, or a decision for the person asking whether a moved plan still holds, with the moved record's id "
        "in matters_for"
    )


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


def _ask_line(view: Any, people: Any, tied: Tied) -> str | None:
    """Who to ask whether a tied action's date should change, in words, or None when the action has no date to ask
    about."""
    if not asks_date(tied):
        return None
    to, instead = date_asker(view, people, tied.data)
    if to is None:
        return None
    who = f"{people.name(to)} ({to})"
    if instead is None:
        return who
    return f"{who}, because no link can be given to {people.name(instead)} ({instead}); say that they are who to ask"


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
            "ask_whether_the_date_should_change": _ask_line(view, people, tied),
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


def _plans(cfg: Any, moves: list[Move], tied: list[Tied]) -> str:
    """The moved entries and replaced facts whose plan the person is asked to confirm, with what is tied to each, or
    empty when no move carried more than one dated action."""
    from engine.today import zone

    here = zone(cfg)
    lines = []
    for move, items in plans_to_confirm(moves, tied):
        day = _day(move.after, here) if move.kind == "event" else None
        what = f"moved to {day.isoformat()}" if day else "replaced"
        listed = ", ".join(f"{t.kind} {t.id}" for t in items)
        lines.append(
            f"- {move.kind} {move.record} {what}: ask the person whether the plan for it still holds. Tied: {listed}."
        )
    return "# Plans to confirm with the person\n" + "\n".join(lines) if lines else ""


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
    plans = _plans(cfg, moves, tied)
    parts = [
        f"Today is {today.isoformat()} ({today.strftime('%A')}).",
        learned.per_input,
        f'# What moved\n<untrusted source="records">\n{_marked(lines)}\n</untrusted>',
        f'# What is tied to it, as it is now\n<untrusted source="records">\n{_marked(shown)}\n</untrusted>',
        plans,
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
