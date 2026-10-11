"""Signing in to a service as the person (plugin API 0.3.33): a plugin declares the service's sign-in; the core opens
its page with PKCE, takes the answer at its own callback, keeps the tokens on this computer, renews them, and gives
the plugin's connector a current token. A sign-in that can't be renewed reads as an auth failure."""

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import engine.net
from engine.connectors import ConnectorError
from tests.test_plugin_api_0329 import reopen
from tests.test_today_panels_jobs import FIXTURE, workspace

N = yaml.safe_load((Path(__file__).parent / "fixtures" / "network" / "network.yaml").read_text())
AUTH = f"https://{N['auth_host']}"

SIGNING = FIXTURE.replace(
    "    registrar.job(",
    "    registrar.sign_in(\n"
    f'        "p18/service", label="The service", authorize_url="{AUTH}/authorize", token_url="{AUTH}/token",\n'
    '        scopes=["read", "offline"], params={"access_type": "offline"},\n'
    "    )\n"
    "    registrar.job(",
)


@pytest.fixture
def signing(tmp_path, monkeypatch):
    ws, cfg, store = workspace(tmp_path, SIGNING)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["provides"]["sign_ins"] = ["p18/service"]
    manifest["requires"] = {"network": [N["auth_host"]], "secrets": ["client-id"]}
    path.write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["secrets"] = {"p18": {"client-id": "env:P18_CLIENT_ID"}}
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    monkeypatch.setenv("P18_CLIENT_ID", "app-123")
    asked = []

    def service(request):
        form = parse_qs(request.content.decode())
        asked.append(form)
        if form["grant_type"] == ["authorization_code"] and form["code"] == ["good"]:
            return httpx.Response(200, json={"access_token": "first", "expires_in": 3600, "refresh_token": "r1"})
        if form["grant_type"] == ["refresh_token"] and form["refresh_token"] == ["r1"]:
            return httpx.Response(200, json={"access_token": "second", "expires_in": 3600})
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(service))
    cfg, store = reopen(ws, cfg)
    yield ws, cfg, store, asked
    store.close()


def test_the_person_signs_in_and_the_connector_gets_a_token(signing):
    from api.app import create_app

    ws, cfg, store, asked = signing
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    listed = c.get(f"{api}/sign-ins").json()
    assert listed[0]["status"] == "signed_out" and listed[0]["ready"] is True
    assert listed[0]["callback"].endswith(f"{cfg.server.base_path.rstrip('/')}/api/sign-ins/callback")
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    query = parse_qs(urlsplit(url).query)
    assert url.startswith(f"{AUTH}/authorize?") and query["client_id"] == ["app-123"]
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["read offline"]
    assert query["access_type"] == ["offline"]
    back = c.get(f"{api}/sign-ins/callback", params={"state": query["state"][0], "code": "good"})
    assert back.status_code == 303 and "sign_in=done" in back.headers["location"]
    assert asked[-1]["code_verifier"] and asked[-1]["redirect_uri"] == query["redirect_uri"]
    kept = ws.root / ".cockpit" / "keys" / "p18" / "sign-in-service.json"
    assert json.loads(kept.read_text())["refresh_token"] == "r1" and oct(kept.stat().st_mode)[-3:] == "600"
    assert c.get(f"{api}/sign-ins").json()[0]["status"] == "signed_in"
    again = c.get(f"{api}/sign-ins/callback", params={"state": query["state"][0], "code": "good"})
    assert "sign_in=expired" in again.headers["location"]  # a state is used once

    context = store.plugins.connector_context("p18", ws.root)
    assert context.access_token("p18/service") == "first"
    tokens = json.loads(kept.read_text())
    kept.write_text(json.dumps({**tokens, "expires_at": time.time() + 30}))  # about to run out: renewed first
    assert context.access_token("p18/service") == "second"
    assert json.loads(kept.read_text())["refresh_token"] == "r1"  # kept when the service doesn't send a new one

    assert c.delete(f"{api}/sign-ins/p18/service").status_code == 200
    with pytest.raises(ConnectorError) as signed_out:
        context.access_token("p18/service")
    assert signed_out.value.kind == "auth"


def test_a_withdrawn_sign_in_asks_the_person_again(signing):
    from engine import sign_in as flow

    ws, cfg, store, _ = signing
    s = store.plugins.sign_ins()["p18/service"]
    keys = ws.root / ".cockpit" / "keys" / "p18"
    flow.keep(keys, s, {"access_token": "old", "expires_at": time.time() - 5, "refresh_token": "revoked"})
    with pytest.raises(ConnectorError) as withdrawn:
        store.plugins.connector_context("p18", ws.root).access_token("p18/service")
    assert withdrawn.value.kind == "auth"


def test_a_sign_in_must_use_declared_https_hosts_and_secrets(tmp_path):
    from engine.sign_in import SignIn, check_addresses

    s = SignIn("p", "p/x", "X", f"{AUTH}/a", f"http://{N['auth_host']}/t", ("read",), "client-id")
    with pytest.raises(ValueError, match="https"):
        check_addresses(s, [N["auth_host"]])
    with pytest.raises(ValueError):
        check_addresses(SignIn("p", "p/x", "X", f"{AUTH}/a", f"{AUTH}/t", ("read",), "client-id"), [N["other_host"]])
