"""Plugin API 0.3.37: a setup step can tell which of its secrets are set, a plugin's wording keys must be ones the
screens read, and a linked plugin imports its own package by name, as it would when installed."""

import sys

import yaml

from tests.test_plugin_api_0329 import reopen
from tests.test_today_panels_jobs import FIXTURE, workspace

STEPPED = FIXTURE.replace(
    "def register(registrar):\n",
    "def registered(view, settings, secrets):\n    return 'client-id' in secrets\n\n"
    "def register(registrar):\n"
    '    registrar.setup_step("p18/registration", label="Set up the app registration", done=registered)\n',
)


def test_a_setup_step_sees_which_secrets_are_set(tmp_path, monkeypatch):
    from engine import setup

    ws, cfg, store = workspace(tmp_path, STEPPED)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["provides"]["setup_steps"] = ["p18/registration"]
    manifest["requires"] = {"secrets": ["client-id"]}
    path.write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["secrets"] = {"p18": {"client-id": "env:P18_ID"}}
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    monkeypatch.delenv("P18_ID", raising=False)
    cfg, store = reopen(ws, cfg)
    try:
        step = lambda: next(s for s in setup.steps(ws, cfg, store) if s.id == "p18/registration")  # noqa: E731
        assert not step().done
        monkeypatch.setenv("P18_ID", "app-1")
        assert step().done
    finally:
        store.close()


def test_only_wording_keys_the_screens_read_are_taken(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    store.close()
    folder = ws.root / "plugins" / "p18"
    (folder / "wording.yaml").write_text(yaml.safe_dump({"op.p18/add-goal": "Add a goal", "nav.p18/goals": "Goals"}))
    manifest = yaml.safe_load((folder / "plugin.yaml").read_text())
    manifest["provides"]["wording"] = ["wording.yaml"]
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    cfg, store = reopen(ws, cfg)
    try:
        words = store.plugins.wording()
        assert words["op.p18/add-goal"] == "Add a goal" and "nav.p18/goals" not in words
        assert any("isn't a key the screens read" in n for n in store.plugins.status["p18"].notes)
    finally:
        store.close()


def test_a_linked_plugin_imports_its_own_package_by_name(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    store.close()
    folder = ws.root / "plugins" / "p18"
    (folder / "parts.py").write_text((folder / "fixture.py").read_text())
    (folder / "fixture.py").unlink()
    (folder / "__init__.py").write_text("from p18.parts import Config, register  # noqa: F401\n")
    manifest = yaml.safe_load((folder / "plugin.yaml").read_text())
    manifest["entry"], manifest["config_schema"] = "p18:register", "p18:Config"
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    cfg, store = reopen(ws, cfg)
    try:
        assert "p18" in sys.modules and "p18.parts" in sys.modules
    finally:
        store.close()
    assert "p18" not in sys.modules  # closing the host forgets it
