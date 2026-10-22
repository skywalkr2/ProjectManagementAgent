"""A newer model is asked about, or moved to after a check, never switched to unchecked (design 6.16).

Every few days (`ai.models.check_every_days`) each account's models and prices are listed. For each tier whose model
has a newer model of its own family (the family the catalog's preset for the account's service names; the newer one is
decided by `engine/ai/family.py`, the same rule the preset uses), and for each tier whose model's price rose, this keeps
an offer in the workspace's private folder; Today shows one line per account.

What happens to a newer model depends on its price against the tier's current model (the adapter's listing, with
`ai.prices` in the settings taking precedence, as the router resolves it):

- its price is known and the same or lower, and `ai.models.follow_newest` is on: the switch is checked first, on a copy
  of the settings, with the check estimated and held for the person's go above the configured amount; only a passed
  check writes the change, through the settings save, and Today says what moved with Keep and Switch back;
- anything else (the setting off, a higher price, a price not known, a check above the amount, a check that failed):
  Today says why and offers Switch (the settings' own switch, with its check) and Not now.

A model of another family is never offered, and nothing moves to one. Nothing here reads a vendor's name: the families
come from the catalog's data.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine.ai import native_move, switch_check
from engine.ai.adapters import make_adapter
from engine.ai.family import is_newer, newest_of_family, of_family
from engine.ai.task import ModelInfo
from engine.config import Config, load_config
from engine.secrets import SecretError, resolve_secret
from engine.state_file import changing, write_whole

STATE_FILE = "ai-model-watch.json"
ASKS, COSTS_MORE, PRICE_UNKNOWN, CHECK_FAILED, CHECK_COST = (
    "asks",
    "costs_more",
    "price_unknown",
    "check_failed",
    "check_cost",
)
#: Which reason a line gives when its tiers have more than one, the first that applies.
REASON_ORDER = (COSTS_MORE, PRICE_UNKNOWN, CHECK_FAILED, CHECK_COST, ASKS)

#: (input, output, cached input or None) dollars per million tokens.
Quote = tuple[float, float, float | None]


def path_of(store: Any) -> Path:
    return store.path.parent / ".cockpit" / STATE_FILE


def read(store: Any) -> dict[str, Any]:
    """The kept state: `checked_at` (when each account was last looked at), `prices` (the last price seen for each
    model by account/model id), `offers` (account -> tier -> offer) and `not_now` (account -> the signature put off)."""
    try:
        data = json.loads(path_of(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    return {
        "checked_at": data.get("checked_at") if isinstance(data.get("checked_at"), dict) else {},
        "prices": data.get("prices") if isinstance(data.get("prices"), dict) else {},
        "offers": data.get("offers") if isinstance(data.get("offers"), dict) else {},
        "not_now": data.get("not_now") if isinstance(data.get("not_now"), dict) else {},
    }


def _write(store: Any, data: dict[str, Any]) -> None:
    write_whole(path_of(store), json.dumps(data, sort_keys=True, indent=2) + "\n")


# ---- prices and use --------------------------------------------------------------------------------------------------


def quote_of(cfg: Config, account: str, model_id: str, listing: Mapping[str, ModelInfo]) -> Quote | None:
    """What a model costs per million tokens, resolved as the router does: the price in the settings (by the account's
    short name for the model, or its id) takes precedence over the service's listing. None when either side of the
    price is unknown."""
    provider = cfg.ai.providers[account]
    shorts = [k for k, v in provider.models.items() if v == model_id] + [model_id]
    price = next((cfg.ai.prices[f"{account}/{k}"] for k in shorts if f"{account}/{k}" in cfg.ai.prices), None)
    if price is not None:
        return price.input_per_million, price.output_per_million, price.cached_input_per_million
    info = listing.get(model_id)
    if info is None or info.input_per_million is None or info.output_per_million is None:
        return None
    return info.input_per_million, info.output_per_million, info.cached_input_per_million


@dataclass(frozen=True)
class Use:
    """What a tier's work on an account used per day over the window: fresh and cached input, and output tokens."""

    fresh: float = 0.0
    cached: float = 0.0
    output: float = 0.0


