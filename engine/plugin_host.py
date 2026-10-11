"""Workspace-local registries, discovery, guarded callbacks and committed events."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import re
import sys
import threading
import uuid
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field as dataclass_field
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
from engine.plugin_manifest import NOT_YET, Manifest, installed_manifest, read_manifest
from engine.records import REFERENCES, REGISTRY, ref_fields, values_at
from engine.storage import StoreError, WriteContext
from engine.tasks import TASKS

BUNDLED = Path(__file__).resolve().parents[1] / "plugins"
#: Events plugins may subscribe to: what each means and the fields of its payload. Payloads carry ids and names,
#: never record contents; read the record for its values.
EVENT_SPECS: dict[str, tuple[str, dict[str, str]]] = {
    "record.changed": (
        "A record was created, changed, deleted or brought back by Undo. One event per record per op.",
        {
            "kind": "The record's kind.",
            "id": "The record's id.",
            "version": "The record's version after the change.",
            "op": "The ledger's op name, with the op's index in its changeset after '#'.",
            "fields": "The names of the fields that changed; `_deleted` for a delete and for its Undo.",
        },
    ),
    "stage.moved": (
        "A record moved to another stage, by the person, a rule or Undo.",
        {
            "kind": "The record's kind.",
            "id": "The record's id.",
            "version": "The record's version after the move.",
            "from": "The stage it left (None when it had none yet).",
            "to": "The stage it entered (None when Undo took it back out of its steps).",
            "op": "The ledger's op name.",
        },
    ),
    "file.added": ("A file was added.", {"id": "The file's id.", "kind": "The file's kind."}),
    "text.accepted": (
        "A long text field got a new current version: the person's edit, an accepted draft or proposal, or a merge.",
        {
            "kind": "The kind of the record the field is on.",
            "id": "That record's id.",
            "field": "The long text field.",
            "version": "The number of the version now current.",
            "previous": "The number of the version it replaced (None for the first).",
            "source": "edit, draft, proposal, merge or import.",
            "authorship": "Words by kind of author: {person, assistant, assistant_edit}.",
        },
    ),
    "request.queued": ("AI work was queued.", {"id": "The request's id."}),
    "question.answered": ("A question was answered.", {"id": "The question's id."}),
    "changeset.applied": ("A changeset was applied (some of its ops may be held or refused).", {"id": "Its id."}),
    "changeset.undone": (
        "Ops of a changeset were undone.",
        {"id": "The changeset's id.", "ops": "The indexes of the ops undone."},
    ),
}
EVENTS = set(EVENT_SPECS)
#: Events whose payload names a kind, so a subscription can be limited to kinds (file kinds for file.added).
EVENTS_WITH_KIND = {"record.changed", "stage.moved", "file.added", "text.accepted"}
log = logging.getLogger(__name__)


@dataclass
class PluginStatus:
    name: str
    state: str
    version: str | None = None
    reason: str | None = None
    tools: dict[str, str] = dataclass_field(default_factory=dict)  # tool name -> what was found on this computer
    notes: list[str] = dataclass_field(default_factory=list)  # what the person should know, though it loaded


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
        self._tools: Any = None
        from engine.actions import Proposals

        self.proposals = Proposals()
        self.candidates: dict[str, Path] = {}
        self.notes: dict[str, list[str]] = {}  # things the person should know about a plugin that still loads
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
        """Bundled plugins, then the workspace's plugins/ folder, then installed ones. A plugin in the workspace's
        folder wins over an installed one of the same name (the usual case while developing it), with a note in its
        status; any other duplicate is refused."""
        local = self.store.path.parent / "plugins"
        for root in (bundled, local):
            for path in sorted(root.glob("*/plugin.yaml")):
                name = path.parent.name
                if name in self.candidates:
                    self.disable(name, "duplicate plugin name across discovery locations")
                else:
                    self.candidates[name] = path
        for ep in entry_points(group="pm_cockpit.plugins"):
            try:
                # Locate the manifest without ep.load(), which would execute code too early.
                path = installed_manifest(ep)
                existing = self.candidates.get(ep.name)
                if existing is not None and existing.parent.parent == local:
                    note = (
                        f"the copy in the workspace's plugins folder is used; the installed one ({path.parent}) isn't"
                    )
                    self.notes.setdefault(ep.name, []).append(note)
                    continue
                if existing is not None:
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
            self.status[name] = PluginStatus(name, "loading", manifest.version, notes=list(self.notes.get(name, [])))
            if Version(PLUGIN_API_VERSION) not in SpecifierSet(manifest.plugin_api):
                raise ValueError(f"plugin API {PLUGIN_API_VERSION} is outside {manifest.plugin_api}")
            if manifest.provides.data and not (path.parent / manifest.provides.data).is_dir():
                raise ValueError(
                    f"provides.data names {manifest.provides.data}, which isn't a folder beside plugin.yaml"
                )
            for key in NOT_YET:
                section, _, attribute = key.partition(".")
                if getattr(getattr(manifest, section), attribute):
                    raise ValueError(f"{key} is not available in plugin API {PLUGIN_API_VERSION} yet")
            self._check_tools(name, manifest)
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
            registrar = Registrar(name, config, path.parent)
            symbols(manifest.entry)(registrar)
            self._validate(manifest, registrar)
            self.registrars[name] = registrar
            self.records.update(registrar.records)
            self.ops.update({key: value.model for key, value in registrar.ops.items()})
            self.tiers.update({key: value.tier for key, value in registrar.ops.items()})
            self.tasks.update(registrar.tasks)
            self.stage_checks.update({key: (name, fn) for key, fn in registrar.stage_checks.items()})
            self.status[name].notes += self._file_kind_notes(registrar)
            self.status[name].state = "enabled"
        except Exception as err:
            self.disable(name, str(err))

    def _file_kind_notes(self, registrar: Registrar) -> list[str]:
        """A file kind keeps only the media types the workspace accepts; say so when that drops some or all of them."""
        accepted = set(self.cfg.storage.files.accepted_types)
        notes = []
        for kind in registrar.file_kinds.values():
            dropped = [t for t in kind.accept if t not in accepted]
            if not dropped:
                continue
            kept = [t for t in kind.accept if t in accepted]
            notes.append(
                f"file kind {kind.name}: {', '.join(dropped)} isn't accepted in this workspace "
                f"(storage.files.accepted_types), so it accepts {', '.join(kept) if kept else 'no files at all'}"
            )
        return notes

    @property
    def tools(self) -> Any:
        """The runner for declared programs on this computer, made on first use."""
        if self._tools is None:
            from engine.tools import ToolLimits, Tools, read_locations

            limits = ToolLimits(**self.cfg.workspace.plugins.tools.model_dump())
            self._tools = Tools(read_locations(self.store.path.parent / ".cockpit" / "tools.yaml"), limits)
        return self._tools

    def _check_tools(self, name: str, manifest: Manifest) -> None:
        """Probe each declared program: a missing required one keeps the plugin off; a missing optional one only
        turns off the features listed with it, which the plugin checks with `tools.available`."""
        import shlex

        names = [tool.name for tool in manifest.requires.tools]
        if len(names) != len(set(names)):
            raise ValueError("declare each tool once in requires.tools")
        for tool in manifest.requires.tools:
            words = shlex.split(tool.probe)
            if not words or words[0] != tool.name:
                raise ValueError(f"the probe for {tool.name} must start with the tool's name")
        for tool in manifest.requires.tools:
            status = self.tools.probe(tool.name, tool.probe, tool.min_version)
            shown = f"found {status.version}" if status.found and status.version else "found"
            self.status[name].tools[tool.name] = shown if status.found else status.reason
            if not status.found and not tool.optional:
                raise ValueError(f"needs {tool.name}: {status.reason}")

    def tool_box(self, name: str) -> Any:
        """The declared programs one plugin may run; each run is recorded as a tool_run."""
        from engine.tools import ToolBox

        declared = {tool.name: tool for tool in self.manifests[name].requires.tools}
        return ToolBox(self.tools, name, declared, self._record_tool_run)

    def _record_tool_run(
        self, plugin: str, tool: str, args: list[str], inputs: list[str], result: Any, version: str | None = None
    ) -> None:
        context = WriteContext(actor="plugin", trust="untrusted", op=f"{plugin}/tool")
        with self.store.transaction() as tx:
            tx.create(
                "tool_run",
                {
                    "plugin": plugin,
                    "tool": tool,
                    "version": version,
                    "args": args,
                    "inputs": inputs,
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "output_cut": result.output_cut,
                    "seconds": result.seconds,
                    "collected": [{"name": n, "size": len(b)} for n, b in result.files.items()],
                    "omitted": result.omitted,
                    "stderr_tail": result.stderr[-4000:],
                    "ran_at": datetime.now(UTC).isoformat(),
                },
                context,
            )

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
        from engine.files import CORE_KINDS

        expected = manifest.provides
        for key, actual in (
            ("record_types", registrar.records),
            ("stage_checks", registrar.stage_checks),
            ("stages", registrar.stage_defaults),
            ("ops", registrar.ops),
            ("op_validators", registrar.validators),
            ("ai_task_kinds", registrar.tasks),
            ("file_kinds", registrar.file_kinds),
            ("actions", registrar.actions),
            ("lints", registrar.lints),
            ("text_formats", registrar.text_formats),
        ):
            if set(getattr(expected, key)) != set(actual):
                raise ValueError(f"registered {key} does not match provides exactly")
        if set(manifest.events()) != set(registrar.handlers):
            raise ValueError("registered handlers do not match subscribes exactly")
        if len(manifest.events()) != len(set(manifest.events())):
            raise ValueError("subscribe to each event once; one handler can route the kinds it gets")
        for event in manifest.events():
            kinds = manifest.kinds_for(event)
            if not kinds:
                continue
            if event not in EVENTS_WITH_KIND:
                raise ValueError(f"{event} carries no kind, so it can't be filtered by kinds")
            known = (
                set(CORE_KINDS) | set(registrar.file_kinds)
                if event == "file.added"
                else set(REGISTRY) | set(registrar.records)
            )
            unknown = sorted(set(kinds) - known)
            if unknown:
                raise ValueError(f"{event} filter names {', '.join(unknown)}: not a core kind or the plugin's own")
        prefixes = {model.prefix for model in self.records.values()}
        for model in registrar.records.values():
            if model.prefix in prefixes:
                raise ValueError("record id prefix collides with an existing record type")
            prefixes.add(model.prefix)
        for model in registrar.records.values():
            fields = set(model.model_fields)
            if not set(model.person_only) <= fields or any(not set(group) <= fields for group in model.unique):
                raise ValueError("person_only and unique may name only the record type's own fields")
            from engine.texts import CORE_FORMATS, long_text_fields

            for field_name, fmt in long_text_fields(model).items():
                if fmt not in CORE_FORMATS and fmt not in registrar.text_formats:
                    raise ValueError(f"{model.record_kind}.{field_name} uses an unknown text format {fmt}")
            levels = model.content_levels_field
            if levels is not None and (
                levels not in fields or "list[str]" not in str(model.model_fields[levels].annotation)
            ):
                raise ValueError(f"{model.record_kind}.content_levels_field must name one of its list[str] fields")
            if model.data_level not in ("open", "internal", "restricted"):
                raise ValueError("data_level must be open, internal or restricted")
            if model.data_level not in manifest.requires.data_levels:
                raise ValueError(
                    f"{model.record_kind} has data_level {model.data_level}, which requires.data_levels doesn't list"
                )
            for field, target in ref_fields(model):
                if target not in REGISTRY and target not in registrar.records:
                    raise ValueError(f"{field} refers to an unknown record kind {target}")
        own_files = set(CORE_KINDS) | set(registrar.file_kinds)
        for action in registrar.actions.values():
            if action.on is not None and action.on not in REGISTRY and action.on not in registrar.records:
                raise ValueError(f"action {action.name} is on an unknown record kind {action.on}")
            if not set(action.file_kinds) <= own_files:
                raise ValueError(f"action {action.name} names a file kind that isn't core or the plugin's own")
        if not set(registrar.stage_defaults) <= set(registrar.records):
            raise ValueError("default stages may target only the plugin's own record types")
        allowed_ops = set(OP_MODELS) | set(registrar.ops)
        if not set(registrar.validators) <= allowed_ops:
            raise ValueError("validators may target only core or own ops")
        for lint in registrar.lints.values():
            if not set(lint.ops) <= allowed_ops:
                raise ValueError(f"lint {lint.name} may check only core or own ops")
        for task in registrar.tasks.values():
            if not set(task.ops) <= allowed_ops:
                raise ValueError("task may use only core or own ops")
            if "file.add" in task.ops:
                raise ValueError("file.add is made only by person actions, never by a task")
            if task.on is not None and task.on not in REGISTRY and task.on not in registrar.records:
                raise ValueError(f"task {task.name} is on an unknown record kind {task.on}")
            if task.output == "draft":
                from engine.texts import long_text_fields

                model = registrar.records.get(task.on) or REGISTRY.get(task.on)
                if task.field not in long_text_fields(model):
                    raise ValueError(f"task {task.name} drafts {task.on}.{task.field}, which isn't a long text field")
            for name in (task.prompt, task.playbook):
                if "/" in name and not name.startswith(registrar.name + "/"):
                    raise ValueError("a task's prompt and guidance are core ones or the plugin's own")
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
                self._with_files(ReadView(view or self.store.read(), owner)),
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

    def lint_findings(self, op: Any, view: Any) -> list[tuple[str, str, Any]]:
        """(lint name, default severity, finding) for every running plugin's lint on this op. A lint that raises or
        returns something else turns its plugin off and finds nothing."""
        from engine.plugin_api import LintFinding

        found = []
        for name, registrar in self.registrars.items():
            if not self.active(name):
                continue
            for lint in registrar.lints.values():
                if op.op not in lint.ops:
                    continue
                try:
                    read = self._with_files(ReadView(view, name))
                    result = lint.fn(op.model_copy(deep=True), read, registrar.config.model_copy(deep=True))
                    if not isinstance(result, list) or any(not isinstance(f, LintFinding) for f in result):
                        raise ValueError("lints return a list of LintFinding")
                    found += [(lint.name, lint.severity, f) for f in result]
                except Exception as err:
                    self.disable(name, f"lint {lint.name} failed: {err}")
                    break
        return found

    def task_kind(self, name: str):
        if "/" in name and not self.active(name.split("/")[0]):
            raise StoreError("task plugin is disabled")
        return self.tasks[name]

    def _with_files(self, view: Any) -> Any:
        from engine.files import read_bytes
        from engine.texts import read_text

        view.read_file = lambda file_id: read_bytes(self.store, file_id)[1]
        view.read_text = lambda sha256: read_text(self.store, sha256)
        view.read_source = lambda digest: _source_text(self.store, digest)
        plugin = getattr(view, "_ReadView__plugin", None)
        view.data_layers = lambda project: self.data_layers(plugin, project)
        view.default_language = self.cfg.workspace.language
        return view

    def data_layers(self, plugin: str | None, project: str | None = None) -> list[Path]:
        """A plugin's data folders, least specific first: what it ships, the workspace's, then the project's."""
        if plugin is None or plugin not in self.manifests:
            return []
        layers = []
        shipped = self.manifests[plugin].provides.data
        if shipped:
            layers.append(self.candidates[plugin].parent / shipped)
        workspace = self.store.path.parent / "plugin-data" / plugin
        layers.append(workspace)
        if project and re.fullmatch(r"[A-Z]+-[0-9]+", project):
            layers.append(workspace / "projects" / project)
        return layers

    def text_formats(self) -> dict[str, Any]:
        """The core's long text formats and those of running plugins."""
        from engine.texts import CORE_FORMATS

        formats = dict(CORE_FORMATS)
        for name, registrar in self.registrars.items():
            if self.active(name):
                formats.update(registrar.text_formats)
        return formats

    def file_kinds(self) -> dict[str, Any]:
        """The core's file kinds and those of running plugins."""
        from engine.files import CORE_KINDS

        kinds = dict(CORE_KINDS)
        for name, registrar in self.registrars.items():
            if self.active(name):
                kinds.update(registrar.file_kinds)
        return kinds

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
                    read = self._with_files(ReadView(view if view is not None else self.store.read(), name))
                    takes = _origin_parameter(fn)
                    if takes == "keyword":
                        result = fn(op.model_copy(deep=True), read, origin=dict(origin))
                    elif takes == "positional":
                        result = fn(op.model_copy(deep=True), read, dict(origin))
                    else:
                        result = fn(op.model_copy(deep=True), read)
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
        writer = OpWriter(
            tx,
            name,
            registration.writes,
            context,
            models=self.records,
            referrers=self._referrers(tx),
            store=self.store,
        )
        self._with_files(writer)
        self._with_files(writer)
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
                            context = self._with_files(EventContext(self.store.read(), name, registrar.config))
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
                allowed_fields = {"request": {"task", "note", "about"}, "question": {"title", "text"}}
                if kind not in allowed_fields or not set(data) <= allowed_fields[kind]:
                    raise StoreError("event handlers may only queue requests or file questions")
                if kind == "request":
                    task = data["task"]
                    if "/" in task and not task.startswith(name + "/"):
                        raise StoreError("requesting another plugin requires an interface")
                    check_about(tx, self.task_kind(task), data.get("about"))
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


