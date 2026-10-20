"""Choosing an AI account and model for a task, calling it with fallbacks, and recording every call as a Run."""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from engine.ai.adapters import Adapter, make_adapter
from engine.ai.borrow import Borrowed, borrowed_path, chain
from engine.ai.catalog import Catalogs
from engine.ai.checked import folder_of
from engine.ai.pauses import Pauses, pauses_path, waiting_text
from engine.ai.task import AiError, AiResult, AiTask, ModelInfo
from engine.config import Config
from engine.secrets import SecretError, resolve_secret
from engine.storage import Store, WriteContext

FALLBACK_ON = {"rate_limited", "quota", "auth", "no_key", "provider_down", "timeout", "offline", "no_work"}
LEVELS = ("open", "internal", "restricted")
_SYSTEM = WriteContext(actor="engine", trust="trusted", op="run.record")


@dataclass(frozen=True)
class Independence:
    """What a check must be independent of: the accounts that wrote the work, and whether the person accepts one of
    them (as a fresh run) when no other account can take it."""

    avoid: frozenset[str]
    same_account: bool = False


@dataclass(frozen=True)
class Choice:
    tier: str
    provider: str
    model_key: str
    model_id: str


class NoProvider(Exception):
    """No configured account can do this task. The message says why in plain words. When the only thing in the way is
    the material's data level, `level` is that level and `blocked` the accounts ("provider/model") that would take the
    work if allowed to see it, in the order the tier tries them."""

    def __init__(self, message: str, *, level: str | None = None, blocked: tuple[str, ...] = ()):
        super().__init__(message)
        self.level = level
        self.blocked = blocked


class IdentityHeld(NoProvider):
    """The only thing in the way is which sign-in a command-line agent runs as: `account` is the agent account, `why`
    is `changed` (it now runs as a different sign-in than the one recorded, and waits for the person's answer on Today)
    or `level` (its sign-in isn't set for the level of the material, `level`). The work waits for the person, as for a
    level no account may see; the message says why in plain words."""

    def __init__(self, message: str, *, account: str, why: str, level: str):
        super().__init__(message, level=level)
        self.account = account
        self.why = why


class AccountPaused(NoProvider):
    """Every account that could take the work is paused until a usage limit resets. `account` is the one that resets
    first and `until` when; `tier` is the tier whose work waits; the message is what the work waits on, in plain
    words."""

    def __init__(self, account: str, until: datetime, message: str, tier: str = ""):
        super().__init__(message)
        self.account = account
        self.until = until
        self.tier = tier


class NetworkOffline(AiError):
    """Every account that could take the work, and wasn't paused, could not be reached because no connection could be
    made at all. The work waits for the network; it is not a failure of any account."""

    def __init__(self, detail: str = ""):
        super().__init__("offline", detail)


class BudgetReached(Exception):
    """A spending limit stops new runs. The message says which and until when."""


