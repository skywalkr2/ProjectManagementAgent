"""Leases: one holder at a time for a named role (the running instance, the scheduler).

A lease has an expiry that the holder keeps pushing forward with heartbeats. Another process may take it after it
expires, at once when its holder is a process on this computer that is no longer running, or by an explicit takeover.
The holder id starts with the process id, so this computer can tell a stopped copy from one that is still open.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from engine.storage.store import Store

INSTANCE = "instance"

log = logging.getLogger(__name__)

_HOLDER_WITH_PID = re.compile(r"^(\d+)-.+$")


@dataclass(frozen=True)
class LeaseInfo:
    name: str
    holder: str
    host: str
    heartbeat: str
    expires: str


def holder_pid(holder: str) -> int | None:
    """The process id a holder id starts with, or None for an id that doesn't name one."""
    match = _HOLDER_WITH_PID.match(holder)
    return int(match.group(1)) if match else None


def process_running(pid: int) -> bool | None:
    """Whether a process with this id is running on this computer; None when this computer can't tell."""
    if pid <= 0 or sys.platform == "win32":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def process_running_for(holder: str) -> bool:
    """True when the holder id names a process that is running here."""
    pid = holder_pid(holder)
    return pid is not None and process_running(pid) is True


class LeaseHeld(Exception):
    """Someone else holds the lease and it hasn't expired."""

    def __init__(self, info: LeaseInfo):
        self.info = info
        this_computer = info.host == socket.gethostname()
        if this_computer and process_running_for(info.holder):
            text = "It is already open in another window on this computer. Close it there."
        else:
            where = "on this computer" if this_computer else f"on {info.host}"
            text = (
                f"This workspace is already open {where} (last heartbeat {info.heartbeat}). Close it there. "
                "If that copy has stopped without closing, run `cockpit takeover` to open it here."
            )
        super().__init__(text)


def _now() -> datetime:
    return datetime.now(UTC)


class Lease:
    def __init__(self, store: Store, name: str = INSTANCE, *, ttl_seconds: int = 60, holder: str | None = None):
        self.store = store
        self.name = name
        self.ttl = timedelta(seconds=ttl_seconds)
        self.holder = holder or f"{os.getpid()}-{uuid.uuid4().hex}"
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
                if not self._stopped_on_this_computer(row):
                    raise LeaseHeld(LeaseInfo(**dict(row)))
                log.info("Took over the lease %r from a copy on this computer that is no longer running.", self.name)
            tx.sql(
                "INSERT INTO leases(name, holder, host, heartbeat, expires) VALUES(?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET holder=excluded.holder, host=excluded.host, "
                "heartbeat=excluded.heartbeat, expires=excluded.expires",
                (self.name, self.holder, self.host, now.isoformat(), (now + self.ttl).isoformat()),
            )

    def _stopped_on_this_computer(self, row: Any) -> bool:
        """True when the held lease belongs to a process on this computer that is no longer running."""
        if row["host"] != self.host:
            return False
        pid = holder_pid(row["holder"])
        return pid is not None and process_running(pid) is False

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
