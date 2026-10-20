"""Several accounts of one service at once (plugin API 0.3.82): a sign-in keeps one set of tokens per account, each
source reads with the account it names, signing one account out pauses only its sources, and a second sign-in starts
sources for the account it just added. The add-on's connector changes nothing: `context.access_token(name)` is the
token of the source's own account, and `context.account` is its address."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import engine.net
from engine import sign_in as flow
from engine import watch
from engine.config import load_config
from engine.connectors import ConnectorError
from engine.storage import Store
from tests.test_plugin_api_0329 import reopen
from tests.test_sign_in import N, landing
from tests.test_today_panels_jobs import FIXTURE, workspace

AUTH = f"https://{N['auth_host']}"

HELPERS = """
from pydantic import BaseModel
from engine.plugin_api import Poll

class InboxSettings(BaseModel):
    pass

def who(context):
    token = context.access_token("p18/service")
    return context.web.get("https://AUTH_HOST/me", headers={"Authorization": "Bearer " + token}).json()["mail"]

def poll_inbox(settings, state, context):
    token = context.access_token("p18/service")
    with open(context.workspace_root / "seen.txt", "a") as seen:
        seen.write(token + " " + str(context.account) + "\\n")
    return Poll([], {})

""".replace("AUTH_HOST", N["auth_host"])

CODE = FIXTURE.replace(
    "    registrar.job(",
    "    registrar.sign_in(\n"
    f'        "p18/service", label="The service", authorize_url="{AUTH}/authorize", token_url="{AUTH}/token",\n'
    '        scopes=["read"], account=who,\n'
    '        sources=[{"connector": "p18/inbox", "label": "Your inbox", "settings": {}}],\n'
    "    )\n"
    "    registrar.job(",
).replace(
    "def register(registrar):\n",
    HELPERS + "def register(registrar):\n"
    "    registrar.connector('p18/inbox', label='Inbox', settings=InboxSettings, poll=poll_inbox, reads='mail')\n",
)

ALICE, BOB = "alice@example.com", "bob@example.com"


def address_of(code: str) -> str:
    return re.sub(r"\d+$", "", code) + "@example.com"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A workspace whose add-on signs in to a fake service; a code "alice" or "bob" signs in that person ("alice2" is
    the same person again)."""
    ws, cfg, store = workspace(tmp_path, CODE)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["provides"]["sign_ins"] = ["p18/service"]
    manifest["provides"]["connectors"] = ["p18/inbox"]
    manifest["provides"]["connector_reads"] = {"p18/inbox": "mail"}
    manifest["requires"] = {"network": [N["auth_host"]], "secrets": ["client-id"]}
    path.write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["secrets"] = {"p18": {"client-id": "env:P18_CLIENT_ID"}}
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    monkeypatch.setenv("P18_CLIENT_ID", "app-123")

    def service(request):
        if request.url.path == "/me":
            token = request.headers["authorization"].removeprefix("Bearer tok-")
            return httpx.Response(200, json={"mail": address_of(token)})
        form = parse_qs(request.content.decode())
        if form["grant_type"] == ["authorization_code"]:
            code = form["code"][0]
            return httpx.Response(200, json={"access_token": f"tok-{code}", "expires_in": 3600, "refresh_token": "r"})
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(service))
    from api.app import create_app

    cfg, store = reopen(ws, cfg)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    return ws, c, cfg.server.base_path.rstrip("/") + "/api"


KEYS = lambda ws: ws.root / ".cockpit" / "keys" / "p18"  # noqa: E731


def sign_in(c, api, code):
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert "sign_in=done" in landing(c.get(f"{api}/sign-ins/callback", params={"state": state, "code": code}))


def sources(ws):
    return [s.model_dump(mode="json") for s in load_config(ws.config_dir, env={}).watch.sources]


def inboxes(ws):
    return {s["account"]: s for s in sources(ws) if s["connector"] == "p18/inbox"}


def read(ws, source_id):
    """Read a source now, as the watcher does; returns the result and what the connector saw."""
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        result = watch.refresh(ws, store, cfg, source_id)
        runs = store.read().find("watch_run", {"source": source_id})
        return result, runs[-1].data
    finally:
        store.close()


def seen(ws):
    path = ws.root / "seen.txt"
    return path.read_text().splitlines() if path.exists() else []


