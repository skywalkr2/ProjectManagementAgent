"""The AI layer: the generic adapter against a simulated server, error kinds from the call only, fallbacks, data
levels, budgets and run records. Account settings come from tests/fixtures/ai/ai.yaml."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from engine.ai.adapters import ADAPTERS
from engine.ai.router import AccountPaused, BudgetReached, NetworkOffline, NoProvider, Router, choices
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

    return Router(cfg, store, env=env, adapter_factory=factory, now=lambda: NOW, catalogs=NoCatalog()), seen


class NoCatalog:
    """Tests that count requests don't want a catalog fetch among them."""

    def model(self, provider, model_id, fetch):
        return None


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


def test_a_timeout_no_connection_at_all_and_a_broken_exchange_are_their_own_kinds(cfg):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def no_connection(request):
        raise httpx.ConnectError("name not resolved", request=request)

    def broken(request):
        raise httpx.RemoteProtocolError("closed mid-answer", request=request)

    for handler, kind in ((timeout, "timeout"), (no_connection, "offline"), (broken, "provider_down")):
        with pytest.raises(AiError) as err:
            adapter(cfg, "main", handler).run(TASK, "m")
        assert err.value.kind == kind
        with pytest.raises(AiError) as listing:
            adapter(cfg, "main", handler).list_models()
        assert listing.value.kind == kind


def test_a_service_that_answers_with_a_failure_is_down_not_offline(cfg):
    with pytest.raises(AiError) as err:
        adapter(cfg, "main", lambda r: httpx.Response(503, text="overloaded")).run(TASK, "m")
    assert err.value.kind == "provider_down"


def test_the_next_account_is_tried_when_one_has_no_connection(cfg, store):
    def no_connection(request):
        raise httpx.ConnectError("name not resolved", request=request)

    router, seen = router_with(
        cfg, store, {"main": no_connection, "backup": lambda r: httpx.Response(200, json=ok_body())}
    )
    _, choice, _ = router.call(TASK, request_id="REQ-1")
    assert choice.provider == "backup" and [h for h, _ in seen] == [host(cfg, "main"), host(cfg, "backup")]
    assert store.read().list("run")[0].data["error_kind"] == "offline"


def test_every_account_without_a_connection_is_the_network_being_offline(cfg, store):
    def no_connection(request):
        raise httpx.ConnectError("name not resolved", request=request)

    router, seen = router_with(cfg, store, {"main": no_connection, "backup": no_connection})
    with pytest.raises(NetworkOffline) as offline:
        router.call(TASK, request_id="REQ-1")
    assert offline.value.kind == "offline" and len(seen) == 2


def test_one_account_without_a_connection_and_another_refusing_the_key_is_not_the_network(cfg, store):
    def no_connection(request):
        raise httpx.ConnectError("name not resolved", request=request)

    router, _ = router_with(cfg, store, {"main": no_connection, "backup": lambda r: httpx.Response(401, text="no")})
    with pytest.raises(AiError) as err:
        router.call(TASK, request_id="REQ-1")
    assert err.value.kind == "auth" and not isinstance(err.value, NetworkOffline)


def test_a_missing_key_is_an_auth_failure_and_falls_through(cfg, store):
    handlers = {"backup": lambda r: httpx.Response(200, json=ok_body())}
    router, seen = router_with(cfg, store, handlers, env={"BACKUP_KEY": "b"})
    _, choice, _ = router.call(TASK, request_id="REQ-1")
    assert choice.provider == "backup" and [h for h, _ in seen] == [host(cfg, "backup")]
    main_run = store.read().list("run")[0].data
    assert main_run["error_kind"] == "no_key" and "MAIN_KEY" in main_run["error_detail"]
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


def test_the_last_account_in_line_is_tried_again_after_waiting(cfg, store):
    replies = iter([httpx.Response(429, headers={"retry-after": "2"}), httpx.Response(200, json=ok_body())])
    cfg.ai.tiers["routine"].fallback = []
    router, seen = router_with(cfg, store, {"main": lambda r: next(replies)})
    waits, told = [], []
    router.sleep = waits.append
    router.on_wait = told.append
    router.call(TASK, request_id="REQ-1")
    assert waits == [2.0] and told == [2.0]
    assert [h for h, _ in seen] == [host(cfg, "main")] * 2


def test_a_wait_longer_than_the_limit_gives_up_without_sleeping(cfg, store):
    cfg.ai.tiers["routine"].fallback = []
    router, seen = router_with(cfg, store, {"main": lambda r: httpx.Response(429, headers={"retry-after": "3600"})})
    router.sleep = lambda s: pytest.fail("must not wait an hour")
    with pytest.raises(AccountPaused) as paused:
        router.call(TASK, request_id="REQ-1")
    assert len(seen) == 1 and paused.value.account == "main" and paused.value.until == NOW + timedelta(hours=1)


def test_an_answer_stopped_at_the_output_limit_is_marked_cut_off(cfg, store):
    body = ok_body('{"summary": "s", "ops": [')
    body["choices"][0]["finish_reason"] = "length"
    router, _ = router_with(cfg, store, {"main": lambda r: httpx.Response(200, json=body)})
    result, _, _ = router.call(TASK, request_id="REQ-1")
    assert result.truncated


