"""AI task kinds: what each kind of work may return and which prompt it uses."""

from __future__ import annotations

from dataclasses import dataclass

from engine.ops import OP_MODELS


@dataclass(frozen=True)
class TaskKind:
    name: str
    ops: tuple[str, ...]
    prompt: str
    playbook: str


TASKS: dict[str, TaskKind] = {
    "notes": TaskKind(name="notes", ops=tuple(OP_MODELS), prompt="notes", playbook="notes"),
}


def task_kind(name: str) -> TaskKind:
    try:
        return TASKS[name]
    except KeyError:
        raise KeyError(f"unknown task kind {name!r}") from None
