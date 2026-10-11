"""Which app registration a sign-in uses (plugin API 0.3.47): the workspace's references, else one the person pasted on
the Sign-ins row, else the add-on's own, so people can sign in without registering anything. Pasting starts the
sign-in over, and a pasted registration can be set aside and brought back."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import engine.net
from tests.test_plugin_api_0329 import reopen
from tests.test_sign_in import landing
from tests.test_today_panels_jobs import FIXTURE, workspace

N = yaml.safe_load((Path(__file__).parent / "fixtures" / "network" / "network.yaml").read_text())
AUTH = f"https://{N['auth_host']}"
CONSOLE = f"https://{N['other_host']}/console"

SIGNING = FIXTURE.replace(
    "    registrar.job(",
    "    registrar.sign_in(\n"
    f'        "p18/service", label="The service", authorize_url="{AUTH}/authorize", token_url="{AUTH}/token",\n'
    '        scopes=["read"], client_secret="client-secret",\n'
    '        default_client_id="addon-app", default_client_secret="addon-secret",\n'
    '        default_app_note="The service shows a warning page and asks again every week.",\n'
    f'        own_app_steps=["Make a project.", ("Make a client for an app on a computer.", "{CONSOLE}")],\n'
    "    )\n"
    "    registrar.job(",
)


def _workspace(tmp_path, monkeypatch, refs=None):
    ws, cfg, store = workspace(tmp_path, SIGNING)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["provides"]["sign_ins"] = ["p18/service"]
    manifest["requires"] = {"network": [N["auth_host"]], "secrets": ["client-id", "client-secret"]}
    path.write_text(yaml.safe_dump(manifest))
    if refs:
        settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
        settings["plugins"]["secrets"] = {"p18": refs}
        (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    asked = []

    def service(request):
        form = parse_qs(request.content.decode())
        asked.append(form)
        return httpx.Response(200, json={"access_token": "first", "expires_in": 3600, "refresh_token": "r1"})

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(service))
    cfg, store = reopen(ws, cfg)
    store.close()
    from api.app import create_app

    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    return ws, c, cfg.server.base_path.rstrip("/") + "/api", asked


def _sign_in(c, api):
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    query = parse_qs(urlsplit(url).query)
    back = c.get(f"{api}/sign-ins/callback", params={"state": query["state"][0], "code": "good"})
    assert "sign_in=done" in landing(back)
    return query


def test_the_add_ons_own_registration_lets_the_person_sign_in_at_once(tmp_path, monkeypatch):
    ws, c, api, asked = _workspace(tmp_path, monkeypatch)
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["ready"] and row["app"] == "add-on" and row["can_paste"] and row["needs_secret"]
    assert row["app_note"] == "The service shows a warning page and asks again every week."
    assert row["own_app_steps"] == [
        {"text": "Make a project.", "link": None},
        {"text": "Make a client for an app on a computer.", "link": CONSOLE},
    ]
    query = _sign_in(c, api)
    assert query["client_id"] == ["addon-app"]
    assert asked[-1]["client_id"] == ["addon-app"] and asked[-1]["client_secret"] == ["addon-secret"]


def test_a_pasted_registration_replaces_the_add_ons_and_can_be_set_aside(tmp_path, monkeypatch):
    ws, c, api, asked = _workspace(tmp_path, monkeypatch)
    _sign_in(c, api)
    keys = ws.root / ".cockpit" / "keys" / "p18"
    assert c.post(f"{api}/sign-ins/p18/service/app", json={"client_id": "mine"}).status_code == 400  # secret too
    row = c.post(f"{api}/sign-ins/p18/service/app", json={"client_id": " mine ", "client_secret": "shh"}).json()
    assert row["app"] == "pasted" and row["status"] == "signed_out" and row["app_note"] is None
    assert oct((keys / "client-id").stat().st_mode)[-3:] == "600" and (keys / "client-secret").read_text() == "shh\n"
    query = _sign_in(c, api)
    assert query["client_id"] == ["mine"] and asked[-1]["client_secret"] == ["shh"]

    row = c.post(f"{api}/sign-ins/p18/service/app/set-aside").json()
    assert row["app"] == "add-on" and row["set_aside"] and row["status"] == "signed_out"
    assert c.post(f"{api}/sign-ins/p18/service/app/set-aside").status_code == 404
    row = c.post(f"{api}/sign-ins/p18/service/app/bring-back").json()
    assert row["app"] == "pasted" and not row["set_aside"]
    assert json.loads(c.get(f"{api}/sign-ins").content)[0]["app"] == "pasted"


def test_the_workspaces_references_win_and_cant_be_pasted_over(tmp_path, monkeypatch):
    monkeypatch.setenv("P18_ID", "from-settings")
    monkeypatch.setenv("P18_SECRET", "settings-secret")
    refs = {"client-id": "env:P18_ID", "client-secret": "env:P18_SECRET"}
    ws, c, api, asked = _workspace(tmp_path, monkeypatch, refs)
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["app"] == "workspace" and not row["can_paste"]
    assert c.post(f"{api}/sign-ins/p18/service/app", json={"client_id": "x", "client_secret": "y"}).status_code == 409
    query = _sign_in(c, api)
    assert query["client_id"] == ["from-settings"] and asked[-1]["client_secret"] == ["settings-secret"]


@pytest.mark.parametrize(
    "extra, problem",
    [
        ({"default_client_secret": "s"}, "comes with default_client_id"),
        ({"default_client_id": " "}, "not empty"),
        ({"own_app_steps": [("Open it.", "http" + "://example.com")]}, "https"),
        ({"own_app_steps": ["A step."] * 13}, "up to 12"),
    ],
)
def test_a_sign_ins_own_registration_settings_are_checked(extra, problem):
    from engine.plugin_api import Registrar

    registrar = Registrar("p18", {}, None)
    with pytest.raises(ValueError, match=problem):
        registrar.sign_in("p18/x", label="X", authorize_url="a", token_url="t", scopes=["read"], **extra)
