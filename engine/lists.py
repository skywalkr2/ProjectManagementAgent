"""Value lists (design 5.1): the values a field may take, kept as records so changing one has history and Undo.

The core ships its lists in `engine/defaults/value_lists.yaml`; plugins declare theirs. `ensure` creates any list a
workspace doesn't have yet, with its first values plus the values its records already use, so nothing that was valid
becomes invalid. After that a list belongs to the person: `list.add`, `list.rename` (which changes every record that
holds the value, in one op), `list.merge` (which moves every record from one value to another and removes the first)
and `list.retire`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.records import list_fields
from engine.storage import StoreError, WriteContext
from engine.yaml_load import load_yaml

DEFAULTS = Path(__file__).parent / "defaults" / "value_lists.yaml"

_ENGINE = WriteContext(actor="engine", trust="trusted", op="lists.ensure")


#: The tones a value can be colored with, and the meanings a status list's values can have.
TONES = ("ok", "warn", "danger", "neutral")
MEANINGS = ("not_started", "open", "at_risk", "blocked", "done")

#: How urgent each meaning is when projects are ranked, most urgent first; a value with no meaning ranks after open
#: and not-started work and before finished work, so unknown stays unknown.
_URGENCY = {"at_risk": 0, "blocked": 1, "open": 2, "not_started": 3, None: 4, "done": 5}


def _data() -> dict[str, Any]:
    return load_yaml(DEFAULTS.read_text(encoding="utf-8")) or {}


def core_lists() -> dict[str, dict[str, Any]]:
    return {
        str(name): {
            "label": str(entry["label"]),
            "values": [str(v) for v in entry.get("values") or []],
            "status": bool(entry.get("status")),
            "tones": {str(k): str(v) for k, v in (entry.get("tones") or {}).items()},
            "meanings": {str(k): str(v) for k, v in (entry.get("meanings") or {}).items()},
        }
        for name, entry in (_data().get("lists") or {}).items()
    }


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def suggest(value: str) -> dict[str, str]:
    """The tone and meaning offered for a typed value: the first shipped suggestion whose words appear in it, else open
    work with no color. The person can change both; a list with no meanings uses only the tone."""
    typed = _words(value)
    for row in _data().get("suggestions") or []:
        for phrase in row.get("words") or []:
            words = _words(str(phrase))
            if words and any(typed[i : i + len(words)] == words for i in range(len(typed) - len(words) + 1)):
                return {"tone": str(row["tone"]), "meaning": str(row["meaning"])}
    return {"tone": "neutral", "meaning": "open"}


@dataclass(frozen=True)
class ValueMeaning:
    """How a value is colored and, on a status list, what it means (None where it has none)."""

    tone: str = "neutral"
    meaning: str | None = None


def is_status_list(view: Any, name: str) -> bool:
    """Whether the list's values carry a meaning: the core ships it as a status list."""
    return bool((core_lists().get(name) or {}).get("status"))


def describe(view: Any, name: str, value: str | None) -> ValueMeaning:
    """The tone and meaning of one value of a list: what the person's list holds for it, else what the core ships for
    the same wording (so a workspace made before meanings existed reads them), else neutral and no meaning. A meaning is
    never guessed from the wording of a value the core doesn't ship."""
    if not value:
        return ValueMeaning()
    record = next((r for r in view.list("value_list") if r.data["name"] == name), None)
    shipped = core_lists().get(name) or {}
    tones = {**{k.casefold(): v for k, v in (shipped.get("tones") or {}).items()}}
    meanings = {k.casefold(): v for k, v in (shipped.get("meanings") or {}).items()}
    if record is not None:
        tones |= {k.casefold(): v for k, v in (record.data.get("tones") or {}).items()}
        meanings |= {k.casefold(): v for k, v in (record.data.get("meanings") or {}).items()}
    key = value.strip().casefold()
    return ValueMeaning(tones.get(key, "neutral"), meanings.get(key))


def status_rank(view: Any, name: str, value: str | None) -> int:
    """How urgent a status value is, from its meaning (0 is the most urgent): at risk, blocked, open, not started, no
    meaning, done. Never from its wording."""
    return _URGENCY[describe(view, name, value).meaning]


def value_rank(view: Any, name: str, value: str | None) -> int:
    """Where a value stands on its list, 0 first, in the order the person keeps the list in; a value with none, or not
    on the list, ranks after every value on it. For a list whose order says how much a value matters (project
    priority)."""
    record = next((r for r in view.list("value_list") if r.data["name"] == name), None)
    values = [str(v) for v in (record.data.get("values") if record is not None else None) or []]
    if record is None:
        values = [str(v) for v in (core_lists().get(name) or {}).get("values") or []]
    key = (value or "").strip().casefold()
    return next((i for i, v in enumerate(values) if v.casefold() == key), len(values)) if key else len(values)


