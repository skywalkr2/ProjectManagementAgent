"""Records join by id, never by a display name (design 6.32, "Records join by id").

Anything that names a record to follow or filter by (a source's project, a triage rule's projects and people, a
connector's settings that refer to records, a rule's or lesson's filter on a reference field) holds the record's id,
so a rename never detaches it. A person may still type a name: `resolve` turns it into the id when the setting is
saved, the screens keep showing the record's current name, and a name that matches nothing (or more than one record) is
refused with its own words rather than stored. `join_stored_names` does the same once for what older files and
records hold. A rule that names a record that is gone matches nothing and so closes nothing (`names_for` returns no
names).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from engine.config.yaml_edit import set_key
from engine.records import REFERENCES, ref_fields
from engine.storage import StoreError, WriteContext
from engine.yaml_load import load_yaml

log = logging.getLogger(__name__)

_MIGRATE = WriteContext(actor="engine", trust="trusted", op="migrate.join_by_id")
#: The fields that hold a record's display name, and the one that holds the other names it goes by.
NAME_FIELDS = ("name", "full_name", "title")
ALIASES = "aliases"
#: The kinds of entry that carry a reach (`applies_to`) with a filter.
SCOPED_KINDS = ("rule", "lesson", "glossary_entry", "routing_entry", "style_note")


def _same(text: Any) -> str:
    return " ".join(str(text).split()).casefold()


def names_of(data: Mapping[str, Any]) -> list[str]:
    """The names a record is known by now: its display name and the other names it goes by."""
    names = [" ".join(data[f].split()) for f in NAME_FIELDS if isinstance(data.get(f), str) and data[f].strip()]
    return names + [a for a in data.get(ALIASES) or [] if isinstance(a, str) and a.strip()]


def names_for(view: Any, kind: str, ids: list[str]) -> list[str]:
    """The current names of these records (each with its other names); an id that names nothing contributes none."""
    names: list[str] = []
    for record_id in ids:
        found = view.get(kind, record_id) if isinstance(record_id, str) else None
        if found is not None and not found.deleted:
            names += names_of(found.data)
    return names


def resolve(view: Any, kind: str, value: Any) -> str:
    """The id a value names: an id of a record of this kind, else the one record of the kind whose current name (or
    other name) it is, in any case. Raises StoreError when nothing matches or when more than one does."""
    word = kind.replace("_", " ")
    if not isinstance(value, str) or not value.strip():
        raise StoreError(f"Choose a {word} from the list.")
    text = " ".join(value.split())
    found = view.get(kind, text)
    if found is not None and not found.deleted:
        return text
    wanted = _same(text)
    matches = [s.id for s in view.list(kind) if wanted in {_same(n) for n in names_of(s.data)}]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise StoreError(f"{text} isn't a {word} the app knows. Choose one from the list.")
    raise StoreError(f"More than one {word} is called {text}. Choose one from the list.")


def _soft(view: Any, kind: str, value: Any) -> Any:
    """`resolve`, but a value nothing matches is returned as it was."""
    try:
        return resolve(view, kind, value)
    except StoreError:
        return value


def _map_at(data: Any, path: str, fn: Callable[[Any], Any]) -> Any:
    """`data` with `fn` applied to each value at a reference path such as "field", "list[]" or "list[].field"."""
    if not isinstance(data, dict):
        return data
    head, _, rest = path.partition(".")
    key = head.removesuffix("[]")
    if key not in data or data[key] is None:
        return data
    if head.endswith("[]"):
        items = data[key]
        if not isinstance(items, list):
            return data
        return {**data, key: [_map_at(i, rest, fn) if rest else fn(i) for i in items]}
    return {**data, key: _map_at(data[key], rest, fn) if rest else fn(data[key])}


def join_settings(model: type[BaseModel], settings: dict[str, Any], view: Any) -> dict[str, Any]:
    """A connector's settings with each field its model marks as a reference (`RefTo`) holding the record's id."""
    joined = dict(settings)
    for path, kind in ref_fields(model):
        joined = _map_at(joined, path, lambda v, kind=kind: resolve(view, kind, v) if isinstance(v, str) else v)
    return joined


def join_triage_rule(view: Any, rule: dict[str, Any], *, soft: bool = False) -> dict[str, Any]:
    """A triage rule with the projects and people it names held by id."""
    find = _soft if soft else resolve
    joined = dict(rule)
    for key, kind in (("projects", "project"), ("people", "person")):
        if joined.get(key):
            joined[key] = [find(view, kind, v) for v in joined[key]]
    return joined


def _join_source(view: Any, source: dict[str, Any], *, soft: bool = False) -> dict[str, Any]:
    find = _soft if soft else resolve
    joined = dict(source)
    if joined.get("project"):
        joined["project"] = find(view, "project", joined["project"])
    return joined


def join_watch_changes(view: Any, changes: dict[str, Any]) -> dict[str, Any]:
    """The settings the person is saving, with the sources' projects and the triage rules' projects and people held by
    id. Raises StoreError, saying which name, when one can't be matched."""
    joined = dict(changes)
    if isinstance(joined.get("watch.sources"), list):
        joined["watch.sources"] = [_join_source(view, s) if isinstance(s, dict) else s for s in joined["watch.sources"]]
    if isinstance(joined.get("watch.triage"), list):
        joined["watch.triage"] = [
            join_triage_rule(view, r) if isinstance(r, dict) else r for r in joined["watch.triage"]
        ]
    return joined


