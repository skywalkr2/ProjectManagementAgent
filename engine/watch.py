"""Watchers (design 6.4): each source in `watch.yaml` is read on its schedule through its connector, compared with
what was seen last time, and every real difference is handed in for the assistant to read, like something the person
pasted, but marked as outside content.

- A source's first read only notes what is there (`first_run: baseline`), so connecting a full folder doesn't hand
  in everything it holds; `all` hands everything in.
- A changed item is handed in with a readable diff and its text now; a new one with its text; one that disappeared
  from a complete listing, as gone (unless the source turns that off).
- No network is not a failure and files nothing. A source that fails `failures_before_asking` reads in a row files one
  question to the person, not one per read; a read that works again ends it.
"""

from __future__ import annotations

import difflib
import hashlib
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from engine.connectors import CORE, Connector, ConnectorContext, ConnectorError, SourceItem
from engine.storage import StoreError, WriteContext
from engine.triage import first_match

_WATCHER = WriteContext(actor="watcher", trust="untrusted", op="watch.read")
#: Lines of unchanged text shown around each change in a diff.
CONTEXT_LINES = 2


@dataclass
class Result:
    source: str
    outcome: str
    new: list[str] = field(default_factory=list)  # request ids handed in
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    problem: str | None = None
    note: str | None = None  # something to tell the person that isn't a problem with the source


#: What a read says when the same source is already being read.
ALREADY_READING = "Already reading this source"

_reading: dict[tuple[str, str], threading.Lock] = {}
_reading_guard = threading.Lock()


def _read_lock(ws: Any, source_id: str) -> threading.Lock:
    """The one lock for a source in a workspace, shared by every caller in this process."""
    with _reading_guard:
        return _reading.setdefault((str(ws.db_path), source_id), threading.Lock())


def connectors(store: Any) -> dict[str, Connector]:
    """Every connector this install has: the core's and running plugins'."""
    return {**CORE, **store.plugins.connectors()}


def last_run(store: Any, source: str) -> Any | None:
    runs = store.read().find("watch_run", {"source": source})
    return runs[-1] if runs else None


def due(store: Any, cfg: Any, now: datetime) -> list[str]:
    """Sources that are on and whose time has come."""
    found = []
    for source in cfg.watch.sources:
        if not source.enabled:
            continue
        last = last_run(store, source.id)
        started = datetime.fromisoformat(str(last.data["started_at"])) if last else None
        if started is not None and now - started < timedelta(minutes=source.every_minutes):
            continue
        retry_at = last.data.get("retry_at") if last else None
        if retry_at and now < datetime.fromisoformat(str(retry_at)):
            continue  # the service asked to wait
        found.append(source.id)
    return found


def failures_in_a_row(store: Any, source: str) -> int:
    count = 0
    for run in reversed(store.read().find("watch_run", {"source": source})):
        if run.data["outcome"] in ("offline", "throttled"):
            continue
        if run.data["outcome"] != "failed":
            break
        count += 1
    return count


def refresh(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None = None) -> Result:
    """Read one source now, compare and hand in what changed. Returns what happened. A source is never read twice at
    the same moment: when another read of it is under way this one does nothing and says so (outcome "busy")."""
    if not any(s.id == source_id for s in cfg.watch.sources):
        raise StoreError(f"there is no source {source_id}")
    lock = _read_lock(ws, source_id)
    if not lock.acquire(blocking=False):
        return Result(source_id, "busy", note=ALREADY_READING)
    try:
        return _refresh(ws, store, cfg, source_id, now)
    finally:
        lock.release()


