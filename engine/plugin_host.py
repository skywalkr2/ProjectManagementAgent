"""Workspace-local registries, discovery, guarded callbacks and committed events."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import threading
import uuid
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from engine.config.stages import validate_rules, validate_stages
from engine.ops import OP_MODELS, TIERS
from engine.plugin_api import (
    PLUGIN_API_VERSION,
    EventContext,
    NeedsPerson,
    OpWriter,
    PluginMisuse,
    ReadView,
    Registrar,
    Settings,
    StageCheckResult,
)
from engine.plugin_manifest import Manifest, read_manifest
from engine.records import REFERENCES, REGISTRY, ref_fields, values_at
from engine.storage import StoreError, WriteContext
from engine.tasks import TASKS

BUNDLED = Path(__file__).resolve().parents[1] / "plugins"
EVENTS = {
    "stage.moved",
    "changeset.applied",
    "changeset.undone",
    "record.changed",
    "request.queued",
    "question.answered",
}
log = logging.getLogger(__name__)


@dataclass
class PluginStatus:
    name: str
    state: str
    version: str | None = None
    reason: str | None = None


class PluginHost:
    def __init__(self, store: Any, cfg: Any, *, bundled: Path = BUNDLED):
        self.store, self.cfg = store, cfg
        self.records = dict(REGISTRY)
        self.ops = dict(OP_MODELS)
        self.tiers = dict(TIERS)
        self.tasks = dict(TASKS)
        self.stage_checks = {}
        self.stages = cfg.stages.model_copy(deep=True)
        self.status: dict[str, PluginStatus] = {}
        self.manifests: dict[str, Manifest] = {}
        self.registrars: dict[str, Registrar] = {}
        self.candidates: dict[str, Path] = {}
        self._modules: list[str] = []
        self._queue: deque = deque()
        self._dispatching = False
        self._chain: frozenset = frozenset()
        self._lock = threading.RLock()
        self._discover(bundled)
        for name in cfg.workspace.plugins.enabled:
            self._load(name, set())
        defaults = {kind: value for reg in self.registrars.values() for kind, value in reg.stage_defaults.items()}
        merged = dict(defaults)
        for kind, override in self.stages.types.items():
            pack = defaults.get(kind)
            # A workspace entry that leaves out `stages` keeps the pack's list and changes only what it sets.
            stages = override.stages if override.stages is not None else (pack.stages if pack else None)
            merged[kind] = override.model_copy(
                update={"stages": stages, "moves": override.moves or (pack and pack.moves)}
            )
        self.stages.types = merged
        running = {name for name in self.status if self.active(name)}
        try:
            validate_rules(cfg.rules, self.stage_checks, running)
            validate_stages(
                self.stages,
                self.records,
                set(self.stage_checks) | {r.id for r in cfg.rules.rules},
                self.tasks,
                running,
            )
        except Exception:
            self.close()
            raise

    def _discover(self, bundled: Path) -> None:
        for root in (bundled, self.store.path.parent / "plugins"):
            for path in sorted(root.glob("*/plugin.yaml")):
                name = path.parent.name
                if name in self.candidates:
                    self.disable(name, "duplicate plugin name across discovery locations")
                else:
                    self.candidates[name] = path
        for ep in entry_points(group="pm_cockpit.plugins"):
            try:
                # Locate the manifest without ep.load(), which would execute code too early.
                module = ep.value.split(":")[0].split(".")[0]
                path = Path(ep.dist.locate_file(module)) / "plugin.yaml"
                if ep.name in self.candidates:
                    raise ValueError("duplicate plugin name across discovery locations")
                self.candidates[ep.name] = path
            except Exception as err:
                if ep.name in self.cfg.workspace.plugins.enabled:
                    self.disable(ep.name, str(err))

    def disable(self, name: str, reason: str) -> None:
        status = self.status.setdefault(name, PluginStatus(name, "disabled"))
        status.state, status.reason = "disabled", reason
        log.error("Plugin %s disabled for this run: %s", name, reason)
        for other, manifest in list(self.manifests.items()):
            if self.active(other) and any(dep.name == name for dep in manifest.depends_on):
                self.disable(other, f"dependency {name} is disabled")

    def active(self, name: str) -> bool:
        return name in self.status and self.status[name].state == "enabled"

    def _load(self, name: str, visiting: set[str]) -> None:
        if name in visiting:
            raise ValueError(f"dependency cycle involving {name}")
        if name in self.status:
            return
        try:
            if name not in self.candidates:
                raise ValueError("enabled plugin was not found")
            path = self.candidates[name]
            manifest = read_manifest(path)
            if manifest.name != name:
                raise ValueError("manifest name must match its discovery name")
            self.manifests[name] = manifest
            self.status[name] = PluginStatus(name, "loading", manifest.version)
            if Version(PLUGIN_API_VERSION) not in SpecifierSet(manifest.plugin_api):
                raise ValueError(f"plugin API {PLUGIN_API_VERSION} is outside {manifest.plugin_api}")
            p, reach = manifest.provides, manifest.requires
            if p.panels or p.today or p.jobs or p.playbook or manifest.interfaces.provides or manifest.interfaces.uses:
                raise ValueError("manifest requests an extension point not implemented in plugin API 0.x")
            if reach.network or reach.secrets or reach.tools:
                raise ValueError("declared reach is not supported by plugin API 0.x")
            if not set(manifest.events()) <= EVENTS:
                raise ValueError("unsupported event subscription")
            for dep in manifest.depends_on:
                if dep.name not in self.cfg.workspace.plugins.enabled:
                    raise ValueError(f"dependency {dep.name} is not enabled")
                self._load(dep.name, visiting | {name})
                if not self.active(dep.name):
                    raise ValueError(f"dependency {dep.name} failed to load")
                if Version(self.manifests[dep.name].version) not in SpecifierSet(dep.version):
                    raise ValueError(f"dependency {dep.name} does not satisfy {dep.version}")
            symbols = self._importer(path.parent, manifest.entry.split(":")[0].split(".")[0])
            schema = symbols(manifest.config_schema)
            if not isinstance(schema, type) or not issubclass(schema, Settings):
                raise ValueError("config schema must derive from plugin_api.Settings")
            for key, info in schema.model_fields.items():
                if info.is_required() or not info.description:
                    raise ValueError(f"config key {key} needs a default and description")
            config_path = self.store.path.parent / "config" / "plugins" / f"{name}.yaml"
            raw = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
            config = schema.model_validate({} if raw is None else raw)
            registrar = Registrar(name, config)
            symbols(manifest.entry)(registrar)
            self._validate(manifest, registrar)
            self.registrars[name] = registrar
            self.records.update(registrar.records)
            self.ops.update({key: value.model for key, value in registrar.ops.items()})
            self.tiers.update({key: value.tier for key, value in registrar.ops.items()})
            self.tasks.update(registrar.tasks)
            self.stage_checks.update({key: (name, fn) for key, fn in registrar.stage_checks.items()})
            self.status[name].state = "enabled"
        except Exception as err:
            self.disable(name, str(err))

    def _importer(self, root: Path, top: str):
        namespace = "_cockpit_plugin_" + uuid.uuid4().hex
        self._modules.append(namespace)
        init = root / "__init__.py"
        if init.exists():
            spec = importlib.util.spec_from_file_location(namespace, init, submodule_search_locations=[str(root)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[namespace] = module
            spec.loader.exec_module(module)
            prefix = top
        else:
            import types

            module = types.ModuleType(namespace)
            module.__path__ = [str(root)]
            sys.modules[namespace] = module
            prefix = ""

        def symbol(value: str):
            module_name, attribute = value.split(":")
            if prefix:
                if module_name != prefix and not module_name.startswith(prefix + "."):
                    raise ValueError("plugin symbols must live in its own package")
                suffix = module_name[len(prefix) :]
            else:
                suffix = "." + module_name
            return getattr(importlib.import_module(namespace + suffix), attribute)

        return symbol

    def _validate(self, manifest: Manifest, registrar: Registrar) -> None:
        expected = manifest.provides
        for key, actual in (
            ("record_types", registrar.records),
            ("stage_checks", registrar.stage_checks),
            ("stages", registrar.stage_defaults),
            ("ops", registrar.ops),
            ("op_validators", registrar.validators),
            ("ai_task_kinds", registrar.tasks),
        ):
            if set(getattr(expected, key)) != set(actual):
                raise ValueError(f"registered {key} does not match provides exactly")
        if set(manifest.events()) != set(registrar.handlers):
            raise ValueError("registered handlers do not match subscribes exactly")
        prefixes = {model.prefix for model in self.records.values()}
        for model in registrar.records.values():
            if model.prefix in prefixes:
                raise ValueError("record id prefix collides with an existing record type")
            prefixes.add(model.prefix)
        for model in registrar.records.values():
            fields = set(model.model_fields)
            if not set(model.person_only) <= fields or any(not set(group) <= fields for group in model.unique):
                raise ValueError("person_only and unique may name only the record type's own fields")
            if model.data_level not in ("open", "internal", "restricted"):
                raise ValueError("data_level must be open, internal or restricted")
            if model.data_level not in manifest.requires.data_levels:
                raise ValueError("a record type's data_level must be listed in requires.data_levels")
            for field, target in ref_fields(model):
                if target not in REGISTRY and target not in registrar.records:
                    raise ValueError(f"{field} refers to an unknown record kind {target}")
        if not set(registrar.stage_defaults) <= set(registrar.records):
            raise ValueError("default stages may target only the plugin's own record types")
        allowed_ops = set(OP_MODELS) | set(registrar.ops)
        if not set(registrar.validators) <= allowed_ops:
            raise ValueError("validators may target only core or own ops")
        for task in registrar.tasks.values():
            if not set(task.ops) <= allowed_ops:
                raise ValueError("task may use only core or own ops")
        for model in registrar.records.values():
            if "stage" in vars(model).get("__annotations__", {}):
                raise ValueError("the stage field belongs to the core; record types may not redefine it")
        for op in registrar.ops.values():
            for kind, fields in op.writes.items():
                # Core records change only through core ops, so their evidence, owner and tier rules always apply.
                model = registrar.records.get(kind)
                if model is None:
                    raise ValueError("ops may write only the plugin's own record types; use core ops for core records")
                if not fields or ("*" not in fields and not set(fields) <= set(model.model_fields)):
                    raise ValueError("op declares unknown record fields")

    def stage_check(self, check_id, record, view=None):
        """Guard callbacks and fail closed on missing, disabled or malformed checks."""
        from engine.stages import wording

        owner, fn = self.stage_checks.get(check_id, (None, None))
        if owner is None or not self.active(owner):
            return StageCheckResult(False, wording(self.cfg, "check_unavailable"))
        if "/" in record.kind and not record.kind.startswith(owner + "/"):
            return StageCheckResult(False, wording(self.cfg, "check_access"))
        try:
            result = fn(
                deepcopy(record),
                ReadView(view or self.store.read(), owner),
                self.registrars[owner].config.model_copy(deep=True),
            )
            if (
                not isinstance(result, StageCheckResult)
                or type(result.passed) is not bool
                or not isinstance(result.reason, str)
                or not result.reason
            ):
                raise ValueError("stage check must return StageCheckResult with a reason")
            return result
        except Exception as err:
            self.disable(owner, f"stage check failed: {err}")
            return StageCheckResult(False, wording(self.cfg, "check_failed"))

    def task_kind(self, name: str):
        if "/" in name and not self.active(name.split("/")[0]):
            raise StoreError("task plugin is disabled")
        return self.tasks[name]

    def references(self) -> dict[str, list[tuple[str, str]]]:
        """Every declared reference, core and plugin: kind -> [(field path, kind it points to)]."""
        refs = {kind: list(paths) for kind, paths in REFERENCES.items()}
        for kind, model in self.records.items():
            if "/" in kind:
                refs.setdefault(kind, []).extend(ref_fields(model))
        return refs

    def _referrers(self, view: Any) -> Any:
        def find(kind: str, record_id: str) -> list[tuple[str, str]]:
            found = []
            for other, paths in self.references().items():
                for path, target in paths:
                    if target != kind or other not in self.records:
                        continue
                    for stored in view.list(other):
                        if record_id in values_at(stored.data, path):
                            found.append((other, stored.id))
            return found

        return find

    def validators(self, op: Any, view: Any = None, origin: dict[str, str] | None = None) -> list[str]:
        """Plugin validators for one op. `view` is the changeset's own transaction when there is one, so a validator
        sees records earlier ops in the same changeset created; `origin` says who asked (passed to validators that
        take a third argument)."""
        problems = []
        origin = dict(origin or {"actor": "pm", "trust": "trusted", "via": "screen"})
        owner = op.op.split("/")[0] if "/" in op.op else None
        if owner and not self.active(owner):
            problems.append("op plugin is disabled")
        for name, registrar in self.registrars.items():
            for fn in registrar.validators.get(op.op, []):
                if not self.active(name):
                    # A disabled plugin's own ops are refused above; core ops carry on without its validators.
                    continue
                try:
                    args = [op.model_copy(deep=True), ReadView(view if view is not None else self.store.read(), name)]
                    if _takes_three(fn):
                        args.append(dict(origin))
                    result = fn(*args)
                    if not isinstance(result, (list, tuple)) or any(not isinstance(p, str) for p in result):
                        raise ValueError("validators return a list of refusal messages")
                    problems.extend(result)
                except Exception as err:
                    self.disable(name, f"validator failed: {err}")
                    problems.append(f"validator plugin {name} failed")
        return problems

    def apply(self, tx: Any, op: Any, context: WriteContext) -> list[dict[str, str]]:
        name = op.op.split("/")[0]
        if not self.active(name):
            raise StoreError("op plugin is disabled")
        registration = self.registrars[name].ops[op.op]
        writer = OpWriter(tx, name, registration.writes, context, models=self.records, referrers=self._referrers(tx))
        try:
            registration.apply(op.model_copy(deep=True), writer, self.registrars[name].config.model_copy(deep=True))
        except PluginMisuse as err:
            self.disable(name, f"op broke its contract: {err}")
            raise
        except NeedsPerson:
            # Held for the person by the applier; nothing is wrong with the plugin.
            raise
        except StoreError:
            # An ordinary refusal (stale version, invalid value) refuses this op only.
            raise
        except Exception as err:
            self.disable(name, f"op callback failed: {err}")
            raise StoreError(f"plugin {name} op failed") from err
        return writer.touched

    def publish(self, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._queue.append((event, deepcopy(data), self._chain))
            if self._dispatching:
                return
            self._dispatching = True
            try:
                while self._queue:
                    event, payload, chain = self._queue.popleft()
                    for name, registrar in list(self.registrars.items()):
                        key = (name, event)
                        if not self.active(name) or event not in registrar.handlers or key in chain:
                            continue
                        kinds = self.manifests[name].kinds_for(event)
                        if kinds and payload.get("kind") not in kinds:
                            continue
                        self._chain = chain | {key}
                        try:
                            context = EventContext(self.store.read(), name, registrar.config)
                            registrar.handlers[event](deepcopy(payload), context)
                            self._commands(name, context.commands, event, payload)
                        except Exception as err:
                            self.disable(name, f"event {event} failed: {err}")
            finally:
                self._chain = frozenset()
                self._dispatching = False

    def _commands(self, name: str, commands: list, event: str = "", payload: dict | None = None) -> None:
        if not commands:
            return
        context = WriteContext(actor="plugin", trust="untrusted", op=f"{name}/event")
        with self.store.transaction() as tx:
            for kind, data in commands:
                allowed_fields = {"request": {"task", "note"}, "question": {"title", "text"}}
                if kind not in allowed_fields or not set(data) <= allowed_fields[kind]:
                    raise StoreError("event handlers may only queue requests or file questions")
                if kind == "request":
                    task = data["task"]
                    if "/" in task and not task.startswith(name + "/"):
                        raise StoreError("requesting another plugin requires an interface")
                    self.task_kind(task)
                    data = {**data, "origin": "schedule", "created_at": datetime.now(UTC).isoformat()}
                    if event == "stage.moved" and payload and payload.get("to"):
                        from engine.stages import wording

                        # Work a stage move starts waits for the person's go, however it was requested.
                        data |= {
                            "state": "needs_you",
                            "approval": "required",
                            "waiting": wording(self.cfg, "waiting"),
                            "stage_start": {
                                "kind": payload["kind"],
                                "record": payload["id"],
                                "stage": payload["to"],
                                "changeset": None,
                            },
                        }
                else:
                    pm = self.cfg.workspace.user.person
                    if not pm or tx.get("person", pm) is None:
                        raise StoreError("no configured PM to receive the question")
                    data = {**data, "to": pm}
                tx.create(kind, data, context)

    def close(self) -> None:
        for key in list(sys.modules):
            if any(key == name or key.startswith(name + ".") for name in self._modules):
                del sys.modules[key]


def _takes_three(fn: Any) -> bool:
    """Validators written for plugin API 0.1 take (op, view); 0.2 adds an optional third argument, the origin."""
    import inspect

    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) >= 3 or any(p.kind == p.VAR_POSITIONAL for p in params)
