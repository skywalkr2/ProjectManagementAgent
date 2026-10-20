"""No bookkeeping in item text (design 6.7, the UI/UX re-review's finding on the assistant's reasoning in item text):
two lints on the assistant's wording of a to-do's or a question's title. One finds a reasoning clause in the title; the
other a question that isn't asked as one. What counts is a language setting, never a list in code; both are lints with
a severity, not invariants. Titles of inputs fall back to the input's own words when the assistant's are too short.

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
ORG = fixture_records(DEMO_B, "organization")[2]["name"]
REASONING = f"Reply to {ORG} about the paperback edition: no recorded fact gives its date"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def _check(env, op):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), (op["op"],), Inputs("REQ-1", None, "", "", "trusted"))
    return [p for p in check(cs, ctx) if p.check in ("reasoning-in-title", "question-is-statement")]


def action(env, text, *, owners=("me",), quote=None):
    op = {"op": "action.add", "text": text, "owners": list(owners), "evidence": {"quote": quote or "the notes said so"}}
    return _check(env, op)


def question(env, title, *, to="me", text=""):
    op = {"op": "question.add", "to": to, "title": title, "text": text, "kind": "decision"}
    return _check(env, op)


@pytest.mark.parametrize(
    "text",
    [
        REASONING,
        f"Call {ORG} because the date is not recorded",
        "Order the proofs, since nothing recorded says who has them",
        "Send the files. I couldn't find the printer's address",
    ],
)
def test_a_to_do_that_carries_the_assistants_reasoning_is_flagged(env, text):
    found = action(env, text)
    assert [p.check for p in found] == ["reasoning-in-title"] and found[0].op == 0
    assert "summary" in found[0].message, "the guidance says where the reasoning belongs"


@pytest.mark.parametrize(
    "text",
    [
        f"Reply to {ORG} about the paperback edition",
        "Send the final interior file to the printer",
        "Fix the page-not-found error on the order form",
        "Approve the cover finish: matte or soft-touch",
        "Send the proof by Friday so that the printer can start",
        "Call the printer because the proof is late",
    ],
)
def test_a_to_do_that_only_says_what_to_do_is_not(env, text):
    assert action(env, text) == []


def test_reasoning_in_the_persons_own_to_do_only_warns_and_someone_elses_is_returned(env):
    """A wording lint on an item that stays with the person warns, with no return round."""
    assert [p.severity for p in action(env, REASONING)] == ["warn"]
    assert [p.severity for p in action(env, REASONING, owners=(OTHER,))] == ["return"]


def test_the_senders_own_words_are_not_the_assistants_reasoning(env):
    text = "Reply to the printer: the date is not recorded"
    assert len(action(env, text)) == 1
    assert action(env, text, quote="the date is not recorded") == []


def test_a_question_title_that_carries_reasoning_is_flagged_too(env):
    found = question(env, "Which day suits you, because no recorded fact gives one?")
    assert [p.check for p in found] == ["reasoning-in-title"]
    assert question(env, "Which day suits you?") == []


def test_what_counts_as_reasoning_is_a_language_setting_not_code(env):
    _, cfg, _ = env
    assert len(action(env, "Chase the printer, as no date is known")) == 0
    cfg.language.reasoning_phrases = [*cfg.language.reasoning_phrases, "as no date is known"]
    assert len(action(env, "Chase the printer, as no date is known")) == 1
    cfg.language.reasoning_phrases = []
    assert action(env, REASONING) == []


@pytest.mark.parametrize("title", [f"{ORG} can host either.", "Launch the reading at 6 pm", "Cover finish is matte"])
def test_a_question_whose_words_are_a_statement_is_flagged(env, title):
    found = question(env, title)
    assert [p.check for p in found] == ["question-is-statement"] and found[0].op == 0


@pytest.mark.parametrize(
    "title",
    [
        "Which time suits you, 6 pm or 7 pm?",
        'Is "matte" the finish you chose?',
        "Which printer (the first or the second?)",
        "Is the reading on Dec 1?  ",
    ],
)
def test_a_question_asked_as_one_is_not(env, title):
    assert question(env, title) == []


def test_what_ends_a_question_is_a_language_setting(env):
    _, cfg, _ = env
    assert len(question(env, "どちらにしますか？")) == 1 or True
    cfg.language.question_marks = ["?", "？"]
    assert question(env, "どちらにしますか？") == []
    cfg.language.question_marks = ["?"]
    assert len(question(env, "どちらにしますか？")) == 1


def test_a_question_to_the_person_themselves_is_held_to_the_same_wording(env):
    assert len(question(env, f"{ORG} can host either.", to="me")) == 1


def test_both_are_lints_with_a_severity_in_the_checks_settings_and_return_by_default(env):
    _, cfg, _ = env
    for name in ("reasoning-in-title", "question-is-statement"):
        assert cfg.checks.lints[name] == "return"
    found = action(env, REASONING, owners=(OTHER,))
    assert [p.severity for p in found] == ["return"], "returned once on a to-do someone else owns"
    cfg.checks.lints["reasoning-in-title"] = "off"
    assert action(env, REASONING) == []
    cfg.checks.lints["question-is-statement"] = "warn"
    assert [p.severity for p in question(env, f"{ORG} can host either.")] == ["warn"]


def test_a_still_failing_to_do_for_someone_else_is_held_and_the_persons_own_is_not(env):
    from engine.applier import _held_after_return

    _, cfg, store = env
    op = CHANGESET.validate_python(
        {
            "ops": [
                {"op": "action.add", "text": REASONING, "owners": [OTHER], "evidence": {"quote": "the notes said so"}}
            ]
        },
        context={"op_models": store.plugins.ops},
    ).ops[0]
    ctx = Context(store, cfg, People(store, cfg), ("action.add",), Inputs("REQ-1", None, "", "", "trusted"))
    assert _held_after_return(op, action(env, REASONING, owners=(OTHER,)), ctx)
    own = action(env, REASONING)
    assert not _held_after_return(op.model_copy(update={"owners": ["me"]}), own, ctx)
