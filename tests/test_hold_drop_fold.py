"""The assistant can hold and drop, and an unowned action can be added to the nearest one (design 6.8, 6.9, 6.20).

`action.hold` and `action.drop` and the assistant's `question.drop` apply as data with Undo and need evidence; only the
person's own act records a correction. A dropped action is never done, never credited and never chased, and leaves
Today's lines, the to-do list and the follow-ups. Folding declines the held action, logs its words on the target and
records a declined correction, in one change with Undo. Names, ids and texts come from the fixtures.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person, fold_unowned, pick_owner, undo
from engine.corrections import request_change
from engine.dispatcher import process, undo_changeset
from engine.followups import put_on_hold, sections
from engine.intake import hand_in
from engine.names import People
from engine.ops import OP_MODELS, reference_for
from engine.owners import suggest_owner
from engine.packet import _open_actions
from engine.storage import Store, StoreError, WriteContext
from engine.tasks import TASKS
from engine.today import todo
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_corrections import (
    NOW,
    asked_by_a_run,
    decision_op,
    other_of,
    pm_of,
    problems,
    signals,
    unowned_action,
)
from tests.test_knowledge_records import apply, source

_TEST = WriteContext(actor="pm", trust="trusted", op="test.hold-drop-fold")
TOKEN = "hold-drop-fold-token"
RAW = "The printer is waiting on the proof, so drop the photographer idea and forget the old question."
WAITING = "waiting on the proof"
DROPPING = "drop the photographer idea"
ACTIONS = fixture_records(DEMO_B, "action")
OPEN = [a for a in ACTIONS if a.get("status", "open") == "open" and a.get("owners")]
DONE = next(a for a in ACTIONS if a.get("status") == "done")
HELD = next(a for a in ACTIONS if a.get("status") == "held")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def an_action(cfg, *, mine: bool) -> str:
    """The id of a fixture action that is open and owned by the person (or by someone else)."""
    return next(a["id"] for a in OPEN if (a["owners"][0]["person"] == pm_of(cfg)) == mine)


def data(store, kind, record_id) -> dict:
    return store.read().get(kind, record_id).data


def from_input(store, cfg, ops):
    """Apply ops as the assistant does for an input that holds RAW."""
    return apply(store, cfg, ops, origin="input", trust="untrusted", source_id=source(store), raw=RAW)


def hold_op(action_id, waiting="  the printer's   quote ", quote=WAITING):
    return {"op": "action.hold", "id": action_id, "waiting_for": waiting, "evidence": {"quote": quote}}


def drop_op(action_id, reason="  No longer   needed ", quote=DROPPING):
    return {"op": "action.drop", "id": action_id, "reason": reason, "evidence": {"quote": quote}}


def made_by_a_run(env, op, kind):
    """Let the stub answer a handed-in input with this op. Returns the changeset, the run and the record made."""
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"summary": "Filed.", "ops": [op]}))
    handed = hand_in(ws, store, pasted="Notes for the item.", now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    changeset = store.read().get("changeset", cs_id).data
    (outcome,) = changeset["ops"]
    assert outcome["status"] == "applied", outcome
    return cs_id, changeset["run"], next(r["id"] for r in outcome["records"] if r["kind"] == kind)


# ---- action.hold ----------------------------------------------------------------------------------------------------


def test_action_hold_writes_what_the_persons_hold_writes_records_no_signal_and_undo_restores_it(env):
    _, cfg, store = env
    target, person_held = an_action(cfg, mine=False), an_action(cfg, mine=True)
    cs_id, result = from_input(store, cfg, [hold_op(target)])
    assert result == ["applied"]
    hold = data(store, "action", target)["on_hold"]
    assert hold["waiting_for"] == "the printer's quote"
    assert not store.read().has("signal"), "what the assistant applies is its own work, not a correction"
    put_on_hold(store, person_held, "an answer")
    assert (
        set(hold) == set(data(store, "action", person_held)["on_hold"])
        and hold["since"] == (data(store, "action", person_held)["on_hold"]["since"])
    )
    assert undo(store, cs_id).restored == [0]
    assert data(store, "action", target)["on_hold"] is None


def test_hold_and_drop_need_evidence_that_is_in_the_input_and_an_open_action(env):
    _, cfg, store = env
    target = an_action(cfg, mine=False)

    def checks(op, **more):
        return [p.check for p in problems(env, op, **more)]

    for op in (hold_op(target), drop_op(target)):
        without = {k: v for k, v in op.items() if k != "evidence"}
        assert "evidence" in checks(without)  # the assistant gives the words
        assert "evidence" not in checks(without, actor="pm")  # the person's own act needs none
    _, result = from_input(
        store, cfg, [hold_op(target, quote="never said anywhere"), drop_op(target, quote="nor this")]
    )
    assert result == ["refused", "refused"]
    assert data(store, "action", target)["on_hold"] is None and data(store, "action", target)["status"] == "open"
    for op in (
        {"op": "action.hold", "id": DONE["id"], "waiting_for": "x"},
        {"op": "action.drop", "id": DONE["id"], "reason": "x"},
    ):
        assert any("already done" in p.message for p in problems(env, op, "targets", actor="pm"))
    for op in (
        {"op": "action.hold", "id": HELD["id"], "waiting_for": "x"},
        {"op": "action.drop", "id": HELD["id"], "reason": "x"},
    ):
        assert any("waiting for an owner" in p.message for p in problems(env, op, "targets", actor="pm"))
    for op in (
        {"op": "action.hold", "id": "ACT-999", "waiting_for": "x"},
        {"op": "action.drop", "id": "ACT-999", "reason": "x"},
    ):
        assert any("no action" in p.message for p in problems(env, op, "targets", actor="pm"))


# ---- action.drop ----------------------------------------------------------------------------------------------------


def test_action_drop_is_never_done_or_credited_records_no_signal_and_undo_opens_it_again(env):
    _, cfg, store = env
    target = an_action(cfg, mine=False)
    cs_id, result = from_input(store, cfg, [drop_op(target)])
    assert result == ["applied"]
    gone = data(store, "action", target)
    assert (gone["status"], gone["dropped_reason"]) == ("dropped", "No longer needed")
    assert gone["done_by"] == [] and gone["reported_by"] is None
    assert not store.read().has("signal")
    # It can't be closed afterwards, and the close is refused rather than crediting anyone.
    _, closed = from_input(store, cfg, [{"op": "action.close", "id": target, "evidence": {"quote": WAITING}}])
    assert closed == ["refused"] and data(store, "action", target)["done_by"] == []
    assert undo(store, cs_id).restored == [0]
    back = data(store, "action", target)
    assert (back["status"], back["dropped_reason"]) == ("open", None)


def test_a_dropped_action_leaves_the_to_do_list_the_overdue_line_the_follow_ups_and_the_packets_open_list(env):
    ws, cfg, store = env
    now = datetime.now(UTC)
    mine, theirs = an_action(cfg, mine=True), an_action(cfg, mine=False)
    with store.transaction() as tx:
        for action_id in (mine, theirs):
            current = tx.get("action", action_id)
            due = (now - timedelta(days=4)).date().isoformat()
            tx.update("action", action_id, {"due": due}, _TEST, read_version=current.version)

    def where() -> dict[str, bool]:
        follow = {a["id"] for s in sections(store, cfg, now.date()) for a in s.actions}
        overdue = [line for line in queue(ws, store, cfg, now) if line.kind == "overdue"]
        return {
            "to-do": any(t.action == mine for t in todo(store, cfg, now)),
            "overdue": any(mine in line.actions for line in overdue),
            "follow-ups": theirs in follow or mine in follow,
            "packet": mine in _open_actions(store, People(store, cfg))
            or theirs in _open_actions(store, People(store, cfg)),
        }

    assert all(where().values())
    for action_id in (mine, theirs):
        apply_as_person(store, cfg, [{"op": "action.drop", "id": action_id, "reason": "Not needed"}], "Dropped")
    assert not any(where().values())


# ---- the person's own drop ------------------------------------------------------------------------------------------


def test_the_persons_drop_of_an_action_records_dropped_naming_the_run_that_made_it_and_undo_keeps_the_signal(env):
    _, cfg, store = env
    made = {
        "op": "action.add",
        "text": "Send the proof to the printer",
        "owners": [other_of(cfg)],
        "evidence": {"quote": "Notes for the item."},
    }
    cs_id, run_id, action_id = made_by_a_run(env, made, "action")
    done = apply_as_person(
        store, cfg, [{"op": "action.drop", "id": action_id, "reason": "  Not   needed now "}], "Drop"
    )
    assert data(store, "action", action_id)["status"] == "dropped"
    (signal,) = signals(store, "dropped")
    assert signal["refs"] == [action_id] and signal["changeset"] == cs_id and signal["run"] == run_id
    assert signal["note"] == "Not needed now"
    undo_changeset(store, done)
    assert data(store, "action", action_id)["status"] == "open"
    assert len(signals(store, "dropped")) == 1 and not signals(store, "undone"), (
        "taking back their own act teaches nothing"
    )
    # An action no run made names no changeset or run.
    other = an_action(cfg, mine=False)
    apply_as_person(store, cfg, [{"op": "action.drop", "id": other, "reason": "Not needed"}], "Drop")
    last = signals(store, "dropped")[-1]
    assert last["refs"] == [other] and last["changeset"] is None and last["run"] is None


def test_the_assistants_question_drop_needs_evidence_and_records_no_signal_while_the_persons_still_does(env):
    _, cfg, store = env
    _, _, mine = asked_by_a_run(env, decision_op(cfg))
    _, theirs_run, other = asked_by_a_run(env, decision_op(cfg, title="Which paper for the jacket?"))
    drop = {"op": "question.drop", "id": mine, "reason": "The input says it is settled."}
    _, refused = from_input(store, cfg, [drop])
    assert refused == ["refused"] and data(store, "question", mine)["status"] == "open"
    cs_id, applied = from_input(store, cfg, [{**drop, "evidence": {"quote": "forget the old question"}}])
    assert applied == ["applied"]
    assert (data(store, "question", mine)["status"], data(store, "question", mine)["dropped_reason"]) == (
        "dropped",
        "The input says it is settled.",
    )
    assert not signals(store, "dropped")
    assert undo(store, cs_id).restored == [0] and data(store, "question", mine)["status"] == "open"
    apply_as_person(store, cfg, [{"op": "question.drop", "id": other, "reason": "Not needed"}], "Drop")
    (signal,) = signals(store, "dropped")
    assert signal["refs"] == [other] and signal["run"] == theirs_run


# ---- reading notes --------------------------------------------------------------------------------------------------


def test_reading_notes_is_offered_the_three_ops_and_a_change_this_note_for_a_hold_is_done_not_refused(env):
    ws, cfg, store = env
    three = {"action.hold", "action.drop", "question.drop"}
    assert three <= set(TASKS["notes"].ops) and three <= set(OP_MODELS)
    listed = reference_for(list(TASKS["notes"].ops))
    assert all(f'- "{name}":' in listed for name in three)
    prompt = (Path(__file__).parent.parent / "engine" / "prompts" / "notes.md").read_text(encoding="utf-8")
    assert all(f'"{name}"' in prompt for name in three) and "an op to put an action on hold" not in prompt
    target = an_action(cfg, mine=True)
    note = "Put it on hold until the proof is back"
    request, _ = request_change(ws, store, cfg, "action", target, note)
    set_responder(
        lambda task: json.dumps(
            {
                "summary": "Put it on hold.",
                "ops": [hold_op(target, waiting="the proof coming back", quote="until the proof is back")],
            }
        )
    )
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "applied", outcome
    assert data(store, "action", target)["on_hold"]["waiting_for"] == "the proof coming back"


# ---- folding an unowned action into the nearest ---------------------------------------------------------------------

NEAR = "Confirm printer slot for hardcover run"


def with_a_near_action(env):
    """A near-duplicate open action, then an unowned one. Returns the near action, the held action, the question and the
    changeset that made them."""
    _, cfg, store = env
    with store.transaction() as tx:
        near = tx.create(
            "action",
            {"text": NEAR, "owners": [{"person": other_of(cfg)}], "notes": "Asked on the phone."},
            _TEST,
        ).id
    held, question = unowned_action(store, cfg)
    return near, held, question, data(store, "question", question)["resolves"]["changeset"]


def test_folding_declines_the_held_action_logs_it_on_the_target_records_held_declined_and_undo_restores_both(env):
    ws, cfg, store = env
    near, held, question, cs_id = with_a_near_action(env)
    suggestion = suggest_owner(store.read(), cfg, held)
    assert suggestion.fold_into == near and suggestion.fold_version == store.read().get("action", near).version
    folded = fold_unowned(store, cfg, cs_id, 0, near, suggestion.fold_version)
    gone = data(store, "action", held)
    assert gone["status"] == "dropped" and NEAR in gone["dropped_reason"] and not gone["owners"]
    target = data(store, "action", near)
    assert target["notes"].startswith("Asked on the phone.\n") and gone["text"] in target["notes"]
    assert gone["evidence"]["quote"] in target["notes"]
    assert data(store, "question", question)["status"] == "dropped"
    assert not [line for line in queue(ws, store, cfg, NOW) if line.kind == "owner"]
    (signal,) = signals(store, "held_declined")
    assert signal["refs"] == [cs_id, held, near] and signal["changeset"] == cs_id and near in signal["note"]
    assert store.read().get("changeset", folded).data["status"] == "applied"
    assert undo(store, folded).restored == [0]
    assert data(store, "action", held)["status"] == "held" and data(store, "action", held)["dropped_reason"] is None
    assert data(store, "action", near)["notes"] == "Asked on the phone."
    assert data(store, "question", question)["status"] == "open"
    assert [line.question for line in queue(ws, store, cfg, NOW) if line.kind == "owner"] == [question]
    assert len(signals(store, "held_declined")) == 1, "taking back their own choice teaches nothing"


def test_folding_is_refused_for_a_target_that_changed_is_closed_or_is_the_action_itself_or_one_that_has_an_owner(env):
    _, cfg, store = env
    near, held, question, cs_id = with_a_near_action(env)
    version = store.read().get("action", near).version
    with store.transaction() as tx:
        current = tx.get("action", near)
        tx.update("action", near, {"notes": "Changed since."}, _TEST, read_version=current.version)
    with pytest.raises(StoreError, match="changed since"):
        fold_unowned(store, cfg, cs_id, 0, near, version)
    with pytest.raises(StoreError, match="no other action"):
        fold_unowned(store, cfg, cs_id, 0, held, 1)
    with pytest.raises(StoreError, match="no other action"):
        fold_unowned(store, cfg, cs_id, 0, "ACT-999", 1)
    with pytest.raises(StoreError, match="isn't an action waiting"):
        fold_unowned(store, cfg, cs_id, 5, near, version)
    with store.transaction() as tx:
        current = tx.get("action", near)
        tx.update("action", near, {"status": "done", "done_by": [other_of(cfg)]}, _TEST, read_version=current.version)
    with pytest.raises(StoreError, match="isn't open"):
        fold_unowned(store, cfg, cs_id, 0, near, store.read().get("action", near).version)
    assert data(store, "action", held)["status"] == "held" and not signals(store, "held_declined")
    with store.transaction() as tx:
        current = tx.get("action", near)
        tx.update("action", near, {"status": "open", "done_by": []}, _TEST, read_version=current.version)
    pick_owner(store, question, other_of(cfg))
    with pytest.raises(StoreError, match="waiting for an owner any more"):
        fold_unowned(store, cfg, cs_id, 0, near, store.read().get("action", near).version)


# ---- the routes -----------------------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def test_the_drop_route_applies_the_persons_drop_with_undo_and_a_dropped_action_cannot_be_marked_done(api):
    client, store, cfg = api
    target = an_action(cfg, mine=False)
    done = client.post(f"/api/actions/{target}/drop", json={"reason": "No longer needed"})
    assert done.status_code == 200
    assert data(store, "action", target)["status"] == "dropped"
    assert client.post(f"/api/actions/{target}/status", json={"status": "done"}).status_code == 409
    assert client.post(f"/api/actions/{target}/drop", json={"reason": "again"}).status_code == 409
    assert client.post(f"/api/actions/{target}/drop", json={"reason": ""}).status_code == 422
    assert client.post("/api/actions/ACT-999/drop", json={"reason": "x"}).status_code == 404
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert data(store, "action", target)["status"] == "open"


def test_the_fold_route_folds_with_undo_and_the_held_item_carries_the_action_to_add_it_to(api):
    client, store, cfg = api
    with store.transaction() as tx:
        near = tx.create("action", {"text": NEAR, "owners": [{"person": other_of(cfg)}]}, _TEST).id
    held, question = unowned_action(store, cfg)
    cs_id = data(store, "question", question)["resolves"]["changeset"]
    version = store.read().get("action", near).version
    shown = next(line for line in client.get("/api/today/queue").json() if line["kind"] == "owner")
    assert shown["suggestion"]["fold_into"] == near and shown["suggestion"]["fold_version"] == version
    stale = client.post(f"/api/changesets/{cs_id}/ops/0/fold", json={"into": near, "read_version": version + 1})
    assert stale.status_code == 409 and "changed since" in stale.json()["detail"]
    done = client.post(f"/api/changesets/{cs_id}/ops/0/fold", json={"into": near, "read_version": version})
    assert done.status_code == 200 and data(store, "action", held)["status"] == "dropped"
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert data(store, "action", held)["status"] == "held"


def test_every_correction_the_person_makes_here_queues_what_the_assistant_learns_from_it(env):
    from engine.learn import learn_request

    _, cfg, store = env
    made = {
        "op": "action.add",
        "text": "Book the caterer",
        "owners": [other_of(cfg)],
        "evidence": {"quote": "Notes for the item."},
    }
    _, _, action_id = made_by_a_run(env, made, "action")
    apply_as_person(store, cfg, [{"op": "action.drop", "id": action_id, "reason": "Not needed"}], "Drop")
    _, _, mine = asked_by_a_run(env, decision_op(cfg))
    apply_as_person(store, cfg, [{"op": "question.update", "id": mine, "text": "Which room do we book?"}], "Reword")
    near, _, _, cs_id = with_a_near_action(env)
    fold_unowned(store, cfg, cs_id, 0, near, store.read().get("action", near).version)
    view = store.read()
    for kind in ("dropped", "reworded", "held_declined"):
        (signal,) = [s for s in view.list("signal") if s.data["kind"] == kind]
        assert learn_request(view, signal.id) is not None, f"a {kind} correction queued no learning"


def test_signals_are_written_only_through_the_one_place_that_queues_their_learning():
    import re

    root = Path(__file__).resolve().parents[1]
    writes = re.compile(r'create\(\s*"signal"')
    writers = sorted(
        str(path.relative_to(root))
        for folder in ("engine", "api")
        for path in (root / folder).rglob("*.py")
        if writes.search(path.read_text(encoding="utf-8"))
    )
    assert writers == ["engine/learn.py"], writers


def test_the_persons_edit_of_what_the_assistant_set_is_an_edited_correction_that_queues_learning(env):
    from engine.learn import learn_request

    _, cfg, store = env
    made = {
        "op": "action.add",
        "text": "Book the caterer",
        "owners": [other_of(cfg)],
        "evidence": {"quote": "Notes for the item."},
    }
    cs_id, run_id, action_id = made_by_a_run(env, made, "action")
    apply_as_person(
        store,
        cfg,
        [
            {
                "op": "record.set",
                "kind": "action",
                "id": action_id,
                "field": "text",
                "value": "Book the caterer for Friday",
            }
        ],
        "Edit",
    )
    (signal,) = signals(store, "edited")
    assert signal["refs"] == [action_id] and signal["changeset"] == cs_id and signal["run"] == run_id
    assert "Book the caterer" in signal["note"] and "for Friday" in signal["note"]
    view = store.read()
    edited = next(s for s in view.list("signal") if s.data["kind"] == "edited")
    assert learn_request(view, edited.id) is not None
    # An edit of what the person set, or a second edit of a field the person already changed, corrects nothing.
    apply_as_person(
        store,
        cfg,
        [
            {
                "op": "record.set",
                "kind": "action",
                "id": action_id,
                "field": "text",
                "value": "Book the caterer for Saturday",
            }
        ],
        "Edit",
    )
    assert len(signals(store, "edited")) == 1
