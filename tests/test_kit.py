"""The define-your-own kit: item types from settings become record types, ops, stages, a panel and Today lines;
templates set it up; the assistant fills only the fields a person allows, with evidence."""

from datetime import date, timedelta

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B


def workspace(tmp_path, template="client-work"):
    from engine import templates
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    # Start from the demo without the kit, so each test sets it up itself.
    (ws.config_dir / "plugins" / "kit.yaml").unlink(missing_ok=True)
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [p for p in settings["plugins"]["enabled"] if p != "kit"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    if template:
        assert templates.apply(ws, template) == ["kit"]
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    assert store.plugins.active("kit"), store.plugins.status["kit"].reason
    yield ws, cfg, store
    store.close()


def apply(cfg, store, ops):
    from engine.applier import apply_as_person

    return apply_as_person(store, cfg, ops, "Test change")


def a_request(cfg, store, title="Harbor brochure", **values):
    apply(cfg, store, [{"op": "kit/request.add", "title": title, "values": values}])
    return store.read().list("kit/request")[-1]


def test_a_template_sets_up_item_types(env):
    ws, cfg, store = env
    assert "kit" in cfg.workspace.plugins.enabled
    assert "kit/request" in store.plugins.records
    assert {"kit/request.add", "kit/request.set", "kit/request.tick", "kit/request.fill"} <= set(store.plugins.ops)
    panel = store.plugins.panel("kit/request")
    assert panel.title == "Requests" and panel.columns == ("title", "client", "due", "size")
    assert [s.id for s in store.plugins.stages.types["kit/request"].stages] == ["new", "agreed", "delivered"]


def test_items_are_added_changed_and_ticked(env):
    from engine.texts import read_text

    _, cfg, store = env
    item = a_request(cfg, store, client="Lantern Press", size="small", brief="Two pages, folded.")
    assert item.data["client"] == "Lantern Press" and item.data["size"] == "small"
    from engine.texts import current

    assert read_text(store, current(store.read(), item.kind, item.id, "brief").data["sha256"]) == "Two pages, folded."
    change = {"op": "kit/request.set", "item": item.id, "values": {"size": "large"}, "read_version": item.version}
    apply(cfg, store, [change])
    item = store.read().get("kit/request", item.id)
    assert item.data["size"] == "large"
    apply(cfg, store, [{"op": "kit/request.tick", "item": item.id, "line": "agreed/0", "read_version": item.version}])
    assert store.read().get("kit/request", item.id).data["ticked"] == ["agreed/0"]


def test_a_choice_outside_its_options_is_refused(env):
    from engine.storage import StoreError

    _, cfg, store = env
    with pytest.raises(StoreError):
        a_request(cfg, store, size="enormous")


def test_stage_checks_come_from_the_type(env):
    from engine.stages import entry_check

    _, cfg, store = env
    item = a_request(cfg, store)
    failed = entry_check(store, "kit/request.agreed", item)
    assert not failed.passed and failed.reason == "Fill in Due first."
    ref = {"item": item.id, "values": {"due": "2030-01-10"}, "read_version": item.version}
    apply(cfg, store, [{"op": "kit/request.set", **ref}])
    item = store.read().get("kit/request", item.id)
    assert entry_check(store, "kit/request.agreed", item).passed
    assert not entry_check(store, "kit/request.delivered", item).passed
    ticks = [{"op": "kit/request.tick", "item": item.id, "line": "agreed/0", "read_version": item.version}]
    apply(cfg, store, ticks)
    item = store.read().get("kit/request", item.id)
    apply(cfg, store, [{"op": "kit/request.tick", "item": item.id, "line": "agreed/1", "read_version": item.version}])
    assert entry_check(store, "kit/request.delivered", store.read().get("kit/request", item.id)).passed


def test_today_shows_what_is_due_and_what_is_missing(env):
    _, cfg, store = env
    soon = (date.today() + timedelta(days=2)).isoformat()
    a_request(cfg, store, "Due soon", due=soon)
    a_request(cfg, store, "No date yet")
    texts = [line.text for plugin, line in store.plugins.today() if plugin == "kit"]
    assert f"Due soon is due {soon}" in texts and "No date yet has no due" in texts


def test_the_assistant_may_fill_only_the_fields_allowed_with_evidence(env):
    _, cfg, store = env
    fill = store.plugins.ops["kit/request.fill"]
    assert {"client", "due", "size", "evidence"} <= set(fill.model_fields) and "contact" not in fill.model_fields
    assert "kit/request.fill" in store.plugins.task_kind("notes").ops
    assert "kit/request.add" not in store.plugins.task_kind("notes").ops


def test_bad_settings_keep_the_kit_off_with_the_reason(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    store.close()
    path = ws.config_dir / "plugins" / "kit.yaml"
    settings = yaml.safe_load(path.read_text())
    settings["types"][0]["fields"][4]["options"] = []
    path.write_text(yaml.safe_dump(settings))
    from engine.storage import Store

    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    try:
        assert "a choice needs options" in store.plugins.status["kit"].reason
    finally:
        store.close()


def test_applying_a_second_template_adds_types_and_keeps_the_first(tmp_path):
    from engine import templates

    ws, cfg, store = workspace(tmp_path)
    store.close()
    templates.apply(ws, "content-calendar")
    settings = yaml.safe_load((ws.config_dir / "plugins" / "kit.yaml").read_text())
    assert [t["id"] for t in settings["types"]] == ["request", "piece"]
    templates.apply(ws, "client-work")
    again = yaml.safe_load((ws.config_dir / "plugins" / "kit.yaml").read_text())
    assert [t["id"] for t in again["types"]] == ["request", "piece"]


def test_a_template_that_doesnt_fit_writes_nothing(tmp_path):
    from engine import templates

    ws, cfg, store = workspace(tmp_path, template=None)
    store.close()
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"name": "Bad", "plugins": {"kit": {"types": [{"id": "x"}]}}}))
    with pytest.raises(templates.TemplateError, match="don't fit"):
        templates.apply(ws, str(bad))
    assert not (ws.config_dir / "plugins" / "kit.yaml").exists()


