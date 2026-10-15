"""Credentials with a known end date (design 6.16): a key or sign-in that stops working on a day the person entered or
the service gave. Today says so a configured number of days ahead, naming every place the same credential is kept, so
renewing it in one place doesn't leave another to fail later. Nothing here reaches a service or reads a secret's value:
two references are the same credential when they point at the same environment variable or file."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from engine import sign_in as flow


@dataclass
class Expiry:
    """One credential that is about to stop working, or has: `kind` is "account" or "sign_in", `name` the account's
    short name or the sign-in's name, `ends` the day, `days_left` the days from today (below zero once it has passed)
    and `places` every place it is used, in plain words, the credential's own first."""

    kind: str
    name: str
    ends: date
    days_left: int
    places: list[str] = field(default_factory=list)


def same_credential(ref: str | None) -> str | None:
    """What a secret reference points at, so two references to one thing compare equal: the variable's name, or the
    file's full path. None for no reference."""
    if not ref or not str(ref).strip():
        return None
    scheme, _, name = str(ref).strip().partition(":")
    if scheme == "file":
        return "file:" + str(Path(name).expanduser())
    return f"{scheme}:{name}"


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def uses_of(cfg: Any, ref: str, skip_account: str | None = None) -> list[str]:
    """Every place in the settings that holds the same secret reference, in plain words: AI accounts, an add-on's
    secrets, the key that encrypts backups, a private pack's read token and a watched source's own settings."""
    wanted = same_credential(ref)
    found: list[str] = []
    for name, provider in cfg.ai.providers.items():
        if name != skip_account and same_credential(provider.auth) == wanted:
            found.append(f"the AI account {name}")
    for plugin, secrets in sorted(cfg.workspace.plugins.secrets.items()):
        for secret, value in sorted(secrets.items()):
            if same_credential(value) == wanted:
                found.append(f"the add-on {plugin}'s secret {secret}")
    if same_credential(cfg.storage.backups.encrypt) == wanted:
        found.append("the key that locks the backups")
    for host, value in sorted(cfg.workspace.plugins.catalog.release_tokens.items()):
        if same_credential(value) == wanted:
            found.append(f"the read token for {host}")
    for source in cfg.watch.sources:
        if any(same_credential(s) == wanted for s in _strings(source.settings) if s.startswith(("env:", "file:"))):
            found.append(f"the source {source.label or source.id}")
    return found


def expiring(ws: Any, cfg: Any, store: Any, now: datetime) -> list[Expiry]:
    """The credentials with a known end that is within `ai.credential_warn_days` days or already past, soonest first.
    An account's own end date comes from its settings; a sign-in's from what the service said when it was granted."""
    today = now.astimezone(UTC).date()
    window = cfg.ai.credential_warn_days
    found: list[Expiry] = []
    for name, provider in cfg.ai.providers.items():
        ends = provider.credential_expires
        if ends is None or (ends - today).days > window:
            continue
        others = uses_of(cfg, provider.auth, skip_account=name) if provider.auth else []
        found.append(Expiry("account", name, ends, (ends - today).days, [f"the AI account {name}", *others]))
    keys_root = ws.root / ".cockpit" / "keys"
    for sign_in in store.plugins.sign_ins().values():
        tokens = flow.kept(keys_root / sign_in.plugin, sign_in) or {}
        stamp = tokens.get("refresh_expires_at")
        if not isinstance(stamp, (int, float)):
            continue
        ends = datetime.fromtimestamp(stamp, UTC).date()
        if (ends - today).days > window:
            continue
        reading = [
            f"the source {s.label or s.id}" for s in cfg.watch.sources if s.connector.split("/", 1)[0] == sign_in.plugin
        ]
        found.append(
            Expiry("sign_in", sign_in.name, ends, (ends - today).days, [f"the {sign_in.label} sign-in", *reading])
        )
    return sorted(found, key=lambda e: (e.ends, e.name))
