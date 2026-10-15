"""A question someone asks the person is one action with a drafted reply (design 6.8, 6.22).

The reply is its own text on the action, marked as a draft until the person approves it or writes their own; only the
person approves or rewords it (`action.reply`, with Undo), and rewording a draft the assistant wrote records a
`draft_edited` correction naming the change and run that made it. Names and ids come from the fixtures.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.applier import apply_as_person, undo
from engine.dispatcher import undo_changeset
from engine.ops import OP_MODELS, PERSON_ONLY_OPS, reference_for
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_corrections import other_of, pm_of, problems, signals
from tests.test_hold_drop_fold import data, env, made_by_a_run  # noqa: F401  (env is the shared fixture)

TOKEN = "action-reply-token"
DRAFT = "The proofs ship on the third (a recorded fact gives the date)."
OWN = "Hi, the proofs ship on the third.\nI will confirm the courier."


def reply_op(cfg, **more):
    return {
        "op": "action.add",
        "text": "Tell the shop when the proofs ship",
        "reply": DRAFT,
        "owners": [pm_of(cfg)],
        "evidence": {"quote": "Notes for the item."},
        **more,
    }


def reviewed(store, action_id) -> tuple[str | None, bool]:
    found = data(store, "action", action_id)
    return found["reply"], found["reply_reviewed"]


# ---- the draft ------------------------------------------------------------------------------------------------------


def test_a_reply_the_assistant_drafts_is_kept_on_the_action_as_a_draft_and_an_action_without_one_has_none(env):  # noqa: F811
    _, cfg, store = env
    _, _, drafted = made_by_a_run(env, reply_op(cfg), "action")
    assert reviewed(store, drafted) == (DRAFT, False)
    bare = {k: v for k, v in reply_op(cfg).items() if k != "reply"}
    _, _, plain = made_by_a_run(env, bare, "action")
    assert reviewed(store, plain) == (None, False)


def test_the_op_reference_tells_the_assistant_what_a_reply_is_and_only_the_person_approves_it(env):  # noqa: F811
    _, cfg, store = env
    assert "reply" in OP_MODELS["action.add"].model_fields
    assert "action.reply" in PERSON_ONLY_OPS
    assert "action.reply" not in reference_for(["action.add"])
    approve = {"op": "action.reply", "id": "ACT-1"}
    assert "person-only" in [p.check for p in problems(env, approve, "person-only")]
    assert not problems(env, approve, "person-only", actor="pm")


# ---- approving and rewording ----------------------------------------------------------------------------------------


def test_approving_marks_it_reviewed_as_it_is_with_undo_and_records_no_correction(env):  # noqa: F811
    _, cfg, store = env
    _, _, action_id = made_by_a_run(env, reply_op(cfg), "action")
    done = apply_as_person(store, cfg, [{"op": "action.reply", "id": action_id}], "Approved a reply")
    assert reviewed(store, action_id) == (DRAFT, True)
    assert not signals(store, "draft_edited")
    undo_changeset(store, done)
    assert reviewed(store, action_id) == (DRAFT, False)


def test_rewording_a_draft_keeps_the_persons_words_reviewed_and_records_draft_edited_naming_the_run(env):  # noqa: F811
    _, cfg, store = env
    cs_id, run_id, action_id = made_by_a_run(env, reply_op(cfg), "action")
    done = apply_as_person(store, cfg, [{"op": "action.reply", "id": action_id, "text": f"  {OWN}  "}], "Reworded")
    assert reviewed(store, action_id) == (OWN, True)
    (edited,) = signals(store, "draft_edited")
    assert edited["refs"] == [action_id] and edited["changeset"] == cs_id and edited["run"] == run_id
    assert edited["note"] == OWN
    undo_changeset(store, done)
    assert reviewed(store, action_id) == (DRAFT, False)
    assert len(signals(store, "draft_edited")) == 1, "taking back their own act leaves the correction as it was"


def test_the_same_words_or_a_reply_where_there_was_none_or_a_later_edit_corrects_nothing(env):  # noqa: F811
    _, cfg, store = env
    _, _, action_id = made_by_a_run(env, reply_op(cfg), "action")
    apply_as_person(store, cfg, [{"op": "action.reply", "id": action_id, "text": f" {DRAFT.upper()} "}], "Same")
    assert reviewed(store, action_id) == (DRAFT.upper(), True)
    assert not signals(store, "draft_edited"), "words that differ only in case or spacing are the same words"
    apply_as_person(store, cfg, [{"op": "action.reply", "id": action_id, "text": OWN}], "Later")
    assert not signals(store, "draft_edited"), "a reply already reviewed is the person's own"
    bare = {k: v for k, v in reply_op(cfg).items() if k != "reply"}
    _, _, plain = made_by_a_run(env, bare, "action")
    apply_as_person(store, cfg, [{"op": "action.reply", "id": plain, "text": OWN}], "Written")
    assert reviewed(store, plain) == (OWN, True)
    assert not signals(store, "draft_edited"), "there was no draft to correct"


def test_approving_needs_a_draft_and_a_closed_or_missing_action_takes_neither(env):  # noqa: F811
    _, cfg, store = env
    bare = {k: v for k, v in reply_op(cfg).items() if k != "reply"}
    _, _, plain = made_by_a_run(env, bare, "action")
    _, _, closed = made_by_a_run(env, reply_op(cfg, text="Tell the printer about the proofs"), "action")
    apply_as_person(store, cfg, [{"op": "action.drop", "id": closed, "reason": "Not needed"}], "Drop")
    for target, op in (
        (plain, {"op": "action.reply", "id": plain}),
        (closed, {"op": "action.reply", "id": closed, "text": OWN}),
        ("ACT-999", {"op": "action.reply", "id": "ACT-999"}),
    ):
        refused = problems(env, op, "targets", actor="pm")
        assert [p.severity for p in refused] == ["refuse"], target


def test_undo_through_the_changeset_restores_the_draft_unchanged(env):  # noqa: F811
    _, cfg, store = env
    _, _, action_id = made_by_a_run(env, reply_op(cfg), "action")
    done = apply_as_person(store, cfg, [{"op": "action.reply", "id": action_id, "text": OWN}], "Reworded")
    assert undo(store, done).restored == [0]
    assert reviewed(store, action_id) == (DRAFT, False)


# ---- the route ------------------------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def test_the_reply_route_approves_or_replaces_the_draft_with_undo_and_says_why_when_it_cannot(api):
    client, store, cfg = api
    with store.transaction() as tx:
        from engine.storage import WriteContext

        test = WriteContext(actor="pm", trust="trusted", op="test.reply")
        drafted = tx.create(
            "action", {"text": "Tell the shop", "owners": [{"person": pm_of(cfg)}], "reply": DRAFT}, test
        ).id
        plain = tx.create("action", {"text": "Tell the printer", "owners": [{"person": other_of(cfg)}]}, test).id
    approved = client.post(f"/api/actions/{drafted}/reply", json={})
    assert approved.status_code == 200 and reviewed(store, drafted) == (DRAFT, True)
    assert client.post(f"/api/changesets/{approved.json()['changeset']}/undo", json={}).status_code == 200
    assert reviewed(store, drafted) == (DRAFT, False)
    assert client.post(f"/api/actions/{drafted}/reply", json={"text": OWN}).status_code == 200
    assert reviewed(store, drafted) == (OWN, True)
    assert [s["note"] for s in map(lambda s: s.data, store.read().list("signal"))] == [OWN]
    assert client.post(f"/api/actions/{plain}/reply", json={}).status_code == 409  # nothing to approve
    assert client.post(f"/api/actions/{plain}/reply", json={"text": ""}).status_code == 422
    assert client.post("/api/actions/ACT-999/reply", json={}).status_code == 404
