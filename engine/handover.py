"""Handing a workspace between computers through the synced folder (design 5.0).

The folder's lease (`.cockpit/lease.json`) says which install holds the workspace, on which computer, its last
heartbeat, whether it was released, and how far its history goes. Opening checks it first: a fresh lease held by
another install refuses. Then the histories are compared, entry by entry of the ledger:
- the same: nothing to do;
- the folder's is longer and starts with this computer's: the folder is newer, so this computer's database is backed
  up and the folder's state loaded;
- this computer's is longer and starts with the folder's: this computer is newer, and the next write brings the
  folder up to date;
- neither starts with the other: both computers worked apart. Nothing loads; the person keeps one history and the
  other is saved as a backup.

A running app can be started while the histories are diverged: it works on this computer's own copy, writes nothing to
the folder, and shows the choice. The person's choice is only noted; it is carried out by `settle_chosen` before the
database is opened at the next start, with the same checks as `keep`.

Only files listed in the folder's manifest, with the hash it records, are ever loaded, so a folder still syncing or a
copy a sync service made on a conflict is never read. Storage and server settings stay per computer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import socket
import sqlite3
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine.state_file import changing, write_whole
from engine.sync import INDEX, MACHINE, MANIFEST, _write_atomic, folder_problem, placement_problem

LEASE = f"{MACHINE}/lease.json"
#: The person's choice between diverged histories, kept on this computer until the next start carries it out.
CHOICE = "handover-choice"
#: Config files that describe one computer, never copied between them.
PER_COMPUTER = {"storage.yaml", "server.yaml"}


class Refused(Exception):
    """The workspace can't be opened here now; the message says why and what to do."""


class Diverged(Refused):
    """Both computers changed the workspace apart; the person keeps one history."""


@dataclass
class FolderLease:
    holder: str
    computer: str
    heartbeat: str
    released: bool = False
    ledger: int = 0  # how many ledger entries the folder's machine copy holds


@dataclass
class Opened:
    action: str  # off, unavailable, same, loaded, newer_here, first, held
    message: str = ""
    conflict_copies: list[str] = field(default_factory=list)
    backup: str | None = None
    kept: tuple[str, str] | None = None  # a start that carried out a choice: (which side, where the other was saved)


def install_id(ws: Any) -> str:
    """This install's own id, made once and kept with the workspace on this computer."""
    path = ws.private_dir / "install-id"
    with changing(path):
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        value = uuid.uuid4().hex
        write_whole(path, value + "\n")
        return value


def _folder(cfg: Any) -> Path:
    return Path(cfg.storage.sync.folder).expanduser().resolve()


def read_lease(folder: Path) -> FolderLease | None:
    try:
        data = json.loads((folder / LEASE).read_text(encoding="utf-8"))
        return FolderLease(**{k: data[k] for k in FolderLease.__dataclass_fields__ if k in data})
    except (OSError, ValueError, TypeError, KeyError):
        return None


def write_lease(folder: Path, lease: FolderLease) -> None:
    _write_atomic(folder / LEASE, (json.dumps(asdict(lease), sort_keys=True, indent=1) + "\n").encode())


def take(ws: Any, cfg: Any, *, ledger: int, released: bool = False, now: datetime | None = None) -> None:
    """Write this install's lease into the folder (a heartbeat, or the release when it closes)."""
    stamp = (now or datetime.now(UTC)).isoformat()
    write_lease(_folder(cfg), FolderLease(install_id(ws), socket.gethostname(), stamp, released, ledger))


def release(ws: Any, cfg: Any) -> None:
    """Mark this install's lease released, for commands that open the workspace only briefly."""
    take(ws, cfg, ledger=len(_local_ledger(ws)), released=True)


def held_elsewhere(ws: Any, cfg: Any, now: datetime | None = None) -> FolderLease | None:
    """The folder's lease when another install holds it and it is fresh, else None."""
    lease = read_lease(_folder(cfg))
    if lease is None or lease.holder == install_id(ws) or lease.released:
        return None
    try:
        beat = datetime.fromisoformat(lease.heartbeat)
    except ValueError:
        return None
    stale = timedelta(minutes=cfg.storage.sync.lease_stale_after_minutes)
    return lease if (now or datetime.now(UTC)) - beat < stale else None


