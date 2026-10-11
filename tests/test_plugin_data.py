"""Plugin data files in layers: what the plugin ships, the workspace's own, and a project's, the most specific
winning; paths stay inside the plugin's data."""

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B, fixture_records

FIXTURE = """
from engine.plugin_api import Settings

class Config(Settings):
    pass

def register(registrar):
    pass
"""


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p10"
    (plugin / "_data" / "templates").mkdir(parents=True)
    (plugin / "_data" / "templates" / "classic.yaml").write_text("name: shipped classic\n")
    (plugin / "_data" / "templates" / "modern.yaml").write_text("name: shipped modern\n")
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p10",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Data files fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"data": "_data"},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    mine = ws.root / "plugin-data" / "p10" / "templates"
    mine.mkdir(parents=True)
    (mine / "modern.yaml").write_text("name: my modern\n")
    (mine / "mine.yaml").write_text("name: only mine\n")
    project = fixture_records(DEMO_B, "project")[0]["id"]
    per_project = ws.root / "plugin-data" / "p10" / "projects" / project / "templates"
    per_project.mkdir(parents=True)
    (per_project / "classic.yaml").write_text("name: this book's classic\n")
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p10"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    assert store.plugins.active("p10"), store.plugins.status["p10"].reason
    yield store, project
    store.close()


def view(store):
    from engine.plugin_api import ReadView

    return store.plugins._with_files(ReadView(store.read(), "p10"))


def test_the_most_specific_layer_wins(env):
    store, project = env
    v = view(store)
    assert v.data("templates/classic.yaml") == b"name: shipped classic\n"
    assert v.data("templates/modern.yaml") == b"name: my modern\n"
    assert v.data("templates/classic.yaml", project=project) == b"name: this book's classic\n"
    assert v.data("templates/missing.yaml") is None


def test_files_are_listed_across_layers_once(env):
    store, project = env
    assert view(store).data_files("templates") == [
        "templates/classic.yaml",
        "templates/mine.yaml",
        "templates/modern.yaml",
    ]
    assert view(store).data_files("templates", project=project) == [
        "templates/classic.yaml",
        "templates/mine.yaml",
        "templates/modern.yaml",
    ]


@pytest.mark.parametrize("bad", ["../secrets.yaml", "/etc/passwd", "templates/../../x"])
def test_paths_stay_inside_the_plugins_data(env, bad):
    from engine.storage import StoreError

    store, _ = env
    with pytest.raises(StoreError, match="relative path"):
        view(store).data(bad)


def test_a_missing_data_folder_refuses_the_plugin(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p10"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p10",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "x",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"data": "nowhere"},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p10"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    assert "isn't a folder beside plugin.yaml" in store.plugins.status["p10"].reason
    store.close()
