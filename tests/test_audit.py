"""The audit trail: signing in, signing out and turning an add-on on or off each leave an `audit_entry`, without ever
holding a token, a secret or the account's name."""

import json
from urllib.parse import parse_qs, urlsplit

import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from tests.test_settings_undo import undo
from tests.test_setup import client, make
from tests.test_sign_in import signing  # noqa: F401  (a fixture)


def entries(ws, cfg):
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        return [e.data for e in store.read().list("audit_entry")]
    finally:
        store.close()


def spare_add_on(ws):
    folder = ws.root / "plugins" / "spare"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "spare",
                "version": "0.1.0",
                "plugin_api": ">=0.3,<0.4",
                "description": "An add-on left off",
                "entry": "spare:register",
                "config_schema": "spare:Config",
            }
        )
    )


def test_turning_an_add_on_on_and_off_and_undoing_it_is_recorded(tmp_path):
    ws, cfg, store = make(tmp_path)
    spare_add_on(ws)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    on = c.post(f"{api}/packs/spare/on", json={"fingerprint": fingerprint})
    off = c.post(f"{api}/packs/spare/off", json={"fingerprint": on.json()["fingerprint"]})
    assert on.status_code == off.status_code == 200
    undone = undo(c, api, off.json())  # the screen's Undo of the off: saves the earlier list again
    assert undone.status_code == 200, undone.text
    found = [(e["kind"], e["subject"]) for e in entries(ws, cfg)]
    assert found == [("plugin_on", "spare"), ("plugin_off", "spare"), ("plugin_on", "spare")]
    assert all(e["at"] for e in entries(ws, cfg))


def test_leaving_an_add_on_that_is_off_off_records_nothing(tmp_path):
    ws, cfg, store = make(tmp_path)
    spare_add_on(ws)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    assert c.post(f"{api}/packs/spare/off", json={"fingerprint": fingerprint}).status_code == 200
    assert entries(ws, cfg) == []


def test_applying_a_template_records_each_add_on_it_turned_on(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    from engine import templates
    from engine.config import load_config

    before = set(load_config(ws.config_dir, env={}).workspace.plugins.enabled)
    template = next(t for t in templates.shipped() if t["adds"])
    done = c.post(f"{api}/templates/apply", json={"id": template["id"]})
    assert done.status_code == 200, done.text
    turned_on = set(load_config(ws.config_dir, env={}).workspace.plugins.enabled) - before
    assert {e["subject"] for e in entries(ws, cfg) if e["kind"] == "plugin_on"} == turned_on


def test_signing_in_and_out_is_recorded_without_a_token_or_the_account(signing):  # noqa: F811
    ws, cfg, store, _ = signing
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    assert entries(ws, cfg) == []  # starting is not signing in
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert c.get(f"{api}/sign-ins/callback", params={"state": state, "code": "wrong"}).status_code == 200
    assert entries(ws, cfg) == []  # a refused sign-in is not a sign-in
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    c.get(f"{api}/sign-ins/callback", params={"state": state, "code": "good"})
    assert c.delete(f"{api}/sign-ins/p18/service").status_code == 200
    assert c.delete(f"{api}/sign-ins/p18/service").status_code == 200  # signing out twice records once
    found = entries(ws, cfg)
    assert [(e["kind"], e["subject"], e["label"]) for e in found] == [
        ("sign_in", "p18/service", "The service"),
        ("sign_out", "p18/service", "The service"),
    ]
    text = json.dumps(found)
    for secret in ("first", "r1", "app-123", "good"):
        assert secret not in text


def test_changing_the_app_registration_of_a_signed_in_service_is_a_sign_out(tmp_path, monkeypatch):
    from tests.test_sign_in_app import _sign_in, _workspace

    ws, c, api, _ = _workspace(tmp_path, monkeypatch)
    _sign_in(c, api)
    assert (
        c.post(f"{api}/sign-ins/p18/service/app", json={"client_id": "mine", "client_secret": "shh"}).status_code == 200
    )
    c.post(f"{api}/sign-ins/p18/service/app/set-aside")  # signed out already: nothing more to lose
    found = entries(ws, ws.config(env={}))
    assert [(e["kind"], e["detail"]) for e in found] == [
        ("sign_in", None),
        ("sign_out", "The app registration it used was changed."),
    ]
    assert "shh" not in json.dumps(found) and "mine" not in json.dumps(found)
