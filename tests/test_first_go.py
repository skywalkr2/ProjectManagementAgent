"""The first runs in a workspace wait for one go (design 7.8, `ai.budgets.first_go`): the first request is held with its
estimate, Today shows one line for all of them, one Go starts them all, and after the first run the usual amount to
confirm applies. The fixture workspace turns the wait off by default; these tests turn it on."""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config.schema import Price
from engine.dispatcher import FIRST_GO, grant_first_go, process
from engine.intake import hand_in
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TOKEN = "test-token-value"
NOTE = "The printer says proof copies will ship on the fifth."


def _price(cfg, per_million: float | None) -> None:
    use = cfg.ai.tiers["routine"].use
    if per_million is None:
        cfg.ai.prices.pop(use, None)
    else:
        cfg.ai.prices[use] = Price(input_per_million=per_million, output_per_million=per_million)


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
    cfg.ai.budgets.first_go = True
    _price(cfg, 5.0)  # a price that keeps an ordinary run well under the confirm amount as the packet grows
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def _hand_in(env, text: str = NOTE) -> str:
    ws, _, store = env
    return hand_in(ws, store, note="", pasted=text, now=NOW).request


def _process(env, request: str):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)


def _data(env, request: str) -> dict:
    return env[2].read().get("request", request).data


def _first_go_lines(env) -> list:
    ws, cfg, store = env
    return [line for line in queue(ws, store, cfg, NOW) if line.kind == "first_go"]


def test_the_first_request_holds_with_its_estimate(env):
    asked: list = []
    _answer(asked)
    request = _hand_in(env)
    assert _process(env, request) is None
    held = _data(env, request)
    assert asked == []
    assert (held["state"], held["approval"], held["waiting"]) == ("needs_you", "required", FIRST_GO)
    assert 0 < held["estimate_usd"] <= env[1].ai.budgets.confirm_above_usd


def test_three_held_requests_make_one_today_line_with_the_summed_estimate(env):
    _answer()
    requests = [_hand_in(env, f"{NOTE} Batch {n}.") for n in range(3)]
    for request in requests:
        _process(env, request)
    (line,) = _first_go_lines(env)
    estimates = [_data(env, r)["estimate_usd"] for r in requests]
    assert line.count == 3 and line.unpriced == 0 and line.estimate_usd == pytest.approx(sum(estimates), abs=1e-3)
    assert line.group == "decide"


def test_a_line_with_no_price_says_how_many_and_has_no_total(env):
    _price(env[1], None)
    _answer()
    requests = [_hand_in(env, f"{NOTE} Batch {n}.") for n in range(2)]
    for request in requests:
        _process(env, request)
    (line,) = _first_go_lines(env)
    assert (line.count, line.estimate_usd, line.unpriced) == (2, None, 2)
    assert _data(env, requests[0])["estimate_usd"] is None


def test_go_starts_them_all_and_nothing_waits_for_it_again(env):
    _answer()
    requests = [_hand_in(env, f"{NOTE} Batch {n}.") for n in range(3)]
    for request in requests:
        _process(env, request)
    assert grant_first_go(env[2]) == 3
    assert grant_first_go(env[2]) == 0
    for request in requests:
        assert _data(env, request)["state"] == "queued" and _data(env, request)["approval"] == "granted"
        assert _process(env, request) is not None
        assert _data(env, request)["state"] == "review"
    assert _first_go_lines(env) == []


def test_after_a_run_exists_a_cheap_request_runs_at_once(env):
    _answer()
    first = _hand_in(env)
    _process(env, first)
    grant_first_go(env[2])
    assert _process(env, first) is not None
    later = _hand_in(env, "The proofs arrive on the fifth. A different message.")
    assert _process(env, later) is not None
    assert _data(env, later)["state"] == "review"


def test_a_workspace_with_the_setting_off_does_not_hold(env):
    env[1].ai.budgets.first_go = False
    _answer()
    request = _hand_in(env)
    assert _process(env, request) is not None
    assert _data(env, request)["state"] == "review"


def test_an_estimate_of_zero_does_not_hold(env):
    _price(env[1], 0.0)
    _answer()
    request = _hand_in(env)
    assert _process(env, request) is not None
    assert _data(env, request)["state"] == "review"


def test_the_per_run_limit_still_wins_over_the_first_go(env):
    _price(env[1], 5000.0)
    _answer()
    request = _hand_in(env)
    assert _process(env, request) is None
    held = _data(env, request)
    assert "per-run limit" in held["waiting"] and held["waiting"] != FIRST_GO
    assert held.get("approval") != "required"


def test_a_request_no_account_can_take_says_so_instead_of_waiting_for_a_go(tmp_path):
    ws = init_workspace(tmp_path / "fresh", git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    request = hand_in(ws, store, note="file this", now=NOW).request
    assert process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW) is None
    waiting = store.read().get("request", request).data["waiting"]
    store.close()
    assert cfg.ai.budgets.first_go is True and waiting != FIRST_GO


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    cfg.ai.budgets.first_go = True
    _price(cfg, 10.0)
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.worker
    set_responder(None)


def test_the_go_route_starts_every_held_run_and_the_changes_say_which_wait(api):
    client, worker = api
    _answer()
    pasted = fixture_records(DEMO_B, "project")[0]["name"]
    for n in range(3):
        assert client.post("/api/handin", json={"note": "", "pasted": f"{NOTE} {pasted} {n}"}).status_code == 200
    worker.run_pending()
    changes = client.get("/api/changes").json()
    assert [c["first_go"] for c in changes] == [True, True, True]
    line = [x for x in client.get("/api/today/queue").json() if x["kind"] == "first_go"]
    assert len(line) == 1 and line[0]["count"] == 3 and line[0]["estimate_usd"] > 0
    started = client.post("/api/runs/first-go")
    assert started.status_code == 200 and started.json() == {"started": 3}
    worker.run_pending()
    after = client.get("/api/changes").json()
    assert {c["state"] for c in after} == {"review"} and not any(c["first_go"] for c in after)
    assert all(x["kind"] != "first_go" for x in client.get("/api/today/queue").json())
    assert client.post("/api/runs/first-go").json() == {"started": 0}
