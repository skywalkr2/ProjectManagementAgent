"""The walkthrough's first result (design 7.8): once a mailbox is connected and an AI account is chosen, the walkthrough
offers to look back over the mail of the last `first_run_days`, says what that would cost before anything is read, and
after the person's go shows a handful of the open promises found, with one follow-up ready to copy.

The look back is the quiet intake of the sources a sign-in brought (design 6.32, `engine/source_intake.py`): this module
only reads where it stands and gives the one go for all of them. Nothing here writes except `go`, which approves the
requests of those intakes, as the Go on Today's line does. The promises are the open promises as every screen shows them
(`engine/promises.py`) and the follow-up is the one the Follow-ups screen composes (`engine/followups.py`), copied
through the same route, so nothing new is kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from engine import followups, promises, source_intake
from engine.connectors import CORE, declared_reads, reads
from engine.dispatcher import waits_on_first_go
from engine.names import People
from engine.storage import WriteContext

_GO = WriteContext(actor="pm", trust="trusted", op="intake.go")

#: Where the first result stands, in the order it is reached.
STAGES = ("no_mail", "no_ai", "reading", "offer", "working", "ready")


@dataclass
class Promise:
    """One open promise as the first-result screen lists it."""

    action: str
    text: str
    owner: str  # in the workspace's owner format
    mine: bool
    promised_to: list[str] = field(default_factory=list)
    due: date | None = None
    quote: str | None = None


@dataclass
class FollowUp:
    """The one follow-up ready to copy: whom it is to, and the message the Follow-ups screen composes for them."""

    person: str
    name: str
    message: str
    to_send: int


@dataclass
class FirstPromises:
    """Where the first result stands. `stage`: no_mail (nothing to read yet), no_ai (no AI account chosen), reading
    (the first read hasn't happened), offer (the look back is held for the person's go: `count` items, about
    `estimate_usd`, `unpriced` with no price, `days` of mail), working (`finished` of `count` done) or ready (the
    promises found, up to the limit; `more` are not shown)."""

    stage: str
    sources: list[str] = field(default_factory=list)
    days: int | None = None
    count: int = 0
    finished: int = 0
    estimate_usd: float | None = None
    unpriced: int = 0
    promises: list[Promise] = field(default_factory=list)
    more: int = 0
    follow_up: FollowUp | None = None


def _sources(store: Any, cfg: Any) -> list[Any]:
    """The sources the first result is about: those that read mail or a calendar (or that already have an intake), and
    are on."""
    said = declared_reads({**CORE, **store.plugins.connectors()})
    taken = {r.data.get("intake") for r in store.read().list("request")}
    return [s for s in cfg.watch.sources if s.enabled and (reads(s.connector, said) or s.id in taken)]


def _held(request: dict[str, Any]) -> bool:
    """Whether an intake request waits for the person: its own go, or the workspace's first go."""
    return source_intake.waits_on_go(request) or (bool(request.get("intake")) and waits_on_first_go(request))


def where(ws: Any, store: Any, cfg: Any, router: Any = None) -> FirstPromises:
    """Where the first result stands now. Reads only."""
    if not any(tier.use for tier in cfg.ai.tiers.values()):
        return FirstPromises("no_ai")
    sources = _sources(store, cfg)
    if not sources:
        return FirstPromises("no_mail")
    view = store.read()
    ids = {s.id for s in sources}
    labels = [s.label or s.id for s in sources]
    if not any(view.find("watch_run", {"source": s.id}) for s in sources):
        return FirstPromises("reading", sources=labels)
    mine = [r for r in view.list("request") if r.data.get("intake") in ids and not r.data.get("dismissed")]
    days = next((d for s in sources if (d := source_intake.days_taken(view, s.id)) is not None), None)
    held = [r for r in mine if _held(r.data)]
    # Some requests held and others still on their way to being held (queued or running) is a moment on the way to the
    # offer, or work under way: the offer shows once everything that is going to wait is waiting.
    on_the_way = any(r.data.get("state") in ("queued", "running") for r in mine)
    if held and not on_the_way:
        count, total, unpriced = 0, 0.0, 0
        priced = False
        for s in sources:
            n, amount, none = source_intake.total_waiting(ws, store, cfg, s.id, router)
            count, unpriced = count + n, unpriced + none
            if amount is not None:
                total, priced = total + amount, True
        # Requests that started by themselves and wait on the workspace's first go are priced by their own estimates.
        for r in held:
            if waits_on_first_go(r.data):
                count += 1
                if r.data.get("estimate_usd") is None:
                    unpriced += 1
                else:
                    total, priced = total + r.data["estimate_usd"], True
        return FirstPromises(
            "offer",
            sources=labels,
            days=days,
            count=count,
            estimate_usd=round(total, 4) if priced else None,
            unpriced=unpriced,
        )
    unfinished = [r for r in mine if source_intake.unfinished(r.data)]
    if unfinished:
        return FirstPromises(
            "working", sources=labels, days=days, count=len(mine), finished=len(mine) - len(unfinished)
        )
    return FirstPromises("ready", sources=labels, days=days, count=len(mine), finished=len(mine))


