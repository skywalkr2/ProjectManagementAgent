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
    '    margins: Margins = Field(default_factory=Margins, description="Page margins.")\n'
    '    extends: str | None = Field(None, description="The template this one builds on.")\n\n'
    "from pydantic import model_validator\n\n"
    "class Item(BaseModel):\n"
    '    model_config = {"extra": "forbid"}\n'
    '    name: str = Field("", min_length=1, description="What the item is called.")\n'
    '    low: int = Field(0, description="The least.")\n'
    '    high: int = Field(10, description="The most.")\n\n'
    "    @model_validator(mode='after')\n"
    "    def _order(self):\n"
    "        if self.low > self.high:\n"
    "            raise ValueError('the least must not be more than the most')\n"
    "        return self\n\n"
    "class Stages(BaseModel):\n"
    '    names: list[str] = Field(default_factory=list, description="The stages, in order.")\n',
).replace(
    "def register(registrar):\n",
    "def register(registrar):\n"
    "    registrar.data_form('p18/templates', label='Book templates', folder='templates', schema=Template)\n"
    "    registrar.data_form('p18/items', label='Items', folder='items', schema=Item, pattern='*/item.yaml')\n"
    "    registrar.data_form('p18/stages', label='Stages', folder='life', schema=Stages, pattern='stages.yaml',"
    " single=True)\n",
)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path, CODE)
    store.close()
    plugin = ws.root / "plugins" / "p18"
    (plugin / "data" / "templates").mkdir(parents=True)
    (plugin / "data" / "templates" / "classic.yaml").write_text(yaml.safe_dump({"title": "Classic"}))
    manifest = dict(MANIFEST)
    manifest["provides"] = {
        **MANIFEST["provides"],
        "data_forms": ["p18/templates", "p18/items", "p18/stages"],
        "data": "data",
    }
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
    forms = {f["name"]: f for f in c.get(f"{api}/data-forms").json()}
    assert forms["p18/templates"] == {
        "name": "p18/templates",
        "plugin": "p18",
        "label": "Book templates",
        "description": "",
        "pattern": "*.yaml",
        "single": False,
    }
    assert forms["p18/stages"]["single"] is True and forms["p18/items"]["pattern"] == "*/item.yaml"
    assert c.get(f"{api}/data-forms/p18/templates/files").json() == [
        {"file": "classic.yaml", "layers": ["shipped"], "layer": "shipped", "problem": None}
    ]
    form = c.get(f"{api}/data-forms/p18/templates/file", params={"path": "classic.yaml"}).json()
    values = {i["key"]: i["value"] for i in form["items"]}
    assert values == {
        "title": "Classic",
        "trim": "5.5x8.5",
        "margins.inner": 0.75,
        "margins.outer": 0.5,
        "extends": None,
    }
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


@pytest.mark.parametrize("name", ["../escape.yaml", "Classic.yaml", "notes.txt", "a/b.yaml", "a/../b.yaml"])
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


def test_a_save_writes_only_what_the_file_had_and_what_was_set(env):
    ws, c, api = env
    shipped = ws.root / "plugins" / "p18" / "data" / "templates"
    (shipped / "large.yaml").write_text(yaml.safe_dump({"title": "Large print", "extends": "classic"}))
    body = {"file": "large.yaml", "layer": "workspace", "changes": {"trim": "6x9"}}
    assert c.post(f"{api}/data-forms/p18/templates/file", json=body).status_code == 200
    copy = ws.root / "plugin-data" / "p18" / "templates" / "large.yaml"
    assert yaml.safe_load(copy.read_text()) == {"title": "Large print", "extends": "classic", "trim": "6x9"}


def test_a_new_file_can_start_from_another_of_its_kind(env):
    ws, c, api = env
    body = {"file": "pocket.yaml", "layer": "workspace", "changes": {"title": "Pocket"}, "start_from": "classic.yaml"}
    assert c.post(f"{api}/data-forms/p18/templates/file", json=body).status_code == 200
    copy = ws.root / "plugin-data" / "p18" / "templates" / "pocket.yaml"
    assert yaml.safe_load(copy.read_text()) == {"title": "Pocket"}
    missing = {**body, "file": "other.yaml", "start_from": "absent.yaml"}
    assert c.post(f"{api}/data-forms/p18/templates/file", json=missing).status_code == 409


def test_a_pattern_reaches_one_level_of_folders_and_problems_show_on_the_list(env):
    ws, c, api = env
    items = ws.root / "plugin-data" / "p18" / "items"
    (items / "lamp").mkdir(parents=True)
    (items / "lamp" / "item.yaml").write_text(yaml.safe_dump({"name": "Lamp"}))
    (items / "lamp" / "notes.yaml").write_text("not: listed\n")
    (items / "chair").mkdir()
    (items / "chair" / "item.yaml").write_text(yaml.safe_dump({"low": 3}))
    listed = {f["file"]: f for f in c.get(f"{api}/data-forms/p18/items/files").json()}
    assert sorted(listed) == ["chair/item.yaml", "lamp/item.yaml"]
    assert listed["lamp/item.yaml"]["problem"] is None
    assert listed["chair/item.yaml"]["problem"].startswith("name:")
    body = {"file": "lamp/item.yaml", "layer": "workspace", "changes": {"low": 20}}
    refused = c.post(f"{api}/data-forms/p18/items/file", json=body)
    assert refused.status_code == 409 and refused.json()["detail"] == "the least must not be more than the most"
    wrong = c.post(f"{api}/data-forms/p18/items/file", json={**body, "file": "lamp/notes.yaml"})
    assert wrong.status_code == 409


def test_a_single_file_kind_is_listed_before_it_exists_and_allows_no_other(env):
    ws, c, api = env
    assert c.get(f"{api}/data-forms/p18/stages/files").json() == [
        {"file": "stages.yaml", "layers": [], "layer": None, "problem": None}
    ]
    body = {"file": "stages.yaml", "layer": "workspace", "changes": {"names": ["Draft", "Done"]}}
    assert c.post(f"{api}/data-forms/p18/stages/file", json=body).status_code == 200
    other = c.post(f"{api}/data-forms/p18/stages/file", json={**body, "file": "more.yaml"})
    assert other.status_code == 409
