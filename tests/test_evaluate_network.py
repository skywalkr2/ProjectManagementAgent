"""`cockpit evaluate` waits for the network as the app's own runs do (design 6.16, 6.20): a case, pair or replay that
finds no connection uses up no try and fails nothing; the run says it is waiting, looks again when the request's own
wait ends, and goes on when the network is back. No real network and no sleeping: the provider is a script and the pause
between looks is injected."""

import json
from datetime import UTC, datetime

import pytest

import engine.evaluate as ev
import engine.pairs as pairs_module
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.ai.task import AiError
from engine.dispatcher import process, process_through_outage
from engine.evaluate import evaluate
from engine.intake import hand_in
from engine.pairs import evaluate_pairs
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_evaluate_harness import case_of

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)


class Offline:
    """A provider that answers `then` after losing the network for its first `times` calls."""

    def __init__(self, times: int, then, error: AiError | None = None):
        self.left, self.then, self.calls = times, then, 0
        self.error = error or AiError("offline", "name resolution failed")

    def __call__(self, task):
        self.calls += 1
        if self.left > 0:
            self.left -= 1
            raise self.error
        return self.then(task)


def through(monkeypatch, module, provider_for):
    """Make every responder a case or pair sets pass through `provider_for(responder)`."""
    real = module.set_responder
    monkeypatch.setattr(module, "set_responder", lambda r: real(None if r is None else provider_for(r)))


@pytest.fixture(autouse=True)
def _no_responder_left():
    yield
    set_responder(None)


# ---- the dispatcher's own wait, reused ---------------------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"ai.budgets.first_go": False})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()


def test_a_request_that_finds_no_network_is_looked_at_again_after_its_wait_and_uses_up_no_try(env):
    ws, cfg, store = env
    case = case_of(DEMO_B, "close-action")
    provider = Offline(2, lambda task: json.dumps(case["stub_answer"]))
    set_responder(provider)
    handed = hand_in(ws, store, note="", pasted=case["pasted"], now=NOW)
    seen, pauses, lines = [], [], []

    def pause(seconds):
        request = store.read().get("request", handed.request).data
        seen.append((request["state"], request["cause"]["kind"], request["attempts"], request["retries"]))
        pauses.append(seconds)

    done = process_through_outage(
        ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW, notice=lines.append, pause=pause
    )
    assert done is not None and provider.calls == 3
    wait = cfg.dispatch.offline_check_seconds
    assert pauses == [wait, wait]
    assert seen == [("queued", "offline", 0, 0)] * 2, "waiting, with no try used and no retry counted"
    request = store.read().get("request", handed.request).data
    assert request["attempts"] == 1 and request["retries"] == 0
    assert len(lines) == 3 and "waiting" in lines[0].lower() and "back" in lines[-1].lower()


def test_a_failure_that_is_not_the_network_is_not_waited_for(env):
    ws, cfg, store = env
    case = case_of(DEMO_B, "close-action")
    set_responder(Offline(99, lambda task: "", AiError("provider_down", "the service answered with a failure")))
    handed = hand_in(ws, store, note="", pasted=case["pasted"], now=NOW)
    pauses = []
    process_through_outage(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW, pause=pauses.append)
    assert pauses == []


def test_process_alone_still_returns_at_the_first_miss(env):
    ws, cfg, store = env
    case = case_of(DEMO_B, "close-action")
    set_responder(Offline(1, lambda task: json.dumps(case["stub_answer"])))
    handed = hand_in(ws, store, note="", pasted=case["pasted"], now=NOW)
    assert process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW) is None
    assert store.read().get("request", handed.request).data["state"] == "queued"


# ---- the harness -------------------------------------------------------------------------------------------


def test_a_case_that_loses_the_network_waits_and_then_passes(monkeypatch):
    provider = {}

    def wrapped(responder):
        provider["it"] = Offline(2, responder)
        return provider["it"]

    through(monkeypatch, ev, wrapped)
    lines, pauses = [], []
    report = evaluate(
        DEMO_B, stub=True, runs=1, env={}, only=["close-action"], notice=lines.append, pause=pauses.append
    )
    (result,) = report.results
    assert result.passed and not result.not_run and result.error is None
    assert len(pauses) == 2 and all(p > 0 for p in pauses)
    waiting = [line for line in lines if "waiting for the network" in line.lower()]
    assert waiting and waiting[0].startswith("[1/1] close-action")
    assert any("network is back" in line.lower() for line in lines)
    assert report.pass_rate() == 1.0


def test_a_lost_network_fails_no_case_for_any_number_of_looks(monkeypatch):
    through(monkeypatch, ev, lambda responder: Offline(7, responder))
    pauses = []
    report = evaluate(DEMO_B, stub=True, runs=2, env={}, only=["close-action"], pause=pauses.append)
    assert [r.passed for r in report.results] == [True, True]
    assert len(pauses) == 14, "each run lost its first seven calls and none of them failed a case"


def test_a_case_whose_account_is_down_still_fails_without_waiting(monkeypatch):
    through(
        monkeypatch, ev, lambda responder: Offline(99, responder, AiError("provider_down", "answered with a failure"))
    )
    pauses = []
    report = evaluate(DEMO_B, stub=True, runs=1, env={}, only=["close-action"], pause=pauses.append)
    assert not report.results[0].passed and pauses == []


def test_a_pair_that_loses_the_network_waits_and_then_passes(monkeypatch):
    through(monkeypatch, pairs_module, lambda responder: Offline(1, responder))
    lines, pauses = [], []
    report = evaluate_pairs(
        DEMO_B,
        stub=True,
        runs=1,
        env={},
        only=["promise-pair-17-non-answer"],
        notice=lines.append,
        pause=pauses.append,
    )
    assert report.results[0].passed, report.results[0].error
    assert pauses and any("waiting for the network" in line.lower() for line in lines)


def test_a_replay_that_loses_the_network_waits_and_then_passes(monkeypatch):
    from engine.replays import evaluate_replays

    through(monkeypatch, pairs_module, lambda responder: Offline(1, responder))
    lines, pauses = [], []
    report = evaluate_replays(
        DEMO_B,
        stub=True,
        runs=1,
        env={},
        only=["a-moved-date-sent-back-leaves-no-calendar-entry"],
        notice=lines.append,
        pause=pauses.append,
    )
    assert report.results[0].passed, report.results[0].error
    assert pauses and any("waiting for the network" in line.lower() for line in lines)
