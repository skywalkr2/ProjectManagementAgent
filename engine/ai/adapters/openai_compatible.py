"""Adapter for any endpoint that speaks the widely used chat-completions format.

Many vendors offer such an endpoint, as do aggregators and local model servers, so one adapter covers them: it needs a
base URL, a key (except for local servers) and model ids, all from config.
"""

from __future__ import annotations

import ipaddress
import time
from typing import Any

import httpx

from engine.ai.task import AiError, AiResult, AiTask, ModelInfo


class OpenAICompatibleAdapter:
    name = "openai-compatible"

    def __init__(self, settings: Any, secret: str | None = None, *, transport: httpx.BaseTransport | None = None):
        if not settings.base_url:
            raise AiError("other", "this account has no base_url")
        self.settings = settings
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        self._client = httpx.Client(
            base_url=settings.base_url.rstrip("/"),
            headers=headers,
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    def run(self, task: AiTask, model: str) -> AiResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": task.instructions + "\n\n" + task.stable},
                {"role": "user", "content": task.request},
            ],
            "temperature": task.temperature,
            "max_tokens": task.max_output,
        }
        if self.settings.json_mode and task.output == "json":
            body["response_format"] = {"type": "json_object"}
        started = time.monotonic()
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as err:
            raise AiError("timeout", str(err)) from None
        except httpx.TransportError as err:
            raise transport_error(err, self.settings.base_url) from None
        seconds = time.monotonic() - started
        if response.status_code >= 400:
            raise classify_http_error(response)
        try:
            data = response.json()
            message = data["choices"][0]["message"]
            text = message.get("content") or ""
            finish = data["choices"][0].get("finish_reason")
            truncated = finish == "length"
            refusal = message.get("refusal") if isinstance(message.get("refusal"), str) else None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AiError("invalid_output", "the response wasn't in the expected format") from None
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return AiResult(
            text=text,
            model_served=str(data.get("model") or model),
            seconds=seconds,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            upstream=data.get("provider"),
            truncated=truncated,
            refused=bool(refusal and refusal.strip()) or finish in REFUSAL_STOPS,
            refusal=(refusal or "").strip() or (REFUSAL_STOPS.get(finish) if finish else None),
            cached_input_tokens=details.get("cached_tokens") if isinstance(details, dict) else None,
        )

    def identity(self) -> None:
        """Not applicable: the account is a key, not a sign-in of a person."""
        return None

    def catalog(self) -> dict[str, ModelInfo]:
        """The account's model list, with context size and prices where the endpoint publishes them; empty when it
        can't be read.

        Endpoints that list models without prices still give their ids; prices then come from config. Per-token prices
        in the listing are turned into prices per million tokens."""
        try:
            return self.list_models()
        except AiError:
            return {}

    def list_models(self) -> dict[str, ModelInfo]:
        """The model list, raising `AiError` with the kind of failure (a key not accepted, the service down or not
        there) instead of returning nothing, so a setup screen can say what went wrong."""
        try:
            response = self._client.get("/models")
        except httpx.TimeoutException as err:
            raise AiError("timeout", str(err)) from None
        except httpx.TransportError as err:
            raise transport_error(err, self.settings.base_url) from None
        if response.status_code >= 400:
            raise classify_http_error(response)
        try:
            items = response.json().get("data") or []
        except (ValueError, AttributeError):
            raise AiError("invalid_output", "the model list wasn't in the expected format") from None
        out: dict[str, ModelInfo] = {}
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
            top = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
            out[item["id"]] = ModelInfo(
                context_tokens=_int(item.get("context_length")),
                max_output_tokens=_int(top.get("max_completion_tokens")),
                input_per_million=_per_million(pricing.get("prompt")),
                output_per_million=_per_million(pricing.get("completion")),
                cached_input_per_million=_per_million(pricing.get("input_cache_read")),
            )
        return out


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _per_million(value: Any) -> float | None:
    try:
        per_token = float(value)
    except (TypeError, ValueError):
        return None
    return round(per_token * 1_000_000, 6) if per_token >= 0 else None


#: Stop reasons that mean the provider's own filter stopped the answer, with what to tell the person.
REFUSAL_STOPS = {"content_filter": "the provider's content filter stopped the answer"}
#: Error codes or types in a provider's error body that mean it refused the request under its own policy.
REFUSAL_CODES = {
    "content_filter",
    "content_policy_violation",
    "moderation",
    "safety",
    "responsible_ai_policy_violation",
}


def _refusal_code(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return False
    return any(str(error.get(key, "")).lower() in REFUSAL_CODES for key in ("code", "type"))


def classify_http_error(response: httpx.Response) -> AiError:
    """Turn an HTTP error into an error kind from the status code, headers and the error body's own code, never from
    its wording."""
    status = response.status_code
    detail = f"HTTP {status}: {response.text[:500]}"
    retry_after = _retry_after(response)
    if status in (400, 403) and _refusal_code(response):
        return AiError("refused", detail)
    if status in (401, 403):
        return AiError("auth", detail)
    if status == 402:
        return AiError("quota", detail, retry_after=retry_after)
    if status == 429:
        return AiError("rate_limited", detail, retry_after=retry_after)
    if status >= 500:
        return AiError("provider_down", detail, retry_after=retry_after)
    return AiError("other", detail)


def is_local(base_url: str) -> bool:
    """Whether an account's address is on this computer: localhost or a loopback address."""
    host = (httpx.URL(base_url).host or "").lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def transport_error(err: httpx.TransportError, base_url: str = "") -> AiError:
    """A call that got no answer, from the kind of transport failure: no connection could be made at all (the name
    didn't resolve, or the connection couldn't be opened) is `offline`; any other break in the exchange is
    `provider_down`. A connection refused by a server on this computer is no loss of network: that server is not
    running, so it is `provider_down`."""
    no_connection = isinstance(err, httpx.ConnectError) and not (base_url and is_local(base_url))
    return AiError("offline" if no_connection else "provider_down", str(err))


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
