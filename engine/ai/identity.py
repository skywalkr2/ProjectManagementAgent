"""Which sign-in a command-line agent runs as (design 6.16).

The account check reads it from the program itself (the adapter's `identity()`) and records it here, beside the check's
other results. A later check or run that reads a different one doesn't replace it: the new one waits as a pending change
until the person answers, Keep (it becomes the recorded one) or Sign in again (the next reading decides). While a change
waits, the account is treated as allowed open material only, so work that needs more waits. An identity that can't be
read is recorded as unknown with the reason, and never changes what was recorded before.

What is kept lives on this computer, in the workspace's private folder, for each account by its short name. Nothing here
is a setting.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.ai.task import AgentIdentity, AiError, IdentityUnknown
from engine.secrets import SecretError, resolve_secret
from engine.state_file import changing, write_whole

STATE_FILE = "ai-identity.json"


@dataclass(frozen=True)
class Shown:
    """What is known about one account's sign-in, for its row in Settings: the recorded identity (with how it was
    read), why the last reading couldn't tell, and the different identity waiting for the person's answer."""

    recorded: AgentIdentity | None = None
    unknown: str | None = None
    changed_to: str | None = None
    read_at: datetime | None = None


def _path(where: Any) -> Path:
    return Path(where.private_dir) / STATE_FILE


def _read(where: Any) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_path(where).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return (
        {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(data, dict) else {}
    )


def _write(where: Any, data: dict[str, dict[str, Any]]) -> None:
    write_whole(_path(where), json.dumps(data, sort_keys=True, indent=2) + "\n")


def _identity(row: Any) -> AgentIdentity | None:
    if isinstance(row, dict) and isinstance(row.get("account"), str) and row["account"]:
        return AgentIdentity(row["account"], str(row.get("how_read") or ""))
    return None


def _stamp(text: Any) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def recorded(where: Any, name: str) -> AgentIdentity | None:
    """The identity recorded for an account, or None when none was read yet."""
    return _identity(_read(where).get(name, {}).get("recorded"))


def shown(where: Any, name: str) -> Shown:
    """What is known about an account's sign-in; empty for an account that was never read."""
    row = _read(where).get(name, {})
    found = _identity(row.get("found"))
    return Shown(
        recorded=_identity(row.get("recorded")),
        unknown=row.get("unknown") if isinstance(row.get("unknown"), str) else None,
        changed_to=found.account if found else None,
        read_at=_stamp(row.get("read_at")),
    )


def pending(where: Any) -> dict[str, tuple[AgentIdentity, AgentIdentity, str]]:
    """The accounts whose sign-in changed and wait for the person: for each, the recorded identity, the new one and when
    the change was found."""
    out = {}
    for name, row in sorted(_read(where).items()):
        before, found = _identity(row.get("recorded")), _identity(row.get("found"))
        if before is not None and found is not None:
            out[name] = (before, found, str(row.get("found_at") or ""))
    return out


def held(where: Any) -> dict[str, str]:
    """The accounts whose sign-in changed and wait for the person, each with the identity found now."""
    return {name: found.account for name, (_, found, _) in pending(where).items()}


def observe(where: Any, name: str, found: AgentIdentity | IdentityUnknown | None, now: datetime | None = None) -> str:
    """Take in one reading of an account's sign-in. Returns what it meant: `none` (the adapter has no identity, nothing
    kept), `recorded` (the first reading), `same`, `changed` (a different identity now waits for the person) or
    `unknown` (the reading failed; what was recorded stands)."""
    if found is None:
        return "none"
    stamp = (now or datetime.now(UTC)).isoformat()
    with changing(_path(where)):
        data = _read(where)
        row = dict(data.get(name) or {})
        row["read_at"] = stamp
        before = _identity(row.get("recorded"))
        if isinstance(found, IdentityUnknown):
            row["unknown"] = found.reason
            outcome = "unknown"
        else:
            row["unknown"] = None
            seen = {"account": found.account, "how_read": found.how_read}
            if before is None:
                row.update(recorded={**seen, "at": stamp}, found=None, found_at=None)
                outcome = "recorded"
            elif _same(before.account, found.account):
                row.update(found=None, found_at=None)
                outcome = "same"
            else:
                already = _identity(row.get("found"))
                row["found"] = seen
                if already is None or not _same(already.account, found.account):
                    row["found_at"] = stamp
                outcome = "changed"
        data[name] = row
        _write(where, data)
    return outcome


def keep(where: Any, name: str) -> bool:
    """Record the identity waiting for the person's answer as the account's own. False when none waits."""
    with changing(_path(where)):
        data = _read(where)
        row = data.get(name) or {}
        found = row.get("found")
        if _identity(found) is None:
            return False
        row.update(recorded={**found, "at": datetime.now(UTC).isoformat()}, found=None, found_at=None)
        data[name] = row
        _write(where, data)
    return True


def due(where: Any, name: str, every_seconds: float, now: datetime) -> bool:
    """Whether a run should read the account's sign-in again: it was never read, or its last reading is older than the
    configured time."""
    at = shown(where, name).read_at
    return at is None or (now - at).total_seconds() >= every_seconds


def watch(
    where: Any,
    cfg: Any,
    name: str,
    adapter_factory: Callable[[str, Any, str | None], Any],
    env: Mapping[str, str] | None,
    now: datetime,
) -> str:
    """Before a run: read an agent account's sign-in again when its configured time has passed, and take the reading in.
    An account with no identity command, or an adapter without the capability, is left alone."""
    settings = cfg.ai.providers.get(name)
    agent = getattr(settings, "agent", None)
    if agent is None or not agent.identity_command or not due(where, name, agent.identity_recheck_seconds, now):
        return "none"
    try:
        adapter = adapter_factory(settings.adapter, settings, resolve_secret(settings.auth, env))
    except (SecretError, AiError, ValueError):
        return "none"  # the run itself says why it can't start
    reader = getattr(adapter, "identity", None)
    return observe(where, name, reader() if callable(reader) else None, now)
