"""Two stops on a new person's path that used to be dead ends: material no account may see, and handing in before the
workspace has a person. Each records a cause the screen can act on, and each is cleared without leaving the screen."""

import json
from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import NoProvider, Router, choices
from engine.config.schema import Price
from engine.dispatcher import SAY_WHO_FIRST, process, requeue_waiting_for_person, waits_on_first_go
from engine.intake import hand_in
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TOKEN = "test-token-value"
NOTE = "The printer says proof copies will ship on the fifth."


def _only_open(config_dir, *names: str) -> None:
    """Narrow the named accounts to open material, and add each one that isn't there as a copy of the first account."""
    path = config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text())
    first = next(iter(data["providers"]))
    for name in names:
        data["providers"].setdefault(name, dict(data["providers"][first]))
        data["providers"][name]["allowed_data"] = ["open"]
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _answer(asked: list | None = None) -> None:
    def responder(task):
        if asked is not None:
            asked.append(task)
        return json.dumps({"summary": "Nothing to do.", "ops": []})

    set_responder(responder)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    first = next(iter(cfg.ai.providers))
    _only_open(ws.config_dir, first)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def _data(env, request: str) -> dict:
    return env[2].read().get("request", request).data


def _run(env, request: str):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)


# ---- material no account may see ---------------------------------------------------------------------------------


def test_the_router_names_the_level_and_the_accounts_that_would_take_it_if_allowed(env):
    _, cfg, _ = env
    account = next(iter(cfg.ai.providers))
    with pytest.raises(NoProvider, match="isn't allowed to see internal") as stopped:
        choices(cfg, "notes", "internal")
    assert stopped.value.level == "internal"
    assert stopped.value.blocked == (cfg.ai.tiers["routine"].use,)
    assert stopped.value.blocked[0].startswith(account + "/")
    # An account that doesn't exist is no cause the person can clear.
    cfg.ai.tiers["routine"].use = "nobody/model"
    with pytest.raises(NoProvider) as missing:
        choices(cfg, "notes", "internal")
    assert missing.value.level is None and missing.value.blocked == ()


def test_a_stopped_request_records_the_level_and_the_accounts_that_would_take_it(env):
    asked: list = []
    _answer(asked)
    ws, cfg, store = env
    request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
    assert _run(env, request) is None
    held = _data(env, request)
    assert held["state"] == "needs_you" and "isn't allowed to see internal material" in held["waiting"]
    assert held["cause"] == {"kind": "data_level", "level": "internal", "accounts": [cfg.ai.tiers["routine"].use]}
    assert asked == []


def test_the_first_account_the_tier_would_use_is_the_one_offered(env):
    ws, cfg, store = env
    _only_open(ws.config_dir, "second")
    config = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())
    first = cfg.ai.tiers["routine"].use
    config["tiers"]["routine"]["fallback"] = ["second/default"]
    (ws.config_dir / "ai.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    cfg = ws.config(env={})
    _answer()
    request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
    process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    assert _data(env, request)["cause"]["accounts"] == [first, "second/default"]


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    _only_open(ws.config_dir, next(iter(cfg.ai.providers)))
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield ws, client, app.state.worker
    set_responder(None)


def test_the_screen_sees_the_cause_and_one_action_lets_the_account_see_it_and_runs_it_again(api):
    ws, client, worker = api
    _answer()
    pasted = fixture_records(DEMO_B, "project")[0]["name"]
    assert client.post("/api/handin", json={"note": "", "pasted": f"{NOTE} {pasted}"}).status_code == 200
    worker.run_pending()
    [stopped] = client.get("/api/changes").json()
    account = next(iter(worker.cfg.ai.providers))
    assert stopped["state"] == "needs_you"
    assert stopped["cause"] == {"kind": "data_level", "level": "internal", "account": account}

    done = client.post(f"/api/requests/{stopped['id']}/allow-data")
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["request"], body["account"], body["level"]) == (stopped["id"], account, "internal")
    [change] = body["saved"]["changes"]
    assert change["key"] == f"ai.providers.{account}.allowed_data"
    assert change["before"] == ["open"] and change["after"] == ["open", "internal"]
    assert body["saved"]["needs_restart"] is False
    on_disk = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())
    assert on_disk["providers"][account]["allowed_data"] == ["open", "internal"]
    [kept] = [c for c in worker.store.read().list("setting_change") if c.data["key"] == change["key"]]
    assert kept.data["after"] == ["open", "internal"]
    queued = client.get("/api/changes").json()[0]
    assert queued["state"] == "queued" and queued["cause"] is None

    worker.run_pending()
    after = client.get("/api/changes").json()[0]
    assert after["state"] == "review" and after["cause"] is None
    assert client.post(f"/api/requests/{stopped['id']}/allow-data").status_code == 409