def choices(
    cfg: Config,
    task_kind: str,
    data_level: str,
    *,
    tier: str | None = None,
    use: str | None = None,
    content: frozenset[str] = frozenset(),
    independent: Independence | None = None,
    unchecked: Collection[tuple[str, str]] = (),
    identity_held: Mapping[str, str] | None = None,
) -> list[Choice]:
    """The main choice for the task's tier, then its fallbacks, keeping only accounts allowed to see this data. `use`
    (a "provider/model" the person picked for this request) replaces the tier's list. For a check, accounts that wrote
    the work are left out, or put last when the person accepts the same account; the person's own pick stands.
    `unchecked` holds the (tier, "provider/model") pairs of backup accounts that can't stand in yet: a backup named
    there is never chosen. `identity_held` maps the agent accounts whose sign-in changed, and waits for the person's
    answer, to the sign-in found now: such an account takes open material only meanwhile. An account whose
    `identity_level` leaves out the material's level is never chosen for it either; when that is all that is in the
    way, the stop is `IdentityHeld`."""
    task = cfg.ai.tasks.get(task_kind)
    tier_name = tier or (task.tier if task else "routine")
    tier_cfg = cfg.ai.tiers.get(tier_name)
    if use is None and tier_cfg is None:
        raise NoProvider(f"the {tier_name!r} tier isn't set up. Add an AI account to it on the AI accounts screen")
    if use is None and not tier_cfg.use:
        raise NoProvider(f"no AI account is set up for the {tier_name!r} tier; add one on the AI accounts screen")
    picked: list[Choice] = []
    refused: list[str] = []
    blocked: list[str] = []
    waiting_on_identity: list[IdentityHeld] = []
    for place, ref in enumerate([use] if use is not None else [tier_cfg.use, *tier_cfg.fallback]):
        provider_name, _, model_key = ref.partition("/")
        provider = cfg.ai.providers.get(provider_name)
        if provider is None:
            refused.append(f"{provider_name} isn't one of your AI accounts")
            continue
        # Only a backup waits for its check: the tier's main account is never one, even when it is also listed as one.
        if use is None and place > 0 and (tier_name, ref) in unchecked:
            refused.append(f"{provider_name} is a backup that hasn't passed its connection check for this work")
            continue
        if LEVELS.index(data_level) > max(LEVELS.index(lvl) for lvl in provider.allowed_data):
            refused.append(f"{provider_name} isn't allowed to see {data_level} material")
            if takes(provider, content):
                blocked.append(ref)
            continue
        if takes(provider, content):
            stop = _identity_stop(provider, provider_name, data_level, identity_held or {})
            if stop is not None:
                refused.append(str(stop))
                waiting_on_identity.append(stop)
                continue
        if not takes(provider, content):
            refused.append(f"{provider_name} doesn't take {', '.join(sorted(content))} material")
            continue
        model_id = provider.models.get(model_key, model_key) if provider.adapter != "stub" else "stub"
        picked.append(Choice(tier_name, provider_name, model_key, model_id))
    if not picked:
        if waiting_on_identity:
            raise waiting_on_identity[0]
        raise NoProvider(
            "no AI account can take this: " + "; ".join(refused),
            level=data_level if blocked else None,
            blocked=tuple(blocked),
        )
    if independent is not None and use is None:
        others = [c for c in picked if c.provider not in independent.avoid]
        same = [c for c in picked if c.provider in independent.avoid]
        if not others and not independent.same_account:
            wrote = ", ".join(sorted({c.provider for c in same}))
            raise NoProvider(
                f"this check needs an account other than the one that wrote the work ({wrote}). Add another account "
                f"to the {tier_name!r} tier, or accept the same account for checks in Settings, AI roles"
            )
        picked = others + (same if independent.same_account else [])
    return picked


def _identity_stop(provider: Any, name: str, data_level: str, identity_held: Mapping[str, str]) -> IdentityHeld | None:
    """Why an agent account's sign-in keeps it from material at this level, or None when it doesn't: a changed sign-in
    waiting for the person takes open material only, and an `identity_level` takes only the levels it names."""
    top = LEVELS.index(data_level)
    label = provider.label or name
    if name in identity_held and top > 0:
        found = identity_held[name]
        return IdentityHeld(
            f"the {label} agent now runs as {found}. {data_level.capitalize()} material waits until you answer on "
            "Today: keep it or sign in again",
            account=name,
            why="changed",
            level=data_level,
        )
    shown = provider.identity_level
    if shown is not None and top > max((LEVELS.index(lvl) for lvl in shown), default=-1):
        return IdentityHeld(
            f"the {label} agent's sign-in isn't set for {data_level} material. It waits until you answer: sign in as "
            "another account, or change the levels it is set for",
            account=name,
            why="level",
            level=data_level,
        )
    return None


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


def takes(provider: Any, content: frozenset[str]) -> bool:
    """Whether an account takes material with these content levels: an account with no list takes every level."""
    return provider.content_levels is None or content <= set(provider.content_levels)


