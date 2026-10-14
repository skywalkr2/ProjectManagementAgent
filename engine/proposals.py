"""The rules for proposals of what the assistant learned (design 6.22): what makes one a duplicate, when one is close
to something the person discarded, where it came from, when it expires, and what "just this time" remembers.

Plain functions over a read of the records, with no AI. A proposal is an entry in the status `proposed`: a lesson,
glossary entry, routing entry or style note, or a standing rule. It changes nothing until the person keeps it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from engine import knowledge
from engine.cleaning import normalize
from engine.records import Rule, Scope
from engine.storage import WriteContext
from engine.storage.store import id_number

#: Every kind a proposal can be: the four kinds of knowledge and standing rules.
KINDS: tuple[str, ...] = (*knowledge.KINDS, "rule")
#: Where a proposal came from, for the line on Today: an input, or one of the person's corrections.
FROM_INPUT, FROM_CORRECTION = "input", "correction"
#: The task kinds whose proposals come from the person's corrections.
CORRECTION_TASKS: tuple[str, ...] = ("learn.correction",)
#: The reasons a proposal is kept as discarded without the person having said no to its wording.
JUST_THIS_TIME_REASON = "Just this time"
NEAR_DISCARD_REASON = "Close to one you discarded"
#: What the person did that counts as looking over proposals.
REVIEW_ACTS = ("kept", "discarded", "just_this_time")

_EXPIRE = WriteContext(actor="engine", trust="trusted", op="knowledge.expire")


def _at(stamp: Any) -> datetime | None:
    if not stamp:
        return None
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# ---- what an entry is about ------------------------------------------------------------------------------------------


def at_of(stamp: Any) -> datetime:
    """A stored time as a moment with a zone."""
    moment = _at(stamp)
    if moment is None:
        raise ValueError("there is no time")
    return moment


def _norm(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", normalize(str(text or ""))))


def subject_of(kind: str, data: dict[str, Any]) -> str:
    """What an entry is about, in normalized words: a glossary entry's term, a routing entry's topic and who it
    names, a style note's audience and observation, a lesson's or rule's wording."""
    if kind == "glossary_entry":
        return _norm(data.get("term"))
    if kind == "routing_entry":
        who = data.get("person") or data.get("team") or ""
        return _norm(f"{data.get('topic')} {who} {'never' if data.get('negative') else ''}")
    if kind == "style_note":
        return _norm(f"{data.get('audience')} {data.get('observation')}")
    return _norm(data.get("text"))


def similarity(a: str, b: str) -> float:
    """How alike two normalized subjects are: the share of their words they have in common."""
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def scopes_overlap(a: dict[str, Any] | Scope, b: dict[str, Any] | Scope) -> bool:
    """Whether two targets can apply to the same work: their task kinds, people and projects each share something,
    where an empty list of task kinds or people means all of them."""
    one = a if isinstance(a, Scope) else Scope.model_validate(a or {})
    two = b if isinstance(b, Scope) else Scope.model_validate(b or {})
    if one.task_kinds and two.task_kinds and not set(one.task_kinds) & set(two.task_kinds):
        return False
    if one.people and two.people and not set(one.people) & set(two.people):
        return False
    everywhere_one, everywhere_two = one.scope == "workspace", two.scope == "workspace"
    if everywhere_one and everywhere_two:
        return True
    if everywhere_one:
        return bool(set(two.projects) - set(one.except_))
    if everywhere_two:
        return bool(set(one.projects) - set(two.except_))
    return bool(set(one.projects) & set(two.projects))


# ---- duplicates and near-discards ------------------------------------------------------------------------------------


def duplicate_of(view: Any, kind: str, data: dict[str, Any]) -> Any | None:
    """The proposed or active entry of this kind that says the same thing over an overlapping target, if any; an
    active one first, then the oldest."""
    subject = subject_of(kind, data)
    if not subject:
        return None
    found = [
        s
        for s in view.list(kind)
        if s.data.get("status") in ("active", "proposed")
        and subject_of(kind, s.data) == subject
        and scopes_overlap(s.data.get("applies_to") or {}, data.get("applies_to") or {})
    ]
    found.sort(key=lambda s: (s.data["status"] != "active", id_number(s.id) or 0))
    return found[0] if found else None


def _signals(view: Any, kinds: tuple[str, ...]) -> list[Any]:
    return [s for s in view.list("signal") if s.data["kind"] in kinds]


def _decisions(view: Any) -> dict[str, tuple[str, datetime]]:
    """For each entry the person discarded or set aside with "just this time", the last of the two they did and when.
    Undoing either records nothing, so the last signal on an entry is what it stands for while it is discarded."""
    found: dict[str, tuple[str, datetime]] = {}
    ordered = sorted(
        _signals(view, ("discarded", "just_this_time")), key=lambda s: (str(s.data["at"]), id_number(s.id) or 0)
    )
    for s in ordered:
        moment = _at(s.data["at"])
        if moment is not None:
            for ref in s.data.get("refs", []):
                found[ref] = (s.data["kind"], moment)
    return found