def test_the_action_refuses_a_request_that_is_not_waiting_on_a_level(api):
    _, client, worker = api
    _answer()
    pasted = fixture_records(DEMO_B, "project")[0]["name"]
    client.post("/api/handin", json={"note": "", "pasted": f"{NOTE} {pasted}"})
    assert client.post("/api/requests/REQ-404/allow-data").status_code == 404
    [queued] = client.get("/api/changes").json()
    assert client.post(f"/api/requests/{queued['id']}/allow-data").status_code == 409
    worker.run_pending()


# ---- handing in before the workspace has a person ----------------------------------------------------------------


@pytest.fixture
def unnamed(env):
    ws, cfg, store = env
    cfg.workspace.user.person = None
    return env


def test_a_request_waits_before_any_cost_or_call_when_no_person_is_set(unnamed):
    asked: list = []
    _answer(asked)
    ws, cfg, store = unnamed
    request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
    assert _run(unnamed, request) is None
    held = _data(unnamed, request)
    assert held["state"] == "needs_you" and held["waiting"] == SAY_WHO_FIRST
    assert held["cause"] == {"kind": "no_person", "level": None, "accounts": []}
    assert held["attempts"] == 0 and asked == [] and not store.read().has("run")


def test_waiting_to_be_named_comes_before_the_first_go_and_is_not_counted_in_it(unnamed):
    ws, cfg, store = unnamed
    cfg.ai.budgets.first_go = True
    use = cfg.ai.tiers["routine"].use
    cfg.ai.prices[use] = Price(input_per_million=10.0, output_per_million=10.0)
    _answer()
    request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
    _run(unnamed, request)
    held = _data(unnamed, request)
    assert held["waiting"] == SAY_WHO_FIRST and held.get("approval") != "required"
    assert not waits_on_first_go(held)
    assert [line for line in queue(ws, store, cfg, NOW) if line.kind == "first_go"] == []


def test_once_a_person_is_set_the_waiting_requests_queue_themselves_and_run(unnamed):
    asked: list = []
    _answer(asked)
    ws, cfg, store = unnamed
    request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
    _run(unnamed, request)
    cfg.ai.providers[next(iter(cfg.ai.providers))].allowed_data = ["open", "internal", "restricted"]
    assert requeue_waiting_for_person(store) == 1
    assert _data(unnamed, request)["state"] == "queued" and _data(unnamed, request)["cause"] is None
    cfg.workspace.user.person = fixture_records(DEMO_B, "person")[0]["id"]
    _run(unnamed, request)
    assert len(asked) == 1 and _data(unnamed, request)["state"] == "review"


def test_naming_the_person_queues_the_waiting_requests_by_itself(tmp_path):
    ws = init_workspace(tmp_path / "fresh", git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.post("/api/handin", json={"note": "file this", "pasted": ""})
        app.state.worker.run_pending()
        [waiting] = client.get("/api/changes").json()
        assert waiting["waiting"] == SAY_WHO_FIRST and waiting["cause"]["kind"] == "no_person"
        assert client.post("/api/me", json={"full_name": "Someone Plain"}).status_code == 200
        [queued] = client.get("/api/changes").json()
        assert queued["state"] == "queued" and queued["cause"] is None


# ---- a folder's first read -----------------------------------------------------------------------------------------


def test_each_kind_of_source_says_how_its_first_read_goes(api):
    from engine.config.schema import WatchSource

    _, client, _ = api
    kinds = client.get("/api/watch/kinds").json()
    assert kinds and {k["first_run"] for k in kinds} == {WatchSource.model_fields["first_run"].get_default()}
