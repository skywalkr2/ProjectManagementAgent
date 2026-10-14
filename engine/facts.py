"""Facts that replace one another (design 6.22).

A fact says which fact it replaces (`supersedes`). The older fact is never edited: what replaced it is worked out from
the newer fact, so undoing the newer fact brings the older one back with no second write to undo.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from engine.storage import StoreError


def superseded_by(view: Any, fact_id: str) -> str | None:
    """The id of the fact that replaces this one, or None when it is still the latest word."""
    for stored in view.list("fact"):
        if stored.data.get("supersedes") == fact_id:
            return stored.id
    return None


def check_replaces(tx: Any, fact_id: str | None) -> None:
    """Refuse a replacement that points at nothing, or at a fact something else already replaced."""
    if fact_id is None:
        return
    if tx.get("fact", fact_id) is None:
        raise StoreError(f"there is no fact {fact_id} to replace")
    newer = superseded_by(tx, fact_id)
    if newer is not None:
        raise StoreError(f"{fact_id} was already replaced by {newer}; replace that one instead")


def received_on(tx: Any, request_id: str | None, source_id: str | None) -> date | None:
    """The day an input was received: its source's received time, else when the request was made; None when neither
    is known."""
    source = tx.get("source", source_id) if source_id else None
    request = tx.get("request", request_id) if request_id else None
    for stored, field in ((source, "received_at"), (request, "created_at")):
        value = stored.data.get(field) if stored is not None else None
        if value:
            return datetime.fromisoformat(str(value)).date()
    return None
