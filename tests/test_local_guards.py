"""Local mode's guards against other web pages (design 12.1): the app answers only to its own address, refuses changes
that another site asks for, and never listens beyond this computer. The addresses come from the app's own settings and
the fictional hosts file, so no address is written out here, and the product allows no test address."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import COOKIE, create_app
from engine.cli import main
from engine.config import load_config
from engine.local_guards import allowed_hosts, allowed_origins, is_loopback, local_address_problem
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "guard-test-token"
HOSTS = yaml.safe_load((Path(__file__).parent / "fixtures" / "network" / "network.yaml").read_text())
FOREIGN = HOSTS["evil_host"]
SCHEME = "http" + "://"
SECURE = "https" + "://"


def _app(tmp_path, **flags):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={}, flags=flags)
    return ws, cfg, create_app(ws, cfg, TOKEN, start_worker=False)


@pytest.fixture
def local(tmp_path):
    ws, cfg, app = _app(tmp_path)
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}), cfg.server


def _reached(response) -> bool:
    """The request got past the guards and the token check (the answer is the route's own)."""
    return response.status_code not in (401, 403)


def _own(server, name="127.0.0.1"):
    return f"{name}:{server.port}"


# ---- the Host header ------------------------------------------------------------------------------


def test_a_foreign_host_is_refused_on_an_api_route_the_health_check_and_the_page(local):
    c, server = local
    wrong = {"Host": f"{FOREIGN}:{server.port}"}
    for path in ("/api/runtime-config", "/api/health", "/"):
        refused = c.get(path, headers=wrong)
        assert refused.status_code == 403, path
        assert "error" in refused.json() and "isn't the app's" in refused.json()["error"]
        assert "content-security-policy" in refused.headers  # the outer headers still apply to a refusal
        assert c.get(path, headers={"Host": _own(server)}).status_code == 200, path


def test_a_foreign_host_is_refused_even_with_the_token_in_the_link(local):
    c, server = local
    refused = c.get(f"/?token={TOKEN}", headers={"Host": FOREIGN}, follow_redirects=False)
    assert refused.status_code == 403 and COOKIE not in refused.headers.get("set-cookie", "")


@pytest.mark.parametrize("name", ["localhost", "127.0.0.1", "[::1]"])
def test_the_loopback_names_with_the_right_port_pass(local, name):
    c, server = local
    assert c.get("/api/runtime-config", headers={"Host": _own(server, name)}).status_code == 200
    assert c.get("/api/health", headers={"Host": _own(server, name)}).status_code == 200


def test_the_configured_address_passes_and_the_wrong_port_is_refused(tmp_path):
    ws, cfg, app = _app(tmp_path, **{"server.host": "127.0.0.2", "server.port": 9123})
    c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    assert c.get("/api/health", headers={"Host": "127.0.0.2:9123"}).status_code == 200
    assert c.get("/api/health", headers={"Host": "localhost:9123"}).status_code == 200
    for wrong in ("127.0.0.2:9124", "localhost:8765", "127.0.0.2", "localhost"):
        assert c.get("/api/health", headers={"Host": wrong}).status_code == 403, wrong


def test_a_host_without_a_port_passes_only_when_the_port_is_80(tmp_path):
    ws, cfg, app = _app(tmp_path, **{"server.port": 80})
    c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    assert c.get("/api/health", headers={"Host": "localhost"}).status_code == 200
    assert c.get("/api/health", headers={"Host": "localhost:80"}).status_code == 200
    assert c.get("/api/health", headers={"Host": "localhost:8765"}).status_code == 403


def test_the_host_is_compared_without_regard_to_case(local):
    c, server = local
    assert c.get("/api/health", headers={"Host": f"LocalHost:{server.port}"}).status_code == 200


def test_the_guards_hold_under_a_nested_base_path(tmp_path):
    ws, cfg, app = _app(tmp_path, **{"server.base_path": "/tools/cockpit"})
    c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    assert c.get("/tools/cockpit/api/health").status_code == 200
    assert c.get("/tools/cockpit/api/health", headers={"Host": FOREIGN}).status_code == 403
    own = {"Origin": SCHEME + _own(cfg.server)}
    assert _reached(c.post("/tools/cockpit/api/handin", json={"note": "", "pasted": " "}, headers=own))
    other = {"Origin": SCHEME + FOREIGN}
    assert c.post("/tools/cockpit/api/handin", json={"note": "", "pasted": " "}, headers=other).status_code == 403


# ---- the Origin and the browser's own marking ---------------------------------------------------------------------


EMPTY_HAND_IN = {"note": "", "pasted": "  "}  # answered 409 by the route itself, with nothing written


def test_a_post_from_a_foreign_origin_is_refused_even_with_a_valid_token(local):
    c, server = local
    refused = c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Origin": SCHEME + FOREIGN})
    assert refused.status_code == 403 and "another web page" in refused.json()["error"]
    opaque = c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Origin": "null"})
    assert opaque.status_code == 403
    secure = c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Origin": SECURE + _own(server)})
    assert secure.status_code == 403  # the same address over another scheme isn't the app's page


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_every_state_changing_method_is_checked(local, method):
    c, server = local
    refused = getattr(c, method)("/api/handin", headers={"Origin": SCHEME + FOREIGN})
    assert refused.status_code == 403


def test_a_post_from_the_apps_own_origin_passes(local):
    c, server = local
    for name in ("127.0.0.1", "localhost", "[::1]"):
        headers = {"Origin": SCHEME + _own(server, name), "Host": _own(server, name)}
        assert c.post("/api/handin", json=EMPTY_HAND_IN, headers=headers).status_code == 409


def test_a_request_the_browser_marks_cross_site_is_refused(local):
    c, server = local
    refused = c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Sec-Fetch-Site": "cross-site"})
    assert refused.status_code == 403
    for fine in ("same-origin", "none"):
        assert c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Sec-Fetch-Site": fine}).status_code == 409


def test_a_post_with_no_origin_and_a_valid_token_passes_and_without_the_token_is_refused(local, tmp_path):
    c, server = local
    assert "origin" not in c.headers
    assert c.post("/api/handin", json=EMPTY_HAND_IN).status_code == 409
    bare = TestClient(_app(tmp_path / "again")[2])
    assert bare.post("/api/handin", json=EMPTY_HAND_IN).status_code == 401  # not from a browser, still needs the token


def test_a_get_with_a_foreign_origin_is_not_refused_by_the_origin_rule(local):
    c, server = local
    assert c.get("/api/runtime-config", headers={"Origin": SCHEME + FOREIGN}).status_code == 200
    assert c.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_no_permissive_cors_headers_are_sent(local):
    c, server = local
    answer = c.get("/api/runtime-config", headers={"Origin": SCHEME + FOREIGN})
    assert not [name for name in answer.headers if name.lower().startswith("access-control-")]


def test_the_sign_in_callback_still_works_without_the_cookie(tmp_path):
    ws, cfg, app = _app(tmp_path)
    bare = TestClient(app, follow_redirects=False)
    answer = bare.get("/api/sign-ins/callback", params={"state": "made-up", "code": "x"})
    assert _reached(answer) and answer.status_code < 500
    foreign = bare.get("/api/sign-ins/callback", params={"state": "made-up", "code": "x"}, headers={"Host": FOREIGN})
    assert foreign.status_code == 403
    # The service's page sends the browser here, so the request carries a foreign origin: a GET, so it still works.
    from_service = bare.get(
        "/api/sign-ins/callback",
        params={"state": "made-up", "code": "x"},
        headers={"Origin": SECURE + HOSTS["auth_host"], "Sec-Fetch-Site": "cross-site"},
    )
    assert _reached(from_service)


# ---- hosted mode ---------------------------------------------------------------------------------------------------


def _hosted(tmp_path, public_url):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    update = {"mode": "hosted", "public_url": public_url}
    cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=update)}, sources={})
    return cfg, TestClient(create_app(ws, cfg, TOKEN, start_worker=False), headers={"Authorization": f"Bearer {TOKEN}"})


