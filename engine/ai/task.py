"""The provider-neutral contract for one AI call."""

from __future__ import annotations

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
