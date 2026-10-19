"""Replies owed (design 6.32, 6.35): which messages ask the person something nobody has answered, the Today line for
each open one, and the endings the rules take on their own.

A reply owed is an action with `reply_owed`, `replies_to` (the message's source) and `asker` (the person it is to). The
rules in `engine.replies_owed` decide, from the message's own headers and new text, whether a reply is owed at all; the
applier asks them before it makes the action. A message the person sent to the asker on the same conversation after the
ask ends it at once, as the person's own act: the change is `action.close` through the applier with the sent message as
its evidence. Everything else here reads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any

from engine.automatic_mail import classify_automatic
from engine.mail_threads import ThreadCandidate, normalize_subject, thread_key
from engine.replies_owed import Address, Message, reply_owed
from engine.reply_split import split_message

#: What the rules say that means no reply is owed. Anything else (a question for someone else, a request phrased
#: without a question, a waiting period) is left to the reading step, never refused here.
NO_REPLY = ("automatic", "sent_by_you", "no_reply_needed")
#: What the change that ends a reply owed records as the rule that made it, so a list of what was done without the
#: person can say a rule did it.
ANSWERED_RULE = "reply_answered"
_HEADER = re.compile(r"^([A-Za-z][A-Za-z-]*):[ \t]*(.*)$")
_WRAPPERS = ("New in ", "Changed in ")
#: Where a reply owed whose message is gone sorts: first, as the one waiting longest.
UNDATED = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Read:
    """A message as its saved text and details give it: who sent it, to whom (`to`, `cc`), when, what it is about, and
    its new text with the quoted history and signature taken off."""

    sender: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    subject: str
    received: datetime | None
    body: str
    new_text: str


def _body_of(text: str) -> str:
    """The message itself inside what a watcher handed in: its text after the line that says it is new, or after the
    words that say what it now reads for a changed one."""
    marker = "\nIt now reads:\n"
    if text.startswith("Changed in ") and marker in text:
        return text.split(marker, 1)[1]
    if text.startswith(_WRAPPERS):
        head, _, rest = text.partition("\n\n")
        return rest if head.strip() else text
    return text


def read_message(text: str, received: datetime | None = None) -> Read | None:
    """The message a text is, when it starts with mail header lines (From and To at least); None for anything else.
    `received` is when it came, used when the headers give no readable date."""
    lines = _body_of(text).lstrip("\n").splitlines()
    headers: dict[str, str] = {}
    current: str | None = None
    used = 0
    for line in lines:
        used += 1
        if not line.strip():
            break
        if line[0] in " \t":
            if current is not None:
                headers[current] += " " + line.strip()
            continue
        found = _HEADER.match(line)
        if found is None:
            return None
        current = found.group(1).lower()
        headers[current] = (headers.get(current, "") + " " + found.group(2).strip()).strip()
    if not headers.get("from") or not headers.get("to"):
        return None
    body = "\n".join(lines[used:])
    when = received
    if headers.get("date"):
        try:
            when = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError, IndexError):
            when = received
    if when is not None and when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return Read(
        sender=headers["from"],
        to=_entries(headers["to"]),
        cc=_entries(headers.get("cc", "")),
        subject=" ".join(headers.get("subject", "").split()),
        received=when,
        body=body,
        new_text=split_message(body).new,
    )


def _entries(value: str) -> tuple[str, ...]:
    return tuple(
        f"{name} <{address}>" if name else address
        for name, address in getaddresses([value])
        if address and address.count("@") == 1
    )


def _address(entry: str) -> Address | None:
    name, address = parseaddr(entry)
    return Address(address, name or None) if address.count("@") == 1 else None


def addresses_of(entries: tuple[str, ...]) -> tuple[Address, ...]:
    return tuple(a for a in map(_address, entries) if a is not None)


def my_addresses(view: Any, cfg: Any) -> list[Address]:
    """The addresses the person writes from: those their own record holds, and any of the names they sign in under that
    are addresses."""
    found: dict[str, Address] = {}
    person = view.get("person", cfg.workspace.user.person) if cfg.workspace.user.person else None
    values = list((person.data.get("how_to_reach") or {}).values()) if person is not None else []
    for value in [*values, *cfg.workspace.user.accounts]:
        parsed = _address(str(value))
        if parsed is not None:
            found.setdefault(parsed.email.casefold(), parsed)
    return list(found.values())


def _message(read: Read, bulk: bool, subject: str) -> Message | None:
    sender = _address(read.sender)
    if sender is None or read.received is None:
        return None
    automatic = bulk or classify_automatic({}, subject, "text/plain").kind != "none"
    return Message(read.new_text, sender, addresses_of(read.to), addresses_of(read.cc), read.received, automatic)


def refusal(view: Any, cfg: Any, text: str, received: datetime | None, bulk: bool = False) -> str | None:
    """Why no reply is owed for the message in `text`, in plain words, when the rules say so for certain: automatic
    mail, mail the person sent, or a message that says no reply is needed. None when a reply may be owed, and when the
    headers can't be read (the model's reading stands)."""
    read = read_message(text, received)
    mine = my_addresses(view, cfg)
    if read is None or not mine:
        return None
    message = _message(read, bulk, read.subject)
    if message is None:
        return None
    found = reply_owed(message, mine, (), message.received, 0)
    return (
        f"no reply is owed to this message: {found.reason[:1].lower()}{found.reason[1:]}"
        if found.code in NO_REPLY
        else None
    )


def asker_of(people: Any, text: str) -> str | None:
    """The one known person a message is from, by the address or name on its From line; None when it is nobody known."""
    read = read_message(text)
    if read is None:
        return None
    found = people.match_entries([read.sender])
    return next(iter(found)) if len(found) == 1 else None


# ---- the line on Today -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Owed:
    """An open reply owed: its `action`, the `text` of the action, who it is to (`asker`, a person id, or `sender`, the
    name as written when that is nobody known), the message's `subject` and when it came (`received`, in UTC), and the
    drafted `reply` with whether the person has `reviewed` it."""

    action: str
    text: str
    project: str | None
    asker: str | None
    sender: str | None
    subject: str
    received: datetime
    reply: str | None
    reviewed: bool


def _read_source(ws: Any, source: Any) -> str:
    path = ws.sources_dir / f"{source.data['content_hash']}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _stamp(value: Any) -> datetime:
    at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(UTC)


def plan(ws: Any, reader: Any) -> list[Owed]:
    """The open replies owed, oldest message first: actions marked as a reply owed that are open and not on hold."""
    found: list[Owed] = []
    for action in reader.list("action"):
        d = action.data
        if not d.get("reply_owed") or d.get("status") != "open" or d.get("on_hold"):
            continue
        source = reader.get("source", d["replies_to"]) if d.get("replies_to") else None
        read = read_message(_read_source(ws, source), None) if source is not None else None
        subject = (read.subject if read is not None else "") or (source.data["title"] if source is not None else "")
        received = _stamp(source.data["received_at"]) if source is not None else UNDATED
        sender = None
        if read is not None and not d.get("asker"):
            name, address = parseaddr(read.sender)
            sender = name or address or None
        found.append(
            Owed(
                action.id,
                str(d["text"]),
                d.get("project"),
                d.get("asker"),
                sender,
                normalize_subject(subject) or subject,
                received,
                d.get("reply"),
                bool(d.get("reply_reviewed")),
            )
        )
    return sorted(found, key=lambda x: (x.received, x.action))


# ---- the ending the rules take: the person's own sent mail -----------------------------------------------------------


def _bare(entries: tuple[str, ...]) -> set[str]:
    return {a.email.casefold() for a in addresses_of(entries)}


def _thread(ask: Read, ask_key: str, sent: Read, sent_key: str, days: int) -> bool:
    """Whether two messages are one conversation: by their headers when they carry them, else the same subject with a
    person in common within `days`. Both sides are the same call to `thread_key`, so one rule decides."""
    people_ask = sorted(_bare((ask.sender, *ask.to, *ask.cc)))
    people_sent = sorted(_bare((sent.sender, *sent.to, *sent.cc)))
    if ask.received is None or sent.received is None or not people_ask or not people_sent:
        return False
    candidate = ThreadCandidate("ask", ask.subject, tuple(people_ask), ask.received, ask_key)
    try:
        key = thread_key(
            sent_key,
            None,
            None,
            sent.subject,
            people_sent,
            received=sent.received,
            candidates=[candidate],
            max_days=days,
        )
    except ValueError:
        return False
    return key == "ask"


def _quote_of(sent: Read) -> str:
    """The words of the sent message to cite: its first line of new text, or its subject line."""
    for line in sent.new_text.splitlines():
        if len(line.strip()) >= 3:
            return line.strip()[:200]
    return f"Subject: {sent.subject}"


def answered_by_sent(ws: Any, store: Any, cfg: Any, owed: Owed, ask: Any, sent_sources: list[Any]) -> Any | None:
    """The person's sent message that answers this reply owed, when there is one: it is on the same conversation, to the
    asker, and after the ask. Returns the source record, else None."""
    if owed.asker is None:
        return None
    person = store.read().get("person", owed.asker)
    asker_addresses = {a.email.casefold() for a in map(_address, (person.data.get("how_to_reach") or {}).values()) if a}
    asked = read_message(_read_source(ws, ask), _stamp(ask.data["received_at"]))
    if asked is None or not asker_addresses:
        return None
    ask_key = ((ask.data.get("watched") or {}).get("key")) or ask.id
    for source in sent_sources:
        sent = read_message(_read_source(ws, source), _stamp(source.data.get("sent_at") or source.data["received_at"]))
        if sent is None or sent.received is None or sent.received <= asked.received:
            continue
        if not asker_addresses & _bare(sent.to):
            continue
        key = ((source.data.get("watched") or {}).get("key")) or source.id
        if _thread(asked, str(ask_key), sent, str(key), cfg.steward.reply_thread_days):
            return source
    return None


def close_answered(ws: Any, store: Any, cfg: Any, now: datetime | None = None) -> list[str]:
    """End every open reply owed that the person's own sent mail has answered, as their own act: `action.close`,
    credited to the person, with the sent message's words as the evidence. Idempotent: what is closed is not looked at
    again. Returns the changesets made."""
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET
    from engine.storage import WriteContext

    view = store.read()
    waiting = plan(ws, view)
    if not waiting:
        return []
    mine = [
        s
        for s in view.list("source")
        if (s.data.get("watched") or {}).get("by_you") and str(s.data.get("kind", "")).startswith("watched:")
    ]
    made: list[str] = []
    for owed in waiting:
        ask = view.get("source", view.get("action", owed.action).data.get("replies_to") or "")
        if ask is None:
            continue
        source = answered_by_sent(ws, store, cfg, owed, ask, mine)
        if source is None:
            continue
        text = _read_source(ws, source)
        sent = read_message(text, _stamp(source.data["received_at"]))
        assert sent is not None
        quote = _quote_of(sent)
        op = {"op": "action.close", "id": owed.action, "evidence": {"quote": quote}}
        summary = "Closed a reply owed: you answered it"
        changeset = CHANGESET.validate_python(
            {"summary": summary, "ops": [op]}, context={"op_models": store.plugins.ops}
        )
        with store.transaction() as tx:
            request = tx.create(
                "request",
                {
                    "task": "notes",
                    "origin": "input",
                    "state": "done",
                    "source": source.id,
                    "note": summary,
                    "created_at": store.clock(),
                },
                WriteContext("engine", "trusted", "reply.ended"),
            )
        people = People(store, cfg)
        ctx = Context(
            store,
            cfg,
            people,
            ("action.close",),
            Inputs(request.id, source.id, text, "", "untrusted"),
            reporter=people.pm,
        )
        cs_id = apply_changeset(changeset, [], ctx, run=None, now=now, extra={"by_rule": ANSWERED_RULE})
        with store.transaction() as tx:
            current = tx.get("request", request.id)
            tx.update(
                "request",
                request.id,
                {"changeset": cs_id},
                WriteContext("engine", "trusted", "reply.ended"),
                read_version=current.version,
            )
        view = store.read()
        made.append(cs_id)
    return made
