"""AI task kinds: what each kind of work may return and which prompt it uses."""

from __future__ import annotations

from dataclasses import dataclass

from engine.ops import OP_MODELS

#: Core ops reading notes never offers: deleting is the person's call, and file.add is made only by person actions.
NOT_FROM_NOTES = {"record.delete", "file.add"}


@dataclass(frozen=True)
class TaskKind:
    name: str
    ops: tuple[str, ...]
    prompt: str
    playbook: str


TASKS: dict[str, TaskKind] = {
    # Reading notes never deletes anything; deletion is the person's own act (or a plugin task that declares it).
    "notes": TaskKind(
        name="notes", ops=tuple(n for n in OP_MODELS if n not in NOT_FROM_NOTES), prompt="notes", playbook="notes"
    ),
}


def task_kind(name: str) -> TaskKind:
    try:
        return TASKS[name]
    except KeyError:
        raise KeyError(f"unknown task kind {name!r}") from None
