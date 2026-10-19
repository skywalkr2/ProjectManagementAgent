"""Closes the person didn't see (design 6.32, "No close goes unseen").

Every way something is closed, dropped, set aside or answered without the person making or seeing the close is one
`Close`, read from the records that already say so:

- a watched change a triage rule closed before the assistant read it (`request.auto_closed`);
- mail a rule or the assistant's sorting set aside as not work (`snapshot.set_aside`);
- an action or question the assistant closed, dropped or answered as data, in a changeset (`action.close`,
  `action.drop`, `question.drop`, `question.done`).

A close is not silent when the person made it themselves (a note, a screen, a person action), or saw and approved it:
confirmed the set-aside mail, marked a rule's close as seen, looked over the changeset ("Looks good") or released the op
from held. A close that was undone, or that the person took a closer look at, is no longer a close. `silent` lists the
closes nobody has seen, newest first, and `measure` counts them with their denominators for the quality figures.
Nothing here writes except `mark_seen`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from engine.set_aside import BY_PERSON
from engine.storage import StoreError, WriteContext

CloseKind = Literal["rule", "set_aside", "assistant"]
How = Literal["closed", "set_aside", "dropped", "answered"]

#: The ops that close something, with the kind of record each closes and how.
CLOSING_OPS: dict[str, tuple[str, How]] = {
    "action.close": ("action", "closed"),
    "action.drop": ("action", "dropped"),
    "question.drop": ("question", "dropped"),
    "question.done": ("question", "answered"),
}
_SEEN = WriteContext(actor="pm", trust="trusted", op="closes.seen")


class NotAClose(StoreError):
    """The reference names nothing that is a close."""


class ReviewElsewhere(StoreError):
    """The close is reviewed on another screen (set-aside mail is confirmed in its folder)."""


@dataclass(frozen=True)
class Close:
    """One close: what was closed, when, by which rule or run, and why. `ref` names it for `mark_seen`."""

    ref: str
    kind: CloseKind
    how: How
    title: str
    when: str
    why: str
    record: tuple[str, str] | None = None
    rule: str | None = None
    run: str | None = None
    request: str | None = None
    changeset: str | None = None
    snapshot: str | None = None
    by_person: bool = False
    approved: bool = False

    @property
    def silent(self) -> bool:
        """Nobody saw it: the person didn't make it and hasn't approved it."""
        return not self.by_person and not self.approved


@dataclass(frozen=True)
class KindCount:
    total: int
    silent: int


@dataclass(frozen=True)
class CloseMeasure:
    """Silent closes out of all closes in a period, with the counts behind the rate."""

    total: int
    silent: int
    by_person: int
    approved: int
    by_kind: dict[str, KindCount] = field(default_factory=dict)

    @property
    def rate(self) -> float | None:
        """Silent closes over all closes; None when nothing was closed, so an empty period has no rate."""
        return self.silent / self.total if self.total else None


def _moment(stamp: Any) -> datetime | None:
    if isinstance(stamp, datetime):
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    try:
        moment = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _text_of(view: Any, kind: str, record_id: str) -> str:
    found = view.get(kind, record_id)
    if found is None:
        return record_id
    return str(found.data.get("title") or found.data.get("text") or record_id)


def _rule_closes(view: Any) -> list[Close]:
    found = []
    for req in view.list("request"):
        mark = req.data.get("auto_closed")
        if not mark:
            continue
        source = view.get("source", req.data["source"]) if req.data.get("source") else None
        found.append(
            Close(
                ref=f"request:{req.id}",
                kind="rule",
                how="closed",
                title=str(source.data["title"]) if source is not None else req.id,
                when=str(req.data["created_at"]),
                why=str(mark.get("reason") or ""),
                record=("request", req.id),
                rule=mark.get("rule"),
                request=req.id,
                approved=bool(mark.get("reviewed_at")),
            )
        )
    return found


def _set_aside_closes(view: Any) -> list[Close]:
    found = []
    for snap in view.list("snapshot"):
        mark = snap.data.get("set_aside")
        if not mark:
            continue
        data = snap.data
        received = (data.get("message") or {}).get("received")
        by_person = mark.get("by") == "person" or mark.get("rule") == BY_PERSON
        found.append(
            Close(
                ref=f"snapshot:{snap.id}",
                kind="set_aside",
                how="set_aside",
                title=str(data.get("title") or ""),
                when=str(data.get("seen_at") or received or ""),
                why=str(mark.get("reason") or ""),
                record=("snapshot", snap.id),
                rule=mark.get("rule"),
                snapshot=snap.id,
                by_person=by_person,
                approved=bool(mark.get("confirmed_at")) or bool(data.get("deleted")),
            )
        )
    return found


def _assistant_closes(view: Any) -> list[Close]:
    found = []
    for cs in view.list("changeset"):
        data = cs.data
        request = view.get("request", data["request"]) if data.get("request") else None
        by_person = bool(data.get("action")) or (request is not None and request.data.get("origin") == "pm")
        for outcome in data["ops"]:
            op = outcome.get("op") or {}
            closing = CLOSING_OPS.get(op.get("op", ""))
            if closing is None or outcome.get("status") != "applied":
                continue
            kind, how = closing
            released = any(p.get("severity") == "hold" for p in outcome.get("problems") or [])
            found.append(
                Close(
                    ref=f"changeset:{cs.id}:{outcome['index']}",
                    kind="assistant",
                    how=how,
                    title=_text_of(view, kind, op["id"]),
                    when=str(data["created_at"]),
                    why=" ".join(str(op.get("reason") or (op.get("evidence") or {}).get("quote") or "").split()),
                    record=(kind, op["id"]),
                    run=data.get("run"),
                    request=data.get("request"),
                    changeset=cs.id,
                    by_person=by_person,
                    approved=bool(data.get("reviewed")) or released,
                )
            )
    return found


def collect(view: Any, since: datetime | None = None, until: datetime | None = None) -> list[Close]:
    """Every close in force, newest first, those the person made or saw included. With `since` and `until`, only the
    closes made in that period (one whose time can't be read is always kept)."""
    found = [*_rule_closes(view), *_set_aside_closes(view), *_assistant_closes(view)]
    if since is not None or until is not None:
        kept = []
        for close in found:
            moment = _moment(close.when)
            if moment is not None and ((since and moment < since) or (until and moment > until)):
                continue
            kept.append(close)
        found = kept
    found.sort(key=lambda c: (_moment(c.when) or datetime.min.replace(tzinfo=UTC), c.ref), reverse=True)
    return found


def silent(view: Any, since: datetime | None = None, until: datetime | None = None) -> list[Close]:
    """The closes nobody has seen, newest first."""
    return [c for c in collect(view, since, until) if c.silent]


def measure(view: Any, since: datetime | None = None, until: datetime | None = None) -> CloseMeasure:
    """Silent closes out of all closes made in the period, in all and for each kind of close."""
    every = collect(view, since, until)
    kinds: dict[str, KindCount] = {}
    for kind in ("rule", "set_aside", "assistant"):
        mine = [c for c in every if c.kind == kind]
        kinds[kind] = KindCount(total=len(mine), silent=sum(1 for c in mine if c.silent))
    return CloseMeasure(
        total=len(every),
        silent=sum(1 for c in every if c.silent),
        by_person=sum(1 for c in every if c.by_person),
        approved=sum(1 for c in every if c.approved and not c.by_person),
        by_kind=kinds,
    )


def mark_seen(store: Any, ref: str, now: datetime | None = None) -> None:
    """The person saw a close and it stands: a rule's close is marked, and an assistant's close is approved by looking
    over its changeset. Set-aside mail is reviewed in its folder, not here."""
    kind, _, rest = ref.partition(":")
    if kind == "request":
        with store.transaction() as tx:
            current = tx.get("request", rest)
            mark = current.data.get("auto_closed") if current is not None else None
            if not mark:
                raise NotAClose("That isn't something a rule closed.")
            stamp = (now or datetime.now(UTC)).isoformat()
            tx.update(
                "request",
                rest,
                {"auto_closed": {**mark, "reviewed_at": stamp}},
                _SEEN,
                read_version=current.version,
            )
    elif kind == "changeset":
        from engine.dispatcher import looks_good

        changeset_id = rest.partition(":")[0]
        view = store.read()
        stored = view.get("changeset", changeset_id)
        if stored is None or not any(c.changeset == changeset_id for c in _assistant_closes(view)):
            raise NotAClose("That isn't a close the assistant made.")
        looks_good(store, changeset_id)
    elif kind == "snapshot":
        raise ReviewElsewhere("Mail that was set aside is reviewed in the Set aside folder.")
    else:
        raise NotAClose("That isn't a close.")
