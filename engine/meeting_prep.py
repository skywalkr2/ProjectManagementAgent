"""Prep before a calendar entry and capture after it (design 6.32), for any entry with other people on it, not only a
series' meeting.

- **Prep** is worked out by rules from the records: who is coming (a person id when the workspace knows them), the
  open things with each of them (promises both ways, questions, replies owed), the last time in touch, and what the last
  entry with them left open. It is the entry's page and a line on Today `steward.meetings.prep_hours_before` before the
  entry starts. A prep note is a draft the assistant writes on request (the `meeting-prep` kind, filed as a pending
  draft of the entry's `prep` text), estimated and held for the person's go like every draft.
- **Capture** is a line on Today after the entry ends, asking what happened. The person's words are handed in like any
  note typed on a record, so the promises, questions and facts in them come out through the usual extraction with their
  evidence and are tied to the entry. Saying there is nothing to note ends the line with no run.

Nothing here reaches a service, and nothing but the prep note calls AI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from engine import entry_rules
from engine.meeting_guests import Guest, guests, window, with_others
from engine.names import People
from engine.people_memory import Item, Touch, action_item, last_in_touch, open_with
from engine.storage import StoreError, WriteContext
from engine.texts import current, read_text, versions
from engine.today import zone

TASK = "meeting-prep"
_CAPTURE = WriteContext(actor="pm", trust="trusted", op="meeting.capture")
_ASK = WriteContext(actor="pm", trust="trusted", op="meeting.prep_note")
#: The request states in which the assistant still has the note, or the person has to act before it can go on.
IN_HAND = ("queued", "running", "needs_you")


@dataclass(frozen=True)
class LeftOpen:
    """The latest entry before this one that a person was on, with what it left open: the open actions and questions
    tied to it that aren't already among what is open with that person."""

    event: str
    title: str
    on: date
    items: list[Item]
    untrusted: bool = False


@dataclass(frozen=True)
class PersonPrep:
    """One person coming: what is open with them (at most `steward.meetings.max_items`, `more` counts the rest), the
    last time in touch and what the last entry with them left open."""

    person: str
    asked_of: list[Item]
    asked_by: list[Item]
    promised_to: list[Item]
    promised_by: list[Item]
    more: int
    last_in_touch: Touch | None
    left_open: LeftOpen | None

    @property
    def open(self) -> int:
        return len(self.asked_of) + len(self.asked_by) + len(self.promised_to) + len(self.promised_by) + self.more


@dataclass(frozen=True)
class Prep:
    """The prep for one entry. `coming` lists everyone else on it who hasn't declined (a person id when known, else the
    name or address as the calendar wrote it); `people` is what rules found for the known ones. `untrusted` marks a
    title that came from outside."""

    event: str
    title: str
    start: str
    end: str | None
    where: str | None
    untrusted: bool
    over: bool
    coming: list[Guest]
    people: list[PersonPrep]


@dataclass(frozen=True)
class Line:
    """An entry that needs a line on Today: its id and title, when it starts and ends, the known people coming
    (`people`), how many others are on it (`others`) and how many things are open with them (`open`)."""

    event: str
    title: str
    start: datetime
    end: datetime
    people: list[str]
    others: int
    open: int
    untrusted: bool = False


def _left_open(
    view: Any, cfg: Any, person: str, entry_id: str, now: datetime, here: ZoneInfo, mine: tuple[set[str], set[str]]
) -> tuple[Any, list[Item]] | None:
    """The latest ended entry other than `entry_id` that the person was on, and what is still open on it."""
    latest = None
    for entry in view.list("event"):
        spans = window(entry.data, here)
        if entry.id == entry_id or spans is None or spans[1] > now or entry.data.get("cancelled"):
            continue
        if not any(g.person == person for g in guests(view, cfg, entry.data, mine=mine)):
            continue
        if latest is None or (spans[1], entry.id) > latest[0]:
            latest = ((spans[1], entry.id), entry)
    if latest is None:
        return None
    entry = latest[1]
    today = now.astimezone(here).date()
    items: list[Item] = []
    for action in view.list("action"):
        if action.data.get("event") == entry.id and action.data.get("status") == "open":
            items.append(action_item(view, "left_open", action, today, here))
    for question in view.list("question"):
        d = question.data
        if d.get("event") == entry.id and d.get("status") in ("open", "sent"):
            items.append(Item("left_open", "question", question.id, str(d["title"]), source=d.get("source")))
    return entry, items


