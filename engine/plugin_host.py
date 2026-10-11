"""Workspace-local registries, discovery, guarded callbacks and committed events."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import re
import sys
import threading
import uuid
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
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
            "authorship": "Words by kind of author: {person, assistant, assistant_edit}, all three always present.",
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
        self.failures: dict[tuple[str, str], int] = {}  # (plugin, where) -> failures in a row
        self._items: dict[str, tuple[str, str, Any]] = {}  # interface item key -> (provider, interface, raw item)
        self._modules: list[str] = []
        self._queue: deque = deque()
        self._dispatching = False
        self._chain: frozenset = frozenset()
        self._follows: str | None = None  # the change whose event is being delivered
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
        self._check_interfaces()
        self._offer_to_notes()
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

    def _offer_to_notes(self) -> None:
        """Add running plugins' ops registered with notes=True to what reading notes may use."""
        from dataclasses import replace as _replace

        offered = sorted(
            name
            for plugin, registrar in self.registrars.items()
            if self.active(plugin)
            for name, op in registrar.ops.items()
            if op.notes
        )
        if offered and "notes" in self.tasks:
            notes = self.tasks["notes"]
            self.tasks["notes"] = _replace(notes, ops=tuple(dict.fromkeys([*notes.ops, *offered])))

    # ---- interfaces (design 3.9) ----------------------------------------------------------------------------------

    def definition(self, name: str) -> Any | None:
        """A running plugin's definition of an interface, by name."""
        for plugin, registrar in self.registrars.items():
            if self.active(plugin) and name in registrar.interface_definitions:
                return registrar.interface_definitions[name]
        return None

    def providers(self, name: str) -> list[str]:
        """Running plugins that provide an interface in the major version its running definition has."""
        definition = self.definition(name)
        if definition is None:
            return []
        return sorted(
            plugin
            for plugin, registrar in self.registrars.items()
            if self.active(plugin)
            and name in registrar.interface_provisions
            and registrar.interface_provisions[name].major == definition.major
        )

    def _check_interfaces(self) -> None:
        """Turn off plugins whose required interfaces nobody running provides, until nothing changes; note on the
        others what they use or provide that isn't there."""
        from engine.plugin_manifest import INTERFACE_USE

        changed = True
        while changed:
            changed = False
            for plugin, manifest in self.manifests.items():
                if not self.active(plugin):
                    continue
                for use in manifest.interfaces.uses:
                    name, major, minor = re.fullmatch(INTERFACE_USE, use.interface).groups()
                    definition = self.definition(name)
                    fits = (
                        definition is not None
                        and definition.major == int(major)
                        and definition.minor >= int(minor or 0)
                        and bool(self.providers(name))
                    )
                    if not fits and not use.optional:
                        self.disable(plugin, f"it needs {use.interface}, which no running plugin provides")
                        changed = True
                        break
        for plugin, registrar in self.registrars.items():
            if not self.active(plugin):
                continue
            for name, provision in registrar.interface_provisions.items():
                definition = self.definition(name)
                if definition is not None and definition.major != provision.major:
                    self.status[plugin].notes.append(
                        f"it provides {name}@{provision.major}, but the running definition is version "
                        f"{definition.version}, so nothing reads it"
                    )

    def _uses(self, plugin: str, name: str) -> bool:
        manifest = self.manifests.get(plugin)
        return manifest is not None and any(u.interface.split("@")[0] == name for u in manifest.interfaces.uses)

    def read_interface(self, plugin: str | None, spec: str, project: Any = None) -> list[Any]:
        from engine.plugin_api import ANY, InterfaceItem, PluginMisuse, ReadView
        from engine.plugin_manifest import INTERFACE_USE

        match = re.fullmatch(INTERFACE_USE, spec)
        if match is None or plugin is None or not self._uses(plugin, match.group(1)):
            raise PluginMisuse(f"read an interface this plugin declares in interfaces.uses, as <name>@<major>: {spec}")
        name, major, minor = match.group(1), int(match.group(2)), int(match.group(3) or 0)
        definition = self.definition(name)
        if definition is None or definition.major != major or definition.minor < minor:
            return []
        allowed = {"open", "internal", *self.manifests[plugin].requires.data_levels}
        found = []
        for provider in self.providers(name):
            registrar = self.registrars[provider]
            reader = self._with_files(ReadView(self.store.read(), provider))
            fn = registrar.interface_provisions[name].items
            wanted = project if project is not ANY else None
            where = f"its {name} items"
            try:
                if _positional_count(fn) >= 3:
                    items = list(fn(reader, registrar.config.model_copy(deep=True), wanted))
                else:
                    items = list(fn(reader, registrar.config.model_copy(deep=True)))
            except Exception as err:
                self.failed(provider, where, err)
                continue
            self.succeeded(provider, where)
            checked, declared = [], set(definition.item.model_fields)
            for item in items:
                try:
                    checked.append((item, definition.item.model_validate(item).model_dump(mode="json")))
                except Exception as err:
                    self._note(provider, f"{where}: one was left out because it doesn't match the definition: {err}")
                    continue
                unknown = sorted(set(item) - declared) if isinstance(item, dict) else []
                if unknown:
                    self._note(
                        provider,
                        f"{where} have fields {name}@{definition.version} doesn't declare, which no reader sees: "
                        + ", ".join(unknown),
                    )
            for raw, item in checked:
                if project is not ANY and project is not None and item.get("project") != project:
                    continue
                if item.get("data_level", "internal") not in allowed:
                    continue
                found.append(InterfaceItem(provider, item, self._keep_item(provider, name, raw)))
        return found

    def _keep_item(self, provider: str, name: str, raw: Any) -> str:
        """A stable key for an item as its provider gave it, remembered so a request can name the item."""
        text = json.dumps([provider, name, raw], sort_keys=True, default=str)
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
        if len(self._items) > 5000:
            self._items.clear()
        self._items[key] = (provider, name, raw)
        return key

    def _item_about(self, plugin: str, name: str, key: str) -> dict[str, str]:
        """The provider's record an item stands for, by the item's key; the provider's items are read again when the
        key isn't remembered (after a restart)."""
        from engine.plugin_api import ANY, ReadView, Stored

        if key not in self._items:
            self.read_interface(plugin, self._use_spec(plugin, name), ANY)
        if key not in self._items:
            raise StoreError("that item isn't offered any more")
        provider, _, raw = self._items[key]
        provision = self.registrars[provider].interface_provisions[name]
        if provision.about is None:
            raise StoreError(f"{provider} doesn't say which of its records an item of {name} stands for")
        reader = self._with_files(ReadView(self.store.read(), provider))
        try:
            found = provision.about(reader, self.registrars[provider].config.model_copy(deep=True), deepcopy(raw))
        except Exception as err:
            self.failed(provider, f"its {name} about", err)
            raise StoreError(f"{provider} couldn't say which record that item stands for") from None
        if isinstance(found, Stored):
            found = (found.kind, found.id)
        if not (isinstance(found, tuple) and len(found) == 2 and all(isinstance(x, str) for x in found)):
            raise StoreError(f"{provider} doesn't have a record for that item")
        return {"kind": found[0], "id": found[1]}

    def _use_spec(self, plugin: str, name: str) -> str:
        return next(u.interface for u in self.manifests[plugin].interfaces.uses if u.interface.split("@")[0] == name)

    def _check_emit(self, plugin: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        from engine.plugin_api import PluginMisuse

        name, _, short = event.rpartition(".")
        registrar = self.registrars[plugin]
        if name not in registrar.interface_provisions:
            raise PluginMisuse(f"{event} isn't an event of an interface this plugin provides")
        definition = self.definition(name)
        if definition is None:
            return dict(payload)  # nobody defines it here, so nobody can be listening
        if short not in definition.events:
            raise PluginMisuse(f"{name} has no event {short}")
        try:
            return definition.events[short].model_validate(payload).model_dump(mode="json")
        except ValueError as err:
            raise PluginMisuse(f"{event} payload doesn't match the definition: {err}") from None

    def _interface_request(self, plugin: str, data: dict[str, Any]) -> dict[str, Any]:
        """The request for another plugin's task kind that an interface offers, as that plugin's own task."""
        from engine.plugin_manifest import INTERFACE_USE

        match = re.fullmatch(INTERFACE_USE, data["via"])
        if match is None or not self._uses(plugin, match.group(1)):
            raise StoreError(f"{plugin} doesn't use {data['via']}")
        name = match.group(1)
        offering = [
            p
            for p in self.providers(name)
            if data["interface_task"] in self.registrars[p].interface_provisions[name].task_kinds
        ]
        if data.get("provider"):
            offering = [p for p in offering if p == data["provider"]]
        if len(offering) != 1:
            raise StoreError(
                f"{'no' if not offering else 'more than one'} running plugin offers {data['interface_task']} "
                f"through {name}" + ("; name the provider" if offering else "")
            )
        task = self.registrars[offering[0]].interface_provisions[name].task_kinds[data["interface_task"]]
        about = data.get("about")
        if data.get("item"):
            about = self._item_about(plugin, name, data["item"])
            if self._items[data["item"]][0] != offering[0]:
                raise StoreError("the item comes from another provider than the one offering that work")
        return {"task": task, "note": data["note"], **({"about": about} if about else {})}

    # ---- Today lines, panels and jobs -----------------------------------------------------------------------------

    def today(self) -> list[tuple[str, Any]]:
        """(plugin, TodayLine) from every running plugin's Today contributors, each checked."""
        from engine.plugin_api import ReadView, TodayLine

        found = []
        for plugin, registrar in sorted(self.registrars.items()):
            if not self.active(plugin):
                continue
            for name, contributor in sorted(registrar.today_lines.items()):
                reader = self._with_files(ReadView(self.store.read(), plugin))
                try:
                    lines = contributor.lines(reader, registrar.config.model_copy(deep=True))
                    for line in lines:
                        if not isinstance(line, TodayLine):
                            raise ValueError("lines must be TodayLine objects")
                        if not line.text.strip() or "\n" in line.text or len(line.text) > 300:
                            raise ValueError("a Today line is one line of up to 300 characters")
                        if line.action is not None and line.action not in registrar.actions | registrar.tasks:
                            raise ValueError(f"{line.action} isn't one of this plugin's actions or task kinds")
                        if line.about is not None and "/" in line.about[0] and not line.about[0].startswith(plugin):
                            raise ValueError("a Today line is about a core record or one of the plugin's own")
                except Exception as err:
                    self.failed(plugin, f"Today lines {name}", err)
                    continue
                self.succeeded(plugin, f"Today lines {name}")
                found += [(plugin, line) for line in lines]
        return found

    def connectors(self) -> dict[str, Any]:
        """Every running plugin's connectors, by name."""
        return {
            name: connector
            for plugin, registrar in sorted(self.registrars.items())
            if self.active(plugin)
            for name, connector in registrar.connectors.items()
        }

    def triage_matchers(self) -> dict[str, Any]:
        """Every running plugin's triage matchers, by name."""
        return {
            name: match
            for plugin, registrar in sorted(self.registrars.items())
            if self.active(plugin)
            for name, match in registrar.triage_matchers.items()
        }

    def run_matcher(self, name: str, match: Any, change: dict[str, Any], params: dict[str, Any]) -> str | None:
        """A plugin's matcher on one change; a failure counts as no match and is contained."""
        plugin = name.split("/", 1)[0]
        where = f"triage matcher {name}"
        try:
            reason = match(deepcopy(change), deepcopy(params))
            if reason is not None and (not isinstance(reason, str) or not reason.strip() or len(reason) > 300):
                raise ValueError("a matcher returns None or one line of up to 300 characters")
        except Exception as err:
            self.failed(plugin, where, err)
            return None
        self.succeeded(plugin, where)
        return " ".join(reason.split()) if reason else None

    def poll_connector(self, connector: Any, settings: Any, state: dict[str, Any], context: Any) -> Any:
        """Read a plugin's connector: its ConnectorError passes through; anything else is contained like a job."""
        from engine.connectors import ConnectorError, Poll

        plugin = connector.name.split("/", 1)[0]
        where = f"connector {connector.name}"
        try:
            poll = connector.poll(settings, deepcopy(state), context)
            if not isinstance(poll, Poll):
                raise ValueError("poll must return a Poll")
        except ConnectorError:
            raise
        except Exception as err:
            self.failed(plugin, where, err)
            raise ConnectorError("outage", f"the add-on {plugin} failed reading it: {err}") from None
        self.succeeded(plugin, where)
        return poll

    def setup_steps(self) -> list[tuple[str, Any]]:
        """(plugin, step) for every running plugin's setup steps."""
        found = []
        for plugin, registrar in sorted(self.registrars.items()):
            if self.active(plugin):
                for name in sorted(registrar.setup_steps):
                    step = registrar.setup_steps[name]
                    if step.action is not None and step.action not in registrar.actions:
                        self.failed(plugin, f"setup step {name}", f"{step.action} isn't one of its person actions")
                        continue
                    found.append((plugin, step))
        return found

    def setup_step_done(self, plugin: str, step: Any) -> bool:
        """Whether a plugin's setup step is done; a failing check counts as not done and is contained."""
        from engine.plugin_api import ReadView

        registrar = self.registrars[plugin]
        reader = self._with_files(ReadView(self.store.read(), plugin))
        try:
            done = bool(step.done(reader, registrar.config.model_copy(deep=True)))
        except Exception as err:
            self.failed(plugin, f"setup step {step.name}", err)
            return False
        self.succeeded(plugin, f"setup step {step.name}")
        return done

    def panel(self, name: str) -> Any | None:
        plugin = name.split("/", 1)[0]
        registrar = self.registrars.get(plugin)
        return registrar.panels.get(name) if registrar and self.active(plugin) else None

    def panel_rows(self, name: str, project: str | None = None) -> list[dict[str, Any]]:
        """The rows of a running plugin's panel: records of its kind matching its filter, with its columns."""
        panel = self.panel(name)
        if panel is None:
            raise StoreError(f"there is no panel {name} running now")
        view = self.store.read()
        equals = dict(panel.filter) | ({"project": project} if project else {})
        records = view.find(panel.kind, equals) if equals else view.list(panel.kind)
        return [{"id": r.id, "values": {c: r.data.get(c) for c in panel.columns}} for r in records]

    def job_settings(self, name: str) -> tuple[bool, int]:
        """Whether a job runs and how often, from the workspace's settings and the plugin's default."""
        plugin = name.split("/", 1)[0]
        job = self.registrars[plugin].jobs[name]
        settings = self.cfg.workspace.plugins.jobs.get(name)
        enabled = settings.enabled if settings is not None else True
        every = settings.every_minutes if settings is not None and settings.every_minutes else job.every_minutes
        return enabled, every

    def last_job_run(self, name: str) -> Any | None:
        plugin, _, _ = name.partition("/")
        runs = self.store.read().find("job_run", {"plugin": plugin, "job": name})
        return runs[-1] if runs else None

    def due_jobs(self, now: datetime) -> list[str]:
        """Jobs of running plugins that are on and whose time has come."""
        due = []
        for plugin, registrar in sorted(self.registrars.items()):
            if not self.active(plugin):
                continue
            for name in sorted(registrar.jobs):
                enabled, every = self.job_settings(name)
                last = self.last_job_run(name)
                started = datetime.fromisoformat(str(last.data["started_at"])) if last else None
                if enabled and (started is None or now - started >= timedelta(minutes=every)):
                    due.append(name)
        return due

    def run_job(self, name: str, now: datetime | None = None) -> str:
        """Run one job now and record it. Returns the outcome."""
        import time

        plugin = name.split("/", 1)[0]
        registrar = self.registrars[plugin]
        started, clock = now or datetime.now(UTC), time.monotonic()
        context = self._with_files(EventContext(self.store.read(), plugin, registrar.config))
        outcome, error = "ok", None
        try:
            registrar.jobs[name].run(context)
            self._commands(plugin, context.commands, f"job:{name}", {})
        except PluginMisuse as err:
            outcome, error = "failed", str(err)
            self.disable(plugin, f"job {name} broke the plugin contract: {error}")
        except Exception as err:
            outcome, error = "failed", str(err) or type(err).__name__
            self.failed(plugin, f"job {name}", error)
        else:
            self.succeeded(plugin, f"job {name}")
        with self.store.transaction() as tx:
            tx.create(
                "job_run",
                {
                    "plugin": plugin,
                    "job": name,
                    "started_at": started.isoformat(),
                    "seconds": round(time.monotonic() - clock, 3),
                    "outcome": outcome,
                    "error": error,
                },
                WriteContext(actor="engine", trust="trusted", op="job.run"),
            )
        return outcome

    def failed(self, plugin: str, where: str, err: object) -> None:
        """A contained failure of one call (Today lines, interface items, an event handler, a job): noted on the plugin
        where the person sees it, and the plugin is turned off once the same place has failed the configured number of
        times in a row."""
        key = (plugin, where)
        count = self.failures.get(key, 0) + 1
        self.failures[key] = count
        limit = self.cfg.workspace.plugins.failures_before_off
        message = f"{where} failed: {err}" if str(err) else f"{where} failed: {type(err).__name__}"
        if count >= limit:
            self.disable(plugin, message + (f" ({count} times in a row)" if count > 1 else ""))
            return
        log.warning("Plugin %s: %s (%d of %d before it is turned off)", plugin, message, count, limit)
        status = self.status.get(plugin)
        if status is not None:
            status.notes = [n for n in status.notes if not n.startswith(where + " failed")]
            status.notes.append(f"{message} (it was skipped; {limit - count} more in a row turns the plugin off)")

    def _note(self, plugin: str, note: str) -> None:
        """Something the person should know about a running plugin, noted once."""
        status = self.status.get(plugin)
        if status is not None and note not in status.notes:
            status.notes.append(note)
            log.warning("Plugin %s: %s", plugin, note)

    def succeeded(self, plugin: str, where: str) -> None:
        """A call that worked after failures: the count starts again and its note goes."""
        if self.failures.pop((plugin, where), None) is not None and plugin in self.status:
            status = self.status[plugin]
            status.notes = [n for n in status.notes if not n.startswith(where + " failed")]

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
            used = {u.interface.split("@")[0] for u in manifest.interfaces.uses}
            for event in manifest.events():
                if event not in EVENTS and event.rpartition(".")[0] not in used:
                    raise ValueError(f"unsupported event subscription {event}; an interface's events need it in uses")
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

    @staticmethod
    def settings_schema(manifest_path: Path) -> type[Settings]:
        """A plugin's settings schema, loaded without starting the plugin (for checking settings before writing)."""
        manifest = read_manifest(manifest_path)
        root = manifest_path.parent
        top = manifest.entry.split(":")[0].split(".")[0]
        loader = PluginHost.__new__(PluginHost)
        loader._modules = []
        try:
            schema = loader._importer(root, top)(manifest.config_schema)
        finally:
            for name in [m for m in sys.modules if any(m == n or m.startswith(n + ".") for n in loader._modules)]:
                sys.modules.pop(name, None)
        if not isinstance(schema, type) or not issubclass(schema, Settings):
            raise ValueError("config schema must derive from plugin_api.Settings")
        return schema

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
            ("working_copies", registrar.working_copies),
            ("derived_files", registrar.derived_files),
            ("panels", registrar.panels),
            ("today", registrar.today_lines),
            ("jobs", registrar.jobs),
            ("setup_steps", registrar.setup_steps),
            ("connectors", registrar.connectors),
            ("triage_matchers", registrar.triage_matchers),
        ):
            declared = set(getattr(expected, key))
            if f"{registrar.name}/*" in declared:
                # Identifiers the plugin's own settings define: any of its namespace, and only those.
                if not all(n.startswith(registrar.name + "/") for n in actual):
                    raise ValueError(f"registered {key} must be in the plugin's own namespace")
                continue
            if declared != set(actual):
                raise ValueError(f"registered {key} does not match provides exactly")
        if set(manifest.interfaces.defines) != set(registrar.interface_definitions):
            raise ValueError("registered interface definitions do not match interfaces.defines exactly")
        provided = {f"{p.interface}@{p.major}" for p in registrar.interface_provisions.values()}
        if set(manifest.interfaces.provides) != provided:
            raise ValueError("registered interface providers do not match interfaces.provides exactly")
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
            if task.where:
                fields = (registrar.records.get(task.on) or REGISTRY[task.on]).model_fields
                unknown = sorted(set(task.where) - set(fields))
                if unknown:
                    raise ValueError(f"task {task.name} narrows {task.on} by {unknown[0]}, which it doesn't have")
            if task.output == "draft":
                from engine.texts import long_text_fields

                model = registrar.records.get(task.on) or REGISTRY.get(task.on)
                if task.field not in long_text_fields(model):
                    raise ValueError(f"task {task.name} drafts {task.on}.{task.field}, which isn't a long text field")
            for name in (task.prompt, task.playbook):
                if "/" in name and not name.startswith(registrar.name + "/"):
                    raise ValueError("a task's prompt and guidance are core ones or the plugin's own")
        for action in registrar.actions.values():
            if action.where:
                model = registrar.records.get(action.on) or REGISTRY.get(action.on)
                unknown = sorted(set(action.where) - set(model.model_fields)) if model is not None else []
                if model is None or unknown:
                    raise ValueError(f"action {action.name} narrows {action.on} by a field it doesn't have")
        for panel in registrar.panels.values():
            model = registrar.records.get(panel.kind) or REGISTRY.get(panel.kind)
            if model is None:
                raise ValueError(f"panel {panel.name} lists {panel.kind}, which is neither core nor the plugin's own")
            for field_name in (*panel.columns, *panel.filter):
                if field_name not in model.model_fields:
                    raise ValueError(f"panel {panel.name}: {panel.kind} has no field {field_name}")
            for action in (*([panel.primary_action] if panel.primary_action else []), *panel.row_actions):
                target = registrar.actions.get(action) or registrar.tasks.get(action)
                if target is None or getattr(target, "on", None) != panel.kind:
                    raise ValueError(f"panel {panel.name}: {action} isn't this plugin's action or task on {panel.kind}")
            if panel.new_action is not None:
                action = registrar.actions.get(panel.new_action)
                if action is None or action.on is not None:
                    raise ValueError(
                        f"panel {panel.name}: {panel.new_action} isn't this plugin's action on the workspace"
                    )
        for derived in registrar.derived_files.values():
            unknown = [k for k in derived.depends_on if k not in REGISTRY and k not in registrar.records]
            if unknown:
                raise ValueError(f"generated file {derived.name} depends on an unknown record kind {unknown[0]}")
        for model in registrar.records.values():
            if getattr(model, "layout", None) is not None:
                from engine.sync import check_layout

                check_layout(model.layout, model, {**REGISTRY, **registrar.records})
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
        view.read_interface = lambda spec, project=None: self.read_interface(plugin, spec, project)
        view.user = self.cfg.workspace.user.person
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
        origin = {"task": None, "about": None, **(origin or {"actor": "pm", "trust": "trusted", "via": "screen"})}
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
        writer.check_emit = lambda event, payload: self._check_emit(name, event, payload)
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
        tx.emitted.extend(writer.emitted)
        return writer.touched

    def publish(self, event: str, data: dict[str, Any], *, follows: str | None = None) -> None:
        """Deliver an event to subscribed plugins. `follows` is the change that raised it; work a handler stages or
        queues is linked to it, and so are events that work raises in turn."""
        with self._lock:
            self._queue.append((event, deepcopy(data), self._chain, follows or self._follows))
            if self._dispatching:
                return
            self._dispatching = True
            try:
                while self._queue:
                    event, payload, chain, self._follows = self._queue.popleft()
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
                        except PluginMisuse as err:
                            self.disable(name, f"event {event} broke the plugin contract: {err}")
                        except Exception as err:
                            self.failed(name, f"event {event}", err)
                        else:
                            self.succeeded(name, f"event {event}")
            finally:
                self._chain = frozenset()
                self._follows = None
                self._dispatching = False

    def _commands(self, name: str, commands: list, event: str = "", payload: dict | None = None) -> None:
        emits = [data for kind, data in commands if kind == "emit"]
        ops = [data for kind, data in commands if kind == "op"]
        commands = [(kind, data) for kind, data in commands if kind not in ("emit", "op")]
        checked = [(e["event"], self._check_emit(name, e["event"], e["payload"])) for e in emits]
        if commands:
            self._write_commands(name, commands, event, payload)
        if ops:
            self._apply_own_ops(name, ops, event)
        for raised, data in checked:
            self.publish(raised, data)

    def _apply_own_ops(self, plugin: str, ops: list[dict[str, Any]], event: str) -> str:
        """Apply ops a handler or job staged, as a changeset from the plugin: only its own ops, treated like work
        from outside content (system ops and person-only values wait for the person)."""
        from engine.applier import Context, Inputs, apply_changeset
        from engine.names import People
        from engine.ops import CHANGESET

        own = tuple(sorted(self.registrars[plugin].ops))
        for op in ops:
            if op.get("op") not in own:
                raise PluginMisuse(f"{op.get('op')} isn't one of {plugin}'s own ops")
        summary = f"{plugin}: {event}" if event else plugin
        changeset = CHANGESET.validate_python({"summary": summary, "ops": ops}, context={"op_models": self.ops})
        with self.store.transaction() as tx:
            request = tx.create(
                "request",
                {
                    "task": "notes",
                    "origin": "schedule",
                    "state": "done",
                    "note": summary,
                    "created_at": datetime.now(UTC).isoformat(),
                    **({"follows": self._follows} if self._follows else {}),
                },
                WriteContext(actor="plugin", trust="untrusted", op=f"{plugin}/stage"),
            )
        ctx = Context(
            self.store, self.cfg, People(self.store, self.cfg), own, Inputs(request.id, None, "", "", "untrusted")
        )
        return apply_changeset(changeset, [], ctx, run=None)

    def _write_commands(self, name: str, commands: list, event: str = "", payload: dict | None = None) -> None:
        context = WriteContext(actor="plugin", trust="untrusted", op=f"{name}/event")
        with self.store.transaction() as tx:
            for kind, data in commands:
                allowed_fields = {
                    "request": {"task", "note", "about", "via", "interface_task", "provider", "needs_go", "item"},
                    "question": {"title", "text"},
                }
                if kind not in allowed_fields or not set(data) <= allowed_fields[kind]:
                    raise PluginMisuse("event handlers may only queue requests or file questions")
                via = kind == "request" and "via" in data
                needs_go = bool(data.pop("needs_go", False)) if kind == "request" else False
                if via:
                    data = self._interface_request(name, data)
                elif kind == "request" and "task" not in data:
                    raise StoreError("a request names a task kind")
                if kind == "request":
                    task = data["task"]
                    if "/" in task and not task.startswith(name + "/") and not via:
                        raise StoreError("requesting another plugin requires an interface")
                    check_about(tx, self.task_kind(task), data.get("about"))
                    data = {**data, "origin": "schedule", "created_at": datetime.now(UTC).isoformat()}
                    if self._follows:
                        data["follows"] = self._follows
                    if needs_go:
                        from engine.stages import wording

                        data |= {"state": "needs_you", "approval": "required", "waiting": wording(self.cfg, "waiting")}
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
    """A request for a task kind declared `on` a record kind must name a live record of that kind that its `where`
    matches; others name none."""
    if kind.on is None:
        if about is not None:
            raise StoreError(f"{kind.name} doesn't work on a record")
        return
    if about is None or about.get("kind") != kind.on:
        raise StoreError(f"{kind.name} works on a {kind.on}")
    record = view.get(about["kind"], about["id"])
    if record is None:
        raise StoreError(f"there is no {about['kind']} {about['id']}")
    if not kind.offered_on(record):
        raise StoreError(f"{kind.label or kind.name} isn't for this {kind.on}")


def _positional_count(fn: Any) -> int:
    """How many positional arguments a plugin callback takes (several are optional, for callbacks written earlier)."""
    import inspect

    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return 0
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return 99
    return len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])


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
