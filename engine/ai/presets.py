"""The tiers a new AI account fills on its own (design 6.16, "A recommended setup per service").

A catalog entry may carry a preset for each tier: a model family to look for among the account's models, and an effort.
A family is a word matched against the model ids, never an exact id, so a newer model of the same family is picked up
with no change. An entry with no preset gets its tiers by price from the models that report one. Nothing here reads a
vendor's name: the words come from the catalog's data.

The functions are pure: they take the entry, the account's models and the tiers as they stand, and say what to set.
The Add account route writes it through the settings save, like every other change.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from engine.ai.family import newest_of_family
from engine.ai.task import ModelInfo

EFFORTS = ("low", "medium", "high")


@dataclass
class TierPlan:
    """What a new account should set: the model (by short name) and effort per tier, a tier to escalate to where one
    is new, the models to add to the account, and what could not be filled from the preset."""

    use: dict[str, str] = field(default_factory=dict)  # tier -> the account's short model name
    effort: dict[str, str] = field(default_factory=dict)  # tier -> low, medium or high
    escalate_to: dict[str, str] = field(default_factory=dict)  # tier -> the tier it retries on
    new_models: dict[str, str] = field(default_factory=dict)  # short name -> id, for models the account lacks
    unmatched: list[str] = field(default_factory=list)  # preset tiers no model matched
    by_price: list[str] = field(default_factory=list)  # tiers filled by price, not checked until the test passes


def clean_presets(raw: Any) -> dict[str, dict[str, str]]:
    """The catalog's `tier_presets` as {tier: {"family": word, "effort": low|medium|high or ""}}, in catalog order;
    an entry without a family, or with an effort that isn't one of the three, is left out or loses its effort."""
    found: dict[str, dict[str, str]] = {}
    for tier, preset in (raw if isinstance(raw, dict) else {}).items():
        family = str(preset.get("family") or "").strip() if isinstance(preset, dict) else ""
        if not family:
            continue
        effort = str(preset.get("effort") or "")
        found[str(tier)] = {"family": family, "effort": effort if effort in EFFORTS else ""}
    return found


def match_family(family: str, ids: list[str], info: Mapping[str, ModelInfo] | None = None) -> str | None:
    """The newest of the ids that contain the family word, ignoring case, by the one rule the weekly check of newer
    models uses too (`engine/ai/family.py`): the listing's own date, else the version in the id, else the list's order.
    A model of another family is never picked."""
    return newest_of_family(family, ids, info)[0]


def _price(info: ModelInfo | None) -> float | None:
    """What a model costs per million tokens in and out together, or None when the service prices it only in part."""
    if info is None or info.input_per_million is None or info.output_per_million is None:
        return None
    return info.input_per_million + info.output_per_million


def plan_tiers(
    entry: Mapping[str, Any],
    models: Mapping[str, str],
    tiers: Mapping[str, Any],
    stand_in: set[str],
    prices: Callable[[], Mapping[str, ModelInfo]],
    listed: Callable[[], Mapping[str, ModelInfo]] | None = None,
) -> TierPlan:
    """The tiers a new account of this kind fills when the person didn't say what it is for.

    `models` is the account's models by short name; `tiers` the tiers as they stand and `stand_in` the names of those
    still on the stand-in account (the only ones a new account takes over). With presets, each preset tier takes the
    newest model whose id holds its family word, by what the service states (`engine/ai/family.py`: the listing's
    release date, else the version in the id, else the order of `models`); `listed` is the service's listing, asked
    once and only when a family has more than one model. A command-line agent that lists no models is matched against
    the entry's examples. Without presets, the cheapest priced model goes to `routine` and the dearest to `deep` when
    those are on the stand-in; `prices` is only called then. A preset tier that is not in the settings is made when
    its family matches, and the tier before it escalates to it when that tier was filled here and names none.
    """
    plan = TierPlan()
    presets = clean_presets(entry.get("tier_presets"))
    if presets:
        ids = list(models.values())
        if entry.get("adapter") == "cli-agent" and entry.get("model_examples"):
            ids = [str(m) for m in entry["model_examples"]]
        info: Mapping[str, ModelInfo] | None = None

        def dates() -> Mapping[str, ModelInfo]:
            nonlocal info
            if info is None:
                info = listed() if listed is not None else {}
            return info

        previous = ""
        for tier, preset in presets.items():
            exists = tier in tiers
            if exists and tier not in stand_in:
                previous = ""  # on another account the person chose: it stays where they put it
                continue
            several = len([i for i in ids if preset["family"].casefold() in i.casefold()]) > 1
            hit = match_family(preset["family"], ids, dates() if several else None)
            if hit is None:
                plan.unmatched.append(tier)
                previous = ""
                continue
            short = next((k for k, v in models.items() if v == hit), None)
            if short is None:
                short = plan.new_models.setdefault(hit, hit)
            plan.use[tier] = short
            if preset["effort"]:
                plan.effort[tier] = preset["effort"]
            if not exists and previous in tiers and tiers[previous].escalate_to is None:
                plan.escalate_to[previous] = tier
            previous = tier
        return plan
    priced = [(price, short) for short, i in models.items() if (price := _price(prices().get(i))) is not None]
    if priced:
        cheapest = min(priced, key=lambda p: p[0])[1]
        dearest = max(priced, key=lambda p: p[0])[1]
        for tier, short in (("routine", cheapest), ("deep", dearest)):
            if tier in stand_in:
                plan.use[tier] = short
                plan.by_price.append(tier)
    return plan
