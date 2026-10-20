"""A record's page and the tables' counts (design 7.14): names, never ids; what is open; what happened."""

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.evaluate import load_cases
from engine.storage import WriteContext
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


def test_a_field_holding_a_records_id_shows_that_records_name_whether_or_not_it_is_declared_a_reference(api):
    client, store = api
    view = store.read()
    person = next(p for p in view.list("person") if p.data.get("team"))
    team = view.get("team", person.data["team"])
    page = client.get(f"/api/record-pages/{person.id}", params={"kind": "person"}).json()
    detail = next(d for d in page["details"] if d["field"] == "team")
    assert detail["refs"] == [{"kind": "team", "id": team.id, "name": team.data["name"]}]
    project = next(p for p in view.list("project") if p.data.get("owner"))
    owner = view.get("person", project.data["owner"])
    page = client.get(f"/api/record-pages/{project.id}", params={"kind": "project"}).json()
    detail = next(d for d in page["details"] if d["field"] == "owner")
    assert detail["refs"] == [{"kind": "person", "id": owner.id, "name": owner.data["full_name"]}]


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


# ---- finished work, a series label and a fact's source (design 7.14) ----------------------------------------------

_PM = WriteContext(actor="pm", trust="trusted", op="test.finish")
ASSISTANT = WriteContext(actor="assistant", trust="trusted", op="test.file")


def _finish(store, action, *, by, reported):
    current = store.read().get("action", action.id)
    with store.transaction() as tx:
        tx.update(
            "action",
            action.id,
            {"status": "done", "done_by": [by], "reported_by": reported},
            _PM,
            read_version=current.version,
        )


def test_finished_work_is_credited_to_who_did_it_and_names_who_reported_it(api):
    client, store = api
    action = next(a for a in store.read().list("action") if a.data.get("project") and a.data.get("owners"))
    people = [p.id for p in store.read().list("person")]
    doer = action.data["owners"][0]["person"]
    reporter = next(p for p in people if p != doer)
    _finish(store, action, by=doer, reported=reporter)
    project = client.get(f"/api/record-pages/{action.data['project']}", params={"kind": "project"}).json()
    done = next(c for c in project["completed_actions"] if c["id"] == action.id)
    names = {p.id: p.data["full_name"] for p in store.read().list("person")}
    assert done["done_by"] == [names[doer]] and done["reported_by"] == names[reporter] and done["done_on"]
    assert action.id not in [a["id"] for a in project["open_actions"]]
    theirs = client.get(f"/api/record-pages/{doer}", params={"kind": "person"}).json()
    assert action.id in [c["id"] for c in theirs["completed_actions"]]
    # The one who only reported it is not credited with the work.
    reporters = client.get(f"/api/record-pages/{reporter}", params={"kind": "person"}).json()
    assert action.id not in [c["id"] for c in reporters["completed_actions"]]


def test_a_project_with_the_configured_done_status_is_marked_completed(api):
    client, store = api
    rows = client.get("/api/projects").json()
    assert not any(r["completed"] for r in rows)
    project = store.read().list("project")[0]
    done = client.get("/api/settings").json()
    wanted = next(i["value"] for i in done["items"] if i["key"] == "workspace.project.completed_status")
    with store.transaction() as tx:
        tx.update("project", project.id, {"status": wanted}, _PM, read_version=project.version)
    rows = {r["id"]: r for r in client.get("/api/projects").json()}
    assert rows[project.id]["completed"] is True
    assert sum(r["completed"] for r in rows.values()) == 1


def test_the_setting_that_names_the_done_status_picks_from_the_projects_status_list(api):
    client, store = api
    item = next(
        i for i in client.get("/api/settings").json()["items"] if i["key"] == "workspace.project.completed_status"
    )
    statuses = next(v for v in store.read().list("value_list") if v.data["name"] == "project-status").data["values"]
    assert item["type"] == "choice" and set(statuses) <= set(item["options"])


def test_an_item_on_a_series_names_the_meeting_it_is_for(api):
    client, store = api
    action = next(a for a in store.read().list("action") if a.data.get("project") and a.data.get("owners"))
    with store.transaction() as tx:
        series = tx.create("series", {"title": "Print sync", "trust": "trusted"}, _PM).id
        event = tx.create(
            "event", {"title": "Print sync", "start": "2030-10-24", "series": series, "trust": "trusted"}, _PM
        ).id
        tx.update("action", action.id, {"series": series, "event": event}, _PM, read_version=action.version)
    page = client.get(f"/api/record-pages/{action.data['project']}", params={"kind": "project"}).json()
    listed = next(a for a in page["open_actions"] if a["id"] == action.id)
    assert (
        listed["series"] == series and listed["series_title"] == "Print sync" and listed["meeting_on"] == "2030-10-24"
    )


