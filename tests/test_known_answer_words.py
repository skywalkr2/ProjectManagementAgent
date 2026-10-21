"""Whether a recorded fact already answers a question compares folded words (plurals, "ing" and "ed") and leaves out the
words that frame a question, so a question asked in full sentences is matched as well as its bare topic. The model's own
workspace search keeps matching whole words.

Names and ids come from the fixtures.
"""

from __future__ import annotations

import pytest

from engine import search as workspace_search
from engine.ai.adapters.stub import set_responder
from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

_PM = WriteContext("pm", "trusted", "test")
PROJECT = fixture_records(DEMO_B, "project")[0]
FACT = "The printer's published schedule lists the interior proofs shipping on November 3."
CAN_YOU = "Can you tell me when the interior proofs will ship?"
TITLE = "When will the interior proofs ship?"
BUDGET = "What is the budget for the interior proofs?"
SIMILARITY = 0.7


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def add_fact(store, text: str = FACT) -> str:
    with store.transaction() as tx:
        return tx.create("fact", {"text": text, "project": PROJECT["id"]}, _PM).id


def answered_by(env, subject: str, *, asking_words=None):
    _, cfg, store = env
    words = cfg.language.asking_words if asking_words is None else asking_words
    return workspace_search.known_answer(store, subject, similarity=SIMILARITY, asking_words=words)


def test_a_question_in_full_words_is_answered_by_the_fact_that_holds_its_topic(env):
    fact = add_fact(env[2])
    hit = answered_by(env, CAN_YOU)
    assert hit is not None and hit.id == fact


def test_a_question_title_is_answered_by_the_same_fact(env):
    fact = add_fact(env[2])
    hit = answered_by(env, TITLE)
    assert hit is not None and hit.id == fact


def test_a_question_about_something_the_fact_does_not_hold_is_not_answered(env):
    add_fact(env[2])
    assert answered_by(env, BUDGET) is None


def test_with_no_asking_words_the_framing_words_keep_the_fact_from_answering(env):
    add_fact(env[2])
    assert answered_by(env, CAN_YOU, asking_words=[]) is None


def test_the_default_asking_words_come_from_the_configuration(env):
    _, cfg, _ = env
    assert {"when", "will", "tell"} <= set(cfg.language.asking_words)


def test_words_fold_plurals_and_endings_with_a_doubled_consonant_undone():
    fold = workspace_search._fold
    assert fold("proofs") == fold("proof") == "proof"
    assert fold("copies") == "copy"
    assert fold("shipping") == fold("shipped") == fold("ship") == "ship"
    assert fold("install") == fold("installed") == fold("installing") == "install"
    assert fold("process") == "process"


def test_the_minimum_words_count_the_subjects_words_after_the_asking_words_are_left_out(env):
    add_fact(env[2])
    assert answered_by(env, "When will the proofs ship?") is not None
    assert answered_by(env, "When will the proofs?") is None


def test_the_models_search_still_matches_whole_words(env):
    ws, _, store = env
    fact = add_fact(store)
    found = workspace_search.search(ws, store, workspace_search.Query(words="shipping", kinds=("facts",)), limit=5)
    assert [h.id for h in found] == [fact]
    assert workspace_search.search(ws, store, workspace_search.Query(words="ship", kinds=("facts",)), limit=5) == []


def test_a_reply_owed_with_no_draft_is_returned_when_a_fact_answers_the_question_in_full_words(env):
    _, cfg, store = env
    fact = add_fact(store)
    op = {
        "op": "action.add",
        "text": "Tell them when the interior proofs ship",
        "owners": [cfg.workspace.user.person],
        "reply_owed": True,
        "evidence": {"quote": CAN_YOU},
    }
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, CAN_YOU, "", "untrusted"),
        actor="assistant",
        searched=False,
    )
    (problem,) = [p for p in check(cs, ctx) if p.check == "already-known"]
    assert (problem.severity, problem.op) == ("return", 0)
    assert problem.message.startswith(f"{fact} looks like the answer: {FACT}")