def test_hosted_mode_allows_only_the_public_urls_host(tmp_path):
    public = SECURE + HOSTS["app_host"]
    cfg, c = _hosted(tmp_path, public)
    assert c.get("/api/health").status_code == 200  # the client's own address is the public one
    assert c.get("/api/health", headers={"Host": HOSTS["app_host"] + ":443"}).status_code == 200
    for name in ("localhost", "127.0.0.1", "[::1]", FOREIGN):
        assert c.get("/api/health", headers={"Host": f"{name}:{cfg.server.port}"}).status_code == 403, name
        assert c.get("/api/health", headers={"Host": name}).status_code == 403, name
    assert c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Origin": public}).status_code == 409
    assert c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Origin": SCHEME + HOSTS["app_host"]}).status_code == 403
    assert c.post("/api/handin", json=EMPTY_HAND_IN, headers={"Origin": SCHEME + "localhost"}).status_code == 403


def test_hosted_mode_with_no_public_url_allows_nothing(tmp_path):
    cfg, c = _hosted(tmp_path, None)
    for name in ("localhost", "127.0.0.1", f"localhost:{cfg.server.port}"):
        assert c.get("/api/health", headers={"Host": name}).status_code == 403
    assert allowed_hosts(cfg.server) == set() and allowed_origins(cfg.server) == set()


def test_a_public_url_with_its_own_port_is_matched_with_that_port(tmp_path):
    public = SECURE + HOSTS["app_host"] + ":8443"
    cfg, c = _hosted(tmp_path, public)
    assert allowed_hosts(cfg.server) == {HOSTS["app_host"] + ":8443"}
    assert allowed_origins(cfg.server) == {public}


# ---- the listen address --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "127.1.2.3", "::1", "[::1]", "localhost", "LOCALHOST"])
def test_loopback_addresses_are_accepted(host):
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "10.0.0.5", HOSTS["app_host"], "", "not an address"])
def test_other_addresses_and_names_are_not_loopback(host):
    assert not is_loopback(host)


def test_local_mode_refuses_a_listen_address_beyond_this_computer(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    server = load_config(ws.config_dir, env={}, flags={"server.host": "0.0.0.0"}).server
    problem = local_address_problem(server)
    assert problem and "hosted mode" in problem and "isn't available yet" in problem and "default" in problem
    for host in ("127.0.0.1", "::1", "localhost"):
        assert local_address_problem(load_config(ws.config_dir, env={}, flags={"server.host": host}).server) is None


def test_serve_refuses_to_start_on_another_address_and_says_why(tmp_path, capsys):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    assert main(["serve", "--workspace", str(ws.root), "--host", "0.0.0.0", "--no-open"]) == 1
    message = capsys.readouterr().err
    assert "hosted mode" in message and "0.0.0.0" in message


def test_demo_refuses_to_start_on_another_address_and_says_why(tmp_path, capsys):
    folder = tmp_path / "demo"
    ws = init_workspace(folder, template=DEMO_B, git=False)
    path = ws.config_dir / "server.yaml"
    settings = yaml.safe_load(path.read_text()) or {}
    settings["host"] = "192.168.1.20"
    path.write_text(yaml.safe_dump(settings))
    assert main(["demo", str(folder), "--no-open"]) == 1
    assert "hosted mode" in capsys.readouterr().err
