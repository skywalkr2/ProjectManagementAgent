"""The accounts that carry acts (design 6.12).

An act names the account it goes through. An account is a sign-in's account (`<sign-in name>:<address>`) or a plain
mailbox the app reads (`mailbox:<source id>`). Acting is the person's switch for each account, kept in the
`watch.acting` setting, off until they turn it on: an act for an account that is off is carried out by Copy, and the
publisher never calls a channel for it.

Everything here reads; nothing writes a record or a setting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The kind of account a plain mailbox source is.
MAILBOX = "mailbox"
_SEP = ":"


@dataclass(frozen=True)
class AccountInfo:
    """One account an act can go through: its id, what it is called, and whether acting is on for it."""

    id: str
    label: str
    acting: bool


def account_id(kind: str, name: str) -> str:
    """The id of an account: its kind (a sign-in's name, or `mailbox`) and its name (the address, or the source id)."""
    return f"{kind}{_SEP}{' '.join(name.split())}"


def kind_of(account: str) -> str:
    """The kind of an account id: the sign-in it belongs to, or `mailbox`."""
    return account.split(_SEP, 1)[0]


def name_of(account: str) -> str:
    """The name part of an account id: the address, or the source id."""
    return account.split(_SEP, 1)[1] if _SEP in account else ""


def same(a: str, b: str) -> bool:
    """Whether two account ids are one account: the kind exactly and the name ignoring case (an address is one account
    in any case)."""
    return kind_of(a) == kind_of(b) and name_of(a).lower() == name_of(b).lower()


def acting_on(cfg: Any, account: str | None) -> bool:
    """Whether the person turned acting on for this account."""
    return account is not None and any(same(account, on) for on in cfg.watch.acting)


def _keys(store: Any, plugin: str) -> Path:
    return Path(store.path.parent) / ".cockpit" / "keys" / plugin


def _signed_in(store: Any, sign_in: Any) -> list[str | None]:
    from engine import sign_in as flow

    try:
        return [a.address for a in flow.list_accounts(_keys(store, sign_in.plugin), sign_in)]
    except OSError:
        return []


def known(store: Any, cfg: Any) -> list[AccountInfo]:
    """The accounts acts can go through now: each signed-in account of each add-on's sign-in, and each plain mailbox the
    workspace reads."""
    found: list[AccountInfo] = []
    for sign_in in store.plugins.sign_ins().values():
        for address in _signed_in(store, sign_in):
            if address:
                found.append(_info(cfg, account_id(sign_in.name, address), f"{sign_in.label} ({address})"))
    for source in cfg.watch.sources:
        if source.connector == MAILBOX:
            found.append(_info(cfg, account_id(MAILBOX, source.id), source.label or source.id))
    return found


def _info(cfg: Any, account: str, label: str) -> AccountInfo:
    return AccountInfo(account, label, acting_on(cfg, account))


def label_of(store: Any, cfg: Any, account: str | None) -> str | None:
    """What an account is called on screen, or its id when it is no longer listed."""
    if account is None:
        return None
    return next((a.label for a in known(store, cfg) if same(a.id, account)), account)


def of_watched_source(store: Any, cfg: Any, source_id: str, account: str | None = None) -> str | None:
    """The account a watched source reads with, or None when it has none: a plain mailbox is its own account; an
    add-on's source reads as the account it names, else the only account its add-on is signed in to."""
    source = next((s for s in cfg.watch.sources if s.id == source_id), None)
    if source is None:
        return None
    if source.connector == MAILBOX:
        return account_id(MAILBOX, source.id)
    plugin = source.connector.split("/", 1)[0] if "/" in source.connector else None
    if plugin is None:
        return None
    sign_ins = [s for s in store.plugins.sign_ins().values() if s.plugin == plugin]
    named = [s for s in sign_ins if any(d.get("connector") == source.connector for d in s.sources)]
    sign_in = (named or sign_ins or [None])[0] if len(named or sign_ins) == 1 else None
    if sign_in is None:
        return None
    address = source.account or account
    if not address:
        addresses = {a for a in _signed_in(store, sign_in)}
        address = next(iter(addresses)) if len(addresses) == 1 else None
    return account_id(sign_in.name, address) if address else None


def of_record(view: Any, store: Any, cfg: Any, record_id: str) -> str | None:
    """The account a saved message or a calendar entry came in on: the account of the watched source it was read from.
    None when it came in another way (pasted, a folder, a link)."""
    found = view.get("source", record_id)
    if found is not None:
        watched = found.data.get("watched")
        return of_watched_source(store, cfg, watched["source"]) if watched else None
    entry = view.get("event", record_id)
    if entry is not None and entry.data.get("source"):
        return of_record(view, store, cfg, entry.data["source"])
    return None


def last_picked(view: Any) -> str | None:
    """The account the person's latest act named, for a new message or event that names none."""
    named = [a for a in view.list("act") if a.data.get("account")]
    named.sort(key=lambda a: int(a.id.rpartition("-")[2]), reverse=True)
    return named[0].data["account"] if named else None
