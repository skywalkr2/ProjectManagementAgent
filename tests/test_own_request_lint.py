"""The person's own request is not their promise: an action owned by the person alone, from mail the person sent,
whose evidence quote asks someone to do something, is sent back once. A rule on the quote and the From line, with no
AI: mail from anyone else, the person's own note, a quote where the person says they will do it, the lint switched off
and a project's switch-off are left alone.

Names, ids and addresses come from the fixtures; the AI is not involved.
"""

from __future__ import annotations

import pytest

from engine.ai.adapters.stub import set_responder
from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

LINT = "own-request-not-promise"
PEOPLE = fixture_records(DEMO_B, "person")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
ME = next(p for p in PEOPLE if p["id"] == "PER-1")
OTHER = next(p for p in PEOPLE if p.get("how_to_reach", {}).get("email"))
RECIPIENT = next(p for p in PEOPLE if p["id"] not in (ME["id"], OTHER["id"]))
MY_ADDRESS = f"{ME['full_name'].lower().replace(' ', '.')}@example.com"
ASK = f"Can you send {RECIPIENT['full_name']} the agenda Monday?"
PROMISE = f"I'll send {RECIPIENT['full_name']} the agenda Monday."


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    cfg.workspace.user.accounts = [f"{ME['full_name']} <{MY_ADDRESS}>"]
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def mail(sender: str, body: str) -> str:
    return f"From: {sender}\nTo: {OTHER['how_to_reach']['email']}\nSubject: Agenda\n\n{body}\n"


FROM_ME = f"{ME['full_name']} <{MY_ADDRESS}>"
FROM_OTHER = f"{OTHER['full_name']} <{OTHER['how_to_reach']['email']}>"


def action(quote: str, owner: str = ME["id"], **more) -> dict:
    return {
        "op": "action.add",
        "text": f"Send {RECIPIENT['full_name']} the agenda",
        "owners": [owner],
        "project": PROJECT,
        "evidence": {"quote": quote},
        **more,
    }


def found(env, op: dict, raw: str, *, actor: str = "assistant", trust: str = "untrusted") -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", "SRC-1" if trust == "untrusted" else None, raw, "", trust),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == LINT]


def test_the_persons_request_in_their_sent_mail_is_not_their_promise(env):
    (problem,) = found(env, action(ASK), mail(FROM_ME, ASK))
    assert (problem.severity, problem.op) == ("return", 0)
    assert "isn't their promise" in problem.message and "no action" in problem.message


def test_a_question_mark_or_please_makes_it_a_request_too(env):
    assert found(env, action("The agenda for Monday, sent on?"), mail(FROM_ME, "The agenda for Monday, sent on?"))
    please = f"Please send {RECIPIENT['full_name']} the agenda Monday."
    assert found(env, action(please), mail(FROM_ME, please))


def test_the_same_quote_in_mail_from_someone_else_is_left_alone(env):
    assert found(env, action(ASK), mail(FROM_OTHER, ASK)) == []


def test_the_persons_promise_in_the_same_sentence_is_left_alone(env):
    assert found(env, action(PROMISE), mail(FROM_ME, PROMISE)) == []
    said = f"I will send it Monday, can you confirm {RECIPIENT['full_name']} is on the list?"
    assert found(env, action(said), mail(FROM_ME, said)) == []


def test_an_action_someone_else_owns_is_left_alone(env):
    assert found(env, action(ASK, owner=RECIPIENT["id"]), mail(FROM_ME, ASK)) == []


def test_the_persons_own_note_is_left_alone(env):
    assert found(env, action(ASK), ASK, actor="pm", trust="trusted") == []
    assert found(env, action(ASK), ASK, trust="trusted") == []


def test_severity_off_turns_it_off(env):
    _, cfg, _ = env
    cfg.checks.lints[LINT] = "off"
    assert found(env, action(ASK), mail(FROM_ME, ASK)) == []


def test_a_project_can_switch_it_off(env):
    _, cfg, _ = env
    cfg.checks.projects[PROJECT] = {LINT: "off"}
    assert found(env, action(ASK), mail(FROM_ME, ASK)) == []


def test_the_asking_words_are_config(env):
    _, cfg, _ = env
    cfg.language.ask_lead_words = ["Kindly"]
    cfg.language.question_marks = []
    assert found(env, action(ASK), mail(FROM_ME, ASK)) == []
    kindly = f"Kindly send {RECIPIENT['full_name']} the agenda Monday."
    assert found(env, action(kindly), mail(FROM_ME, kindly))


# ---- own-promise-missed: the person's own promise in mail they sent is their to-do ---------------------------------


def missed(env, ops: list[dict], raw: str, *, actor: str = "assistant") -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", "SRC-1", raw, "", "untrusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == "own-promise-missed"]


def test_the_persons_own_promise_in_mail_they_sent_answered_without_their_action_is_sent_back(env):
    (problem,) = missed(env, [], mail(FROM_ME, PROMISE))
    assert problem.severity == "return" and PROMISE.rstrip(".") in problem.message
    news = {"op": "action.news", "id": "ACT-1", "text": "They will look at it", "evidence": {"quote": PROMISE}}
    assert missed(env, [news], mail(FROM_ME, PROMISE)) != []  # news on someone else's action doesn't record it


def test_an_action_of_the_persons_quoting_the_promise_settles_it_and_others_mail_and_their_own_note_are_left(env):
    assert missed(env, [action(PROMISE)], mail(FROM_ME, PROMISE)) == []
    assert missed(env, [], mail(FROM_OTHER, PROMISE)) == []
    assert missed(env, [], mail(FROM_ME, ASK)) == []
    assert missed(env, [], mail(FROM_ME, PROMISE), actor="pm") == []
