"""A reply owed with no drafted reply, from a run that never searched, is checked like a question: when a recorded fact
already answers the words the person was asked, the answer goes back once to draft the reply from it. A rule on the
words, with no AI; a reply that is drafted, a run that searched and a subject no fact answers are left alone.

Names and ids come from the fixtures.
"""

from __future__ import annotations

import pytest

from engine.ai.adapters.stub import set_responder
from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

LINT = "already-known"
_PM = WriteContext("pm", "trusted", "test")
PROJECT = fixture_records(DEMO_B, "project")[0]
ASKED = f"What is the interior file deadline for {PROJECT['name']}?"
FACT = f"The interior file deadline for {PROJECT['name']} is the sixteenth of October"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def add_fact(store) -> str:
    with store.transaction() as tx:
        return tx.create("fact", {"text": FACT, "project": PROJECT["id"]}, _PM).id


def reply_owed(cfg, quote: str = ASKED, **more) -> dict:
    return {
        "op": "action.add",
        "text": "Tell them the interior file deadline",
        "owners": [cfg.workspace.user.person],
        "reply_owed": True,
        "evidence": {"quote": quote},
        **more,
    }


def found(env, op: dict, *, searched: bool = False) -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, ASKED, "", "untrusted"),
        actor="assistant",
        searched=searched,
    )
    return [p for p in check(cs, ctx) if p.check == LINT]


def test_a_reply_owed_with_no_reply_about_a_subject_a_fact_answers_is_returned(env):
    _, cfg, store = env
    fact = add_fact(store)
    (problem,) = found(env, reply_owed(cfg))
    assert (problem.severity, problem.op) == ("return", 0)
    assert problem.message.startswith(f"{fact} looks like the answer: {FACT}")
    assert "never the id" in problem.message


def test_a_reply_owed_that_already_has_its_reply_is_left_alone(env):
    _, cfg, store = env
    add_fact(store)
    assert found(env, reply_owed(cfg, reply="The interior file deadline is the sixteenth of October.")) == []


def test_a_run_that_searched_is_left_alone(env):
    _, cfg, store = env
    add_fact(store)
    assert found(env, reply_owed(cfg), searched=True) == []


def test_a_subject_no_fact_answers_is_left_alone(env):
    _, cfg, store = env
    add_fact(store)
    assert found(env, reply_owed(cfg, f"Which caterer handles the party for {PROJECT['name']}?")) == []


def test_an_action_that_is_not_a_reply_owed_is_left_alone(env):
    _, cfg, store = env
    add_fact(store)
    assert found(env, reply_owed(cfg, reply_owed=False)) == []


def test_the_lint_off_in_config_leaves_it_alone(env):
    _, cfg, store = env
    add_fact(store)
    cfg.checks.lints[LINT] = "off"
    assert found(env, reply_owed(cfg)) == []