def prep(store: Any, cfg: Any, entry_id: str, now: datetime) -> Prep | None:
    """The prep for one entry, or None when there is no such entry. An entry nobody else is on has an empty list of
    people coming."""
    view = store.read()
    entry = view.get("event", entry_id)
    if entry is None:
        return None
    here = zone(cfg)
    mine = entry_rules.identity(view, cfg)
    pm = cfg.workspace.user.person
    today = now.astimezone(here).date()
    coming = guests(view, cfg, entry.data, mine=mine)
    people = People(store, cfg)
    cap = cfg.steward.meetings.max_items
    found: list[PersonPrep] = []
    for guest in coming:
        if guest.person is None:
            continue
        items = open_with(view, pm, guest.person, today, here)
        # The cap is for each person over the four kinds together, in the order below; what is cut is counted.
        total = sum(len(v) for v in items.values())
        trimmed: dict[str, list[Item]] = {}
        kept = 0
        for kind in ("promised_to", "promised_by", "asked_by", "asked_of"):
            trimmed[kind] = items[kind][: max(0, cap - kept)]
            kept += len(trimmed[kind])
        touch, _ = last_in_touch(view, cfg, people, guest.person, now)
        left = _left_open(view, cfg, guest.person, entry_id, now, here, mine)
        left_open = None
        if left is not None:
            counted = {i.id for group in items.values() for i in group}
            left_open = LeftOpen(
                left[0].id,
                left[0].data["title"],
                (window(left[0].data, here) or (now, now))[1].astimezone(here).date(),
                [i for i in left[1] if i.id not in counted],
                left[0].data.get("trust") == "untrusted",
            )
        found.append(
            PersonPrep(
                guest.person,
                trimmed["asked_of"],
                trimmed["asked_by"],
                trimmed["promised_to"],
                trimmed["promised_by"],
                total - kept,
                touch,
                left_open,
            )
        )
    spans = window(entry.data, here)
    return Prep(
        entry.id,
        entry.data["title"],
        entry.data["start"],
        entry.data.get("end"),
        entry.data.get("where"),
        entry.data.get("trust") == "untrusted",
        spans is not None and spans[1] <= now,
        coming,
        found,
    )


def _open_count(view: Any, pm: str | None, guests_: list[Guest], today: date, here: ZoneInfo) -> int:
    seen: set[str] = set()
    for guest in guests_:
        if guest.person is not None:
            for items in open_with(view, pm, guest.person, today, here).values():
                seen.update(i.id for i in items)
    return len(seen)


def prep_lines(store: Any, cfg: Any, now: datetime) -> list[Line]:
    """The entries with other people on them that start within `steward.meetings.prep_hours_before` hours and have not
    started, with at least `prep_min_open` open things with the people coming; soonest first."""
    view = store.read()
    here = zone(cfg)
    rules = cfg.steward.meetings
    mine = entry_rules.identity(view, cfg)
    pm = cfg.workspace.user.person
    today = now.astimezone(here).date()
    found: list[Line] = []
    for entry in view.list("event"):
        spans = window(entry.data, here)
        if spans is None or not spans[0] - timedelta(hours=rules.prep_hours_before) <= now < spans[0]:
            continue
        others = with_others(view, cfg, entry, mine=mine)
        if not others:
            continue
        open_ = _open_count(view, pm, others, today, here)
        if open_ < rules.prep_min_open:
            continue
        found.append(
            Line(
                entry.id,
                entry.data["title"],
                spans[0],
                spans[1],
                [g.person for g in others if g.person],
                len(others),
                open_,
                entry.data.get("trust") == "untrusted",
            )
        )
    return sorted(found, key=lambda x: (x.start, x.event))


def capture_lines(store: Any, cfg: Any, now: datetime) -> list[Line]:
    """The entries with other people on them that ended within `steward.meetings.capture_hours_after` hours and that
    nothing has been written down for; the latest ended first."""
    view = store.read()
    here = zone(cfg)
    rules = cfg.steward.meetings
    mine = entry_rules.identity(view, cfg)
    found: list[Line] = []
    for entry in view.list("event"):
        spans = window(entry.data, here)
        if entry.data.get("captured_at") or spans is None:
            continue
        if not spans[1] <= now < spans[1] + timedelta(hours=rules.capture_hours_after):
            continue
        others = with_others(view, cfg, entry, mine=mine)
        if not others:
            continue
        found.append(
            Line(
                entry.id,
                entry.data["title"],
                spans[0],
                spans[1],
                [g.person for g in others if g.person],
                len(others),
                0,
                entry.data.get("trust") == "untrusted",
            )
        )
    return sorted(found, key=lambda x: (x.end, x.event), reverse=True)


