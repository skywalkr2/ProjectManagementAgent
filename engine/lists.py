"""Value lists (design 5.1): the values a field may take, kept as records so changing one has history and Undo.

The core ships its lists in `engine/defaults/value_lists.yaml`; plugins declare theirs. `ensure` creates any list a
workspace doesn't have yet, with its first values plus the values its records already use, so nothing that was valid
becomes invalid. After that a list belongs to the person: `list.add`, `list.rename` (which changes every record that
holds the value, in one op) and `list.retire`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.records import list_fields
from engine.storage import StoreError, WriteContext

DEFAULTS = Path(__file__).parent / "defaults" / "value_lists.yaml"

_ENGINE = WriteContext(actor="engine", trust="trusted", op="lists.ensure")


def core_lists() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8")) or {}
    return {
        str(name): {"label": str(entry["label"]), "values": [str(v) for v in entry.get("values") or []]}
        for name, entry in (data.get("lists") or {}).items()
    }


def declared(store: Any) -> dict[str, dict[str, Any]]:
    """Every list the core and the running plugins declare, with its label and first values."""
    found = core_lists()
    plugins = getattr(store, "plugins", None)
    for name, entry in (getattr(plugins, "value_lists", {}) or {}).items():
        found.setdefault(name, entry)
    return found


def in_use(tx: Any, models: dict[str, Any], name: str) -> list[str]:
    """Values records hold today in fields bound to this list, in first-seen order."""
    seen: dict[str, None] = {}
    for kind, model in models.items():
        for field, bound, many in list_fields(model):
            if bound != name:
                continue
            for record in tx.list(kind):
                value = record.data.get(field)
                for v in (value or []) if many else [value]:
                    if isinstance(v, str) and v.strip():
                        seen.setdefault(v, None)
    return list(seen)


def ensure(store: Any) -> list[str]:
    """Create the lists this workspace lacks. Returns the names created."""
    created = []
    with store.transaction() as tx:
        have = {r.data["name"] for r in tx.list("value_list")}
        for name, entry in declared(store).items():
            if name in have:
                continue
            values = list(entry["values"])
            known = {v.casefold() for v in values}
            values += [v for v in in_use(tx, tx.models, name) if v.casefold() not in known]
            tx.create("value_list", {"name": name, "label": entry["label"], "values": values}, _ENGINE)
            created.append(name)
    return created


def find(tx: Any, name: str) -> Any:
    found = next((r for r in tx.list("value_list") if r.data["name"] == name), None)
    if found is None:
        raise StoreError(f"there is no list called {name}")
    return found


def apply(tx: Any, op: Any, w: WriteContext) -> list[dict[str, Any]]:
    """Apply list.add, list.rename or list.retire. Returns the records touched."""
    value_list = find(tx, op.list)
    values, retired = list(value_list.data["values"]), list(value_list.data["retired"])
    every = {v.casefold(): v for v in (*values, *retired)}
    touched = [{"kind": "value_list", "id": value_list.id}]
    if op.op == "list.add":
        value = " ".join(op.value.split())
        if value.casefold() in every:
            existing = every[value.casefold()]
            if existing in values:
                raise StoreError(f"{existing!r} is already on the list")
            retired.remove(existing)  # adding a retired value offers it again
            values.append(existing)
        else:
            values.append(value)
    elif op.op == "list.retire":
        if op.value not in values:
            raise StoreError(f"{op.value!r} isn't offered on the list")
        values.remove(op.value)
        retired.append(op.value)
    elif op.op == "list.rename":
        to = " ".join(op.to.split())
        if op.value not in values and op.value not in retired:
            raise StoreError(f"{op.value!r} isn't on the list")
        if to.casefold() in every and every[to.casefold()] != op.value:
            raise StoreError(f"{every[to.casefold()]!r} is already on the list; retire one of them instead")
        values = [to if v == op.value else v for v in values]
        retired = [to if v == op.value else v for v in retired]
        # The list first, so the records' new value is on it when they are written.
        tx.update(
            "value_list", value_list.id, {"values": values, "retired": retired}, w, read_version=value_list.version
        )
        for kind, model in tx.models.items():
            for field, bound, many in list_fields(model):
                if bound != op.list:
                    continue
                for record in tx.list(kind):
                    held = record.data.get(field)
                    if many and op.value in (held or []):
                        new = [to if v == op.value else v for v in held]
                    elif not many and held == op.value:
                        new = to
                    else:
                        continue
                    tx.update(kind, record.id, {field: new}, w, read_version=record.version)
                    touched.append({"kind": kind, "id": record.id})
        return touched
    tx.update("value_list", value_list.id, {"values": values, "retired": retired}, w, read_version=value_list.version)
    return touched
