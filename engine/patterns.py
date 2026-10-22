"""Gentle suggestions with choices (design 6.32, "Manner"): patterns the rules find in the person's own records, each
offered as one suggestion line with two or three choices, and what each choice does.

The patterns, all read from the records with no AI:
- `moved`: one of the person's own to-dos whose day has moved `steward.patterns.moved_times` times. Choices: drop it,
  make it weekly, leave it.
- `redated`: a promise the person made whose day has moved `steward.patterns.redated_times` times. Choices: drop it,
  put it on hold, leave it.
- `replies`: the same person asked for `steward.patterns.owed_replies` replies and the person owes them all. Choices:
  none is needed, leave it.
- `stale`: the person's own undated to-dos nothing has changed for `ui.today.stale_after_days` ("Still doing this?").
  Choices: keep it, drop it, snooze it (several to-dos on one line: keep them, snooze them).

A choice acts at once and records a `suggestion_chosen` signal. One that changes records goes through the applier as the
person's own change, so its Undo is the change's Undo; one that only says "leave it", "keep" or "snooze" changes no
record, and its Undo takes the signal back. A choice that says "leave it" keeps the line away until something about it
changes (its change key), as "Not now" does. Nothing here closes or sends anything on its own: the line only offers.

The words a choice writes into a record (a reason for a drop, what a hold waits for, the phrase of a repeat) come from
the person's wording sheet, passed in by the caller; this module has none of its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.blocked import standing_hold
from engine.promises import is_promise
from engine.storage import StoreError, WriteContext

MOVED = "moved"
REDATED = "redated"
REPLIES = "replies"
STATES = (MOVED, REDATED, REPLIES)

#: What each pattern offers, in the order the line shows them: the first is the line's main button.
CHOICES: dict[str, tuple[str, ...]] = {
    MOVED: ("drop", "weekly", "leave"),
    REDATED: ("drop", "hold", "leave"),
    REPLIES: ("no_reply", "leave"),
}
#: What a stale line offers for one to-do, and for several.
STALE_ONE = ("keep", "drop", "snooze")
STALE_MANY = ("keep", "snooze")
#: The choices that change no record and keep the line away until it changes.
STAYS_OFF = ("leave",)
#: The choices that only mark a to-do as looked at: its quiet clock starts again (keep) or waits (snooze).
MARKS = ("keep", "snooze")
TAKEN_BACK = "taken back"

_CHOOSE = WriteContext(actor="pm", trust="trusted", op="suggestion.choose")


@dataclass(frozen=True)
class Found:
    """One pattern found: its `state`, the `subject` it is about (an action's id, or a person's for replies), the
    `actions` it covers, how many times it happened (`count`), the words of the first action (`text`) and, for
    replies, who they are owed to (`person`)."""

    state: str
    subject: str
    actions: list[str]
    count: int
    text: str
    person: str | None = None


def _me(store: Any, cfg: Any) -> str | None:
    from engine.names import People

    return People(store, cfg).pm


def date_moves(view: Any) -> dict[str, int]:
    """How many times the day of each action was moved from one day to another (setting a first day or taking one
    away is not a move), from the ledger."""
    counts: dict[str, int] = {}
    for record_id, rows in view.field_changes("action", ("due",)).items():
        moved = sum(
            1
            for r in rows
            if r["field"] == "due" and r["before"] is not None and r["after"] is not None and r["before"] != r["after"]
        )
        if moved:
            counts[record_id] = moved
    return counts


def _open_own(view: Any, me: str | None, d: dict[str, Any]) -> bool:
    """Whether an action is the person's own, open, and not waiting on a hold or a reply."""
    if d.get("status") != "open" or d.get("reply_owed") or standing_hold(view, d, pm=me):
        return False
    return bool(me) and any(o.get("person") == me for o in d.get("owners") or [])


def moved_todos(store: Any, cfg: Any) -> list[Found]:
    """The person's own to-dos that are not promises and whose day has moved `moved_times` times, most moves first. A
    repeating one is left out: it is meant to come round."""
    needed = cfg.steward.patterns.moved_times
    return _moved(store, cfg, needed, MOVED, promise=False)


def redated_promises(store: Any, cfg: Any) -> list[Found]:
    """The promises the person made whose day has moved `redated_times` times, most moves first."""
    return _moved(store, cfg, cfg.steward.patterns.redated_times, REDATED, promise=True)