# ---- capture ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Captured:
    """What capturing did: the `request` queued to read the person's words (none when they said nothing to note, or
    only a bare confirmation, which makes no run) and when the entry was marked."""

    request: str | None
    captured_at: datetime


def capture(ws: Any, store: Any, cfg: Any, entry_id: str, text: str, now: datetime) -> Captured:
    """Write down what happened at an entry, as the person's own words typed on it: handed in like any note, so what
    they promised, asked and learned comes out through the usual extraction with its evidence, tied to the entry. No
    words means there is nothing to note. Either way the entry is marked, and its line on Today goes."""
    from engine.intake import note_as_input

    view = store.read()
    entry = view.get("event", entry_id)
    if entry is None:
        raise StoreError(f"There is no calendar entry {entry_id}.")
    words = (text or "").strip()
    request = (
        note_as_input(ws, store, cfg, item=("event", entry_id), text=words, route="meeting_capture", now=now)
        if words
        else None
    )
    with store.transaction() as tx:
        current_entry = tx.get("event", entry_id)
        if current_entry is not None:
            tx.update("event", entry_id, {"captured_at": now.isoformat()}, _CAPTURE, read_version=current_entry.version)
    return Captured(request, now)


# ---- the prep note ---------------------------------------------------------------------------------------------------


def _requests(view: Any, entry_id: str) -> list[Any]:
    return [
        r
        for r in view.list("request")
        if r.data["task"] == TASK and (r.data.get("about") or {}).get("id") == entry_id and not r.data.get("dismissed")
    ]


def pending_draft(view: Any, entry_id: str) -> Any | None:
    """The draft of the prep note that waits for the person's review, if there is one."""
    waiting = [v for v in versions(view, "event", entry_id, "prep") if v.data["status"] == "pending"]
    return waiting[-1] if waiting else None


@dataclass(frozen=True)
class NoteState:
    """Where the prep note stands. `state`: none (nobody has asked), working (queued or running), needs_go (held for the
    person's go, with the estimate when there is one), draft (a draft waits for review) or kept (the person's own)."""

    state: str
    request: str | None = None
    estimate_usd: float | None = None


def note_state(view: Any, entry_id: str) -> NoteState:
    draft = pending_draft(view, entry_id)
    for r in sorted(_requests(view, entry_id), key=lambda r: (str(r.data["created_at"]), r.id), reverse=True):
        if r.data["state"] in ("queued", "running"):
            return NoteState("working", r.id)
        if r.data["state"] == "needs_you" and r.data.get("approval") == "required":
            return NoteState("needs_go", r.id, r.data.get("estimate_usd"))
        if r.data["state"] == "review" and draft is not None:
            return NoteState("draft", r.id)
    return NoteState("kept" if current(view, "event", entry_id, "prep") is not None else "none")


def ask_for_note(store: Any, entry_id: str, note: str | None = None) -> str:
    """Queue the request for a prep note on an entry; returns its id. Nothing is kept until the person has read the
    draft."""
    words = " ".join((note or "").split())[:2000] or None
    with store.transaction() as tx:
        if tx.get("event", entry_id) is None:
            raise StoreError(f"There is no calendar entry {entry_id}.")
        held = note_state(tx, entry_id)
        if held.state in ("working", "needs_go", "draft"):
            raise StoreError("The assistant already has this prep note in hand.")
        made = tx.create(
            "request",
            {
                "task": TASK,
                "about": {"kind": "event", "id": entry_id},
                "note": words,
                "origin": "pm",
                "state": "queued",
                "waiting": "With the assistant, starting now",
                "created_at": store.clock(),
            },
            _ASK,
        )
    return made.id


def _marked(text: str) -> str:
    """Text that can't close the marking it sits in."""
    return text.replace("</untrusted", "</ untrusted")


