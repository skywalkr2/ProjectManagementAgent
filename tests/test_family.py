"""Which model of a family is the newest (design 6.16): one rule, used by the preset that fills a new account's tiers
and by the weekly look at newer models. By the listing's own date, else the version in the id compared number by number,
else the list's order; a model of another family is never picked. Ids here are made up."""

from __future__ import annotations

import httpx

from engine.ai.adapters import ADAPTERS
from engine.ai.family import is_newer, newest_of_family, of_family, version_of
from engine.ai.presets import match_family, plan_tiers
from engine.ai.task import ModelInfo
from engine.config.schema import ProviderSettings, TierSettings

HOSTED = "https" + "://api.example.com/v1"


def dated(**when):
    return {i: ModelInfo(released=d) for i, d in when.items()}


def test_several_models_of_one_family_in_a_shuffled_order_pick_the_newest_by_version():
    ids = ["zed-medium-4-5", "zed-medium-10", "zed-medium-9", "zed-medium-5-5", "zed-small-99"]
    assert newest_of_family("medium", ids) == ("zed-medium-10", "version")
    assert newest_of_family("medium", list(reversed(ids))) == ("zed-medium-10", "version")
    assert newest_of_family("medium", ["zed-medium-4-5", "zed-medium-5-5"]) == ("zed-medium-5-5", "version")
    assert newest_of_family("medium", ["zed-medium-4-10", "zed-medium-4-9"]) == ("zed-medium-4-10", "version")


def test_a_model_of_another_family_is_never_picked_however_new_it_looks():
    ids = ["zed-small-99", "zed-medium-1", "zed-large-100"]
    assert newest_of_family("medium", ids)[0] == "zed-medium-1"
    assert newest_of_family("tiny", ids)[0] is None
    assert of_family("MEDIUM", ids) == ["zed-medium-1"]
    assert match_family("medium", ids) == "zed-medium-1"


def test_the_listings_own_date_decides_before_the_version_in_the_id():
    ids = ["zed-medium-9", "zed-medium-2"]
    info = dated(**{"zed-medium-9": "2025-01-01T00:00:00+00:00", "zed-medium-2": "2026-01-01T00:00:00+00:00"})
    assert newest_of_family("medium", ids, info) == ("zed-medium-2", "date")
    # A date for only some of them is not enough to compare by: the version decides.
    assert newest_of_family("medium", ids, dated(**{"zed-medium-2": "2026-01-01T00:00:00+00:00"}))[1] == "version"


def test_a_date_stamp_in_an_id_is_not_a_version_and_only_breaks_a_tie_between_equal_versions():
    assert version_of("zed-medium-4-5-20250101") == ((4, 5), (20250101,))
    ids = ["zed-medium-4-5-20250101", "zed-medium-4-5-20260101", "zed-medium-4-4-20270101"]
    assert newest_of_family("medium", ids) == ("zed-medium-4-5-20260101", "version")


def test_ids_with_no_version_keep_the_lists_order_and_say_so():
    assert newest_of_family("medium", ["medium-latest", "medium-preview"]) == ("medium-latest", "list")
    assert newest_of_family("medium", ["medium", "medium-2"]) == ("medium", "list")  # one has none: no comparison
    assert newest_of_family("medium", ["only-medium-1"]) == ("only-medium-1", "list")


def test_a_model_is_newer_than_the_current_one_only_when_the_rule_says_so():
    ids = ["zed-medium-1", "zed-medium-2", "zed-small-9"]
    assert is_newer("medium", "zed-medium-1", "zed-medium-2", ids, None)
    assert not is_newer("medium", "zed-medium-2", "zed-medium-1", ids, None)
    assert not is_newer("medium", "zed-medium-1", "zed-medium-1", ids, None)
    assert not is_newer("medium", "zed-medium-1", "zed-small-9", ids, None)
    assert not is_newer("medium", "zed-medium-1", "zed-medium-3", ids, None)  # not listed


def test_the_preset_takes_the_newest_of_each_family_in_whatever_order_the_list_comes():
    entry = {"tier_presets": {"routine": {"family": "small"}, "deep": {"family": "medium"}}}
    models = {f"m{n}": i for n, i in enumerate(["x-medium-2", "x-small-3", "x-medium-10", "x-small-12", "x-medium-9"])}
    tiers = {"routine": TierSettings(escalate_to="deep"), "deep": TierSettings()}
    plan = plan_tiers(entry, models, tiers, {"routine", "deep"}, lambda: {})
    assert models[plan.use["routine"]] == "x-small-12" and models[plan.use["deep"]] == "x-medium-10"


def test_the_preset_asks_the_service_for_dates_only_when_a_family_has_several_models():
    entry = {"tier_presets": {"routine": {"family": "small"}}}
    asked = []

    def listing():
        asked.append(1)
        return dated(**{"x-small-1": "2026-05-01T00:00:00+00:00", "x-small-2": "2025-05-01T00:00:00+00:00"})

    tiers = {"routine": TierSettings()}
    one = plan_tiers(entry, {"a": "x-small-1"}, tiers, {"routine"}, lambda: {}, listing)
    assert one.use == {"routine": "a"} and asked == []
    two = plan_tiers(entry, {"a": "x-small-1", "b": "x-small-2"}, tiers, {"routine"}, lambda: {}, listing)
    assert two.use == {"routine": "a"} and asked == [1]  # the service says the first is the newer


def test_the_adapters_listings_carry_the_release_date_the_service_gives():
    def serve(items):
        return httpx.MockTransport(lambda request: httpx.Response(200, json={"data": items, "has_more": False}))

    names = {name: cls for name, cls in ADAPTERS.items() if name not in ("stub", "cli-agent")}
    for name, cls in names.items():
        settings = ProviderSettings(adapter=name, base_url=HOSTED)
        both = [
            {"id": "a", "created_at": "2026-02-19T00:00:00Z", "created": 1_771_459_200},
            {"id": "b", "created_at": "not a date", "created": "nonsense"},
            {"id": "c"},
        ]
        models = cls(settings, "k", transport=serve(both)).list_models()
        assert models["a"].released and models["a"].released.startswith("2026-02-19")
        assert models["b"].released is None and models["c"].released is None
