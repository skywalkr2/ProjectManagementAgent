"""Full backups to somewhere off this computer (design 4.15, 5.0).

A backup is a consistent copy of the database (SQLite's online backup), the config and the saved sources, in a dated
folder in each configured target. Older backups beyond `keep` are removed. The result of the last attempt per target is
kept in the workspace's private folder, so the app can show the age of the last backup and nag until one succeeds.

When `storage.backups.encrypt` names a key, every file of every copy is encrypted (`engine/backup_crypto.py`) and the
copy's folder says so; restoring one needs the key, and a wrong key is refused before anything is written.

A backup folder can be made into a new workspace (`restore_backup`): its database is checked first, nothing is written
into a folder that already has files, and the backup itself is never changed.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine import backup_crypto
from engine.config import Config
from engine.secrets import SecretError, resolve_secret
from engine.state_file import write_whole
from engine.workspace import WORKSPACE_GITIGNORE, Workspace

#: The folders a backup holds beside its database, copied into a restored workspace.
BACKUP_FOLDERS = ("config", "sources", "files", "texts", "plugin-data")
STATUS_FILE = "backups.json"
#: One backup at a time per process, whether started on schedule or on request.
_RUNNING = threading.Lock()


@dataclass(frozen=True)
class BackupState:
    configured: bool
    last_success: str | None
    age_hours: float | None
    needs_attention: bool
    message: str
    last_error: str | None = None
    encrypted: bool = False


def run_backup(ws: Workspace, cfg: Config, now: datetime | None = None) -> dict[str, Any]:
    with _RUNNING:
        return _run(ws, cfg, now or datetime.now(UTC))


def due(ws: Workspace, cfg: Config, now: datetime | None = None) -> bool:
    """Whether a scheduled backup should run now: some target's last success is older than `every_hours` (or there is
    none), and its last try is older than `retry_minutes`. Wall-clock based, so a computer waking from sleep catches up
    at once."""
    settings = cfg.storage.backups
    if not settings.automatic or not settings.targets:
        return False
    now = now or datetime.now(UTC)
    status = _load(ws)
    for target in settings.targets:
        entry = status.get(target.path, {})
        success, attempt = entry.get("last_success"), entry.get("last_attempt")
        if success and _hours(now, success) < settings.every_hours:
            continue
        if attempt and _hours(now, attempt) * 60 < settings.retry_minutes:
            continue
        return True
    return False


def _free_folder(base: Path, name: str) -> Path:
    """The dated folder for a backup: two backups in the same second get -2, -3 … rather than refusing each other."""
    path = base / name
    n = 2
    while path.exists():
        path = base / f"{name}-{n}"
        n += 1
    return path


def _hours(now: datetime, stamp: str) -> float:
    return (now - datetime.fromisoformat(stamp)).total_seconds() / 3600


def _run(ws: Workspace, cfg: Config, now: datetime) -> dict[str, Any]:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    status = _load(ws)
    secret: str | None = None
    if cfg.storage.backups.encrypt:
        # With a key set, a backup is never made without it: a key that can't be read fails every target.
        try:
            secret = resolve_secret(cfg.storage.backups.encrypt) or ""
            if not secret.strip():
                raise SecretError("the key for encrypting backups is empty")
        except SecretError as err:
            for target in cfg.storage.backups.targets:
                prev = status.get(target.path, {})
                status[target.path] = {
                    "last_success": prev.get("last_success"),
                    "last_attempt": now.isoformat(),
                    "last_error": f"the key for encrypting backups can't be read: {err}",
                    "label": target.label,
                }
            _save(ws, status)
            return status
    for target in cfg.storage.backups.targets:
        key = target.path
        try:
            base = Path(target.path).expanduser()
            if base.resolve().is_relative_to(ws.root.resolve()):
                raise ValueError("the backup folder is inside the workspace, so it isn't a copy somewhere else")
            if not base.is_dir():
                # Never create it: a drive that isn't connected would otherwise get a folder on this computer's disk.
                raise ValueError(f"{base} isn't there; connect the drive or check the folder")
            dest = _free_folder(base, f"{ws.root.name}-{stamp}")
            dest.mkdir(exist_ok=False)
            if secret is None:
                _copy(ws, dest)
            else:
                _copy_encrypted(ws, dest, secret)
            _prune(base, ws.root.name, cfg.storage.backups.keep)
            status[key] = {
                "last_success": now.isoformat(),
                "last_attempt": now.isoformat(),
                "last_error": None,
                "label": target.label,
            }
        except (OSError, ValueError, sqlite3.Error) as err:
            prev = status.get(key, {})
            status[key] = {
                "last_success": prev.get("last_success"),
                "last_attempt": now.isoformat(),
                "last_error": str(err),
                "label": target.label,
            }
    _save(ws, status)
    return status


def _database_copy(ws: Workspace, path: Path) -> None:
    """A consistent copy of the database at `path`, made with SQLite's online backup."""
    src = sqlite3.connect(ws.db_path)
    dst = sqlite3.connect(path)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()


