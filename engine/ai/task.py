"""The provider-neutral contract for one AI call."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

ErrorKind = Literal[
    "rate_limited",
    "quota",
    "auth",
    "unsupported",  # the service no longer lets this program be used with this kind of account
    "no_key",
    "timeout",
    "invalid_output",
    "no_output",  # the program finished without error but gave no answer
    "provider_down",
    "offline",  # no connection could be made at all; any answer from the service, even a failure, is not this
    "no_work",  # the run did no work: cut off by the computer sleeping, or a program that only printed a banner
    "refused",
    "other",
]


#: What the person reads when a service no longer lets a program run with their kind of account: what happened, and
#: what to do about it. It is never a sign-in hint, because signing in again does not help.
UNSUPPORTED_PLAIN = "The service no longer lets this program run with your kind of account"
UNSUPPORTED_ADVICE = "Pick another account, or use a key instead"


#: Failed runs that say nothing about an account or the model's work: no connection could be made, or the run did
#: nothing. They are no try, never a mistake, and are left out of counts of how an account is doing.
NO_WORK_KINDS = ("offline", "no_work")


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
    knowledge: dict[str, Any] | None = None  # the run's knowledge log (what it was given), written onto its record
    effort: Literal["low", "medium", "high"] | None = None  # the tier's effort; an adapter applies it only if told how
    # The tier's wish about the model's own thinking; an adapter applies "off" only where the model's listed
    # capabilities accept it at the tier's effort.
    thinking: Literal["default", "off"] = "default"
    # What the provider's catalog says about the model this call runs on, for an adapter whose service lists
    # capabilities; None when it isn't known.
    model_info: ModelInfo | None = None

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
    # Capabilities, filled only by an adapter whose service lists them per model. None means the service didn't say.
    efforts: list[str] | None = None  # the effort levels the model takes; an empty list means it takes no effort
    adaptive_thinking: bool | None = None  # whether the model can think on its own, where the service says so
    thinking_off_efforts: list[str] | None = None  # the efforts at which its thinking can be turned off; [] never


class AiError(Exception):
    """A provider call failed. `kind` comes only from the call itself (status, transport), never from model text."""

    def __init__(self, kind: ErrorKind, detail: str = "", *, retry_after: float | None = None, hint: str | None = None):
        self.kind = kind
        self.detail = detail[:2000]
        self.retry_after = retry_after
        self.hint = hint  # what the person can do about it, from the account's settings (a sign-in command)
        super().__init__(f"{kind}: {self.detail}" if self.detail else kind)


@dataclass(frozen=True)
class AgentIdentity:
    """The account a command-line agent runs as, as the program itself says: `account` is what it printed and
    `how_read` says in plain words which command and which part of its output it came from."""

    account: str
    how_read: str


@dataclass(frozen=True)
class IdentityUnknown:
    """The program's sign-in couldn't be read: `reason` says why in plain words. It is never a guess."""

    reason: str


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