def projects_at_risk(view: Any) -> list[str]:
    """The ids of the projects whose status means at risk, by the status's meaning, not its wording."""
    return [
        p.id
        for p in view.list("project")
        if describe(view, "project-status", p.data.get("status")).meaning == "at_risk"
    ]


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
            shipped = {v.casefold() for v in entry["values"]}
            tones = {v: t for v, t in (entry.get("tones") or {}).items() if v in values and v.casefold() in shipped}
            meanings = {v: m for v, m in (entry.get("meanings") or {}).items() if v in values}
            tx.create(
                "value_list",
                {"name": name, "label": entry["label"], "values": values, "tones": tones, "meanings": meanings},
                _ENGINE,
            )
            created.append(name)
    return created


def find(tx: Any, name: str) -> Any:
    found = next((r for r in tx.list("value_list") if r.data["name"] == name), None)
    if found is None:
        raise StoreError(f"there is no list called {name}")
    return found


def merge_problem(view: Any, op: Any) -> str | None:
    """Why a list.merge can't apply, or None: the list exists, the value is on it (offered or retired), the value it
    merges into is offered, and the two are different."""
    found = next((r for r in view.list("value_list") if r.data["name"] == op.list), None)
    if found is None:
        return f"there is no list called {op.list}"
    values, retired = found.data["values"], found.data["retired"]
    if op.value not in values and op.value not in retired:
        return f"{op.value!r} isn't on the list"
    if op.into not in values:
        return f"{op.into!r} isn't offered on the list, so nothing can be merged into it"
    if op.value == op.into:
        return "a value can't be merged into itself"
    return None


def _merge(tx: Any, op: Any, w: WriteContext, value_list: Any) -> list[dict[str, Any]]:
    """The value leaves the list, and every record that holds it in a field bound to the list holds `op.into` instead
    (once, in a field that holds many). The list is written first, so Undo puts the value back on the list before any
    record holds it again."""
    if (why := merge_problem(tx, op)) is not None:
        raise StoreError(why)
    touched = [{"kind": "value_list", "id": value_list.id}]
    tx.update(
        "value_list",
        value_list.id,
        {
            "values": [v for v in value_list.data["values"] if v != op.value],
            "retired": [v for v in value_list.data["retired"] if v != op.value],
            "tones": {k: t for k, t in (value_list.data.get("tones") or {}).items() if k != op.value},
            "meanings": {k: m for k, m in (value_list.data.get("meanings") or {}).items() if k != op.value},
        },
        w,
        read_version=value_list.version,
    )
    for kind, model in tx.models.items():
        for field, bound, many in list_fields(model):
            if bound != op.list:
                continue
            for record in tx.list(kind):
                held = record.data.get(field)
                if many and op.value in (held or []):
                    new = list(dict.fromkeys(op.into if v == op.value else v for v in held))
                elif not many and held == op.value:
                    new = op.into
                else:
                    continue
                tx.update(kind, record.id, {field: new}, w, read_version=record.version)
                touched.append({"kind": kind, "id": record.id})
    return touched


def apply(tx: Any, op: Any, w: WriteContext) -> list[dict[str, Any]]:
    """Apply list.add, list.rename, list.merge or list.retire. Returns the records touched."""
    value_list = find(tx, op.list)
    if op.op == "list.merge":
        return _merge(tx, op, w, value_list)
    values, retired = list(value_list.data["values"]), list(value_list.data["retired"])
    every = {v.casefold(): v for v in (*values, *retired)}
    touched = [{"kind": "value_list", "id": value_list.id}]
    tones, meanings = dict(value_list.data.get("tones") or {}), dict(value_list.data.get("meanings") or {})
    if op.op == "list.add":
        value = " ".join(op.value.split())
        if value.casefold() in every:
            existing = every[value.casefold()]
            if existing in values:
                raise StoreError(f"{existing!r} is already on the list")
            retired.remove(existing)  # adding a retired value offers it again
            values.append(existing)
            value = existing
        else:
            values.append(value)
        status = bool(core_lists().get(op.list, {}).get("status"))
        if op.meaning and not status:
            raise StoreError(f"the values of {value_list.data['label']} have no meanings")
        offered = suggest(value)
        if op.tone or value not in tones:
            tones[value] = op.tone or (offered["tone"] if status else "neutral")
        if status and (op.meaning or value not in meanings):
            meanings[value] = op.meaning or offered["meaning"]
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
        tones = {(to if k == op.value else k): t for k, t in tones.items()}
        meanings = {(to if k == op.value else k): m for k, m in meanings.items()}
        # The list first, so the records' new value is on it when they are written.
        tx.update(
            "value_list",
            value_list.id,
            {"values": values, "retired": retired, "tones": tones, "meanings": meanings},
            w,
            read_version=value_list.version,
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
    tx.update(
        "value_list",
        value_list.id,
        {"values": values, "retired": retired, "tones": tones, "meanings": meanings},
        w,
        read_version=value_list.version,
    )
    return touched