def _copy(ws: Workspace, dest: Path) -> None:
    _database_copy(ws, dest / "cockpit.db")
    for name in BACKUP_FOLDERS:
        if (ws.root / name).is_dir():
            shutil.copytree(ws.root / name, dest / name)


def _copy_encrypted(ws: Workspace, dest: Path, secret: str) -> None:
    """The same copy with every file sealed. The database is copied to a temporary folder first (inside the workspace's
    private folder, which stays on this computer) and removed as soon as it is sealed."""
    sealer, manifest = backup_crypto.create(secret)
    backup_crypto.write_manifest(dest, manifest)
    ws.private_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ws.private_dir, prefix="backup-") as temporary:
        plain = Path(temporary) / "cockpit.db"
        _database_copy(ws, plain)
        sealer.seal(plain, dest / "cockpit.db", "cockpit.db")
    for name in BACKUP_FOLDERS:
        if (ws.root / name).is_dir():
            backup_crypto.seal_tree(sealer, ws.root / name, dest / name, name)


def state(ws: Workspace, cfg: Config, now: datetime | None = None) -> BackupState:
    now = now or datetime.now(UTC)
    targets = cfg.storage.backups.targets
    encrypted = bool(cfg.storage.backups.encrypt)
    if not targets:
        return BackupState(False, None, None, True, "No backup on another device is set up.", encrypted=encrypted)
    status = _load(ws)
    errors = [s["last_error"] for t in targets if (s := status.get(t.path)) and s.get("last_error")]
    successes = [s["last_success"] for t in targets if (s := status.get(t.path)) and s.get("last_success")]
    if not successes:
        why = f" The last try failed: {errors[0]}" if errors else ""
        return BackupState(
            True, None, None, True, "No successful backup yet." + why, errors[0] if errors else None, encrypted
        )
    last = max(successes)
    age = (now - datetime.fromisoformat(last)).total_seconds() / 3600
    stale = age > 2 * cfg.storage.backups.every_hours
    message = f"Backed up {_ago(age)}." + (" That's overdue." if stale else "")
    message += " Encrypted." if encrypted else ""
    return BackupState(True, last, round(age, 2), stale, message, errors[0] if errors else None, encrypted)


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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(ws: Workspace, status: dict[str, Any]) -> None:
    write_whole(ws.private_dir / STATUS_FILE, json.dumps(status, indent=2, sort_keys=True) + "\n")


# ---- restoring a whole backup ----------------------------------------------------------------------------------------


class RestoreError(Exception):
    """A backup can't be made into a workspace; the message says why and nothing was written."""


class KeyNeeded(RestoreError):
    """The backup is encrypted and no key was given."""


@dataclass(frozen=True)
class Restored:
    workspace: Workspace
    records: int
    ledger: int


