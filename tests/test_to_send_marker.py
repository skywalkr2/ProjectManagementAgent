"""An action row says "to send" while its owner hasn't been told about it (design 6.10, 7.3, 7.5): an open action with
an owner other than the person, who was never told it (or was told something since changed), and whom the person
doesn't only watch. It is on the row in What changed and in To-dos and questions; Mark sent takes it away. Names come
from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.followups import actions_to_send, mark_sent
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "to-send-token"
TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
_PM = WriteContext("pm", "trusted", "test")
PEOPLE = [p["id"] for p in fixture_records(DEMO_B, "person")]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def other(cfg) -> str:
    return next(p for p in PEOPLE if p != me(cfg))


def make(store, owner: str, **fields) -> str:
    with store.transaction() as tx:
        return tx.create("action", {"text": "Send the proof", "owners": [{"person": owner}], **fields}, _PM).id


def test_an_open_action_owned_by_someone_else_and_never_told_is_to_send(env):
    _, cfg, store = env
    before = actions_to_send(store, cfg)
    theirs, mine = make(store, other(cfg)), make(store, me(cfg))
    assert actions_to_send(store, cfg) == before | {theirs}
    assert mine not in actions_to_send(store, cfg)


def test_a_closed_action_and_one_held_for_an_owner_are_never_to_send(env):
    _, cfg, store = env
    done = make(store, other(cfg), status="done", done_by=[other(cfg)])
    dropped = make(store, other(cfg), status="dropped", dropped_reason="No longer needed")
    held = make(store, other(cfg), status="held", owners=[])
    assert actions_to_send(store, cfg) & {done, dropped, held} == set()


def test_telling_the_owner_takes_it_away_and_changing_the_words_after_brings_it_back(env):
    _, cfg, store = env
    who = other(cfg)
    action = make(store, who)
    assert action in actions_to_send(store, cfg)
    mark_sent(store, cfg, who, now=NOW)
    assert action not in actions_to_send(store, cfg)
    with store.transaction() as tx:
        current = tx.get("action", action)
        tx.update("action", action, {"text": "Send the corrected proof"}, _PM, read_version=current.version)
    assert action in actions_to_send(store, cfg)


def test_someone_the_person_only_watches_is_never_sent_their_actions(env):
    _, cfg, store = env
    who = other(cfg)
    with store.transaction() as tx:
        current = tx.get("person", who)
        tx.update("person", who, {"stance": "watch"}, _PM, read_version=current.version)
    action = make(store, who)
    assert action not in actions_to_send(store, cfg)


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def test_to_do_rows_carry_the_marker(api):
    client, store, cfg = api
    theirs, mine = make(store, other(cfg)), make(store, me(cfg), text="Review it")
    rows = {a["id"]: a for a in client.get("/api/open-items").json()["actions"]}
    assert rows[theirs]["to_send"] is True and rows[mine]["to_send"] is False


def test_an_action_the_assistant_added_shows_to_send_on_its_row_in_what_changed(api):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET
    from tests.test_knowledge_records import request as make_request

    client, store, cfg = api
    who = other(cfg)
    request_id = make_request(store, "input")
    cs = CHANGESET.validate_python(
        {
            "ops": [
                {
                    "op": "action.add",
                    "text": "Send the proof to the printer",
                    "owners": [who],
                    "evidence": {"quote": "send the proof"},
                }
            ]
        },
        context={"op_models": store.plugins.ops},
    )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request_id, None, "", "Please send the proof to the printer", "untrusted"),
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    with store.transaction() as tx:
        request = tx.get("request", request_id)
        tx.update("request", request_id, {"changeset": cs_id, "state": "review"}, _PM, read_version=request.version)
    changes = client.get("/api/changes").json()
    ops = [o for c in changes if c["changeset"] for o in c["changeset"]["ops"] if o["op"] == "action.add"]
    assert ops and ops[0]["meta"]["to_send"] is True
