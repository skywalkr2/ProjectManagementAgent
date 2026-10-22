"""A to-do's reminder on the app's own calendar (design 6.12).

When the person has chosen "My calendar", each open to-do with a reminder time still ahead gets an entry on the app's
own calendar (a `CalendarEntry` with `reminder` naming the to-do and an alarm at its start). The entry is local data:
nothing is published outside the workspace, so it is no act and needs no yes. The engine keeps it true: a snooze moves
the same entry, and a reminder cleared, or a to-do that is done, dropped or put on hold, removes it. Each is the
engine's own `reminder.entry` op, so it is in the ledger and Undo takes it back. A to-do never gets two entries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from engine import reminder_content, reminder_template
from engine.blocked import standing_hold
from engine.ops import ReminderEntryOp
from engine.storage import StoreError, WriteContext
from engine.storage.store import Tx


def entries_of(view: Any, action_id: str) -> list[Any]:
    """The calendar entries the engine made as this to-do's reminder."""
    return [e for e in view.list("event") if e.data.get("reminder") == action_id]


def apply(tx: Tx, op: ReminderEntryOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    """Make, move or remove a to-do's reminder entry. Only the engine's own reminders may."""
    if ctx.actor != "reminders":
        raise StoreError("only the engine's reminders keep a reminder on the calendar")
    action = tx.get("action", op.action)
    if action is None:
        raise StoreError(f"to-do {op.action} doesn't exist")
    have = entries_of(tx, op.action)
    if op.at is None:
        for entry in have:
            tx.delete("event", entry.id, w, read_version=entry.version)
        return [{"kind": "event", "id": entry.id} for entry in have]
    if action.data.get("status") != "open" or standing_hold(tx, action.data):
        raise StoreError("that to-do has no reminder to keep")
    minutes = int(reminder_template.load(reminder_content.root_of(ctx.store))["event_minutes"])
    start = op.at.astimezone(UTC)
    fields = {
        "title": " ".join(str(action.data["text"]).split()),
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=minutes)).isoformat(),
        "project": action.data.get("project"),
        "reminder": op.action,
        "alarm_minutes": 0,
        "trust": "trusted",
    }
    if have:
        entry = have[0]
        tx.update("event", entry.id, fields, w, read_version=entry.version)
        return [{"kind": "event", "id": entry.id}]
    return [{"kind": "event", "id": tx.create("event", fields, w).id}]


def due_entry(view: Any, action: Any, now: datetime) -> datetime | None:
    """The reminder time an open to-do's entry is for: its time while it is still ahead, else None."""
    d = action.data
    if d.get("status") != "open" or standing_hold(view, d) or not d.get("remind_at"):
        return None
    at = reminder_content.instant(d["remind_at"])
    return at if at >= now else None
