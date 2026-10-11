"""Value lists (design 5.1): a field bound to a list takes only the list's values, wherever it is written; the person
adds, renames (every record follows, in one step) and retires values, each with Undo; a workspace gets the core's
lists with the values it already uses."""

import os

import pytest
from fastapi.testclient import TestClient

from engine.config import load_config
from engine.lists import core_lists
from tests.conftest import DEMO_B


@pytest.fixture
def app(tmp_path):
    from api.app import create_app
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    yield c, api, ws, Store
    c.close()


def lists(c, api):
    return {v["name"]: v for v in c.get(f"{api}/lists").json()}


def project(c, api):
    first = c.get(f"{api}/projects").json()[0]
    return c.get(f"{api}/record", params={"kind": "project", "id": first["id"]}).json()


def edit(c, api, record, **fields):
    return c.post(
        f"{api}/records/edit",
        json={"kind": "project", "id": record["id"], "fields": fields, "read_version": record["version"]},
    )


def test_a_workspace_gets_the_core_lists_with_the_values_it_uses(app):
    c, api, _, _ = app
    found = lists(c, api)
    assert set(core_lists()) <= set(found)
    status = found["project-status"]
    assert status["values"][: len(core_lists()["project-status"]["values"])] == core_lists()["project-status"]["values"]
    held = project(c, api)["fields"]
    assert held["status"] in status["values"] and held["group"] in found["project-group"]["values"]
    assert "project.status" in status["used_by"]
    kind = {f["name"]: f for f in c.get(f"{api}/kinds/project").json()["fields"]}
    assert kind["status"]["type"] == "choice" and kind["status"]["options"] == status["values"]
    assert kind["status"]["value_list"] == "project-status" and kind["name"]["value_list"] is None


def test_a_value_off_the_list_is_refused_until_it_is_added(app):
    c, api, _, _ = app
    record = project(c, api)
    refused = edit(c, api, record, status="Sideways")
    assert refused.status_code >= 400 and "isn't on the list" in refused.text and "add it to the list" in refused.text
    added = c.post(f"{api}/lists/project-status/add", json={"value": "  Sideways "})
    assert added.status_code == 200, added.text
    assert lists(c, api)["project-status"]["values"][-1] == "Sideways"
    assert c.post(f"{api}/lists/project-status/add", json={"value": "sideways"}).status_code >= 400  # once
    assert edit(c, api, project(c, api), status="Sideways").status_code == 200
    # Undo of the add takes the value back off the list (the record keeps what it holds).
    assert c.post(f"{api}/changesets/{added.json()['changeset']}/undo", json={}).status_code == 200
    assert "Sideways" not in lists(c, api)["project-status"]["values"]


def test_renaming_a_value_changes_every_record_that_holds_it(app):
    c, api, _, _ = app
    record = project(c, api)
    old = record["fields"]["status"]
    done = c.post(f"{api}/lists/project-status/rename", json={"value": old, "to": "Going well"})
    assert done.status_code == 200, done.text
    assert project(c, api)["fields"]["status"] == "Going well"
    assert (
        "Going well" in lists(c, api)["project-status"]["values"]
        and old not in lists(c, api)["project-status"]["values"]
    )
    taken = lists(c, api)["project-status"]["values"][1]
    clash = c.post(f"{api}/lists/project-status/rename", json={"value": "Going well", "to": taken.upper()})
    assert clash.status_code >= 400 and "already on the list" in clash.text
    assert c.post(f"{api}/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert project(c, api)["fields"]["status"] == old


def test_a_retired_value_stays_on_records_that_hold_it_but_isnt_offered(app):
    c, api, _, _ = app
    record = project(c, api)
    held = record["fields"]["status"]
    assert c.post(f"{api}/lists/project-status/retire", json={"value": held}).status_code == 200
    found = lists(c, api)["project-status"]
    assert held in found["retired"] and held not in found["values"]
    kept = edit(c, api, project(c, api), summary="Still fine")
    assert kept.status_code == 200, kept.text  # the record keeps its retired value
    other = found["values"][0]
    assert edit(c, api, project(c, api), status=other).status_code == 200
    assert edit(c, api, project(c, api), status=held).status_code >= 400  # not offered any more
    assert c.post(f"{api}/lists/project-status/add", json={"value": held}).status_code == 200  # offered again
    assert held in lists(c, api)["project-status"]["values"]


@pytest.mark.skipif(os.environ.get("COCKPIT_TEST_CORE_ONLY") == "1", reason="the example plugin is off in this run")
def test_a_plugin_declares_its_own_list_and_binds_its_fields_to_it(app):
    c, api, ws, Store = app
    found = lists(c, api)
    assert "example/kind" in found and found["example/kind"]["values"]
    assert "example/reminder.kind" in found["example/kind"]["used_by"]
    kind = {f["name"]: f for f in c.get(f"{api}/kinds/example/reminder").json()["fields"]}
    assert kind["kind"]["value_list"] == "example/kind" and kind["kind"]["options"] == found["example/kind"]["values"]


def test_a_plugin_field_bound_to_a_list_it_doesnt_own_is_refused(tmp_path):
    from typing import Annotated, ClassVar

    from pydantic import Field

    from engine.plugin_api import InList, Record, Registrar
    from engine.plugin_host import PluginHost
    from engine.plugin_manifest import Manifest

    class Thing(Record):
        record_kind: ClassVar[str] = "p30/thing"
        prefix: ClassVar[str] = "THG"
        sort: Annotated[str | None, InList("other/sorts")] = Field(None)

    manifest = Manifest.model_validate(
        {
            "name": "p30",
            "version": "0.1.0",
            "plugin_api": ">=0.3,<0.4",
            "description": "Lists fixture",
            "entry": "p30:register",
            "config_schema": "p30:Config",
            "provides": {"record_types": ["p30/thing"]},
        }
    )
    registrar = Registrar("p30", None)
    registrar.record_type(Thing)
    host = PluginHost.__new__(PluginHost)
    with pytest.raises(ValueError, match="neither its own list nor the core's"):
        host._validate(manifest, registrar)
    with pytest.raises(ValueError):
        registrar.value_list("p30/sorts", label="Sorts", values=["A", "a"])  # each value once


def test_the_assistant_is_told_the_values_a_field_takes(app):
    c, api, ws, Store = app
    from engine.packet import _value_lists

    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    try:
        block = _value_lists(store)
    finally:
        store.close()
    status = lists(c, api)["project-status"]["values"]
    assert "project.status: " + "; ".join(status) in block and "Use one of these exactly" in block
