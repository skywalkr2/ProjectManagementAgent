"""The provider-neutral contract for one AI call."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

ErrorKind = Literal[
    "rate_limited", "quota", "auth", "no_key", "timeout", "invalid_output", "provider_down", "refused", "other"
]


@dataclass(frozen=True)
class AiTask:
    """One call: what kind of work, the packet split into its stable part and its request part, and limits."""

    kind: str
    instructions: str
    stable: str
    request: str
    output_schema: dict[str, Any]
    temperature: float = 0.0
    max_output: int = 4000
    output: Literal["json", "text"] = "json"  # text: the answer is prose (a draft), not a JSON object
    expected_output: int | None = None  # this run's likely answer size in tokens, when its packet knows better

    @property
    def size(self) -> int:
        return len(self.instructions) + len(self.stable) + len(self.request)


@dataclass(frozen=True)
class AiResult:
    text: str
    model_served: str
    seconds: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    upstream: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False  # the provider stopped at the output limit, so the text is incomplete
    cached_input_tokens: int | None = None  # input tokens the provider served from its prompt cache
    # The provider said it refused the work under its own policy (a stop reason or refusal field, never the text).
    refused: bool = False
    refusal: str | None = None  # the provider's own reason, if it gave one
    cost_usd: float | None = None  # what the provider itself reports the call cost, when it does


@dataclass
class ModelInfo:
    """What a provider's catalog says about one model; any field may be unknown."""

    context_tokens: int | None = None
    max_output_tokens: int | None = None
    input_per_million: float | None = None
    output_per_million: float | None = None
    cached_input_per_million: float | None = None


class AiError(Exception):
    """A provider call failed. `kind` comes only from the call itself (status, transport), never from model text."""

    def __init__(self, kind: ErrorKind, detail: str = "", *, retry_after: float | None = None, hint: str | None = None):
        self.kind = kind
        self.detail = detail[:2000]
        self.retry_after = retry_after
        self.hint = hint  # what the person can do about it, from the account's settings (a sign-in command)
        super().__init__(f"{kind}: {self.detail}" if self.detail else kind)


REASON_LIMIT = 200


def provider_reason(detail: str, limit: int = REASON_LIMIT) -> str:
    """The provider's own words for a failure: the `error.message` (or `message`) of a JSON body inside the detail,
    otherwise its first `limit` characters. Empty when there is no detail. It is the provider's text, shown as data."""
    text = " ".join(detail.split())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            body = json.loads(text[start : end + 1])
        except ValueError:
            body = None
        if isinstance(body, dict):
            error = body.get("error")
            message = error.get("message") if isinstance(error, dict) else error if isinstance(error, str) else None
            message = message if isinstance(message, str) and message.strip() else body.get("message")
            if isinstance(message, str) and message.strip():
                return " ".join(message.split())[:limit].rstrip(" .")
    return text[:limit].rstrip(" .")
