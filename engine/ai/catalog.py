"""Each account's model catalog (context size, prices), fetched from the provider and kept for a while.

A copy is kept in the workspace's private folder so prices survive restarts and a provider being unreachable. A failed
fetch keeps the last copy; with none, prices come only from config.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.ai.task import ModelInfo
from engine.state_file import changing, write_whole


class Catalogs:
    def __init__(self, path: Path, refresh_hours: float, clock: Callable[[], float] = time.time):
        self.path, self.refresh_seconds, self.clock = path, refresh_hours * 3600, clock
        self._cache: dict[str, dict[str, Any]] | None = None

    def model(self, provider: str, model_id: str, fetch: Callable[[], dict[str, ModelInfo]]) -> ModelInfo | None:
        """The catalog entry for one model, fetching the provider's catalog when the kept copy is missing or old."""
        entry = self._load().get(provider)
        if entry is None or self.clock() - entry.get("fetched_at", 0) > self.refresh_seconds:
            try:
                models = fetch()
            except Exception:
                models = {}
            if models:
                entry = {"fetched_at": self.clock(), "models": {k: asdict(v) for k, v in models.items()}}
                self._save(provider, entry)
        info = (entry or {}).get("models", {}).get(model_id)
        return ModelInfo(**info) if info else None

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._cache is None:
            self._cache = self._read()
        return self._cache

    def _save(self, provider: str, entry: dict[str, Any]) -> None:
        # Read again under the file's lock, so a copy kept meanwhile by another reader of the same file stays.
        with changing(self.path):
            cache = self._cache = {**(self._cache or {}), **self._read(), provider: entry}
            with contextlib.suppress(OSError):
                write_whole(self.path, json.dumps(cache))
