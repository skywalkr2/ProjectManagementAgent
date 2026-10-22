"""People memory (design 6.32): what the records say about one person, worked out by rules, each part with the words or
the record it rests on.

- *Last in touch*: the latest mail from them, the latest mail the person sent them (read from the watched mail), the
  latest message the person copied to send them, or the latest entry they were on that has ended.
- *Open with them*: what they asked of the person (replies owed), what the person asked of them (open questions), and
  the promises both ways, each with the exact words it was made from.
- *How they like to be reached*: the ways kept on their record, and the one they last wrote from.
- *Their dates*: facts about them with a date word (a birthday) and the day it next falls on, and facts about them
  with a full date still ahead.
- *What matters to them*: the facts the person kept about them, newest first.

It also finds the promises that have gone quiet, which become a line on Today. A person's name in a fact is read by the
same rules every other screen uses; nothing here calls AI, and a record the person has not kept (an untrusted or
inferred fact) is never shown as something they said or care about. Reads only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from engine import entry_rules, promises
from engine.blocked import standing_hold
from engine.firm_due import firm_due
from engine.meeting_guests import guests, window
from engine.names import entry_parts

MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_FIRST = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b")
_DAY_FIRST = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?(?:,?\s+(\d{4}))?\b")


@dataclass(frozen=True)
class Item:
    """One thing open with a person. `kind`: promised_to (the person promised it to them), promised_by (they promised
    it to the person), asked_of (a question to them) or asked_by (a reply the person owes them). `record` is the kind
    of record it is (action or question) and `id` its id. `quote` is the exact words it was made from, when the record
    carries them, and `source` the input they came from. `quiet` is the days with no news (since it was made, or its
    latest news or chase); `since` that day."""

    kind: str
    record: str
    id: str
    text: str
    due: date | None = None
    quote: str | None = None
    source: str | None = None
    quiet: int = 0
    since: date | None = None


@dataclass(frozen=True)
class Touch:
    """The last contact with a person. `kind`: from (mail from them), to (mail or a copied message to them) or met (an
    entry they were on). `record_kind` and `record` name the record that shows it; `subject` is its title, outside
    text when `untrusted`."""

    kind: str
    on: date
    record_kind: str | None = None
    record: str | None = None
    subject: str | None = None
    untrusted: bool = False


@dataclass(frozen=True)
class Reach:
    """How a person likes to be reached: the ways kept on their record (`kept`, channel to address), and the channel of
    the mail they last wrote from (`replies_on`, a key of `kept`), shown with the input it was read from."""

    kept: dict[str, str] = field(default_factory=dict)
    replies_on: str | None = None
    replies_record: str | None = None


@dataclass(frozen=True)
class Dated:
    """A fact about a person that carries a date. `on` is the next day it falls on, none when no month and day could be
    read; `yearly` says it comes round every year."""

    fact: str
    text: str
    on: date | None
    yearly: bool
    quote: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Kept:
    """A fact the person kept about someone, with the day it was true as of."""

    fact: str
    text: str
    as_of: date | None = None
    quote: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Memory:
    """Everything the records say about one person, by part. A part with nothing in it is empty or none."""

    person: str
    name: str
    last_in_touch: Touch | None
    asked_of: list[Item]
    asked_by: list[Item]
    promised_to: list[Item]
    promised_by: list[Item]
    reach: Reach
    dates: list[Dated]
    matters: list[Kept]


@dataclass(frozen=True)
class Quiet:
    """A promise that has gone quiet: the open action, the `person` to follow up with, `direction` (to: the person
    promised it to them; from: they promised it to the person), its words and exact `quote`, its day, the `quiet` days
    with no news and the day they count from."""

    action: str
    person: str
    direction: str
    text: str
    quiet: int
    since: date
    due: date | None = None
    quote: str | None = None
    project: str | None = None


def local_day(value: Any, here: ZoneInfo) -> date | None:
    """The person's own day for a stored time (a stored time with no zone is UTC); none when it can't be read."""
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(here).date()


def _made_on(view: Any, kind: str, record_id: str, here: ZoneInfo) -> date | None:
    rows = view.ledger(kind=kind, record_id=record_id)
    return local_day(rows[0]["at"], here) if rows else None


def _heard(data: dict[str, Any]) -> list[date]:
    """The days an action had news, was told or was chased."""
    days = [date.fromisoformat(str(n["on"])) for n in data.get("news") or []]
    days += [date.fromisoformat(str(d)) for d in (data.get("told") or {}).values()]
    days += [date.fromisoformat(str(d)) for given in (data.get("followed_up") or {}).values() for d in given]
    return days


def action_item(view: Any, kind: str, record: Any, today: date, here: ZoneInfo) -> Item:
    d = record.data
    heard = _heard(d)
    since = max(heard, default=None) or _made_on(view, "action", record.id, here) or today
    evidence = d.get("evidence") or {}
    return Item(
        kind,
        "action",
        record.id,
        str(d["text"]),
        date.fromisoformat(str(d["due"])) if d.get("due") else None,
        evidence.get("quote"),
        d.get("source") or evidence.get("source"),
        max(0, (today - since).days),
        since,
    )


def _order(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (i.due is None, i.due or date.max, i.text.casefold(), i.id))


def open_with(view: Any, pm: str | None, person: str, today: date, here: ZoneInfo) -> dict[str, list[Item]]:
    """What is open between the person and one other, by `kind` (promised_to, promised_by, asked_of, asked_by): earliest
    day first, an item with none last. A promise someone else made to a third person is not between them."""
    found: dict[str, list[Item]] = {"promised_to": [], "promised_by": [], "asked_of": [], "asked_by": []}
    for record in view.list("action"):
        d = record.data
        if d.get("status") != "open":
            continue
        owners = {o.get("person") for o in d.get("owners") or []}
        promised = list(d.get("promised_to") or [])
        if d.get("reply_owed"):
            if d.get("asker") == person and pm in owners:
                found["asked_by"].append(action_item(view, "asked_by", record, today, here))
        elif pm in owners and person in promised:
            found["promised_to"].append(action_item(view, "promised_to", record, today, here))
        elif person in owners and pm not in owners and (pm in promised or not promised):
            found["promised_by"].append(action_item(view, "promised_by", record, today, here))
    for record in view.list("question"):
        d = record.data
        if d.get("to") == person and d.get("status") in ("open", "sent"):
            found["asked_of"].append(
                Item(
                    "asked_of",
                    "question",
                    record.id,
                    str(d["title"]),
                    None,
                    None,
                    d.get("source"),
                    0,
                    _made_on(view, "question", record.id, here),
                )
            )
    return {kind: _order(items) for kind, items in found.items()}


# ---- last in touch ----------------------------------------


def _sources_by_item(view: Any) -> dict[tuple[str, str], str]:
    """The latest input saved from each watched item, by the watched source and the item's key."""
    found: dict[tuple[str, str], str] = {}
    for source in sorted(view.list("source"), key=lambda s: (str(s.data["received_at"]), s.id)):
        watched = source.data.get("watched") or {}
        if watched.get("source") and watched.get("key"):
            found[(str(watched["source"]), str(watched["key"]))] = source.id
    return found


