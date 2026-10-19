"""Learning from the sent version (design 6.35): what the person copied, matched to what they then sent.

Each time a follow-up is marked as sent or a drafted reply is copied, a `copy` record keeps the text exactly as copied,
who it was for, when, and the questions and actions it covered. When the sent folder's mail is taken in, each sent
message is matched, by rules alone, to the newest copy not yet matched that was for the same recipient, was copied no
more than `steward.sent_match.window_days` before it, and is at least `steward.sent_match.similarity` like it. A matched
pair whose texts differ is a `draft_edited` signal carrying the sent text, exactly as an edit made in the app is, so
what the assistant learns reaches it by the same path. A copy that stays unmatched for
`steward.sent_match.ask_after_days` becomes one Today line asking whether it went out, only while a sent folder is
being read. Nothing here calls AI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from engine import learn
from engine.cleaning import normalize
from engine.reply_lines import _address, _bare, _read_source, _stamp, read_message
from engine.storage import WriteContext

_COPY = WriteContext(actor="pm", trust="trusted", op="copy")
_MATCH = WriteContext(actor="pm", trust="trusted", op="copy.match")
_SIGNAL = WriteContext(actor="pm", trust="trusted", op="draft_edited")

#: The answers the person gives to "Did your message go out?".
ANSWERS = ("sent_another_way", "not_sent", "still_to_send")


def alike(a: str, b: str) -> float:
    """How alike two messages are, from 0 to 1: the share of their words they have in common. It is the measure the
    applier uses for near-duplicates."""
    from engine.applier import _similar

    return _similar(a, b)


# ---- keeping a copy --------------------------------------------------------------------------------------------------


def record_copy(
    store: Any,
    kind: str,
    person: str | None,
    text: str,
    *,
    questions: list[str] | tuple[str, ...] = (),
    actions: list[str] | tuple[str, ...] = (),
    now: datetime | None = None,
) -> str:
    """Keep a message the person copied, exactly as copied. Copying the same message again (same kind, person, covered
    items and words, not yet matched or settled) moves that copy forward instead of keeping a second. Returns its id."""
    stamp = (now or datetime.now(UTC)).isoformat()
    with store.transaction() as tx:
        for found in tx.list("copy"):
            d = found.data
            if (
                d["kind"] == kind
                and d.get("person") == person
                and not d.get("sent_source")
                and not d.get("settled")
                and set(d["questions"]) == set(questions)
                and set(d["actions"]) == set(actions)
                and normalize(d["text"]) == normalize(text)
            ):
                tx.update("copy", found.id, {"at": stamp, "ask_again_at": None}, _COPY, read_version=found.version)
                return found.id
        return tx.create(
            "copy",
            {
                "kind": kind,
                "person": person,
                "text": text,
                "at": stamp,
                "questions": list(questions),
                "actions": list(actions),
            },
            _COPY,
        ).id


def forget_copy(store: Any, person: str, question_ids: list[str], action_ids: list[str]) -> None:
    """Take back the copy a follow-up marked as sent made, when the person undoes the mark: the message covering exactly
    these questions and actions, if it has not been matched to a sent message."""
    with store.transaction() as tx:
        for found in tx.list("copy"):
            d = found.data
            if (
                d["kind"] == "follow_up"
                and d.get("person") == person
                and not d.get("sent_source")
                and set(d["questions"]) == set(question_ids)
                and set(d["actions"]) == set(action_ids)
            ):
                tx.delete("copy", found.id, _COPY, read_version=found.version)


# ---- matching the sent folder ----------------------------------------------------------------------------------------


def _sent_sources(view: Any) -> list[Any]:
    return [
        s
        for s in view.list("source")
        if (s.data.get("watched") or {}).get("by_you") and str(s.data.get("kind", "")).startswith("watched:")
    ]


def _when(source: Any) -> datetime:
    return _stamp(source.data.get("sent_at") or source.data["received_at"])


def _addresses_of(view: Any, person: str) -> set[str]:
    record = view.get("person", person)
    if record is None:
        return set()
    return {a.email.casefold() for a in map(_address, (record.data.get("how_to_reach") or {}).values()) if a}


def match_sent(ws: Any, store: Any, cfg: Any, now: datetime | None = None) -> list[str]:
    """Match each message in the sent folder that has no copy yet to its copy, oldest message first, and record what the
    person changed. A sent message takes the newest copy not yet matched that was for the same recipient, was copied
    before it and no more than the window earlier, and is alike enough; a copy takes one message and a message one copy.
    Idempotent. Returns the ids of the copies matched."""
    now = now or datetime.now(UTC)
    view = store.read()
    settings = cfg.steward.sent_match
    open_copies = [
        c
        for c in view.list("copy")
        if not c.data.get("sent_source") and not c.data.get("settled") and c.data.get("person")
    ]
    if not open_copies:
        return []
    earliest = min(_stamp(c.data["at"]) for c in open_copies)
    used = {c.data["sent_source"] for c in view.list("copy") if c.data.get("sent_source")}
    window = timedelta(days=settings.window_days)
    messages = sorted(
        (s for s in _sent_sources(view) if s.id not in used and _when(s) >= earliest), key=lambda s: (_when(s), s.id)
    )
    made: list[str] = []
    people: dict[str, set[str]] = {}
    for source in messages:
        sent = read_message(_read_source(ws, source), _when(source))
        if sent is None or sent.received is None:
            continue
        to = _bare(sent.to)
        best = None
        for copy in open_copies:
            d = copy.data
            copied = _stamp(d["at"])
            if not copied <= sent.received <= copied + window:
                continue
            if not people.setdefault(d["person"], _addresses_of(view, d["person"])) & to:
                continue
            if alike(d["text"], sent.new_text) < settings.similarity:
                continue
            if best is None or copied > _stamp(best.data["at"]):
                best = copy
        if best is None:
            continue
        open_copies.remove(best)
        _record_match(store, cfg, best, source, sent.new_text, now)
        made.append(best.id)
    return made


def _record_match(store: Any, cfg: Any, copy: Any, source: Any, sent_text: str, now: datetime) -> None:
    """The copy is matched to the sent message; when their words differ, the difference is a `draft_edited` signal with
    the sent text, written in the same change so a match is never half recorded."""
    from engine.followups import _written_by

    d = copy.data
    changeset, run = (
        _written_by(store, d["questions"]) if d["questions"] else _written_by(store, d["actions"], kind="action")
    )
    with store.transaction() as tx:
        current = tx.get("copy", copy.id)
        tx.update(
            "copy",
            copy.id,
            {"sent_source": source.id, "matched_at": now.isoformat()},
            _MATCH,
            read_version=current.version,
        )
        if normalize(sent_text) != normalize(d["text"]):
            learn.record(
                tx,
                cfg,
                {
                    "kind": "draft_edited",
                    "refs": [d["person"], *d["questions"], *d["actions"], copy.id],
                    "changeset": changeset,
                    "run": run,
                    "note": sent_text,
                    "at": now.isoformat(),
                },
                _SIGNAL,
                now,
            )


# ---- a copy no sent message matched ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Unsent:
    """A copy the person was asked about: its id, who it was for, when it was copied, and what it covered."""

    copy: str
    kind: str
    person: str
    at: datetime
    questions: list[str]
    actions: list[str]


def sent_folder_read(view: Any, cfg: Any) -> bool:
    """Whether a sent folder is being read: a source that is switched on in the watch settings has handed in mail the
    person sent."""
    enabled = {s.id for s in cfg.watch.sources if s.enabled}
    return any((s.data.get("watched") or {}).get("source") in enabled for s in _sent_sources(view))


def unsent(view: Any, cfg: Any, now: datetime) -> list[Unsent]:
    """The copies to ask about, oldest first: not matched or settled, copied at least `ask_after_days` ago (or since the
    person said Still to send), for a known person, and, for a reply, one still owed. Nothing at all unless a sent
    folder is being read."""
    if not sent_folder_read(view, cfg):
        return []
    wait = timedelta(days=cfg.steward.sent_match.ask_after_days)
    found: list[Unsent] = []
    for copy in view.list("copy"):
        d = copy.data
        if d.get("sent_source") or d.get("settled") or not d.get("person"):
            continue
        copied = _stamp(d["at"])
        due = _stamp(d["ask_again_at"]) if d.get("ask_again_at") else copied + wait
        if due > now:
            continue
        if d["kind"] == "reply":
            owed = [view.get("action", a) for a in d["actions"]]
            if not any(a is not None and a.data.get("status") == "open" and a.data.get("reply_owed") for a in owed):
                continue
        found.append(Unsent(copy.id, d["kind"], d["person"], copied, list(d["questions"]), list(d["actions"])))
    return sorted(found, key=lambda x: (x.at, x.copy))


class CopyError(ValueError):
    """An answer that can't be recorded; the message says why in plain words."""


