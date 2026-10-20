"""`event.set` (design 6.7, follow-on changes; roadmap L7): the assistant moves a calendar entry's start or end
from an input. A data op that needs the quoted words, with Undo; offered to reading notes; its move starts the
follow-on run like the person's own edit. Names and ids come from the fixtures; the AI is the stub."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from engine import follow_on
from engine.ai.adapters.stub import set_responder
from engine.applier import Context, Inputs, apply_changeset, check
from engine.dispatcher import undo_changeset
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, TIERS
from engine.packet import _calendar_section
from engine.storage import Store, WriteContext
from engine.tasks import TASKS
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_knowledge_records import request as make_request

_PM = WriteContext("pm", "trusted", "test")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
OLD_START, OLD_END = "2026-11-16T14:00:00+00:00", "2026-11-16T15:00:00+00:00"
NEW_START, NEW_END = "2026-11-17T15:00:00+00:00", "2026-11-17T16:00:00+00:00"
QUOTE = "has moved to Tuesday, November 17, 3:00 pm to 4:00 pm UTC"
RAW = f"The walkthrough {QUOTE}, still at the shop."


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def entry(store, **more) -> str:
    fields = {"title": "Walkthrough", "start": OLD_START, "end": OLD_END, "project": PROJECT, "trust": "trusted"}
    with store.transaction() as tx:
        return tx.create("event", {**fields, **more}, _PM).id


def set_op(entry_id, **more) -> dict:
    return {"op": "event.set", "id": entry_id, "start": NEW_START, "end": NEW_END, "evidence": {"quote": QUOTE}, **more}


def context(env, raw=RAW, trust="untrusted"):
    _, cfg, store = env
    return Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(make_request(store, "input", task="notes"), None, "", raw, trust),
    )


def apply(env, ops, **kw) -> tuple[str, list[str]]:
    _, _, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    cs_id = apply_changeset(cs, [], context(env, **kw), run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def refusals(env, op) -> list[str]:
    _, _, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    return [p.message for p in check(cs, context(env)) if p.severity == "refuse"]


def follow_ons(store) -> list:
    return [r for r in store.read().list("request") if r.data["task"] == follow_on.TASK]


def test_event_set_is_a_data_op_that_needs_evidence_and_names_what_moves():
    assert TIERS["event.set"] == "data"
    model = OP_MODELS["event.set"]
    assert model.model_fields["evidence"].is_required()
    op = model.model_validate(
        {"op": "event.set", "id": "EVT-1", "start": "2026-11-17T15:00Z", "evidence": {"quote": QUOTE}}
    )
    assert op.start == NEW_START and op.end is None
    assert NEW_START in op.describe() and "EVT-1" not in op.describe()  # named by title where a view is given
    with pytest.raises(ValidationError, match="new start, the new end or both"):
        model.model_validate({"op": "event.set", "id": "EVT-1", "evidence": {"quote": QUOTE}})
    with pytest.raises(ValidationError):
        model.model_validate({"op": "event.set", "id": "EVT-1", "start": "next week", "evidence": {"quote": QUOTE}})


def test_reading_notes_is_offered_event_set_and_the_follow_on_run_is_not():
    assert "event.set" in TASKS["notes"].ops
    assert "event.set" not in TASKS["follow-on"].ops


def test_the_assistant_moves_an_entrys_start_and_end_and_undo_puts_them_back(env):
    _, _, store = env
    found = entry(store)
    cs_id, statuses = apply(env, [set_op(found)])
    assert statuses == ["applied"]
    data = store.read().get("event", found).data
    assert (data["start"], data["end"], data["project"]) == (NEW_START, NEW_END, PROJECT)
    ledger = [r for r in store.read().changes_of(cs_id) if r["kind"] == "event"]
    assert {r["field"] for r in ledger} == {"start", "end"} and all(r["evidence"]["quote"] == QUOTE for r in ledger)
    report = undo_changeset(store, cs_id)
    assert report.restored == [0]
    data = store.read().get("event", found).data
    assert (data["start"], data["end"]) == (OLD_START, OLD_END)


def test_a_move_of_the_start_alone_leaves_the_end_and_a_move_that_ends_before_it_starts_is_refused(env):
    _, _, store = env
    found = entry(store, end=None)
    _, statuses = apply(env, [set_op(found, end=None)])
    assert statuses == ["applied"]
    assert store.read().get("event", found).data["end"] is None
    ends = entry(store)
    [why] = refusals(env, set_op(ends, end=None))
    assert ends in why
    assert store.read().get("event", ends).data["start"] == OLD_START


def test_a_missing_entry_words_not_in_the_input_and_no_evidence_are_refused(env):
    _, _, store = env
    found = entry(store)
    assert any("there is no calendar entry" in why for why in refusals(env, set_op("EVT-999")))
    assert any("isn't in the input" in why for why in refusals(env, set_op(found, evidence={"quote": "not said"})))
    bare = {k: v for k, v in set_op(found).items() if k != "evidence"}
    with pytest.raises(ValidationError):
        CHANGESET.validate_python({"ops": [bare]}, context={"op_models": store.plugins.ops})


def test_the_assistants_move_from_an_input_queues_one_follow_on_request_for_the_save(env):
    _, _, store = env
    found = entry(store)
    cs_id, statuses = apply(env, [set_op(found)])
    assert statuses == ["applied"]
    (queued,) = follow_ons(store)
    assert queued.data["follows"] == cs_id and queued.data["about"] == {"kind": "event", "id": found}
    moves = follow_on.moves_of(store.read(), cs_id)
    assert {(m.field, m.before, m.after) for m in moves} == {
        ("start", OLD_START, NEW_START),
        ("end", OLD_END, NEW_END),
    }
    undo_changeset(store, cs_id)
    assert follow_ons(store) == [queued]  # the undo is not a move


def test_a_refused_move_changes_nothing_and_queues_nothing(env):
    _, _, store = env
    found = entry(store)
    _, statuses = apply(env, [set_op(found, evidence={"quote": "not said"})])
    assert statuses == ["refused"]
    assert store.read().get("event", found).data["start"] == OLD_START and follow_ons(store) == []


def test_the_packet_lists_an_entrys_end_with_its_start_so_a_move_can_name_both(env):
    _, cfg, store = env
    found = entry(store)
    section = _calendar_section(store, cfg, date(2026, 10, 14))
    assert f"{found} Walkthrough ({OLD_START} to {OLD_END})" in section


def test_the_notes_prompt_says_a_message_that_moves_an_event_uses_event_set_on_its_entry(env):
    from engine.intake import hand_in
    from engine.packet import build

    ws, cfg, store = env
    handed = hand_in(ws, store, pasted=RAW, now=datetime(2026, 10, 14, 9, 0, tzinfo=UTC))
    built = build(ws, store, cfg, handed.request, date(2026, 10, 14)).task
    assert 'uses "event.set" on that entry\'s id' in built.instructions
    assert 'never a new entry with "event.add"' in built.instructions
    assert '"event.set"' in built.stable


def test_the_golden_case_for_a_moved_meeting_passes_with_its_ideal_answer_and_fails_on_a_second_entry(monkeypatch):
    from tests.test_evaluate_harness import case_of, run_edited

    case = case_of(DEMO_B, "moved-meeting-moves-its-entry")
    assert case["skills"] == ["dates"]
    assert run_edited(monkeypatch, DEMO_B, case["id"]).passed
    [ideal] = case["stub_answer"]["ops"]
    second = {"op": "event.add", "title": "Walkthrough", "start": ideal["start"], "evidence": ideal["evidence"]}
    wrong = run_edited(monkeypatch, DEMO_B, case["id"], stub_answer={"summary": "s", "ops": [second]})
    assert not wrong.passed and wrong.missing
