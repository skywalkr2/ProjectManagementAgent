"""No record id in a title the person reads (design 6.7, 7.14; roadmap B-8 R1, check C54).

Every label an op gives the person names its record by its title in quotes, never by its id, and falls back to the
kind of record in words when the record has no title; an op that writes a title holding the id of a record that exists
is refused (an invariant, `id-in-title`); and the sweep re-words stored labels and titles that already hold an id.
Names, ids and texts come from the fixtures.
"""

from __future__ import annotations

import json
import re

import pytest

from engine import outward
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import _label
from engine.dispatcher import process
from engine.id_words import title_of
from engine.intake import hand_in
from engine.ops import OP_MODELS
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_corrections import NOW
from tests.test_held_ask import held_drop
from tests.test_hold_drop_fold import DROPPING, OPEN, RAW, drop_op, hold_op
from tests.test_knowledge_records import apply, reasons, source

_TEST = WriteContext(actor="pm", trust="trusted", op="test.titles-without-ids")
ID = re.compile(r"\b[A-Z]{2,}-\d+\b")
QUESTIONS = fixture_records(DEMO_B, "question")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def words(record: dict) -> str:
    """A record's title as a label gives it, cut where a label cuts it."""
    return title_of(record) or ""


def made(op: dict):
    return OP_MODELS[op["op"]].model_validate(op)


def test_every_label_names_its_record_by_title_and_never_by_id(env):
    _, cfg, store = env
    view = store.read()
    action = OPEN[0]
    question = QUESTIONS[0]
    ops = [
        (hold_op(action["id"]), action),
        ({"op": "action.unhold", "id": action["id"], "evidence": {"quote": "the proof"}}, action),
        (drop_op(action["id"]), action),
        ({"op": "action.move", "id": action["id"], "due": "2026-11-05", "evidence": {"quote": "Nov 5"}}, action),
        (
            {
                "op": "action.part",
                "id": action["id"],
                "delivered": "the draft",
                "left": "the notes",
                "evidence": {"quote": "the draft"},
            },
            action,
        ),
        ({"op": "action.news", "id": action["id"], "text": "It slipped", "evidence": {"quote": "It slipped"}}, action),
        ({"op": "action.reply", "id": action["id"]}, action),
        ({"op": "question.update", "id": question["id"], "title": "A new way to ask"}, question),
        (
            {"op": "question.drop", "id": question["id"], "reason": "Not needed", "evidence": {"quote": "Not needed"}},
            question,
        ),
        ({"op": "question.mark_sent", "id": question["id"]}, question),
        (
            {
                "op": "record.edit",
                "record": {"kind": "action", "id": action["id"]},
                "fields": {"notes": "x"},
                "read_version": 1,
            },
            action,
        ),
    ]
    for op, record in ops:
        label = _label(made(op), view, store)
        assert label, op["op"]
        assert not ID.search(label), (op["op"], label)
        assert f"'{words(record)}'" in label, (op["op"], label)


def test_an_op_whose_record_has_no_title_names_its_kind_in_words_never_its_id(env):
    _, _, store = env
    gone = "ACT-9999"
    for op in (
        drop_op(gone),
        {"op": "action.hold", "id": gone, "waiting_for": "the proof", "evidence": {"quote": "the proof"}},
    ):
        label = _label(made(op), store.read(), store)
        assert label and not ID.search(label), label
    # Even without a view to read titles from, a label never holds the id.
    assert not ID.search(made(drop_op(gone)).describe() or "")


