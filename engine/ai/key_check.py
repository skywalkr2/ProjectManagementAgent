"""Checking an AI account before it is saved (design 6.16, 7.8): the check that runs the moment a key is pasted.

It is the same check an added account gets (`engine.ai.smoke.smoke_test`): every kind of work on every tier, with the
exact settings it will use, and for a command-line agent the lock-down and sign-in checks. The account is put into a
copy of the settings with each tier pointed at it, the pasted key is handed to the adapter and kept nowhere, and
nothing is written.

The result is one reason, worded for the kind of account (a hosted service never gets the advice for one on this
computer), and the sign-in the account runs as where the check could find it. The reason comes from the failure's own
kind (the call's status or transport), never from the words of a service or a model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from engine.ai.adapters import make_adapter
from engine.ai.smoke import SmokeResult, smoke_test, where_of
from engine.config import Config
from engine.config.schema import ProviderSettings, TierSettings

Reason = Literal["works", "key_missing", "key_refused", "no_credit", "unreachable", "wait", "not_signed_in", "failed"]

#: The name the account has inside the copy of the settings the check runs on.
CHECKED = "checked"


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    reason: Reason
    message: str  # in words that fit the kind of account; "" when it works
    identity: str | None = None  # the sign-in it runs as, when the check found it
    identity_unknown: str | None = None  # why that can't be told, in plain words, when it can't


#: What a failure means for an account reached with a key, by the kind the call itself gave.
_KEYED = {
    "auth": ("key_refused", "The service didn't accept that key. Check that it was copied whole and is still active."),
    "no_key": ("key_missing", "Paste your key to go on."),
    "quota": (
        "no_credit",
        "That account has no credit left. Add credit on the service's billing page, then paste the key again.",
    ),
    "rate_limited": ("wait", "The service asked to wait a moment. Try again shortly."),
}
#: What it means when the service can't be reached, by where the account lives.
_UNREACHABLE = {
    "hosted": "Couldn't reach the service. Check your internet connection and try again.",
    "local": "Couldn't reach it. Check the address, or start it if it runs on this computer.",
    "program": "The program didn't answer. Check this computer's network connection and try again.",
}
_TRANSPORT = frozenset({"provider_down", "offline", "timeout"})


def _failure(bad: SmokeResult, where: str) -> tuple[Reason, str]:
    """The reason and the words for a failed part of the check."""
    kind = bad.error_kind
    if kind in _TRANSPORT:
        return "unreachable", _UNREACHABLE.get(where, _UNREACHABLE["local"])
    if where == "program" and kind in ("auth", "no_work"):
        return "not_signed_in", bad.detail
    if kind in _KEYED:
        reason, words = _KEYED[kind]
        return reason, words  # type: ignore[return-value]
    return "failed", bad.detail


def check_account(
    cfg: Config,
    env: Mapping[str, str],
    provider: ProviderSettings,
    key: str | None,
    *,
    use: Mapping[str, str] | None = None,
    adapter_factory: Callable[[str, Any, str | None], Any] = make_adapter,
    store: Any = None,
) -> KeyCheck:
    """Check a new account on every tier of the settings. `provider` is the account as it would be saved (its models,
    address and, for an agent, its command); `key` is the pasted key, used for the calls and kept nowhere; `use` names
    the model (by its short name) each tier would use, the account's first for a tier it leaves out."""
    if not provider.models:
        return KeyCheck(False, "failed", "Choose a model to check.")
    first = next(iter(provider.models))
    tiers = {
        name: TierSettings(
            use=f"{CHECKED}/{(use or {}).get(name) if (use or {}).get(name) in provider.models else first}"
        )
        for name in cfg.ai.tiers
    }
    ai = cfg.ai.model_copy(update={"providers": {**cfg.ai.providers, CHECKED: provider}, "tiers": tiers})
    results = smoke_test(
        replace(cfg, files={**cfg.files, "ai": ai}), env, lambda name, s, _: adapter_factory(name, s, key), store
    )
    where = where_of(provider)
    bad = next((r for r in results if not r.ok and r.error_kind != ""), None) or next(
        (r for r in results if not r.ok), None
    )
    if bad is not None:
        reason, words = _failure(bad, where)
        return KeyCheck(False, reason, words)
    identity = next((r.identity for r in results if r.part == "identity" and r.identity), None) or {}
    if "account" in identity:
        return KeyCheck(True, "works", "", identity=identity["account"])
    unknown = identity.get("unknown")
    if unknown:
        return KeyCheck(True, "works", "", identity_unknown=unknown)
    return KeyCheck(
        True,
        "works",
        "",
        identity_unknown=(
            "the service doesn't say whose account the key belongs to"
            if where == "hosted"
            else "it doesn't say whose account this is"
        ),
    )