def join_scope(
    view: Any, scope: dict[str, Any] | None, references: Mapping[str, Any] | None = None, *, soft: bool = False
) -> dict[str, Any] | None:
    """A reach (`applies_to`) whose filter holds ids where it filters a reference field: a name is resolved to the id.
    A filter key that isn't a reference field, or one that points at more than one kind of record, is left as written.
    `references` is every declared reference (kind to [(path, target)]); the core's by default."""
    if not scope or not scope.get("filter"):
        return scope
    declared = references if references is not None else REFERENCES
    kinds = [t.partition(".")[0] for t in scope.get("records") or []] or list(declared)
    find = _soft if soft else resolve
    filtered: dict[str, Any] = {}
    for key, value in scope["filter"].items():
        targets = {target for kind in kinds for path, target in declared.get(kind, []) if path in (key, f"{key}[]")}
        if len(targets) == 1:
            (target,) = targets
            if isinstance(value, str):
                value = find(view, target, value)
            elif isinstance(value, list):
                value = [find(view, target, v) if isinstance(v, str) else v for v in value]
        filtered[key] = value
    return {**scope, "filter": filtered}


# ---- what older files and records hold -------------------------------------------------------------------------------


def join_stored_names(ws: Any, store: Any) -> list[str]:
    """Join by id what was stored by name before: the watch settings' sources and triage rules, and the reach of rules
    and lessons. A name that matches nothing is left as it was (a rule that names nothing closes nothing). Returns a
    line for each thing changed; running it again changes nothing."""
    changed: list[str] = []
    view = store.read()
    path = ws.config_dir / "watch.yaml"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        data = load_yaml(text) or {}
        for key, make in (("sources", _join_source), ("triage", join_triage_rule)):
            before = data.get(key)
            if not isinstance(before, list):
                continue
            after = [make(view, r, soft=True) if isinstance(r, dict) else r for r in before]
            if after != before:
                text = set_key(text, [key], after)
                changed.append(f"watch.{key}")
        if changed:
            path.write_text(text, encoding="utf-8")
    declared = store.plugins.references()
    for kind in SCOPED_KINDS:
        for stored in view.list(kind):
            scope = stored.data.get("applies_to")
            joined = join_scope(view, scope, declared, soft=True)
            if joined != scope:
                with store.transaction() as tx:
                    current = tx.get(kind, stored.id)
                    tx.update(kind, stored.id, {"applies_to": joined}, _MIGRATE, read_version=current.version)
                changed.append(f"{kind} {stored.id}")
    return changed