def _moved(store: Any, cfg: Any, needed: int, state: str, *, promise: bool) -> list[Found]:
    if needed <= 0:
        return []
    view = store.read()
    me = _me(store, cfg)
    moves = date_moves(view)
    found = []
    for record in view.list("action"):
        d = record.data
        count = moves.get(record.id, 0)
        if count < needed or is_promise(d) != promise or d.get("repeat") or d.get("occurrence_of"):
            continue
        if _open_own(view, me, d):
            found.append(Found(state, record.id, [record.id], count, str(d["text"])))
    return sorted(found, key=lambda f: (-f.count, f.subject))


def owed_replies(store: Any, cfg: Any) -> list[Found]:
    """People the person owes `owed_replies` or more replies, the most first. Replies on hold are not owed yet."""
    needed = cfg.steward.patterns.owed_replies
    if needed <= 0:
        return []
    view = store.read()
    by_person: dict[str, list[Any]] = {}
    for record in view.list("action"):
        d = record.data
        if not d.get("reply_owed") or d.get("status") != "open" or not d.get("asker") or standing_hold(view, d):
            continue
        by_person.setdefault(str(d["asker"]), []).append(record)
    found = [
        Found(REPLIES, person, [r.id for r in records], len(records), str(records[0].data["text"]), person)
        for person, records in by_person.items()
        if len(records) >= needed
    ]
    return sorted(found, key=lambda f: (-f.count, f.subject))


def all_found(store: Any, cfg: Any) -> list[Found]:
    """Every pattern found, by kind: moved to-dos, re-dated promises, then replies owed."""
    return [*moved_todos(store, cfg), *redated_promises(store, cfg), *owed_replies(store, cfg)]


# ---- what a keep or a snooze marks ----


@dataclass(frozen=True)
class Mark:
    """When the person last said they were still doing a to-do (`at`) and, for a snooze, until when it stays away."""

    at: datetime
    until: datetime | None = None


def _moment(stamp: Any) -> datetime | None:
    if isinstance(stamp, datetime):
        found = stamp
    else:
        try:
            found = datetime.fromisoformat(str(stamp))
        except (TypeError, ValueError):
            return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def _said(signal: Any) -> dict[str, Any] | None:
    if signal.data["kind"] != "suggestion_chosen" or signal.data.get("note") in (None, TAKEN_BACK):
        return None
    try:
        said = json.loads(signal.data["note"])
    except (ValueError, TypeError):
        return None
    return said if isinstance(said, dict) else None


def marks(view: Any) -> dict[str, Mark]:
    """For each to-do the person kept or snoozed from a stale line and didn't take back: the latest such mark."""
    found: dict[str, Mark] = {}
    for signal in view.list("signal"):
        said = _said(signal)
        if said is None or said.get("choice") not in MARKS:
            continue
        at = _moment(signal.data["at"])
        if at is None:
            continue
        until = _moment(said["until"]) if said.get("until") else None
        for ref in signal.data.get("refs") or []:
            held = found.get(ref)
            if held is None or at >= held.at:
                found[ref] = Mark(at, until)
    return found


def stays_off(view: Any) -> dict[tuple[str, str], str]:
    """What the person chose to leave and hasn't taken back: (kind, line key) to the change key it had."""
    found: dict[tuple[str, str], str] = {}
    for signal in sorted(view.list("signal"), key=lambda s: int(s.id.rpartition("-")[2])):
        said = _said(signal)
        if said is not None and said.get("choice") in STAYS_OFF:
            found[(said["kind"], said["subject"])] = said["change"]
    return found


# ---- the choices ----


@dataclass(frozen=True)
class Chosen:
    """What a choice did: the signal it recorded and, when it changed records, the change (whose Undo is its undo)."""

    signal: str
    changeset: str | None = None


@dataclass(frozen=True)
class Words:
    """The wording a choice writes into a record, from the wording sheet: a reason for a drop, what a hold waits for
    and the phrase of a weekly repeat."""

    reason: str = ""
    waiting: str = ""
    weekly: str = ""


@dataclass
class Plan:
    """What one choice will do: the ops to apply as the person's own change, whether a drop in them is a correction
    of the assistant, and what the signal says."""

    ops: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    corrections: bool = False
    until: datetime | None = None


def _drops(ids: list[str], reason: str) -> list[dict[str, Any]]:
    if not reason.strip():
        raise StoreError("say why it is dropped")
    return [{"op": "action.drop", "id": i, "reason": reason.strip()} for i in ids]


