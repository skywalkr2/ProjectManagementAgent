"""Plugin API 0.3.31: a plugin names its own kinds on screen. Its AI task kinds' labels and its wording files reach the
screens' wording, under the workspace's own overrides; a key outside its namespace is left out and noted."""

import yaml

from tests.test_plugin_api_0329 import reopen, with_manifest
from tests.test_today_panels_jobs import FIXTURE, workspace


def test_a_plugins_wording_reaches_the_screens_under_the_workspaces(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws, cfg, store = workspace(tmp_path, FIXTURE)
    store.close()
    folder = ws.root / "plugins" / "p18"
    (folder / "wording.yaml").write_text(
        yaml.safe_dump(
            {"stages.group.p18/goal": "Goals", "followups.title": "Not mine to rename", "panel.p18/goals": "x" * 500}
        )
    )
    with_manifest(ws, wording=["wording.yaml"])
    ui = ws.config_dir / "ui.yaml"
    data = yaml.safe_load(ui.read_text()) or {}
    data["wording"] = {"panel.p18/other": "Mine"}
    ui.write_text(yaml.safe_dump(data))
    cfg, store = reopen(ws, cfg)
    try:
        words = store.plugins.wording()
        assert words["stages.group.p18/goal"] == "Goals" and words["task.p18/plan"] == "Plan"
        assert "followups.title" not in words and "panel.p18/goals" not in words
        assert any("left out" in n for n in store.plugins.status["p18"].notes)
    finally:
        store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    base = cfg.server.base_path.rstrip("/")
    rc = c.get(f"{base}/api/runtime-config", headers={"Authorization": "Bearer t"}).json()
    assert rc["wording"]["stages.group.p18/goal"] == "Goals" and rc["wording"]["panel.p18/other"] == "Mine"


def test_a_wording_file_must_be_yaml_inside_the_plugin():
    import pytest
    from pydantic import ValidationError

    from engine.plugin_manifest import Provides

    for bad in ("/etc/words.yaml", "../words.yaml", "words.txt"):
        with pytest.raises(ValidationError):
            Provides(wording=[bad])
