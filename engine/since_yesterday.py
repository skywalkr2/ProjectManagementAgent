"""What changed since yesterday (design 6.32, 6.35): everything the assistant or a rule did to the person's records
since the start of the previous day on their clock, or since they last opened this list when that is later, newest
first.

One entry for each record, the newest thing done to it:

- what was done (added, closed, moved, merged, dropped, set aside, news heard), the record's words, and the reason in
  the words the assistant gave, with the exact quote it rested on and who said it;
- whether the person has seen it: a close follows the silent-close rule (`engine.closes`), anything else is seen once
  the person has looked the change over;
- where its Undo is: an op of a change, a rule's close taken a closer look at, or mail put back from the Set aside
  folder.

Not listed: changes the person made themselves (their notes, screens and person actions), held items (they have their
own lines) and ops the person released from held. A change made by the engine's own rules says so (`because`).
Nothing here calls AI; reading the list writes nothing. `mark_seen` writes the person's one small `look` record, which
records the moment the list was last drawn and opened, and only ever moves forward."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal

from engine import closes
from engine.reply_lines import ANSWERED_RULE as RULE_REPLIED
from engine.storage import WriteContext
from engine.titles import head_of, title_for
from engine.today import zone

Act = Literal["added", "closed", "moved", "merged", "dropped", "set_aside", "news"]
Because = Literal["said", "rule", "sorting", "replied", "meeting"]
UndoKind = Literal["changeset", "closer_look", "set_aside"]

#: The acts in the order a count is read ("3 closed, 2 moved, 4 new").
ACTS: tuple[str, ...] = ("closed", "moved", "added", "merged", "dropped", "set_aside", "news")

#: The ops that make an entry, with the act each is.
_ACT_OF: dict[str, Act] = {
    "action.add": "added",
    "action.close": "closed",
    "action.drop": "dropped",
    "action.move": "moved",
    "action.part": "news",
    "action.news": "news",
    "question.drop": "dropped",
    "question.done": "closed",
}
#: The ops whose closes are read by the silent-close rule.
_CLOSING = frozenset(closes.CLOSING_OPS)
_LOOK = WriteContext(actor="pm", trust="trusted", op="since.look")
_QUOTE_LIMIT = 240


@dataclass(frozen=True)
class Entry:
    """One thing done since yesterday. `ref` is stable and names it. `record` is the person's record it is about, when
    it has one the screens open (an action or a question). `quote` is the exact words it rested on, `said_by` the person
    who said them (an id, when they are a known person) and `said_by_name` their name, or the sender as written when
    that isn't a known person; `by_you` when it was the person themselves. `because` says how it came about: said in
    an input, closed by a triage rule, set aside by a sorting rule, a reply the person's own sent mail answered, or a
    promise's date following its meeting. `reason` is the
    rule's own words (or the assistant's, for a drop), `day` the date a move or a reply carries, `detail` what was heard
    (news). `changeset` and `op` name the op to undo; a rule's close or set-aside mail names its `request` or
    `snapshot` and the `version` read, and `undo` says which kind of undo it is (none when it can no longer be put
    back)."""

    ref: str
    act: Act
    title: str
    when: str
    because: Because
    seen: bool
    undo: UndoKind | None
    quote: str | None = None
    said_by: str | None = None
    said_by_name: str | None = None
    by_you: bool = False
    reason: str | None = None
    day: str | None = None
    detail: str | None = None
    record: tuple[str, str] | None = None
    changeset: str | None = None
    op: int | None = None
    request: str | None = None
    snapshot: str | None = None
    version: int | None = None


@dataclass
class Plan:
    """The list as drawn at `until`: from `since` (the start of the previous day, or the last look when later), newest
    first."""

    since: datetime
    until: datetime
    entries: list[Entry] = field(default_factory=list)

    @property
    def unseen(self) -> list[Entry]:
        return [e for e in self.entries if not e.seen]

    def counts(self) -> dict[str, int]:
        """What is unseen, counted by act, in the order a person reads it."""
        unseen = self.unseen
        return {act: n for act in ACTS if (n := sum(1 for e in unseen if e.act == act))}


def _moment(stamp: Any) -> datetime | None:
    if isinstance(stamp, datetime):
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    try:
        moment = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def window_start(cfg: Any, now: datetime, looked: datetime | None) -> datetime:
    """The start of the previous day on the person's clock, as a moment; the last look instead when that is later."""
    here = zone(cfg)
    first = datetime.combine(now.astimezone(here).date() - timedelta(days=1), time(0), tzinfo=here).astimezone(UTC)
    return max(first, looked) if looked is not None else first


