"""The export round trip on a live workspace: export it, load it into a fresh database, export that, and compare.

`engine.selfcheck.check_workspace_fixture` runs the same steps on a fixture folder. This runs them on a store that has
been used, so what a person did (hand-ins, reviews, undo) is part of what must survive: every record with its id,
version and deletion mark, the id sequences and the whole ledger, and the exported files byte for byte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.storage import Store
from engine.storage.export import export_data, import_data


def _contents(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def _records(store: Store) -> dict[tuple[str, str], tuple[int, bool, Any]]:
    view = store.read()
    return {
        (kind, row.id): (row.version, row.deleted, row.data)
        for kind in view.kinds()
        for row in view.list(kind, include_deleted=True)
    }


def round_trip(store: Store, cfg: Any, work: Path) -> dict[str, Any]:
    """Compare a live store with its export loaded into a fresh database. Returns the counts compared and
    `differences`, a list of plain sentences that is empty when the two are identical."""
    work.mkdir(parents=True, exist_ok=True)
    export_data(store, work / "export-1")
    fresh = Store(work / "fresh.db", cfg=cfg)
    try:
        import_data(fresh, work / "export-1")
        export_data(fresh, work / "export-2")
        differences: list[str] = []
        live, loaded = _records(store), _records(fresh)
        for key in sorted(live.keys() | loaded.keys()):
            kind, record_id = key
            if key not in loaded:
                differences.append(f"{kind} {record_id} is missing after the import")
            elif key not in live:
                differences.append(f"{kind} {record_id} appeared in the import")
            elif live[key][0] != loaded[key][0]:
                differences.append(f"{kind} {record_id} is at version {live[key][0]}, then {loaded[key][0]}")
            elif live[key][1] != loaded[key][1]:
                differences.append(f"{kind} {record_id} changed its deleted mark")
            elif live[key][2] != loaded[key][2]:
                differences.append(f"{kind} {record_id} holds other values after the import")
        before, after = store.read().ledger(), fresh.read().ledger()
        if before != after:
            differences.append(f"the ledger has {len(before)} entries, then {len(after)}, or they differ")
        if store.read().sequences() != fresh.read().sequences():
            differences.append("the id sequences differ")
        if _contents(work / "export-1") != _contents(work / "export-2"):
            differences.append("exporting the imported database writes other files")
        return {"records": len(live), "ledger": len(before), "differences": differences}
    finally:
        fresh.close()
