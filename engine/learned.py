"""What the assistant learned from one correction, as the correction's own card shows it (design 7.18).

Plain functions over a read of the records, with no AI. A correction's card shows one line: the learning is still
being worked on, there is a proposal to keep, or the person's own words were kept at once and can be undone. The
signal links a correction to the changeset it corrects and to the entry learned from it; this module follows those
links, so the screens never have to.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from engine import knowledge, learn
from engine.records import REGISTRY

#: The states of the learning request that mean the assistant is still working on a correction.
PENDING_STATES = ("queued", "running", "needs_you")
#: The kinds of record an entry the assistant said it applied can be.
APPLIED_KINDS: tuple[str, ...] = (*knowledge.KINDS, "rule", "fact")

LEARNING, PROPOSED, KEPT = "learning", "proposed", "kept"


def signal_of_entry(stored: Any) -> str | None:
    """The correction an entry was learned from, as its evidence (or, for a lesson, its own field) names it."""
    data = stored.data
    return (data.get("evidence") or {}).get("signal") or data.get("signal")


def changeset_of_signal(view: Any, signal_id: str) -> str | None:
    """The changeset a correction is about, as the signal names it; None when it names none."""
    found = view.get("signal", signal_id)
    return found.data.get("changeset") if found is not None else None


def changeset_of_entry(view: Any, stored: Any) -> str | None:
    """The changeset the correction an entry was learned from is about; None for an entry that came from an input."""
    signal_id = signal_of_entry(stored)
    if signal_id is None:
        return None
    return changeset_of_signal(view, signal_id) or (stored.data.get("evidence") or {}).get("changeset")


@dataclass(frozen=True)
class Line:
    """The learning of one correction: its `signal`, what state it is in, the waiting request's words while it is
    being learned, the entry once there is one, and for the person's own words kept at once the changeset to undo."""

    signal: str
    state: str
    waiting: str | None = None
    entry: Any | None = None
    kind: str | None = None
    undo: str | None = None


def _pending(view: Any) -> dict[str, Any]:
    """The learning requests still being worked on, by the signal each learns from."""
    found: dict[str, Any] = {}
    for request in view.list("request"):
        signal_id = learn.signal_of(request.data)
        if signal_id and request.data["state"] in PENDING_STATES and not request.data.get("dismissed"):
            found[signal_id] = request
    return found


def _created_in(view: Any, kind: str, record_id: str) -> str | None:
    """The changeset that made a record, from the first entry of its history."""
    entries = view.ledger(kind=kind, record_id=record_id)
    return entries[0]["changeset"] if entries else None


def lines(view: Any, *, hidden: Collection[str] = ()) -> list[Line]:
    """One line for each correction the assistant is learning from or has learned from: the entry proposed from it, or
    the person's own words kept at once. Entries in `hidden` (the catch-up list's) are left out, and corrections with
    nothing to show, learned from with nothing to propose, have no line."""
    out: dict[str, Line] = {}
    for kind in knowledge.KINDS:
        for stored in view.list(kind):
            signal_id = signal_of_entry(stored)
            if signal_id is None or stored.id in hidden or view.get("signal", signal_id) is None:
                continue
            status = stored.data.get("status")
            if status == "proposed":
                out[signal_id] = Line(signal_id, PROPOSED, entry=stored, kind=kind)
            elif status == "active" and stored.data.get("origin") == "person":
                out[signal_id] = Line(signal_id, KEPT, entry=stored, kind=kind, undo=_created_in(view, kind, stored.id))
    for signal_id, request in _pending(view).items():
        if signal_id not in out and view.get("signal", signal_id) is not None:
            out[signal_id] = Line(signal_id, LEARNING, waiting=request.data.get("waiting"))
    return sorted(out.values(), key=lambda line: _number(line.signal))


def _number(record_id: str) -> int:
    tail = record_id.rpartition("-")[2]
    return int(tail) if tail.isdigit() else 0


def applied_entries(view: Any, ids: list[str]) -> list[tuple[str, Any]]:
    """The entries a run said it applied that still exist, in the order named, each with its record kind: a piece of
    what was learned, a standing rule or a fact."""
    found: list[tuple[str, Any]] = []
    for entry_id in ids:
        kind = learn.kind_of_id(REGISTRY, entry_id)
        stored = view.get(kind, entry_id) if kind in APPLIED_KINDS else None
        if stored is not None:
            found.append((str(kind), stored))
    return found


def request_changeset(view: Any, request_id: str | None) -> str | None:
    """The changeset a request produced, when it has one."""
    found = view.get("request", request_id) if request_id else None
    return found.data.get("changeset") if found is not None else None
