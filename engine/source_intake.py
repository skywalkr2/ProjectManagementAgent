"""A newly added source is taken in quietly (design 6.32).

The first read of a source with `first_run: intake` notes everything it holds, then hands the assistant what is worth
taking in: the mail of the last `first_run_days`, and every item of any other kind of source. Nothing is reported as new
one by one. The requests it makes carry `intake: <source id>`; they are priced together as one total and either start by
themselves (the total is not above `ai.budgets.confirm_above_usd`, and is known unless unpriced runs need no go) or wait
for one go, which is one line on Today. Their results are gathered into one line and one list to look over, not a line
each, until the person opens the list. Every open item found is followed from then on, whatever its age: the records the
assistant makes from it are ordinary records. Age only decides whether something is taken in at all.

The date before which a source's mail wasn't looked at is kept on the source's first `watch_run` (`looked_back_to`).
The person can ask for a look further back: the older mail the connector already returned (its snapshots) is taken in
the same way, under the same go rules, and the date moves.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine import catch_up, watch
from engine.storage import StoreError, WriteContext

#: What the requests of an intake wait on until the person's go; Today gathers them into one line for the source.
WAITING = "Taking in this source waits for you to start it."

_ENGINE = WriteContext(actor="engine", trust="trusted", op="intake.take_in")
_GO = WriteContext(actor="pm", trust="trusted", op="intake.go")
_SEEN = WriteContext(actor="pm", trust="trusted", op="intake.seen")
_MOVED = WriteContext(actor="engine", trust="trusted", op="intake.look_back")

#: How far past now a message's time may be and still count as received.
_SKEW = timedelta(minutes=5)


def waits_on_go(request: dict[str, Any]) -> bool:
    """Whether a request's data says it is part of a source's intake waiting for the person's go."""
    return (
        request.get("state") == "needs_you"
        and request.get("approval") == "required"
        and request.get("waiting") == WAITING
        and bool(request.get("intake"))
        and not request.get("dismissed")
    )


def unfinished(request: dict[str, Any]) -> bool:
    """Whether an intake request is still to be done: waiting its turn, running, or waiting for a go (the intake's
    own, or the first one in the workspace). A request that stopped, failed or has its result is finished."""
    from engine.dispatcher import waits_on_first_go

    return request.get("state") in ("queued", "running") or waits_on_go(request) or waits_on_first_go(request)


# ---- the window ---------------------------------------------------------------------------------------------


def _start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _when(data: dict[str, Any]) -> datetime | None:
    """When a mail item was received (else when it changed), as a moment with a zone; None when it says neither."""
    from engine.connectors import moment

    stamp = (data.get("message") or {}).get("received") or data.get("changed_at")
    if not stamp:
        return None
    try:
        at = moment(stamp)
    except (TypeError, ValueError):
        return None
    if not isinstance(at, datetime):
        at = _start(at)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def looked_back_to(source: Any, items: list[Any], now: datetime) -> date | None:
    """The day before which a source's mail isn't looked at by its first read: `first_run_days` before the read. None
    for a source that holds no mail (any other kind of source is taken in whole)."""
    if not any(getattr(item, "message", None) is not None for item in items):
        return None
    return (now - timedelta(days=source.first_run_days)).date()


def _in_window(back_to: date | None, until: date | None, now: datetime) -> Callable[[dict[str, Any]], bool]:
    """Which snapshots are taken in: mail received from the start of `back_to` (and before the start of `until`, or
    before now when there is none); everything that isn't mail when there is no `until`."""

    def accept(data: dict[str, Any]) -> bool:
        if not data.get("message"):
            return until is None  # another kind of item is taken in whole, once, by the first read
        at = _when(data)
        if at is None:
            return False
        if back_to is not None and at < _start(back_to):
            return False
        return at < _start(until) if until is not None else at <= now + _SKEW

    return accept


# ---- taking a source in -------------------------------------------------------------------------------------


