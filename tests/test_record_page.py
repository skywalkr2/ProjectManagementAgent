"""A record's page and the tables' counts (design 7.14): names, never ids; what is open; what happened."""

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "test-token-value"


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        c = next(c for c in load_cases(DEMO_B) if c["id"] == "production-checkin")
        set_responder(lambda task: json.dumps(c["stub_answer"]))
        client.post("/api/handin", json={"pasted": c["pasted"]})
        app.state.worker.run_pending()
        yield client, app.state.store
    set_responder(None)


def test_a_person_page_resolves_names_and_lists_what_is_open_with_them(api):
    client, store = api
    person = next(p for p in store.read().list("person") if p.data.get("org"))
    org = store.read().get("organization", person.data["org"])
    page = client.get(f"/api/record-pages/{person.id}", params={"kind": "person"}).json()
    assert page["name"] == person.data["full_name"]
    org_detail = next(d for d in page["details"] if d["field"] == "org")
    assert org_detail["refs"] == [{"kind": "organization", "id": org.id, "name": org.data["name"]}]
    assert all(d["field"] not in ("full_name", "aliases") for d in page["details"])


def test_a_project_page_shows_its_open_actions_and_activity(api):
    client, store = api
    action = next(a for a in store.read().list("action") if a.data.get("project"))
    project = action.data["project"]
    page = client.get(f"/api/record-pages/{project}", params={"kind": "project"}).json()
    assert action.id in [a["id"] for a in page["open_actions"]]
    opened = next(a for a in page["open_actions"] if a["id"] == action.id)
    assert opened["owners"] and all(not o.startswith("PER-") for o in opened["owners"])
    assert any(e["kind"] == "action" and e["by_assistant"] for e in page["activity"])
    rows = {p["id"]: p for p in client.get("/api/projects").json()}
    assert rows[project]["open_actions"] >= 1


def test_people_rows_count_open_items(api):
    client, store = api
    rows = client.get("/api/people").json()
    owner = store.read().list("action")[0].data["owners"][0]["person"]
    assert next(r for r in rows if r["id"] == owner)["open_items"] >= 1


def test_an_unknown_record_has_no_page(api):
    client, _ = api
    assert client.get("/api/record-pages/PER-999", params={"kind": "person"}).status_code == 404


def test_the_owner_format_applies_to_the_owners_on_the_review_screen_and_the_record_page(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    flags = {
        "server.base_path": "/",
        "storage.backups.automatic": False,
        "workspace.owner_format": "{full_name} of {team}",
    }
    app = create_app(ws, ws.config(env={}, flags=flags), TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        c = next(c for c in load_cases(DEMO_B) if c["id"] == "production-checkin")
        set_responder(lambda task: json.dumps(c["stub_answer"]))
        client.post("/api/handin", json={"pasted": c["pasted"]})
        app.state.worker.run_pending()
        store = app.state.store
        teams = {t.id: t.data["name"] for t in store.read().list("team")}
        people = {p.id: p.data for p in store.read().list("person")}
        owned = {
            o["person"]: f"{people[o['person']]['full_name']} of {teams[people[o['person']]['team']]}"
            for a in store.read().list("action")
            for o in a.data.get("owners", [])
            if people[o["person"]].get("team") in teams
        }
        shown = {
            owner
            for item in client.get("/api/changes").json()
            for op in (item.get("changeset") or {}).get("ops", [])
            for owner in op["meta"].get("owners") or []
        }
        assert owned and shown & set(owned.values()), "an owner with a team is written in the workspace's format"
        action = next(a for a in store.read().list("action") if a.data.get("project") and a.data.get("owners"))
        page = client.get(f"/api/record-pages/{action.data['project']}", params={"kind": "project"}).json()
        listed = next(a for a in page["open_actions"] if a["id"] == action.id)["owners"]
        person = people[action.data["owners"][0]["person"]]
        expected = (
            f"{person['full_name']} of {teams[person['team']]}" if person.get("team") in teams else person["full_name"]
        )
        assert listed[0] == expected
    set_responder(None)
