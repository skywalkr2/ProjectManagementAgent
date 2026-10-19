"""Records join by id, never by a display name (design 6.32): anything that names a project or person to follow or
filter by holds its id, resolved from the name when the setting is saved, so a rename never detaches it. A rule that
names a record that is gone closes nothing. Names and ids come from the fixtures."""

from __future__ import annotations

from typing import Annotated

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.app import create_app
from engine import references
from engine.config import load_config
from engine.records import RefTo
from engine.rules import active_rules, seed_rules
from engine.settings import SettingsError, fingerprint
from engine.settings import save as save_settings
from engine.stages import covers
from engine.storage import Store, StoreError, WriteContext
from engine.watch import refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_knowledge_records import apply
from tests.test_watch import NOW, fake, make, reread

_TEST = WriteContext(actor="pm", trust="trusted", op="test.join-by-id")
PROJECT = fixture_records(DEMO_B, "project")[0]
PERSON = fixture_records(DEMO_B, "person")[0]
RENAMED = "The Renamed Launch"
NOT_OURS = {"name": "Not ours", "kind": "terms-absent"}


def rename(store, kind, record_id, **changes):
    with store.transaction() as tx:
        current = tx.get(kind, record_id)
        tx.update(kind, record_id, changes, _TEST, read_version=current.version)


def state_of(store, request_id):
    return store.read().get("request", request_id).data


# ---- a rule or watch list that names a record by id follows its rename ---------------------------------------------


def test_a_triage_rule_that_names_a_project_by_id_still_matches_after_the_project_is_renamed(tmp_path):
    def plan(first, second):
        return [{"key": "a", "title": "Plan", "text": f"{first}\n{second}"}]

    items = plan(f"{PROJECT['name']} ships on Friday.", "Lunch at noon.")
    ws, cfg, store = make(tmp_path, [fake(items)], triage=[{**NOT_OURS, "projects": [PROJECT["id"]]}])
    try:
        assert len(refresh(ws, store, cfg, "s", NOW).new) == 1
        rename(store, "project", PROJECT["id"], name=RENAMED)
        cfg, store, kept = reread(tmp_path, ws, store, plan(f"{RENAMED} ships on Monday.", "Lunch at noon."))
        assert state_of(store, kept.changed[0])["state"] == "queued"  # about the project, so not closed as unrelated
        cfg, store, closed = reread(tmp_path, ws, store, plan(f"{RENAMED} ships on Monday.", "Lunch at one."))
        data = state_of(store, closed.changed[0])
        assert data["auto_closed"]["rule"] == "Not ours" and RENAMED.lower() in data["auto_closed"]["reason"]
    finally:
        store.close()


def test_a_triage_rule_that_names_a_person_by_id_follows_the_name_they_go_by_now(tmp_path):
    items = [{"key": "a", "title": "Plan", "text": f"{PERSON['full_name']} will review it."}]
    ws, cfg, store = make(tmp_path, [fake(items)], triage=[{**NOT_OURS, "people": [PERSON["id"]]}])
    try:
        refresh(ws, store, cfg, "s", NOW)
        rename(store, "person", PERSON["id"], full_name="Avery Renamed", aliases=["Av"])
        cfg, store, by_alias = reread(tmp_path, ws, store, [{**items[0], "text": "Av will review it again."}])
        assert state_of(store, by_alias.changed[0])["state"] == "queued"
        cfg, store, by_name = reread(tmp_path, ws, store, [{**items[0], "text": "Avery Renamed signed off."}])
        assert state_of(store, by_name.changed[0])["state"] == "queued"
    finally:
        store.close()


def test_a_rule_that_names_a_record_that_is_gone_closes_nothing(tmp_path):
    items = [{"key": "a", "title": "Plan", "text": "Anything at all."}]
    ws, cfg, store = make(tmp_path, [fake(items)], triage=[{**NOT_OURS, "projects": ["PRJ-9999"]}])
    try:
        refresh(ws, store, cfg, "s", NOW)
        cfg, store, changed = reread(tmp_path, ws, store, [{**items[0], "text": "Something else entirely."}])
        data = state_of(store, changed.changed[0])
        assert data["state"] == "queued" and not data.get("auto_closed")
    finally:
        store.close()


