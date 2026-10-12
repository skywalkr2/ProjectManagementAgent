"""Undo of a guided save: the screens undo by saving the values from before through the general settings save, so every
key a guided route writes must be accepted there too (a source added on Sources, an add-on turned on or off, the
person's own name)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.setup_routes import GUIDED
from tests.test_setup import make


def undo(c: TestClient, api: str, saved: dict) -> object:
    body = {
        "changes": {x["key"]: x["before"] for x in saved["changes"]},
        "reset": [],
        "fingerprint": saved["fingerprint"],
    }
    return c.post(f"{api}/settings", json=body)


def test_adding_a_source_can_be_undone(tmp_path):
    ws, cfg, store = make(tmp_path)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    body = {"connector": "folder", "label": "Undo me", "settings": {"path": str(tmp_path)}, "fingerprint": fingerprint}
    added = c.post(f"{api}/watch/sources", json=body)
    assert added.status_code == 200, added.text
    undone = undo(c, api, added.json())
    assert undone.status_code == 200, undone.text
    assert "Undo me" not in (ws.config_dir / "watch.yaml").read_text(encoding="utf-8")


def test_every_key_a_guided_route_writes_can_be_saved_back_for_undo():
    source = (Path(__file__).parents[1] / "api" / "setup_routes.py").read_text(encoding="utf-8")
    used = set()
    for group in re.findall(r"allow=\(([^)]*)\)", source):
        used |= {
            p for p in re.findall(r'"([^"]*)"', group) if p
        }  # "" is a plugin step's own settings, not a guided key
    for prefix in sorted(used):
        assert any(prefix.startswith(g) or g.startswith(prefix) for g in GUIDED), prefix
