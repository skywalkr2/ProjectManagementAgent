"""The background worker: processes queued requests one at a time and tells listeners when anything changes."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

from engine.ai.router import Router
from engine.config import Config
from engine.dispatcher import needs_you, process
from engine.storage import Store
from engine.workspace import Workspace


class Events:
    """A change counter that waiters can block on; the live-update stream reads it."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.version = 0

    def changed(self) -> None:
        with self._cond:
            self.version += 1
            self._cond.notify_all()

    def wait(self, after: int, timeout: float) -> int:
        with self._cond:
            self._cond.wait_for(lambda: self.version > after, timeout=timeout)
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

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="cockpit-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def poke(self) -> None:
        self._wake.set()

    def run_pending(self) -> int:
        """Process every queued request now. Returns how many were processed."""
        done = 0
        while not self._stop.is_set():
            queued = [r for r in self.store.read().list("request") if r.data["state"] == "queued"]
            if not queued:
                break
            try:
                process(self.ws, self.store, self.cfg, self.router_factory(), queued[0].id)
            except Exception as err:  # a failure in one request must not stop the worker
                needs_you(self.store, queued[0].id, f"Something went wrong processing this: {err}")
            done += 1
            self.events.changed()
        return done

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_pending()
            self._wake.wait(timeout=5)
            self._wake.clear()
