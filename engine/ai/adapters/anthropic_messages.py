"""Adapter for the recommended service's own messages interface, rather than its chat-completions compatibility layer.

The native interface takes the stable part of a packet as a cached prefix, takes a tier's effort in its own setting,
and reports a refusal as its own stop reason, none of which the compatibility layer offers. It needs a base URL, a key
and model ids, all from config.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from engine.ai.adapters.openai_compatible import _int, _retry_after, transport_error
from engine.ai.task import AiError, AiResult, AiTask, ErrorKind, ModelInfo

#: The interface's version header, which every request carries.
API_VERSION = "2023-06-01"
#: What to tell the person when the service stopped the answer under its own safety policy.
REFUSAL_TEXT = "the service declined to answer under its own safety policy"

#: Error types in an error body, by the kind of failure they mean. Only the structured type is read, never the message.
ERROR_TYPES: dict[str, ErrorKind] = {
    "authentication_error": "auth",
    "permission_error": "auth",
    "billing_error": "quota",
    "rate_limit_error": "rate_limited",
    "overloaded_error": "rate_limited",
    "api_error": "provider_down",
}
#: What a status means when the body carries no error type this adapter knows.
STATUS_KINDS: dict[int, ErrorKind] = {401: "auth", 403: "auth", 402: "quota", 429: "rate_limited", 529: "rate_limited"}
#: Stop reasons that mean the answer was cut off before it was complete.
CUT_OFF_STOPS = frozenset({"max_tokens", "model_context_window_exceeded"})


class AnthropicMessagesAdapter:
    name = "anthropic-messages"
    #: This service lists each model's capabilities, so a caller that has the catalog's entry hands it over in
    #: `AiTask.model_info` (the router from its kept catalog, the smoke test from one read of the list).
    reads_capabilities = True

    def __init__(self, settings: Any, secret: str | None = None, *, transport: httpx.BaseTransport | None = None):
        if not settings.base_url:
            raise AiError("other", "this account has no base_url")
        self.settings = settings
        headers = {"Content-Type": "application/json", "anthropic-version": API_VERSION}
        if secret:
            headers["x-api-key"] = secret
        base = settings.base_url.rstrip("/")
        # The address of the compatibility layer ends in /v1, which this interface's paths already carry.
        base = base.removesuffix("/v1")
        self._client = httpx.Client(
            base_url=base, headers=headers, timeout=settings.timeout_seconds, transport=transport
        )

    def run(self, task: AiTask, model: str) -> AiResult:
        body = request_body(
            task,
            model,
            send_temperature=getattr(self.settings, "send_temperature", True),
            thinking_room=getattr(self.settings, "thinking_room", 0),
        )
        started = time.monotonic()
        try:
            response = self._client.post("/v1/messages", json=body)
        except httpx.TimeoutException as err:
            raise AiError("timeout", str(err)) from None
        except httpx.TransportError as err:
            raise transport_error(err, self.settings.base_url) from None
        seconds = time.monotonic() - started
        if response.status_code >= 400:
            raise classify_http_error(response)
        try:
            data = response.json()
            blocks = data["content"]
            if not isinstance(blocks, list):
                raise TypeError("content is not a list")
            text = "".join(b["text"] for b in blocks if isinstance(b, dict) and b.get("type") == "text" and "text" in b)
            stop = data.get("stop_reason")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AiError("invalid_output", "the response wasn't in the expected format") from None
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        # `input_tokens` is only what wasn't read from or written to the cache; the router counts it as the whole
        # prompt with the cached part inside it, so the three are added up here.
        read = _int(usage.get("cache_read_input_tokens"))
        written = _int(usage.get("cache_creation_input_tokens"))
        fresh = _int(usage.get("input_tokens"))
        total = None if fresh is None else fresh + (read or 0) + (written or 0)
        refused = stop == "refusal"
        return AiResult(
            text=text,
            model_served=str(data.get("model") or model),
            seconds=seconds,
            input_tokens=total,
            output_tokens=_int(usage.get("output_tokens")),
            cached_input_tokens=read,
            truncated=stop in CUT_OFF_STOPS,
            refused=refused,
            refusal=REFUSAL_TEXT if refused else None,
        )

    def capability_notes(self, task: AiTask) -> list[str]:
        """What the task asks for that the model's listed capabilities don't allow, in plain words, one line each:
        what was therefore left out of the request. Empty when everything asked for is sent (or when the list says
        nothing about the model, which is sent as asked)."""
        return capability_notes(task)

    def identity(self) -> None:
        """Not applicable: the account is a key, not a sign-in of a person."""
        return None

    def catalog(self) -> dict[str, ModelInfo]:
        """The account's models with their context and output limits; empty when the list can't be read. The service's
        list carries no prices, so those come from config."""
        try:
            return self.list_models()
        except AiError:
            return {}

    def list_models(self) -> dict[str, ModelInfo]:
        """The model list, raising `AiError` with the kind of failure (a key not accepted, the service down) instead of
        returning nothing, so a setup screen can say what went wrong."""
        out: dict[str, ModelInfo] = {}
        after: str | None = None
        for _ in range(max(1, getattr(self.settings, "model_list_pages", 10))):
            items, more = self._model_page(after)
            before = len(out)
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                efforts, adaptive = listed_capabilities(item.get("capabilities"))
                out[item["id"]] = ModelInfo(
                    context_tokens=_int(item.get("max_input_tokens")),
                    max_output_tokens=_int(item.get("max_tokens")),
                    efforts=efforts,
                    adaptive_thinking=adaptive,
                )
            if more is None or more == after or len(out) == before:
                break
            after = more
        return out

    def _model_page(self, after: str | None) -> tuple[list[Any], str | None]:
        """One page of the model list and, when the service says more follow, the id to ask for the page after."""
        try:
            response = self._client.get("/v1/models", params={"after_id": after} if after else None)
        except httpx.TimeoutException as err:
            raise AiError("timeout", str(err)) from None
        except httpx.TransportError as err:
            raise transport_error(err, self.settings.base_url) from None
        if response.status_code >= 400:
            raise classify_http_error(response)
        try:
            body = response.json()
            items = body.get("data") or []
            last = body.get("last_id")
            more = last if body.get("has_more") is True and isinstance(last, str) and last else None
        except (ValueError, AttributeError):
            raise AiError("invalid_output", "the model list wasn't in the expected format") from None
        return (items if isinstance(items, list) else []), more


def _supported(node: Any) -> bool | None:
    """The `supported` flag of one node of a capability tree, or None when the node or the flag isn't there."""
    flag = node.get("supported") if isinstance(node, dict) else None
    return flag if isinstance(flag, bool) else None


