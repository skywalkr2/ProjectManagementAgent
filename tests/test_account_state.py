"""What an AI account row says about the account (design 7.16, 6.16): when it last answered, what it cost today, the
work it passed its check for or failed, and until when a usage limit holds it. Nothing reaches a service."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from engine.ai.account_state import account_states
from engine.ai.checked import account_fingerprint
from engine.ai.pauses import Pauses, pauses_path
from engine.config.schema import ProviderSettings
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
WRITE = WriteContext(actor="engine", trust="trusted", op="test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    cfg.ai.providers["main"] = ProviderSettings(adapter="stub", models={"everyday": "x"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def run(store, at, outcome="ok", cost=0.5, provider="main", error_kind=None):
    data = {
        "task": "notes",
        "provider": provider,
        "model": "x",
        "tier": "routine",
        "outcome": outcome,
        "started_at": at.isoformat(),
        "cost_usd": cost,
        "error_kind": error_kind,
    }
    with store.transaction() as tx:
        tx.create("run", data, WRITE)


def test_the_last_answer_and_todays_cost_come_from_the_runs_that_reached_the_account(env):
    ws, cfg, store = env
    run(store, NOW - timedelta(hours=2), cost=0.25)
    run(store, NOW - timedelta(hours=1), cost=0.5)
    run(store, NOW - timedelta(minutes=30), outcome="error", cost=9)  # failed: not an answer, but it did cost
    run(store, NOW - timedelta(minutes=10), outcome="error", error_kind="offline", cost=0)  # never reached it
    run(store, NOW - timedelta(days=3), cost=4)  # not today
    run(store, NOW - timedelta(hours=1), provider="other", cost=1)
    state = account_states(ws, store, cfg, NOW)["main"]
    assert state.answered_at == NOW - timedelta(hours=1)
    assert state.spent_today_usd == pytest.approx(9.75)
    assert account_states(ws, store, cfg, NOW)["stub"].answered_at is None


def test_what_it_was_checked_for_follows_the_check_kept_for_its_exact_settings(env):
    ws, cfg, store = env
    assert account_states(ws, store, cfg, NOW)["main"].checked_for == []
    from engine.ai.smoke import _params_for_tier

    ref = "main/everyday"
    kept = {
        ref: {
            "fingerprint": account_fingerprint(cfg, ref),
            "params": [list(p) for t in cfg.ai.tiers for p in _params_for_tier(cfg, t)],
            "failed": [],
            "complete": True,
            "at": NOW.isoformat(),
        }
    }
    (ws.private_dir).mkdir(parents=True, exist_ok=True)
    (ws.private_dir / "ai-checked.json").write_text(json.dumps(kept))
    state = account_states(ws, store, cfg, NOW)["main"]
    assert state.checked_for == list(cfg.ai.tiers) and state.check_failed_for == []
    assert state.checked_at == NOW
    # Renaming it changes nothing about its check; changing how it connects does.
    cfg.ai.providers["main"].label = "Main account"
    assert account_states(ws, store, cfg, NOW)["main"].checked_for == list(cfg.ai.tiers)
    cfg.ai.providers["main"].models = {"everyday": "y"}
    assert account_states(ws, store, cfg, NOW)["main"].checked_for == []


def test_a_pause_says_until_when(env):
    ws, cfg, store = env
    until = NOW + timedelta(hours=2)
    Pauses(pauses_path(store), lambda: NOW).pause("main", until)
    state = account_states(ws, store, cfg, NOW)["main"]
    assert state.paused_until == until
    assert account_states(ws, store, cfg, until + timedelta(minutes=1))["main"].paused_until is None
