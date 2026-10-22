"""A conversation on a record (design 6.25, 6.32): the person talks to the assistant from a to-do, question, person,
project or calendar entry. Each message is an ask about that record, estimated and held for the person's go above the
configured amount, answered with prose and, when it proposes changes, a changeset each op of which the person keeps
or drops inline; the conversation stays on the record. The AI is the stub; names and ids come from the fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine import conversation
from engine import packet as packets
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config.schema import Price
from engine.dispatcher import process
from engine.storage import Store, StoreError
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records, without_first_go

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
PEOPLE = fixture_records(DEMO_B, "person")
ACTION = next(a for a in fixture_records(DEMO_B, "action") if a.get("status", "open") == "open")
PROJECT = fixture_records(DEMO_B, "project")[0]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


@pytest.fixture
def app(tmp_path):
    from api.app import create_app

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/"})
    application = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(application, headers={"Authorization": "Bearer t"})
    yield c, application.state.store, application.state.worker
    set_responder(None)


def reply(text: str, cites: list[str], *ops):
    """Make the stub answer every ask with one answer and the given ops; returns the packets it was shown."""
    seen = []

    def respond(task):
        seen.append(task)
        return json.dumps(
            {
                "summary": "Answered.",
                "ops": [{"op": "answer", "text": text, "cites": [{"quote": c} for c in cites]}, *ops],
            }
        )

    set_responder(respond)
    return seen


def say(env, message="What is this waiting on?", kind="action", record=ACTION["id"]) -> str:
    _, _, store = env
    return conversation.say(store, kind, record, message)


# ---- saying something ----


def test_a_message_is_an_ask_about_the_record_with_the_persons_own_words(env):
    _, _, store = env
    made = say(env, "  What is this waiting on?  ")
    data = store.read().get("request", made).data
    assert data["task"] == "ask" and data["origin"] == "pm" and data["state"] == "queued"
    assert data["about"] == {"kind": "action", "id": ACTION["id"]} and data["note"] == "What is this waiting on?"


@pytest.mark.parametrize("kind", ["action", "question", "person", "project", "event"])
def test_every_kind_the_conversation_names_can_be_talked_about(env, kind):
    _, _, store = env
    found = next(iter(store.read().list(kind)), None)
    if found is None:
        pytest.skip(f"the fixtures have no {kind}")
    assert store.read().get("request", conversation.say(store, kind, found.id, "Tell me about it.")).data["about"] == {
        "kind": kind,
        "id": found.id,
    }


def test_a_record_that_isnt_there_a_kind_that_cant_be_talked_about_and_no_words_are_refused(env):
    _, _, store = env
    with pytest.raises(StoreError, match="no action"):
        conversation.say(store, "action", "ACT-9999", "Hello")
    with pytest.raises(StoreError, match="to-do, question"):
        conversation.say(store, "snapshot", "SNAP-1", "Hello")
    with pytest.raises(StoreError, match="Say something"):
        conversation.say(store, "action", ACTION["id"], "   ")


# ---- what the assistant is sent ----


def test_the_packet_has_the_record_and_the_message_and_the_record_can_be_quoted(env):
    ws, cfg, store = env
    made = say(env)
    built = packets.build(ws, store, cfg, made, NOW.date())
    text = built.task.request
    assert "# The record this conversation is about" in text and ACTION["id"] in text and ACTION["text"] in text
    assert text.rstrip().endswith("<question>\nWhat is this waiting on?\n</question>")
    assert "# Earlier in this conversation" not in text
    assert ACTION["text"] in built.raw_input or ACTION["text"] in text
    assert built.knowledge is not None and built.cites == "help"


def test_earlier_exchanges_come_word_for_word_when_recent_and_as_one_short_line_when_older(env):
    ws, cfg, store = env
    cfg.steward.conversation.recent_turns = 1
    cfg.steward.conversation.older_turn_chars = 30
    first = say(env, "Who asked for this to be done, and when did they ask?")
    second = say(env, "Is it blocking anything else?")
    with store.transaction() as tx:
        for request, said in ((first, "Nobody asked."), (second, "It blocks nothing.")):
            tx.create("answer", {"request": request, "text": said, "cites": []}, conversation._ASK)
    third = say(env, "Then should I drop it?")
    text = packets.build(ws, store, cfg, third, NOW.date()).task.request
    earlier = text.split("# Earlier in this conversation\n", 1)[1].split("<question>", 1)[0]
    assert "- You were asked earlier: Who asked for this to be done…" in earlier and "when did they ask" not in earlier
    assert "- Asked: Is it blocking anything else?\n  You answered: It blocks nothing." in earlier
    assert "Nobody asked." not in earlier, "an older exchange is only its question's short line"


def test_the_conversation_is_kept_on_the_record_oldest_first_and_other_records_have_their_own(env):
    _, _, store = env
    other = next(a for a in store.read().list("action") if a.id != ACTION["id"] and a.data["status"] == "open")
    a = say(env, "First")
    b = say(env, "Second")
    c = say(env, "Elsewhere", record=other.id)
    assert [r.id for r in conversation.turns(store.read(), "action", ACTION["id"])] == [a, b]
    assert [r.id for r in conversation.turns(store.read(), "action", other.id)] == [c]


# ---- the answer, with its changes inline ----


def test_an_answer_is_prose_that_cites_the_record_and_is_kept_on_the_record(app):
    c, store, worker = app
    reply("It waits on the printer.", [ACTION["text"]])
    made = c.post(f"/api/records/action/{ACTION['id']}/conversation", json={"message": "What is this waiting on?"})
    assert made.status_code == 200
    worker.run_pending()
    view = c.get(f"/api/records/action/{ACTION['id']}/conversation").json()
    (turn,) = view["turns"]
    assert turn["id"] == made.json()["id"] and turn["about"] == {"kind": "action", "id": ACTION["id"]}
    assert turn["answer"]["text"] == "It waits on the printer."
    assert turn["answer"]["cites"][0]["quote"] == ACTION["text"] and turn["ops"] == []
    assert store.read().list("run")[-1].data["knowledge"], "the run wrote its knowledge log"


def test_a_conversation_on_a_record_is_not_in_the_general_ask_list(app):
    c, _, worker = app
    reply("Fine.", [ACTION["text"]])
    c.post(f"/api/records/action/{ACTION['id']}/conversation", json={"message": "Hello?"})
    c.post("/api/ask", json={"question": "What is the weather?"})
    worker.run_pending()
    assert [a["question"] for a in c.get("/api/asks").json()] == ["What is the weather?"]


def test_changes_the_assistant_proposes_are_listed_with_the_answer_and_dropping_one_undoes_only_it(app):
    c, store, worker = app
    me = store.read().get("person", PEOPLE[0]["id"]).id
    ops = [
        {
            "op": "action.add",
            "text": "Confirm the print date",
            "owners": [me],
            "project": PROJECT["id"],
            "evidence": {"quote": "Please add: confirm the print date"},
        },
        {
            "op": "action.add",
            "text": "Check the proof",
            "owners": [me],
            "project": PROJECT["id"],
            "evidence": {"quote": "Please add: confirm the print date"},
        },
    ]
    reply("Added two to-dos.", [ACTION["text"]], *ops)
    c.post(
        f"/api/records/action/{ACTION['id']}/conversation",
        json={"message": "Please add: confirm the print date"},
    )
    worker.run_pending()
    (turn,) = c.get(f"/api/records/action/{ACTION['id']}/conversation").json()["turns"]
    assert [o["title"] for o in turn["ops"]] == ["Confirm the print date", "Check the proof"]
    assert {o["status"] for o in turn["ops"]} == {"applied"} and turn["reviewed"] is False
    first, second = turn["ops"]
    texts = lambda: {a.data["text"] for a in store.read().list("action")}  # noqa: E731
    assert {"Confirm the print date", "Check the proof"} <= texts()
    dropped = c.post(f"/api/changesets/{turn['changeset']}/undo", json={"ops": [second["index"]]})
    assert dropped.status_code == 200 and dropped.json()["restored"] == [second["index"]]
    assert "Check the proof" not in texts() and "Confirm the print date" in texts()
    (after,) = c.get(f"/api/records/action/{ACTION['id']}/conversation").json()["turns"]
    assert {o["index"]: o["status"] for o in after["ops"]} == {first["index"]: "applied", second["index"]: "undone"}
    kept = c.post(f"/api/changesets/{turn['changeset']}/looks-good")
    assert kept.status_code == 200
    assert c.get(f"/api/records/action/{ACTION['id']}/conversation").json()["turns"][0]["reviewed"] is True
    assert [s.data["kind"] for s in store.read().list("signal")].count("undone") >= 1


def test_the_conversation_of_a_missing_record_or_an_unsupported_kind_is_not_found(app):
    c, _, _ = app
    assert c.get("/api/records/action/ACT-9999/conversation").status_code == 404
    assert c.get("/api/records/snapshot/SNAP-1/conversation").status_code == 404
    assert c.post("/api/records/action/ACT-9999/conversation", json={"message": "Hi"}).status_code == 409


# ---- estimated and held for the go ----


def test_a_message_is_estimated_and_waits_for_the_go_above_the_amount_to_confirm(env):
    ws, cfg, store = env
    use = cfg.ai.tiers["routine"].use
    cfg.ai.prices[use] = Price(input_per_million=500_000.0, output_per_million=500_000.0)
    cfg.ai.budgets.per_run_usd = 1_000_000.0
    cfg.ai.budgets.confirm_above_usd = 0.0
    seen = reply("Fine.", [ACTION["text"]])
    made = say(env)
    process(ws, store, cfg, Router(cfg, store, env={}), made, now=NOW)
    held = store.read().get("request", made).data
    assert (held["state"], held["approval"]) == ("needs_you", "required") and held["estimate_usd"] > 0
    assert seen == [], "nothing was sent before the go"