def listed_capabilities(tree: Any) -> tuple[list[str] | None, bool | None]:
    """The effort levels a model takes and whether it can think on its own, from the model list's capability tree.

    Each is None when the tree doesn't carry it (unknown). The effort node says `supported` and then one node per
    level it takes; a model whose node says it isn't supported takes none, which is an empty list, not unknown. Whether
    thinking can be turned off, and at which efforts, is not read: the tree has no node for it."""
    if not isinstance(tree, dict):
        return None, None
    node = tree.get("effort")
    levels = [k for k, v in node.items() if k != "supported" and _supported(v)] if isinstance(node, dict) else []
    efforts: list[str] | None = None
    if _supported(node) is False:
        efforts = []
    elif _supported(node) is True and levels:
        efforts = levels
    thinking = tree.get("thinking")
    types = thinking.get("types") if isinstance(thinking, dict) else None
    adaptive = _supported(types.get("adaptive")) if isinstance(types, dict) else None
    return efforts, adaptive


def _effort_taken(task: AiTask) -> bool:
    """Whether the tier's effort is sent: when the model's listed efforts include it, or when they aren't known."""
    info = task.model_info
    return bool(task.effort) and (info is None or info.efforts is None or task.effort in info.efforts)


def _thinking_off(task: AiTask) -> bool:
    """Whether thinking is turned off: when the tier asks for it and the model's listed capabilities accept it at the
    tier's effort. Never when the list doesn't say."""
    info = task.model_info
    if task.thinking != "off" or info is None or not info.thinking_off_efforts:
        return False
    return bool(task.effort) and _effort_taken(task) and task.effort in info.thinking_off_efforts