def go(ws: Any, store: Any, cfg: Any, router: Any = None) -> int:
    """The person's go for the look back: each source's held intake is started (the mail waiting for sorting is sorted
    first), and an intake request waiting on the workspace's first go is approved, since this go covers it. Returns how
    many requests it started."""
    started = 0
    for source in _sources(store, cfg):
        started += source_intake.grant_go(ws, store, cfg, source.id, router)
        with store.transaction() as tx:
            for req in tx.list("request"):
                d = req.data
                if d.get("intake") == source.id and not d.get("dismissed") and waits_on_first_go(d):
                    tx.update(
                        "request",
                        req.id,
                        {"approval": "granted", "state": "queued", "waiting": None},
                        _GO,
                        read_version=req.version,
                    )
                    started += 1
    return started


def found(store: Any, cfg: Any, limit: int, today: date | None = None) -> FirstPromises:
    """The open promises, soonest day first and those with no day after, up to `limit`, with how many more there are
    and the one follow-up ready to copy: the first person, A to Z, who owes one of those shown and not yet been told,
    with the message the Follow-ups screen composes for them (never one to the person themselves)."""
    reader = store.read()
    people = People(store, cfg)
    open_promises = [
        a
        for a in reader.list("action")
        if a.data.get("status") == "open" and not a.data.get("on_hold") and promises.is_promise(a.data)
    ]
    open_promises.sort(key=lambda a: (a.data.get("due") is None, str(a.data.get("due") or ""), a.data["text"], a.id))
    shown = open_promises[: max(0, limit)]
    listed = [
        Promise(
            action=a.id,
            text=a.data["text"],
            owner=", ".join(people.owner(o) for o in a.data.get("owners") or []),
            mine=people.pm is not None and any(o.get("person") == people.pm for o in a.data.get("owners") or []),
            promised_to=[people.name(p) for p in a.data.get("promised_to") or []],
            due=date.fromisoformat(str(a.data["due"])) if a.data.get("due") else None,
            quote=(a.data.get("evidence") or {}).get("quote"),
        )
        for a in shown
    ]
    shown_ids = {a.id for a in shown}
    ready = [
        s
        for s in followups.sections(store, cfg, today or date.today())
        if not s.is_pm and s.message and any(a["id"] in shown_ids and a["told"] is None for a in s.actions)
    ]
    follow_up = FollowUp(ready[0].person, ready[0].name, ready[0].message, ready[0].to_send) if ready else None
    return FirstPromises("ready", promises=listed, more=len(open_promises) - len(listed), follow_up=follow_up)


def view(ws: Any, store: Any, cfg: Any, router: Any = None, today: date | None = None) -> FirstPromises:
    """The whole first result: where it stands, and once it is ready the promises and the follow-up."""
    state = where(ws, store, cfg, router)
    if state.stage != "ready":
        return state
    result = found(store, cfg, cfg.ui.walkthrough.first_promises, today)
    state.promises, state.more, state.follow_up = result.promises, result.more, result.follow_up
    return state