def looked_at(view: Any, person: str | None) -> datetime | None:
    """When the person last opened the list, or None if they never have."""
    for record in view.list("look"):
        if record.data.get("person") == person:
            return _moment(record.data["at"])
    return None


def mark_seen(store: Any, cfg: Any, until: datetime) -> None:
    """The person opened the list as it was drawn at `until`: everything made up to then counts as seen. The look only
    moves forward, so an older mark changes nothing."""
    from engine.names import People

    person = People(store, cfg).pm
    stamp = (until if until.tzinfo else until.replace(tzinfo=UTC)).astimezone(UTC)
    with store.transaction() as tx:
        current = next((r for r in tx.list("look") if r.data.get("person") == person), None)
        if current is None:
            tx.create("look", {"person": person, "at": stamp.isoformat()}, _LOOK)
            return
        before = _moment(current.data["at"])
        if before is None or stamp > before:
            tx.update("look", current.id, {"at": stamp.isoformat()}, _LOOK, read_version=current.version)


def _clip(text: str | None) -> str | None:
    words = " ".join((text or "").split())
    if not words:
        return None
    return words if len(words) <= _QUOTE_LIMIT else words[: _QUOTE_LIMIT - 1].rstrip() + "…"


def _text_of(view: Any, kind: str, record_id: str) -> str | None:
    found = view.get(kind, record_id)
    if found is None:
        return None
    return str(found.data.get("text") or found.data.get("title") or "") or None


def _local_day(stamp: Any, cfg: Any) -> str | None:
    moment = _moment(stamp)
    return moment.astimezone(zone(cfg)).date().isoformat() if moment is not None else None


def build(ws: Any, view: Any, cfg: Any, people: Any, now: datetime) -> Plan:
    """The list as of `now`, for the person who runs the app."""
    since = window_start(cfg, now, looked_at(view, people.pm))
    found: dict[tuple[str, str], tuple[datetime, Entry]] = {}

    def keep(key: tuple[str, str], moment: datetime, entry: Entry) -> None:
        # One entry for each record: the newest thing done to it.
        held = found.get(key)
        if held is None or (moment, entry.ref) > (held[0], held[1].ref):
            found[key] = (moment, entry)

    every = {c.ref: c for c in closes.collect(view)}
    for cs in view.list("changeset"):
        moment = _moment(cs.data["created_at"])
        if moment is None or not (since < moment <= now) or cs.data["status"] == "rejected":
            continue
        request = view.get("request", cs.data["request"]) if cs.data.get("request") else None
        if cs.data.get("action") or (request is not None and request.data.get("origin") == "pm"):
            continue  # the person's own change
        who = _who(ws, view, cfg, people, request, cs)
        for outcome in cs.data["ops"]:
            if outcome.get("status") != "applied":
                continue
            if any(p.get("severity") == "hold" for p in outcome.get("problems") or []):
                continue  # the person released it from held: their decision
            for key, entry in _entries_of(view, cfg, cs, outcome, request, who, every):
                keep(key, moment, entry)
    for close in every.values():
        moment = _moment(close.when)
        if close.by_person or close.kind == "assistant" or moment is None or not (since < moment <= now):
            continue
        entry = _rule_entry(view, close)
        if entry is not None:
            keep((close.record or ("", close.ref))[:2], moment, entry)
    entries = [e for _, e in sorted(found.values(), key=lambda pair: (pair[0], pair[1].ref), reverse=True)]
    return Plan(since=since, until=now, entries=entries)


@dataclass(frozen=True)
class _Who:
    person: str | None
    name: str | None
    by_you: bool


def _who(ws: Any, view: Any, cfg: Any, people: Any, request: Any, cs: Any) -> _Who:
    """Who said what a change rested on: the one person the input came from, or the sender as written when that is not
    a known person. A change the engine made from the person's own sent mail is theirs."""
    if cs.data.get("by_rule") == RULE_REPLIED:
        return _Who(people.pm, people.name(people.pm) if people.pm else None, people.pm is not None)
    if request is None:
        return _Who(None, None, False)
    source = view.get("source", request.data["source"]) if request.data.get("source") else None
    title = title_for(
        request.data,
        source.data if source is not None else None,
        cs.data,
        people=people,
        skip=list(cfg.language.title_skip),
        head=head_of(ws.sources_dir, source.data.get("content_hash") if source is not None else None),
    )
    name = people.name(title.person) if title.person else title.sender
    return _Who(title.person, name, title.person is not None and title.person == people.pm)


