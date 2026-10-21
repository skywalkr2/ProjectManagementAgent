"""The native adapter for the recommended service's own messages interface (design 6.16): the exact request, the answer
read from text blocks only, stop reasons as outcomes, errors from the structured type never the words, the model list
read page by page, and the smoke test with a tier's exact parameters.

The adapter's name, address and header names are read from `tests/fixtures/ai/catalog-claims.yaml`, so no service is
named here. Everything runs against a stubbed transport."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import yaml

from engine.ai.adapters import ADAPTERS, make_adapter
from engine.ai.smoke import smoke_test
from engine.ai.task import AiError, AiTask
from engine.config import load_config
from engine.config.schema import ProviderSettings
from engine.setup import known_endpoints

CLAIMS = yaml.safe_load((Path(__file__).parent / "fixtures" / "ai" / "catalog-claims.yaml").read_text("utf-8"))
NATIVE = CLAIMS["native_adapter"]
AI_FIXTURES = Path(__file__).parent / "fixtures" / "ai"
MODEL = "example-model"
TASK = AiTask("notes", "Do it.", "Reference.", "Input.", {}, temperature=0.3, max_output=1234, output="json")


def settings(**extra) -> ProviderSettings:
    """An account as the catalog makes it: no temperature sent unless a test says so."""
    return ProviderSettings(
        **{"adapter": NATIVE["adapter"], "base_url": NATIVE["base_url"], "send_temperature": False, **extra}
    )


def adapter_with(handler, secret="k", **extra):
    return ADAPTERS[NATIVE["adapter"]](settings(**extra), secret, transport=httpx.MockTransport(handler))


def answer(content=None, stop="end_turn", usage=None, model="served-model"):
    return {
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": "{}"}] if content is None else content,
        "stop_reason": stop,
        "usage": {"input_tokens": 10, "output_tokens": 5} if usage is None else usage,
    }


def run(task=TASK, body=None, status=200, headers=None, **extra):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=answer() if body is None else body, headers=headers)

    result = adapter_with(handler, **extra).run(task, MODEL)
    return result, seen


# ---- the request ---------------------------------------------------------------------------------------------------


def test_a_json_task_without_an_effort_sends_the_cached_system_prompt_and_nothing_else():
    _, seen = run()
    request = seen[0]
    assert str(request.url) == NATIVE["base_url"] + NATIVE["path"]
    assert json.loads(request.content) == {
        "model": MODEL,
        "max_tokens": 1234,
        "system": [
            {"type": "text", "text": "Do it."},
            {"type": "text", "text": "Reference.", "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content": "Input."}],
    }


def test_a_tiers_effort_goes_in_the_place_the_interface_documents():
    _, seen = run(replace(TASK, effort="high"))
    body = json.loads(seen[0].content)
    assert body["output_config"] == {"effort": "high"}
    assert "temperature" not in body and "tools" not in body and "thinking" not in body
    assert "fallbacks" not in body and "response_format" not in body


def test_the_headers_are_the_key_and_the_version_the_documentation_names():
    _, seen = run()
    assert seen[0].headers[NATIVE["key_header"]] == "k"
    assert seen[0].headers[NATIVE["version_header"]] == NATIVE["version"]
    assert "authorization" not in seen[0].headers


def test_with_no_key_no_key_header_is_sent():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=answer())

    ADAPTERS[NATIVE["adapter"]](settings(), None, transport=httpx.MockTransport(handler)).run(TASK, MODEL)
    assert NATIVE["key_header"] not in seen[0].headers


@pytest.mark.parametrize("send", [True, False])
def test_a_temperature_is_sent_only_when_the_account_says_to(send):
    _, seen = run(send_temperature=send)
    body = json.loads(seen[0].content)
    assert ("temperature" in body) is send
    if send:
        assert body["temperature"] == 0.3


def test_the_cache_marker_goes_on_the_last_block_that_exists():
    _, seen = run(replace(TASK, stable=""))
    system = json.loads(seen[0].content)["system"]
    assert system == [{"type": "text", "text": "Do it.", "cache_control": {"type": "ephemeral"}}]


def test_the_address_of_the_compatibility_layer_still_reaches_the_same_path():
    _, seen = run(base_url=NATIVE["base_url"] + "/v1/")
    assert str(seen[0].url) == NATIVE["base_url"] + NATIVE["path"]


def test_the_catalog_entry_names_this_adapter_and_builds_it():
    kind = next(e for e in known_endpoints() if e["id"] == NATIVE["entry"])
    assert kind["adapter"] == NATIVE["adapter"] and kind["base_url"] == NATIVE["base_url"]
    assert kind["settings"]["send_temperature"] is False
    assert {"json_mode", "max_tokens_param", "effort_param"}.isdisjoint(kind["settings"])
    assert kind["tier_presets"]
    built = make_adapter(
        kind["adapter"],
        ProviderSettings.model_validate({**kind["settings"], "adapter": kind["adapter"], "base_url": kind["base_url"]}),
        "k",
    )
    assert isinstance(built, ADAPTERS[NATIVE["adapter"]])


# ---- the answer ----------------------------------------------------------------------------------------------------


def test_the_text_is_taken_from_text_blocks_only():
    content = [
        {"type": "thinking", "thinking": "private reasoning", "signature": "s"},
        {"type": "text", "text": '{"a": '},
        {"type": "unknown_kind", "text": "not this"},
        {"type": "text", "text": "1}"},
    ]
    result, _ = run(body=answer(content))
    assert result.text == '{"a": 1}'
    assert result.model_served == "served-model" and not result.truncated and not result.refused


def test_an_answer_cut_off_by_the_output_limit_is_truncated():
    result, _ = run(body=answer(stop="max_tokens"))
    assert result.truncated and not result.refused


def test_an_answer_cut_off_by_the_context_window_is_truncated_too():
    result, _ = run(body=answer(stop="model_context_window_exceeded"))
    assert result.truncated


def test_a_refusal_stop_is_the_refusal_outcome_and_is_not_retried_inside_the_call():
    result, seen = run(body=answer(content=[], stop="refusal"))
    assert result.refused and result.refusal and result.text == "" and not result.truncated
    assert len(seen) == 1


def test_usage_adds_the_cached_parts_to_the_prompt_and_reports_the_cache_reads():
    usage = {
        "input_tokens": 20,
        "cache_creation_input_tokens": 30,
        "cache_read_input_tokens": 400,
        "output_tokens": 7,
    }
    result, _ = run(body=answer(usage=usage))
    assert result.input_tokens == 450 and result.cached_input_tokens == 400 and result.output_tokens == 7


def test_usage_without_cache_fields_has_no_cache_reads():
    result, _ = run()
    assert (result.input_tokens, result.output_tokens, result.cached_input_tokens) == (10, 5, None)


@pytest.mark.parametrize("body", [{"content": "not a list"}, {"nothing": 1}, ["x"]])
def test_an_answer_in_another_shape_is_invalid_output(body):
    with pytest.raises(AiError) as err:
        run(body=body)
    assert err.value.kind == "invalid_output"


# ---- errors --------------------------------------------------------------------------------------------------------


def error_body(kind, message="x"):
    return {"type": "error", "error": {"type": kind, "message": message}}


@pytest.mark.parametrize(
    ("status", "error_type", "kind"),
    [
        (400, "invalid_request_error", "other"),
        (401, "authentication_error", "auth"),
        (402, "billing_error", "quota"),
        (403, "permission_error", "auth"),
        (404, "not_found_error", "other"),
        (413, "request_too_large", "other"),
        (429, "rate_limit_error", "rate_limited"),
        (500, "api_error", "provider_down"),
        (529, "overloaded_error", "rate_limited"),
    ],
)
def test_each_documented_error_type_gives_its_kind(status, error_type, kind):
    with pytest.raises(AiError) as err:
        run(body=error_body(error_type), status=status)
    assert err.value.kind == kind


@pytest.mark.parametrize(
    ("error_type", "kind"),
    [("invalid_request_error", "other"), ("not_found_error", "other"), ("api_error", "provider_down")],
)
def test_the_message_never_decides_the_kind(error_type, kind):
    worded = "authentication failed: invalid key; rate limit exceeded; credit balance too low; overloaded"
    status = 500 if kind == "provider_down" else 400
    with pytest.raises(AiError) as err:
        run(body=error_body(error_type, worded), status=status)
    assert err.value.kind == kind


def test_the_type_decides_over_the_status_when_the_body_has_one():
    with pytest.raises(AiError) as err:
        run(body=error_body("overloaded_error"), status=500)
    assert err.value.kind == "rate_limited"


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "auth"),
        (403, "auth"),
        (402, "quota"),
        (429, "rate_limited"),
        (529, "rate_limited"),
        (503, "provider_down"),
        (400, "other"),
    ],
)
def test_a_body_with_no_known_type_is_read_by_its_status_alone(status, kind):
    for body in ("no", {"error": "plain"}, error_body("a_type_nobody_documented")):

        def handler(request, body=body):
            return httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)

        with pytest.raises(AiError) as err:
            adapter_with(handler).run(TASK, MODEL)
        assert err.value.kind == kind


@pytest.mark.parametrize(
    ("status", "error_type"), [(429, "rate_limit_error"), (529, "overloaded_error"), (500, "api_error")]
)
def test_the_retry_after_answer_is_kept_and_a_bad_one_is_ignored(status, error_type):
    with pytest.raises(AiError) as err:
        run(body=error_body(error_type), status=status, headers={"retry-after": "7"})
    assert err.value.retry_after == 7.0
    with pytest.raises(AiError) as err:
        run(body=error_body(error_type), status=status, headers={"retry-after": "soon"})
    assert err.value.retry_after is None


def test_a_timeout_no_connection_and_a_broken_exchange_are_their_own_kinds():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def no_connection(request):
        raise httpx.ConnectError("name not resolved", request=request)

    def broken(request):
        raise httpx.RemoteProtocolError("closed mid-answer", request=request)

    for handler, kind in ((timeout, "timeout"), (no_connection, "offline"), (broken, "provider_down")):
        with pytest.raises(AiError) as err:
            adapter_with(handler).run(TASK, MODEL)
        assert err.value.kind == kind


def test_an_account_with_no_address_is_refused_at_once():
    with pytest.raises(AiError):
        ADAPTERS[NATIVE["adapter"]](ProviderSettings(adapter=NATIVE["adapter"]), "k")


# ---- the model list ------------------------------------------------------------------------------------------------


def model(model_id, context=1_000_000, output=128_000):
    return {"id": model_id, "display_name": model_id, "max_input_tokens": context, "max_tokens": output}


def test_the_model_list_is_read_over_two_pages_with_its_limits_and_no_prices():
    pages = {
        None: {"data": [model("m-one"), model("m-two", 200_000, 64_000)], "has_more": True, "last_id": "m-two"},
        "m-two": {"data": [model("m-three", None, None)], "has_more": False, "last_id": "m-three"},
    }
    asked = []

    def handler(request):
        asked.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=pages[request.url.params.get("after_id")])

    models = adapter_with(handler).list_models()
    assert asked == [(NATIVE["models_path"], {}), (NATIVE["models_path"], {"after_id": "m-two"})]
    assert list(models) == ["m-one", "m-two", "m-three"]
    assert (models["m-one"].context_tokens, models["m-one"].max_output_tokens) == (1_000_000, 128_000)
    assert (models["m-two"].context_tokens, models["m-two"].max_output_tokens) == (200_000, 64_000)
    assert (models["m-three"].context_tokens, models["m-three"].max_output_tokens) == (None, None)
    assert all(m.input_per_million is None and m.output_per_million is None for m in models.values())
    assert models == adapter_with(handler).catalog()


def test_the_model_list_stops_at_the_configured_number_of_pages():
    asked = []

    def handler(request):
        asked.append(request.url.params.get("after_id"))
        n = len(asked)
        return httpx.Response(200, json={"data": [model(f"m-{n}")], "has_more": True, "last_id": f"m-{n}"})

    models = adapter_with(handler, model_list_pages=3).list_models()
    assert len(asked) == 3 and list(models) == ["m-1", "m-2", "m-3"]


def test_a_page_that_repeats_itself_ends_the_listing():
    asked = []

    def handler(request):
        asked.append(1)
        return httpx.Response(200, json={"data": [model("m-1")], "has_more": True, "last_id": "m-1"})

    assert list(adapter_with(handler).list_models()) == ["m-1"] and len(asked) == 2


def test_a_model_list_that_fails_says_why_and_the_catalog_is_empty():
    def refused(request):
        return httpx.Response(401, json=error_body("authentication_error"))

    with pytest.raises(AiError) as err:
        adapter_with(refused).list_models()
    assert err.value.kind == "auth"
    assert adapter_with(refused).catalog() == {}

    def odd(request):
        return httpx.Response(200, text="not json")

    with pytest.raises(AiError) as err:
        adapter_with(odd).list_models()
    assert err.value.kind == "invalid_output"


def test_an_account_has_no_sign_in_identity():
    assert adapter_with(lambda request: httpx.Response(200, json=answer())).identity() is None


# ---- the smoke test ------------------------------------------------------------------------------------------------


def native_config():
    """The AI test accounts all made native accounts, with no temperature sent and the routine tier at an effort."""
    cfg = load_config(AI_FIXTURES, env={})
    providers = {
        n: p.model_copy(
            update={"adapter": NATIVE["adapter"], "base_url": NATIVE["base_url"], "send_temperature": False}
        )
        for n, p in cfg.ai.providers.items()
    }
    tiers = {n: t.model_copy(update={"effort": "high" if n == "routine" else None}) for n, t in cfg.ai.tiers.items()}
    return replace(cfg, files={**cfg.files, "ai": cfg.ai.model_copy(update={"providers": providers, "tiers": tiers})})


def test_the_smoke_test_passes_with_the_exact_parameters_of_each_tier():
    cfg = native_config()
    seen: list[dict] = []

    def factory(name, provider_settings, secret):
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=answer([{"type": "text", "text": '{"ok": true}'}]))

        return ADAPTERS[name](provider_settings, secret, transport=httpx.MockTransport(handler))

    results = smoke_test(cfg, {"MAIN_KEY": "k", "BACKUP_KEY": "k"}, factory)
    calls = [r for r in results if r.part == "call"]
    assert calls and all(r.ok and r.answered for r in calls), [r.detail for r in calls if not r.ok]
    tests = [b for b in seen if b["system"][0]["text"] == "This is a connection test."]
    assert tests and all("temperature" not in b and "tools" not in b for b in tests)
    by_tokens = {(c.params[0], c.params[2]): c.tier for c in calls}
    for body in tests:
        assert body["messages"][0]["role"] == "user" and body["max_tokens"] in {k[1] for k in by_tokens}
    efforts = {b.get("output_config", {}).get("effort") for b in tests}
    assert efforts == {"high", None}
    routine = [r for r in calls if r.tier == "routine"]
    assert routine and all(r.params[-1] == "high" for r in routine)


def test_the_smoke_test_reports_a_refused_key_by_its_kind():
    cfg = native_config()

    def factory(name, provider_settings, secret):
        def handler(request):
            return httpx.Response(401, json=error_body("authentication_error"))

        return ADAPTERS[name](provider_settings, secret, transport=httpx.MockTransport(handler))

    calls = [r for r in smoke_test(cfg, {"MAIN_KEY": "k", "BACKUP_KEY": "k"}, factory) if r.part == "call"]
    assert calls and all(not r.ok and r.error_kind == "auth" for r in calls)