def test_a_facts_page_says_who_it_rests_on_and_where_it_came_from(api):
    client, store = api
    people = store.read().list("person")
    said, author = people[0], people[1]
    with store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": "2026-10-09T10:00:00+00:00",
                "kind": "pasted",
                "title": "Production check-in notes",
                "content_hash": "abc",
                "trust": "untrusted",
                "author": author.id,
            },
            _PM,
        ).id
        inferred = tx.create(
            "fact", {"text": "Both spines are in the folder.", "basis": "inferred", "source": source}, _PM
        ).id
        reported = tx.create(
            "fact", {"text": "The proof is approved.", "basis": "said", "said_by": said.id, "source": source}, _PM
        ).id
        own = tx.create("fact", {"text": "The trim size is fixed.", "basis": "person"}, _PM).id

    def label(fact):
        return client.get(f"/api/record-pages/{fact}", params={"kind": "fact"}).json()["fact_source"]

    assert label(inferred)["basis"] == "inferred" and label(inferred)["kind"] == "pasted"
    assert label(inferred)["sender"] == author.data["full_name"]
    assert "Production check-in notes" not in json.dumps(label(inferred)), (
        "the source's own title never reaches the label"
    )
    said_label = label(reported)
    assert said_label["basis"] == "said" and said_label["by"] == said.data["full_name"]
    assert said_label["reported_by"] == author.data["full_name"]
    assert label(own)["basis"] == "person" and label(own)["by"] is None
    assert (
        client.get(f"/api/record-pages/{project_id(store)}", params={"kind": "project"}).json()["fact_source"] is None
    )


def test_the_kind_of_a_facts_source_is_a_word_never_the_sources_own_title(api):
    client, store = api
    author = store.read().list("person")[0]
    with store.transaction() as tx:

        def fact(title, trust):
            source = tx.create(
                "source",
                {
                    "received_at": "2026-10-09T10:00:00+00:00",
                    "kind": "pasted",
                    "title": title,
                    "content_hash": "abc",
                    "trust": trust,
                    "author": author.id,
                },
                _PM,
            ).id
            return tx.create("fact", {"text": f"About {title}.", "basis": "said", "source": source}, _PM).id

        mail, note, pasted = (
            fact(f"From: {author.data['full_name']}", "untrusted"),
            fact("My own words", "trusted"),
            fact("Notes", "untrusted"),
        )

    def label(fact_id):
        return client.get(f"/api/record-pages/{fact_id}", params={"kind": "fact"}).json()["fact_source"]

    assert [label(f)["kind"] for f in (mail, note, pasted)] == ["email", "note", "pasted"]
    assert all("input" not in label(f) for f in (mail, note, pasted))


def project_id(store):
    return store.read().list("project")[0].id


def test_confirming_an_inferred_fact_makes_it_the_persons_own_and_undo_brings_it_back(api):
    client, store = api
    with store.transaction() as tx:
        fact = tx.create("fact", {"text": "Both spines are in the folder.", "basis": "inferred"}, ASSISTANT)
    done = client.post(
        "/api/records/edit", json={"kind": "fact", "id": fact.id, "fields": {"basis": "person"}, "read_version": 1}
    )
    assert done.status_code == 200, done.text
    assert store.read().get("fact", fact.id).data["basis"] == "person"
    page = client.get(f"/api/record-pages/{fact.id}", params={"kind": "fact"}).json()
    assert page["fact_source"]["basis"] == "person"
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert store.read().get("fact", fact.id).data["basis"] == "inferred"


def test_only_confirming_can_change_a_facts_basis(api):
    client, store = api
    with store.transaction() as tx:
        said = tx.create("fact", {"text": "Said by someone.", "basis": "said"}, ASSISTANT)
        fact = tx.create("fact", {"text": "Inferred.", "basis": "inferred"}, ASSISTANT)
    assert (
        client.post(
            "/api/records/edit", json={"kind": "fact", "id": said.id, "fields": {"basis": "person"}, "read_version": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/records/edit", json={"kind": "fact", "id": fact.id, "fields": {"basis": "said"}, "read_version": 1}
        ).status_code
        == 409
    )


def test_what_changed_names_the_people_an_op_gives_by_id_and_a_set_value_that_is_an_id(api):
    from api.routes import _op_view
    from engine.config import load_config
    from engine.names import People

    client, store = api
    view = store.read()
    cfg = None
    people = People(store, load_config(DEMO_B / "config", env={}))
    person = view.list("person")[1]
    project = view.list("project")[0]

    def shown(op):
        return _op_view(
            {"op": op, "index": 0, "status": "applied", "group": "g", "records": []}, store, people, {}, cfg
        ).meta

    assert shown({"op": "question.add", "to": person.id, "title": "Which day?"}).to == person.data["full_name"]
    assert shown({"op": "action.add", "text": "Send the proof", "owners": [person.id]}).owners == [
        person.data["full_name"]
    ]
    value = shown({"op": "record.set", "kind": "project", "id": project.id, "field": "owner", "value": person.id})
    assert value.field == "owner" and value.value == person.data["full_name"]
    plain = shown({"op": "record.set", "kind": "project", "id": project.id, "field": "summary", "value": "Notes"})
    assert plain.value == "Notes"