def test_two_accounts_of_one_sign_in_are_kept_apart(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    files = sorted(p.name for p in KEYS(ws).glob("sign-in-*"))
    assert files == sorted(f"sign-in-service--{flow.account_key(a)}.json" for a in (ALICE, BOB))
    assert all(oct((KEYS(ws) / f).stat().st_mode)[-3:] == "600" for f in files)
    row = c.get(f"{api}/sign-ins").json()[0]
    assert [(a["address"], a["status"]) for a in row["accounts"]] == [(ALICE, "signed_in"), (BOB, "signed_in")]
    assert row["status"] == "signed_in" and row["several"] is True
    assert json.loads((KEYS(ws) / files[0]).read_text())["access_token"].startswith("tok-")


def test_the_old_single_file_is_the_first_account_and_is_migrated(world):
    ws, c, api = world
    legacy = KEYS(ws) / "sign-in-service.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"access_token": "tok-alice", "expires_at": 9e9, "refresh_token": "r", "account": ALICE})
    )
    legacy.chmod(0o600)
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["status"] == "signed_in" and [a["address"] for a in row["accounts"]] == [ALICE]
    moved = KEYS(ws) / f"sign-in-service--{flow.account_key(ALICE)}.json"
    assert moved.is_file() and not legacy.exists() and oct(moved.stat().st_mode)[-3:] == "600"
    sign_in(c, api, "bob")
    assert [a["address"] for a in c.get(f"{api}/sign-ins").json()[0]["accounts"]] == [ALICE, BOB]


def test_an_old_file_whose_account_was_never_named_is_still_one_account(world):
    ws, c, api = world
    legacy = KEYS(ws) / "sign-in-service.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"access_token": "tok-carol", "expires_at": 9e9, "refresh_token": "r"}))
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["status"] == "signed_in" and [a["address"] for a in row["accounts"]] == [None]
    assert legacy.is_file()  # nothing to key it by: it stays where it is
    assert c.delete(f"{api}/sign-ins/p18/service?account={row['accounts'][0]['key']}").status_code == 200
    assert not legacy.exists()
    assert c.get(f"{api}/sign-ins").json()[0]["status"] == "signed_out"


def test_signing_in_with_a_named_account_replaces_one_kept_before_its_address_could_be_read(world):
    ws, c, api = world
    legacy = KEYS(ws) / "sign-in-service.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"access_token": "tok-old", "expires_at": 9e9, "refresh_token": "r"}))
    sign_in(c, api, "alice")
    assert not legacy.exists()
    assert [a["address"] for a in c.get(f"{api}/sign-ins").json()[0]["accounts"]] == [ALICE]


