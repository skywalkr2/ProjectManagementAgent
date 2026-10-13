"""Smoke test for the AI setup (design 6.16): one small live call per configured tier and account, with the exact
parameters the work will use, so a setting a model refuses is found before real work fails.

The result is kept with a fingerprint of `ai.yaml`, so the server can say when the settings changed since the last test.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from engine.ai.adapters import make_adapter
from engine.ai.task import AiError, AiTask, provider_reason
from engine.config import Config
from engine.secrets import SecretError, describe_secret, resolve_secret
from engine.state_file import write_whole
from engine.storage import Store
from engine.workspace import Workspace

STATUS_FILE = "ai-test.json"
_REQUEST = 'Reply with exactly this JSON and nothing else: {"ok": true}'


@dataclass
class SmokeResult:
    tier: str
    account: str
    main: bool
    ok: bool
    detail: str
    seconds: float = 0.0
    key_source: str | None = None
    provider: str = ""  # the account's short name
    answered: bool = False  # the account's call went through, whatever it said
    offline: bool = False  # no connection could be made at all: the test says nothing about the account


def _params_for_tier(cfg: Config, tier: str) -> list[tuple[str, float, int]]:
    """(task kind, temperature, max_output) for every task kind that runs on this tier, directly or by escalation."""
    uses = [(k, t.temperature, t.max_output) for k, t in cfg.ai.tasks.items() if t.tier == tier]
    if not uses:
        uses = [
            (k, t.temperature, t.max_output)
            for k, t in cfg.ai.tasks.items()
            if cfg.ai.tiers.get(t.tier) and cfg.ai.tiers[t.tier].escalate_to == tier
        ]
    return uses or [("smoke", 0.0, 256)]


def smoke_test(
    cfg: Config,
    env: Mapping[str, str],
    adapter_factory: Callable[[str, Any, str | None], Any] = make_adapter,
) -> list[SmokeResult]:
    results: list[SmokeResult] = []
    locked: set[str] = set()
    for tier_name, tier in cfg.ai.tiers.items():
        if not tier.use:
            results.append(SmokeResult(tier_name, "", True, False, "no AI account is set up for this tier"))
            continue
        for position, ref in enumerate([tier.use, *tier.fallback]):
            provider_name, _, model_key = ref.partition("/")
            settings = cfg.ai.providers[provider_name]
            model_id = settings.models.get(model_key, model_key)
            for kind, temperature, max_output in _params_for_tier(cfg, tier_name):
                task = AiTask(kind, "This is a connection test.", "", _REQUEST, {}, temperature, max_output)
                start = time.monotonic()
                key_source = None
                answered = no_network = False
                try:
                    secret = resolve_secret(settings.auth, env)
                    reply = adapter_factory(settings.adapter, settings, secret).run(task, model_id)
                    detail = "answered" if _is_ok(reply.text) else "answered, but not with the requested JSON"
                    ok = answered = True
                except SecretError as err:
                    ok, detail, key_source = False, f"key not found: {err}", describe_secret(settings.auth)
                except AiError as err:
                    ok, detail = False, _problem(err)
                    no_network = err.kind == "offline"
                    if err.kind in ("auth", "no_key"):
                        key_source = describe_secret(settings.auth)
                except ValueError as err:
                    ok, detail = False, str(err)
                label = f"{ref} ({kind}, temperature {temperature}, max output {max_output})"
                results.append(
                    SmokeResult(
                        tier_name,
                        label,
                        position == 0,
                        ok,
                        detail,
                        time.monotonic() - start,
                        key_source,
                        provider_name,
                        answered,
                        no_network,
                    )
                )
            if ref not in locked:
                locked.add(ref)
                results.extend(_lockdown(tier_name, ref, position == 0, settings, model_id, env, adapter_factory))
    return results


#: What a failed test call means, in plain words, by the kind of failure.
PROBLEMS = {
    "auth": "It isn't signed in, or the key was refused",
    "no_key": "The key wasn't found",
    "quota": "The account is out of credit or at its plan's limit",
    "rate_limited": "The account asked to wait; try again shortly",
    "timeout": "It didn't answer in time",
    "provider_down": "It couldn't be reached",
    "offline": "There is no network connection to reach it",
    "invalid_output": "Its answer couldn't be read",
    "no_output": "It finished without giving an answer",
    "refused": "It refused the request",
}


def _problem(err: AiError) -> str:
    """A failed test call in plain words: what it means, the account's own words for it, and what to do."""
    reason = provider_reason(err.detail)
    plain = PROBLEMS.get(err.kind, "It stopped with an error")
    detail = f"{plain} ({reason})" if reason else plain
    return f"{detail}. {err.hint}" if err.hint else f"{detail}."


def _lockdown(
    tier: str,
    ref: str,
    main: bool,
    settings: Any,
    model_id: str,
    env: Mapping[str, str],
    adapter_factory: Callable[[str, Any, str | None], Any],
) -> list[SmokeResult]:
    """For an agent account, its lockdown test: one result per probe (design 6.16). Other accounts have none."""
    try:
        adapter = adapter_factory(settings.adapter, settings, resolve_secret(settings.auth, env))
    except (SecretError, AiError, ValueError):
        return []  # the connection test above already says why
    if not hasattr(adapter, "lockdown_test"):
        return []
    start = time.monotonic()
    checks = adapter.lockdown_test(model_id)
    seconds = time.monotonic() - start
    return [
        SmokeResult(tier, f"{ref} (lockdown: {c.name})", main, c.ok, c.detail, seconds, provider=ref.partition("/")[0])
        for c in checks
    ]


