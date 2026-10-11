"""AI task kinds: what each kind of work may return, which prompt and guidance it uses, what its runs see, and its
default settings (the workspace's `ai.tasks.<kind>` overrides any of them)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from dataclasses import field as _field
from pathlib import Path
from typing import Any

from engine.ops import OP_MODELS

#: Core ops reading notes never offers: deleting is the person's call, file.add is made only by person actions, and
#: starting projects is for actions and plugin work.
NOT_FROM_NOTES = {
    "record.delete",
    "file.add",
    "project.add",
    "record.edit",
    "text.edit",
    "text.propose",
    "text.accept",
    "text.discard",
    "text.draft",
}


@dataclass(frozen=True)
class TaskKind:
    name: str
    ops: tuple[str, ...]
    prompt: str
    playbook: str
    label: str = ""
    on: str | None = None  # the record kind a run is about, if any
    packet: Callable[..., Any] | None = None  # (target, view, settings, note) -> PacketParts, from a plugin
    defaults: dict[str, Any] = field(default_factory=dict)  # TaskSettings fields the plugin sets
    prompt_file: Path | None = None  # a plugin's own prompt template
    guidance_file: Path | None = None  # a plugin's own guidance
    output: str = "ops"  # "draft": the answer is prose for the long text field `field` of the record it is about
    field: str | None = None
    anchored: bool = False  # a draft that revises the current text, paragraph by paragraph, with ids
    questions: int = 0  # how many questions for the person a draft may end with
    role: str = "write"  # write, check (an independent second opinion) or research
    where: dict[str, tuple[Any, ...]] = _field(default_factory=dict)  # field values a record of kind `on` must have

    def offered_on(self, record: Any) -> bool:
        """Whether this work applies to a record (of kind `on`): every `where` field holds one of its values."""
        return all(record.data.get(key) in values for key, values in self.where.items())


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


def settings(cfg: Any, kind: TaskKind | None, name: str | None = None) -> Any:
    """A task kind's settings: its own defaults, then the tier its role maps to (ai.roles), then whatever the
    workspace's ai.tasks.<kind> sets."""
    from engine.config.schema import TaskSettings

    key = kind.name if kind is not None else name
    configured = cfg.ai.tasks.get(key) if key else None
    values = dict(kind.defaults) if kind is not None else {}
    role_tier = getattr(cfg.ai.roles, kind.role).tier if kind is not None else None
    if role_tier is not None:
        values["tier"] = role_tier
    if configured is not None:
        values.update({f: getattr(configured, f) for f in configured.model_fields_set})
    return TaskSettings.model_validate(values)
