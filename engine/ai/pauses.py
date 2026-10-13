"""Accounts paused until a usage limit resets (design 6.16, 8.6).

A pause is kept in the workspace's private folder, so it holds across a restart. An account that is paused is not called
until its reset; work that needs it waits, and the router uses another account in the tier's chain when one is allowed.
Nothing here calls a provider or reads a provider's words: the reset time comes from the adapter's classified error.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.today import zone

_LOCK = threading.Lock()


def pauses_path(store: Any) -> Path:
    """Where the workspace keeps its pauses."""
    return store.path.parent / ".cockpit" / "ai-pauses.json"


class Pauses:
    def __init__(self, path: Path, now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.path = path
        self.now = now

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return (
            {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(data, dict)
            else {}
        )

    def _save(self, data: dict[str, str]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def active(self) -> dict[str, datetime]:
        """The accounts paused now and when each one's limit resets. A pause whose time has passed is dropped."""
        now = self.now()
        live: dict[str, datetime] = {}
        for account, stamp in self._load().items():
            try:
                until = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if until.tzinfo is None:
                until = until.replace(tzinfo=UTC)
            if until > now:
                live[account] = until
        return live

    def until(self, account: str) -> datetime | None:
        return self.active().get(account)

    def pause(self, account: str, until: datetime) -> None:
        """Leave an account alone until `until`. A later reset replaces an earlier one; a pause never gets shorter."""
        with _LOCK:
            data = {k: v.isoformat() for k, v in self.active().items()}
            current = data.get(account)
            if current is None or datetime.fromisoformat(current) < until:
                data[account] = until.isoformat()
            self._save(data)

    def clear(self, account: str | None = None) -> None:
        """Lift one account's pause, or every pause."""
        with _LOCK:
            data = {} if account is None else {k: v.isoformat() for k, v in self.active().items() if k != account}
            self._save(data)


def when_text(cfg: Any, until: datetime, now: datetime) -> str:
    """A time in the person's time zone in plain words: the time alone today, otherwise the day and the time."""
    here = zone(cfg)
    local, today = until.astimezone(here), now.astimezone(here).date()
    clock = f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"
    if local.date() == today:
        return clock
    return f"{local.strftime(cfg.language.messages.date_format)} at {clock}"


def waiting_text(cfg: Any, account: str, until: datetime, now: datetime) -> str:
    """What work waits on while an account's limit is not yet reset."""
    return f"Waiting for {account}'s limit to reset at {when_text(cfg, until, now)}"