def use_of(store: Any, account: str, tier: str, now: datetime, days: int) -> Use:
    """The tier's use on the account per day over the last `days`, from the recorded runs."""
    start = now - timedelta(days=days)
    fresh = cached = output = 0.0
    for stored in store.read().since("run", "started_at", start.date().isoformat()):
        run = stored.data
        if run.get("provider") != account or run.get("tier") != tier or run.get("no_work"):
            continue
        if datetime.fromisoformat(run["started_at"]).astimezone(UTC) < start.astimezone(UTC):
            continue
        used = run.get("input_tokens") or 0
        hit = min(run.get("cached_input_tokens") or 0, used)
        fresh += used - hit
        cached += hit
        output += run.get("output_tokens") or 0
    return Use(fresh / days, cached / days, output / days)


def per_day(quote: Quote, use: Use) -> float:
    """What the use costs per day at a price."""
    cached_price = quote[0] if quote[2] is None else quote[2]
    return (use.fresh * quote[0] + use.cached * cached_price + use.output * quote[1]) / 1e6


def change_per_day(now: Quote | None, then: Quote | None, use: Use) -> float | None:
    """What the same use would cost per day more (below zero: less) at `then` than at `now`; None when either price
    isn't known."""
    if now is None or then is None:
        return None
    return round(per_day(then, use) - per_day(now, use), 4)


def price_relation(current: Quote | None, candidate: Quote | None) -> str:
    """`unknown` when either price isn't known, `lower_or_same` when the candidate costs no more per million tokens in
    and out, else `higher`."""
    if current is None or candidate is None:
        return "unknown"
    return "lower_or_same" if candidate[0] <= current[0] and candidate[1] <= current[1] else "higher"


# ---- the catalog's family --------------------------------------------------------------------------------------------


def entry_of(provider: Any, endpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The catalog entry of an account's service: the kind it was made from, else the one whose address it uses."""
    by_kind = next((e for e in endpoints if provider.kind and e["id"] == provider.kind), None)
    if by_kind is not None:
        return by_kind
    host = native_move.host_of(provider.base_url)
    return next((e for e in endpoints if host and native_move.host_of(e["base_url"]) == host), None) if host else None


def family_of(model_id: str, entry: Mapping[str, Any] | None) -> str | None:
    """The family word of the catalog's presets that the model's id holds, the first in the catalog's order."""
    from engine.ai.presets import clean_presets

    for preset in clean_presets((entry or {}).get("tier_presets")).values():
        if of_family(preset["family"], [model_id]):
            return preset["family"]
    return None


# ---- looking ---------------------------------------------------------------------------------------------------------


def signature(offers: Mapping[str, Mapping[str, Any]]) -> str:
    """What identifies a line's offers, so Not now holds until a different newer model or a different price rise
    appears."""
    parts = sorted(
        f"{t}:{o.get('candidate') or ''}:{json.dumps(o.get('price_rise'), sort_keys=True)}" for t, o in offers.items()
    )
    return "|".join(parts)


def look(
    cfg: Config,
    account: str,
    listing: Mapping[str, ModelInfo],
    endpoints: list[dict[str, Any]],
    uses: Mapping[str, Use],
    before: Mapping[str, Any],
    prices_seen: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[float | None]]]:
    """The offers for one account's tiers, and the prices to keep, from its listing: for each tier on the account whose
    model's id holds a family word of the catalog's presets, a newer model of that family (by `engine/ai/family.py`:
    the listing's date, else the version in the id; the order of the list alone never says one is newer) and a price
    rise of the tier's current model since the last look. `before` is the account's earlier offers, whose check
    results and price rises are kept while they still apply."""
    provider = cfg.ai.providers[account]
    entry = entry_of(provider, endpoints)
    ids = list(listing)
    found: dict[str, dict[str, Any]] = {}
    seen: dict[str, list[float | None]] = {}
    for tier_name, tier in cfg.ai.tiers.items():
        name, _, key = tier.use.partition("/")
        if name != account:
            continue
        current = provider.models.get(key, key)
        now_quote = quote_of(cfg, account, current, listing)
        use = uses.get(tier_name, Use())
        offer: dict[str, Any] = {"current": current, "candidate": None}
        known = prices_seen.get(f"{account}/{current}")
        if now_quote is not None:
            seen[f"{account}/{current}"] = [now_quote[0], now_quote[1], now_quote[2]]
        old = before.get(tier_name) or {}
        rise = old.get("price_rise") if old.get("current") == current else None
        if now_quote is not None and isinstance(known, list) and known[0] is not None and known[1] is not None:
            then: Quote = (known[0], known[1], known[2] if len(known) > 2 else None)
            if now_quote[0] > then[0] or now_quote[1] > then[1]:
                rise = {
                    "was": [then[0], then[1]],
                    "now": [now_quote[0], now_quote[1]],
                    "usd_per_day": change_per_day(then, now_quote, use),
                }
        if rise:
            offer["price_rise"] = rise
        family = family_of(current, entry)
        if family:
            pool = ids if current in ids else [*ids, current]
            newest, basis = newest_of_family(family, pool, listing)
            if newest and basis != "list" and newest != current and is_newer(family, current, newest, pool, listing):
                candidate = newest
                quote = quote_of(cfg, account, candidate, listing)
                offer.update(
                    candidate=candidate,
                    basis=basis,
                    price=price_relation(now_quote, quote),
                    usd_per_day=change_per_day(now_quote, quote, use),
                )
                if old.get("candidate") == candidate and old.get("check"):
                    offer["check"] = old["check"]
                if old.get("candidate") == candidate and old.get("check_usd") is not None:
                    offer["check_usd"] = old["check_usd"]
        if offer.get("candidate") or offer.get("price_rise"):
            found[tier_name] = offer
    return found, seen


