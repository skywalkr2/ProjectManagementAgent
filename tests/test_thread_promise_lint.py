"""A reply that quotes an open promise (design 6.33): when the quoted history of the input holds words an open action
was recorded with, and the answer has no op on that action, the answer is sent back once to say what the reply means
for it. A rule on the words, with no AI and no overlap guessing; input without quoted history behaves as before.

Names, ids and addresses come from the fixtures; the AI is the stub.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import THREAD_PROMISE_MIN_WORDS, Context, Inputs, check
from engine.dispatcher import process
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
LINT = "thread-promise-unanswered"
_PM = WriteContext("pm", "trusted", "test")
SETTER = next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == "Editor")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
PROMISE = "to send the final interior file to the printer by the 16th"
FIRST, SECOND = PROMISE.split(" file ")
MAIL = f"Interior: {SETTER['full_name']} {PROMISE}."
# The same words as a mail program quotes them: wrapped, marked and indented.
REPLY = (
    "Thanks, the final interior file proofs came back late this week.\n\n"
    f"On Thu, Oct 8, 2026, {SETTER['full_name']} wrote:\n"
    f"> Interior: {SETTER['full_name']} {FIRST}\n"
    f"> file {SECOND}.\n"
)
UNRELATED = (
    "Thanks, the final interior file proofs came back late this week.\n\n"
    f"On Thu, Oct 8, 2026, {SETTER['full_name']} wrote:\n> Lunch is at noon on Friday, see you there.\n"
)
NEWS_QUOTE = "the final interior file proofs came back late this week"
ADD = {
    "summary": "One action.",
    "ops": [
        {
            "op": "action.add",
            "text": "Send the final interior file to the printer",
            "owners": [SETTER["full_name"]],
            "due": "2026-10-16",
            "project": PROJECT,
            "evidence": {"quote": PROMISE},
        }
    ],
}


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def answering(*bodies: dict) -> list:
    """Make the stub answer reading notes with these changesets in turn (the last repeats), and record what it was
    asked; other kinds of work get an empty answer."""
    asked: list = []
    queue = [json.dumps(b) for b in bodies]

    def responder(task):
        if task.kind != "notes":
            return json.dumps({"summary": "", "ops": []})
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    set_responder(responder)
    return asked


def hand_in_and_run(env, pasted: str, note: str = ""):
    ws, cfg, store = env
    handed = hand_in(ws, store, note=note, pasted=pasted, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    return handed, cs_id


def promise(env, body: dict = ADD, mail: str = MAIL) -> str:
    """The open action the first mail made, through a real hand-in, so its ledger holds the quote."""
    _, _, store = env
    before = {a.id for a in store.read().list("action")}
    answering(body)
    hand_in_and_run(env, mail)
    (action,) = (a for a in store.read().list("action") if a.id not in before)
    assert action.data["status"] == "open"
    return action.id


def found(
    env,
    reply: str,
    ops: list | None = None,
    *,
    request: str | None = None,
    trust="untrusted",
    actor="assistant",
    lint: str = LINT,
):
    """The problems of one lint (this one unless named) for an answer with these ops to a reply, as the applier checks
    it."""
    _, cfg, store = env
    ops = ops or []
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request or "REQ-1", None, "", "", trust),
        actor=actor,
    )
    ctx.inputs.raw_input = reply
    if trust == "untrusted":
        ctx.inputs.source = "SRC-1"
    return [p for p in check(cs, ctx) if p.check == lint]


def news(action_id: str) -> dict:
    return {
        "op": "action.news",
        "id": action_id,
        "text": "The reply says the proofs are late.",
        "evidence": {"quote": NEWS_QUOTE},
    }


def test_a_reply_quoting_an_open_promise_with_no_op_on_it_is_flagged(env):
    action = promise(env)
    (problem,) = found(env, REPLY)
    assert (problem.severity, problem.op) == ("return", None)
    assert action in problem.message and "action.news" in problem.message


def test_an_empty_answer_is_checked_too(env):
    action = promise(env)
    assert [p.check for p in found(env, REPLY, [])] == [LINT]
    assert action in found(env, REPLY, [])[0].message


def test_an_op_on_that_action_answers_it(env):
    action = promise(env)
    assert found(env, REPLY, [news(action)]) == []


def test_history_that_quotes_none_of_the_open_promises_is_left_alone(env):
    promise(env)
    assert found(env, UNRELATED) == []


def test_input_with_no_quoted_history_is_left_alone(env):
    promise(env)
    assert found(env, f"Interior: {SETTER['full_name']} {PROMISE}.") == []


def test_a_closed_promise_quoted_in_history_is_left_alone(env):
    _, _, store = env
    action = promise(env)
    with store.transaction() as tx:
        current = tx.get("action", action)
        tx.update("action", action, {"status": "done"}, _PM, read_version=current.version)
    assert found(env, REPLY) == []


def test_a_quote_of_only_a_few_words_is_not_enough_to_link_a_promise(env):
    short = "send proofs Friday"
    assert len(short.split()) < THREAD_PROMISE_MIN_WORDS
    body = {"summary": "One action.", "ops": [{**ADD["ops"][0], "evidence": {"quote": short}}]}
    promise(env, body, f"{SETTER['full_name']} {short}.")
    history = f"On Thu, Oct 8, 2026, {SETTER['full_name']} wrote:\n> {SETTER['full_name']} {short}.\n"
    assert found(env, "Thanks.\n\n" + history) == []


def test_severity_off_turns_it_off(env):
    _, cfg, _ = env
    promise(env)
    cfg.checks.lints[LINT] = "off"
    assert found(env, REPLY) == []


def test_a_project_can_switch_it_off(env):
    _, cfg, _ = env
    promise(env)
    cfg.checks.projects[PROJECT] = {LINT: "off"}
    assert found(env, REPLY) == []
    cfg.checks.projects[PROJECT] = {LINT: "warn"}
    assert [p.severity for p in found(env, REPLY)] == ["warn"]


def test_the_persons_own_note_quoting_it_is_left_alone(env):
    ws, cfg, store = env
    promise(env)
    note = hand_in(ws, store, note="Checking in on this", now=NOW)
    assert found(env, REPLY, request=note.request, trust="trusted") == []


def test_a_change_the_person_makes_is_left_alone(env):
    promise(env)
    assert found(env, REPLY, actor="pm") == []


def test_through_a_hand_in_an_empty_answer_is_sent_back_once(env, monkeypatch):
    _, _, store = env
    monkeypatch.setattr("engine.dispatcher.escalation_tier", lambda cfg, tier: None)  # one run, not a stronger re-run
    action = promise(env)
    asked = answering({"summary": "Nothing to do.", "ops": []})
    hand_in_and_run(env, REPLY)
    assert len(asked) == 2, "one answer, one return round, then it stops"
    assert action in asked[1].request and "quotes the promise" in asked[1].request
    assert "quotes the promise" not in asked[0].request
    assert store.read().get("action", action).data.get("news", []) == []


def test_through_a_hand_in_news_on_the_promise_is_accepted_at_once(env):
    _, _, store = env
    action = promise(env)
    asked = answering({"summary": "News.", "ops": [news(action)]})
    _, cs_id = hand_in_and_run(env, REPLY)
    assert len(asked) == 1
    assert [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]] == ["applied"]
    assert store.read().get("action", action).data["news"][0]["quote"] == NEWS_QUOTE


def test_news_from_a_reply_that_quotes_the_promise_is_about_it_whatever_its_own_words(env):
    """The reply's history holds the promise's words, so its new text is about the promise even when it shares no word
    with the action; the same words with no such history are still sent back as not about it."""
    action = promise(env)
    short = "Noted, many thanks."
    reply = short + REPLY[REPLY.index("\n\n") :]
    said = {**news(action), "evidence": {"quote": short}}
    assert found(env, reply, [said], lint="evidence-fit") == []
    assert found(env, short, [said], lint="evidence-fit") != []
