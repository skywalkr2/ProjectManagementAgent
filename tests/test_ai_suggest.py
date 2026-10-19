"""What the measurements suggest for each kind of work: the cheapest model that passed everything wins, and a stale,
missing or under-minimum measurement is never read as a pass."""

from datetime import date

from engine.ai.matrix import Standing
from engine.ai.suggest import fit, suggest_rule, suggest_tier
from engine.config.schema import RouteRule
from engine.skills import Skill


def skill(name):
    return Skill(name, name, "")


def held(name, *, runs=4, passes=4, cost=0.01, stale=None, min_score=0.8):
    """One model's standing for one skill: `runs` of 0 is a skill nobody measured."""
    if not runs:
        return Standing(skill(name), 0, 0, None, None, None, False)
    return Standing(
        skill(name), runs, passes, date(2026, 10, 1), cost if passes else None, stale, passes / runs < min_score
    )


def fits(**tiers):
    """Fits by tier, each given as the standings for the skills a and b."""
    return [fit(tier, ["a", "b"], standings) for tier, standings in tiers.items()]


def test_a_model_passed_when_every_skill_it_needs_was_measured_fresh_and_above_the_minimum():
    f = fit("routine", ["a", "b"], [held("a", runs=4, passes=4, cost=0.02), held("b", runs=2, passes=2, cost=0.05)])
    assert (f.status, f.skills, f.measured, f.runs, f.passes) == ("ok", 2, 2, 6, 6)
    assert f.cost_per_pass_usd == (0.02 * 4 + 0.05 * 2) / 6  # what the passing runs cost, together


def test_a_skill_nobody_measured_makes_the_model_not_measured_however_well_the_others_did():
    f = fit("routine", ["a", "b"], [held("a"), held("b", runs=0)])
    assert f.status == "not_measured" and f.measured == 1 and f.skills == 2
    assert fit("routine", [], [held("a")]).status == "not_measured"  # nothing to go by is not a pass


def test_a_stale_measurement_is_unknown_and_a_low_one_is_below_the_minimum():
    assert fit("t", ["a"], [held("a", stale="age")]).status == "stale"
    assert fit("t", ["a"], [held("a", runs=4, passes=2)]).status == "below_min"
    low = fit("t", ["a", "b"], [held("a", runs=4, passes=2), held("b")])
    assert (low.status, low.below, low.stale) == ("below_min", 1, 0)
    both = fit("t", ["a", "b"], [held("a", stale="program"), held("b", runs=4, passes=1)])
    assert both.status == "stale"  # unknown comes before a low score: it may be fine once measured again


def test_the_cheapest_model_that_passed_everything_is_suggested():
    got = suggest_tier(
        fits(
            routine=[held("a", cost=0.05), held("b", cost=0.05)],
            deep=[held("a", cost=0.01), held("b", cost=0.01)],
        ),
        current="routine",
    )
    assert (got.tier, got.why_not) == ("deep", None)


def test_a_cheaper_model_that_is_stale_or_below_the_minimum_or_not_measured_is_not_suggested():
    expensive = [held("a", cost=0.50), held("b", cost=0.50)]
    for cheap in (
        [held("a", cost=0.01, stale="age"), held("b", cost=0.01)],
        [held("a", cost=0.01, runs=4, passes=2), held("b", cost=0.01)],
        [held("a", cost=0.01), held("b", runs=0)],
    ):
        got = suggest_tier(fits(routine=expensive, deep=cheap), current="deep")
        assert got.tier == "routine" and got.why_not is None


def test_a_tie_keeps_the_tier_already_in_use_and_otherwise_the_earlier_tier():
    same = [held("a", cost=0.02), held("b", cost=0.02)]
    assert suggest_tier(fits(routine=same, deep=same), current="deep").tier == "deep"
    assert suggest_tier(fits(routine=same, deep=same), current="elsewhere").tier == "routine"


def test_a_free_model_beats_a_priced_one_and_a_cost_that_is_not_known_comes_after_a_known_one():
    free = [held("a", cost=0.0), held("b", cost=0.0)]
    priced = [held("a", cost=0.30), held("b", cost=0.30)]
    assert suggest_tier(fits(routine=priced, deep=free), current="routine").tier == "deep"
    # With a minimum of nothing, a model that never passed a run is ok but has no cost per passing run.
    unpriced = [held("a", runs=4, passes=0, min_score=0), held("b", runs=4, passes=0, min_score=0)]
    assert fits(routine=unpriced)[0].cost_per_pass_usd is None
    assert suggest_tier(fits(routine=unpriced, deep=priced), current="routine").tier == "deep"
    assert suggest_tier(fits(routine=unpriced), current="routine").tier == "routine"