def reason_of(offer: Mapping[str, Any]) -> str:
    """Why a newer model is only asked about: a higher price, a price not known, a check that failed, a check above the
    amount the person set, or simply that the setting asks."""
    check = offer.get("check") or {}
    if offer.get("price") == "higher":
        return COSTS_MORE
    if offer.get("price") == "unknown":
        return PRICE_UNKNOWN
    if check.get("state") in ("failed", "unfinished"):
        return CHECK_FAILED
    if check.get("state") == "waiting_go":
        return CHECK_COST
    return ASKS


NEWER, PRICE = "newer", "price"
#: How long after a look that couldn't list every account the next one is made.
RETRY_MINUTES = 60


def shown_offers(cfg: Config, store: Any) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """The offers that still apply (the tier is still on that model) and that the person hasn't put off, by account and
    kind of line: `newer` for tiers with a newer model, `price` for tiers whose model's price rose and have none."""
    data = read(store)
    visible: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for account, offers in sorted(data["offers"].items()):
        provider = cfg.ai.providers.get(account)
        if provider is None or not isinstance(offers, dict):
            continue
        live = {}
        for tier_name, offer in offers.items():
            tier = cfg.ai.tiers.get(tier_name)
            name, _, key = (tier.use if tier else "").partition("/")
            if name == account and provider.models.get(key, key) == offer.get("current"):
                live[tier_name] = offer
        kinds = {
            NEWER: {t: o for t, o in live.items() if o.get("candidate")},
            PRICE: {t: o for t, o in live.items() if o.get("price_rise") and not o.get("candidate")},
        }
        for state, group in kinds.items():
            if group and data["not_now"].get(f"{account}:{state}") != signature(group):
                visible[(account, state)] = group
    return visible


def not_now(store: Any, cfg: Config, account: str, state: str) -> bool:
    """Put off one of an account's lines: until a different newer model, or a different price rise, appears."""
    live = shown_offers(cfg, store).get((account, state))
    if live is None:
        return False
    with changing(path_of(store)):
        data = read(store)
        data["not_now"][f"{account}:{state}"] = signature(live)
        _write(store, data)
    return True


# ---- the weekly look -------------------------------------------------------------------------------------------------


