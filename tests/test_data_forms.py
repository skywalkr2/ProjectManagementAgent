"""Data-file forms (plugin API 0.3.52): a plugin declares a kind of data file and its schema; the screens list the
files across the layers and edit the workspace's or a project's copy through a form, checked, with Undo. The shipped
copy is never written."""

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_today_panels_jobs import FIXTURE, MANIFEST, workspace

CODE = FIXTURE.replace(
    "class Config(Settings):\n    pass\n",
    "from pydantic import BaseModel, Field\n\n"
    "class Config(Settings):\n    pass\n\n"
    "class Margins(BaseModel):\n"
    '    inner: float = Field(0.75, description="Inside margin, in inches.")\n'
    '    outer: float = Field(0.5, description="Outside margin, in inches.")\n\n'
    "class Template(BaseModel):\n"
    '    model_config = {"extra": "forbid"}\n'
    '    title: str = Field("Untitled", description="What the template is called.")\n'
    '    trim: str = Field("5.5x8.5", description="Page size.")\n'
    '    margins: Margins = Field(default_factory=Margins, description="Page margins.")\n',
).replace(
    "def register(registrar):\n",
    "def register(registrar):\n"
    "    registrar.data_form('p18/templates', label='Book templates', folder='templates', schema=Template)\n",
)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path, CODE)
    store.close()
    plugin = ws.root / "plugins" / "p18"
    (plugin / "data" / "templates").mkdir(parents=True)
    (plugin / "data" / "templates" / "classic.yaml").write_text(yaml.safe_dump({"title": "Classic"}))
    manifest = dict(MANIFEST)
    manifest["provides"] = {**MANIFEST["provides"], "data_forms": ["p18/templates"], "data": "data"}
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    from tests.test_plugin_api_0329 import reopen

    cfg, store = reopen(ws, cfg)
    store.close()
    from api.app import create_app

    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    yield ws, c, cfg.server.base_path.rstrip("/") + "/api"


def test_a_shipped_file_is_listed_and_shown_as_a_form(env):
    ws, c, api = env
    assert c.get(f"{api}/data-forms").json() == [
        {"name": "p18/templates", "plugin": "p18", "label": "Book templates", "description": ""}
    ]
    assert c.get(f"{api}/data-forms/p18/templates/files").json() == [
        {"file": "classic.yaml", "layers": ["shipped"], "layer": "shipped", "problem": None}
    ]
    form = c.get(f"{api}/data-forms/p18/templates/file", params={"path": "classic.yaml"}).json()
    values = {i["key"]: i["value"] for i in form["items"]}
    assert values == {"title": "Classic", "trim": "5.5x8.5", "margins.inner": 0.75, "margins.outer": 0.5}
    assert form["layer"] == "shipped"


def test_saving_writes_the_workspaces_copy_never_the_shipped_one_and_undoes(env):
    ws, c, api = env
    shipped = ws.root / "plugins" / "p18" / "data" / "templates" / "classic.yaml"
    before = shipped.read_text()
    body = {"file": "classic.yaml", "layer": "workspace", "changes": {"margins.inner": 1.0}}
    saved = c.post(f"{api}/data-forms/p18/templates/file", json=body)
    assert saved.status_code == 200, saved.text and saved.json()["before"] is None
    copy = ws.root / "plugin-data" / "p18" / "templates" / "classic.yaml"
    assert yaml.safe_load(copy.read_text())["margins"]["inner"] == 1.0 and shipped.read_text() == before
    listed = c.get(f"{api}/data-forms/p18/templates/files").json()[0]
    assert listed["layers"] == ["shipped", "workspace"] and listed["layer"] == "workspace"
    bad = c.post(f"{api}/data-forms/p18/templates/file", json={**body, "changes": {"margins.inner": "wide"}})
    assert bad.status_code == 409 and "margins.inner" in bad.text
    unknown = c.post(f"{api}/data-forms/p18/templates/file", json={**body, "changes": {"colour": "red"}})
    assert unknown.status_code == 409
    undo = {"file": "classic.yaml", "layer": "workspace", "before": None}
    assert c.post(f"{api}/data-forms/p18/templates/restore", json=undo).status_code == 200
    assert not copy.exists()


def test_a_new_file_starts_from_the_defaults_and_a_copy_can_be_removed(env):
    ws, c, api = env
    new = c.get(f"{api}/data-forms/p18/templates/file", params={"path": "pocket.yaml"}).json()
    assert new["layer"] is None and {i["key"]: i["value"] for i in new["items"]}["title"] == "Untitled"
    made = {"file": "pocket.yaml", "layer": "workspace", "changes": {"title": "Pocket", "trim": "4.25x6.87"}}
    assert c.post(f"{api}/data-forms/p18/templates/file", json=made).status_code == 200
    removed = c.post(f"{api}/data-forms/p18/templates/remove", json={"file": "pocket.yaml", "layer": "workspace"})
    assert removed.status_code == 200 and "Pocket" in removed.json()["before"]
    assert [f["file"] for f in c.get(f"{api}/data-forms/p18/templates/files").json()] == ["classic.yaml"]
    back = {"file": "pocket.yaml", "layer": "workspace", "before": removed.json()["before"]}
    assert c.post(f"{api}/data-forms/p18/templates/restore", json=back).status_code == 200
    assert "pocket.yaml" in [f["file"] for f in c.get(f"{api}/data-forms/p18/templates/files").json()]


def test_a_project_copy_wins_for_that_project(env):
    ws, c, api = env
    from engine.storage import Store

    store = Store(ws.db_path)
    try:
        project = store.read().list("project")[0].id
    finally:
        store.close()
    body = {"file": "classic.yaml", "layer": "project", "project": project, "changes": {"title": "For this book"}}
    assert c.post(f"{api}/data-forms/p18/templates/file", json=body).status_code == 200
    here = c.get(f"{api}/data-forms/p18/templates/file", params={"path": "classic.yaml", "project": project}).json()
    assert here["layer"] == "project" and {i["key"]: i["value"] for i in here["items"]}["title"] == "For this book"
    elsewhere = c.get(f"{api}/data-forms/p18/templates/file", params={"path": "classic.yaml"}).json()
    assert {i["key"]: i["value"] for i in elsewhere["items"]}["title"] == "Classic"
    no_project = c.post(f"{api}/data-forms/p18/templates/file", json={**body, "project": None})
    assert no_project.status_code == 409


@pytest.mark.parametrize("name", ["../escape.yaml", "Classic.yaml", "notes.txt", "a/b.yaml"])
def test_file_names_stay_inside_the_folder(env, name):
    ws, c, api = env
    body = {"file": name, "layer": "workspace", "changes": {}}
    assert c.post(f"{api}/data-forms/p18/templates/file", json=body).status_code == 409


def test_a_data_forms_schema_is_checked_at_registration():
    from pydantic import BaseModel

    from engine.plugin_api import Registrar

    class NoDefault(BaseModel):
        title: str

    with pytest.raises(ValueError, match="default and a description"):
        Registrar("p18", {}, None).data_form("p18/x", label="X", folder="x", schema=NoDefault)
    with pytest.raises(ValueError, match="relative path"):
        Registrar("p18", {}, None).data_form("p18/y", label="Y", folder="../x", schema=BaseModel)
