"""AI adapters. Vendor and model names may appear only inside this package and in configuration."""

from __future__ import annotations

from typing import Any, Protocol

from engine.ai.adapters.anthropic_messages import AnthropicMessagesAdapter
from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.adapters.openai_compatible import OpenAICompatibleAdapter
from engine.ai.adapters.stub import StubAdapter
from engine.ai.task import AiResult, AiTask


class Adapter(Protocol):
    """What every adapter does. Capabilities beyond `run` are optional methods the caller looks for: `catalog`,
    `program_version` and `lockdown_test` (a command-line agent), and `identity`, which returns the account a
    command-line agent runs as (or why that can't be told), and None for an adapter it doesn't apply to.

    Two capabilities serve the estimates (`engine/ai/calibration.py`): `count_tokens(task, model)` returns the tokens
    the service counts for a request without running it, and raises `CountNotOffered` when it can't; an adapter with no
    such method doesn't offer it (the app's own count stands). `adds_overhead = True` says the adapter's program adds
    its own text to every request, so the account check measures that fixed overhead from its small call."""

    name: str

    def run(self, task: AiTask, model: str) -> AiResult: ...


#: The adapter for a service that has none of its own: any endpoint that takes the common chat format.
GENERIC_ADAPTER = OpenAICompatibleAdapter.name

ADAPTERS: dict[str, type[Any]] = {
    StubAdapter.name: StubAdapter,
    OpenAICompatibleAdapter.name: OpenAICompatibleAdapter,
    AnthropicMessagesAdapter.name: AnthropicMessagesAdapter,
    CliAgentAdapter.name: CliAgentAdapter,
}


def make_adapter(name: str, settings: Any, secret: str | None) -> Adapter:
    try:
        cls = ADAPTERS[name]
    except KeyError:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"no adapter called {name!r} is installed (installed: {known})") from None
    return cls(settings, secret)
