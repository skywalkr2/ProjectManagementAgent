"""Choosing an AI account and model for a task, calling it with fallbacks, and recording every call as a Run."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from engine.ai.adapters import Adapter, make_adapter
from engine.ai.catalog import Catalogs
from engine.ai.task import AiError, AiResult, AiTask, ModelInfo
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


def choices(
    cfg: Config, task_kind: str, data_level: str, *, tier: str | None = None, use: str | None = None
) -> list[Choice]:
    """The main choice for the task's tier, then its fallbacks, keeping only accounts allowed to see this data. `use`
    (a "provider/model" the person picked for this request) replaces the tier's list."""
    task = cfg.ai.tasks.get(task_kind)
    tier_name = tier or (task.tier if task else "routine")
    tier_cfg = cfg.ai.tiers.get(tier_name)
    if use is None and tier_cfg is None:
        raise NoProvider(f"the {tier_name!r} tier isn't set up in ai.yaml")
    if use is None and not tier_cfg.use:
        raise NoProvider(
            f"no AI account is set up for the {tier_name!r} tier; add one to ai.yaml and set tiers.{tier_name}.use"
        )
    picked: list[Choice] = []
    refused: list[str] = []
    for ref in [use] if use is not None else [tier_cfg.use, *tier_cfg.fallback]:
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


