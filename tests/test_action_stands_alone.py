"""Actions worded to stand on their own (design 6.9, the playbook's rule for reading notes): the lint on the assistant's
wording that finds an action that leans on something the reader can't see ("send it", "follow up on that"), what counts
as one is a setting, and an action for someone else is held when it still fails after the one return.

Names come from the fixtures.
"""

from __future__ import annotations

import pytest

from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

PEOPLE = fixture_records(DEMO_B, "person")
OTHER = PEOPLE[1]["full_name"]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def problems(env, text, *, owners=("me",), quote=None):
    _, cfg, store = env
    op = {"op": "action.add", "text": text, "owners": list(owners), "evidence": {"quote": quote or "the notes said so"}}
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), ("action.add",), Inputs("REQ-1", None, "", "", "trusted"))
    return [p for p in check(cs, ctx) if p.check == "action-stands-alone"]


@pytest.mark.parametrize(
    "text",
    [
        "Send it to the printer",
        "Follow up on that",
        "Ask the editor about it",
        "Reply",
        "Do the above before Friday",
        "Send the files to them",
        "Call him",
    ],
)
def test_an_action_that_leans_on_something_unseen_is_flagged(env, text):
    found = problems(env, text)
    assert len(found) == 1 and found[0].op == 0


@pytest.mark.parametrize(
    "text",
    [
        "Send the final interior file to the printer",
        "Review the proof that the editor sent",
        "Call the printer",
        "Agree on the back-cover copy",
        "Approve the cover finish: matte or soft-touch",
    ],
)
def test_an_action_that_names_what_it_is_about_is_not(env, text):
    assert problems(env, text) == []


def test_words_quoted_from_the_input_are_still_the_actions_own_words(env):
    # Unlike a wording lint on the app's own words, this reads what the action says, whoever first wrote it.
    assert len(problems(env, "Tell the editor about it", quote="about it")) == 1
    assert problems(env, "Confirm the print run", quote="the print run") == []


def test_what_counts_is_a_setting_not_code(env):
    _, cfg, _ = env
    assert problems(env, "Send report") == []
    cfg.language.unanchored_words = [*cfg.language.unanchored_words, "report"]
    assert len(problems(env, "Send report")) == 1
    cfg.language.unanchored_words = []
    assert problems(env, "Send it") == []
    cfg.checks.tuning.action_stands_alone.min_words = 4
    assert len(problems(env, "Call the printer")) == 1


def test_it_is_a_lint_with_a_severity_in_the_checks_settings(env):
    _, cfg, _ = env
    assert cfg.checks.lints["action-stands-alone"] == "return"
    cfg.checks.lints["action-stands-alone"] = "off"
    assert problems(env, "Send it") == []


def test_on_the_persons_own_action_it_only_warns_and_on_someone_elses_it_returns(env):
    own = problems(env, "Send it to the printer")
    assert [p.severity for p in own] == ["warn"], "nobody else reads it, so no fix round is spent"
    theirs = problems(env, "Send it to the printer", owners=(OTHER,))
    assert [p.severity for p in theirs] == ["return"], "they are told it, so it is worded for them"


def test_a_still_failing_action_for_someone_else_is_held(env):
    from engine.applier import _held_after_return

    _, cfg, store = env
    op = CHANGESET.validate_python(
        {"ops": [{"op": "action.add", "text": "Send it", "owners": [OTHER], "evidence": {"quote": "Send it"}}]},
        context={"op_models": store.plugins.ops},
    ).ops[0]
    ctx = Context(store, cfg, People(store, cfg), ("action.add",), Inputs("REQ-1", None, "", "", "trusted"))
    found = problems(env, "Send it", owners=(OTHER,))
    assert _held_after_return(op, found, ctx)
    own = problems(env, "Send it")
    assert not _held_after_return(op.model_copy(update={"owners": ["me"]}), own, ctx)


def test_the_playbook_says_the_same_to_the_assistant():
    from importlib import resources

    text = resources.files("engine.playbook.guidance").joinpath("notes.md").read_text(encoding="utf-8")
    assert "stand on its own" in text and 'never "send it"' in text
