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
from engine.triage import classify

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


def last_read(store: Any, source: str) -> Any | None:
    """The latest run that actually read the source (not one that found no network or failed)."""
    runs = [r for r in store.read().find("watch_run", {"source": source}) if r.data["outcome"] in ("ok", "baseline")]
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


def refresh(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None = None, router: Any = None) -> Result:
    """Read one source now, compare and hand in what changed. Returns what happened. A source is never read twice at
    the same moment: when another read of it is under way this one does nothing and says so (outcome "busy"). The
    router makes the assistant's sorting run for mail the rules can't place; left out, one is made when it is needed."""
    if not any(s.id == source_id for s in cfg.watch.sources):
        raise StoreError(f"there is no source {source_id}")
    lock = _read_lock(ws, source_id)
    if not lock.acquire(blocking=False):
        return Result(source_id, "busy", note=ALREADY_READING)
    try:
        return _refresh(ws, store, cfg, source_id, now, router)
    finally:
        lock.release()


def _refresh(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None, router: Any = None) -> Result:
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
    result = _compare(ws, store, cfg, source, poll, now, baseline, recent, router)
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


@dataclass
class _Entry:
    """One item of a read that is new or changed: what the read found, and how the rules placed it."""

    item: SourceItem
    digest: str
    before: Any
    details: dict[str, Any]
    change: str
    old: str | None
    closed: dict[str, str] | None
    handed: bool  # it is handed in now, not only noted


def _compare(
    ws: Any,
    store: Any,
    cfg: Any,
    source: Any,
    poll: Any,
    now: datetime,
    baseline: bool,
    recent: timedelta | None = None,
    router: Any = None,
) -> Result:
    result = Result(source.id, "ok")
    seen = {s.data["key"]: s for s in store.read().find("snapshot", {"source": source.id}) if not s.data["gone"]}
    listed = set()
    entries: list[_Entry] = []
    unplaced: dict[str, dict[str, Any]] = {}
    for item in poll.items:
        listed.add(item.key)
        digest = _keep_text(ws, item.text)
        before = seen.get(item.key)
        if before is not None and before.data.get("deleted"):
            continue  # the person had its content deleted; only its marker is kept, so it isn't handed in again
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
        closed, kept = classify(store, cfg, facts)
        handed = not baseline or (recent is not None and is_recent(details, item.changed_at, now, recent))
        if closed is None and not kept:
            closed = _carried_sorting(before)
        if handed and closed is None and not kept and before is None and item.message is not None:
            unplaced[item.key] = facts
        entries.append(_Entry(item, digest, before, details, change, old, closed, handed))
    marks, result.note = _assistant_sorted(ws, store, cfg, source, router, unplaced)
    for entry in entries:
        item, before, closed = entry.item, entry.before, entry.closed or marks.get(entry.item.key)
        with store.transaction() as tx:
            data = {
                "source": source.id,
                "key": item.key,
                "title": item.title,
                "content_hash": entry.digest,
                "author": item.author,
                "seen_at": now.isoformat(),
                **entry.details,
                "closed_by": closed["rule"] if closed and not closed.get("section") else None,
                "set_aside": _set_aside_of(closed) or _kept_set_aside(before),
            }
            if before is None:
                tx.create("snapshot", data, _WATCHER)
            else:
                tx.update("snapshot", before.id, data, _WATCHER, read_version=before.version)
            if not entry.handed:
                continue
            text = _input_text(source, item, entry.change, entry.old)
            request = _hand_in(ws, store, tx, cfg, source, item, entry.change, text, now, closed)
        (result.new if entry.change == "new" else result.changed).append(request)
    gone_keys = [k for k in seen if k not in listed] if poll.complete else [k for k in poll.removed if k in seen]
    for key in gone_keys:
        snapshot = seen[key]
        with store.transaction() as tx:
            tx.update("snapshot", snapshot.id, {"gone": True}, _WATCHER, read_version=snapshot.version)
            if baseline or not source.report_removed:
                continue
            gone = SourceItem(
                key, snapshot.data["title"], "", author=None, message=_message_of(snapshot.data.get("message"))
            )
            text = f"{snapshot.data['title']} is no longer in {source.label or source.id}."
            facts = _change(cfg, source, gone, "removed", _read_text(ws, snapshot.data["content_hash"]))
            closed = classify(store, cfg, facts)[0]
            result.removed.append(_hand_in(ws, store, tx, cfg, source, gone, "removed", text, now, closed))
    return result


