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

from engine.config.schema import StageDefinition, TypeStages
from engine.ops import EvidenceIn, OpModel, Tier
from engine.records import Record, RefTo, ref_fields
from engine.storage import Stored, StoreError, WriteContext
from engine.tasks import TaskKind

PLUGIN_API_VERSION = "0.2.0"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)
    version: Literal[1] = Field(1, description="Settings format version.")


class PluginMisuse(StoreError):
    """The plugin broke its contract (reached outside its scope); the host disables it for the run."""


class NeedsPerson(StoreError):
    """An op set a value only the person may set; the host holds it for the person instead of applying it."""


class ReadView:
    """Read core records and this plugin's records, never another plugin's tables."""

    def __init__(self, view: Any, plugin: str):
        self.__view, self.__plugin = view, plugin

    def _allow(self, kind: str) -> None:
        if "/" in kind and not kind.startswith(self.__plugin + "/"):
            raise PluginMisuse("another plugin's records require a declared interface")

    def get(self, kind: str, record_id: str) -> Stored | None:
        self._allow(kind)
        return self.__view.get(kind, record_id)

    def list(self, kind: str, *, project: str | None = None, **equals: Any) -> list[Stored]:
        """Live records of a kind, optionally only those in one project or with given field values (matched in the
        database, not by reading every record)."""
        self._allow(kind)
        if project is not None:
            equals = {**equals, "project": project}
        return self.__view.find(kind, equals) if equals else self.__view.list(kind)

    def find(self, kind: str, **equals: Any) -> Stored | None:
        """The first live record of a kind with these field values, or None."""
        found = self.list(kind, **equals)
        return found[0] if found else None


class OpWriter(ReadView):
    """An op's only write surface; context and declared fields cannot be replaced."""

    def __init__(
        self,
        tx: Any,
        plugin: str,
        writes: dict[str, tuple[str, ...]],
        context: WriteContext,
        models: dict[str, type[Record]] | None = None,
        referrers: Callable[[str, str], list[tuple[str, str]]] | None = None,
    ):
        super().__init__(tx, plugin)
        self.__tx, self.__writes, self.__context = tx, writes, context
        self.__models = models or {}
        self.__referrers = referrers or (lambda kind, record_id: [])
        self.touched: list[dict[str, str]] = []

    def _declared(self, kind: str, record_id: str | None, data: dict[str, Any]) -> None:
        """Enforce what the record type declares: person-only values, unique fields and references."""
        model = self.__models.get(kind)
        if model is None:
            return
        if self.__context.actor != "pm":
            for field, values in model.person_only.items():
                if field in data and data[field] in values:
                    raise NeedsPerson(f"only you can set {field} to {data[field]}")
        current = self.__tx.get(kind, record_id).data if record_id else {}
        merged = {**current, **data}
        for group in model.unique:
            if not set(group) & set(data):
                continue
            equals = {f: merged.get(f) for f in group}
            clash = [s for s in self.__tx.find(kind, equals) if s.id != record_id]
            if clash:
                shown = ", ".join(f"{f}={v}" for f, v in equals.items())
                raise StoreError(f"there is already a {kind} with {shown}")
        for field, target in ref_fields(model):
            value = data.get(field)
            if value is not None and self.__tx.get(target, value) is None:
                raise StoreError(f"{field} refers to {target} {value}, which doesn't exist")

    def _write(self, kind: str, fields: set[str]) -> None:
        self._allow(kind)
        allowed = self.__writes.get(kind, ())
        if not allowed or ("*" not in allowed and not fields <= set(allowed)):
            raise PluginMisuse("op attempted to write outside its declared fields")

    def create(self, kind: str, data: dict[str, Any]) -> Stored:
        if kind == "request" and (data.get("stage_start") is not None or data.get("approval") is not None):
            raise PluginMisuse("stage task approval belongs to the core")
        if data.get("stage") is not None:
            raise PluginMisuse("stage changes require stage.move")
        self._write(kind, {"*"})
        self._declared(kind, None, data)
        result = self.__tx.create(kind, data, self.__context)
        self.touched.append({"kind": kind, "id": result.id})
        return result

    def update(self, kind: str, record_id: str, changes: dict[str, Any], *, read_version: int) -> Stored:
        if kind == "request" and {"approval", "stage_start"} & set(changes):
            raise PluginMisuse("stage task approval belongs to the core")
        if "stage" in changes:
            raise PluginMisuse("stage changes require stage.move")
        self._write(kind, set(changes))
        self._declared(kind, record_id, changes)
        result = self.__tx.update(kind, record_id, changes, self.__context, read_version=read_version)
        self.touched.append({"kind": kind, "id": result.id})
        return result

    def delete(self, kind: str, record_id: str, *, read_version: int) -> None:
        """Delete one of this plugin's records (the op must declare `("*",)` for the kind). Refused while another
        live record refers to it; Undo brings it back."""
        self._write(kind, {"*"})
        users = self.__referrers(kind, record_id)
        if users:
            raise StoreError(f"{kind} {record_id} is still referred to by {users[0][0]} {users[0][1]}")
        self.__tx.delete(kind, record_id, self.__context, read_version=read_version)
        self.touched.append({"kind": kind, "id": record_id})


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


@dataclass(frozen=True)
class StageCheckResult:
    passed: bool
    reason: str


class Registrar:
    """A staging registry: the host installs it only after checking the manifest."""

    def __init__(self, name: str, config: Settings):
        self.name, self.config = name, config
        self.records: dict[str, type[Record]] = {}
        self.ops: dict[str, OpRegistration] = {}
        self.validators: dict[str, list[Callable]] = {}
        self.tasks: dict[str, TaskKind] = {}
        self.handlers: dict[str, Callable] = {}
        self.stage_checks: dict[str, Callable] = {}
        self.stage_defaults: dict[str, TypeStages] = {}

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
        if name in self.ops or tier not in ("data", "system") or not callable(apply) or not writes:
            raise ValueError(
                "duplicate op, invalid tier (outbound ops wait for the publisher), callback, or missing model.writes"
            )
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

    def stage_check(self, id: str, fn: Callable) -> None:
        """Register a pure check: (record, read_view, settings) -> StageCheckResult. Never call AI."""
        self._name(id)
        if id in self.stage_checks or not callable(fn):
            raise ValueError("duplicate stage check or invalid callback")
        self.stage_checks[id] = fn

    def stages(self, record_type: str, stages: list[StageDefinition | dict], *, moves=None) -> None:
        """Supply replaceable defaults for one of this plugin's record types."""
        self._name(record_type)
        if record_type in self.stage_defaults:
            raise ValueError("duplicate default stages")
        self.stage_defaults[record_type] = TypeStages(stages=stages, moves=moves)

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
    "NeedsPerson",
    "PluginMisuse",
    "RefTo",
    "Tier",
    "WriteContext",
    "Stored",
    "StoreError",
    "ReadView",
    "OpWriter",
    "EventContext",
    "Registrar",
    "StageDefinition",
    "StageCheckResult",
]
