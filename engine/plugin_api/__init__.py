"""The public plugin contract. In-process plugins are trusted code, not a sandbox.

Register contributions atomically at startup. Op callbacks get a writer limited to
model.writes; validators and event handlers get read-only views. Handler commands
are staged until the handler returns successfully.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from engine.ops import EvidenceIn, OpModel, Tier
from engine.records import Record
from engine.storage import Stored, StoreError, WriteContext
from engine.tasks import TaskKind

PLUGIN_API_VERSION = "0.1.0"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)
    version: Literal[1] = Field(1, description="Settings format version.")


class ReadView:
    """Read core records and this plugin's records, never another plugin's tables."""

    def __init__(self, view: Any, plugin: str):
        self.__view, self.__plugin = view, plugin

    def _allow(self, kind: str) -> None:
        if "/" in kind and not kind.startswith(self.__plugin + "/"):
            raise StoreError("another plugin's records require a declared interface")

    def get(self, kind: str, record_id: str) -> Stored | None:
        self._allow(kind)
        return self.__view.get(kind, record_id)

    def list(self, kind: str) -> list[Stored]:
        self._allow(kind)
        return self.__view.list(kind)


class OpWriter(ReadView):
    """An op's only write surface; context and declared fields cannot be replaced."""

    def __init__(self, tx: Any, plugin: str, writes: dict[str, tuple[str, ...]], context: WriteContext):
        super().__init__(tx, plugin)
        self.__tx, self.__writes, self.__context = tx, writes, context
        self.touched: list[dict[str, str]] = []

    def _write(self, kind: str, fields: set[str]) -> None:
        self._allow(kind)
        allowed = self.__writes.get(kind, ())
        if not allowed or ("*" not in allowed and not fields <= set(allowed)):
            raise StoreError("op attempted to write outside its declared fields")

    def create(self, kind: str, data: dict[str, Any]) -> Stored:
        self._write(kind, {"*"})
        result = self.__tx.create(kind, data, self.__context)
        self.touched.append({"kind": kind, "id": result.id})
        return result

    def update(self, kind: str, record_id: str, changes: dict[str, Any], *, read_version: int) -> Stored:
        self._write(kind, set(changes))
        result = self.__tx.update(kind, record_id, changes, self.__context, read_version=read_version)
        self.touched.append({"kind": kind, "id": result.id})
        return result


class EventContext(ReadView):
    """Commands are requests to the core, never direct record writes or sends."""

    def __init__(self, view: Any, plugin: str, config: Settings):
        super().__init__(view, plugin)
        self.config = config.model_copy(deep=True)
        self.commands: list[tuple[str, dict[str, Any]]] = []

    def queue_request(self, task: str, note: str) -> None:
        self.commands.append(("request", {"task": task, "note": note}))

    def file_question(self, title: str, text: str = "") -> None:
        """File a question for the configured PM; sending is never part of handling an event."""
        self.commands.append(("question", {"title": title, "text": text}))


@dataclass(frozen=True)
class OpRegistration:
    model: type[OpModel]
    tier: Tier
    apply: Callable
    writes: dict[str, tuple[str, ...]]


class Registrar:
    """A staging registry: the host installs it only after checking the manifest."""

    def __init__(self, name: str, config: Settings):
        self.name, self.config = name, config
        self.records: dict[str, type[Record]] = {}
        self.ops: dict[str, OpRegistration] = {}
        self.validators: dict[str, list[Callable]] = {}
        self.tasks: dict[str, TaskKind] = {}
        self.handlers: dict[str, Callable] = {}

    def _name(self, name: str) -> None:
        if not re.fullmatch(re.escape(self.name) + r"/[a-z][a-z0-9_.-]*", name):
            raise ValueError(f"identifier must be namespaced {self.name}/<name>: {name}")

    def record_type(self, model: type[Record]) -> None:
        if not issubclass(model, Record):
            raise ValueError("record_type requires a Record model")
        self._name(model.record_kind)
        if model.record_kind in self.records or not re.fullmatch(r"[A-Z]+", model.prefix):
            raise ValueError("duplicate record kind or invalid id prefix")
        self.records[model.record_kind] = model

    def op(self, model: type[OpModel], tier: Tier, apply: Callable) -> None:
        if not issubclass(model, OpModel) or "op" not in model.model_fields:
            raise ValueError("op requires an OpModel with a literal op identifier")
        annotation = model.model_fields["op"].annotation
        names = get_args(annotation)
        if get_origin(annotation) is not Literal or len(names) != 1 or not isinstance(names[0], str):
            raise ValueError("op identifier must be a single literal")
        name = names[0]
        self._name(name)
        writes = getattr(model, "writes", None)
        if name in self.ops or tier not in ("data", "outbound", "system") or not callable(apply) or not writes:
            raise ValueError("duplicate op, invalid tier/callback, or missing model.writes")
        for kind in writes:
            if "/" in kind:
                self._name(kind)
        self.ops[name] = OpRegistration(model, tier, apply, writes)

    def op_validator(self, op_name: str, fn: Callable) -> None:
        if not callable(fn):
            raise ValueError("validator must be callable")
        self.validators.setdefault(op_name, []).append(fn)

    def task_kind(self, name: str, *, ops: tuple[str, ...], prompt: str = "notes", playbook: str = "notes") -> None:
        self._name(name)
        if name in self.tasks or not ops:
            raise ValueError("duplicate task kind or empty op list")
        self.tasks[name] = TaskKind(name, ops, prompt, playbook)

    def subscribe(self, event: str, fn: Callable) -> None:
        if event in self.handlers or not callable(fn):
            raise ValueError("duplicate subscription or invalid handler")
        self.handlers[event] = fn


__all__ = [
    "PLUGIN_API_VERSION",
    "Settings",
    "Record",
    "OpModel",
    "EvidenceIn",
    "Tier",
    "WriteContext",
    "Stored",
    "StoreError",
    "ReadView",
    "OpWriter",
    "EventContext",
    "Registrar",
]
