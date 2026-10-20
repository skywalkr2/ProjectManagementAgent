"""History for readers: what is shown of a record's changes (its activity, a published page) leaves out a change that
only moves a date on an existing item.

A change is only a date move when the item's words are unchanged and nothing but a date moved: every field written in
that one change is a date (or the words that come with it, such as `due_words` beside `due`), and at least one of them
went from one date to another. Setting a first date, taking one away, or moving a date together with any other change
is news and stays. The ledger keeps every row; this only decides what a reader is shown. Reads only.
"""

from __future__ import annotations

import types
from datetime import date, datetime
from functools import cache
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

#: Fields that hold a date as text, by record kind, because their type is a string.
_TEXT_DATES: dict[str, frozenset[str]] = {"event": frozenset({"start", "end"})}


def _is_date_type(annotation: Any) -> bool:
    if annotation in (date, datetime):
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return any(_is_date_type(a) for a in get_args(annotation) if a is not type(None))
    return False


@cache
def _date_fields(model: type[BaseModel]) -> frozenset[str]:
    names = {name for name, info in model.model_fields.items() if _is_date_type(info.annotation)}
    kind = getattr(model, "record_kind", None)
    return frozenset(names | _TEXT_DATES.get(kind, frozenset()))


def date_fields(model: type[BaseModel]) -> set[str]:
    """The fields of a record type that hold a date: by type, and a calendar entry's start and end."""
    return set(_date_fields(model))


def _comes_with(field: str, dates: set[str]) -> bool:
    """Whether a field only qualifies a date that moved with it: `due_words` beside `due`."""
    return any(field.startswith(f"{d}_") for d in dates)


def is_date_move(rows: list[dict[str, Any]], model: type[BaseModel] | None) -> bool:
    """Whether the ledger rows of one change (one record, one version) only move a date on an existing item."""
    if model is None or not rows or any(r.get("field") is None for r in rows):
        return False
    dates = date_fields(model)
    changed = {r["field"] for r in rows}
    moved = {
        r["field"]
        for r in rows
        if r["field"] in dates
        and r.get("before") is not None
        and r.get("after") is not None
        and r["before"] != r["after"]
    }
    if not moved:
        return False
    return all(f in dates or _comes_with(f, moved) for f in changed)


def for_readers(rows: list[dict[str, Any]], model: type[BaseModel] | None) -> list[dict[str, Any]]:
    """One record's ledger rows, oldest first, without the changes that only move a date."""
    by_version: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        by_version.setdefault(row.get("version"), []).append(row)
    quiet = {v for v, group in by_version.items() if is_date_move(group, model)}
    return [r for r in rows if r.get("version") not in quiet]


def changes_for_readers(view: Any, kind: str, record_id: str) -> list[dict[str, Any]]:
    """A record's ledger rows as readers see them, oldest first: every change but a pure date move."""
    return for_readers(view.ledger(kind=kind, record_id=record_id), view.models.get(kind))