def _source_text(store: Any, digest: str) -> str:
    path = store.path.parent / "sources" / f"{digest}.txt"
    return path.read_text(encoding="utf-8") if path.exists() and re.fullmatch(r"[0-9a-f]+", digest) else ""


def check_about(view: Any, kind: Any, about: dict[str, str] | None) -> None:
    """A request for a task kind declared `on` a record kind must name a live record of that kind; others name none."""
    if kind.on is None:
        if about is not None:
            raise StoreError(f"{kind.name} doesn't work on a record")
        return
    if about is None or about.get("kind") != kind.on:
        raise StoreError(f"{kind.name} works on a {kind.on}")
    if view.get(about["kind"], about["id"]) is None:
        raise StoreError(f"there is no {about['kind']} {about['id']}")


def _origin_parameter(fn: Any) -> str | None:
    """How a validator takes the origin: as a third positional argument, as a keyword `origin`, or not at all
    (validators written for plugin API 0.1 take only the op and the view)."""
    import inspect

    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return None
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if len(positional) >= 3 or any(p.kind == p.VAR_POSITIONAL for p in params):
        return "positional"
    if any(p.name == "origin" and p.kind == p.KEYWORD_ONLY for p in params) or any(
        p.kind == p.VAR_KEYWORD for p in params
    ):
        return "keyword"
    return None
