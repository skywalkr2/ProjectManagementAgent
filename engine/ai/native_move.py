"""Moving a saved account to its service's own connection, only on the person's yes (design 6.16).

An account saved before the catalog named a native adapter for its service keeps the adapter its own settings name until
the person re-adds it. This module finds those accounts (the account's address is a catalog service whose entry names
another adapter than the account uses), says in plain words which identity the new connection would sign in as, from
what is known without a call, runs the account's connection check on the new connection before anything is written, and
keeps "Not now" for an account so the question never comes back unasked.

Nothing here writes a setting: `planned` says what would change and the Move route writes it through the settings save,
with Undo, only after `check` passed. The check is the account check (one call per tier and kind of work with its exact
parameters, the lock-down check for an agent and the learning round-trip), made on a copy of the settings with the new
connection. Nothing here reads a vendor's name: the service, its address and its adapter come from the catalog's data.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from engine.ai.adapters import ADAPTERS, GENERIC_ADAPTER, make_adapter
from engine.ai.smoke import SmokeResult, smoke_test
from engine.config import Config
from engine.config.schema import ProviderSettings, TierSettings
from engine.secrets import SecretError, resolve_secret
from engine.state_file import changing, write_whole

STATE_FILE = "ai-moves.json"

#: The generic adapter an account was saved on before a service had one of its own.
GENERIC = GENERIC_ADAPTER
#: A key shorter than this shows no characters of itself in the read-back.
MIN_KEY_TO_SHOW = 8


def path_of(store: Any) -> Path:
    """Where this workspace keeps which accounts' moves the person put off."""
    return store.path.parent / ".cockpit" / STATE_FILE


def host_of(address: str | None) -> str:
    """The host part of an address, lowercase, or empty."""
    return (urlsplit(address or "").hostname or "").lower()