def take_in(
    ws: Any, store: Any, cfg: Any, source: Any, now: datetime, router: Any = None, back_to: date | None = None
) -> list[str]:
    """Take in a source's first read: hand in what the window takes, held for one go, price it as one total, and start
    it at once when the total is not above the amount to confirm and is known (or unpriced runs need no go). Returns
    the requests made."""
    return _take(ws, store, cfg, source, now, router, _in_window(back_to, None, now))


def _take(
    ws: Any, store: Any, cfg: Any, source: Any, now: datetime, router: Any, accept: Callable[[dict[str, Any]], bool]
) -> list[str]:
    made = watch._hand_in_window(
        ws,
        store,
        cfg,
        source.id,
        now,
        router,
        accept,
        extra={"intake": source.id, "state": "needs_you", "approval": "required", "waiting": WAITING},
        sort=False,  # the assistant's sorting is part of the one total: it runs when the intake starts
    )
    view = store.read()
    held = [r for r in made if waits_on_go(view.get("request", r).data)]
    if not held:
        return made
    catch_up._price(ws, store, cfg, router, held, now, _ENGINE)
    count, total, unpriced = total_waiting(ws, store, cfg, source.id, router)
    # Unpriced runs wait only when the person asked for a go before those too, as single runs do.
    priced_enough = unpriced == 0 or not cfg.ai.budgets.confirm_unpriced
    if count and priced_enough and (total or 0.0) <= cfg.ai.budgets.confirm_above_usd:
        # Sorting first, while they are held, so mail it sets aside never queues; with no go given, its own checks hold.
        watch.sort_before_first_go(ws, store, cfg, router, now, only=source.id, go=False)
        _release(store, source.id, now)
    return made


def _release(store: Any, source_id: str, now: datetime) -> int:
    """Start the intake's held requests without a go: the total is known and below the amount to confirm, so they
    are queued like any other work (the first-go and per-run checks still apply when each is processed)."""
    started = 0
    with store.transaction() as tx:
        for req in tx.list("request"):
            if waits_on_go(req.data) and req.data.get("intake") == source_id:
                tx.update(
                    "request",
                    req.id,
                    {"state": "queued", "approval": None, "waiting": watch.STARTING},
                    _ENGINE,
                    read_version=req.version,
                )
                started += 1
    return started


def waiting(view: Any, source_id: str | None = None) -> list[Any]:
    """The requests held for an intake's go, oldest first; of one source, or of every source."""
    held = [
        r
        for r in view.list("request")
        if waits_on_go(r.data) and (source_id is None or r.data.get("intake") == source_id)
    ]
    return sorted(held, key=lambda r: str(r.data.get("created_at")))


def total_waiting(ws: Any, store: Any, cfg: Any, source_id: str, router: Any = None) -> tuple[int, float | None, int]:
    """What a source's intake would start: how many requests wait for its go, what the ones with a price cost together
    with the sorting run for their mail (None when nothing has a price) and how many runs have no price."""
    held = waiting(store.read(), source_id)
    if not held:
        return 0, None, 0
    priced = [r.data["estimate_usd"] for r in held if r.data.get("estimate_usd") is not None]
    _runs, sorting_usd, sorting_unpriced = watch.first_go_sorting(ws, store, cfg, router, only=source_id)
    total = sum(priced) + (sorting_usd or 0.0)
    return (
        len(held),
        round(total, 4) if priced or sorting_usd is not None else None,
        len(held) - len(priced) + sorting_unpriced,
    )


def grant_go(ws: Any, store: Any, cfg: Any, source_id: str, router: Any = None, now: datetime | None = None) -> int:
    """The person's go for a source's intake: the mail that waits for sorting is sorted first (what it sets aside never
    runs), then every request held for the go is approved and queued. Returns how many were."""
    watch.sort_before_first_go(ws, store, cfg, router, now, only=source_id)
    started = 0
    with store.transaction() as tx:
        for req in tx.list("request"):
            if waits_on_go(req.data) and req.data.get("intake") == source_id:
                tx.update(
                    "request",
                    req.id,
                    {"approval": "granted", "state": "queued", "waiting": None, "cause": None},
                    _GO,
                    read_version=req.version,
                )
                started += 1
    return started


