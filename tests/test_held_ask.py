"""A held item is asked as a question (design 7.6, 7.7): the line says what would change, who was told, and the words it
rests on; keeping things as they are leaves the list, records one correction the assistant learns from, and can be taken
back. Names, ids and texts come from the fixtures."""

from __future__ import annotations

import json

import pytest

from engine import held_ask
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import DECLINED_REASON, decline_held, undecline_held
from engine.dispatcher import process
from engine.intake import hand_in
from engine.names import People
from engine.storage import Store, StoreError
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_corrections import NOW, other_of, signals
from tests.test_hold_drop_fold import _TEST, DROPPING, OPEN, RAW, data, drop_op


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def held_drop(env):
    """A run's drop of an action someone was told about: it waits for the person. Returns the changeset, its index and
    the action."""
    ws, cfg, store = env
    action = OPEN[0]["id"]
    someone = other_of(cfg)
    with store.transaction() as tx:
        tx.update(
            "action",
            action,
            {"told": {someone: NOW.date().isoformat()}},
            _TEST,
            read_version=tx.get("action", action).version,
        )
    set_responder(lambda task: json.dumps({"summary": "Dropped.", "ops": [drop_op(action)]}))
    handed = hand_in(ws, store, pasted=RAW, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "held", outcome
    return cs_id, outcome["index"], action


def test_a_held_drop_is_asked_with_who_was_told_and_the_words_it_rests_on(env):
    ws, cfg, store = env
    cs_id, index, action = held_drop(env)
    line = next(line for line in queue(ws, store, cfg, NOW) if line.kind == "held")
    assert line.held["ask"] == "drop"
    assert line.held["item"] == " ".join(data(store, "action", action)["text"].split())
    assert (
        line.held["told"] == [People(store, cfg).name(other_of(cfg))] and line.held["told_on"] == NOW.date().isoformat()
    )
    assert line.held["quote"] == DROPPING


def test_close_date_and_routing_holds_are_asked_as_what_they_would_change(env):
    _, cfg, store = env
    people = People(store, cfg)
    view = store.read()
    mine = OPEN[0]
    close = held_ask.describe(view, people, {"op": "action.close", "id": mine["id"], "evidence": {"quote": "done"}})
    assert close == {"ask": "close", "item": " ".join(mine["text"].split()), "quote": "done"}
    moved = held_ask.describe(
        view, people, {"op": "record.set", "kind": "action", "id": mine["id"], "field": "due", "value": "2030-11-05"}
    )
    assert moved["ask"] == "date" and moved["value"] == "2030-11-05" and moved["item"] == close["item"]
    question = view.list("question")[0]
    target = next(p for p in view.list("person") if p.id != question.data["to"])
    sent = held_ask.describe(view, people, {"op": "question.move", "id": question.id, "to": target.id})
    assert sent["ask"] == "routing" and sent["to_name"] == target.data["full_name"]
    assert held_ask.describe(view, people, {"op": "note", "text": "x"}) is None
    assert held_ask.describe(view, people, {"op": "action.close", "id": "ACT-999"}) is None


def test_keeping_things_as_they_are_leaves_the_list_and_records_one_correction(env):
    ws, cfg, store = env
    cs_id, index, action = held_drop(env)
    decline_held(store, cs_id, index, now=NOW)
    outcome = store.read().get("changeset", cs_id).data["ops"][index]
    assert outcome["status"] == "undone" and outcome["reason"] == DECLINED_REASON
    assert data(store, "action", action)["status"] == "open"
    assert not [line for line in queue(ws, store, cfg, NOW) if line.kind == "held"]
    (signal,) = signals(store, "held_declined")
    assert action in signal["refs"] and cs_id in signal["refs"]
    with pytest.raises(StoreError):
        decline_held(store, cs_id, index, now=NOW)


def test_taking_that_back_makes_it_wait_again_and_the_correction_is_not_learned_from(env):
    ws, cfg, store = env
    cs_id, index, action = held_drop(env)
    before = store.read().get("changeset", cs_id).data["ops"][index]["reason"]
    decline_held(store, cs_id, index, now=NOW)
    undecline_held(store, cs_id, index)
    outcome = store.read().get("changeset", cs_id).data["ops"][index]
    assert outcome["status"] == "held" and outcome["reason"] == before
    assert any(line.kind == "held" for line in queue(ws, store, cfg, NOW))
    with pytest.raises(StoreError):
        undecline_held(store, cs_id, index)