def capability_notes(task: AiTask) -> list[str]:
    """Plain-words reasons for each setting of the task that the model's listed capabilities don't allow, so the
    smoke test can say what was left out instead of dropping it silently."""
    info = task.model_info
    notes: list[str] = []
    if task.effort and info is not None and info.efforts is not None and task.effort not in info.efforts:
        notes.append(
            f"this model takes effort {', '.join(info.efforts)}, so {task.effort} was left out and the model uses "
            "its own"
            if info.efforts
            else f"this model takes no effort setting, so {task.effort} was left out"
        )
    if task.thinking == "off" and not _thinking_off(task):
        if info is None or info.thinking_off_efforts is None:
            notes.append("the service doesn't say this model's thinking can be turned off, so thinking was left on")
        elif not info.thinking_off_efforts:
            notes.append("this model's thinking can't be turned off, so it was left on")
        elif not task.effort:
            notes.append("thinking can be turned off only at an effort this tier hasn't set, so it was left on")
        else:
            taken = ", ".join(info.thinking_off_efforts)
            notes.append(
                f"this model's thinking can be turned off only at effort {taken}, not {task.effort}, so it was left on"
            )
    return notes


def request_body(task: AiTask, model: str, *, send_temperature: bool, thinking_room: int = 0) -> dict[str, Any]:
    """The request for one task: the instructions and then the stable part as the system prompt, with the cache marker
    on the last of them so the whole stable prefix is cached, and the request as the one user turn.

    The answer limit leaves `thinking_room` tokens beyond the task's own for a model whose listed capabilities say it
    thinks on its own (and whose thinking isn't turned off), within the model's own output limit, so thinking never
    uses up the room the answer needs. The effort goes only where the model's listed efforts include it."""
    system = [{"type": "text", "text": text} for text in (task.instructions, task.stable) if text]
    if system:
        system[-1]["cache_control"] = {"type": "ephemeral"}
    off = _thinking_off(task)
    info = task.model_info
    limit = task.max_output
    if info is not None and info.adaptive_thinking and not off and thinking_room > 0:
        limit = task.max_output + thinking_room
        if info.max_output_tokens is not None:
            limit = max(task.max_output, min(limit, info.max_output_tokens))
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": limit,
        "system": system,
        "messages": [{"role": "user", "content": task.request}],
    }
    if send_temperature:
        body["temperature"] = task.temperature
    if _effort_taken(task):
        body["output_config"] = {"effort": task.effort}
    if off:
        body["thinking"] = {"type": "disabled"}
    return body


def _error_type(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    kind = error.get("type") if isinstance(error, dict) else None
    return kind if isinstance(kind, str) else ""


def classify_http_error(response: httpx.Response) -> AiError:
    """Turn an HTTP error into an error kind from the error body's own type, or from the status when the body gives
    none this adapter knows, never from its wording."""
    status = response.status_code
    detail = f"HTTP {status}: {response.text[:500]}"
    kind: ErrorKind | None = ERROR_TYPES.get(_error_type(response)) or STATUS_KINDS.get(status)
    if kind is None:
        kind = "provider_down" if status >= 500 else "other"
    if kind in ("quota", "rate_limited", "provider_down"):
        return AiError(kind, detail, retry_after=_retry_after(response))
    return AiError(kind, detail)