def conflict_copies(folder: Path) -> list[str]:
    """Files a sync service seems to have made on a conflict: in the machine copy, anything the manifest doesn't list;
    elsewhere, an unlisted file named like a listed one with something added ("name (1).md", "name-PC.md")."""
    manifest = _manifest(folder)
    listed = set(manifest) | {MANIFEST, LEASE, INDEX, f"{MACHINE}/outside.json"}
    stems: dict[str, set[str]] = {}
    for rel in manifest:
        head, _, name = rel.rpartition("/")
        stems.setdefault(head, set()).add(name.rsplit(".", 1)[0].casefold())
    found = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name.endswith(".cockpit-tmp"):
            continue
        rel = path.relative_to(folder).as_posix()
        if rel in listed:
            continue
        if rel.startswith(MACHINE + "/"):
            found.append(rel)
            continue
        head, _, name = rel.rpartition("/")
        stem = name.rsplit(".", 1)[0].casefold()
        added = any(stem != s and stem.startswith(s) and stem[len(s)] in " -_" for s in stems.get(head, ()))
        if added or "conflict" in stem:
            found.append(rel)
    return found


def _manifest(folder: Path) -> dict[str, str]:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _verified(folder: Path, prefix: str) -> dict[str, Path]:
    """{path under prefix: file} for every manifest-listed file there, each matching its recorded hash. Raises Refused
    when one doesn't: the folder is still bringing in changes."""
    files = {}
    for rel, digest in _manifest(folder).items():
        if not rel.startswith(prefix):
            continue
        path = folder / rel
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise Refused(
                "The synced folder is still bringing in changes from the other computer. Try again in a minute."
            )
        files[rel[len(prefix) :]] = path
    return files


def _folder_ledger(folder: Path) -> list[str] | None:
    files = _verified(folder, f"{MACHINE}/export/")
    if "ledger.jsonl" not in files:
        return None
    return [line for line in files["ledger.jsonl"].read_text(encoding="utf-8").splitlines() if line.strip()]


