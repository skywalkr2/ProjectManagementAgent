"""Choosing an AI account and model for a task, calling it with fallbacks, and recording every call as a Run."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from engine.ai.adapters import Adapter, make_adapter
from engine.ai.task import AiError, AiResult, AiTask
from engine.config import Config
from engine.secrets import SecretError, resolve_secret
from engine.storage import Store, WriteContext

FALLBACK_ON = {"rate_limited", "quota", "auth", "no_key", "provider_down", "timeout"}
LEVELS = ("open", "internal", "restricted")
_SYSTEM = WriteContext(actor="engine", trust="trusted", op="run.record")


@dataclass(frozen=True)
class Choice:
    tier: str
    provider: str
    model_key: str
    model_id: str


class NoProvider(Exception):
    """No configured account can do this task. The message says why in plain words."""


class BudgetReached(Exception):
    """A spending limit stops new runs. The message says which and until when."""


def choices(cfg: Config, task_kind: str, data_level: str, *, tier: str | None = None) -> list[Choice]:
    """The main choice for the task's tier, then its fallbacks, keeping only accounts allowed to see this data."""
    task = cfg.ai.tasks.get(task_kind)
    tier_name = tier or (task.tier if task else "routine")
    tier_cfg = cfg.ai.tiers.get(tier_name)
    if tier_cfg is None:
        raise NoProvider(f"the {tier_name!r} tier isn't set up in ai.yaml")
    if not tier_cfg.use:
        raise NoProvider(
            f"no AI account is set up for the {tier_name!r} tier; add one to ai.yaml and set tiers.{tier_name}.use"
        )
    picked: list[Choice] = []
    refused: list[str] = []
    for ref in [tier_cfg.use, *tier_cfg.fallback]:
        provider_name, _, model_key = ref.partition("/")
        provider = cfg.ai.providers.get(provider_name)
        if provider is None:
            refused.append(f"{provider_name} isn't an account in ai.yaml")
            continue
        if LEVELS.index(data_level) > max(LEVELS.index(lvl) for lvl in provider.allowed_data):
            refused.append(f"{provider_name} isn't allowed to see {data_level} material")
            continue
        model_id = provider.models.get(model_key, model_key) if provider.adapter != "stub" else "stub"
        picked.append(Choice(tier_name, provider_name, model_key, model_id))
    if not picked:
        raise NoProvider("no AI account can take this: " + "; ".join(refused))
    return picked


def escalation_tier(cfg: Config, tier: str) -> str | None:
    tier_cfg = cfg.ai.tiers.get(tier)
    return tier_cfg.escalate_to if tier_cfg else None


class Router:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        *,
        env: Mapping[str, str] | None = None,
        adapter_factory: Callable[[str, Any, str | None], Adapter] = make_adapter,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.sleep = sleep
        self.cfg = cfg
        self.store = store
        self.env = env
        self.adapter_factory = adapter_factory
        self.now = now

    def call(
        self, task: AiTask, *, request_id: str, data_level: str = "internal", tier: str | None = None
    ) -> tuple[AiResult, Choice, str]:
        """Run the task on the first account that can serve it. Returns the result, the choice and the Run id."""
        self._check_budget()
        last: AiError | None = None
        options = list(choices(self.cfg, task.kind, data_level, tier=tier))
        for position, choice in enumerate(options):
            settings = self.cfg.ai.providers[choice.provider]
            started = self.now()
            clock = time.monotonic()
            try:
                secret = resolve_secret(settings.auth, self.env)
                adapter = self.adapter_factory(settings.adapter, settings, secret)
                # Wait out a rate limit only on the last account in line; otherwise the next one is faster.
                last_in_line = position == len(options) - 1
                result = self._run_paced(adapter, task, choice, request_id, last_in_line)
            except SecretError as err:
                last = AiError("no_key", str(err))
                self._record(task, request_id, choice, started, time.monotonic() - clock, None, last)
                continue
            except AiError as err:
                last = err
                self._record(task, request_id, choice, started, time.monotonic() - clock, None, err)
                if err.kind in FALLBACK_ON:
                    continue
                raise
            run_id = self._record(task, request_id, choice, started, time.monotonic() - clock, result, None)
            return result, choice, run_id
        assert last is not None
        raise last

    def _run_paced(self, adapter: Adapter, task: AiTask, choice: Choice, request_id: str, wait: bool) -> AiResult:
        """Run on one account, waiting and trying again while it says to slow down, within the configured limits."""
        limits = self.cfg.ai.rate_limits
        for attempt in range(limits.tries if wait else 1):
            started, clock = self.now(), time.monotonic()
            try:
                return adapter.run(task, choice.model_id)
            except AiError as err:
                pause = err.retry_after if err.retry_after is not None else 2.0 * 2**attempt
                if (
                    not wait
                    or err.kind != "rate_limited"
                    or attempt + 1 >= limits.tries
                    or pause > limits.max_wait_seconds
                ):
                    raise
                self._record(task, request_id, choice, started, time.monotonic() - clock, None, err)
                self.sleep(pause)
        raise AssertionError("unreachable")

    # ---- budgets and runs --------------------------------------------------------------------------------------------

    def spent(self) -> tuple[float, float]:
        """USD spent today and this month (UTC), from recorded runs."""
        now = self.now()
        day = month = 0.0
        for run in self.store.read().list("run"):
            cost = run.data.get("cost_usd") or 0.0
            at = datetime.fromisoformat(run.data["started_at"])
            if (at.year, at.month) == (now.year, now.month):
                month += cost
                if at.date() == now.date():
                    day += cost
        return day, month

    def _check_budget(self) -> None:
        budgets = self.cfg.ai.budgets
        day, month = self.spent()
        if month >= budgets.per_month_usd:
            raise BudgetReached(f"Paused: this month's AI budget (${budgets.per_month_usd:.2f}) is used up.")
        if day >= budgets.per_day_usd:
            raise BudgetReached(f"Paused until tomorrow: today's AI budget (${budgets.per_day_usd:.2f}) is used up.")

    def _cost(self, choice: Choice, result: AiResult | None) -> float | None:
        price = self.cfg.ai.prices.get(f"{choice.provider}/{choice.model_key}")
        if price is None or result is None or result.input_tokens is None or result.output_tokens is None:
            return None
        return (result.input_tokens * price.input_per_million + result.output_tokens * price.output_per_million) / 1e6

    def _record(
        self,
        task: AiTask,
        request_id: str,
        choice: Choice,
        started: datetime,
        seconds: float,
        result: AiResult | None,
        error: AiError | None,
    ) -> str:
        data: dict[str, Any] = {
            "request": request_id,
            "task": task.kind,
            "provider": choice.provider,
            "model": result.model_served if result else choice.model_id,
            "tier": choice.tier,
            "input_chars": task.size,
            "output_chars": len(result.text) if result else 0,
            "input_tokens": result.input_tokens if result else None,
            "output_tokens": result.output_tokens if result else None,
            "cost_usd": self._cost(choice, result),
            "seconds": round(seconds, 3),
            "outcome": "ok" if error is None else "error",
            "error_kind": error.kind if error else None,
            "error_detail": error.detail if error else None,
            "started_at": started.isoformat(),
        }
        with self.store.transaction() as tx:
            return tx.create("run", data, _SYSTEM).id
