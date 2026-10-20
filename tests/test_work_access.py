"""An AI account the person answered "Not now" about reading work mail and notes comes back on Today as a line with
Allow (design 6.16, 7.7). Allow is one settings change with Undo; the account's other levels stay as they were."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go
from tests.test_setup import COMMON

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
TOKEN = "work-access-token"


def add_account(ws, name, **more) -> None:
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"][name] = {"adapter": "stub", "models": {"default": "scripted"}, "allowed_data": ["open"], **more}
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def lines(ws, store):
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    return [line for line in queue(ws, store, cfg, NOW) if line.kind == "work_access"]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, store
    store.close()
    set_responder(None)


def test_an_account_the_person_said_not_now_about_has_a_line_naming_it(env):
    ws, store = env
    assert lines(ws, store) == []
    add_account(ws, "standin", work_data="not_now")
    (line,) = lines(ws, store)
    assert (line.account, line.group, line.key) == ("standin", "decide", "work_access:standin")


def test_an_account_never_asked_about_has_no_line(env):
    ws, store = env
    add_account(ws, "standin")
    assert lines(ws, store) == []


def test_an_account_that_may_read_work_material_has_no_line_even_if_not_now_was_recorded(env):
    ws, store = env
    add_account(ws, "standin", work_data="not_now", allowed_data=["open", "internal"])
    assert lines(ws, store) == []


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    add_account(ws, "standin", work_data="not_now")
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield ws, client
    set_responder(None)


def test_the_today_route_carries_the_line_and_allow_gives_the_yes_with_undo(api):
    ws, client = api
    shown = [x for x in client.get("/api/today/queue").json() if x["kind"] == "work_access"]
    assert [x["account"] for x in shown] == ["standin"]

    fingerprint = client.get("/api/settings").json()["fingerprint"]
    done = client.post("/api/ai/accounts/standin/allow-work", json={"fingerprint": fingerprint})
    assert done.status_code == 200, done.text
    changes = {c["key"]: c for c in done.json()["changes"]}
    allowed = changes["ai.providers.standin.allowed_data"]
    assert allowed["before"] == ["open"] and allowed["after"] == ["open", "internal"]
    assert changes["ai.providers.standin.work_data"]["after"] in ("", None)
    on_disk = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())["providers"]["standin"]
    assert on_disk["allowed_data"] == ["open", "internal"] and not on_disk.get("work_data")
    assert [x for x in client.get("/api/today/queue").json() if x["kind"] == "work_access"] == []

    # Undo posts the values from before, through the settings save every other change uses.
    undo = {"changes": {}, "reset": [], "fingerprint": done.json()["fingerprint"]}
    for change in done.json()["changes"]:
        if change["was_default"]:
            undo["reset"].append(change["key"])
        else:
            undo["changes"][change["key"]] = change["before"]
    assert client.post("/api/settings", json=undo).status_code == 200
    back = [x for x in client.get("/api/today/queue").json() if x["kind"] == "work_access"]
    assert [x["account"] for x in back] == ["standin"]


def test_allow_keeps_a_higher_level_the_account_already_had(api):
    ws, client = api
    add_account(ws, "wide", work_data="not_now", allowed_data=["open", "restricted"])
    fingerprint = client.get("/api/settings").json()["fingerprint"]
    done = client.post("/api/ai/accounts/wide/allow-work", json={"fingerprint": fingerprint})
    assert done.status_code == 200, done.text
    on_disk = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())["providers"]["wide"]
    assert on_disk["allowed_data"] == ["open", "internal", "restricted"]


def test_allow_refuses_an_account_that_is_not_there(api):
    _, client = api
    fingerprint = client.get("/api/settings").json()["fingerprint"]
    assert client.post("/api/ai/accounts/nobody/allow-work", json={"fingerprint": fingerprint}).status_code == 404


def test_the_guide_records_not_now_with_the_account_and_allow_does_not(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        fingerprint = client.get("/api/settings").json()["fingerprint"]
        body = {
            "name": "mine",
            "adapter": COMMON,
            "base_url": "http://localhost:11434/v1",
            "key": "not-a-real-key",
            "models": {"small": "small-model"},
            "allowed_data": ["open"],
            "work_data": "not_now",
            "fingerprint": fingerprint,
        }
        assert client.post("/api/ai/accounts", json=body).status_code == 200
        kept = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())["providers"]["mine"]
        assert kept["work_data"] == "not_now" and kept["allowed_data"] == ["open"]
        shown = [x for x in client.get("/api/today/queue").json() if x["kind"] == "work_access"]
        assert [x["account"] for x in shown] == ["mine"]