# ---- the results, as one list -------------------------------------------------------------------------------


def unseen(view: Any) -> dict[str, list[Any]]:
    """The requests of each source's intake whose results the person hasn't opened yet, by source id."""
    found: dict[str, list[Any]] = {}
    for req in view.list("request"):
        d = req.data
        if d.get("intake") and not d.get("intake_seen") and not d.get("dismissed"):
            found.setdefault(d["intake"], []).append(req)
    return found


def mark_seen(store: Any, source_id: str) -> list[str]:
    """The person opened the list of what an intake found: its requests show on Today one by one again if they still
    need a look. Returns the requests marked, for Undo."""
    marked: list[str] = []
    with store.transaction() as tx:
        for req in tx.list("request"):
            d = req.data
            if d.get("intake") == source_id and not d.get("intake_seen") and not d.get("dismissed"):
                tx.update("request", req.id, {"intake_seen": True}, _SEEN, read_version=req.version)
                marked.append(req.id)
    return marked


def mark_unseen(store: Any, request_ids: list[str]) -> int:
    """Undo `mark_seen` for these requests. Returns how many were put back."""
    back = 0
    with store.transaction() as tx:
        for request_id in request_ids:
            req = tx.get("request", request_id)
            if req is not None and req.data.get("intake") and req.data.get("intake_seen"):
                tx.update("request", req.id, {"intake_seen": False}, _SEEN, read_version=req.version)
                back += 1
    return back


# ---- how far back a source was looked at --------------------------------------------------------------------


def intake_run(view: Any, source_id: str) -> Any | None:
    """The read of a source that took it in quietly and noted how far back it looked, or None."""
    runs = [r for r in view.find("watch_run", {"source": source_id}) if r.data.get("looked_back_to")]
    return runs[0] if runs else None


def back_to_of(view: Any, source_id: str) -> date | None:
    """The day before which a source's mail wasn't looked at, or None (nothing was taken in, or no mail)."""
    run = intake_run(view, source_id)
    return date.fromisoformat(str(run.data["looked_back_to"])[:10]) if run else None


def days_taken(view: Any, source_id: str) -> int | None:
    """How many days before its first read a source's mail was looked at (what the intake's line says), None for a
    source with no mail."""
    run = intake_run(view, source_id)
    if run is None:
        return None
    # The look-back date is a UTC day (`looked_back_to`), so the read is counted in UTC days too.
    read = datetime.fromisoformat(str(run.data["started_at"])).date()
    return (read - date.fromisoformat(str(run.data["looked_back_to"])[:10])).days


# ---- looking further back -----------------------------------------------------------------------------------


@dataclass
class LookBack:
    """What looking further back would take in, or did: the items, what they cost, and how far the source reaches."""

    days: int
    from_date: date  # the day asked for
    count: int = 0
    estimate_usd: float | None = None
    unpriced: int = 0
    available_from: date | None = None  # the oldest mail the source has returned, when it is later than asked
    reaches: bool = True  # the source holds mail as far back as asked
    started: bool = False  # taken in and started at once (False: held for the go, or nothing to take in)
    taken: int = 0


def _candidates(ws: Any, store: Any, cfg: Any, source: Any, accept: Callable[[dict[str, Any]], bool]) -> list[Any]:
    """The snapshots a look further back would hand in: mail in the window that was never handed in and that no rule
    closes."""
    from engine.triage import classify

    view = store.read()
    handed = {
        (s.data.get("watched") or {}).get("key")
        for s in view.list("source")
        if (s.data.get("watched") or {}).get("source") == source.id
    }
    found = []
    for snap in view.find("snapshot", {"source": source.id}):
        data = snap.data
        if data.get("gone") or data.get("deleted") or data.get("set_aside") or data["key"] in handed:
            continue
        if not accept(data):
            continue
        item = watch.item_of_snapshot(ws, data)
        closed, kept = classify(store, cfg, watch._change(cfg, source, item, "new", None))
        if closed is None or kept:
            found.append(snap)
    return found


