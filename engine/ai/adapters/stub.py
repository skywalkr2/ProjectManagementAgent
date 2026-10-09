"""A stand-in AI for tests, evaluation dry runs and trying the app without an account.

With a responder set, it answers with whatever the responder returns. Without one, it files the input as a note, so the
whole loop can be exercised with no AI at all.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from engine.ai.task import AiResult, AiTask

Responder = Callable[[AiTask], str]
_responder: Responder | None = None


def set_responder(responder: Responder | None) -> None:
    global _responder
    _responder = responder


class StubAdapter:
    name = "stub"

    def __init__(self, settings: object, secret: str | None = None):
        self.settings = settings

    def run(self, task: AiTask, model: str) -> AiResult:
        if _responder is not None:
            return AiResult(text=_responder(task), model_served="stub", seconds=0.0)
        first = _first_line(task.request)
        body = {"summary": "Filed the input as a note.", "ops": [{"op": "note", "text": first or "(empty input)"}]}
        return AiResult(text=json.dumps(body), model_served="stub", seconds=0.0)


def _first_line(request: str) -> str:
    match = re.search(r"<untrusted[^>]*>\s*(.+?)\s*</untrusted>", request, re.S) or re.search(
        r"<note>\s*(.+?)\s*</note>", request, re.S
    )
    text = match.group(1) if match else request
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""
