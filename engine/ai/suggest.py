"""What the measurements say about which model should do which kind of work (design 6.16, 7.9).

Plain rules over the capability matrix (`engine/ai/matrix.py`), returning data and codes; the screen words them. A
measurement that is stale, or that was never made, counts as unknown and is never read as a pass. Nothing here applies
anything: a suggestion is only ever offered to the person.

- `fit` says how one model measured for the skills one kind of work needs: how many skills were measured, how many are
  stale or below the minimum score, the runs and passes together, and what a passing run cost.
- `suggest_tier` names the cheapest tier whose model passed every skill the kind needs (all measured, none stale, none
  below the minimum), keeping the tier the work already uses when it ties; otherwise it says why there is none.
- `suggest_rule` offers a routing rule when the model a kind of work uses is measured below the minimum on a skill and
  another tier's model passes that skill.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from engine.ai.matrix import Standing

Status = Literal["ok", "below_min", "stale", "not_measured"]
#: Why no tier is suggested: no model in use, no case that proves a skill for this kind of work, or the best model's
#: measurements are missing (not_measured), out of date (stale) or under the minimum (none_passes).
NoSuggestion = Literal["no_accounts", "no_cases", "not_measured", "stale", "none_passes"]


@dataclass(frozen=True)
class Fit:
    """How one model measured for the skills a kind of work needs."""

    tier: str
    skills: int  # how many skills the kind needs
    measured: int  # of them, with at least one run
    stale: int  # of the measured, out of date
    below: int  # of the measured, under the minimum score
    runs: int  # all runs of those skills, stale ones included
    passes: int
    cost_per_pass_usd: float | None
    status: Status


def fit(tier: str, needed: Sequence[str], held: Sequence[Standing]) -> Fit:
    """The model's standing for the skills in `needed`. Not measured when any needed skill has no run (a partial
    measurement proves nothing about the rest), else stale when any is out of date, else below the minimum when any is,
    else ok. With no skill to go by the status is not measured."""
    by_id = {s.skill.id: s for s in held}
    mine = [by_id[i] for i in needed if i in by_id]
    done = [s for s in mine if s.measured]
    stale = [s for s in done if s.stale]
    below = [s for s in done if s.below_min]
    passes = sum(s.passes for s in done)
    spent = sum((s.cost_per_pass_usd or 0.0) * s.passes for s in done)
    if not mine or len(done) < len(mine):
        status: Status = "not_measured"
    elif stale:
        status = "stale"
    elif below:
        status = "below_min"
    else:
        status = "ok"
    return Fit(
        tier=tier,
        skills=len(mine),
        measured=len(done),
        stale=len(stale),
        below=len(below),
        runs=sum(s.runs for s in done),
        passes=passes,
        cost_per_pass_usd=spent / passes if passes else None,
        status=status,
    )


@dataclass(frozen=True)
class TierSuggestion:
    tier: str | None
    why_not: NoSuggestion | None


def suggest_tier(fits: Sequence[Fit], current: str) -> TierSuggestion:
    """The tier to suggest for a kind of work, from the fits of the tiers that have a model (in the order the tiers are
    set up). Among those that passed everything, the cheapest per passing run wins (an unknown cost after a known one);
    a tie goes to the tier already in use, then to the earlier tier. With none, the reason is the first that applies:
    no model, no skill to measure, a model not fully measured, a stale measurement, or none passing."""
    if not fits:
        return TierSuggestion(None, "no_accounts")
    if all(f.skills == 0 for f in fits):
        return TierSuggestion(None, "no_cases")
    passing = [(i, f) for i, f in enumerate(fits) if f.status == "ok"]
    if passing:

        def rank(item: tuple[int, Fit]) -> tuple[bool, float, bool, int]:
            i, f = item
            return (f.cost_per_pass_usd is None, f.cost_per_pass_usd or 0.0, f.tier != current, i)

        return TierSuggestion(min(passing, key=rank)[1].tier, None)
    if any(f.status == "not_measured" for f in fits):
        return TierSuggestion(None, "not_measured")
    if any(f.status == "stale" for f in fits):
        return TierSuggestion(None, "stale")
    return TierSuggestion(None, "none_passes")


@dataclass(frozen=True)
class RuleSuggestion:
    """A routing rule the measurements back: send `task` (with the request facts in `when`) to `tier`, because the model
    in use is under the minimum on `skills` and that tier's model passes them."""

    task: str
    tier: str
    skills: tuple[str, ...]
    when: Mapping[str, int]


def _passes(s: Standing | None) -> bool:
    return s is not None and s.measured and not s.stale and not s.below_min


def suggest_rule(
    task: str,
    current: str,
    needed: Sequence[str],
    held: Mapping[str, Sequence[Standing]],
    *,
    escalate_to: str | None = None,
    route_when: Mapping[str, Mapping[str, int]] | None = None,
    existing: Sequence[Any] = (),
) -> RuleSuggestion | None:
    """A rule for a kind of work whose tier's model measured under the minimum (not stale) on some needed skills, when
    another tier's model passes all of those. `held` is each tier's standings (in tier order). The tier the work already
    tries once more on (`escalate_to`) is preferred, else the cheapest per passing run on those skills. The rule names
    the kind of work, and the request facts the failing skills are at risk on (`route_when` by skill) when every failing
    skill has some; one failing skill with none makes it a rule for the whole kind. Nothing when the tier in use isn't
    known to fail, nobody else passes, or an existing rule (anything with `task`, `tier` and `when`) already says it."""
    if current not in held:
        return None
    mine = {s.skill.id: s for s in held[current]}
    failing = [i for i in needed if (s := mine.get(i)) is not None and s.measured and not s.stale and s.below_min]
    if not failing:
        return None
    options = []
    for index, (tier, standings) in enumerate(held.items()):
        if tier == current:
            continue
        by_id = {s.skill.id: s for s in standings}
        if all(_passes(by_id.get(i)) for i in failing):
            spent = sum((by_id[i].cost_per_pass_usd or 0.0) for i in failing)
            unknown = any(by_id[i].cost_per_pass_usd is None for i in failing)
            options.append((tier != escalate_to, unknown, spent, index, tier))
    if not options:
        return None
    tier = min(options)[4]
    facts = [dict((route_when or {}).get(i) or {}) for i in failing]
    when: dict[str, int] = {}
    if all(facts):
        for one in facts:
            for key, value in one.items():
                when[key] = min(value, when.get(key, value))
    wanted = {"task": task, **when}
    for rule in existing:
        shown = {k: v for k, v in rule.when.model_dump().items() if v is not None}
        if rule.tier == tier and shown == wanted:
            return None
    return RuleSuggestion(task=task, tier=tier, skills=tuple(failing), when=when)