def test_a_rule_that_names_a_source_keeps_matching_when_the_source_is_relabeled(tmp_path):
    items = [{"key": "a", "title": "Plan", "text": "One budget."}]
    rule = {"name": "Spacing", "kind": "cosmetic", "sources": ["s"]}
    ws, cfg, store = make(tmp_path, [fake(items)], triage=[rule])
    try:
        refresh(ws, store, cfg, "s", NOW)
        current = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
        current["sources"][0]["label"] = "A renamed board"
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(current))
        cfg, store, spaced = reread(tmp_path, ws, store, [{**items[0], "text": "One  budget"}])
        assert state_of(store, spaced.changed[0])["auto_closed"]["rule"] == "Spacing"
    finally:
        store.close()


# ---- a name is resolved to an id when the setting is saved ---------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def save_changes(ws, cfg, store, changes, allow=("watch.sources", "watch.triage")):
    return save_settings(
        ws,
        cfg,
        store,
        changes=changes,
        reset=[],
        read_fingerprint=fingerprint(ws.config_dir),
        env={},
        allow=allow,
    )


def test_saving_a_triage_rule_that_names_a_project_or_person_by_name_stores_their_ids(env):
    ws, cfg, store = env
    rule = {**NOT_OURS, "projects": [PROJECT["name"].upper()], "people": [PERSON["full_name"], "PER-2"]}
    save_changes(ws, cfg, store, {"watch.triage": [rule]})
    stored = load_config(ws.config_dir, env={}).watch.triage[0]
    assert stored.projects == [PROJECT["id"]]
    assert stored.people == [PERSON["id"], "PER-2"]


def test_saving_a_rule_that_names_something_the_app_does_not_know_is_refused_and_says_which(env):
    ws, cfg, store = env
    with pytest.raises(SettingsError, match="Nonexistent Project"):
        save_changes(ws, cfg, store, {"watch.triage": [{**NOT_OURS, "projects": ["Nonexistent Project"]}]})
    assert "Nonexistent" not in (ws.config_dir / "watch.yaml").read_text(encoding="utf-8")


def test_saving_a_source_with_a_project_name_stores_the_projects_id(env):
    ws, cfg, store = env
    source = {"id": "notes", "connector": "folder", "settings": {"path": str(ws.root)}, "project": PROJECT["name"]}
    save_changes(ws, cfg, store, {"watch.sources": [source]})
    assert load_config(ws.config_dir, env={}).watch.sources[0].project == PROJECT["id"]


def client_for(ws, cfg):
    app = create_app(ws, cfg, "join-token", ui_dist=ws.root / "no-ui", start_worker=False)
    return TestClient(app, headers={"Authorization": "Bearer join-token"}), cfg.server.base_path.rstrip("/") + "/api"


def test_adding_a_source_through_the_api_with_a_project_name_stores_its_id_and_refuses_an_unknown_one(env):
    ws, cfg, store = env
    store.close()
    client, api = client_for(ws, cfg)
    body = {"connector": "folder", "label": "Notes", "settings": {"path": str(ws.root)}}

    def add(project):
        fp = client.get(f"{api}/settings").json()["fingerprint"]
        return client.post(f"{api}/watch/sources", json={**body, "project": project, "fingerprint": fp})

    refused = add("No such project")
    assert refused.status_code == 400 and "No such project" in refused.text
    done = add(PROJECT["name"])
    assert done.status_code == 200, done.text
    added = next(s for s in load_config(ws.config_dir, env={}).watch.sources if s.label == "Notes")
    assert added.project == PROJECT["id"]


class Watched(BaseModel):
    project: Annotated[str | None, RefTo("project")] = None
    people: list[Annotated[str, RefTo("person")]] = []


def test_a_connectors_settings_that_refer_to_records_are_stored_as_ids(env):
    _, _, store = env
    given = {"project": PROJECT["name"], "people": [PERSON["full_name"], "PER-2"], "other": "kept"}
    found = references.join_settings(Watched, given, store.read())
    assert found == {"project": PROJECT["id"], "people": [PERSON["id"], "PER-2"], "other": "kept"}
    with pytest.raises(StoreError, match="No such"):
        references.join_settings(Watched, {"project": "No such"}, store.read())