def test_a_workspace_saves_its_settings_as_a_template(tmp_path):
    from engine import templates

    ws, cfg, store = workspace(tmp_path)
    store.close()
    saved = templates.save(ws, tmp_path / "mine.yaml", "Mine", "My own setup.", ["kit"])
    data = yaml.safe_load(saved.read_text())
    assert data["name"] == "Mine" and data["plugins"]["kit"]["types"][0]["id"] == "request"
    assert [t["id"] for t in templates.shipped()] == ["client-work", "content-calendar"]


def test_items_have_a_place_in_the_synced_folder(env, tmp_path):
    from engine.sync import readable_files

    _, cfg, store = env
    a_request(cfg, store, "Harbor brochure", brief="Two pages.")
    files, _ = readable_files(store, store.read())
    assert "_workspace/requests/Harbor brochure.md" in files


def test_a_new_item_is_added_from_its_panel_with_a_typed_title(env):
    from engine import actions

    _, cfg, store = env
    assert store.plugins.panel("kit/request").new_action == "kit/request.new"
    empty = actions.preview(store, cfg, "kit/request.new")
    assert empty.ops == [] and empty.choice_list[0]["text"]
    project = store.read().list("project")[0]
    pending = actions.preview(store, cfg, "kit/request.new", None, {"title": "Spring catalog", "project": project.id})
    actions.apply(store, cfg, pending.token, {})
    item = store.read().list("kit/request")[-1]
    assert item.data["title"] == "Spring catalog" and item.data["project"] == project.id


def test_the_person_edits_any_shown_record_with_undo(env):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws, cfg, store = env
    item = a_request(cfg, store)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    body = {"kind": "kit/request", "id": item.id, "fields": {"client": "Lantern Press"}, "read_version": item.version}
    done = c.post(f"{api}/records/edit", json=body)
    assert done.status_code == 200, done.text
    assert (
        c.get(f"{api}/record", params={"kind": "kit/request", "id": item.id}).json()["fields"]["client"]
        == "Lantern Press"
    )
    refused = c.post(
        f"{api}/records/edit", json={**body, "fields": {"size": "enormous"}, "read_version": item.version + 1}
    )
    assert refused.status_code == 409