class _Matcher:
    """Whether a header entry (`Name <address>`) is one person, remembered so each entry is read once."""

    def __init__(self, people: Any):
        self.people = people
        self.known: dict[str, set[str]] = {}

    def of(self, entry: str) -> set[str]:
        if entry not in self.known:
            self.known[entry] = self.people.match_entries([entry])
        return self.known[entry]


def _mail_touches(
    view: Any, people: Any, pm: str | None, person: str, here: ZoneInfo
) -> list[tuple[Touch, str | None]]:
    """The mail the watched mailboxes hold from the person or sent to them by the person, each with the address of the
    sender when it is from them."""
    matcher = _Matcher(people)
    sources = None
    found: list[tuple[Touch, str | None]] = []
    for snap in view.list("snapshot"):
        message = snap.data.get("message")
        if not message or snap.data.get("gone") or snap.data.get("deleted"):
            continue
        sender = message.get("sender")
        day = local_day(message.get("received") or snap.data["seen_at"], here)
        if day is None or not sender:
            continue
        who = matcher.of(sender)
        kind = None
        if person in who:
            kind = "from"
        elif pm is not None and pm in who and any(person in matcher.of(p) for p in message.get("participants") or []):
            kind = "to"
        if kind is None:
            continue
        if sources is None:
            sources = _sources_by_item(view)
        record = sources.get((str(snap.data["source"]), str(snap.data["key"])))
        found.append(
            (
                Touch(kind, day, "source" if record else "snapshot", record or snap.id, snap.data["title"], True),
                sender if kind == "from" else None,
            )
        )
    return found