def service_of(provider: ProviderSettings, endpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The catalog entry of the service an account's address belongs to and that names another adapter than the
    account uses, or None: an account with no address, one already on its service's adapter, one that isn't on the
    generic adapter, and one whose service has no entry of its own all have none."""
    host = host_of(provider.base_url)
    if not host or provider.adapter != GENERIC:
        return None
    for entry in endpoints:
        if entry["adapter"] != provider.adapter and entry["adapter"] in ADAPTERS and host_of(entry["base_url"]) == host:
            return entry
    return None


@dataclass(frozen=True)
class Move:
    account: str
    service: str  # the catalog's name for it, for words on screen
    entry: dict[str, Any]


def candidates(cfg: Config, endpoints: list[dict[str, Any]], store: Any = None) -> list[Move]:
    """The accounts that could move to their service's own connection and whose person hasn't put it off."""
    off = put_off(store) if store is not None else set()
    found = []
    for name, provider in sorted(cfg.ai.providers.items()):
        entry = service_of(provider, endpoints)
        if entry is not None and name not in off:
            found.append(Move(name, entry["name"], entry))
    return found


def planned(provider: ProviderSettings, entry: Mapping[str, Any]) -> dict[str, Any]:
    """The settings of the account that change with the move, by field name: its adapter, the service's own address
    when it differs, and each setting the service's entry gives that the account hasn't set itself. What the person set
    on the account stays."""
    changes: dict[str, Any] = {"adapter": entry["adapter"]}
    if entry.get("base_url") and entry["base_url"] != provider.base_url:
        changes["base_url"] = entry["base_url"]
    for key, value in (entry.get("settings") or {}).items():
        if (
            key in ProviderSettings.model_fields
            and key not in provider.model_fields_set
            and getattr(provider, key) != value
        ):
            changes[key] = value
    return changes


@dataclass(frozen=True)
class Readback:
    """What the new connection would sign in as, from what is known without a call."""

    account: str  # the account's name as the person knows it
    service: str
    key_ending: str  # the last four characters of the key, or "" when it can't be read or is too short to show any
    key_known: bool  # whether the key could be read now
    key_differs: bool  # the new connection would use another key than the account does now
    address: str  # the new connection's host
    address_was: str
    address_differs: bool
    changes: dict[str, Any]


def _key(ref: str | None, env: Mapping[str, str] | None) -> str | None:
    try:
        return resolve_secret(ref, env)
    except SecretError:
        return None


def _ending(key: str | None) -> str:
    return key[-4:] if key and len(key) >= MIN_KEY_TO_SHOW else ""


def readback(
    provider: ProviderSettings, name: str, entry: Mapping[str, Any], env: Mapping[str, str] | None
) -> Readback:
    """The identity the new connection signs in as: the key (masked to its last four characters) and whether it is the
    one the account uses now, the address and whether it is the same, and the account's name, which doesn't change."""
    changes = planned(provider, entry)
    now = _key(provider.auth, env)
    then = _key(changes.get("auth", provider.auth), env)
    address = host_of(changes.get("base_url", provider.base_url))
    was = host_of(provider.base_url)
    return Readback(
        account=provider.label or name,
        service=str(entry["name"]),
        key_ending=_ending(then),
        key_known=then is not None,
        key_differs=then != now,
        address=address,
        address_was=was,
        address_differs=address != was,
        changes=changes,
    )


@dataclass(frozen=True)
class Checked:
    ok: bool
    detail: str
    results: list[SmokeResult]
    cfg: Config


def moved_config(cfg: Config, name: str, changes: Mapping[str, Any]) -> Config:
    """A copy of the settings in which the account has the new connection and the only kinds of work are those that
    use it (each on its own account/model, with the same effort, thinking and escalation), so the check makes the
    exact calls the account would make."""
    provider = cfg.ai.providers[name].model_copy(update=dict(changes))
    tiers: dict[str, TierSettings] = {}
    for tier_name, tier in cfg.ai.tiers.items():
        ref = next((r for r in [tier.use, *tier.fallback] if r.partition("/")[0] == name), None)
        if ref is not None:
            tiers[tier_name] = tier.model_copy(update={"use": ref, "fallback": []})
    if not tiers:
        first = next(iter(provider.models), "")
        tiers = {"account": TierSettings(use=f"{name}/{first}")}
    ai = cfg.ai.model_copy(update={"providers": {**cfg.ai.providers, name: provider}, "tiers": tiers})
    return replace(cfg, files={**cfg.files, "ai": ai})


def check(
    cfg: Config,
    env: Mapping[str, str],
    name: str,
    entry: Mapping[str, Any],
    store: Any = None,
    adapter_factory: Callable[[str, Any, str | None], Any] | None = None,
) -> Checked:
    """The account check on the new connection, before anything is written: every tier that uses the account, with
    the exact parameters. Only a check where every call answered passes; one that found no network, or couldn't run,
    doesn't, and says why."""
    moved = moved_config(cfg, name, planned(cfg.ai.providers[name], entry))
    results = smoke_test(moved, env, adapter_factory or make_adapter, store)
    bad = next((r for r in results if not r.ok), None)
    if not results:
        return Checked(False, "the account has no model to check", results, moved)
    if bad is not None:
        return Checked(False, bad.detail or "the check didn't pass", results, moved)
    return Checked(True, "", results, moved)


# ---- Not now ---------------------------------------------------------------------------------------------------------


def put_off(store: Any) -> set[str]:
    """The accounts whose move the person said Not now to."""
    try:
        data = json.loads(path_of(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    names = data.get("not_now") if isinstance(data, dict) else None
    return {n for n in names if isinstance(n, str)} if isinstance(names, list) else set()


def not_now(store: Any, name: str) -> None:
    """Remember that this account's move is put off: its line never comes back unasked."""
    with changing(path_of(store)):
        names = sorted(put_off(store) | {name})
        write_whole(path_of(store), json.dumps({"not_now": names}, indent=2) + "\n")