def near_discard(view: Any, kind: str, data: dict[str, Any], now: datetime, days: int, alike: float) -> Any | None:
    """A discarded entry of this kind that the person discarded in the last `days` days, with words alike enough
    (`alike`, 0 to 1) and an overlapping target, if any. An entry set aside with "just this time" is not one: the
    person said it was right, only not a pattern yet."""
    subject = subject_of(kind, data)
    if not subject:
        return None
    since = now - timedelta(days=days)
    decided = _decisions(view)
    for stored in view.list(kind):
        d = stored.data
        last = decided.get(stored.id)
        if d.get("status") != "discarded" or last is None or last[0] != "discarded" or last[1] < since:
            continue
        if similarity(subject_of(kind, d), subject) >= alike and scopes_overlap(
            d.get("applies_to") or {}, data.get("applies_to") or {}
        ):
            return stored
    return None


def just_this_time_before(view: Any, kind: str, data: dict[str, Any], *, own_id: str | None = None) -> int:
    """How many entries about the same thing (same kind, same normalized subject) the person set aside with "just
    this time" before this one, so a repeat of the same correction counts toward a later proposal."""
    subject = subject_of(kind, data)
    if not subject:
        return 0
    decided = _decisions(view)
    return sum(
        1
        for stored in view.list(kind)
        if stored.id != own_id
        and stored.data.get("status") == "discarded"
        and (decided.get(stored.id) or ("", None))[0] == "just_this_time"
        and subject_of(kind, stored.data) == subject
    )


# ---- where a proposal came from --------------------------------------------------------------------------------------


def tag_of(view: Any, kind: str, stored: Any, creations: dict[str, tuple[str | None, str | None]] | None = None) -> str:
    """Whether a proposal came from one of the person's corrections (it cites the signal, or the request that wrote
    it was a learning run on a correction) or from an input."""
    data = stored.data
    evidence = data.get("evidence") or {}
    if evidence.get("signal") or data.get("signal"):
        return FROM_CORRECTION
    request_id = evidence.get("request")
    if request_id is None and creations is not None:
        request_id = creations.get(stored.id, (None, None))[1]
    request = view.get("request", request_id) if request_id else None
    if request is not None and request.data.get("task") in CORRECTION_TASKS:
        return FROM_CORRECTION
    return FROM_INPUT


@dataclass(frozen=True)
class Proposal:
    kind: str
    stored: Any
    came_from: str  # input or correction


def proposals(view: Any) -> list[Proposal]:
    """Every proposal waiting for the person, oldest first, each with where it came from."""
    found: list[Proposal] = []
    for kind in KINDS:
        waiting = [s for s in view.list(kind) if s.data.get("status") == "proposed"]
        if not waiting:
            continue
        creations = view.creations(kind) if hasattr(view, "creations") else None
        found += [Proposal(kind, s, tag_of(view, kind, s, creations)) for s in waiting]
    found.sort(key=lambda p: (str(p.stored.data.get("learned_at") or ""), p.stored.id))
    return found


# ---- expiry and the last review --------------------------------------------------------------------------------------


def expire_due(store: Any, now: datetime, days: int) -> list[str]:
    """Set the proposals from inputs that have waited more than `days` days to `expired`. Proposals from the person's
    own corrections never expire. Running it again changes nothing. Returns the ids expired."""
    view = store.read()
    due = [
        p
        for p in proposals(view)
        if p.came_from == FROM_INPUT
        and (learned := _at(p.stored.data.get("learned_at"))) is not None
        and now - learned > timedelta(days=days)
    ]
    if not due:
        return []
    with store.transaction() as tx:
        for p in due:
            current = tx.get(p.kind, p.stored.id)
            if current is not None and current.data.get("status") == "proposed":
                tx.update(p.kind, p.stored.id, {"status": "expired"}, _EXPIRE, read_version=current.version)
    return [p.stored.id for p in due]


def last_reviewed(view: Any) -> datetime | None:
    """When the person last kept, discarded or set aside a proposal, from the signals those acts record."""
    moments = [
        _at(s.data["at"])
        for s in _signals(view, REVIEW_ACTS)
        if any(knowledge.kind_of(ref) or ref.startswith(f"{Rule.prefix}-") for ref in s.data.get("refs", []))
    ]
    return max((m for m in moments if m is not None), default=None)


def expired_since(view: Any, since: datetime | None) -> int:
    """How many proposals expired after `since` (all of them when it is None)."""
    count = 0
    for kind in KINDS:
        for stored in view.list(kind):
            if stored.data.get("status") != "expired":
                continue
            entries = view.ledger(kind=kind, record_id=stored.id)
            moment = _at(entries[-1]["at"]) if entries else None
            if since is None or (moment is not None and moment > since):
                count += 1
    return count