def last_in_touch(view: Any, cfg: Any, people: Any, person: str, now: datetime) -> tuple[Touch | None, str | None]:
    """The latest contact with a person (mail from them, mail or a copied message to them, an entry they were on that
    has ended), with the address they last wrote from. A later day wins; on one day, mail from them over mail to them
    over an entry."""
    from engine.today import zone

    here = zone(cfg)
    pm = cfg.workspace.user.person
    touches = _mail_touches(view, people, pm, person, here)
    for copy in view.list("copy"):
        day = local_day(copy.data["at"], here) if copy.data.get("person") == person else None
        if day is not None:
            touches.append((Touch("to", day, "copy", copy.id, None), None))
    mine = entry_rules.identity(view, cfg)
    for entry in view.list("event"):
        spans = window(entry.data, here)
        if spans is None or spans[1] > now or entry.data.get("cancelled"):
            continue
        if any(g.person == person for g in guests(view, cfg, entry.data, mine=mine)):
            touches.append(
                (
                    Touch(
                        "met",
                        spans[1].astimezone(here).date(),
                        "event",
                        entry.id,
                        entry.data["title"],
                        entry.data.get("trust") == "untrusted",
                    ),
                    None,
                )
            )
    if not touches:
        return None, None
    order = {"from": 0, "to": 1, "met": 2}
    best = max(touches, key=lambda t: (t[0].on, -order[t[0].kind], t[0].record or ""))[0]
    latest = max((t for t in touches if t[0].kind == "from"), key=lambda t: (t[0].on, t[0].record or ""), default=None)
    return best, latest[1] if latest else None


def reach_of(view: Any, person: Any, written_from: str | None, written_record: str | None) -> Reach:
    """The ways kept on a person's record, and the one they last wrote from: the channel whose address is the one the
    latest mail from them came from."""
    kept = {str(k): str(v) for k, v in (person.data.get("how_to_reach") or {}).items()}
    address = entry_parts(written_from)[1].strip().casefold() if written_from else ""
    channel = next((k for k, v in sorted(kept.items()) if address and v.strip().casefold() == address), None)
    return Reach(kept, channel, written_record if channel else None)


# ---- dates and what matters ----------------------------------------


def _month_day(text: str) -> tuple[int, int, int | None] | None:
    """A month, a day and perhaps a year written in a text: an ISO date, "March 3 (2026)" or "3 March (2026)"."""
    found = _ISO.search(text)
    if found:
        return int(found.group(2)), int(found.group(3)), int(found.group(1))
    for pattern, month_at, day_at in ((_MONTH_FIRST, 1, 2), (_DAY_FIRST, 2, 1)):
        for match in pattern.finditer(text):
            month = MONTHS.get(match.group(month_at).casefold())
            day = int(match.group(day_at))
            if month and 1 <= day <= 31:
                return month, day, int(match.group(3)) if match.group(3) else None
    return None


def _next_on(month: int, day: int, today: date) -> date | None:
    for year in range(today.year, today.year + 9):
        try:
            found = date(year, month, day)
        except ValueError:
            continue
        if found >= today:
            return found
    return None


def facts_about(view: Any, people: Any, person: str, cfg: Any, today: date) -> tuple[list[Dated], list[Kept]]:
    """The facts the person kept that name this person, split into their dates and what matters to them. A fact the
    assistant only inferred, one from outside content, one someone else said and one that a newer fact replaced are
    left out."""
    from engine.today import zone

    rules = cfg.steward.people
    words = [w.casefold() for w in rules.date_words if w.strip()]
    facts = view.list("fact")
    replaced = {f.data["supersedes"] for f in facts if f.data.get("supersedes")}
    dates: list[Dated] = []
    kept: list[Kept] = []
    here = zone(cfg)
    for fact in facts:
        d = fact.data
        if fact.id in replaced or d.get("trust") == "untrusted" or d.get("basis") not in (None, "person"):
            continue
        if person not in people.mentioned_in(str(d["text"])):
            continue
        evidence = d.get("evidence") or {}
        text = str(d["text"])
        shared = {"quote": evidence.get("quote"), "source": d.get("source") or evidence.get("source")}
        parsed = _month_day(text)
        if parsed is not None and any(w in text.casefold() for w in words):
            dates.append(Dated(fact.id, text, _next_on(parsed[0], parsed[1], today), True, **shared))
        elif any(w in text.casefold() for w in words):
            dates.append(Dated(fact.id, text, None, True, **shared))
        elif parsed is not None and parsed[2] is not None:
            try:
                once = date(parsed[2], parsed[0], parsed[1])
            except ValueError:
                once = None
            if once is not None and once >= today:
                dates.append(Dated(fact.id, text, once, False, **shared))
                continue
            kept.append(Kept(fact.id, text, _as_of(d, view, fact.id, here), **shared))
        else:
            kept.append(Kept(fact.id, text, _as_of(d, view, fact.id, here), **shared))
    dates.sort(key=lambda x: (x.on is None, x.on or date.max, x.text.casefold(), x.fact))
    kept.sort(key=lambda x: (x.as_of or date.min, x.fact), reverse=True)
    return dates[: rules.max_facts], kept[: rules.max_facts]