def review_line(env):
    """A run's hold of an action nobody was told about: it applies at once and waits for a look."""
    ws, cfg, store = env
    action = next(a["id"] for a in OPEN if not a.get("told"))
    set_responder(lambda task: json.dumps({"summary": "Held.", "ops": [hold_op(action)]}))
    handed = hand_in(ws, store, pasted=RAW, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "applied", outcome
    return action, next(line for line in queue(ws, store, cfg, NOW) if line.kind == "review")


def test_a_review_line_and_a_held_line_are_titled_by_the_item_and_hold_no_id(env):
    ws, cfg, store = env
    action, line = review_line(env)
    title = words(store.read().get("action", action).data)
    assert line.subject and f"'{title}'" in line.subject and not ID.search(line.subject)
    set_responder(None)


def test_a_held_drops_line_names_the_item_by_title(env):
    ws, cfg, store = env
    cs_id, index, action = held_drop(env)
    title = words(store.read().get("action", action).data)
    line = next(line for line in queue(ws, store, cfg, NOW) if line.kind == "held")
    assert line.text and f"'{title}'" in line.text and not ID.search(line.text)
    outcome = store.read().get("changeset", cs_id).data["ops"][index]
    assert not ID.search(outcome["label"])
    assert DROPPING in line.held["quote"]


# ---- the invariant --------------------------------------------------------------------------------------------------


def test_an_op_that_writes_a_title_holding_the_id_of_a_record_is_refused_with_the_reason(env):
    _, cfg, store = env
    target = OPEN[0]["id"]
    src = source(store)
    text = f"Finish what {target} started"
    cs_id, result = apply(
        store,
        cfg,
        [{"op": "action.add", "text": text, "evidence": {"quote": text}}],
        origin="input",
        trust="untrusted",
        source_id=src,
        raw=text,
    )
    assert result == ["refused"]
    (reason,) = reasons(store, cs_id)
    assert words(OPEN[0]) in reason and target not in reason
    # A question's title, a project's name and a record.set of a title are refused the same way.
    for op in (
        {"op": "question.add", "title": f"Is {target} done?", "to": "PER-1"},
        {
            "op": "record.set",
            "kind": "action",
            "id": target,
            "field": "text",
            "value": f"As {target}",
            "evidence": {"quote": text},
        },
    ):
        _, result = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=src, raw=text)
        assert result == ["refused"], op["op"]


def test_a_title_that_names_no_existing_record_is_not_refused(env):
    _, cfg, store = env
    text = "Compare with ACT-987654 and COVID-19 numbers"
    src = source(store)
    _, result = apply(
        store,
        cfg,
        [{"op": "action.add", "text": text, "evidence": {"quote": text}}],
        origin="input",
        trust="untrusted",
        source_id=src,
        raw=text,
    )
    assert result != ["refused"]


def test_the_person_typing_a_title_is_not_refused(env):
    _, cfg, store = env
    target = OPEN[0]["id"]
    cs_id, result = apply(
        store,
        cfg,
        [{"op": "action.add", "text": f"Chase {target}", "evidence": {"quote": "Chase it"}}],
        origin="pm",
        actor="pm",
        source_id=source(store),
        raw="Chase it",
    )
    assert result != ["refused"], reasons(store, cs_id)


# ---- the sweep ------------------------------------------------------------------------------------------------------


def old_label_row(store, action: str, cs_id: str) -> None:
    """Make a changeset's label the way it was written before labels named records by title."""
    rec = store.read().get("changeset", cs_id)
    ops = [dict(o) for o in rec.data["ops"]]
    ops[0]["label"] = f"Put action {action} on hold"
    with store.transaction() as tx:
        tx.update("changeset", cs_id, {"ops": ops}, _TEST, read_version=rec.version)


def test_the_sweep_rewords_an_old_label_from_the_record(env):
    ws, cfg, store = env
    action, line = review_line(env)
    cs_id = line.changeset
    old_label_row(store, action, cs_id)
    assert queue(ws, store, cfg, NOW)  # the old label is what Today would show
    assert outward.sweep_ids(store, cfg) == 1
    label = store.read().get("changeset", cs_id).data["ops"][0]["label"]
    title = words(store.read().get("action", action).data)
    assert f"'{title}'" in label and not ID.search(label)
    assert outward.sweep_ids(store, cfg) == 0  # nothing left to do
    line = next(line for line in queue(ws, store, cfg, NOW) if line.kind == "review")
    assert f"'{title}'" in line.subject and not ID.search(line.subject)


def test_the_sweep_never_touches_a_title_that_holds_an_id(env):
    # A title may be the person's own words, and the invariant keeps the assistant from writing an id into one: the
    # sweep re-makes only the app's own labels.
    ws, cfg, store = env
    target = OPEN[0]["id"]
    other = OPEN[1]
    text = f"{words(other)} (after {target})"
    rec = store.read().get("action", other["id"])
    with store.transaction() as tx:
        tx.update("action", other["id"], {"text": text}, _TEST, read_version=rec.version)
    assert outward.sweep_ids(store, cfg) == 0
    assert store.read().get("action", other["id"]).data["text"] == text