def settle(store: Any, cfg: Any, copy_id: str, how: str, now: datetime | None = None) -> dict[str, Any]:
    """The person's answer to "Did your message go out?": sent another way (settled), not sent (the questions are open
    again and the person is no longer marked as told) or still to send (asked again after the same number of days).
    Returns what `unsettle` takes to put everything back."""
    from engine import followups

    if how not in ANSWERS:
        raise CopyError(f"{how} isn't an answer")
    now = now or datetime.now(UTC)
    view = store.read()
    found = view.get("copy", copy_id)
    if found is None:
        raise CopyError(f"copy {copy_id} doesn't exist")
    d = found.data
    previous: dict[str, Any] = {
        "settled": d.get("settled"),
        "ask_again_at": d.get("ask_again_at"),
        "sent_at": {},
        "told": {},
    }
    changes: dict[str, Any]
    if how == "sent_another_way":
        changes = {"settled": "sent_another_way"}
    elif how == "still_to_send":
        changes = {"ask_again_at": (now + timedelta(days=cfg.steward.sent_match.ask_after_days)).isoformat()}
    else:
        changes = {"settled": "not_sent"}
        for qid in d["questions"]:
            q = view.get("question", qid)
            if q is not None and q.data["status"] == "sent":
                previous["sent_at"][qid] = q.data.get("sent_at")
        for aid in d["actions"]:
            a = view.get("action", aid)
            if a is not None and d.get("person") in (a.data.get("told") or {}):
                previous["told"][aid] = a.data["told"][d["person"]]
        if d.get("person"):
            followups.unmark_sent(store, d["person"], d["questions"], d["actions"], forget_copy=False)
    with store.transaction() as tx:
        current = tx.get("copy", copy_id)
        tx.update("copy", copy_id, changes, _COPY, read_version=current.version)
    return previous


def unsettle(store: Any, copy_id: str, previous: dict[str, Any]) -> None:
    """Take an answer back: the copy is as it was, and a "Not sent" is undone by marking the questions as sent again, as
    they were, and the person as told."""
    found = store.read().get("copy", copy_id)
    if found is None:
        raise CopyError(f"copy {copy_id} doesn't exist")
    person = found.data.get("person")
    with store.transaction() as tx:
        tx.update(
            "copy",
            copy_id,
            {"settled": previous.get("settled"), "ask_again_at": previous.get("ask_again_at")},
            _COPY,
            read_version=tx.get("copy", copy_id).version,
        )
        for qid, sent_at in (previous.get("sent_at") or {}).items():
            q = tx.get("question", qid)
            if q is not None and q.data["status"] == "open":
                tx.update("question", qid, {"status": "sent", "sent_at": sent_at}, _COPY, read_version=q.version)
        for aid, day in (previous.get("told") or {}).items():
            a = tx.get("action", aid)
            if a is not None and person and person not in (a.data.get("told") or {}):
                told = {**(a.data.get("told") or {}), person: day}
                tx.update("action", aid, {"told": told}, _COPY, read_version=a.version)
