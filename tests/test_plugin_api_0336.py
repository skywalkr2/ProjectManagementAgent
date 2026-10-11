"""Plugin API 0.3.36: a sign-in says what it asks before the person leaves, names the signed-in account, shows what
wasn't allowed, says at once (and once) when the service refuses to renew it, withdraws access on sign-out, keeps the
service's refusal code, and has a setup step of its own."""

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import engine.net
from tests.test_plugin_api_0329 import reopen
from tests.test_today_panels_jobs import FIXTURE, workspace

N = yaml.safe_load((Path(__file__).parent / "fixtures" / "network" / "network.yaml").read_text())
AUTH = f"https://{N['auth_host']}"

SIGNING = FIXTURE.replace(
    "def register(registrar):\n",
    "def who(context):\n"
    f'    me = "{AUTH}/me"\n'
    '    answer = context.web.get(me, headers={"Authorization": "Bearer " + context.access_token("p18/service")})\n'
    '    return answer.json()["name"]\n\n'
    "def register(registrar):\n",
).replace(
    "    registrar.job(",
    "    registrar.sign_in(\n"
    f'        "p18/service", label="The service", authorize_url="{AUTH}/authorize", token_url="{AUTH}/token",\n'
    '        scopes=["read", "offline"], allows=["Read your goals"], account=who,\n'
    f'        revoke_url="{AUTH}/revoke",\n'
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
        path = urlsplit(str(request.url)).path
        form = parse_qs(request.content.decode()) if request.method == "POST" else {}
        asked.append((path, form))
        if path == "/me":
            ok = request.headers.get("authorization") == "Bearer first"
            return httpx.Response(200, json={"name": "Pat at example"}) if ok else httpx.Response(401)
        if path == "/revoke":
            return httpx.Response(200)
        if form.get("grant_type") == ["authorization_code"]:
            return httpx.Response(
                200, json={"access_token": "first", "expires_in": 3600, "refresh_token": "r1", "scope": "read"}
            )
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(service))
    cfg, store = reopen(ws, cfg)
    yield ws, cfg, store, asked
    store.close()


def sign_in(c, api):
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    return c.get(f"{api}/sign-ins/callback", params={"state": state, "code": "good"})


def test_the_row_says_what_is_asked_names_the_account_and_what_was_not_allowed(signing):
    from api.app import create_app
    from engine import setup

    ws, cfg, store, asked = signing
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["allows"] == ["Read your goals"] and row["account"] is None and row["missing"] == []
    step = next(s for s in setup.steps(ws, cfg, store) if s.sign_in == "p18/service")
    assert not step.done and step.explanation == "Read your goals"
    assert "sign_in=done" in sign_in(c, api).headers["location"]
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["account"] == "Pat at example" and row["missing"] == ["offline"]
    assert next(s for s in setup.steps(ws, cfg, store) if s.sign_in == "p18/service").done
    assert store.plugins.connector_context("p18", ws.root).granted("p18/service") == {"read"}
    assert c.delete(f"{api}/sign-ins/p18/service").status_code == 200
    revoked = next(form for path, form in asked if path == "/revoke")
    assert revoked["token"] == ["r1"] and revoked["token_type_hint"] == ["refresh_token"]


def test_a_refused_renewal_shows_at_once_and_asks_once(signing):
    from api.app import create_app
    from engine.connectors import ConnectorError

    ws, cfg, store, _ = signing
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    sign_in(c, api)
    kept = ws.root / ".cockpit" / "keys" / "p18" / "sign-in-service.json"
    kept.write_text(json.dumps({**json.loads(kept.read_text()), "expires_at": time.time() - 1}))
    context = store.plugins.connector_context("p18", ws.root)
    for _ in range(2):
        with pytest.raises(ConnectorError) as refused:
            context.access_token("p18/service")
        assert refused.value.kind == "auth"
    assert c.get(f"{api}/sign-ins").json()[0]["status"] == "expired"
    questions = [q for q in store.read().list("question") if (q.data.get("resolves") or {}).get("kind") == "sign_in"]
    assert len(questions) == 1 and questions[0].data["status"] == "open"
    sign_in(c, api)
    assert store.read().get("question", questions[0].id).data["status"] == "dropped"
    assert c.get(f"{api}/sign-ins").json()[0]["status"] == "signed_in"


def test_the_services_refusal_code_comes_back_to_the_screen(signing):
    from api.app import create_app

    ws, cfg, store, _ = signing
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    back = c.get(
        f"{api}/sign-ins/callback",
        params={"state": state, "error": "consent_required", "error_description": "An administrator must approve."},
    )
    query = parse_qs(urlsplit(back.headers["location"]).query)
    assert query["sign_in"] == ["refused"] and query["error"] == ["consent_required"]
    assert query["detail"] == ["An administrator must approve."]
