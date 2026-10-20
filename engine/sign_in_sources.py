"""Sources a sign-in starts: once the person signs in, the core starts reading what the plugin declared for that
sign-in (the inbox, the main calendar), so signing in is the whole setup. Each account's sources are added once, and
only where the workspace reads nothing with that connector as that account yet; the person's later changes stand.
Which accounts have had theirs added is kept on this computer, beside the sign-ins themselves."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from engine import settings as config_screens
from engine.config import ConfigError, load_config
from engine.state_file import changing, write_whole

STATE = "sign-in-sources.json"


def _state_path(ws: Any) -> Path:
    return ws.private_dir / STATE


def _started(ws: Any) -> set[str]:
    try:
        return set(json.loads(_state_path(ws).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _remember(ws: Any, names: set[str]) -> None:
    """Add `names` to the sign-ins that have had their sources added. The file is read again under its lock, so
    sign-ins finishing at the same moment each stay recorded."""
    with changing(_state_path(ws)):
        write_whole(_state_path(ws), json.dumps(sorted(_started(ws) | names)))


def _keys(ws: Any, sign_in: Any) -> Path:
    return ws.root / ".cockpit" / "keys" / sign_in.plugin


def _addresses(ws: Any, sign_in: Any) -> list[str | None]:
    """The addresses of the accounts signed in to a sign-in (None for one never named); one entry of None when no
    account is signed in, so a sign-in with nothing signed in is still looked at once."""
    from engine.sign_in import list_accounts

    return [a.address for a in list_accounts(_keys(ws, sign_in), sign_in)] or [None]


def accounts_of(ws: Any, store: Any, plugin: str) -> list[str] | None:
    """The addresses of the accounts signed in across a plugin's sign-ins that name their accounts, oldest first; None
    when the plugin has no such sign-in (its sources have no account to choose)."""
    from engine.sign_in import list_accounts

    own = [s for s in store.plugins.sign_ins().values() if s.plugin == plugin and s.account is not None]
    if not own:
        return None
    found: list[str] = []
    for sign_in in own:
        for a in list_accounts(_keys(ws, sign_in), sign_in):
            if a.address and a.address.lower() not in {f.lower() for f in found}:
                found.append(a.address)
    return found


def _reads(sources: list[Any], connector: str, address: str | None, only: str | None) -> bool:
    """Whether a source reads with this connector as this account: any account when it has no address; a source that
    names none reads the one account signed in (`only`, when there is exactly one)."""
    return any(
        (s["connector"] if isinstance(s, dict) else s.connector) == connector
        and (address is None or ((s["account"] if isinstance(s, dict) else s.account) or only) == address)
        for s in sources
    )


def not_read(ws: Any, sign_in: Any) -> list[str]:
    """The labels of the sign-in's declared sources the workspace reads nothing with yet for some signed-in account
    (none were added, or the person removed them), so the screens can offer to start them with one click."""
    try:
        current = load_config(ws.config_dir, env=dict(os.environ))
    except ConfigError:
        return []
    addresses = _addresses(ws, sign_in)
    only = addresses[0] if len(addresses) == 1 else None
    return [
        s["label"]
        for s in sign_in.sources
        if any(not _reads(current.watch.sources, s["connector"], a, only) for a in addresses)
    ]


def start_sources(
    ws: Any, cfg: Any, store: Any, sign_in: Any, *, again: bool = False, accounts: list[str | None] | None = None
) -> list[str]:
    """Add the sign-in's declared sources the workspace doesn't read yet, for each account just signed in (`accounts`,
    by address; left out, every account signed in): once per account, or `again` when the person asks for them. Each
    source reads with the account it was started for. Returns the labels added. Sign-ins finishing at the same moment
    are handled one after the other, so the check that an account's sources were added and the adding itself never
    interleave."""
    with changing(_state_path(ws)):
        return _start_sources(ws, cfg, store, sign_in, again=again, accounts=accounts)


def _marker(sign_in: Any, address: str | None) -> str:
    from engine.sign_in import account_key

    return sign_in.name if address is None else f"{sign_in.name}#{account_key(address)}"


def _done(started: set[str], sign_in: Any, address: str | None) -> bool:
    """Whether this account's sources were added. Sign-ins made before accounts were kept apart are marked by the
    sign-in's name alone, which covers the accounts that existed then."""
    if _marker(sign_in, address) in started:
        return True
    return sign_in.name in started and not any(m.startswith(sign_in.name + "#") for m in started)