def _local_ledger(ws: Any) -> list[str]:
    from engine.storage.store import _ledger_row, dumps

    if not ws.db_path.exists():
        return []
    conn = sqlite3.connect(ws.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM ledger ORDER BY seq").fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [dumps(_ledger_row(r)) for r in rows]


def _redacted_records(*histories: list[str]) -> dict[tuple[str, str], list[str]]:
    """{(kind, record id): fields} for every record a confirmed set-aside deleted, found in any of the histories."""
    from engine.set_aside import DELETE_OP, REDACTED_FIELDS

    found: dict[tuple[str, str], list[str]] = {}
    for history in histories:
        for line in history:
            entry = json.loads(line)
            if entry.get("op") == DELETE_OP and entry.get("kind") in REDACTED_FIELDS:
                found[(entry["kind"], entry["record_id"])] = REDACTED_FIELDS[entry["kind"]]
    return found


def apply_redactions(local: list[str], folder: list[str]) -> tuple[list[str], list[str]]:
    """Both histories with every set-aside deletion found in either applied to both, the way the store blanks the
    earlier values of a deleted item's fields, so a redacted entry matches its original and the comparison doesn't
    read a deletion made on one computer as a divergence."""
    from engine.storage.store import dumps

    targets = _redacted_records(local, folder)
    if not targets:
        return local, folder

    def redact(history: list[str]) -> list[str]:
        out = []
        for line in history:
            entry = json.loads(line)
            if entry.get("field") in targets.get((entry.get("kind"), entry.get("record_id")), ()):
                for key in ("before", "after"):
                    if entry.get(key) is not None:
                        entry[key] = None
                line = dumps(entry)
            out.append(line)
        return out

    return redact(local), redact(folder)


def compare(local: list[str], folder: list[str]) -> str:
    """same, folder_newer, newer_here or diverged. Set-aside deletions in either history count in both."""
    local, folder = apply_redactions(local, folder)
    if local == folder:
        return "same"
    if folder[: len(local)] == local:
        return "folder_newer"
    if local[: len(folder)] == folder:
        return "newer_here"
    return "diverged"


def open_workspace(ws: Any, cfg: Any, *, now: datetime | None = None) -> Opened:
    """Check the folder before the workspace opens here: refuse, load the folder's newer state, or go ahead. Takes the
    lease when it goes ahead. Raises Refused (or Diverged) with what to do."""
    if not cfg.storage.sync.folder.strip():
        return Opened("off")
    placed = placement_problem(ws, cfg)
    if placed:
        raise Refused(f"Can't open: {placed}.")
    problem = folder_problem(ws, cfg)
    if problem:
        return Opened("unavailable", f"Working on this computer only: {problem}.")
    folder = _folder(cfg)
    other = held_elsewhere(ws, cfg, now)
    if other is not None:
        minutes = cfg.storage.sync.lease_stale_after_minutes
        raise Refused(
            f"This workspace is open on {other.computer} (last seen {other.heartbeat}). Close it there first. If that "
            f"computer is off or asleep, it can be opened here {minutes} minutes after it was last seen."
        )
    copies = conflict_copies(folder)
    theirs = _folder_ledger(folder)
    mine = _local_ledger(ws)
    if theirs is None:
        take(ws, cfg, ledger=len(mine), now=now)
        return Opened("first", conflict_copies=copies)
    verdict = compare(mine, theirs)
    if verdict == "diverged":
        raise Diverged(
            "This computer and the synced folder both have changes the other lacks, made while they couldn't sync. "
            "Nothing was loaded. Choose which to keep with `cockpit sync keep --here` or `cockpit sync keep "
            "--folder`; the other is saved as a backup."
        )
    opened = Opened(verdict if verdict != "folder_newer" else "loaded", conflict_copies=copies)
    if verdict == "folder_newer":
        opened.backup = load_from_folder(ws, cfg)
    take(ws, cfg, ledger=len(theirs) if verdict != "newer_here" else len(mine), now=now)
    return opened


def backup_local(ws: Any, label: str) -> Path | None:
    """A consistent copy of this computer's database, kept with the workspace. Returns where, or None if it has none."""
    if not ws.db_path.exists():
        return None
    folder = ws.private_dir / "handover-backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / f"{stamp}-{label}.db"
    source = sqlite3.connect(ws.db_path)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return target


def load_from_folder(ws: Any, cfg: Any) -> str | None:
    """Replace this computer's database, config (storage and server settings aside) and plugin data with the folder's.
    The database is backed up first and the new one is built beside it, so a failure leaves everything as it was.
    Returns where the backup went."""
    from engine.config import load_config
    from engine.storage import Store
    from engine.storage.export import import_data

    folder = _folder(cfg)
    export = _verified(folder, f"{MACHINE}/export/")
    config = _verified(folder, f"{MACHINE}/config/")
    plugin_data = _verified(folder, f"{MACHINE}/plugin-data/")
    blobs = _verified(folder, f"{MACHINE}/files/")
    texts = _verified(folder, f"{MACHINE}/sources/")
    with tempfile.TemporaryDirectory(prefix="cockpit-load-") as tmp:
        data_dir, config_dir = Path(tmp) / "export", Path(tmp) / "config"
        shutil.copytree(ws.config_dir, config_dir)
        for rel, path in config.items():
            if rel not in PER_COMPUTER:
                (config_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, config_dir / rel)
        for rel, path in export.items():
            (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, data_dir / rel)
        loading = ws.root / "cockpit.db-loading"
        for stale in (loading, Path(f"{loading}-wal"), Path(f"{loading}-shm")):
            stale.unlink(missing_ok=True)
        store = Store(loading, cfg=load_config(config_dir))
        try:
            import_data(store, data_dir)
        except BaseException:
            store.close()
            loading.unlink(missing_ok=True)
            raise
        store.close()
        from engine.sync import restore_bytes

        # Named by hash, so adding them first changes nothing if a later step fails.
        restore_bytes(ws.root, blobs, texts)
        backup = backup_local(ws, "before-loading-the-synced-folder")
        for rel in config:
            if rel not in PER_COMPUTER:
                (ws.config_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(config_dir / rel, ws.config_dir / rel)
    for rel, path in plugin_data.items():
        target = ws.root / "plugin-data" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for old in (Path(f"{ws.db_path}-wal"), Path(f"{ws.db_path}-shm")):
        old.unlink(missing_ok=True)
    os.replace(loading, ws.db_path)
    for leftover in (Path(f"{loading}-wal"), Path(f"{loading}-shm")):
        leftover.unlink(missing_ok=True)
    return str(backup) if backup else None


def keep(ws: Any, cfg: Any, which: str, *, now: datetime | None = None) -> str:
    """Settle diverged histories: keep this computer's ("here") or the folder's ("folder"). The other is saved as a
    backup. Returns where the backup went."""
    if held_elsewhere(ws, cfg, now) is not None:
        raise Refused("The workspace is open on the other computer. Close it there first.")
    folder = _folder(cfg)
    if which == "folder":
        backup = load_from_folder(ws, cfg)
        take(ws, cfg, ledger=len(_folder_ledger(folder) or []), released=True, now=now)
        return backup or ""
    if which != "here":
        raise ValueError('keep "here" or "folder"')
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = ws.private_dir / "handover-backups" / f"{stamp}-synced-folder"
    source = folder / MACHINE
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("lease.json", "*.cockpit-tmp"))
    from engine.storage import Store
    from engine.sync import write_folder

    store = Store(ws.db_path, cfg=cfg)
    try:
        write_folder(store, ws, cfg)
    finally:
        store.close()
    take(ws, cfg, ledger=len(_local_ledger(ws)), released=True, now=now)
    return str(target)


# ---- showing the situation, and choosing from a screen -----------------------------------------------------


@dataclass
class Side:
    """What one side has that the other lacks: how many changes, the time of the latest, and the computer."""

    computer: str
    changes: int
    latest: str | None


@dataclass
class Situation:
    """What stands in the way of using the synced folder, described without changing anything.
    `diverged`: both sides changed apart (`here` and `folder` say what each has). `elsewhere`: another computer holds
    the workspace now (`computer`, `last_seen`, and `minutes_left` until it can be opened here without it closing)."""

    kind: str
    here: Side | None = None
    folder: Side | None = None
    computer: str = ""
    last_seen: str | None = None
    minutes_left: int = 0


def _side(entries: list[str], computer: str) -> Side:
    latest = None
    for line in entries:
        stamp = json.loads(line).get("at")
        if stamp and (latest is None or stamp > latest):
            latest = stamp
    return Side(computer, len(entries), latest)


def other_computer(cfg: Any) -> str:
    """The computer the folder's lease names, or an empty string."""
    lease = read_lease(_folder(cfg))
    return lease.computer if lease else ""


def situation(ws: Any, cfg: Any, now: datetime | None = None) -> Situation | None:
    """Why the folder can't be used right now, or None. Only reads."""
    if not cfg.storage.sync.folder.strip() or folder_problem(ws, cfg):
        return None
    folder = _folder(cfg)
    when = now or datetime.now(UTC)
    other = held_elsewhere(ws, cfg, when)
    if other is not None:
        beat = datetime.fromisoformat(other.heartbeat)
        stale = timedelta(minutes=cfg.storage.sync.lease_stale_after_minutes)
        left = max(1, math.ceil((stale - (when - beat)).total_seconds() / 60))
        return Situation("elsewhere", computer=other.computer, last_seen=other.heartbeat, minutes_left=left)
    try:
        theirs = _folder_ledger(folder)
    except Refused:
        return None
    if theirs is None:
        return None
    mine = _local_ledger(ws)
    if compare(mine, theirs) != "diverged":
        return None
    local, remote = apply_redactions(mine, theirs)
    common = 0
    while common < min(len(local), len(remote)) and local[common] == remote[common]:
        common += 1
    return Situation(
        "diverged",
        here=_side(local[common:], socket.gethostname()),
        folder=_side(remote[common:], other_computer(cfg)),
    )


def chosen(ws: Any) -> str | None:
    """The side the person chose to keep ("here" or "folder"), waiting for the next start, or None."""
    try:
        value = (ws.private_dir / CHOICE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if value in ("here", "folder") else None


def clear_choice(ws: Any) -> None:
    (ws.private_dir / CHOICE).unlink(missing_ok=True)


def choose(ws: Any, cfg: Any, which: str, *, now: datetime | None = None) -> None:
    """Note which side to keep, to be carried out at the next start. Refused while the other computer has the workspace
    open, and when the histories aren't diverged."""
    if which not in ("here", "folder"):
        raise ValueError('keep "here" or "folder"')
    if held_elsewhere(ws, cfg, now) is not None:
        raise Refused("The workspace is open on the other computer. Close it there first.")
    found = situation(ws, cfg, now)
    if found is None or found.kind != "diverged":
        raise Refused("There is nothing to choose between: the two copies agree, or the folder can't be read now.")
    write_whole(ws.private_dir / CHOICE, which + "\n")


def settle_chosen(ws: Any, cfg: Any, *, now: datetime | None = None) -> tuple[str, str] | None:
    """Carry out the choice noted from the screen, before the database is opened: (which, where the other side was
    saved), or None when no choice is waiting. The note is removed first, so a refusal is never retried unasked; the
    choice goes through `keep`, with all its checks."""
    which = chosen(ws)
    if which is None:
        return None
    clear_choice(ws)
    return which, keep(ws, cfg, which, now=now)


HELD_NOTE = (
    "Both this computer and the synced folder changed while they couldn't sync. The app opens on this computer's own "
    "copy and writes nothing to the folder until you choose which copy to keep on the screen."
)


def open_or_hold(ws: Any, cfg: Any, *, now: datetime | None = None) -> Opened:
    """`open_workspace` for starting the app: histories that diverged don't stop it. A choice noted from the screen is
    carried out first (through `keep`, so every check holds); with none, nothing loads and nothing is written to the
    folder, the lease isn't taken, and the app opens on this computer's copy (action "held"). Every other refusal
    still raises, and drops any choice noted from the screen."""
    try:
        return open_workspace(ws, cfg, now=now)
    except Diverged:
        settled = settle_chosen(ws, cfg, now=now)
        if settled is None:
            return Opened("held", HELD_NOTE)
        opened = open_workspace(ws, cfg, now=now)
        opened.kept = settled
        return opened
    except Refused:
        # A start that is refused drops the noted choice: what it was chosen against may have changed.
        clear_choice(ws)
        raise