def test_when_none_qualifies_the_reason_is_a_code_never_a_suggestion():
    nothing = [held("a", runs=0), held("b", runs=0)]
    stale = [held("a", stale="age"), held("b")]
    low = [held("a", runs=4, passes=1), held("b")]
    assert suggest_tier(fits(routine=nothing), "routine").why_not == "not_measured"
    assert suggest_tier(fits(routine=nothing, deep=stale), "routine").why_not == "not_measured"
    assert suggest_tier(fits(routine=stale, deep=low), "routine").why_not == "stale"
    assert suggest_tier(fits(routine=low, deep=low), "routine") == suggest_tier(fits(routine=low), "routine")
    assert suggest_tier(fits(routine=low, deep=low), "routine").why_not == "none_passes"
    assert suggest_tier(fits(routine=low), "routine").tier is None


def test_no_accounts_and_no_cases_have_their_own_reasons():
    assert suggest_tier([], "routine").why_not == "no_accounts"
    nothing_to_prove = [fit("routine", [], []), fit("deep", [], [])]
    assert suggest_tier(nothing_to_prove, "routine").why_not == "no_cases"


# ---- a rule for work the model in use is measured below the minimum on ---------------------------------------------


def ruled(**over):
    base = dict(
        task="notes",
        current="routine",
        needed=["a", "b"],
        held={
            "routine": [held("a", runs=4, passes=1), held("b")],
            "deep": [held("a", cost=0.20), held("b", cost=0.20)],
        },
    )
    return suggest_rule(**{**base, **over})


def test_a_failing_skill_that_another_tier_passes_suggests_sending_the_kind_there():
    got = ruled()
    assert (got.task, got.tier, got.skills, dict(got.when)) == ("notes", "deep", ("a",), {})


def test_the_request_facts_a_failing_skill_is_at_risk_on_narrow_the_rule_when_all_failing_skills_have_them():
    got = ruled(route_when={"a": {"quoted_messages_over": 3}})
    assert dict(got.when) == {"quoted_messages_over": 3}
    both = ruled(
        held={
            "routine": [held("a", runs=4, passes=1), held("b", runs=4, passes=1)],
            "deep": [held("a"), held("b")],
        },
        route_when={"a": {"quoted_messages_over": 3}},
    )
    assert dict(both.when) == {} and both.skills == ("a", "b")  # one has no fact to go by: the whole kind


def test_the_tier_the_work_already_tries_again_on_is_preferred_over_a_cheaper_one():
    standings = {
        "routine": [held("a", runs=4, passes=1), held("b")],
        "cheap": [held("a", cost=0.01), held("b")],
        "deep": [held("a", cost=0.30), held("b")],
    }
    assert ruled(held=standings).tier == "cheap"
    assert ruled(held=standings, escalate_to="deep").tier == "deep"


def test_no_rule_is_suggested_on_unknown_failure_or_unknown_success():
    unknown_here = {"routine": [held("a", stale="age", runs=4, passes=1)], "deep": [held("a")]}
    assert ruled(held=unknown_here) is None  # a stale low score is unknown, not a failure
    unmeasured_here = {"routine": [held("a", runs=0)], "deep": [held("a")]}
    assert ruled(held=unmeasured_here) is None
    others_unknown = {"routine": [held("a", runs=4, passes=1)], "deep": [held("a", stale="age")]}
    assert ruled(held=others_unknown) is None
    others_low = {"routine": [held("a", runs=4, passes=1)], "deep": [held("a", runs=4, passes=2)]}
    assert ruled(held=others_low) is None
    fine_here = {"routine": [held("a")], "deep": [held("a")]}
    assert ruled(held=fine_here) is None
    assert ruled(held={}) is None


def test_a_rule_that_already_exists_is_not_suggested_again():
    existing = [RouteRule.model_validate({"when": {"task": "notes"}, "tier": "deep"})]
    assert ruled(existing=existing) is None
    other = [RouteRule.model_validate({"when": {"task": "notes", "quoted_messages_over": 3}, "tier": "deep"})]
    assert ruled(existing=other) is not None  # a narrower rule isn't the same rule