def _start_sources(
    ws: Any, cfg: Any, store: Any, sign_in: Any, *, again: bool, accounts: list[str | None] | None
) -> list[str]:
    started = _started(ws)
    signed = _addresses(ws, sign_in)
    wanted_for = signed if accounts is None else accounts
    pending = [a for a in wanted_for if again or not _done(started, sign_in, a)]
    try:
        current = load_config(ws.config_dir, env=dict(os.environ))
    except ConfigError:
        return []
    sources = [s.model_dump(mode="json") for s in current.watch.sources]
    connectors = {
        name: connector
        for registrar in store.plugins.registrars.values()
        for name, connector in registrar.connectors.items()
    }
    # With a second account signed in, a source that names none would have to choose: it keeps the account it was
    # reading, the first one.
    named = [a for a in signed if a is not None]
    first = named[0] if named else None
    changed = False
    if len(named) > 1 and first is not None:
        for source in sources:
            if source["connector"].split("/", 1)[0] == sign_in.plugin and not source.get("account"):
                source["account"] = first
                changed = True
    only = signed[0] if len(signed) == 1 else None
    taken = {s["id"] for s in sources}
    added = []
    for address in pending:
        for wanted in sign_in.sources:
            connector = connectors.get(wanted["connector"])
            if connector is None or _reads(sources, wanted["connector"], address, only):
                continue
            base = re.sub(r"[^a-z0-9]+", "-", wanted["label"].lower()).strip("-")[:40] or "source"
            source_id = (
                base if base not in taken else next(f"{base}-{n}" for n in range(2, 999) if f"{base}-{n}" not in taken)
            )
            taken.add(source_id)
            settings = connector.settings.model_validate(wanted["settings"]).model_dump(
                mode="json", exclude_defaults=True
            )
            sources.append(
                {
                    "id": source_id,
                    "connector": wanted["connector"],
                    "label": wanted["label"],
                    "every_minutes": wanted["every_minutes"],
                    # The first read is taken in quietly (one total, one go, one list to look over), not item by item.
                    "first_run": "intake",
                    "settings": settings,
                    **({"account": address} if address else {}),
                }
            )
            added.append(wanted["label"])
    if added or changed:
        config_screens.save(
            ws,
            cfg,
            store,
            changes={"watch.sources": sources},
            reset=[],
            read_fingerprint=config_screens.fingerprint(ws.config_dir),
            env=dict(os.environ),
            allow=("watch.sources",),
        )
    if pending:
        _remember(ws, {_marker(sign_in, a) for a in pending})
    return added


def start_signed_in(ws: Any, cfg: Any, store: Any) -> list[str]:
    """At start-up: sources for sign-ins already signed in before their plugin declared any (or before this app
    started them). Returns the labels added."""
    from engine.sign_in import list_accounts

    added = []
    for registrar in store.plugins.registrars.values():
        if not store.plugins.active(registrar.name):
            continue
        for sign_in in registrar.sign_ins.values():
            if not sign_in.sources:
                continue
            keys = ws.root / ".cockpit" / "keys" / registrar.name
            started = _started(ws)
            fresh = [a.address for a in list_accounts(keys, sign_in) if not _done(started, sign_in, a.address)]
            if fresh:
                added += start_sources(ws, cfg, store, sign_in, accounts=fresh)
    return added
