"""The background worker: processes queued requests one at a time, makes scheduled backups, and tells listeners when
anything changes."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

from engine.ai.router import Router
from engine.config import Config
from engine.dispatcher import needs_you, process
from engine.storage import Store, WriteContext
from engine.workspace import Workspace

CODE_ROOTS = (Path(__file__).resolve().parent, Path(__file__).resolve().parents[1] / "api")
log = logging.getLogger(__name__)
RESTART_NEEDED = "Settings or code changed since the cockpit started; restart it to use them."


def config_fingerprint(ws: Workspace) -> str:
    """A hash of the workspace's config files, to notice edits made while the process runs."""
    digest = hashlib.sha256()
    for path in sorted(ws.config_dir.rglob("*.yaml")):
        digest.update(str(path.relative_to(ws.config_dir)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def code_fingerprint() -> str:
    """The newest modification time of the running program's own source files."""
    newest = max((p.stat().st_mtime for root in CODE_ROOTS if root.is_dir() for p in root.rglob("*.py")), default=0.0)
    return repr(newest)


class Events:
    """A change counter that waiters can block on; the live-update stream reads it."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.version = 0
        self.closed = False

    def close(self) -> None:
        """Release every waiter and make later waits return at once, so live streams can end."""
        with self._cond:
            self.closed = True
            self._cond.notify_all()

    def changed(self) -> None:
        with self._cond:
            self.version += 1
            self._cond.notify_all()

    def wait(self, after: int, timeout: float) -> int:
        with self._cond:
            self._cond.wait_for(lambda: self.version > after or self.closed, timeout=timeout)
            return self.version


class Worker:
    def __init__(
        self,
        ws: Workspace,
        store: Store,
        cfg: Config,
        events: Events,
        router_factory: Callable[[], Router] | None = None,
    ):
        self.ws, self.store, self.cfg, self.events = ws, store, cfg, events
        self.router_factory = router_factory or (lambda: Router(cfg, store, env=os.environ))
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._backups: threading.Thread | None = None
        self._started_with = (config_fingerprint(ws), code_fingerprint())
        self.restart_needed: str | None = None

    def _changed_since_start(self) -> bool:
        """Old code never runs new settings: once config or code changed, no new job starts in this process."""
        if self.restart_needed is None and (config_fingerprint(self.ws), code_fingerprint()) != self._started_with:
            self.restart_needed = RESTART_NEEDED
        return self.restart_needed is not None

    def _hold_queued(self) -> None:
        ctx = WriteContext(actor="engine", trust="trusted", op="worker.hold")
        held = False
        with self.store.transaction() as tx:
            for r in tx.list("request"):
                if r.data["state"] == "queued" and r.data.get("waiting") != RESTART_NEEDED:
                    tx.update("request", r.id, {"waiting": RESTART_NEEDED}, ctx, read_version=r.version)
                    held = True
        if held:
            self.events.changed()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="cockpit-worker", daemon=True)
        self._thread.start()
        self._backups = threading.Thread(target=self._backup_loop, name="cockpit-backups", daemon=True)
        self._backups.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)
        if self._backups:
            self._backups.join(timeout=60)

    def poke(self) -> None:
        self._wake.set()

    def run_pending(self) -> int:
        """Process every queued request now. Returns how many were processed."""
        done = 0
        while not self._stop.is_set():
            queued = [r for r in self.store.read().list("request") if r.data["state"] == "queued"]
            if not queued:
                break
            if self._changed_since_start():
                self._hold_queued()
                break
            try:
                process(self.ws, self.store, self.cfg, self.router_factory(), queued[0].id)
            except Exception as err:  # a failure in one request must not stop the worker
                needs_you(self.store, queued[0].id, f"Something went wrong processing this: {err}")
            done += 1
            self.events.changed()
        if not self._stop.is_set() and not self._changed_since_start():
            from engine.stages import move_ready_records

            if move_ready_records(self.store):
                self.events.changed()
        return done

    def backup_if_due(self) -> bool:
        """Make a scheduled backup when one is due. On its own thread, so a large copy never holds up other work."""
        from engine.backup import due, run_backup

        if not due(self.ws, self.cfg):
            return False
        run_backup(self.ws, self.cfg)
        self.events.changed()
        return True

    def _backup_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.backup_if_due()
            except Exception:  # a failed backup is recorded by run_backup; nothing here may stop the thread
                log.exception("scheduled backup failed")
            self._stop.wait(timeout=60)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_pending()
            self._wake.wait(timeout=5)
            self._wake.clear()
