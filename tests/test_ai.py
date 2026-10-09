"""The AI layer: the generic adapter against a simulated server, error kinds from the call only, fallbacks, data
levels, budgets and run records. Account settings come from tests/fixtures/ai/ai.yaml."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from engine.ai.adapters import ADAPTERS
from engine.ai.router import BudgetReached, NoProvider, Router, choices
from engine.ai.task import AiError, AiTask
from engine.config import load_config
from engine.storage import Store, WriteContext

TASK = AiTask(kind="notes", instructions="Do it.", stable="Reference.", request="Input.", output_schema={})
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
AI_CONFIG = Path(__file__).parent / "fixtures" / "ai"
KEYS = {"MAIN_KEY": "main-secret", "BACKUP_KEY": "backup-secret"}


def ok_body(text="{}", model="served-model"):
    return {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
    }


@pytest.fixture
def cfg():
    return load_config(AI_CONFIG, env={})


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "ai.db")
    yield s
    s.close()


def host(cfg, provider):
    return httpx.URL(cfg.ai.providers[provider].base_url).host


def adapter(cfg, provider, handler):
    settings = cfg.ai.providers[provider]
    return ADAPTERS[settings.adapter](settings, "k", transport=httpx.MockTransport(handler))


def router_with(cfg, store, handlers, env=KEYS):
    """handlers: account name -> function(request) -> httpx.Response"""
    seen = []
    by_host = {host(cfg, name): fn for name, fn in handlers.items()}

    def factory(name, settings, secret):
        def handle(request):
            seen.append((request.url.host, request))
            return by_host[request.url.host](request)

        return ADAPTERS[name](settings, secret, transport=httpx.MockTransport(handle))

    return Router(cfg, store, env=env, adapter_factory=factory, now=lambda: NOW), seen


def test_a_call_sends_the_packet_and_reads_text_usage_and_cost(cfg, store):
    router, seen = router_with(cfg, store, {"main": lambda r: httpx.Response(200, json=ok_body())})
    _, _, run_id = router.call(TASK, request_id="REQ-1")
    _, request = seen[0]
    sent = json.loads(request.content)
    assert request.headers["authorization"] == "Bearer main-secret"
    assert sent["model"] == cfg.ai.providers["main"].models["small"]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][0]["content"].startswith("Do it.") and sent["messages"][1]["content"] == "Input."
    run = store.read().get("run", run_id).data
    assert run["outcome"] == "ok" and run["model"] == "served-model"
    assert run["cost_usd"] == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1e6)


def test_a_rate_limit_falls_through_to_the_next_account_and_both_runs_are_kept(cfg, store):
    router, _ = router_with(
        cfg,
        store,
        {
            "main": lambda r: httpx.Response(429, headers={"retry-after": "30"}, text="slow down"),
            "backup": lambda r: httpx.Response(200, json=ok_body()),
        },
    )
    _, choice, _ = router.call(TASK, request_id="REQ-1")
    assert choice.provider == "backup"
    runs = [r.data for r in store.read().list("run")]
    assert [(r["provider"], r["outcome"], r["error_kind"]) for r in runs] == [
        ("main", "error", "rate_limited"),
        ("backup", "ok", None),
    ]


def test_error_kind_comes_from_the_call_never_from_the_model_text(cfg, store):
    text = "Report: not logged in; auth failed."
    router, _ = router_with(cfg, store, {"main": lambda r: httpx.Response(200, json=ok_body(text))})
    result, choice, _ = router.call(TASK, request_id="REQ-1")
    assert choice.provider == "main" and result.text == text


@pytest.mark.parametrize(
    "status,kind",
    [(401, "auth"), (403, "auth"), (402, "quota"), (429, "rate_limited"), (503, "provider_down"), (400, "other")],
)
def test_http_errors_are_classified_by_status(cfg, status, kind):
    with pytest.raises(AiError) as err:
        adapter(cfg, "main", lambda r: httpx.Response(status, text="no")).run(TASK, "m")
    assert err.value.kind == kind


def test_a_timeout_and_a_dropped_connection_are_their_own_kinds(cfg):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def dropped(request):
        raise httpx.ConnectError("refused", request=request)

    for handler, kind in ((timeout, "timeout"), (dropped, "provider_down")):
        with pytest.raises(AiError) as err:
            adapter(cfg, "main", handler).run(TASK, "m")
        assert err.value.kind == kind


def test_a_missing_key_is_an_auth_failure_and_falls_through(cfg, store):
    handlers = {"backup": lambda r: httpx.Response(200, json=ok_body())}
    router, seen = router_with(cfg, store, handlers, env={"BACKUP_KEY": "b"})
    _, choice, _ = router.call(TASK, request_id="REQ-1")
    assert choice.provider == "backup" and [h for h, _ in seen] == [host(cfg, "backup")]
    main_run = store.read().list("run")[0].data
    assert main_run["error_kind"] == "auth" and "MAIN_KEY" in main_run["error_detail"]
    assert "main-secret" not in json.dumps([r.data for r in store.read().list("run")])


def test_accounts_only_see_data_they_are_allowed(cfg):
    assert [c.provider for c in choices(cfg, "notes", "internal")] == ["main", "backup"]
    with pytest.raises(NoProvider, match="isn't allowed to see internal"):
        choices(cfg, "notes", "internal", tier="deep")
    assert [c.provider for c in choices(cfg, "notes", "open", tier="deep")] == ["public-only"]


def test_the_daily_budget_stops_new_runs(cfg, store):
    run = {
        "request": "REQ-1",
        "task": "notes",
        "provider": "main",
        "model": "m",
        "tier": "routine",
        "cost_usd": 0.02,
        "outcome": "ok",
        "started_at": NOW.isoformat(),
    }
    with store.transaction() as tx:
        tx.create("run", run, WriteContext("engine", "trusted", "test"))
    router, _ = router_with(cfg, store, {})
    with pytest.raises(BudgetReached, match="today"):
        router.call(TASK, request_id="REQ-2")
