"""A stand-in AI for tests, evaluation dry runs and trying the app without an account.

With a responder set, it answers with whatever the responder returns. Without one, it reads inputs and answers questions
by plain rules (`stand_in`), so the whole loop can be tried with no AI at all.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from engine.ai.adapters import stand_in
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
        if task.output == "text":
            return AiResult(
                text=f"A draft about: {first or 'nothing in particular'}\n", model_served="stub", seconds=0.0
            )
        if task.kind == "ask":
            body = stand_in.answer(task.request, task.stable)
        elif task.kind == "notes":
            body = stand_in.read(task.request)
        elif task.kind == "sort-mail":
            body = stand_in.sort_mail(task.request)
        elif task.kind == "learn.correction":
            body = {"summary": "Nothing to generalize.", "topic": "", "ops": []}
        else:
            body = {"summary": "Filed the input as a note.", "ops": [{"op": "note", "text": first or "(empty input)"}]}
        return AiResult(text=json.dumps(body), model_served="stub", seconds=0.0)

    def catalog(self) -> dict:
        return {}


def _first_line(request: str) -> str:
    match = re.search(r"<untrusted[^>]*>\s*(.+?)\s*</untrusted>", request, re.S) or re.search(
        r"<note>\s*(.+?)\s*</note>", request, re.S
    )
    text = match.group(1) if match else request
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""
