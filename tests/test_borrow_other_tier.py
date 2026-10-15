"""Borrowing another kind of work's account while the work's own is paused (design 6.16): the question on Today,
the work done on the other account after a yes and only until the reset, a no that keeps the work waiting, and never
asking when the setting says never or no free account may see the material. A fake adapter per account and a clock the
test moves stand in for the providers and for time."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.borrow import Borrowed, BorrowError, borrowed_path
from engine.ai.router import Router
from engine.storage import Store
from engine.today_queue import queue
from engine.worker import Events, Worker
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_silent_stops import ANSWER, NOTE, START, Clock, Scripted, adapters_by_account, quota

OTHER = "second"
REF = f"{OTHER}/default"


def configure(ws, *, allowed=("open", "internal", "restricted")) -> None:
    """A second account that does the deep tier's work, beside the stand-in that does the routine tier's."""
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"][OTHER] = {"adapter": "stub", "models": {"default": "scripted"}, "allowed_data": list(allowed)}
    data["tiers"]["deep"] = {"use": REF}
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    configure(ws)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    clock = Clock()
    yield ws, cfg, store, clock
    store.close()
    set_responder(None)


def account_of(cfg) -> str:
    return cfg.ai.tiers["routine"].use.partition("/")[0]


def worker_of(env, answers) -> Worker:
    ws, cfg, store, clock = env
    by_account = {account_of(cfg): answers[0], OTHER: answers[1]}
    return Worker(
        ws,
        store,
        cfg,
        Events(),
        router_factory=lambda: Router(
            cfg, store, env={}, now=clock, sleep=lambda s: None, adapter_factory=adapters_by_account(cfg, by_account)
        ),
        now=clock,
    )


def hand(env, text: str = NOTE) -> str:
    from engine.intake import hand_in

    ws, _, store, clock = env
    return hand_in(ws, store, note="", pasted=text, now=clock()).request


def data(env, request: str) -> dict:
    return env[2].read().get("request", request).data


def borrow_lines(env):
    ws, cfg, store, clock = env
    return [line for line in queue(ws, store, cfg, clock()) if line.kind == "borrow"]


def paused_routine(env):
    """The routine account is out of its limit with one request waiting on it; the other account would answer."""
    limited, other = Scripted(quota(7200), ANSWER), Scripted(ANSWER)
    request = hand(env)
    worker = worker_of(env, (limited, other))
    worker.run_pending()
    assert data(env, request)["state"] == "queued" and data(env, request)["cause"]["tier"] == "routine"
    return worker, request, limited, other


def test_a_paused_routine_account_asks_first_then_the_work_runs_on_the_other_account_until_the_reset(env):
    ws, cfg, store, clock = env
    worker, request, limited, other = paused_routine(env)
    [line] = borrow_lines(env)
    assert (line.group, line.kind, line.account, line.model, line.tier) == (
        "decide",
        "borrow",
        OTHER,
        "default",
        "routine",
    )
    assert line.text == account_of(cfg) and line.count == 1
    assert line.until == (START.replace(hour=START.hour + 2)).isoformat()
    assert other.calls == 0, "nothing is borrowed before the person says yes"
    assert worker.run_pending() == 0 and other.calls == 0, "and the work keeps waiting"

    from engine.ai.borrow import answer

    assert answer(ws, store, cfg, "routine", REF, True, clock()) == 1
    assert borrow_lines(env) == []
    assert worker.run_pending() == 1
    assert other.calls == 1 and limited.calls == 1, "it ran on the other account; the paused one wasn't called again"
    assert data(env, request)["state"] == "review"
    runs = [r.data for r in store.read().list("run")]
    assert [r["provider"] for r in runs if r["outcome"] == "ok"] == [OTHER]

    # More work during the same pause goes to the other account without asking again.
    later = hand(env, NOTE + " Also the covers.")
    assert worker.run_pending() == 1 and data(env, later)["state"] == "review"
    assert other.calls == 2 and limited.calls == 1 and borrow_lines(env) == []

    # After the reset the routine account is used again.
    clock.move(hours=2, seconds=1)
    after = hand(env, NOTE + " And the proofs.")
    assert worker.run_pending() == 1 and data(env, after)["state"] == "review"
    assert limited.calls == 2 and other.calls == 2
    assert Borrowed(borrowed_path(store), clock).lent("routine") is None


def test_no_keeps_the_work_waiting_and_the_same_pause_is_not_asked_again(env):
    ws, cfg, store, clock = env
    worker, request, limited, other = paused_routine(env)
    from engine.ai.borrow import answer

    assert answer(ws, store, cfg, "routine", REF, False, clock()) == 0
    assert borrow_lines(env) == []
    assert data(env, request)["cause"]["kind"] == "paused"
    assert worker.run_pending() == 0 and other.calls == 0
    clock.move(hours=2, seconds=1)
    assert worker.run_pending() == 1 and limited.calls == 2 and other.calls == 0


def test_never_does_not_ask_and_refuses_an_answer(env):
    ws, cfg, store, clock = env
    cfg.ai.borrow_other_tier = "never"
    worker, request, limited, other = paused_routine(env)
    assert borrow_lines(env) == []
    from engine.ai.borrow import answer

    with pytest.raises(BorrowError):
        answer(ws, store, cfg, "routine", REF, True, clock())
    assert worker.run_pending() == 0 and other.calls == 0


def test_only_the_account_the_question_offered_can_be_answered_for(env):
    ws, cfg, store, clock = env
    paused_routine(env)
    from engine.ai.borrow import answer

    with pytest.raises(BorrowError):
        answer(ws, store, cfg, "routine", f"{account_of(cfg)}/default", True, clock())
    with pytest.raises(BorrowError):
        answer(ws, store, cfg, "deep", REF, True, clock())


def test_no_question_when_no_free_account_may_see_the_material(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    configure(ws, allowed=("open",))
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    env = (ws, cfg, store, Clock())
    try:
        paused_routine(env)
        assert borrow_lines(env) == []
    finally:
        store.close()


def test_no_question_when_the_other_kind_of_work_uses_the_same_account(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    clock = Clock()
    limited = Scripted(quota(7200), ANSWER)
    try:
        request = hand((ws, cfg, store, clock))
        worker = Worker(
            ws,
            store,
            cfg,
            Events(),
            router_factory=lambda: Router(
                cfg,
                store,
                env={},
                now=clock,
                sleep=lambda s: None,
                adapter_factory=adapters_by_account(cfg, {account_of(cfg): limited}),
            ),
            now=clock,
        )
        worker.run_pending()
        assert data((ws, cfg, store, clock), request)["cause"]["kind"] == "paused"
        assert [x for x in queue(ws, store, cfg, clock()) if x.kind == "borrow"] == []
    finally:
        store.close()


def test_the_question_and_its_answer_go_through_the_routes(env, tmp_path):
    ws, cfg, store, clock = env
    clock.at = datetime.now(UTC)  # the app reads the real clock
    paused_routine(env)
    application = create_app(ws, cfg, "screen-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer screen-token"}) as client:
        shown = [x for x in client.get("/api/today/queue").json() if x["kind"] == "borrow"]
        assert [(x["account"], x["model"], x["tier"], x["count"]) for x in shown] == [(OTHER, "default", "routine", 1)]
        refused = client.post(
            "/api/ai/borrow", json={"tier": "routine", "account": "nobody", "model": "default", "use": True}
        )
        assert refused.status_code == 409
        said = client.post(
            "/api/ai/borrow", json={"tier": "routine", "account": OTHER, "model": "default", "use": True}
        )
        assert said.status_code == 200 and said.json() == {"released": 1}
        assert [x for x in client.get("/api/today/queue").json() if x["kind"] == "borrow"] == []


def test_the_question_carries_the_estimate_on_the_other_account_and_a_yes_prices_runs_there(env):
    from engine.ai.borrow import answer
    from engine.config.schema import Price
    from tests.test_silent_stops import TASK

    ws, cfg, store, clock = env
    cfg.ai.prices[REF] = Price(input_per_million=2.0, output_per_million=8.0)
    worker, request, limited, other = paused_routine(env)
    [line] = borrow_lines(env)
    assert line.estimate_usd is not None and line.estimate_usd > 0 and line.unpriced == 0
    router = Router(cfg, store, env={}, now=clock)
    assert router.estimate(TASK) is None, "the paused routine account has no price"
    answer(ws, store, cfg, "routine", REF, True, clock())
    assert router.estimate(TASK) is not None, "with the yes, a run is priced on the account that will take it"
