"""The near-duplicate action check: the similarity it fires at is a setting, and it compares with open and done
actions."""

import pytest

from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import WriteContext
from tests.conftest import DEMO_B, fixture_records
from tests.test_plugin_api_02 import env  # noqa: F401 - the fixture is reused

_PM = WriteContext("pm", "trusted", "test")
EXISTING = "Send quarterly budget report"
# Word overlap with EXISTING, counting words of four letters or more: 3 of 5 shared, and 4 of 5 shared.
SHARES_THREE_OF_FIVE = "Send quarterly budget summary"
SHARES_FOUR_OF_FIVE = "Send quarterly budget report today"


def near_duplicates(env, text):  # noqa: F811
    _, cfg, store = env
    op = {"op": "action.add", "text": text, "evidence": {"quote": text}}
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), ("action.add",), Inputs("REQ-1", None, "", "", "trusted"))
    return [p for p in check(cs, ctx) if p.check == "near-duplicate-action"]


def seed(env, status):  # noqa: F811
    _, _, store = env
    owner = fixture_records(DEMO_B, "person")[0]["id"]
    with store.transaction() as tx:
        tx.create("action", {"text": EXISTING, "owners": [{"person": owner}], "status": status}, _PM)


def set_similarity(env, value):  # noqa: F811
    env[1].checks.tuning.near_duplicate_action.similarity = value


def test_the_check_fires_at_and_above_the_configured_similarity_and_not_below(env):  # noqa: F811
    seed(env, "open")
    set_similarity(env, 0.8)
    assert near_duplicates(env, SHARES_FOUR_OF_FIVE)  # exactly at the setting
    assert not near_duplicates(env, SHARES_THREE_OF_FIVE)  # below it
    set_similarity(env, 0.6)
    assert near_duplicates(env, SHARES_FOUR_OF_FIVE)  # above it
    assert near_duplicates(env, SHARES_THREE_OF_FIVE)  # exactly at it


def test_the_check_compares_with_done_actions_too(env):  # noqa: F811
    seed(env, "done")
    problems = near_duplicates(env, EXISTING)
    assert len(problems) == 1 and "done action" in problems[0].message


def test_the_similarity_is_between_zero_and_one():
    from engine.config.schema import NearDuplicateActionTuning

    assert NearDuplicateActionTuning().similarity == 0.8
    for value in (-0.1, 1.1):
        with pytest.raises(ValueError):
            NearDuplicateActionTuning(similarity=value)


def test_a_near_duplicate_on_an_internal_item_still_returns(env):  # noqa: F811
    # Only wording lints drop to a warning on an item that stays internal; a lint about correctness keeps its severity.
    seed(env, "open")
    env[1].checks.lints["near-duplicate-action"] = "return"
    (problem,) = near_duplicates(env, EXISTING)
    assert problem.severity == "return"
