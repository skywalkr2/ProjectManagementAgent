"""About what the connection check of an account costs, so the person sees it before an account is added or made a
backup (design 6.16): a few tiny calls for each kind of work, and the round-trip that tests learning.

The size is counted from the settings; the price comes from the prices in config or from the catalog kept by earlier
runs.
Nothing here calls a service, so an account whose price isn't known yet has no estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.ai.calibration import lookup, scaled
from engine.config import Config

# One call of the check reads about this many tokens and writes about this many.
CALL_INPUT_TOKENS = 60
CALL_OUTPUT_TOKENS = 20
# The learning round-trip and the lock-down probe make a few calls each.
EXTRA_CALLS = 4


@dataclass(frozen=True)
class Size:
    calls: int
    input_tokens: int
    output_tokens: int


def size(cfg: Config) -> Size:
    """How many calls one account's check makes, with the tokens they read and write."""
    from engine.ai.smoke import _params_for_tier

    calls = sum(len(_params_for_tier(cfg, tier)) for tier in cfg.ai.tiers) + EXTRA_CALLS
    return Size(calls, calls * CALL_INPUT_TOKENS, calls * CALL_OUTPUT_TOKENS)


def cost(cfg: Config, name: str, catalogs: Any, where: Any = None) -> float | None:
    """What checking the account would cost on its dearest model, or None when a price isn't known. `catalogs` is the
    kept catalog (read only here: nothing is fetched). With `where` (the workspace's private folder), each call's size
    is corrected by what the account's model was measured to count and the fixed overhead its program adds."""
    provider = cfg.ai.providers.get(name)
    if provider is None or not provider.models:
        return None
    found = size(cfg)
    dearest: float | None = None
    for short, model_id in provider.models.items():
        price = cfg.ai.prices.get(f"{name}/{short}")
        if price is not None:
            read, write = price.input_per_million, price.output_per_million
        else:
            info = catalogs.model(name, model_id, lambda: {})
            read, write = (info.input_per_million, info.output_per_million) if info else (None, None)
        if read is None or write is None:
            return None
        reads = found.input_tokens
        if where is not None:
            reads = found.calls * scaled(
                CALL_INPUT_TOKENS, lookup(where, name, model_id, cfg.ai.estimates.calibration_runs)
            )
        usd = (reads * read + found.output_tokens * write) / 1e6
        dearest = usd if dearest is None else max(dearest, usd)
    return dearest
