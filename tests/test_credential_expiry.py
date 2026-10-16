"""Credentials with a known end (design 6.16): an AI account's key the person gave an end date for, and a sign-in whose
renewal credential the service gave one for. Today says so `ai.credential_warn_days` days ahead and after the day, and
names every place the same credential is used. Nothing reaches a service; a fake response stands in for its answer."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import sign_in as flow
from engine.ai.adapters import ADAPTERS
from engine.config.schema import ProviderSettings, WatchSource
from engine.credentials import same_credential
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_sign_in import signing  # noqa: F401  (a fixture: a plugin with a sign-in and a fake service)

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
SHARED = "env:SHARED_KEY"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def lines(env, now=NOW):
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, now) if x.kind == "credential"]


def add_account(cfg, name, **more):
    cfg.ai.providers[name] = ProviderSettings(adapter="stub", models={"default": "x"}, **more)


def test_a_key_ending_within_the_warning_days_is_a_line_naming_every_place_the_same_key_is_used(env):
    ws, cfg, store = env
    add_account(cfg, "main", auth=SHARED, credential_expires=NOW.date() + timedelta(days=5))
    add_account(cfg, "backup", auth=SHARED)
    add_account(cfg, "unrelated", auth="env:ANOTHER_KEY")
    cfg.workspace.plugins.secrets = {"packx": {"token": SHARED}, "packy": {"token": "env:ANOTHER_KEY"}}
    cfg.storage.backups.encrypt = SHARED
    cfg.workspace.plugins.catalog.release_tokens = {"packs.example.com": SHARED}
    cfg.watch.sources.append(WatchSource(id="reader", connector="folder", label="Reader", settings={"p": SHARED}))
    [line] = lines(env)
    assert (line.group, line.credential_kind, line.credential_name, line.due, line.waiting_days) == (
        "risk",
        "account",
        "main",
        (NOW.date() + timedelta(days=5)).isoformat(),
        5,
    )
    assert line.places == [
        "the AI account main",
        "the AI account backup",
        "the add-on packx's secret token",
        "the key that locks the backups",
        "the read token for packs.example.com",
        "the source Reader",
    ]


def test_the_line_comes_exactly_when_the_end_is_within_the_setting_and_stays_after_the_day(env):
    ws, cfg, store = env
    add_account(cfg, "main", auth=SHARED, credential_expires=NOW.date() + timedelta(days=8))
    assert lines(env) == [], "eight days out is beyond the seven the setting gives"
    assert len(lines(env, NOW + timedelta(days=1))) == 1, "seven days out is inside it"
    cfg.ai.credential_warn_days = 2
    assert lines(env, NOW + timedelta(days=1)) == []
    assert [x.waiting_days for x in lines(env, NOW + timedelta(days=6))] == [2]
    [past] = lines(env, NOW + timedelta(days=11))
    assert past.waiting_days == -3, "after the day the line stays, counting how long ago, until it is renewed"


def test_an_account_with_no_end_date_or_a_different_key_has_no_line_and_a_lone_key_names_one_place(env):
    ws, cfg, store = env
    add_account(cfg, "main", auth=SHARED)
    add_account(cfg, "other", auth="env:ANOTHER_KEY")
    assert lines(env) == []
    cfg.ai.providers["other"].credential_expires = NOW.date()
    [line] = lines(env)
    assert line.places == ["the AI account other"]


def test_two_references_to_one_file_are_the_same_credential():
    assert same_credential("file:~/keys/one") == same_credential("file:~/keys/one ")
    assert same_credential("env:A") != same_credential("env:B") and same_credential(None) is None


def test_the_expiry_the_person_enters_reaches_the_line_through_the_account_routes(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "screen-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    soon = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    with TestClient(application, headers={"Authorization": "Bearer screen-token"}) as client:
        fingerprint = client.get("/api/settings").json()["fingerprint"]
        added = client.post(
            "/api/ai/accounts",
            json={
                "name": "added",
                "adapter": next(a for a in ADAPTERS if a not in ("stub", "cli-agent")),
                "key_ref": SHARED,
                "credential_expires": soon,
                "models": {"default": "m"},
                "fingerprint": fingerprint,
            },
        )
        assert added.status_code == 200, added.text
        [shown] = [a for a in client.get("/api/ai/accounts").json() if a["name"] == "added"]
        assert shown["credential_expires"] == soon
        found = [x for x in client.get("/api/today/queue").json() if x["kind"] == "credential"]
        assert [(x["credential_name"], x["credential_kind"], x["places"]) for x in found] == [
            ("added", "account", ["the AI account added"])
        ]
        later = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
        fingerprint = client.get("/api/settings").json()["fingerprint"]
        moved = client.post("/api/ai/accounts/added", json={"credential_expires": later, "fingerprint": fingerprint})
        assert moved.status_code == 200, moved.text
        assert [x for x in client.get("/api/today/queue").json() if x["kind"] == "credential"] == []
        fingerprint = client.get("/api/settings").json()["fingerprint"]
        cleared = client.post(
            "/api/ai/accounts/added", json={"clear_credential_expires": True, "fingerprint": fingerprint}
        )
        assert cleared.status_code == 200, cleared.text
        [shown] = [a for a in client.get("/api/ai/accounts").json() if a["name"] == "added"]
        assert shown["credential_expires"] is None


class Said:
    """A service's answer to a token request."""

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_the_end_the_service_gives_a_sign_in_is_kept_and_a_renewal_that_sends_no_new_credential_keeps_it():
    given = flow._tokens(Said({"access_token": "a", "refresh_token": "r", "refresh_token_expires_in": 86400}), 1000.0)
    assert given["refresh_expires_at"] == 1000.0 + 86400
    kept = flow._tokens(Said({"access_token": "b"}), 2000.0, keep_refresh="r", keep_expires=given["refresh_expires_at"])
    assert kept["refresh_expires_at"] == given["refresh_expires_at"] and kept["refresh_token"] == "r"
    replaced = flow._tokens(
        Said({"access_token": "c", "refresh_token": "r2"}),
        3000.0,
        keep_refresh="r",
        keep_expires=given["refresh_expires_at"],
    )
    assert replaced["refresh_expires_at"] is None, "a new credential with no stated end has no known end"
    assert flow._tokens(Said({"access_token": "d"}), 4000.0)["refresh_expires_at"] is None


