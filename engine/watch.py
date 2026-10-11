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
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from engine.connectors import CORE, Connector, ConnectorContext, ConnectorError, SourceItem
from engine.storage import StoreError, WriteContext

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
        if started is None or now - started >= timedelta(minutes=source.every_minutes):
            found.append(source.id)
    return found


def failures_in_a_row(store: Any, source: str) -> int:
    count = 0
    for run in reversed(store.read().find("watch_run", {"source": source})):
        if run.data["outcome"] == "offline":
            continue
        if run.data["outcome"] != "failed":
            break
        count += 1
    return count


def refresh(ws: Any, store: Any, cfg: Any, source_id: str, now: datetime | None = None) -> Result:
    """Read one source now, compare and hand in what changed. Returns what happened."""
    now = now or datetime.now(UTC)
    clock = time.monotonic()
    source = next((s for s in cfg.watch.sources if s.id == source_id), None)
    if source is None:
        raise StoreError(f"there is no source {source_id} in watch.yaml")
    last = last_run(store, source.id)
    state = dict(last.data.get("state") or {}) if last and last.data["outcome"] in ("ok", "baseline") else {}
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
        outcome = "offline" if err.kind == "offline" else "failed"
        _record(
            store,
            source.id,
            now,
            clock,
            outcome,
            error_kind=None if outcome == "offline" else err.kind,
            error=err.detail or None,
        )
        problem = None
        if outcome == "failed":
            problem = _maybe_ask(store, cfg, source, err)
        return Result(source.id, outcome, problem=problem)
    read_before = any(
        r.data["outcome"] in ("ok", "baseline") for r in store.read().find("watch_run", {"source": source.id})
    )
    baseline = not read_before and source.first_run == "baseline"
    result = _compare(ws, store, cfg, source, poll, now, baseline)
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


def _compare(ws: Any, store: Any, cfg: Any, source: Any, poll: Any, now: datetime, baseline: bool) -> Result:
    result = Result(source.id, "ok")
    seen = {s.data["key"]: s for s in store.read().find("snapshot", {"source": source.id}) if not s.data["gone"]}
    listed = set()
    for item in poll.items:
        listed.add(item.key)
        digest = _keep_text(ws, item.text)
        before = seen.get(item.key)
        if before is not None and before.data["content_hash"] == digest:
            continue
        change = "new" if before is None else "changed"
        with store.transaction() as tx:
            data = {
                "source": source.id,
                "key": item.key,
                "title": item.title,
                "content_hash": digest,
                "author": item.author,
                "seen_at": now.isoformat(),
            }
            if before is None:
                tx.create("snapshot", data, _WATCHER)
            else:
                tx.update("snapshot", before.id, data, _WATCHER, read_version=before.version)
            if baseline:
                continue
            old = _read_text(ws, before.data["content_hash"]) if before is not None else None
            request = _hand_in(ws, tx, cfg, source, item, change, _input_text(source, item, change, old), now)
        if not baseline:
            (result.new if change == "new" else result.changed).append(request)
    if poll.complete and not baseline:
        for key, snapshot in seen.items():
            if key in listed:
                continue
            with store.transaction() as tx:
                tx.update("snapshot", snapshot.id, {"gone": True}, _WATCHER, read_version=snapshot.version)
                if not source.report_removed:
                    continue
                gone = SourceItem(key, snapshot.data["title"], "", author=None)
                text = f"{snapshot.data['title']} is no longer in {source.label or source.id}."
                result.removed.append(_hand_in(ws, tx, cfg, source, gone, "removed", text, now))
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


def _hand_in(ws: Any, tx: Any, cfg: Any, source: Any, item: SourceItem, change: str, text: str, now: datetime) -> str:
    """Save the input's text and queue it for the assistant, as outside content."""
    digest = _keep_text(ws, text)
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
            "watched": {"source": source.id, "key": item.key, "change": change, "author": item.author},
        },
        _WATCHER,
    )
    request = tx.create(
        "request",
        {
            "task": "notes",
            "source": record.id,
            "origin": "input",
            "state": "queued",
            "waiting": "With the assistant, starting now",
            "created_at": now.isoformat(),
        },
        _WATCHER,
    )
    return request.id


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
    "no_access": "Check its settings in watch.yaml, or ask for access to it.",
    "not_found": "Check that it is still there and that watch.yaml names it right.",
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
