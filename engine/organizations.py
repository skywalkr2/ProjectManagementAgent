"""Organizations people work for, kept as records (design 5.1): one name in one place, referred to by id.

`resolve` turns a name the assistant or an older workspace used into the organization's id, matching names and
aliases without regard to case, and creating the organization when none matches. `move_names` is the one-time move
of a workspace whose people still hold organization names.
"""

from __future__ import annotations

from typing import Any

from engine.storage import StoreError, WriteContext
from engine.text_shape import text_problem

_ENGINE = WriteContext(actor="engine", trust="trusted", op="organizations.move")


def find(tx: Any, name: str) -> str | None:
    """The id of the organization with this name or alias, or None."""
    wanted = " ".join(name.split()).casefold()
    for org in tx.list("organization"):
        names = [org.data["name"], *org.data.get("aliases", [])]
        if any(" ".join(n.split()).casefold() == wanted for n in names):
            return org.id
    return None


def resolve(tx: Any, value: str | None, w: WriteContext) -> str | None:
    """An organization's id from an id or a name: an id stays; a name finds its organization, or creates one."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise StoreError(
            text_problem("An organization's name or id", value) or "An organization's name or id has to be text."
        )
    if not value.strip():
        return None
    value = value.strip()
    if tx.get("organization", value) is not None:
        return value
    return find(tx, value) or tx.create("organization", {"name": " ".join(value.split())}, w).id


def move_names(store: Any) -> int:
    """Give every person who holds an organization's name the organization's id instead. Returns how many moved."""
    moved = 0
    with store.transaction() as tx:
        for person in tx.list("person"):
            held = person.data.get("org")
            if not held or tx.get("organization", held) is not None:
                continue
            tx.update("person", person.id, {"org": resolve(tx, held, _ENGINE)}, _ENGINE, read_version=person.version)
            moved += 1
    return moved
