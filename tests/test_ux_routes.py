"""Routes the screens use: any shown record and its kind's fields, and the synced folder's state."""

import yaml

from tests.test_today_panels_jobs import goals, workspace


def client_for(ws, cfg, store):
    from fastapi.testclient import TestClient

    from api.app import create_app

    store.close()
    token = "test-token"
    c = TestClient(create_app(ws, cfg, token, start_worker=False))
    c.headers["Authorization"] = f"Bearer {token}"
    return c, cfg.server.base_path.rstrip("/") + "/api"


def test_a_kind_and_a_record_are_described_for_screens(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    goals(cfg, store, "Finish the map")
    goal = store.read().list("p18/goal")[-1]
    c, api = client_for(ws, cfg, store)
    kind = c.get(f"{api}/kinds/p18/goal").json()
    assert [f["name"] for f in kind["fields"]] == ["id", "stage", "title", "status"]
    record = c.get(f"{api}/record", params={"kind": "p18/goal", "id": goal.id}).json()
    assert record["fields"]["title"] == "Finish the map" and record["long_text"] == []
    assert c.get(f"{api}/kinds/run").status_code == 404
    assert c.get(f"{api}/record", params={"kind": "changeset", "id": "CS-1"}).status_code == 404


def test_the_synced_folder_state_is_reported(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    c, api = client_for(ws, cfg, store)
    off = c.get(f"{api}/sync").json()
    assert off["folder"] == "" and off["problem"] is None and not off["stopped"]
    folder = tmp_path / "synced"
    folder.mkdir()
    storage = yaml.safe_load((ws.config_dir / "storage.yaml").read_text())
    storage["sync"] = {"folder": str(folder)}
    (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage))
    from engine.config import load_config
    from engine.storage import Store

    cfg = load_config(ws.config_dir, env={})
    c, api = client_for(ws, cfg, Store(ws.db_path, cfg=cfg))
    on = c.get(f"{api}/sync").json()
    assert on["folder"] == str(folder) and on["outside_edits"] == [] and on["conflict_copies"] == []
