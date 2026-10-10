"""Adapter for any endpoint that speaks the widely used chat-completions format.

Many vendors offer such an endpoint, as do aggregators and local model servers, so one adapter covers them: it needs a
base URL, a key (except for local servers) and model ids, all from config.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from engine.ai.task import AiError, AiResult, AiTask


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
        if self.settings.json_mode:
            body["response_format"] = {"type": "json_object"}
        started = time.monotonic()
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as err:
            raise AiError("timeout", str(err)) from None
        except httpx.TransportError as err:
            raise AiError("provider_down", str(err)) from None
        seconds = time.monotonic() - started
        if response.status_code >= 400:
            raise classify_http_error(response)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
            truncated = data["choices"][0].get("finish_reason") == "length"
        except (ValueError, KeyError, IndexError, TypeError):
            raise AiError("invalid_output", "the response wasn't in the expected format") from None
        usage = data.get("usage") or {}
        return AiResult(
            text=text,
            model_served=str(data.get("model") or model),
            seconds=seconds,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            upstream=data.get("provider"),
            truncated=truncated,
        )


def classify_http_error(response: httpx.Response) -> AiError:
    """Turn an HTTP error into an error kind from the status code and headers only."""
    status = response.status_code
    detail = f"HTTP {status}: {response.text[:500]}"
    retry_after = _retry_after(response)
    if status in (401, 403):
        return AiError("auth", detail)
    if status == 402:
        return AiError("quota", detail)
    if status == 429:
        return AiError("rate_limited", detail, retry_after=retry_after)
    if status >= 500:
        return AiError("provider_down", detail, retry_after=retry_after)
    return AiError("other", detail)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