def _is_ok(text: str) -> bool:
    try:
        return json.loads(text.strip().strip("`").removeprefix("json").strip()) == {"ok": True}
    except ValueError:
        return False


def ai_fingerprint(ws: Workspace) -> str:
    path = ws.config_dir / "ai.yaml"
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def inconclusive(results: list[SmokeResult]) -> bool:
    """Whether the test found no network and nothing else wrong: every failure is a missing connection. Such a test
    says nothing about the accounts, so it is neither kept as a failure nor counted toward one."""
    failed = [r for r in results if not r.ok]
    return bool(failed) and all(r.offline for r in failed)


def record(ws: Workspace, results: list[SmokeResult]) -> None:
    """Keep a test's result. A test that only found no network is not kept: the last real result stands."""
    if inconclusive(results):
        return
    passed = all(r.ok for r in results if r.main)
    data = {
        "fingerprint": ai_fingerprint(ws),
        "passed": passed,
        "at": datetime.now(UTC).isoformat(),
        "results": [asdict(r) for r in results],
    }
    write_whole(ws.private_dir / STATUS_FILE, json.dumps(data, indent=2) + "\n")


def lift_pauses(ws: Workspace, results: list[SmokeResult]) -> None:
    """An account whose test call was answered is not out of its usage limit any more: its pause is lifted."""
    from engine.ai.pauses import Pauses

    pauses = Pauses(ws.private_dir / "ai-pauses.json")
    for account in {r.provider for r in results if r.answered and r.provider}:
        if pauses.until(account) is not None:
            pauses.clear(account)


def untested_since_change(ws: Workspace) -> bool:
    """True when ai.yaml changed since the last passing smoke test (or there never was one)."""
    data = last_test(ws)
    if data is None:
        return True
    return not data.get("passed") or data.get("fingerprint") != ai_fingerprint(ws)


def last_test(ws: Workspace) -> dict[str, Any] | None:
    """The last recorded smoke test, or None when there never was one or the file can't be read."""
    path = ws.private_dir / STATUS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


DETAIL_LIMIT = 200


def ai_state(ws: Workspace, cfg: Config, store: Store) -> tuple[str, str | None]:
    """Whether the assistant can do its work: "not_set_up" (no account for any tier), "failing" (the last connection
    test failed for the current settings, or the latest request ended with the account refusing its key),
    "stand_in" (every tier uses the built-in stand-in, which only files notes), "untested" (settings changed since the
    last passing test), or "ok". The detail is the provider's own reason."""
    if not any(tier.use for tier in cfg.ai.tiers.values()):
        return "not_set_up", None
    if stand_in(cfg):
        return "stand_in", None
    test = last_test(ws)
    current = test is not None and test.get("fingerprint") == ai_fingerprint(ws)
    if test is not None and current and not test.get("passed"):
        failed = [r for r in test.get("results", []) if not r.get("ok") and not r.get("offline")]
        pick = next((r for r in failed if r.get("main")), failed[0] if failed else None)
        if failed or not test.get("results"):
            return "failing", (str(pick.get("detail", ""))[:DETAIL_LIMIT] or None) if pick else None
    # A call that found no network says nothing about the account, so it never hides or makes a failure.
    runs = sorted(
        (run for run in store.read().list("run") if run.data.get("error_kind") != "offline"),
        key=lambda run: run.data.get("started_at", ""),
    )
    if runs and runs[-1].data.get("outcome") == "error" and runs[-1].data.get("error_kind") == "auth":
        latest = runs[-1].data
        passed_since = bool(test and test.get("passed") and current and str(test.get("at", "")) >= latest["started_at"])
        if not passed_since:
            return "failing", (provider_reason(latest.get("error_detail") or "")[:DETAIL_LIMIT] or None)
    if untested_since_change(ws):
        return "untested", None
    return "ok", None


def stand_in(cfg: Config) -> bool:
    """True when every account the tiers use is the built-in stand-in, which only files notes."""
    return all(cfg.ai.providers[ref.partition("/")[0]].adapter == "stub" for ref in _accounts_in_use(cfg))


def _accounts_in_use(cfg: Config) -> list[str]:
    """Every provider/model a tier uses or falls back to."""
    return [ref for tier in cfg.ai.tiers.values() for ref in ([tier.use] if tier.use else []) + list(tier.fallback)]


def account_test(
    cfg: Config,
    env: Mapping[str, str],
    name: str,
    adapter_factory: Callable[[str, Any, str | None], Any] = make_adapter,
) -> list[SmokeResult]:
    """Test one account on its first model, whether or not any kind of work uses it yet: one small call (and the
    lockdown check for a command-line agent), reported under the tier name "account"."""
    from dataclasses import replace

    from engine.config.schema import TierSettings

    provider = cfg.ai.providers.get(name)
    if provider is None or not provider.models:
        return [SmokeResult("account", name, True, False, "this account has no model to test")]
    first = next(iter(provider.models))
    ai = cfg.ai.model_copy(update={"tiers": {"account": TierSettings(use=f"{name}/{first}")}})
    return smoke_test(replace(cfg, files={**cfg.files, "ai": ai}), env, adapter_factory)
