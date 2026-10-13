"""The scheduled readable export (design 4.15, 5.0).

On the configured interval the records, the ledger and the long texts are written to the workspace's `data/` folder and
committed, with the settings, to the workspace's own git repository. Nothing is ever pushed: the export stays on this
computer. A workspace made without git has nothing to commit to, so the job does nothing there. The time of the last
attempt is kept in the workspace's private folder, so a restart doesn't write sooner than the interval, and a computer
waking from sleep catches up at once (the check is wall-clock based).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from typing import Any

from engine.config import Config
from engine.storage import Store
from engine.storage.export import commit_export, export_data
from engine.workspace import Workspace

STATUS_FILE = "export.json"
log = logging.getLogger(__name__)


def has_git(ws: Workspace) -> bool:
    return (ws.root / ".git").exists()


def due(ws: Workspace, cfg: Config, now: datetime | None = None) -> bool:
    """Whether a scheduled export should run now: the workspace has a git repository, and the last attempt is older
    than `every_minutes` (or there was none)."""
    if not has_git(ws):
        return False
    last = _load(ws).get("last_attempt")
    if not last:
        return True
    now = now or datetime.now(UTC)
    return (now - datetime.fromisoformat(last)).total_seconds() >= cfg.storage.export.every_minutes * 60


def run(ws: Workspace, store: Store, cfg: Config, now: datetime | None = None) -> bool:
    """Write the export and, when the settings say so, commit it. Returns whether anything was committed. A failed
    attempt is logged and counts as an attempt, so it is tried again after the interval, not in a loop."""
    now = now or datetime.now(UTC)
    _save(ws, {"last_attempt": now.isoformat()})
    try:
        export_data(store, ws.data_dir)
        if cfg.storage.export.commit:
            return commit_export(ws.root, "Export")
    except (OSError, subprocess.CalledProcessError):
        log.warning("The scheduled export wasn't written; it is tried again at the next interval.", exc_info=True)
    return False


def _load(ws: Workspace) -> dict[str, Any]:
    path = ws.private_dir / STATUS_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(ws: Workspace, status: dict[str, Any]) -> None:
    ws.private_dir.mkdir(parents=True, exist_ok=True)
    (ws.private_dir / STATUS_FILE).write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