def due(store: Any, cfg: Config, now: datetime) -> bool:
    """Whether the accounts are to be looked at again: never looked at, or longer ago than `check_every_days`."""
    kept = read(store)["checked_at"]
    if kept.get("retry") and now < datetime.fromisoformat(kept["retry"]):
        return False
    stamp = kept.get("all")
    if not stamp:
        return True
    return now - datetime.fromisoformat(stamp) >= timedelta(days=cfg.ai.models.check_every_days)


def _accounts(cfg: Config) -> list[str]:
    """The accounts a tier's own model is on (not a stand-in, which lists nothing)."""
    names = []
    for tier in cfg.ai.tiers.values():
        name = tier.use.partition("/")[0]
        provider = cfg.ai.providers.get(name)
        if provider is not None and provider.adapter != "stub" and name not in names:
            names.append(name)
    return names


def listing_of(
    cfg: Config, account: str, env: Mapping[str, str], factory: Callable[[str, Any, str | None], Any]
) -> dict[str, ModelInfo]:
    """What an account's service lists for its models and prices; empty when it can't be read now (a missing key, no
    network, an adapter that lists nothing)."""
    settings = cfg.ai.providers[account]
    try:
        adapter = factory(settings.adapter, settings, resolve_secret(settings.auth, env))
        return dict(adapter.catalog()) if hasattr(adapter, "catalog") else {}
    except (SecretError, ValueError, OSError):
        return {}
    except Exception:  # an adapter's own error: nothing is known now, the look is made again next time
        return {}


def models_with(cfg: Config, account: str, model_id: str) -> tuple[dict[str, str], str]:
    """The account's models with this one added when it isn't there (named by its id), and the short name it has."""
    models = dict(cfg.ai.providers[account].models)
    short = next((k for k, v in models.items() if v == model_id), None)
    if short is None:
        short = model_id
        models[short] = model_id
    return models, short


def run(
    ws: Any,
    store: Any,
    cfg: Config,
    env: Mapping[str, str] | None = None,
    *,
    endpoints: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
    factory: Callable[[str, Any, str | None], Any] = make_adapter,
    estimator: Callable[..., tuple[float | None, int]] | None = None,
    evaluator: Callable[..., Any] | None = None,
) -> list[str]:
    """Look at every account once: list its models and prices, keep what each tier's offers are, and, where
    `follow_newest` is on and a newer model of the family costs the same or less, check it and move the tier. Returns
    the tiers moved."""
    from engine.setup import known_endpoints

    env = os.environ if env is None else env
    now = now or datetime.now(UTC)
    found_endpoints = known_endpoints() if endpoints is None else endpoints
    moved: list[str] = []
    looked: list[str] = []
    for account in _accounts(cfg):
        listing = listing_of(cfg, account, env, factory)
        if not listing:
            continue
        looked.append(account)
        uses = {
            t: use_of(store, account, t, now, cfg.ai.models.use_days)
            for t, tier in cfg.ai.tiers.items()
            if tier.use.partition("/")[0] == account
        }
        with changing(path_of(store)):
            data = read(store)
            offers, seen = look(
                cfg, account, listing, found_endpoints, uses, data["offers"].get(account) or {}, data["prices"]
            )
            data["prices"].update(seen)
            data["offers"][account] = offers
            _write(store, data)
        for tier_name, offer in offers.items():
            wanted = bool(offer.get("candidate")) and cfg.ai.models.follow_newest
            if wanted and try_move(
                ws, store, cfg, env, account, tier_name, offer, now=now, estimator=estimator, evaluator=evaluator
            ):
                moved.append(tier_name)
    with changing(path_of(store)):
        data = read(store)
        if len(looked) == len(_accounts(cfg)):
            data["checked_at"]["all"] = now.isoformat()
            data["checked_at"].pop("retry", None)
        else:  # an account couldn't be listed (no network, a key not found): try again soon, not in a week
            data["checked_at"]["retry"] = (now + timedelta(minutes=RETRY_MINUTES)).isoformat()
        _write(store, data)
    return moved