def estimate_tokens(chars: int) -> int:
    """A rough token count from characters: about four characters per token in English text, rounded up."""
    return -(-chars // 4)


def route(
    cfg: Config, task_kind: str, *, input_chars: int, quoted_messages: int, data_level: str, default: str | None = None
) -> str:
    """The tier for one request: the first routing rule that matches, otherwise the task's own tier.
    Decided from measurable facts about the request, before any call."""
    for rule in cfg.ai.routing:
        when = rule.when
        if when.task is not None and when.task != task_kind:
            continue
        if when.input_chars_over is not None and input_chars <= when.input_chars_over:
            continue
        if when.quoted_messages_over is not None and quoted_messages <= when.quoted_messages_over:
            continue
        if when.data_level is not None and when.data_level != data_level:
            continue
        return rule.tier
    if default is not None:
        return default
    task = cfg.ai.tasks.get(task_kind)
    return task.tier if task else "routine"


def accounts(cfg: Config, data_level: str) -> list[str]:
    """Every "provider/model" set up for any tier that may see material at this level, in tier order, once each."""
    found: list[str] = []
    for tier in cfg.ai.tiers.values():
        for ref in [tier.use, *tier.fallback]:
            provider = cfg.ai.providers.get(ref.partition("/")[0]) if ref else None
            if provider is None or ref in found:
                continue
            if LEVELS.index(data_level) <= max(LEVELS.index(lvl) for lvl in provider.allowed_data):
                found.append(ref)
    return found


def _outcome(result: AiResult | None, error: AiError | None) -> str:
    if (error is not None and error.kind == "refused") or (result is not None and result.refused):
        return "refused"
    return "ok" if error is None else "error"


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
        on_wait: Callable[[float], None] | None = None,
        catalogs: Catalogs | None = None,
    ):
        self.sleep = sleep
        self.on_wait = on_wait
        self.catalogs = catalogs or Catalogs(
            store.path.parent / ".cockpit" / "ai-catalog.json", cfg.ai.catalog_refresh_hours
        )
        self.cfg = cfg
        self.store = store
        self.env = env
        self.adapter_factory = adapter_factory
        self.now = now

    def call(
        self,
        task: AiTask,
        *,
        request_id: str,
        data_level: str = "internal",
        tier: str | None = None,
        use: str | None = None,
    ) -> tuple[AiResult, Choice, str]:
        """Run the task on the first account that can serve it. Returns the result, the choice and the Run id. A
        refusal is returned like an answer (marked refused), never handed to the next account."""
        self._check_budget(task.kind)
        last: AiError | None = None
        options = self._that_fit(task, list(choices(self.cfg, task.kind, data_level, tier=tier, use=use)))
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
                if self.on_wait is not None:
                    self.on_wait(pause)
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

    def estimate(
        self, task: AiTask, *, tier: str | None = None, data_level: str = "internal", use: str | None = None
    ) -> float | None:
        """What a run would cost in USD on the account it would use, or None when the price isn't known.
        Input from the packet's size; output from past runs of this kind, or its configured typical size."""
        try:
            choice = self._that_fit(task, list(choices(self.cfg, task.kind, data_level, tier=tier, use=use)))[0]
        except NoProvider:
            return None
        info = self.model_info(choice)
        if info.input_per_million is None or info.output_per_million is None:
            return None
        output = self.typical_output(task.kind)
        return (estimate_tokens(task.size) * info.input_per_million + output * info.output_per_million) / 1e6

    def typical_output(self, kind: str) -> int:
        """The average answer size of the last runs of this kind, or the kind's configured typical size."""
        sizes = [
            r.data["output_tokens"]
            for r in self.store.read().list("run")
            if r.data.get("task") == kind and r.data.get("outcome") == "ok" and r.data.get("output_tokens")
        ][-20:]
        if sizes:
            return round(sum(sizes) / len(sizes))
        from engine.tasks import settings

        return settings(self.cfg, self.store.plugins.tasks.get(kind), kind).expected_output

    def spent_on(self, kind: str) -> tuple[float, float]:
        """USD spent today and this month (UTC) on one kind of work."""
        now = self.now()
        day = month = 0.0
        for run in self.store.read().list("run"):
            if run.data.get("task") != kind:
                continue
            cost = run.data.get("cost_usd") or 0.0
            at = datetime.fromisoformat(run.data["started_at"])
            if (at.year, at.month) == (now.year, now.month):
                month += cost
                if at.date() == now.date():
                    day += cost
        return day, month

    def _check_budget(self, kind: str | None = None) -> None:
        budgets = self.cfg.ai.budgets
        limits = budgets.per_task.get(kind) if kind else None
        if limits is not None:
            day, month = self.spent_on(kind)
            if limits.per_month_usd is not None and month >= limits.per_month_usd:
                raise BudgetReached(
                    f"Paused: this month's budget for this kind of work (${limits.per_month_usd:.2f}) is used up."
                )
            if limits.per_day_usd is not None and day >= limits.per_day_usd:
                raise BudgetReached(
                    f"Paused until tomorrow: today's budget for this kind of work (${limits.per_day_usd:.2f}) "
                    "is used up."
                )
        day, month = self.spent()
        if month >= budgets.per_month_usd:
            raise BudgetReached(f"Paused: this month's AI budget (${budgets.per_month_usd:.2f}) is used up.")
        if day >= budgets.per_day_usd:
            raise BudgetReached(f"Paused until tomorrow: today's AI budget (${budgets.per_day_usd:.2f}) is used up.")

    def _that_fit(self, task: AiTask, options: list[Choice]) -> list[Choice]:
        """Drop accounts whose model can't hold this request plus its answer, by the catalog's context size.
        A model with no known context size is kept."""
        needed = estimate_tokens(task.size) + task.max_output
        fitting = []
        for choice in options:
            context = self.model_info(choice, need_limits=True).context_tokens
            if context is None or context >= needed:
                fitting.append(choice)
        if not fitting:
            raise NoProvider(
                f"this is too long for every account on this tier (about {needed:,} tokens with the answer)"
            )
        return fitting

    def model_info(self, choice: Choice, *, need_limits: bool = False) -> ModelInfo:
        """What is known about the chosen model: the provider's catalog, with prices in config taking precedence.
        With prices in config and no need for the model's limits, the catalog isn't fetched."""
        settings = self.cfg.ai.providers[choice.provider]

        def fetch() -> dict[str, ModelInfo]:
            adapter = self.adapter_factory(settings.adapter, settings, resolve_secret(settings.auth, self.env))
            return adapter.catalog() if hasattr(adapter, "catalog") else {}

        price = self.cfg.ai.prices.get(f"{choice.provider}/{choice.model_key}")
        if price is not None and not need_limits:
            info = ModelInfo()
        else:
            info = self.catalogs.model(choice.provider, choice.model_id, fetch) or ModelInfo()
        if price is not None:
            info.input_per_million = price.input_per_million
            info.output_per_million = price.output_per_million
            info.cached_input_per_million = price.cached_input_per_million
        return info

    def _cost(self, choice: Choice, result: AiResult | None) -> float | None:
        if result is None or result.input_tokens is None or result.output_tokens is None:
            return None
        info = self.model_info(choice)
        if info.input_per_million is None or info.output_per_million is None:
            return None
        cached = min(result.cached_input_tokens or 0, result.input_tokens)
        cached_price = info.cached_input_per_million
        cached_price = info.input_per_million if cached_price is None else cached_price
        fresh = result.input_tokens - cached
        total = fresh * info.input_per_million + cached * cached_price + result.output_tokens * info.output_per_million
        return total / 1e6

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
            "cached_input_tokens": result.cached_input_tokens if result else None,
            "cost_usd": self._cost(choice, result),
            "seconds": round(seconds, 3),
            "outcome": _outcome(result, error),
            "error_kind": error.kind if error else ("refused" if result and result.refused else None),
            "error_detail": error.detail if error else (result.refusal if result and result.refused else None),
            "started_at": started.isoformat(),
        }
        with self.store.transaction() as tx:
            return tx.create("run", data, _SYSTEM).id
