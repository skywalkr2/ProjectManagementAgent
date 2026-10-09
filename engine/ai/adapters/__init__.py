"""AI adapters. Vendor and model names may appear only inside this package and in configuration."""

from __future__ import annotations

from typing import Any, Protocol

from engine.ai.adapters.openai_compatible import OpenAICompatibleAdapter
from engine.ai.adapters.stub import StubAdapter
from engine.ai.task import AiResult, AiTask


class Adapter(Protocol):
    name: str

    def run(self, task: AiTask, model: str) -> AiResult: ...


ADAPTERS: dict[str, type[Any]] = {
    StubAdapter.name: StubAdapter,
    OpenAICompatibleAdapter.name: OpenAICompatibleAdapter,
}


def make_adapter(name: str, settings: Any, secret: str | None) -> Adapter:
    try:
        cls = ADAPTERS[name]
    except KeyError:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"no adapter called {name!r} is installed (installed: {known})") from None
    return cls(settings, secret)
