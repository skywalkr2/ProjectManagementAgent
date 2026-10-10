"""Full backups to somewhere off this computer (design 4.15, 5.0).

A backup is a consistent copy of the database (SQLite's online backup), the config and the saved sources, in a dated
folder in each configured target. Older backups beyond `keep` are removed. The result of the last attempt per target is
kept in the workspace's private folder, so the app can show the age of the last backup and nag until one succeeds.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.config import Config
from engine.workspace import Workspace

STATUS_FILE = "backups.json"


@dataclass(frozen=True)
class BackupState:
    configured: bool
    last_success: str | None
    age_hours: float | None
    needs_attention: bool
    message: str
    last_error: str | None = None


def run_backup(ws: Workspace, cfg: Config, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    status = _load(ws)
    for target in cfg.storage.backups.targets:
        key = target.path
        try:
            base = Path(target.path).expanduser()
            if base.resolve().is_relative_to(ws.root.resolve()):
                raise ValueError("the backup folder is inside the workspace, so it isn't a copy somewhere else")
            dest = base / f"{ws.root.name}-{stamp}"
            dest.mkdir(parents=True, exist_ok=False)
            src = sqlite3.connect(ws.db_path)
            dst = sqlite3.connect(dest / "cockpit.db")
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            for name in ("config", "sources", "files"):
                if (ws.root / name).is_dir():
                    shutil.copytree(ws.root / name, dest / name)
            _prune(base, ws.root.name, cfg.storage.backups.keep)
            status[key] = {"last_success": now.isoformat(), "last_error": None, "label": target.label}
        except (OSError, ValueError, sqlite3.Error) as err:
            prev = status.get(key, {})
            status[key] = {"last_success": prev.get("last_success"), "last_error": str(err), "label": target.label}
    _save(ws, status)
    return status


def state(ws: Workspace, cfg: Config, now: datetime | None = None) -> BackupState:
    now = now or datetime.now(UTC)
    targets = cfg.storage.backups.targets
    if not targets:
        return BackupState(False, None, None, True, "No off-device backup is set up.")
    status = _load(ws)
    errors = [s["last_error"] for t in targets if (s := status.get(t.path)) and s.get("last_error")]
    successes = [s["last_success"] for t in targets if (s := status.get(t.path)) and s.get("last_success")]
    if not successes:
        why = f" The last try failed: {errors[0]}" if errors else ""
        return BackupState(True, None, None, True, "No backup has succeeded yet." + why, errors[0] if errors else None)
    last = max(successes)
    age = (now - datetime.fromisoformat(last)).total_seconds() / 3600
    stale = age > 2 * cfg.storage.backups.every_hours
    message = f"Backed up {_ago(age)}." + (" That's overdue." if stale else "")
    return BackupState(True, last, round(age, 2), stale, message, errors[0] if errors else None)


def _ago(hours: float) -> str:
    if hours < 1:
        return "less than an hour ago"
    if hours < 48:
        return f"{int(hours)} h ago"
    return f"{int(hours // 24)} days ago"


def _prune(base: Path, name: str, keep: int) -> None:
    copies = sorted(p for p in base.glob(f"{name}-*") if p.is_dir())
    for old in copies[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def _load(ws: Workspace) -> dict[str, Any]:
    path = ws.private_dir / STATUS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(ws: Workspace, status: dict[str, Any]) -> None:
    ws.private_dir.mkdir(parents=True, exist_ok=True)
    (ws.private_dir / STATUS_FILE).write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
