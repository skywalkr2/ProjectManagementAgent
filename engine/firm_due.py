"""An action's due date as a deadline.

A date the rules could not read for certain is kept with `due_check`, so the person checks it. Until they confirm it,
it is a date to look at, not a deadline: nothing is reminded, at risk, overdue or chased because of it. Every place
that turns a due date into urgency reads it through here."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any


def firm_due(data: Mapping[str, Any]) -> date | None:
    """The day an action is due as a deadline: its date, or None when it has none or the date is still to be checked."""
    if data.get("due_check") or not data.get("due"):
        return None
    return date.fromisoformat(str(data["due"]))