def _assistant_sorted(
    ws: Any, store: Any, cfg: Any, source: Any, router: Any, unplaced: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, str]], str | None]:
    """The assistant's sorting (design 6.5, step 3) of the mail the rules couldn't place, as {item key: facts}: one
    run per batch of headers, never the text. Returns, by item key, the set-aside match of each message it set aside,
    and a note when some mail wasn't sorted by it (that mail is handed in as work)."""
    from engine import mail_sorting
    from engine.set_aside import SECTION_WORDS

    if cfg.watch.sorting != "ai" or not unplaced:
        return {}, None
    sorted_ = mail_sorting.sort(
        ws,
        store,
        cfg,
        router,
        [mail_sorting.header_of(key, facts) for key, facts in unplaced.items()],
        data_level_of(cfg, source),
    )
    marks = {
        key: {
            "rule": mail_sorting.RULE,
            "reason": f"the assistant sorted it as {SECTION_WORDS[section]}",
            "section": section,
            "by": "assistant",
        }
        for key, section in sorted_.sections.items()
    }
    return marks, sorted_.note


def _carried_sorting(before: Any) -> dict[str, str] | None:
    """What the assistant set aside stays set aside when the item changes: its mark, as a match."""
    mark = before.data.get("set_aside") if before is not None else None
    if mark and mark.get("by") == "assistant" and mark.get("section"):
        return {"rule": mark["rule"], "reason": mark["reason"], "section": mark["section"], "by": "assistant"}
    return None


def _input_text(source: Any, item: SourceItem, change: str, old: str | None) -> str:
    where = source.label or source.id
    if change == "new":
        return f"New in {where}: {item.title}\n\n{item.text}"
    diff = difflib.unified_diff(
        (old or "").splitlines(), item.text.splitlines(), "before", "now", n=CONTEXT_LINES, lineterm=""
    )
    shown = "\n".join(list(diff)[2:])
    return f"Changed in {where}: {item.title}\n\nWhat changed:\n{shown}\n\nIt now reads:\n{item.text}"


def _message_dict(message: Any) -> dict[str, Any] | None:
    """A message's details as plain data, the way the snapshot keeps them (categories and participants as lists)."""
    from dataclasses import asdict

    if message is None:
        return None
    return {**asdict(message), "categories": list(message.categories), "participants": list(message.participants)}


def _set_aside_of(closed: dict[str, str] | None) -> dict[str, str] | None:
    """A match that sets mail aside, as the snapshot keeps it: {section, rule, reason}, and `by` when the assistant's
    sorting made it."""
    if not closed or not closed.get("section"):
        return None
    mark = {"section": closed["section"], "rule": closed["rule"], "reason": closed["reason"]}
    return {**mark, "by": closed["by"]} if closed.get("by") else mark


def _kept_set_aside(before: Any) -> dict[str, str] | None:
    """What the person set aside by hand stays set aside when the item changes."""
    mark = before.data.get("set_aside") if before is not None else None
    return mark if mark and mark.get("by") == "person" else None


def data_level_of(cfg: Any, source: Any) -> str:
    """How sensitive what a watched source holds is: the source's own setting, else the one for its kind of source,
    else the default for all sources."""
    return source.data_level or cfg.watch.connector_data_levels.get(source.connector) or cfg.watch.default_data_level