def test_a_sign_in_whose_credential_ends_soon_is_a_line_naming_the_sign_in_and_what_reads_through_it(signing):  # noqa: F811
    ws, cfg, store, _ = signing
    sign_in = store.plugins.sign_ins()["p18/service"]
    keys = ws.root / ".cockpit" / "keys" / "p18"
    now = datetime.now(UTC)
    ends = (now + timedelta(days=2)).timestamp()
    flow.keep(
        keys,
        sign_in,
        {"access_token": "t", "expires_at": time.time() + 3600, "refresh_token": "r", "refresh_expires_at": ends},
    )
    cfg.watch.sources.append(WatchSource(id="reader", connector="p18/service-reader", label="Reader"))
    found = [x for x in queue(ws, store, cfg, now) if x.kind == "credential"]
    assert [(x.credential_kind, x.credential_name, x.waiting_days) for x in found] == [("sign_in", "p18/service", 2)]
    assert found[0].places == [f"the {sign_in.label} sign-in", "the source Reader"]
    flow.keep(keys, sign_in, {"access_token": "t", "expires_at": time.time() + 3600, "refresh_token": "r"})
    assert [x for x in queue(ws, store, cfg, now) if x.kind == "credential"] == []


def test_work_with_no_account_is_a_line_until_one_does_it(env):
    ws, cfg, store = env
    assert [x for x in queue(ws, store, cfg, NOW) if x.kind == "no_account"] == []
    cfg.ai.tiers["routine"].use = ""
    [line] = [x for x in queue(ws, store, cfg, NOW) if x.kind == "no_account"]
    assert (line.group, line.count, line.tier, line.names) == ("risk", 1, "routine", ["routine"])
    cfg.ai.tiers["routine"].use = "gone/default"  # an account that isn't set up is no account either
    assert [x.names for x in queue(ws, store, cfg, NOW) if x.kind == "no_account"] == [["routine"]]


def test_a_workspace_with_no_account_at_all_is_left_to_the_setup_line(env):
    ws, cfg, store = env
    cfg.ai.providers.clear()
    for tier in cfg.ai.tiers.values():
        tier.use = ""
    assert [x for x in queue(ws, store, cfg, NOW) if x.kind == "no_account"] == []
