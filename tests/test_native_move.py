"""A saved account moves to its service's own connection only on the person's yes (design 6.16): the line on Today
for an account on the generic connection to a service that has its own, a read-back of the identity the new
connection signs in as, the account check on the new connection before anything is written, Undo, and Not now
remembered. The service, its address and its adapter are read from the catalog fixture, so no service is named here;
nothing calls a network."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai import native_move
from engine.ai.adapters.stub import StubAdapter
from engine.ai.task import AiError
from engine.config import load_config
from engine.setup import known_endpoints
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

CLAIMS = yaml.safe_load((Path(__file__).parent / "fixtures" / "ai" / "catalog-claims.yaml").read_text("utf-8"))
NATIVE = CLAIMS["native_adapter"]
SERVICE = next(e for e in known_endpoints() if e["id"] == NATIVE["entry"])
GENERIC = native_move.GENERIC
OLD_ADDRESS = NATIVE["base_url"] + "/v1"
KEY = "key-0123456789-wxyz"
OTHER_ENTRY = next(e for e in known_endpoints() if e["adapter"] == GENERIC and e["base_url"].startswith("https://"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A workspace with an account on the generic connection to the service that has its own, tiers with different
    efforts on it, an account on a service with no native connection, and one already on the native connection."""
    monkeypatch.setenv("OLD_KEY", KEY)
    monkeypatch.setenv("NATIVE_KEY", KEY)
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    raw = yaml.safe_load(path.read_text())
    models = {"default": "model-a", "harder": "model-b"}
    raw["providers"].update(
        {
            "old": {"adapter": GENERIC, "base_url": OLD_ADDRESS, "auth": "env:OLD_KEY", "models": models},
            "plain": {"adapter": GENERIC, "base_url": OTHER_ENTRY["base_url"], "auth": "env:OLD_KEY", "models": models},
            "own": {
                "adapter": NATIVE["adapter"],
                "base_url": NATIVE["base_url"],
                "auth": "env:NATIVE_KEY",
                "models": models,
            },
        }
    )
    raw["tiers"]["routine"] = {"use": "old/default", "fallback": [], "escalate_to": "deep", "effort": "low"}
    raw["tiers"]["deep"] = {"use": "old/harder", "effort": "high"}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer t"
    return ws, client


class Calls:
    """The adapters the check made, in place of real ones: each answers like the stand-in, or fails as told."""

    def __init__(self, fail: AiError | None = None, snapshot=lambda: ""):
        self.fail, self.made, self.ran, self.at_first_call, self.ai_yaml = fail, [], [], None, snapshot

    def __call__(self, name, settings, secret):
        self.made.append((name, settings.base_url, secret))
        calls = self

        class Fake(StubAdapter):
            def run(self, task, model):
                if calls.at_first_call is None:
                    calls.at_first_call = calls.ai_yaml()
                calls.ran.append((name, task.effort, model))
                if calls.fail is not None:
                    raise calls.fail
                return StubAdapter(settings).run(task, model)

        return Fake(settings)


def base(client, ws):
    return load_config(ws.config_dir, env={}).server.base_path.rstrip("/") + "/api"


def fingerprint(client, ws):
    return client.get(f"{base(client, ws)}/settings").json()["fingerprint"]


def lines(ws, kind="account_move"):
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        return [x for x in queue(ws, store, cfg, datetime.now(UTC)) if x.kind == kind]
    finally:
        store.close()


def provider(ws, name):
    return load_config(ws.config_dir, env={}).ai.providers[name]


def test_only_an_account_on_the_generic_connection_of_a_service_with_its_own_gets_a_line(env):
    ws, _client = env
    found = lines(ws)
    assert [(x.account, x.group, x.subject) for x in found] == [("old", "decide", SERVICE["name"])]
    # One already on the native connection, one on a service with none, and the stand-in have no line.
    assert native_move.service_of(provider(ws, "own"), known_endpoints()) is None
    assert native_move.service_of(provider(ws, "plain"), known_endpoints()) is None
    assert native_move.service_of(provider(ws, "stub"), known_endpoints()) is None


def test_the_read_back_says_the_same_key_masked_the_same_address_and_the_account_name(env):
    ws, client = env
    got = client.get(f"{base(client, ws)}/ai/accounts/old/move")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["key_ending"] == KEY[-4:] and body["key_known"] and not body["key_differs"]
    assert KEY[:-4] not in got.text and KEY not in got.text
    assert body["address"] == body["address_was"] and not body["address_differs"]
    assert body["service"] == SERVICE["name"] and body["account"] == "old"
    assert client.get(f"{base(client, ws)}/ai/accounts/own/move").status_code == 404
    assert client.get(f"{base(client, ws)}/ai/accounts/plain/move").status_code == 404


