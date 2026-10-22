"""An action's project (with the project it is part of) and notes reach the Follow-ups ask and Today's line about it,
and a Waiting on them ask carries what Reassign needs (design 7.5, 7.7, roadmap B-6a). Names and ids come from the
fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "action-row-details-token"
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.action-row-details")
PEOPLE = fixture_records(DEMO_B, "person")
OTHER = PEOPLE[1]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]
NOTES = "Ask about the paper too"


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(
        env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"},
        flags={"server.base_path": "/", "storage.backups.automatic": False},
    )
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.store = app.state.store
        client.cfg = cfg
        app.state.worker.now = lambda: NOW
        yield client
    set_responder(None)


def in_a_series(store) -> str:
    """Put the fixture project inside a project of its own and return the outer one's name."""
    with store.transaction() as tx:
        outer = tx.create("project", {"name": "The whole list", "status": "On track"}, _TEST)
        rec = tx.get("project", PROJECT["id"])
        tx.update("project", PROJECT["id"], {"parent": outer.id}, _TEST, read_version=rec.version)
    return "The whole list"


def an_action(api, **more) -> str:
    data = {"text": "Ring the printer", "project": PROJECT["id"], "notes": NOTES, **more}
    with api.store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def test_a_follow_ups_ask_carries_its_parent_project_notes_and_what_reassign_needs(api):
    parent = in_a_series(api.store)
    told = (NOW - timedelta(days=3)).date().isoformat()
    action = an_action(api, owners=[{"person": OTHER}], told={OTHER: told})
    section = next(s for s in api.get("/api/followups").json() if s["person"] == OTHER)
    ask = next(a for a in section["actions"] if a["id"] == action)
    assert (ask["project_name"], ask["parent_name"], ask["notes"]) == (PROJECT["name"], parent, NOTES)
    assert ask["version"] == api.store.read().get("action", action).version
    assert [o["person"] for o in ask["owners"]] == [OTHER] and ask["owners"][0]["name"]


def test_an_ask_with_no_parent_or_notes_says_none(api):
    action = an_action(api, owners=[{"person": OTHER}], notes=None)
    section = next(s for s in api.get("/api/followups").json() if s["person"] == OTHER)
    ask = next(a for a in section["actions"] if a["id"] == action)
    assert (ask["parent_name"], ask["notes"]) == (None, None)


def test_todays_line_about_one_action_carries_its_parent_project_and_notes(api):
    parent = in_a_series(api.store)
    action = an_action(
        api,
        owners=[{"person": api.cfg.workspace.user.person}],
        remind_at=(NOW - timedelta(minutes=1)).isoformat(),
    )
    (line,) = [x for x in api.get("/api/today/queue").json() if x["kind"] == "reminder"]
    assert line["actions"] == [action]
    assert (line["project_name"], line["parent_name"], line["notes"]) == (PROJECT["name"], parent, NOTES)