# ---- a rule's or lesson's filter on a record's reference holds the id --------------------------------------------


def a_rule(applies_to, text="Check dates before sending."):
    return {"op": "rule.add", "text": text, "applies_to": applies_to}


def test_a_rule_filtering_actions_by_project_name_stores_the_id_and_covers_them_after_a_rename(env):
    _, cfg, store = env
    cs_id, statuses = apply(store, cfg, [a_rule({"records": ["action"], "filter": {"project": PROJECT["name"]}})])
    assert statuses == ["applied"], store.read().get("changeset", cs_id).data["ops"][0]["reason"]
    (rule,) = [r for r in active_rules(store.read()) if r.text == "Check dates before sending."]
    assert rule.applies_to.filter == {"project": PROJECT["id"]}
    rename(store, "project", PROJECT["id"], name=RENAMED)
    action = next(a for a in store.read().list("action") if a.data.get("project") == PROJECT["id"])
    assert covers(rule.applies_to, action)


def test_a_rule_filtering_by_a_project_that_does_not_exist_is_refused(env):
    _, cfg, store = env
    _, statuses = apply(store, cfg, [a_rule({"records": ["action"], "filter": {"project": "No such project"}})])
    assert statuses == ["refused"]


def test_a_filter_on_a_field_that_is_not_a_reference_is_left_as_written(env):
    _, cfg, store = env
    _, statuses = apply(store, cfg, [a_rule({"records": ["action"], "filter": {"status": "open"}})])
    assert statuses == ["applied"]
    assert [r.applies_to.filter for r in active_rules(store.read())] == [{"status": "open"}]


def test_a_lesson_filtering_by_a_person_name_stores_the_id(env):
    _, cfg, store = env
    op = {
        "op": "lesson.add",
        "text": "Ask before closing.",
        "applies_to": {"records": ["question"], "filter": {"to": PERSON["full_name"]}},
    }
    cs_id, statuses = apply(store, cfg, [op])
    assert statuses == ["applied"]
    record = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]
    assert store.read().get(record["kind"], record["id"]).data["applies_to"]["filter"] == {"to": PERSON["id"]}


def test_a_starting_rule_in_the_rules_file_that_filters_by_name_is_seeded_with_the_id(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    rules = {
        "version": 1,
        "rules": [
            {
                "id": "by-name",
                "text": "Dates are checked.",
                "applies_to": {"records": ["action"], "filter": {"project": PROJECT["name"]}},
            }
        ],
    }
    (ws.config_dir / "rules.yaml").write_text(yaml.safe_dump(rules))
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        assert seed_rules(store) == ["by-name"]
        (rule,) = [r for r in active_rules(store.read()) if r.id == "by-name"]
        assert rule.applies_to.filter == {"project": PROJECT["id"]}
    finally:
        store.close()


# ---- what was stored by name before is joined by id when the app starts ------------------------------------------


def test_names_already_stored_in_the_watch_settings_and_in_rules_become_ids_when_the_app_starts(env):
    ws, cfg, store = env
    stale = {
        "version": 1,
        "sources": [
            {"id": "notes", "connector": "folder", "settings": {"path": str(ws.root)}, "project": PROJECT["name"]}
        ],
        "triage": [{**NOT_OURS, "projects": [PROJECT["name"], "No such project"]}],
    }
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(stale))
    with store.transaction() as tx:
        tx.create(
            "rule",
            {
                "name": "old-rule",
                "text": "Stored with a name.",
                "applies_to": {"records": ["action"], "filter": {"project": PROJECT["name"]}},
                "origin": "person",
                "status": "active",
                "learned_at": "2026-10-01T00:00:00+00:00",
            },
            _TEST,
        )
    changed = references.join_stored_names(ws, store)
    assert changed
    after = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    assert after["sources"][0]["project"] == PROJECT["id"]
    # A name nothing matches is left as it was (the rule closes nothing on it), not guessed at.
    assert after["triage"][0]["projects"] == [PROJECT["id"], "No such project"]
    (rule,) = [r for r in active_rules(store.read()) if r.id == "old-rule"]
    assert rule.applies_to.filter == {"project": PROJECT["id"]}
    assert references.join_stored_names(ws, store) == []  # running it again changes nothing
