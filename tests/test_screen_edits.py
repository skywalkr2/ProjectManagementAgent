"""Edits made on the People & projects screens go through the applier as `record.edit`, so every check and every
running plugin's validators see them (plugin round 34, question 171). Names come from the fixture."""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "test-token-value"


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store


def edits(store, kind: str, record_id: str) -> list[dict]:
    found = []
    for cs in store.read().list("changeset"):
        for outcome in cs.data["ops"]:
            op = outcome["op"]
            if op.get("op") == "record.edit" and op["record"] == {"kind": kind, "id": record_id}:
                found.append(outcome)
    return found


@pytest.mark.parametrize(
    ("kind", "route", "field"),
    [("project", "projects", "summary"), ("person", "people", "role"), ("organization", "organizations", "notes")],
)
def test_a_screen_edit_is_a_record_edit_through_the_applier(api, kind, route, field):
    client, store = api
    record = store.read().list(kind)[0]
    r = client.post(f"/api/{route}/{record.id}", json={field: "Changed on the screen"})
    assert r.status_code == 200, r.text
    assert store.read().get(kind, record.id).data[field] == "Changed on the screen"
    made = edits(store, kind, record.id)
    assert len(made) == 1 and made[0]["status"] == "applied"


def test_a_screen_edit_the_applier_refuses_changes_nothing(api):
    client, store = api
    project = store.read().list("project")[0]
    r = client.post(f"/api/projects/{project.id}", json={"target": "not a date"})
    assert r.status_code in (409, 422)
    assert store.read().get("project", project.id).version == project.version