def test_the_read_back_says_plainly_when_the_key_would_differ_or_can_not_be_read(monkeypatch):
    monkeypatch.setenv("A_KEY", KEY)
    monkeypatch.setenv("B_KEY", "another-key-0000-abcd")
    from engine.config.schema import ProviderSettings

    account = ProviderSettings(adapter=GENERIC, base_url=OLD_ADDRESS, auth="env:A_KEY", models={"d": "m"})
    same = native_move.readback(account, "old", SERVICE, None)
    assert same.key_ending == KEY[-4:] and not same.key_differs
    monkeypatch.setattr(native_move, "planned", lambda provider, entry: {"adapter": "x", "auth": "env:B_KEY"})
    other = native_move.readback(account, "old", SERVICE, None)
    monkeypatch.undo()
    monkeypatch.setenv("A_KEY", KEY)
    assert other.key_differs and other.key_ending == "abcd"
    monkeypatch.delenv("A_KEY")
    monkeypatch.setenv("B_KEY", "x")
    gone = native_move.readback(account, "old", SERVICE, None)
    assert not gone.key_known and gone.key_ending == ""
    short = ProviderSettings(adapter=GENERIC, base_url=OLD_ADDRESS, auth="env:S_KEY", models={"d": "m"})
    monkeypatch.setenv("S_KEY", "tiny")
    assert native_move.readback(short, "s", SERVICE, None).key_ending == ""


def test_the_move_keeps_what_the_person_set_and_changes_only_the_connection(env):
    ws, _ = env
    mine = provider(ws, "old").model_copy(update={"send_temperature": True})
    mine = type(mine).model_validate({**mine.model_dump(), "send_temperature": True})
    changes = native_move.planned(mine, SERVICE)
    assert changes["adapter"] == NATIVE["adapter"] and changes["base_url"] == NATIVE["base_url"]
    assert "send_temperature" not in changes, "a setting the account set itself stays"
    assert "auth" not in changes and "models" not in changes


def test_move_runs_the_check_on_the_new_connection_first_and_only_a_passed_check_writes_it(env, monkeypatch):
    ws, client = env
    calls = Calls(snapshot=lambda: (ws.config_dir / "ai.yaml").read_text())
    monkeypatch.setattr(native_move, "make_adapter", calls)
    before = (ws.config_dir / "ai.yaml").read_text()
    done = client.post(f"{base(client, ws)}/ai/accounts/old/move", json={"fingerprint": fingerprint(client, ws)})
    assert done.status_code == 200, done.text
    assert done.json()["moved"] is True and done.json()["saved"]["changes"]
    # The check ran on the native adapter and the service's own address, with every tier's exact effort, and nothing
    # was written until it had passed.
    assert {name for name, _url, _key in calls.made} == {NATIVE["adapter"]}
    assert {url for _n, url, _k in calls.made} == {NATIVE["base_url"]}
    assert {effort for _n, effort, _m in calls.ran if effort} == {"low", "high"}
    assert calls.at_first_call == before
    now = provider(ws, "old")
    assert now.adapter == NATIVE["adapter"] and now.base_url == NATIVE["base_url"] and now.auth == "env:OLD_KEY"
    assert lines(ws) == [], "the line goes once the account is moved"


def test_a_failed_check_writes_nothing_and_says_why(env, monkeypatch):
    ws, client = env
    monkeypatch.setattr(native_move, "make_adapter", Calls(AiError("auth", "key refused")))
    before = (ws.config_dir / "ai.yaml").read_text()
    done = client.post(f"{base(client, ws)}/ai/accounts/old/move", json={"fingerprint": fingerprint(client, ws)})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["moved"] is False and body["saved"] is None and body["detail"]
    assert (ws.config_dir / "ai.yaml").read_text() == before
    assert provider(ws, "old").adapter == GENERIC
    assert [x.account for x in lines(ws)] == ["old"], "the line stays, since nothing moved"


def test_no_network_is_not_a_pass(env, monkeypatch):
    ws, client = env
    monkeypatch.setattr(native_move, "make_adapter", Calls(AiError("offline", "no connection")))
    done = client.post(f"{base(client, ws)}/ai/accounts/old/move", json={"fingerprint": fingerprint(client, ws)})
    assert done.json()["moved"] is False
    assert provider(ws, "old").adapter == GENERIC


def test_undo_puts_the_account_back_as_it_was(env, monkeypatch):
    ws, client = env
    calls = Calls()
    monkeypatch.setattr(native_move, "make_adapter", calls)
    done = client.post(f"{base(client, ws)}/ai/accounts/old/move", json={"fingerprint": fingerprint(client, ws)})
    saved = done.json()["saved"]
    before = provider(ws, "old")
    assert before.adapter == NATIVE["adapter"]
    undo = {
        "changes": {x["key"]: x["before"] for x in saved["changes"]},
        "reset": [],
        "fingerprint": saved["fingerprint"],
    }
    assert client.post(f"{base(client, ws)}/settings", json=undo).status_code == 200
    back = provider(ws, "old")
    assert back.adapter == GENERIC and back.base_url == OLD_ADDRESS
    assert [x.account for x in lines(ws)] == ["old"]


def test_not_now_is_remembered_for_that_account_and_the_line_never_comes_back_unasked(env):
    ws, client = env
    raw = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())
    raw["providers"]["second"] = {**raw["providers"]["old"]}
    (ws.config_dir / "ai.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    assert [x.account for x in lines(ws)] == ["old", "second"]
    done = client.post(f"{base(client, ws)}/ai/accounts/old/move/not-now")
    assert done.status_code == 200, done.text
    assert [x.account for x in lines(ws)] == ["second"]
    assert [x.account for x in lines(ws)] == ["second"], "still gone on the next look, and after a restart"
    assert provider(ws, "old").adapter == GENERIC, "Not now changes nothing"
    assert client.post(f"{base(client, ws)}/ai/accounts/plain/move/not-now").status_code == 404
