"""The provider-neutral contract for one AI call."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

ErrorKind = Literal["rate_limited", "quota", "auth", "no_key", "timeout", "invalid_output", "provider_down", "other"]


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


class AiError(Exception):
    """A provider call failed. `kind` comes only from the call itself (status, transport), never from model text."""

    def __init__(self, kind: ErrorKind, detail: str = "", *, retry_after: float | None = None):
        self.kind = kind
        self.detail = detail[:2000]
        self.retry_after = retry_after
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