def test_each_source_reads_with_its_own_accounts_token(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    by_account = inboxes(ws)
    assert set(by_account) == {ALICE, BOB}  # signing in started a source for each account
    for address in (ALICE, BOB):
        result, run = read(ws, by_account[address]["id"])
        assert result.outcome in ("ok", "baseline"), run
    assert sorted(seen(ws)) == sorted([f"tok-alice {ALICE}", f"tok-bob {BOB}"])


def test_signing_one_account_out_pauses_only_its_sources(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    by_account = inboxes(ws)
    key = flow.account_key(ALICE)
    assert c.delete(f"{api}/sign-ins/p18/service?account={key}").status_code == 200
    row = c.get(f"{api}/sign-ins").json()[0]
    assert [a["address"] for a in row["accounts"]] == [BOB] and row["status"] == "signed_in"
    assert not (KEYS(ws) / f"sign-in-service--{key}.json").exists()
    result, run = read(ws, by_account[ALICE]["id"])
    assert result.outcome == "failed" and run["error_kind"] == "auth"
    assert ALICE in result.problem and "Sign in" in result.problem  # the existing line, naming the account
    result, run = read(ws, by_account[BOB]["id"])
    assert result.outcome in ("ok", "baseline"), run
    assert seen(ws) == [f"tok-bob {BOB}"]


def test_signing_every_account_out_forgets_them_all(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    assert c.delete(f"{api}/sign-ins/p18/service").status_code == 200
    assert not list(KEYS(ws).glob("sign-in-*"))
    assert c.get(f"{api}/sign-ins").json()[0]["status"] == "signed_out"


def test_a_second_sign_in_starts_sources_for_the_new_account_and_pins_the_old_ones(world):
    ws, c, api = world
    # A source made before accounts existed has none named; with one account it reads that one.
    legacy = KEYS(ws) / "sign-in-service.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"access_token": "tok-alice", "expires_at": 9e9, "refresh_token": "r", "account": ALICE})
    )
    config = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    config["sources"] = [
        *config.get("sources", []),
        {"id": "mine", "label": "My inbox", "connector": "p18/inbox", "settings": {}},
    ]
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(config))
    result, run = read(ws, "mine")
    assert result.outcome in ("ok", "baseline"), run
    assert seen(ws) == [f"tok-alice {ALICE}"]  # the only account, and context.account says so
    sign_in(c, api, "bob")
    by_account = inboxes(ws)
    assert by_account[ALICE]["id"] == "mine" and by_account[BOB]["label"] == "Your inbox"
    assert len([s for s in sources(ws) if s["connector"] == "p18/inbox"]) == 2


def test_the_same_address_twice_is_one_account(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "alice2")
    row = c.get(f"{api}/sign-ins").json()[0]
    assert [a["address"] for a in row["accounts"]] == [ALICE]
    assert len(list(KEYS(ws).glob("sign-in-*"))) == 1
    assert json.loads(next(KEYS(ws).glob("sign-in-*")).read_text())["access_token"] == "tok-alice2"
    assert len([s for s in sources(ws) if s["connector"] == "p18/inbox"]) == 1  # started once


def test_a_source_with_no_account_among_several_must_choose(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        context = store.plugins.connector_context("p18", ws.root)
        assert context.account is None  # two accounts and none chosen
        with pytest.raises(ConnectorError) as chosen:
            context.access_token("p18/service")
        assert chosen.value.kind == "no_access" and "choose" in chosen.value.detail
        named = store.plugins.connector_context("p18", ws.root, account=BOB)
        assert named.account == BOB and named.access_token("p18/service") == "tok-bob"
        with pytest.raises(ConnectorError) as gone:
            store.plugins.connector_context("p18", ws.root, account="nobody@example.com").access_token("p18/service")
        assert gone.value.kind == "auth" and "nobody@example.com" in gone.value.detail
    finally:
        store.close()


def test_the_source_form_offers_the_accounts_and_checks_the_one_chosen(world):
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    kind = next(k for k in c.get(f"{api}/watch/kinds").json() if k["name"] == "p18/inbox")
    assert kind["accounts"] == [ALICE, BOB]
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    refused = c.post(
        f"{api}/watch/sources",
        json={"connector": "p18/inbox", "label": "Second", "settings": {}, "fingerprint": fingerprint},
    )
    assert refused.status_code == 400 and "account" in refused.json()["detail"].lower()
    unknown = c.post(
        f"{api}/watch/sources",
        json={
            "connector": "p18/inbox",
            "label": "Second",
            "account": "nobody@example.com",
            "settings": {},
            "fingerprint": fingerprint,
        },
    )
    assert unknown.status_code == 400
    ok = c.post(
        f"{api}/watch/sources",
        json={"connector": "p18/inbox", "label": "Second", "account": BOB, "settings": {}, "fingerprint": fingerprint},
    )
    assert ok.status_code == 200, ok.text
    added = next(s for s in c.get(f"{api}/watch").json() if s["label"] == "Second")
    assert added["account"] == BOB
    changed = c.post(
        f"{api}/watch/sources/{added['id']}",
        json={"account": ALICE, "fingerprint": ok.json()["fingerprint"]},
    )
    assert changed.status_code == 200, changed.text
    assert next(s for s in c.get(f"{api}/watch").json() if s["id"] == added["id"])["account"] == ALICE


def test_the_test_kit_gives_a_connector_its_account():
    from engine.plugin_api.testing import connector_context

    context = connector_context(lambda asked: None, network=["api.example.com"], account=ALICE)
    assert context.account == ALICE
    assert connector_context(lambda asked: None, network=["api.example.com"]).account is None


def test_the_accounts_of_a_sign_in_are_listed_oldest_first_and_a_new_one_never_replaces_another(tmp_path):
    keys = tmp_path / "keys"
    s = flow.SignIn("p", "p/x", "X", f"{AUTH}/a", f"{AUTH}/t", ("read",), "client-id")
    flow.keep(keys, s, {"access_token": "1", "expires_at": 9e9, "account": ALICE, "signed_in_at": 10})
    flow.keep(keys, s, {"access_token": "2", "expires_at": 9e9, "account": BOB, "signed_in_at": 5})
    assert [a.address for a in flow.list_accounts(keys, s)] == [BOB, ALICE]
    assert flow.kept(keys, s)["access_token"] == "2"  # no account named: the first
    assert flow.kept(keys, s, ALICE.upper())["access_token"] == "1"  # an address is one account in any case
    assert flow.forget(keys, s, flow.account_key(BOB)) and [a.address for a in flow.list_accounts(keys, s)] == [ALICE]
    assert Path(keys).stat().st_mode & 0o077 == 0


def test_the_version_is_at_least_the_one_that_added_accounts():
    from engine.plugin_api import PLUGIN_API_VERSION

    assert tuple(int(n) for n in PLUGIN_API_VERSION.split(".")) >= (0, 3, 82)