def _source(cfg: Any, source_id: str) -> Any:
    source = next((s for s in cfg.watch.sources if s.id == source_id), None)
    if source is None:
        raise StoreError(f"there is no source {source_id}")
    return source


def _plan(store: Any, cfg: Any, source_id: str, days: int) -> tuple[date, date, date, date | None]:
    """The day the person asked for, the day the first look stopped at, the day the look will stop at and the oldest
    mail the source holds (None when it holds none)."""
    old = back_to_of(store.read(), source_id)
    if old is None:
        raise StoreError("this source was not taken in with a look back, so there is nothing further to look at")
    if days not in cfg.watch.look_back_choices:
        raise StoreError(f"{days} days is not one of the choices")
    asked = old - timedelta(days=days)
    oldest = min(
        (
            at
            for s in store.read().find("snapshot", {"source": source_id})
            if s.data.get("message") and not s.data.get("gone") and (at := _when(s.data)) is not None
        ),
        default=None,
    )
    available = oldest.date() if oldest is not None else None
    reaches = available is None or available <= asked
    return asked, old, asked if reaches else min(old, available or old), available


def look_back_preview(
    ws: Any, store: Any, cfg: Any, source_id: str, days: int, now: datetime | None = None
) -> LookBack:
    """What looking `days` further back than the source was looked at would take in: how many items, about what they
    cost (the average of what the source's earlier items were priced at, times the count; none when none has a price),
    and whether the source holds mail that far back. Writes nothing."""
    source = _source(cfg, source_id)
    asked, old, _new, available = _plan(store, cfg, source_id, days)
    found = _candidates(ws, store, cfg, source, _in_window(asked, old, now or datetime.now(UTC)))
    prices = [
        r.data["estimate_usd"]
        for r in store.read().list("request")
        if r.data.get("intake") == source_id and r.data.get("estimate_usd") is not None
    ]
    result = LookBack(days, asked, len(found), available_from=available if available and available > asked else None)
    result.reaches = result.available_from is None
    if found and prices:
        result.estimate_usd = round(sum(prices) / len(prices) * len(found), 4)
    elif found:
        result.unpriced = len(found)
    return result


def look_further_back(
    ws: Any, store: Any, cfg: Any, source_id: str, days: int, now: datetime | None = None, router: Any = None
) -> LookBack:
    """Take in the older mail the source already returned, `days` further back than it was looked at, the same quiet
    way: marked as the source's intake, priced as one total with what is still held, held for the go or started by
    the same rule. The date it was looked back to moves to the day asked for, or to the oldest mail the source holds
    when that is later. The result says so when the source doesn't reach that far."""
    now = now or datetime.now(UTC)
    source = _source(cfg, source_id)
    with watch._read_lock(ws, source_id):
        asked, old, new, available = _plan(store, cfg, source_id, days)
        found = _candidates(ws, store, cfg, source, _in_window(asked, old, now))
        result = LookBack(
            days, asked, len(found), available_from=available if available and available > asked else None
        )
        result.reaches = result.available_from is None
        keys = {snap.data["key"] for snap in found}
        made = _take(ws, store, cfg, source, now, router, lambda data: data["key"] in keys)
        result.taken = len(made)
        view = store.read()
        held = [r for r in made if waits_on_go(view.get("request", r).data)]
        result.started = bool(made) and not held
        run = intake_run(view, source_id)
        if run is not None and new < old:
            with store.transaction() as tx:
                current = tx.get("watch_run", run.id)
                tx.update(
                    "watch_run", run.id, {"looked_back_to": new.isoformat()}, _MOVED, read_version=current.version
                )
        counted, total, unpriced = total_waiting(ws, store, cfg, source_id, router)
        result.estimate_usd, result.unpriced = total, unpriced
        return result
