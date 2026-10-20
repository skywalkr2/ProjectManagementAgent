"""One decision is one Today line (design 7.6, 7.7): a held op leaves the review line of its change and is asked once,
under Decide. The review line says how many of its ops wait there and counts only what the assistant already did; a
change whose only ops are held has no review line; and Looks good on a change never settles a held op."""

from __future__ import annotations

import json

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import looks_good, process
from engine.intake import hand_in
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_corrections import NOW, other_of
from tests.test_held_ask import held_drop
from tests.test_hold_drop_fold import _TEST, OPEN, RAW, an_action, drop_op, hold_op


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def told_about(env):
    """Make the first open action one that someone was told about, so dropping it waits for the person."""
    _, cfg, store = env
    action = OPEN[0]["id"]
    with store.transaction() as tx:
        tx.update(
            "action",
            action,
            {"told": {other_of(cfg): NOW.date().isoformat()}},
            _TEST,
            read_version=tx.get("action", action).version,
        )
    return action


def ran(env, ops):
    """Let the assistant answer a handed-in input with these ops; returns the changeset."""
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"summary": "Done.", "topic": "printer proof dates", "ops": ops}))
    handed = hand_in(ws, store, pasted=RAW, now=NOW)
    return process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)


def lines_of(env, kind):
    ws, cfg, store = env
    return [line for line in queue(ws, store, cfg, NOW) if line.kind == kind]


def test_a_change_holding_only_a_held_op_has_no_review_line_and_one_decide_line(env):
    cs_id, index, _ = held_drop(env)
    held = [line for line in lines_of(env, "held") if line.changeset == cs_id]
    assert [(line.group, line.op) for line in held] == [("decide", index)]
    assert not [line for line in lines_of(env, "review") if line.changeset == cs_id]


def test_a_review_line_leaves_out_the_held_op_and_says_how_many_wait_under_decide(env):
    _, cfg, store = env
    action = told_about(env)
    note = {"op": "note", "text": "The printer is waiting on the proof."}
    cs_id = ran(env, [drop_op(action), note])
    statuses = [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]
    assert statuses == ["held", "applied"]
    (review,) = [line for line in lines_of(env, "review") if line.changeset == cs_id]
    (held,) = [line for line in lines_of(env, "held") if line.changeset == cs_id]
    assert review.count == 1, "the line counts what was done, not what waits"
    assert review.outcome.get("held", 0) == 0 and review.outcome == {"notes": 1}
    assert review.deciding == [held.key], "it links to the line the held op is asked on"
    assert review.subject and "printer" in review.subject.lower()


def test_no_item_is_on_two_lines(env):
    """Every line names what it deals with: the op a held line asks about, or the ops of a change a review line counts
    (the applied ones). No op is on two lines, and a review line's own ops are never the ones another line asks."""
    ws, cfg, store = env
    action = told_about(env)
    ran(env, [drop_op(action), {"op": "note", "text": "The printer is waiting on the proof."}])
    on_a_line: dict[tuple[str, int], str] = {}
    lines = queue(ws, store, cfg, NOW)
    for line in lines:
        if line.kind in ("held", "who_is") and line.op is not None:
            assert (line.changeset, line.op) not in on_a_line
            on_a_line[(line.changeset, line.op)] = line.key
    for line in lines:
        if line.kind != "review":
            continue
        ops = store.read().get("changeset", line.changeset).data["ops"]
        counted = [o["index"] for o in ops if o["status"] == "applied"]
        assert counted and not [i for i in counted if (line.changeset, i) in on_a_line]
        assert sorted(line.deciding) == sorted(k for (cs, _), k in on_a_line.items() if cs == line.changeset)


def test_looks_good_never_settles_a_held_op(env):
    ws, cfg, store = env
    action = told_about(env)
    cs_id = ran(env, [drop_op(action), {"op": "note", "text": "The printer is waiting on the proof."}])
    looks_good(store, cs_id)
    outcomes = store.read().get("changeset", cs_id).data["ops"]
    assert [o["status"] for o in outcomes] == ["held", "applied"]
    assert store.read().get("action", action).data["status"] == "open"
    assert [line.changeset for line in lines_of(env, "held")] == [cs_id], "it still waits under Decide"
    assert not [line for line in lines_of(env, "review") if line.changeset == cs_id]


def test_a_held_line_carries_the_reason_it_waits_in_todays_words_and_where_it_came_from(env):
    from engine.applier import REACHED_WAITS

    ws, cfg, store = env
    cs_id, index, _ = held_drop(env)
    (held,) = [line for line in lines_of(env, "held") if line.changeset == cs_id]
    assert held.waiting == REACHED_WAITS, "the stored reason, as the card of the change words it"
    assert held.title is not None and held.title.kind == "pasted", "where it came from"
    assert held.held["quote"] and held.request


def test_a_review_line_for_one_thing_says_what_was_done_and_to_what(env):
    _, cfg, store = env
    action = an_action(cfg, mine=False)
    cs_id = ran(env, [hold_op(action)])
    assert [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]] == ["applied"]
    (review,) = [line for line in lines_of(env, "review") if line.changeset == cs_id]
    item = " ".join(store.read().get("action", action).data["text"].split())
    assert review.did == {"op": "action.hold", "item": item}
    assert review.deciding == []
    # More than one thing: no single account of what was done.
    both = ran(
        env, [hold_op(action, waiting="the proof"), {"op": "note", "text": "The printer is waiting on the proof."}]
    )
    (many,) = [line for line in lines_of(env, "review") if line.changeset == both]
    assert many.did is None and many.count == 2


def test_the_queue_carries_the_new_fields_through_the_api(tmp_path):
    from api.schemas import QueueLineView

    shown = QueueLineView(
        key="review:REQ-1",
        group="review",
        kind="review",
        count=1,
        did={"op": "action.drop", "item": "x"},
        deciding=["held:CS-1:0"],
    )
    assert shown.did.op == "action.drop" and shown.deciding == ["held:CS-1:0"]