def restore_backup(source: Path, target: Path, key: str | None = None) -> Restored:
    """Make a new workspace in `target` from one dated backup folder. The backup's database is checked first, the copy
    is made with SQLite's online backup, and the copy must open as a workspace. Locks held by the computer that made
    the backup are dropped, so the restored workspace opens here. An encrypted backup needs `key`, the secret it was
    made with: a missing one raises `KeyNeeded` and a wrong one is refused, before anything is written. Raises
    `RestoreError` and leaves the target as it was when anything fails; the source is only ever read."""
    source = Path(source).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    database = source / "cockpit.db"
    if not database.is_file():
        raise RestoreError(f"{source} isn't a backup of a workspace: it has no database.")
    sealer = _sealer(source, key)
    if target == source or source in target.parents:
        raise RestoreError("The new folder can't be inside the backup. Choose another folder.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise RestoreError(f"{target} isn't empty. Choose a new folder to restore into.")
    if sealer is None:
        _check_database(database)
    existed = target.is_dir()
    target.mkdir(parents=True, exist_ok=True)
    try:
        if sealer is None:
            return _restore(source, target)
        # The opened copy lives in a temporary folder beside the new workspace and is removed whatever happens.
        with tempfile.TemporaryDirectory(dir=target.parent, prefix=".restore-") as temporary:
            opened = Path(temporary)
            try:
                backup_crypto.open_tree(sealer, source, opened)
            except backup_crypto.BackupDamaged as err:
                raise RestoreError(f"The backup can't be restored: {err}.") from None
            _check_database(opened / "cockpit.db")
            return _restore(opened, target)
    except Exception as err:
        _undo(target, existed)
        if isinstance(err, RestoreError):
            raise
        raise RestoreError(f"The backup couldn't be restored: {err}") from err


def _sealer(source: Path, key: str | None) -> backup_crypto.Sealer | None:
    """The key for an encrypted backup folder; None for a backup that isn't encrypted."""
    if not backup_crypto.encrypted(source):
        return None
    if key is None or not key.strip():
        raise KeyNeeded("This backup is encrypted, so restoring it needs the key it was made with.")
    try:
        return backup_crypto.open_backup(source, key)
    except backup_crypto.BackupKeyError:
        raise RestoreError(
            "That key doesn't open this backup. Use the key the backup was made with; nothing was restored."
        ) from None
    except backup_crypto.BackupDamaged as err:
        raise RestoreError(f"The backup can't be restored: {err}.") from None


def _read_only(path: Path) -> sqlite3.Connection:
    """The backup's database, opened so that nothing is created or changed beside it."""
    return sqlite3.connect(f"{path.as_uri()}?immutable=1", uri=True)


def _check_database(path: Path) -> None:
    """Refuse a file that isn't a workspace's database or doesn't pass SQLite's own integrity check."""
    try:
        conn = _read_only(path)
        try:
            verdict = [row[0] for row in conn.execute("PRAGMA integrity_check")]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.Error as err:
        raise RestoreError(f"The backup's database can't be read, so it can't be restored ({err}).") from None
    if verdict != ["ok"]:
        raise RestoreError(f"The backup's database is damaged, so it can't be restored ({verdict[0]}).")
    if not {"records", "ledger"} <= tables:
        raise RestoreError("The backup's database isn't a workspace's, so it can't be restored.")


def _restore(source: Path, target: Path) -> Restored:
    from engine.storage import Store
    from engine.storage.export import commit_export, export_data

    src = _read_only(source / "cockpit.db")
    dst = sqlite3.connect(target / "cockpit.db")
    try:
        with dst:
            src.backup(dst)
        with dst:
            dst.execute("DELETE FROM leases")  # the old computer's hold on the workspace ends here
    finally:
        src.close()
        dst.close()
    for name in BACKUP_FOLDERS:
        if (source / name).is_dir():
            shutil.copytree(source / name, target / name)
    ws = Workspace(target)
    ws.config_dir.mkdir(exist_ok=True)
    ws.sources_dir.mkdir(exist_ok=True)
    (target / ".gitignore").write_text(WORKSPACE_GITIGNORE, encoding="utf-8")
    cfg = ws.config()  # the workspace's own settings must load, as they do for `cockpit serve`
    store = Store(ws.db_path, cfg=cfg)
    try:
        records = sum(len(store.read().list(kind)) for kind in store.read().kinds())
        ledger = store.read().sql("SELECT COUNT(*) FROM ledger").fetchone()[0]
        ws.data_dir.mkdir(exist_ok=True)
        export_data(store, ws.data_dir)
    finally:
        store.close()
    if shutil.which("git"):
        try:
            subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True)
            commit_export(target, "Restore from backup")
        except (OSError, subprocess.CalledProcessError):
            pass  # the workspace works without a history of its own
    return Restored(ws, records, ledger)


def _undo(target: Path, existed: bool) -> None:
    """Take away what a failed restore wrote: the folder if it was made here, else what was put in the empty folder."""
    if not existed:
        shutil.rmtree(target, ignore_errors=True)
        return
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
