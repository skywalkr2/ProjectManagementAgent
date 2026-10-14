"""Which work the core's own learning steps run on (design 6.22, "Plugins and the learning loop").

A record type or a task kind declares `learning: own` when what it holds is not workspace knowledge (a story's cast
and plan). The core's learning from inputs, its new-term scan, first-name resolution against people and fact ranking
into the workspace's facts don't run on that work. Every one of those steps asks `learns_on` before it starts.
"""

from __future__ import annotations

from typing import Any

LEARNING = ("core", "own")


def learns_on(plugins: Any, *, task_kind: str | None = None, record_type: str | None = None) -> bool:
    """Whether the core's learning steps run on this work: False when the task kind declares `learning: own`, when the
    record type does, or when the task kind works on a record type that does. Names that aren't known learn."""
    kind = plugins.tasks.get(task_kind) if task_kind else None
    if kind is not None:
        if kind.learning == "own":
            return False
        record_type = record_type or kind.on
    model = plugins.records.get(record_type) if record_type else None
    return model is None or model.learning != "own"


def request_learns(store: Any, request: dict[str, Any]) -> bool:
    """`learns_on` for a request's data: its task kind and the record it is about (or the one whose stage entry
    started it)."""
    target = request.get("about") or {}
    record_type = target.get("kind") or (request.get("stage_start") or {}).get("kind")
    return learns_on(store.plugins, task_kind=request.get("task"), record_type=record_type)
