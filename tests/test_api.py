import pytest
from fastapi.testclient import TestClient

from api.app import COOKIE, create_app
from engine.config import load_config
from engine.workspace import init_workspace

TOKEN = "test-token-value"


@pytest.fixture(params=["/", "/admin", "/tools/cockpit"])
def client(request, tmp_path, demo):
    ws = init_workspace(tmp_path / "ws", template=demo, git=False)
    cfg = load_config(ws.config_dir, env={}, flags={"server.base_path": request.param})
    prefix = "" if request.param == "/" else request.param
    return TestClient(create_app(ws, cfg, TOKEN)), prefix, cfg


def test_health_needs_no_token(client):
    c, prefix, _ = client
    assert c.get(f"{prefix}/api/health").json() == {"status": "ok"}


def test_everything_else_needs_the_token(client):
    c, prefix, _ = client
    assert c.get(f"{prefix}/api/runtime-config").status_code == 401
    assert c.get(f"{prefix}/api/runtime-config", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_bearer_token_works(client):
    c, prefix, cfg = client
    body = c.get(f"{prefix}/api/runtime-config", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert body["base_path"] == cfg.server.base_path
    assert body["api_base"] == f"{prefix}/api"
    assert body["assistant_name"] == cfg.workspace.assistant_name


def test_link_token_sets_a_cookie_scoped_to_the_base_path_and_strips_itself(client):
    c, prefix, _ = client
    r = c.get(f"{prefix}/?token={TOKEN}", follow_redirects=False)
    assert r.status_code == 303
    assert "token=" not in r.headers["location"]
    cookie = r.headers["set-cookie"]
    assert f"{COOKIE}=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert f"Path={prefix or '/'}" in cookie
    assert c.get(f"{prefix}/api/runtime-config").status_code == 200


def test_wrong_link_token_is_refused(client):
    c, prefix, _ = client
    assert c.get(f"{prefix}/?token=nope", follow_redirects=False).status_code == 401


def test_nothing_is_served_outside_the_base_path(client):
    c, prefix, _ = client
    if prefix:
        assert c.get("/api/health").status_code == 404


def test_shutdown_hook_runs_when_the_server_stops(tmp_path, demo):
    ws = init_workspace(tmp_path / "ws", template=demo, git=False)
    calls = []
    for base in ("/", "/admin"):
        cfg = load_config(ws.config_dir, env={}, flags={"server.base_path": base})
        with TestClient(create_app(ws, cfg, TOKEN, on_shutdown=lambda b=base: calls.append(b))):
            pass
    assert calls == ["/", "/admin"]
