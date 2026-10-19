"""A home for unfiled work (design 7.14, open promise P14): what the assistant filed with no project is gathered in one
place, can be filed under a project several at a time with one Undo, and each filing is a correction the assistant
learns from. Names and ids come from the fixtures."""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "test-token-value"
ASSISTANT = WriteContext(actor="assistant", trust="trusted", op="test.file", request="REQ-1")
PERSON = WriteContext(actor="pm", trust="trusted", op="test.own")


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store


def made(store, ctx=ASSISTANT):
    """One of each kind the assistant files, none under a project. Returns their ids by kind."""
    pm = next(p for p in store.read().list("person") if p.data.get("role") == "Editor")
    with store.transaction() as tx:
        note = tx.create("note", {"text": "Printer prefers PDF/X files."}, ctx)
        action = tx.create(
            "action", {"text": "Send the proof to the printer", "owners": [{"person": pm.id}], "status": "open"}, ctx
        )
        question = tx.create("question", {"to": pm.id, "title": "Which trim size?", "status": "open"}, ctx)
        fact = tx.create("fact", {"text": "The trim size is 6 by 9 inches."}, ctx)
    return {"note": note.id, "action": action.id, "question": question.id, "fact": fact.id}


def test_what_the_assistant_filed_with_no_project_is_gathered_in_one_list(api):
    client, store = api
    ids = made(store)
    project = store.read().list("project")[0].id
    with store.transaction() as tx:
        tx.create("note", {"text": "Filed already.", "project": project}, ASSISTANT)
        tx.create("note", {"text": "My own loose note."}, PERSON)
    shown = client.get("/api/unfiled").json()
    assert {(i["kind"], i["id"]) for i in shown["items"]} == {(k, v) for k, v in ids.items()}
    assert shown["count"] == 4
    assert all(i["text"] for i in shown["items"])


def test_an_item_filed_under_a_project_that_was_removed_is_unfiled_again(api):
    client, store = api
    made(store)
    project = store.read().list("project")[0]
    with store.transaction() as tx:
        note = tx.create("note", {"text": "About a project that goes.", "project": project.id}, ASSISTANT)
    assert note.id not in [i["id"] for i in client.get("/api/unfiled").json()["items"]]
    with store.transaction() as tx:
        tx.delete("project", project.id, PERSON, read_version=project.version)
    assert note.id in [i["id"] for i in client.get("/api/unfiled").json()["items"]]


def test_filing_several_at_once_files_each_under_the_project_with_one_undo(api):
    client, store = api
    ids = made(store)
    project = store.read().list("project")[0].id
    body = {"project": project, "items": [{"kind": k, "id": v} for k, v in ids.items()]}
    done = client.post("/api/unfiled/file", json=body)
    assert done.status_code == 200, done.text
    view = store.read()
    assert view.get("note", ids["note"]).data["project"] == project
    assert view.get("action", ids["action"]).data["project"] == project
    assert view.get("question", ids["question"]).data["projects"] == [project]
    assert view.get("fact", ids["fact"]).data["project"] == project
    assert client.get("/api/unfiled").json()["count"] == 0
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert client.get("/api/unfiled").json()["count"] == 4


def test_each_filing_records_the_project_as_a_correction_the_assistant_learns_from(api):
    client, store = api
    ids = made(store)
    project = store.read().list("project")[0].id
    client.post("/api/unfiled/file", json={"project": project, "items": [{"kind": k, "id": v} for k, v in ids.items()]})
    signals = [s.data for s in store.read().list("signal") if s.data["kind"] == "edited"]
    named = {ref for s in signals for ref in s["refs"]}
    assert named == set(ids.values())
    assert all("project" in s["note"] for s in signals)


def test_filing_under_a_project_that_does_not_exist_changes_nothing(api):
    client, store = api
    ids = made(store)
    done = client.post("/api/unfiled/file", json={"project": "PRJ-999", "items": [{"kind": "note", "id": ids["note"]}]})
    assert done.status_code in (404, 409)
    assert client.get("/api/unfiled").json()["count"] == 4


def test_today_has_one_line_for_unfiled_work_only_while_there_is_some(api):
    client, store = api
    assert not [line for line in client.get("/api/today/queue").json() if line["kind"] == "unfiled"]
    ids = made(store)
    line = next(line for line in client.get("/api/today/queue").json() if line["kind"] == "unfiled")
    assert line["count"] == 4 and line["group"] == "review"
    project = store.read().list("project")[0].id
    client.post("/api/unfiled/file", json={"project": project, "items": [{"kind": k, "id": v} for k, v in ids.items()]})
    assert not [line for line in client.get("/api/today/queue").json() if line["kind"] == "unfiled"]


def test_filing_an_item_whose_project_changed_since_the_person_saw_it_is_refused_and_nothing_is_filed(api):
    client, store = api
    ids = made(store)
    with store.transaction() as tx:
        other = tx.create("project", {"name": "Another project"}, PERSON).id
    projects = [store.read().list("project")[0].id, other]
    action = store.read().get("action", ids["action"])
    with store.transaction() as tx:
        tx.update("action", action.id, {"project": projects[1]}, PERSON, read_version=action.version)
    body = {
        "project": projects[0],
        "items": [
            {"kind": "note", "id": ids["note"]},
            {"kind": "action", "id": action.id, "read_version": action.version},
        ],
    }
    refused = client.post("/api/unfiled/file", json=body)
    assert refused.status_code == 409
    assert store.read().get("action", action.id).data["project"] == projects[1]
    assert store.read().get("note", ids["note"]).data.get("project") is None, "one change: all of it or none of it"