def _model_of(cfg: Config, tier: str) -> tuple[str, str]:
    """The account and the model id a tier's own choice names now."""
    name, _, key = cfg.ai.tiers[tier].use.partition("/")
    provider = cfg.ai.providers.get(name)
    return name, provider.models.get(key, key) if provider is not None else key


def _keep_check(store: Any, account: str, tier: str, candidate: str, **fields: Any) -> None:
    with changing(path_of(store)):
        data = read(store)
        offer = (data["offers"].get(account) or {}).get(tier)
        if offer is not None and offer.get("candidate") == candidate:
            offer.update(fields)
            _write(store, data)


def try_move(
    ws: Any,
    store: Any,
    cfg: Config,
    env: Mapping[str, str],
    account: str,
    tier: str,
    offer: Mapping[str, Any],
    *,
    now: datetime,
    estimator: Callable[..., tuple[float | None, int]] | None = None,
    evaluator: Callable[..., Any] | None = None,
) -> bool:
    """Check a newer model of the tier's family and, only if the check passes, move the tier to it. It moves only when
    the model's price is known and the same or lower, the check's estimate is known and within the amount the person
    set (above it, the person is asked), and the check wasn't already tried on this model and failed. The change is the
    settings save's: the account's model list and the tier's choice, with the switch kept for Keep and Switch back."""
    from engine import settings as config_screens
    from engine.config.yaml_edit import set_key

    candidate = offer["candidate"]
    check = offer.get("check") or {}
    if offer.get("price") != "lower_or_same" or check.get("state") in ("failed", "unfinished"):
        return False
    models, short = models_with(cfg, account, candidate)
    ref = f"{account}/{short}"
    price_estimate = estimator or switch_check.estimate
    text = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
    text = set_key(text, ["providers", account, "models"], models)
    with tempfile.TemporaryDirectory() as tmp:
        aside = Path(tmp) / "ai.yaml"
        aside.write_text(text, encoding="utf-8")
        try:
            after = load_config(ws.config_dir, env=dict(env), flags={f"ai.providers.{account}.models": models})
            usd, cases = price_estimate(after, ws, ref, env, ai_config=aside)
        except Exception:
            usd, cases = None, 0
        _keep_check(store, account, tier, candidate, check_usd=usd, check_cases=cases)
        if usd is None or usd > cfg.ai.budgets.confirm_above_usd:
            _keep_check(store, account, tier, candidate, check={"state": "waiting_go", "usd": usd})
            return False
        try:
            run_check = evaluator or switch_check.evaluate_on
            report = run_check(ref, after, ws, env, ai_config=aside)
            verdict = switch_check.judge(ws, after, report)
        except Exception:  # a check that can't run is one that didn't finish, never a pass
            verdict = {"state": switch_check.FAILED, "failed": [], "unfinished": True}
    if verdict["state"] != switch_check.PASSED:
        _keep_check(
            store,
            account,
            tier,
            candidate,
            check={
                "state": "unfinished" if verdict["unfinished"] else "failed",
                "failed": verdict["failed"],
                "count": len(verdict["failed"]),
            },
        )
        return False
    before = load_config(ws.config_dir, env=dict(env))
    if _model_of(before, tier) != (account, offer["current"]):
        return False  # the person changed the tier meanwhile: nothing moves under them
    changes = {f"ai.providers.{account}.models": models, f"ai.tiers.{tier}.use": ref}
    done = config_screens.save(
        ws,
        cfg,
        store,
        changes=changes,
        reset=[],
        read_fingerprint=config_screens.fingerprint(ws.config_dir),
        env=dict(env),
        allow=("ai.providers.", "ai.tiers."),
    )
    after_saved = load_config(ws.config_dir, env=dict(env))
    found = switch_check.switches(before, after_saved)
    switch_check.begin(store, found, done.changes, check=False)
    for switch in found:
        switch_check.keep_moved(store, switch, done.changes, offer.get("usd_per_day"))
    with changing(path_of(store)):
        data = read(store)
        (data["offers"].get(account) or {}).pop(tier, None)
        _write(store, data)
    return True