def facts(store: Any, cfg: Any, entry_id: str, now: datetime) -> str:
    """What the prep note is written from, as the assistant is shown it: the entry, who is coming and, for each person,
    what is open with them, the last time in touch and what the last entry with them left open. Plain lines from the
    records; data, never instruction."""
    found = prep(store, cfg, entry_id, now)
    if found is None:
        return ""
    people = People(store, cfg)

    def line(item: Item) -> str:
        return f"- {item.text}" + (f" (due {item.due.isoformat()})" if item.due else "")

    parts = [
        f"The entry: {found.title}, {found.start}" + (f" to {found.end}" if found.end else ""),
        f"Where: {found.where}" if found.where else "",
    ]
    outside = [g for g in found.coming if g.person is None]
    if outside:
        parts.append(
            "Others coming the workspace doesn't know: " + ", ".join(g.name or g.address or "?" for g in outside)
        )
    for one in found.people:
        name = people.name(one.person)
        parts.append(f"## {name}")
        groups = (
            ("The person promised them", one.promised_to),
            ("They promised the person", one.promised_by),
            ("They asked the person (a reply is owed)", one.asked_by),
            ("The person asked them", one.asked_of),
        )
        for label, items in groups:
            if items:
                parts.append(f"{label}:\n" + "\n".join(line(i) for i in items))
        if one.more:
            parts.append(f"{one.more} more open things are not listed.")
        if one.last_in_touch is not None:
            touch = one.last_in_touch
            how = {"from": "mail from them", "to": "a message to them", "met": "a meeting with them"}[touch.kind]
            parts.append(f"Last in touch: {how} on {touch.on.isoformat()}")
        if one.left_open is not None and one.left_open.items:
            parts.append(
                f"Still open from the last meeting with them ({one.left_open.title}, {one.left_open.on.isoformat()}):\n"
                + "\n".join(line(i) for i in one.left_open.items)
            )
    return "\n".join(p for p in parts if p)


def build(ws: Any, store: Any, cfg: Any, req: Any, kind: Any, today: date) -> Any:
    """The packet for one run. Stable first: the instructions, the practice, what has been learned, the people and the
    projects. Then the request: the entry's facts (data, marked as from outside), the text kept so far when there is
    one, and the person's note."""
    from engine.cleaning import Cleaned
    from engine.dispatcher import _data_level
    from engine.packet import DRAFT_RULE, Packet, PacketRefused, _guidance, _learned, _people, _projects, _task
    from engine.prompts import render

    about = req.data.get("about") or {}
    found = store.read().get("event", about.get("id")) if about.get("kind") == "event" else None
    if found is None:
        raise PacketRefused("the calendar entry this note was for is gone")
    note = req.data.get("note") or ""
    moment = datetime.combine(today, datetime.min.time(), tzinfo=zone(cfg)) + timedelta(hours=12)
    shown = facts(store, cfg, found.id, moment)
    kept = current(store.read(), "event", found.id, "prep")
    kept_text = read_text(store, kept.data["sha256"]) if kept is not None else ""
    learned = _learned(
        store, cfg, kind, People(store, cfg), projects=[], source=None, text=f"{shown}\n{note}", today=today
    )
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        part
        for part in (
            "# Practice\n" + _guidance(kind),
            learned.stable,
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )
    parts = [
        f"Today is {today.isoformat()} ({today.strftime('%A')}).",
        learned.per_input,
        f'# The meeting\n<untrusted source="records">\n{_marked(shown)}\n</untrusted>',
        f"# The text so far, which you revise\n<text>\n{kept_text.strip()}\n</text>" if kept_text.strip() else "",
        f"# The person's note\n<note>\n{note}\n</note>" if note else "",
        DRAFT_RULE,
    ]
    request = "\n\n".join(p for p in parts if p)
    task = replace(_task(cfg, store, kind, instructions, stable, request), knowledge=learned.log.model_dump())
    return Packet(
        task,
        request,
        Cleaned("", 0, 0, False, 0),
        note,
        too_long=False,
        untrusted_material=True,
        cites=f"event:{found.id}",
        about=("event", found.id),
        draft_base=kept.data["number"] if kept is not None else None,
        data_level=_data_level(store, req.data),
        knowledge=learned.log,
    )


__all__ = [
    "Captured",
    "LeftOpen",
    "Line",
    "NoteState",
    "PersonPrep",
    "Prep",
    "ask_for_note",
    "build",
    "capture",
    "capture_lines",
    "facts",
    "note_state",
    "prep",
    "prep_lines",
]