MODELS_BODY = {
    "data": [
        {
            "id": "vendor/listed-model",
            "context_length": 200000,
            "top_provider": {"max_completion_tokens": 8000},
            "pricing": {"prompt": "0.000001", "completion": "0.000005", "input_cache_read": "0.0000001"},
        },
        {"id": "vendor/no-prices"},
    ]
}


def test_the_model_list_gives_context_and_prices_per_million(cfg):
    catalog = adapter(cfg, "main", lambda r: httpx.Response(200, json=MODELS_BODY)).catalog()
    listed = catalog["vendor/listed-model"]
    assert (listed.context_tokens, listed.max_output_tokens) == (200000, 8000)
    assert (listed.input_per_million, listed.output_per_million, listed.cached_input_per_million) == (1.0, 5.0, 0.1)
    assert catalog["vendor/no-prices"].input_per_million is None


def test_a_catalog_is_kept_refreshed_when_old_and_kept_when_a_fetch_fails(tmp_path):
    from engine.ai.catalog import Catalogs
    from engine.ai.task import ModelInfo

    now = [1000.0]
    catalogs = Catalogs(tmp_path / "catalog.json", refresh_hours=1, clock=lambda: now[0])
    fetches = []

    def fetch():
        fetches.append(1)
        return {"m": ModelInfo(input_per_million=1.0)}

    assert catalogs.model("acct", "m", fetch).input_per_million == 1.0
    assert catalogs.model("acct", "m", fetch).input_per_million == 1.0 and len(fetches) == 1
    now[0] += 7200
    assert (
        Catalogs(tmp_path / "catalog.json", 1, clock=lambda: now[0]).model("acct", "m", lambda: {}).input_per_million
        == 1.0
    )


def test_cached_input_is_priced_at_the_cached_rate(cfg, store):
    body = ok_body()
    body["usage"]["prompt_tokens_details"] = {"cached_tokens": 800}
    router, _ = router_with(cfg, store, {"main": lambda r: httpx.Response(200, json=body)})
    from engine.config.schema import Price

    model_key = cfg.ai.tiers["routine"].use.partition("/")[2]
    cfg.ai.prices[f"main/{model_key}"] = Price(
        input_per_million=1.0, output_per_million=2.0, cached_input_per_million=0.1
    )
    _, _, run_id = router.call(TASK, request_id="REQ-1")
    run = store.read().get("run", run_id).data
    # 200 fresh input at $1/M + 800 cached at $0.10/M + 500 output at $2/M
    assert run["cached_input_tokens"] == 800
    assert run["cost_usd"] == pytest.approx((200 * 1.0 + 800 * 0.1 + 500 * 2.0) / 1e6)


def test_an_account_whose_model_cant_hold_the_request_is_skipped(cfg, store):
    from engine.ai.task import ModelInfo

    router, seen = router_with(
        cfg,
        store,
        {
            "main": lambda r: httpx.Response(200, json=ok_body()),
            "backup": lambda r: httpx.Response(200, json=ok_body()),
        },
    )
    main_model = cfg.ai.providers["main"].models[cfg.ai.tiers["routine"].use.partition("/")[2]]

    class Small:
        def model(self, provider, model_id, fetch):
            return ModelInfo(context_tokens=100) if model_id == main_model else None

    router.catalogs = Small()
    router.call(TASK, request_id="REQ-1")
    assert [h for h, _ in seen] == [host(cfg, "backup")]


def test_route_sends_matching_requests_to_another_tier():
    from engine.ai.router import route
    from engine.config.schema import AiFile

    cfg = type("Cfg", (), {})()
    cfg.ai = AiFile.model_validate(
        {"routing": [{"when": {"task": "notes", "quoted_messages_over": 3}, "tier": "deep"}]}
    )
    assert route(cfg, "notes", input_chars=100, quoted_messages=5, data_level="internal") == "deep"
    assert route(cfg, "notes", input_chars=100, quoted_messages=1, data_level="internal") == "routine"


@pytest.mark.parametrize(
    "host_part,kind",
    [
        ("localhost:11434", "provider_down"),
        ("127.0.0.1:8080", "provider_down"),
        ("127.3.4.5", "provider_down"),
        ("[::1]:8080", "provider_down"),
        ("models.example.net", "offline"),
        ("192.168.1.20:8080", "offline"),
    ],
)
def test_a_refused_connection_to_this_computer_is_a_stopped_server_not_a_lost_network(cfg, host_part, kind):
    def refused(request):
        raise httpx.ConnectError("connection refused", request=request)

    scheme = httpx.URL(cfg.ai.providers["main"].base_url).scheme
    settings = cfg.ai.providers["main"].model_copy(update={"base_url": f"{scheme}://{host_part}/v1"})
    local = ADAPTERS[settings.adapter](settings, "k", transport=httpx.MockTransport(refused))
    with pytest.raises(AiError) as err:
        local.run(TASK, "m")
    assert err.value.kind == kind
    with pytest.raises(AiError) as listing:
        local.list_models()
    assert listing.value.kind == kind