def _refresh(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None) -> Result:
    now = now or datetime.now(UTC)
    clock = time.monotonic()
    source = next((s for s in cfg.watch.sources if s.id == source_id), None)
    if source is None:
        raise StoreError(f"there is no source {source_id}")
    worked = [
        r for r in store.read().find("watch_run", {"source": source.id}) if r.data["outcome"] in ("ok", "baseline")
    ]
    # A read that failed keeps nothing: the next one starts from the last read that worked.
    state = dict(worked[-1].data.get("state") or {}) if worked else {}
    connector = connectors(store).get(source.connector)
    try:
        if connector is None:
            raise ConnectorError("not_found", f"no running connector is called {source.connector}")
        try:
            settings = connector.settings.model_validate(source.settings)
        except ValidationError as err:
            first = err.errors()[0]
            where = ".".join(str(p) for p in first["loc"]) or "settings"
            raise ConnectorError("no_access", f"its settings don't fit: {where}: {first['msg']}") from None
        poll = _poll(store, connector, settings, state, ws)
    except ConnectorError as err:
        outcome = {"offline": "offline", "throttled": "throttled"}.get(err.kind, "failed")
        wait = err.retry_after if err.retry_after is not None else source.every_minutes * 60
        _record(
            store,
            source.id,
            now,
            clock,
            outcome,
            error_kind=err.kind if outcome == "failed" else None,
            error=err.detail or None,
            **({"retry_at": (now + timedelta(seconds=wait)).isoformat()} if outcome == "throttled" else {}),
        )
        problem = None
        if outcome == "failed":
            problem = _maybe_ask(store, cfg, source, err)
        return Result(source.id, outcome, problem=problem)
    read_before = any(
        r.data["outcome"] in ("ok", "baseline") for r in store.read().find("watch_run", {"source": source.id})
    )
    baseline = not read_before and source.first_run in ("baseline", "recent")
    recent = timedelta(hours=source.first_run_hours) if baseline and source.first_run == "recent" else None
    result = _compare(ws, store, cfg, source, poll, now, baseline, recent)
    _record(
        store,
        source.id,
        now,
        clock,
        "baseline" if baseline else "ok",
        new=len(result.new),
        changed=len(result.changed),
        removed=len(result.removed),
        state=poll.state,
    )
    _close_question(store, source.id)
    result.outcome = "baseline" if baseline else "ok"
    return result


def _poll(store: Any, connector: Connector, settings: Any, state: dict[str, Any], ws: Any) -> Any:
    context = ConnectorContext(workspace_root=ws.root)
    if "/" not in connector.name:
        return connector.poll(settings, state, context)
    return store.plugins.poll_connector(connector, settings, state, context)


def is_recent(details: dict[str, Any], changed_at: str | None, now: datetime, window: timedelta) -> bool:
    """Whether an item belongs to the recent past or near future: a message received within the window, an event
    starting within it (before or after now), or else an item changed within it. An item with no time isn't."""
    from engine.connectors import moment

    message, event = details.get("message") or {}, details.get("event") or {}
    try:
        if message.get("received"):
            return now - window <= moment(message["received"]) <= now + timedelta(minutes=5)
        if event.get("start"):
            start = moment(event["start"], all_day=bool(event.get("all_day")))
            if not isinstance(start, datetime):
                start = datetime(start.year, start.month, start.day, tzinfo=now.tzinfo)
            return now - window <= start <= now + window
        if changed_at:
            return now - window <= moment(changed_at) <= now + timedelta(minutes=5)
    except (ValueError, TypeError):
        return False
    return False


def _compare(
    ws: Any,
    store: Any,
    cfg: Any,
    source: Any,
    poll: Any,
    now: datetime,
    baseline: bool,
    recent: timedelta | None = None,
) -> Result:
    result = Result(source.id, "ok")
    seen = {s.data["key"]: s for s in store.read().find("snapshot", {"source": source.id}) if not s.data["gone"]}
    listed = set()
    for item in poll.items:
        listed.add(item.key)
        digest = _keep_text(ws, item.text)
        before = seen.get(item.key)
        details = _details(item)
        if before is not None and before.data["content_hash"] == digest:
            if any(before.data.get(k) != v for k, v in details.items()):
                # Only what it is changed (a message was opened, say): kept for Today, nothing to read again.
                with store.transaction() as tx:
                    tx.update("snapshot", before.id, details, _WATCHER, read_version=before.version)
            continue
        change = "new" if before is None else "changed"
        old = _read_text(ws, before.data["content_hash"]) if before is not None else None
        facts = _change(cfg, source, item, change, old)
        closed = first_match(store, cfg, facts)
        with store.transaction() as tx:
            data = {
                "source": source.id,
                "key": item.key,
                "title": item.title,
                "content_hash": digest,
                "author": item.author,
                "seen_at": now.isoformat(),
                **details,
                "closed_by": closed["rule"] if closed else None,
            }
            if before is None:
                tx.create("snapshot", data, _WATCHER)
            else:
                tx.update("snapshot", before.id, data, _WATCHER, read_version=before.version)
            handed = not baseline or (recent is not None and is_recent(details, item.changed_at, now, recent))
            if not handed:
                continue
            text = _input_text(source, item, change, old)
            request = _hand_in(ws, store, tx, cfg, source, item, change, text, now, closed)
        if handed:
            (result.new if change == "new" else result.changed).append(request)
    gone_keys = [k for k in seen if k not in listed] if poll.complete else [k for k in poll.removed if k in seen]
    for key in gone_keys:
        snapshot = seen[key]
        with store.transaction() as tx:
            tx.update("snapshot", snapshot.id, {"gone": True}, _WATCHER, read_version=snapshot.version)
            if baseline or not source.report_removed:
                continue
            gone = SourceItem(key, snapshot.data["title"], "", author=None)
            text = f"{snapshot.data['title']} is no longer in {source.label or source.id}."
            facts = _change(cfg, source, gone, "removed", _read_text(ws, snapshot.data["content_hash"]))
            closed = first_match(store, cfg, facts)
            result.removed.append(_hand_in(ws, store, tx, cfg, source, gone, "removed", text, now, closed))
    return result