def _as_of(data: dict[str, Any], view: Any, fact_id: str, here: ZoneInfo) -> date | None:
    if data.get("as_of"):
        return date.fromisoformat(str(data["as_of"]))
    return _made_on(view, "fact", fact_id, here)


# ---- the whole page ----------------------------------------


def memory(store: Any, cfg: Any, person_id: str, now: datetime) -> Memory | None:
    """What the records say about one person, or None when there is no such person."""
    from engine.names import People
    from engine.today import zone

    view = store.read()
    record = view.get("person", person_id, include_deleted=True)
    if record is None:
        return None
    people = People(store, cfg)
    here = zone(cfg)
    today = now.astimezone(here).date()
    items = open_with(view, cfg.workspace.user.person, person_id, today, here)
    touch, written_from = last_in_touch(view, cfg, people, person_id, now)
    record_for_touch = touch.record if touch is not None and touch.kind == "from" else None
    dates, matters = facts_about(view, people, person_id, cfg, today)
    return Memory(
        person_id,
        str(record.data["full_name"]),
        touch,
        items["asked_of"],
        items["asked_by"],
        items["promised_to"],
        items["promised_by"],
        reach_of(view, record, written_from, record_for_touch),
        dates,
        matters,
    )


# ---- promises gone quiet ----------------------------------------


def quiet_promises(
    store: Any,
    cfg: Any,
    today: date,
    *,
    skip: set[str] | frozenset[str] = frozenset(),
    hidden: frozenset[str] | set[str] = frozenset(),
) -> list[Quiet]:
    """The open promises to or from someone that have had no news for `steward.people.quiet_promise_days`, longest quiet
    first. The days count from when it was made or from its latest news, chase or notice. Left out: an action in `skip`
    (it already has a line), one on hold or with an ending waiting for the person's Keep, a reply owed (it has its own
    line), one of the person's own past its day (the overdue line has it), a promise someone made to a third person,
    and a promise from someone the person reports to or only watches, who is waited on and never chased. Nothing is
    shown when the setting is zero."""
    from engine.names import People
    from engine.scope import stance_of
    from engine.today import zone

    wait = cfg.steward.people.quiet_promise_days
    pm = cfg.workspace.user.person
    if wait <= 0 or pm is None:
        return []
    view = store.read()
    here = zone(cfg)
    people = People(store, cfg)
    pending = promises.pending_endings(view, hidden)
    found: list[Quiet] = []
    for record in view.list("action"):
        d = record.data
        if d.get("status") != "open" or d.get("reply_owed") or record.id in skip or record.id in pending:
            continue
        if not promises.is_promise(d) or standing_hold(view, d, people, here, pm):
            continue
        owners = [o["person"] for o in d.get("owners") or [] if o.get("person")]
        promised = [p for p in d.get("promised_to") or [] if p != pm]
        if pm in owners:
            due = firm_due(d)
            if not promised or (due is not None and due < today):
                continue  # a promise past its day is on the overdue line already
            who, direction = promised[0], "to"
        else:
            if not owners or (d.get("promised_to") and pm not in d["promised_to"]):
                continue
            who, direction = owners[0], "from"
            if stance_of(view, cfg.steward, who) in ("report_to", "watch"):
                continue
        recent = max(_heard(d), default=None)
        if recent is not None and (today - recent).days < wait:
            continue
        since = max(recent or date.min, _made_on(view, "action", record.id, here) or date.min)
        if since == date.min:
            continue
        quiet = (today - since).days
        if quiet < wait:
            continue
        due = date.fromisoformat(str(d["due"])) if d.get("due") else None
        evidence = d.get("evidence") or {}
        found.append(
            Quiet(record.id, who, direction, str(d["text"]), quiet, since, due, evidence.get("quote"), d.get("project"))
        )
    return sorted(found, key=lambda q: (-q.quiet, q.action))