def plan(store: Any, cfg: Any, line: Any, choice: str, words: Words, now: datetime) -> Plan:
    """The ops and the signal for a choice on a line, refused in plain words when the choice isn't one the line offers
    or the to-do has gone."""
    if choice not in (getattr(line, "choices", None) or ()):
        raise StoreError("that isn't one of the choices")
    view = store.read()
    ids = list(line.actions)
    for action in ids:
        found = view.get("action", action)
        if found is None or found.data.get("status") != "open":
            raise StoreError("that to-do is no longer open")
    if choice == "leave":
        return Plan()
    if choice == "keep":
        return Plan()
    if choice == "snooze":
        return Plan(until=now + timedelta(days=cfg.steward.patterns.snooze_days))
    if choice == "drop":
        return Plan(_drops(ids, words.reason), "Dropped a to-do from a suggestion")
    if choice == "no_reply":
        return Plan(_drops(ids, words.reason), "Said no reply is needed", corrections=True)
    if choice == "hold":
        if not words.waiting.strip():
            raise StoreError("say what it waits for")
        ops = [{"op": "action.hold", "id": i, "waiting_for": words.waiting.strip()} for i in ids]
        return Plan(ops, "Put a promise on hold from a suggestion")
    if choice == "weekly":
        return Plan([_weekly(store, cfg, ids[0], words.weekly, now)], "Made a to-do weekly from a suggestion")
    raise StoreError("that isn't one of the choices")


def _weekly(store: Any, cfg: Any, action: str, phrase: str, now: datetime) -> dict[str, Any]:
    from engine import repeats

    if not phrase.strip():
        raise StoreError("say how it repeats")
    today = repeats.local_today(store, cfg)
    record = store.read().get("action", action)
    # A to-do that has a day repeats from that day, however long ago it was; one without starts today.
    start = date.fromisoformat(str(record.data["due"])) if record.data.get("due") else None
    found = repeats.read_phrase(phrase.strip(), start, today)
    if found.status != "ok" or found.rule is None or found.start is None:
        raise StoreError(
            "that repeat isn't clear" if found.status == "unclear" else "the to-do's day isn't one of those days"
        )
    return {
        "op": "action.repeat",
        "id": action,
        "rule": found.rule,
        "phrase": phrase.strip(),
        "start": found.start.isoformat(),
    }


def choose(store: Any, cfg: Any, line: Any, choice: str, words: Words, now: datetime, key: Any = None) -> Chosen:
    """Do what a choice on a suggestion line says, at once, and record its signal. `key` is the line's change key."""
    from engine.applier import apply_as_person
    from engine.learn import record

    made = plan(store, cfg, line, choice, words, now)
    changeset = None
    if made.ops:
        changeset = apply_as_person(store, cfg, made.ops, made.summary, corrections=made.corrections)
    note = {
        "kind": line.kind,
        "subject": line.key,
        "change": key if key is not None else str(line.count),
        "choice": choice,
        "pattern": line.state if line.kind == "pattern" else line.kind,
    }
    if made.until is not None:
        note["until"] = made.until.astimezone(UTC).isoformat()
    data = {
        "kind": "suggestion_chosen",
        "refs": [*line.actions][:200],
        "changeset": changeset,
        "note": json.dumps(note),
        "at": now.astimezone(UTC).isoformat(),
    }
    with store.transaction() as tx:
        signal = record(tx, cfg, data, _CHOOSE, now)
    return Chosen(signal, changeset)


def undo(store: Any, signal_id: str) -> bool:
    """Take a choice back: the records it changed go back (its change's Undo), and its signal is marked as taken back,
    so a line it kept away shows again and a keep or snooze no longer counts. Returns whether there was one to take
    back."""
    from engine.dispatcher import undo_changeset

    found = store.read().get("signal", signal_id)
    if found is None or found.data["kind"] != "suggestion_chosen" or found.data.get("note") == TAKEN_BACK:
        return False
    changeset = found.data.get("changeset")
    if changeset:
        report = undo_changeset(store, changeset, None)
        if not report.restored:
            return False
    with store.transaction() as tx:
        tx.update(
            "signal",
            signal_id,
            {"note": TAKEN_BACK},
            WriteContext(actor="pm", trust="trusted", op="suggestion.take_back"),
            read_version=found.version,
        )
    return True
