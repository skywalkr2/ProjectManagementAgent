"""The audit trail: sign-ins, sign-outs and turning add-ons on or off, each kept as an `audit_entry` record.

An entry names what happened and to what (the sign-in's name and label, or the add-on's name) and when. It never holds a
token, a secret or the account's name. The records are in the export and the ledger like any other; no screen lists
them yet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from engine.storage import WriteContext

KINDS = ("sign_in", "sign_out", "plugin_on", "plugin_off")


def entry(
    kind: str, subject: str, *, label: str | None = None, detail: str | None = None, at: datetime | None = None
) -> dict[str, Any]:
    """The data of one audit entry."""
    if kind not in KINDS:
        raise ValueError(f"there is no audit kind {kind}")
    return {
        "kind": kind,
        "subject": subject,
        "label": label,
        "detail": detail,
        "at": (at or datetime.now(UTC)).isoformat(),
    }


def _write(tx: Any, kind: str, data: dict[str, Any]) -> None:
    tx.create("audit_entry", data, WriteContext("pm", "trusted", f"audit.{kind}"))


def record(store: Any, kind: str, subject: str, *, label: str | None = None, detail: str | None = None) -> None:
    """Write one entry in its own transaction."""
    with store.transaction() as tx:
        _write(tx, kind, entry(kind, subject, label=label, detail=detail))


def plugin_changes(tx: Any, before: list[str], after: list[str]) -> None:
    """In the open transaction `tx`, one entry for each add-on in `after` and not in `before` (turned on), and one for
    each in `before` and not in `after` (turned off)."""
    now = datetime.now(UTC)
    for name in after:
        if name not in before:
            _write(tx, "plugin_on", entry("plugin_on", name, at=now))
    for name in before:
        if name not in after:
            _write(tx, "plugin_off", entry("plugin_off", name, at=now))