def _input_text(source: Any, item: SourceItem, change: str, old: str | None) -> str:
    where = source.label or source.id
    if change == "new":
        return f"New in {where}: {item.title}\n\n{item.text}"
    diff = difflib.unified_diff(
        (old or "").splitlines(), item.text.splitlines(), "before", "now", n=CONTEXT_LINES, lineterm=""
    )
    shown = "\n".join(list(diff)[2:])
    return f"Changed in {where}: {item.title}\n\nWhat changed:\n{shown}\n\nIt now reads:\n{item.text}"


def _details(item: SourceItem) -> dict[str, Any]:
    """What a calendar or mail item is, as the snapshot keeps it."""
    from dataclasses import asdict

    return {
        "link": item.link,
        "event": asdict(item.event) if item.event is not None else None,
        "message": asdict(item.message) if item.message is not None else None,
    }


def _change(cfg: Any, source: Any, item: SourceItem, change: str, old: str | None) -> dict[str, Any]:
    """What triage matchers see about a change."""
    before, now = old or "", item.text
    diff = list(difflib.ndiff(before.splitlines(), now.splitlines())) if change == "changed" else []
    return {
        "source": source.id,
        "key": item.key,
        "title": item.title,
        "change": change,
        "author": item.author,
        "before": before,
        "now": now,
        "added": [line[2:] for line in diff if line.startswith("+ ")],
        "removed": [line[2:] for line in diff if line.startswith("- ")],
        "our_accounts": list(cfg.workspace.our_accounts),
    }


def _hand_in(
    ws: Any,
    store: Any,
    tx: Any,
    cfg: Any,
    source: Any,
    item: SourceItem,
    change: str,
    text: str,
    now: datetime,
    closed: dict[str, Any] | None,
) -> str:
    """Save the input's text and queue it for the assistant, as outside content: closed at once when a triage rule
    matches, and with any older change to the same item that is still waiting folded in, so they are read once, in
    order."""
    folded = [] if closed else _waiting_for(tx, source.id, item.key)
    if folded:
        earlier = [_read_text(ws, tx.get("source", r.data["source"]).data["content_hash"]) for r in folded]
        text = "\n\nThen:\n\n".join([*earlier, text])
    digest = _keep_text(ws, text)
    by_us = bool(item.author) and item.author.strip().lower() in {a.lower() for a in cfg.workspace.our_accounts}
    record = tx.create(
        "source",
        {
            "received_at": now.isoformat(),
            "kind": f"watched:{source.connector}",
            "title": f"{item.title}"[:120],
            "content_hash": digest,
            "trust": "untrusted",
            "projects": [source.project] if source.project else [],
            "url": item.link,
            "watched": {
                "source": source.id,
                "key": item.key,
                "change": change,
                "author": item.author,
                "by_us": by_us,
            },
        },
        _WATCHER,
    )
    data: dict[str, Any] = {
        "task": "notes",
        "source": record.id,
        "origin": "input",
        "state": "queued",
        "waiting": "With the assistant, starting now",
        "created_at": now.isoformat(),
    }
    if closed:
        data.update(state="done", waiting=f"Closed by {closed['rule']}: {closed['reason']}", auto_closed=closed)
    request = tx.create("request", data, _WATCHER)
    for older in folded:
        tx.update(
            "request",
            older.id,
            {"state": "done", "waiting": "Folded into a newer change to the same item", "folded_into": request.id},
            _WATCHER,
            read_version=older.version,
        )
    return request.id


def _waiting_for(tx: Any, source: str, key: str) -> list[Any]:
    """Requests for earlier changes to this item that the assistant hasn't started, oldest first."""
    found = []
    for request in tx.list("request"):
        if request.data["state"] != "queued" or not request.data.get("source"):
            continue
        record = tx.get("source", request.data["source"])
        watched = record.data.get("watched") if record else None
        if watched and watched["source"] == source and watched["key"] == key:
            found.append(request)
    return sorted(found, key=lambda r: str(r.data["created_at"]))


