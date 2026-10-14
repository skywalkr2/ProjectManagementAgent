"""Where an item came from (design 7.5): an action, a question or a decision carries one origin for its link, decided
on the server in the order the page, then the saved text, then the change and its request.

Names, ids and addresses come from the fixtures.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.origin import origins
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records, without_first_go

TOKEN = "origin-token"
PAGE = fixture_records(DEMO_B, "project")[0]["links"][0]["url"]
_TEST = WriteContext(actor="pm", trust="trusted", op="test.origin")


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg
    set_responder(None)


def handed_in(client, store) -> None:
    """A hand-in the assistant turned into actions and questions, the way the journeys do."""
    c = next(c for c in load_cases(DEMO_B) if c["id"] == "production-checkin")
    set_responder(lambda task: json.dumps(c["stub_answer"]))
    client.post("/api/handin", json={"pasted": c["pasted"]})
    client.app.state.worker.run_pending()


def new_source(store, **fields) -> str:
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": "2026-01-01T00:00:00+00:00",
                "kind": "pasted",
                "title": "An input",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                **fields,
            },
            _TEST,
        ).id


def new_action(store, **fields) -> str:
    owner = fixture_records(DEMO_B, "person")[0]["id"]
    with store.transaction() as tx:
        return tx.create("action", {"text": "Check the proof", "owners": [{"person": owner}], **fields}, _TEST).id


def new_question(store, **fields) -> str:
    to = fixture_records(DEMO_B, "person")[0]["id"]
    with store.transaction() as tx:
        return tx.create("question", {"to": to, "title": "Which printer?", "kind": "decision", **fields}, _TEST).id


def followup_action(client, action: str) -> dict:
    return next(a for s in client.get("/api/followups").json() for a in s["actions"] if a["id"] == action)


def followup_question(client, question: str) -> dict:
    return next(q for s in client.get("/api/followups").json() for q in s["questions"] if q["id"] == question)


# ---- the three cases -------------------------------------------------------------------------------------------------


def test_an_input_with_an_address_opens_the_page(api):
    client, store, _ = api
    src = new_source(store, url=PAGE)
    action = new_action(store, source=src)
    question = new_question(store, source=src)
    expected = {"kind": "link", "url": PAGE, "source": src, "changeset": None, "request": None}
    assert followup_action(client, action)["origin"] == expected
    assert followup_question(client, question)["origin"] == expected
    assert client.get("/api/record", params={"kind": "action", "id": action}).json()["origin"] == expected


def test_an_input_with_no_address_opens_its_saved_text(api):
    client, store, _ = api
    handed_in(client, store)
    action = next(a for a in store.read().list("action") if a.data.get("source"))
    src = action.data["source"]
    expected = {"kind": "source", "url": None, "source": src, "changeset": None, "request": None}
    assert followup_action(client, action.id)["origin"] == expected
    assert client.get("/api/record", params={"kind": "action", "id": action.id}).json()["origin"] == expected
    # An address a browser can't open as a page is not offered as one.
    odd = new_source(store, url="file:///elsewhere")
    assert followup_action(client, new_action(store, source=odd))["origin"]["kind"] == "source"
    # The saved text is the view the link opens.
    assert client.get(f"/api/sources/{src}").json()["id"] == src


def test_an_item_with_no_input_opens_the_change_and_the_request_behind_it(api):
    client, store, _ = api
    handed_in(client, store)
    action = next(a for a in store.read().list("action") if a.data.get("source"))
    # The input is gone (never kept, or cleared by retention): the change that made the action is what is left.
    with store.transaction() as tx:
        tx.update("action", action.id, {"source": None}, _TEST, read_version=action.version)
    first = store.read().ledger(kind="action", record_id=action.id)[0]
    assert first["changeset"] and first["request"]
    assert followup_action(client, action.id)["origin"] == {
        "kind": "change",
        "url": None,
        "source": None,
        "changeset": first["changeset"],
        "request": first["request"],
    }
    # The request behind it is one What changed lists, so the link has a row to open.
    listed = {c["id"]: c for c in client.get("/api/changes").json()}
    assert listed[first["request"]]["changeset"]["id"] == first["changeset"]


def test_an_item_nothing_reaches_has_no_origin(api):
    client, store, _ = api
    imported = fixture_records(DEMO_B, "action")[0]["id"]
    assert origins(store.read(), "action", [imported]) == {imported: None}
    assert client.get("/api/record", params={"kind": "action", "id": imported}).json()["origin"] is None
    # Other records carry none.
    person = fixture_records(DEMO_B, "person")[0]["id"]
    assert client.get("/api/record", params={"kind": "person", "id": person}).json()["origin"] is None


# ---- where else the rows show ---------------------------------------------------------------------------------------


def test_todays_own_actions_and_a_record_pages_open_items_carry_the_origin(api):
    client, store, cfg = api
    src = new_source(store, url=PAGE)
    me = cfg.workspace.user.person
    project = fixture_records(DEMO_B, "project")[0]["id"]
    action = new_action(store, source=src, project=project)
    with store.transaction() as tx:
        cur = tx.get("action", action)
        tx.update("action", action, {"owners": [{"person": me}]}, _TEST, read_version=cur.version)
    question = new_question(store, source=src, projects=[project])
    expected = {"kind": "link", "url": PAGE, "source": src, "changeset": None, "request": None}
    todo = next(t for t in client.get("/api/today/todo").json() if t["action"] == action)
    assert todo["origin"] == expected
    page = client.get(f"/api/record-pages/{project}", params={"kind": "project"}).json()
    assert next(a for a in page["open_actions"] if a["id"] == action)["origin"] == expected
    assert next(q for q in page["open_questions"] if q["id"] == question)["origin"] == expected