def _details(item: SourceItem) -> dict[str, Any]:
    """What a calendar or mail item is, as the snapshot keeps it."""
    from dataclasses import asdict

    return {
        "link": item.link,
        "changed_at": item.changed_at,
        "event": asdict(item.event) if item.event is not None else None,
        "message": _message_dict(item.message),
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
        "message": _message_dict(item.message),
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
    received = item.message.received if item.message is not None and item.message.received else None
    by_us = bool(item.author) and item.author.strip().lower() in {a.lower() for a in cfg.workspace.our_accounts}
    record = tx.create(
        "source",
        {
            "received_at": received or now.isoformat(),
            "kind": f"watched:{source.connector}",
            "title": f"{item.title}"[:120],
            "content_hash": digest,
            "trust": "untrusted",
            "projects": [source.project] if source.project else [],
            "sensitivity": data_level_of(cfg, source),
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
    if closed and closed.get("section"):
        data.update(
            state="done",
            waiting=f"Set aside: {closed['reason']}",
            set_aside=_set_aside_of(closed),
        )
    elif closed:
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


def hand_in_recent(
    ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None = None, router: Any = None
) -> list[str]:
    """Hand the assistant what a source already holds from the recent past or near future (its `first_run_hours`
    around now) that it hasn't been handed yet: the person asks for this after a first read that only noted what was
    there. Triage rules and the assistant's sorting of mail apply as for any change. Returns the requests made. It
    waits for a read of the same source under way, and holds that source's lock while it works, so the same item is
    never handed in twice."""
    with _read_lock(ws, source_id):
        return _hand_in_recent(ws, store, cfg, source_id, now, router)


def hand_in_snapshot(ws: Any, store: Any, cfg: Any, snapshot_id: str, now: datetime | None = None) -> str | None:
    """Hand the assistant an item the source holds that was never handed in (it was noted on a first read, or set
    aside), whatever its age. Returns the request made, or None when the item or its source isn't there."""
    snap = store.read().get("snapshot", snapshot_id)
    source = next((s for s in cfg.watch.sources if snap is not None and s.id == snap.data["source"]), None)
    if snap is None or source is None or snap.data.get("deleted"):
        return None
    data = snap.data
    from engine.connectors import EventDetails

    item = SourceItem(
        data["key"],
        data["title"],
        _read_text(ws, data["content_hash"]),
        author=data.get("author"),
        changed_at=data.get("changed_at"),
        link=data.get("link"),
        event=EventDetails(**data["event"]) if data.get("event") else None,
        message=_message_of(data.get("message")),
    )
    with _read_lock(ws, source.id), store.transaction() as tx:
        return _hand_in(
            ws,
            store,
            tx,
            cfg,
            source,
            item,
            "new",
            _input_text(source, item, "new", None),
            now or datetime.now(UTC),
            None,
        )


def _message_of(details: dict[str, Any] | None) -> Any:
    """A snapshot's kept message details as the connector's own type."""
    from engine.connectors import MessageDetails

    if not details:
        return None
    return MessageDetails(**{**details, "categories": tuple(details.get("categories") or ())})


def _hand_in_recent(
    ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None, router: Any = None
) -> list[str]:
    from engine.connectors import EventDetails

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
    pending: list[tuple[Any, SourceItem, dict[str, str] | None]] = []
    unplaced: dict[str, dict[str, Any]] = {}
    for snap in store.read().find("snapshot", {"source": source_id}):
        data = snap.data
        if data.get("gone") or data.get("deleted") or data.get("set_aside") or data["key"] in handed:
            continue
        if not is_recent(data, data.get("changed_at"), now, window):
            continue
        item = SourceItem(
            data["key"],
            data["title"],
            _read_text(ws, data["content_hash"]),
            author=data.get("author"),
            changed_at=data.get("changed_at"),
            link=data.get("link"),
            event=EventDetails(**data["event"]) if data.get("event") else None,
            message=_message_of(data.get("message")),
        )
        facts = _change(cfg, source, item, "new", None)
        closed, kept = classify(store, cfg, facts)
        if closed is None and not kept and item.message is not None:
            unplaced[item.key] = facts
        pending.append((snap, item, closed))
    marks, _note = _assistant_sorted(ws, store, cfg, source, router, unplaced)
    made = []
    for snap, item, closed in pending:
        sorted_aside = marks.get(item.key) if closed is None else None
        with store.transaction() as tx:
            if sorted_aside:
                tx.update(
                    "snapshot", snap.id, {"set_aside": _set_aside_of(sorted_aside)}, _WATCHER, read_version=snap.version
                )
            made.append(
                _hand_in(
                    ws,
                    store,
                    tx,
                    cfg,
                    source,
                    item,
                    "new",
                    _input_text(source, item, "new", None),
                    now,
                    closed or sorted_aside,
                )
            )
    return made
