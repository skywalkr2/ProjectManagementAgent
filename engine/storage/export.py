"""The readable export and import.

The export writes every record, the id sequences and the ledger as deterministic JSON under the workspace's `data/`
folder, so it diffs cleanly in git. Import loads an export into an empty database. Exporting, importing and exporting
again gives byte-identical files: that round trip is what makes git history a working recovery path.

A folder of records with no ledger (a hand-written starting set) can be imported too: each record gets one ledger
entry per field, as if it had been created by an import.

Long text is written beside the records as plain files, `texts/<hash>.txt`, one per distinct text a version holds, and
loaded back into the workspace's text store on import.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from engine.records import REGISTRY
from engine.storage.store import Store, Stored, StoreError, WriteContext, dumps, id_number

LEDGER_FILE = "ledger.jsonl"
TEXTS_DIR = "texts"
SEQUENCES_FILE = "_sequences.json"
_IMPORT = WriteContext(actor="import", trust="trusted", op="import")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def export_data(store: Store, data_dir: Path) -> list[Path]:
    """Write the readable export. Returns the files written."""
    data_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    view = store.read()
    kinds = sorted(set(view.kinds()) | set(store.plugins.records), key=_kind_order)
    for kind in kinds:
        rows = view.list(kind, include_deleted=True)
        path = data_dir / f"{kind}.json"
        if not rows:
            if path.exists():
                path.unlink()
            continue
        items = [_record_out(s) for s in rows]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json(items), encoding="utf-8")
        written.append(path)
    written += _export_texts(store, view, data_dir / TEXTS_DIR)
    seq = data_dir / SEQUENCES_FILE
    seq.write_text(_json(view.sequences()), encoding="utf-8")
    written.append(seq)
    ledger = data_dir / LEDGER_FILE
    with ledger.open("w", encoding="utf-8") as fh:
        for entry in view.ledger():
            fh.write(dumps(entry) + "\n")
    written.append(ledger)
    return written


def import_data(store: Store, data_dir: Path) -> int:
    """Load an export (or a fixture folder) into an empty store. Returns the number of records loaded."""
    view = store.read()
    if view.kinds() or view.sequences():
        raise StoreError("import needs an empty database; this one already has records")
    ledger_path = data_dir / LEDGER_FILE
    has_ledger = ledger_path.exists()
    count = 0
    known = store.plugins.records
    unknown = [
        p.relative_to(data_dir).as_posix()[:-5]
        for p in data_dir.rglob("*.json")
        if p.name != SEQUENCES_FILE
        and p.relative_to(data_dir).parts[0] != TEXTS_DIR
        and p.relative_to(data_dir).as_posix()[:-5] not in known
    ]
    if unknown:
        raise StoreError("enable the record plugins before importing: " + ", ".join(unknown))
    with store.transaction(notify=False) as tx:
        for kind in sorted(known, key=_kind_order):
            path = data_dir / f"{kind}.json"
            if not path.exists():
                continue
            items = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                raise StoreError(f"{path.name}: expected a list of records")
            for item in items:
                stored = _record_in(kind, item, path.name)
                if has_ledger:
                    tx.restore_record(stored)
                else:
                    tx.create(kind, stored.data, _IMPORT, record_id=stored.id)
                count += 1
        if has_ledger:
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    tx.restore_ledger(json.loads(line))
        seq_path = data_dir / SEQUENCES_FILE
        if seq_path.exists():
            for kind, next_value in json.loads(seq_path.read_text(encoding="utf-8")).items():
                tx.set_sequence(kind, int(next_value))
    _import_texts(store, data_dir / TEXTS_DIR)
    return count


def _export_texts(store: Store, view: Any, folder: Path) -> list[Path]:
    """Every distinct text a version holds, as a plain file named by its hash; files no version needs are removed."""
    from engine.texts import read_text

    wanted = {v.data["sha256"] for v in view.list("text_version", include_deleted=True)}
    written = []
    for digest in sorted(wanted):
        path = folder / f"{digest}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(read_text(store, digest), encoding="utf-8", newline="")
        written.append(path)
    if folder.exists():
        for stale in folder.glob("*.txt"):
            if stale.stem not in wanted:
                stale.unlink()
    return written


def _import_texts(store: Store, folder: Path) -> None:
    """Load exported texts into the text store, checking each against the hash it is named by."""
    from engine.texts import store_text

    for path in sorted(folder.glob("*.txt")) if folder.exists() else []:
        if store_text(store, path.read_bytes().decode("utf-8")) != path.stem:
            raise StoreError(f"{TEXTS_DIR}/{path.name} doesn't match its name; it was changed after the export")


def commit_export(workspace_root: Path, message: str) -> bool:
    """Commit config and the export to the workspace's git repository. Returns False when there was nothing to commit
    or the workspace isn't a git repository."""
    if not (workspace_root / ".git").exists():
        return False
    git = ["git", "-C", str(workspace_root), "-c", "user.name=PM Cockpit", "-c", "user.email=cockpit@localhost"]
    paths = [name for name in ("config", "data", "plugin-data") if (workspace_root / name).exists()]
    if not paths:
        return False
    subprocess.run([*git, "add", "-A", "--", *paths], check=True, capture_output=True)
    staged = subprocess.run([*git, "diff", "--cached", "--quiet"], capture_output=True)
    if staged.returncode == 0:
        return False
    subprocess.run([*git, "commit", "-q", "-m", message], check=True, capture_output=True)
    return True


def _kind_order(kind: str) -> tuple[int, str]:
    order = list(REGISTRY)
    return (order.index(kind) if kind in order else len(order), kind)


def _record_out(stored: Stored) -> dict[str, Any]:
    out = {k: v for k, v in stored.data.items() if v not in (None, [], {}) or k == "id"}
    out["_version"] = stored.version
    if stored.deleted:
        out["_deleted"] = True
    return out


def _record_in(kind: str, item: dict[str, Any], where: str) -> Stored:
    if not isinstance(item, dict) or "id" not in item:
        raise StoreError(f"{where}: every record needs an id")
    data = {k: v for k, v in item.items() if not k.startswith("_")}
    if id_number(data["id"]) is None:
        raise StoreError(f"{where}: {data['id']!r} is not a valid id")
    return Stored(kind, data["id"], int(item.get("_version", 1)), bool(item.get("_deleted", False)), data)