def _entries_of(
    view: Any, cfg: Any, cs: Any, outcome: dict[str, Any], request: Any, who: _Who, every: dict[str, closes.Close]
) -> list[tuple[tuple[str, str], Entry]]:
    op = outcome.get("op") or {}
    name = op.get("op", "")
    index = outcome["index"]
    base = f"changeset:{cs.id}:{index}"
    reviewed = bool(cs.data.get("reviewed"))
    if name == "event.set":
        return _meeting_moves(view, cs, outcome, base, reviewed)
    act = _ACT_OF.get(name)
    if act is None:
        return []
    kind = "question" if name.startswith("question.") else "action"
    record_id = op.get("id")
    if name == "action.add":
        record_id = next((r["id"] for r in outcome.get("records") or [] if r.get("kind") == "action"), None)
    target = view.get(kind, record_id) if record_id else None
    if target is None or target.data.get("status") == "held":
        return []
    if name == "action.add":
        first = view.ledger(kind="action", record_id=target.id)
        if first and first[0].get("changeset") != cs.id:
            act = "merged"
    title = _text_of(view, kind, target.id) or target.id
    quote = _clip((op.get("evidence") or {}).get("quote"))
    close = every.get(base)
    seen = (not close.silent) if close is not None and name in _CLOSING else reviewed
    replied = cs.data.get("by_rule") == RULE_REPLIED
    day = None
    if act == "moved":
        day = target.data.get("due")
    elif replied and request is not None and request.data.get("source"):
        source = view.get("source", request.data["source"])
        day = _local_day(source.data.get("received_at"), cfg) if source is not None else None
    detail = None
    if name == "action.part":
        detail = _clip(op.get("delivered"))
    elif name == "action.news":
        detail = _clip(op.get("text"))
    elif name == "question.done":
        detail = _clip(op.get("answer"))
    entry = Entry(
        ref=base,
        act=act,
        title=title,
        when=str(cs.data["created_at"]),
        because="replied" if replied else "said",
        seen=seen,
        undo="changeset",
        quote=quote,
        said_by=who.person,
        said_by_name=who.name,
        by_you=who.by_you,
        reason=_clip(op.get("reason")) if act == "dropped" else None,
        day=str(day) if day else None,
        detail=detail,
        record=(kind, target.id),
        changeset=cs.id,
        op=index,
    )
    return [((kind, target.id), entry)]


def _meeting_moves(
    view: Any, cs: Any, outcome: dict[str, Any], base: str, reviewed: bool
) -> list[tuple[tuple[str, str], Entry]]:
    """The promises whose date followed a calendar entry the assistant moved: one entry each, said to be a rule's."""
    found = []
    for ref in outcome.get("records") or []:
        if ref.get("kind") != "action":
            continue
        action = view.get("action", ref["id"])
        if action is None or action.data.get("status") == "held":
            continue
        found.append(
            (
                ("action", action.id),
                Entry(
                    ref=f"{base}:{action.id}",
                    act="moved",
                    title=str(action.data["text"]),
                    when=str(cs.data["created_at"]),
                    because="meeting",
                    seen=reviewed,
                    undo="changeset",
                    day=action.data.get("due"),
                    record=("action", action.id),
                    changeset=cs.id,
                    op=outcome["index"],
                ),
            )
        )
    return found


def _rule_entry(view: Any, close: closes.Close) -> Entry | None:
    """A change a triage rule closed before the assistant read it, or mail a sorting rule set aside."""
    if close.kind == "rule" and close.request:
        found = view.get("request", close.request)
        return Entry(
            ref=close.ref,
            act="closed",
            title=close.title,
            when=close.when,
            because="rule",
            seen=not close.silent,
            undo="closer_look",
            reason=_clip(close.why),
            request=close.request,
            version=found.version if found is not None else None,
        )
    if close.kind == "set_aside" and close.snapshot:
        found = view.get("snapshot", close.snapshot)
        return Entry(
            ref=close.ref,
            act="set_aside",
            title=close.title,
            when=close.when,
            because="sorting",
            seen=not close.silent,
            undo=None if close.approved else "set_aside",
            reason=_clip(close.why),
            snapshot=close.snapshot,
            version=found.version if found is not None else None,
        )
    return None
