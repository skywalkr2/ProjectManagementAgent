"""Which accounts have passed the connection check (design 6.16), and who may stand in a fallback chain.

A fallback is a switch nobody chose at that moment, so only an account that passed the check with a tier's exact
parameters, or that the person accepted unchecked, may be added to that tier's chain. A result is kept for each
"account/model" with a fingerprint of the account's settings, so changing the account (its address, key reference,
models, agent) means it is checked again. Accepting an account unchecked is not part of the fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from engine.ai.smoke import SmokeResult, _params_for_tier
from engine.config import Config
from engine.state_file import write_whole
from engine.workspace import Workspace

CHECKED_FILE = "ai-checked.json"
NOT_ACCOUNT = ("accepted_unchecked",)


def account_fingerprint(cfg: Config, ref: str) -> str | None:
    """A hash of the account's settings and the model id the reference names, or None when the account isn't set up."""
    name, _, model_key = ref.partition("/")
    provider = cfg.ai.providers.get(name)
    if provider is None:
        return None
    data = provider.model_dump(mode="json", exclude=set(NOT_ACCOUNT))
    data["model"] = provider.models.get(model_key, model_key)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _read(ws: Workspace) -> dict[str, Any]:
    try:
        data = json.loads((ws.private_dir / CHECKED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remember(ws: Workspace, cfg: Config, results: list[SmokeResult]) -> None:
    """Keep what a test showed for each account it covered: the parameters whose call answered, and whether every part
    of its check (the lockdown probes and the learning round-trip) passed. A result that only found no network says
    nothing and changes nothing."""
    by_ref: dict[str, list[SmokeResult]] = {}
    for r in results:
        if r.ref:
            by_ref.setdefault(r.ref, []).append(r)
    kept = _read(ws)
    for ref, found in by_ref.items():
        fingerprint = account_fingerprint(cfg, ref)
        if fingerprint is None or any(r.offline for r in found):
            continue
        calls = [r for r in found if r.part == "call"]
        before = kept.get(ref) or {}
        earlier = before.get("params", []) if before.get("fingerprint") == fingerprint else []
        failed = [tuple(r.params) for r in calls if not r.ok and r.params]
        passed = [tuple(r.params) for r in calls if r.ok and r.params]
        params = [tuple(p) for p in [*earlier, *passed]]
        failed_before = before.get("failed", []) if before.get("fingerprint") == fingerprint else []
        still_failed = [tuple(p) for p in failed_before if tuple(p) not in passed]
        kept[ref] = {
            "fingerprint": fingerprint,
            "params": [list(p) for p in dict.fromkeys(params) if p not in failed],
            "failed": [list(p) for p in dict.fromkeys([*still_failed, *failed])],
            "complete": all(r.ok for r in found if r.part != "call"),
            "at": datetime.now(UTC).isoformat(),
        }
    write_whole(ws.private_dir / CHECKED_FILE, json.dumps(kept, indent=2) + "\n")


def is_checked(ws: Workspace, cfg: Config, ref: str, tier: str) -> bool:
    """Whether the account passed the check for this tier's kinds of work, with their exact parameters, as it is set up
    now: every one answered, and its lockdown probes and learning round-trip passed."""
    found = _read(ws).get(ref)
    if not isinstance(found, dict) or found.get("fingerprint") != account_fingerprint(cfg, ref):
        return False
    passed = {tuple(p) for p in found.get("params", [])}
    return bool(found.get("complete")) and {tuple(p) for p in _params_for_tier(cfg, tier)} <= passed


def check_failed(ws: Workspace, cfg: Config, ref: str, tier: str) -> bool:
    """Whether the account's last check, as it is set up now, failed for this tier's kinds of work: one of their calls
    didn't answer, or a lockdown probe or the learning round-trip failed. An account never checked has not failed."""
    found = _read(ws).get(ref)
    if not isinstance(found, dict) or found.get("fingerprint") != account_fingerprint(cfg, ref):
        return False
    wanted = {tuple(p) for p in _params_for_tier(cfg, tier)}
    return not found.get("complete", True) or bool(wanted & {tuple(p) for p in found.get("failed", [])})


@dataclass(frozen=True)
class Standing:
    """An account in a tier's fallback chain that can't stand in yet: `ref` is "account/model", `failed` is true when
    its last check failed (rather than it never having been checked for this tier)."""

    tier: str
    ref: str
    account: str
    model: str
    failed: bool


def cannot_stand_in(ws: Workspace, cfg: Config) -> list[Standing]:
    """Every account now in a fallback chain that is neither checked for that tier nor accepted unchecked, or whose
    last check failed. Reads the chains as they are, so a hand-edited file is covered too."""
    found = []
    for tier, settings in cfg.ai.tiers.items():
        for ref in settings.fallback:
            name, _, model = ref.partition("/")
            provider = cfg.ai.providers.get(name)
            if provider is None:
                continue
            failed = check_failed(ws, cfg, ref, tier)
            if failed or not (provider.accepted_unchecked or is_checked(ws, cfg, ref, tier)):
                found.append(Standing(tier, ref, name, model, failed))
    return found


def chain_problems(ws: Workspace, before: Config, after: Config) -> list[str]:
    """Why each account newly added to a fallback chain can't stand there, in plain words: it hasn't passed the check
    for that tier's kinds of work, and the person hasn't accepted it unchecked. Accounts already in a chain stay."""
    found = []
    for tier, settings in after.ai.tiers.items():
        old = before.ai.tiers.get(tier)
        for ref in settings.fallback:
            if old is not None and ref in old.fallback:
                continue
            name = ref.partition("/")[0]
            provider = after.ai.providers.get(name)
            if provider is None or provider.accepted_unchecked or is_checked(ws, after, ref, tier):
                continue
            found.append(
                f"{name} can't be a backup account for this work yet: it hasn't passed the connection check with the "
                "settings this work uses. Test it first, or accept it without a check in its settings."
            )
    return found
