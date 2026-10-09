"""Leases: one holder at a time for a named role (the running instance, the scheduler).

A lease has an expiry that the holder keeps pushing forward with heartbeats. Another process may take it only after it
expires, or by an explicit takeover.
"""

from __future__ import annotations

import socket
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from engine.storage.store import Store

INSTANCE = "instance"


@dataclass(frozen=True)
class LeaseInfo:
    name: str
    holder: str
    host: str
    heartbeat: str
    expires: str


class LeaseHeld(Exception):
    """Someone else holds the lease and it hasn't expired."""

    def __init__(self, info: LeaseInfo):
        self.info = info
        super().__init__(
            f"This workspace is already open on {info.host} (last heartbeat {info.heartbeat}). "
            "Close it there, or run `cockpit takeover` once that copy has stopped."
        )


def _now() -> datetime:
    return datetime.now(UTC)


class Lease:
    def __init__(self, store: Store, name: str = INSTANCE, *, ttl_seconds: int = 60, holder: str | None = None):
        self.store = store
        self.name = name
        self.ttl = timedelta(seconds=ttl_seconds)
        self.holder = holder or uuid.uuid4().hex
        self.host = socket.gethostname()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def current(self) -> LeaseInfo | None:
        row = self.store.read().sql("SELECT * FROM leases WHERE name=?", (self.name,)).fetchone()
        return LeaseInfo(**dict(row)) if row else None

    def acquire(self, *, force: bool = False) -> None:
        with self.store.transaction() as tx:
            row = tx.sql("SELECT * FROM leases WHERE name=?", (self.name,)).fetchone()
            now = _now()
            if row and not force and row["holder"] != self.holder and datetime.fromisoformat(row["expires"]) > now:
                raise LeaseHeld(LeaseInfo(**dict(row)))
            tx.sql(
                "INSERT INTO leases(name, holder, host, heartbeat, expires) VALUES(?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET holder=excluded.holder, host=excluded.host, "
                "heartbeat=excluded.heartbeat, expires=excluded.expires",
                (self.name, self.holder, self.host, now.isoformat(), (now + self.ttl).isoformat()),
            )

    def heartbeat(self) -> bool:
        """Push the expiry forward. Returns False if the lease was taken over."""
        with self.store.transaction() as tx:
            now = _now()
            cur = tx.sql(
                "UPDATE leases SET heartbeat=?, expires=? WHERE name=? AND holder=?",
                (now.isoformat(), (now + self.ttl).isoformat(), self.name, self.holder),
            )
            return cur.rowcount == 1

    def release(self) -> None:
        self._stop.set()
        with self.store.transaction() as tx:
            tx.sql("DELETE FROM leases WHERE name=? AND holder=?", (self.name, self.holder))

    def keep_alive(self, on_lost: Callable[[], None] | None = None) -> None:
        """Heartbeat in the background every third of the lease time until released."""
        interval = self.ttl.total_seconds() / 3

        def run() -> None:
            while not self._stop.wait(interval):
                if not self.heartbeat():
                    if on_lost:
                        on_lost()
                    return

        self._thread = threading.Thread(target=run, name=f"lease-{self.name}", daemon=True)
        self._thread.start()