def _keep_text(ws: Any, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ws.sources_dir.mkdir(parents=True, exist_ok=True)
    path = ws.sources_dir / f"{digest}.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return digest


def _read_text(ws: Any, digest: str) -> str:
    path = ws.sources_dir / f"{digest}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _record(store: Any, source: str, now: datetime, clock: float, outcome: str, **values: Any) -> None:
    with store.transaction() as tx:
        tx.create(
            "watch_run",
            {
                "source": source,
                "started_at": now.isoformat(),
                "seconds": round(time.monotonic() - clock, 3),
                "outcome": outcome,
                **values,
            },
            WriteContext(actor="watcher", trust="trusted", op="watch.run"),
        )


WHAT_TO_DO = {
    "auth": "Sign in to it again, then it is read on its next turn.",
    "no_access": "Check what it reads (Change, on Sources), or sign in again and allow access to it.",
    "not_found": "Check that it is still there and that its settings on Sources name it right (Change).",
    "outage": "The service it is on seems to be failing; it is tried again on its schedule.",
}


def _maybe_ask(store: Any, cfg: Any, source: Any, err: ConnectorError) -> str:
    """The problem in words; at the configured count of failures in a row, one question to the person."""
    where = source.label or source.id
    problem = f"{where} can't be read: {err.detail or err.kind}. {WHAT_TO_DO.get(err.kind, '')}".strip()
    if failures_in_a_row(store, source.id) != cfg.watch.failures_before_asking:
        return problem
    pm = cfg.workspace.user.person
    if not pm or store.read().get("person", pm) is None:
        return problem
    with store.transaction() as tx:
        tx.create(
            "question",
            {
                "to": pm,
                "title": f"{where} can't be read",
                "text": problem,
                "kind": "decision",
                "resolves": {"kind": "watch", "source": source.id},
            },
            WriteContext(actor="watcher", trust="trusted", op="watch.problem"),
        )
    return problem


def _close_question(store: Any, source: str) -> None:
    """A read that works ends the question about that source."""
    open_ones = [
        q
        for q in store.read().list("question")
        if (q.data.get("resolves") or {}).get("kind") == "watch"
        and q.data["resolves"].get("source") == source
        and q.data["status"] == "open"
    ]
    if not open_ones:
        return
    with store.transaction() as tx:
        for question in open_ones:
            tx.update(
                "question",
                question.id,
                {"status": "dropped"},
                WriteContext(actor="watcher", trust="trusted", op="watch.recovered"),
                read_version=question.version,
            )


def hand_in_recent(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None = None) -> list[str]:
    """Hand the assistant what a source already holds from the recent past or near future (its `first_run_hours`
    around now) that it hasn't been handed yet: the person asks for this after a first read that only noted what was
    there. Triage rules apply as for any change. Returns the requests made. It waits for a read of the same source under
    way, and holds that source's lock while it works, so the same item is never handed in twice."""
    with _read_lock(ws, source_id):
        return _hand_in_recent(ws, store, cfg, source_id, now)


def _hand_in_recent(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None) -> list[str]:
    from engine.connectors import EventDetails, MessageDetails

    now = now or datetime.now(UTC)
    source = next((s for s in cfg.watch.sources if s.id == source_id), None)
    if source is None:
        raise StoreError(f"there is no source {source_id}")
    window = timedelta(hours=source.first_run_hours)
    handed = {
        (s.data.get("watched") or {}).get("key")
        for s in store.read().list("source")
        if (s.data.get("watched") or {}).get("source") == source_id
    }
    made = []
    for snap in store.read().find("snapshot", {"source": source_id}):
        data = snap.data
        if data.get("gone") or data["key"] in handed or not is_recent(data, None, now, window):
            continue
        item = SourceItem(
            data["key"],
            data["title"],
            _read_text(ws, data["content_hash"]),
            author=data.get("author"),
            link=data.get("link"),
            event=EventDetails(**data["event"]) if data.get("event") else None,
            message=MessageDetails(**data["message"]) if data.get("message") else None,
        )
        closed = first_match(store, cfg, _change(cfg, source, item, "new", None))
        with store.transaction() as tx:
            made.append(
                _hand_in(ws, store, tx, cfg, source, item, "new", _input_text(source, item, "new", None), now, closed)
            )
    return made