def accounts(cfg: Config, data_level: str, content: frozenset[str] = frozenset()) -> list[str]:
    """Every "provider/model" set up for any tier that may see material at this level and takes these content levels,
    in tier order, once each."""
    found: list[str] = []
    for tier in cfg.ai.tiers.values():
        for ref in [tier.use, *tier.fallback]:
            provider = cfg.ai.providers.get(ref.partition("/")[0]) if ref else None
            if provider is None or ref in found or not takes(provider, content):
                continue
            if LEVELS.index(data_level) <= max(LEVELS.index(lvl) for lvl in provider.allowed_data):
                found.append(ref)
    return found


#: The failures of a call that, when the computer slept during it, are a call cut off with no answer.
CUT_OFF_BY = ("timeout", "provider_down")


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
        self.pauses = Pauses(pauses_path(store), now)
        self.borrowed = Borrowed(borrowed_path(store), now)

    def _unchecked(self) -> frozenset[tuple[str, str]]:
        """The backup accounts that can't stand in yet, as (tier, "provider/model"): not checked for that tier's work
        and not accepted unchecked, or whose last check failed. Read from what the checks kept, at the moment of use."""
        from engine.ai.checked import cannot_stand_in, folder_of

        return frozenset((s.tier, s.ref) for s in cannot_stand_in(folder_of(self.store), self.cfg))

    def _identity_held(self, task_kind: str, tier: str | None, use: str | None) -> dict[str, str]:
        """The agent accounts whose sign-in changed and wait for the person's answer, each with the sign-in found now.
        Before a run, every agent account this work could use is read again when its configured time has passed, so a
        change found by a run is held at once. Read from what the checks kept, at the moment of use."""
        from engine.ai import identity

        where = folder_of(self.store)
        task = self.cfg.ai.tasks.get(task_kind)
        tier_cfg = self.cfg.ai.tiers.get(tier or (task.tier if task else "routine"))
        refs = [use] if use is not None else ([tier_cfg.use, *tier_cfg.fallback] if tier_cfg and tier_cfg.use else [])
        for name in dict.fromkeys(ref.partition("/")[0] for ref in refs):
            identity.watch(where, self.cfg, name, self.adapter_factory, self.env, self.now())
        return {n: who for n, who in identity.held(where).items() if n in self.cfg.ai.providers}

    def call(
        self,
        task: AiTask,
        *,
        request_id: str | None,
        data_level: str = "internal",
        tier: str | None = None,
        use: str | None = None,
        content: frozenset[str] = frozenset(),
        independent: Independence | None = None,
        offline_known: bool = False,
        spend_limit: float | None = None,
        unpriced_ok: bool = True,
    ) -> tuple[AiResult, Choice, str]:
        """Run the task on the first account that can serve it. Returns the result, the choice and the Run id. A
        refusal is returned like an answer (marked refused), never handed to the next account. `offline_known`: the
        request is already waiting for the network, so a call that again finds none is not recorded as another run.
        `spend_limit` and `unpriced_ok`: what the person allowed for this run; an account in line whose estimate is
        above the limit, or unknown when an unpriced run isn't allowed, is never called."""
        self._check_budget(task.kind)
        last: AiError | None = None
        picked = choices(
            self.cfg,
            task.kind,
            data_level,
            tier=tier,
            use=use,
            content=content,
            independent=independent,
            unchecked=self._unchecked(),
            identity_held=self._identity_held(task.kind, tier, use),
        )
        options = self._that_fit(task, list(picked))
        paused: dict[str, datetime] = {}
        offline = 0  # accounts that could not be reached at all
        over: list[Choice] = []  # accounts in line that would cost more than the person allowed
        for position, choice in enumerate(options):
            if spend_limit is not None:
                cost = self._price_of(task, choice)
                if (cost is None and not unpriced_ok) or (cost is not None and cost > spend_limit):
                    over.append(choice)
                    continue
            held = self.pauses.until(choice.provider)
            if held is not None:
                # A usage limit isn't over: this account isn't called, and the next in line takes the work.
                paused[choice.provider] = held
                continue
            settings = self.cfg.ai.providers[choice.provider]
            started = self.now()
            clock = time.monotonic()
            try:
                secret = resolve_secret(settings.auth, self.env)
                adapter = self.adapter_factory(settings.adapter, settings, secret)
                # Wait out a rate limit only on the last account in line; otherwise the next one is faster.
                last_in_line = position == len(options) - 1
                result = self._run_paced(adapter, task, choice, request_id, last_in_line, independent)
            except SecretError as err:
                last = AiError("no_key", str(err))
                self._record(task, request_id, choice, started, time.monotonic() - clock, None, last, independent)
                continue
            except AiError as err:
                if err.kind in CUT_OFF_BY and self._slept(started, clock):
                    # The computer slept during the call: it was cut off with no answer, so it did no work.
                    err = AiError("no_work", err.detail)
                last = err
                if err.kind == "offline":
                    offline += 1
                if not (err.kind == "offline" and offline_known):
                    self._record(task, request_id, choice, started, time.monotonic() - clock, None, err, independent)
                until = self._pause_until(err, position == len(options) - 1)
                if until is not None:
                    self.pauses.pause(choice.provider, until)
                    paused[choice.provider] = until
                if err.kind in FALLBACK_ON:
                    continue
                raise
            run_id = self._record(
                task, request_id, choice, started, time.monotonic() - clock, result, None, independent
            )
            if self.pauses.until(choice.provider) is not None:
                # An answer proves the limit has lifted, whatever reset time was written down earlier.
                self.pauses.clear(choice.provider)
            return result, choice, run_id
        if paused and len(paused) == len(options):
            account, until = min(paused.items(), key=lambda item: item[1])
            lent = self._lent(options[0].tier, independent) if use is None else None
            if lent is not None:
                # The person said yes to using another tier's account until the limit resets.
                try:
                    return self.call(
                        task,
                        request_id=request_id,
                        data_level=data_level,
                        tier=tier,
                        use=lent,
                        content=content,
                        offline_known=offline_known,
                        spend_limit=spend_limit,
                        unpriced_ok=unpriced_ok,
                    )
                except NoProvider:
                    pass
                except AiError as err:
                    if err.kind not in FALLBACK_ON:
                        raise
            raise AccountPaused(
                account, until, waiting_text(self.cfg, account, until, self.now()), tier=options[0].tier
            )
        if last is None and over:
            raise BudgetReached(
                "the accounts left to try would cost more than you allowed for this run, or their price isn't known"
            )
        assert last is not None
        if offline and offline + len(paused) + len(over) == len(options):
            raise NetworkOffline(last.detail)
        raise last

    def _slept(self, started: datetime, clock: float) -> bool:
        """Whether the computer was asleep during a call that began at `started` (wall clock) and `clock` (the awake
        clock): the time on the wall clock ran ahead of the time the computer was awake by more than the configured
        gap."""
        wall = (self.now() - started).total_seconds()
        return wall - (time.monotonic() - clock) > self.cfg.dispatch.sleep_gap_seconds

    def _lent(self, tier: str, independent: Independence | None = None) -> str | None:
        """The account of another tier the person said yes to for this tier's work, while that answer counts and the
        account is still free, still another tier's and fit for a check's independence; None otherwise."""
        ref = self.borrowed.lent(tier)
        if ref is None:
            return None
        provider = ref.partition("/")[0]
        own = {r.partition("/")[0] for r in chain(self.cfg, tier)}
        elsewhere = any(ref in chain(self.cfg, other) for other in self.cfg.ai.tiers if other != tier)
        if provider in own or not elsewhere or self.pauses.until(provider) is not None:
            return None
        if independent is not None and provider in independent.avoid and not independent.same_account:
            return None
        return ref

    def _first_choice(
        self, task: AiTask, options: list[Choice], data_level: str, independent: Independence | None
    ) -> Choice:
        """The account a request would use first: the first that fits, or the account lent for the tier while every
        one of its own accounts is paused."""
        fitting = self._that_fit(task, list(options))
        if all(self.pauses.until(c.provider) is not None for c in fitting):
            lent = self._lent(options[0].tier, independent)
            if lent is not None:
                try:
                    return choices(self.cfg, task.kind, data_level, tier=options[0].tier, use=lent)[0]
                except NoProvider:
                    pass
        return fitting[0]

    def _pause_until(self, err: AiError, last_in_line: bool) -> datetime | None:
        """When a failed call's account can be used again, if the failure is a usage limit with a reset to wait for:
        the reset the account gave, or for a request to slow down that kept coming after the waits in the call, the
        configured pause. A short wait the call itself made, or a limit with no reset time, is no pause."""
        limits = self.cfg.ai.rate_limits
        if err.kind == "quota":
            seconds = err.retry_after
        elif err.kind == "rate_limited":
            known = err.retry_after
            seconds = known if known is not None and known > limits.max_wait_seconds else None
            if seconds is None and last_in_line:
                seconds = limits.pause_seconds
        else:
            return None  # only a usage limit pauses an account; no connection, a timeout or an outage never does
        return self.now() + timedelta(seconds=seconds) if seconds else None

    def _run_paced(
        self,
        adapter: Adapter,
        task: AiTask,
        choice: Choice,
        request_id: str | None,
        wait: bool,
        independent: Independence | None = None,
    ) -> AiResult:
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
                self._record(task, request_id, choice, started, time.monotonic() - clock, None, err, independent)
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
        self,
        task: AiTask,
        *,
        tier: str | None = None,
        data_level: str = "internal",
        use: str | None = None,
        content: frozenset[str] = frozenset(),
        independent: Independence | None = None,
    ) -> float | None:
        """What a run would cost in USD on the account it would use, or None when the price isn't known.
        Input from the packet's size; output from past runs of this kind, or its configured typical size."""
        try:
            options = choices(
                self.cfg,
                task.kind,
                data_level,
                tier=tier,
                use=use,
                content=content,
                independent=independent,
                unchecked=self._unchecked(),
            )
            choice = self._first_choice(task, options, data_level, independent)
        except NoProvider:
            return None
        return self._price_of(task, choice)

    def _price_of(self, task: AiTask, choice: Choice) -> float | None:
        """What this task would cost in USD on this account, or None when its price isn't known."""
        info = self.model_info(choice)
        if info.input_per_million is None or info.output_per_million is None:
            return None
        output = task.expected_output or self.typical_output(task.kind)
        return (estimate_tokens(task.size) * info.input_per_million + output * info.output_per_million) / 1e6

    def estimate_for(
        self, kind: str, input_tokens: int, output_tokens: int | None = None, *, data_level: str = "internal"
    ) -> float | None:
        """What a run of `kind` with this many tokens read (and written: by default its typical answer) would cost in
        USD on the account it would use first, priced as the request's go will be; None when the price isn't known
        or no account takes the work."""
        try:
            options = list(choices(self.cfg, kind, data_level, unchecked=self._unchecked()))
        except NoProvider:
            return None
        if not options:
            return None
        info = self.model_info(options[0])
        if info.input_per_million is None or info.output_per_million is None:
            return None
        output = self.typical_output(kind) if output_tokens is None else output_tokens
        return (max(0, input_tokens) * info.input_per_million + max(0, output) * info.output_per_million) / 1e6

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
        if result is not None and result.cost_usd is not None:
            return result.cost_usd
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
        request_id: str | None,
        choice: Choice,
        started: datetime,
        seconds: float,
        result: AiResult | None,
        error: AiError | None,
        independent: Independence | None = None,
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
            "independence": (
                None
                if independent is None
                else ("same_account" if choice.provider in independent.avoid else "other_account")
            ),
            "error_kind": error.kind if error else ("refused" if result and result.refused else None),
            "error_detail": error.detail if error else (result.refusal if result and result.refused else None),
            "no_work": error is not None and error.kind == "no_work",
            "started_at": started.isoformat(),
            "knowledge": task.knowledge,
        }
        with self.store.transaction() as tx:
            return tx.create("run", data, _SYSTEM).id
