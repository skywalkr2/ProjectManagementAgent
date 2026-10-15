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
    assert body["assistant_named"] is True  # the fixture's assistant has a name of its own


def test_the_runtime_config_says_whether_the_assistant_has_a_name_of_its_own(tmp_path):
    def asked(folder, **names):
        ws = init_workspace(tmp_path / folder, git=False, **names)
        app = create_app(ws, ws.config(env={}), TOKEN, start_worker=False)
        return TestClient(app).get("/api/runtime-config", headers={"Authorization": f"Bearer {TOKEN}"}).json()

    # The default name is the one the person hasn't chosen yet; the screens word themselves for that.
    assert asked("plain")["assistant_named"] is False
    named = asked("named", assistant="Ada")
    assert named["assistant_name"] == "Ada" and named["assistant_named"] is True


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


def test_the_ui_gets_a_base_for_the_configured_path_and_a_strict_policy(tmp_path, demo):
    import re

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><head><title>x</title></head><body></body></html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    ws = init_workspace(tmp_path / "ws", template=demo, git=False)
    for base in ("/", "/tools/cockpit"):
        cfg = load_config(ws.config_dir, env={}, flags={"server.base_path": base})
        prefix = "" if base == "/" else base
        app = create_app(ws, cfg, TOKEN, ui_dist=dist)
        c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
        page = c.get(f"{prefix}/some/deep/route")
        assert page.status_code == 200
        assert re.search(rf'<base href="{prefix}/"', page.text)
        assert "script-src 'self'" in page.headers["content-security-policy"]
        assert c.get(f"{prefix}/assets/app.js").text == "console.log(1)"
        assert c.get(f"{prefix}/api/nothing-here").status_code == 404
        refused = TestClient(app).get(f"{prefix}/")
        assert refused.status_code == 401 and "frame-ancestors 'none'" in refused.headers["content-security-policy"]


def test_a_copy_whose_screens_are_not_built_shows_a_page_saying_how_to_build_them(tmp_path, demo):
    """A fresh copy of the code has no built screens: the browser gets a page in words with the two steps, never raw
    data."""
    ws = init_workspace(tmp_path / "ws", template=demo, git=False)
    cfg = load_config(ws.config_dir, env={})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    page = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}).get("/")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "npm --prefix web install" in page.text and "npm --prefix web run build" in page.text
    assert '"ui"' not in page.text
