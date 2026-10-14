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
from pydantic import ValidationError

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
from engine.plugin_manifest import MANIFEST_PARTS, NOT_YET, Manifest, installed_manifest, plain_error, read_manifest
from engine.records import REFERENCES, REGISTRY, ref_fields, values_at
from engine.rules import rule_names
from engine.storage import StoreError, WriteContext
from engine.tasks import TASKS
from engine.yaml_load import load_yaml

BUNDLED = Path(__file__).resolve().parents[1] / "plugins"
#: The longest text a plugin's wording entry may have.
WORDING_MAX = 200
#: The wording keys the screens read for a plugin's own things, with what each names. A plugin's wording file may set
#: only these, for identifiers in its own namespace; connectors, sign-ins, actions, panels and triage rule kinds take
#: their names from their registration's `label` instead.
WORDING_KEYS = {
    "task.{task kind}": "What a kind of AI work is called (set from the task kind's label unless the file sets it).",
    "stages.group.{record kind}": "The heading for a kind of record on the Stages screen.",
    "op.{op}": "What an op is called in What changed and on reviews.",
    "setup_step.{setup step}": "A setup step's title in the setup guide (instead of its label).",
    "setup_step.{setup step}.explanation": "A setup step's explanation in the setup guide.",
    "welcome.skip.{setup step}": "The words on a setup step's Skip button.",
}


def _wording_key_known(key: str) -> bool:
    import re

    for pattern in WORDING_KEYS:
        regex = "^" + re.sub(r"\\{[^}]+\\}", r"\\S+", re.escape(pattern)) + "$"
        if re.match(regex, key):
            return True
    return False


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
            "request": "The request whose run drafted the version, or None (the person's own edit, an import).",
            "part": "The part of the text that request named (as given to queue_request(part=)), or None.",
        },
    ),
    "request.queued": ("AI work was queued.", {"id": "The request's id."}),
    "question.answered": ("A question was answered.", {"id": "The question's id."}),
    "changeset.applied": ("A changeset was applied (some of its ops may be held or refused).", {"id": "Its id."}),
    "changeset.reviewed": (
        "The person accepted the assistant's answer to a request, or sent it back with a note (which undoes it and "
        "queues the work again). A draft the person accepts raises text.accepted instead.",
        {
            "id": "The changeset's id.",
            "outcome": "accepted or sent_back.",
            "request": "The request it answered.",
            "task": "That request's kind of work.",
            "part": "The part of a text that request named (as given to queue_request(part=)), or None.",
            "about": "The record the request was about, as {kind, id}, or None.",
        },
    ),
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
        self._in_stage_check = False
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
                set(self.stage_checks) | {r.id for r in cfg.rules.rules} | rule_names(self.store),
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
                    if existing.resolve() == path.resolve():
                        continue  # the workspace links to the installed copy itself (a development install)
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

    def note_candidates(self, allowed: tuple[str, ...], project: str | None = None) -> str:
        """The records offered ops may name, for the notes packet: one block per op that lists them. A candidates
        function taking a third argument gets the project the note was handed in for (or None)."""
        from engine.plugin_api import ReadView

        blocks = []
        for plugin, registrar in sorted(self.registrars.items()):
            if not self.active(plugin):
                continue
            for name, op in sorted(registrar.ops.items()):
                if name not in allowed or op.candidates is None:
                    continue
                reader = self._with_files(ReadView(self.store.read(), plugin))
                where = f"candidates for {name}"
                try:
                    args = [reader, registrar.config.model_copy(deep=True)]
                    if _positional_count(op.candidates) >= 3:
                        args.append(project)
                    found = list(op.candidates(*args))[:50]
                    lines = [f"- {str(i)}: {' '.join(str(n).split())[:120]}" for i, n in found]
                except Exception as err:
                    self.failed(plugin, where, err)
                    continue
                self.succeeded(plugin, where)
                if lines:
                    blocks.append(f"Records {name} may name, by id:\n" + "\n".join(lines))
        return "\n\n".join(blocks)

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
            raise PluginMisuse(f"read an interface this plugin says it uses, as <name>@<major>: {spec}")
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
            per_project = _positional_count(fn) >= 3
            try:
                if per_project:
                    items = list(fn(reader, registrar.config.model_copy(deep=True), wanted))
                else:
                    items = list(fn(reader, registrar.config.model_copy(deep=True)))
            except Exception as err:
                if not per_project or wanted is not None:
                    self.failed(provider, where, err)
                    continue
                # Reading everything failed: ask project by project, so one project's failure leaves out only its
                # items.
                items = []
                failures = []
                for each in self.store.read().list("project"):
                    try:
                        items += list(fn(reader, registrar.config.model_copy(deep=True), each.id))
                    except Exception as inner:
                        failures.append(f"{each.id}: {inner}")
                self.failed(provider, where, f"{err}; left out the items of {', '.join(failures) or 'no project'}")
                if not items:
                    continue
            else:
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

    def interface_about(self, plugin: str | None, item: Any, task: str) -> tuple[str, str] | None:
        """For a using plugin: the record a request for `task` about an item would work on, or None."""
        if plugin is None or not getattr(item, "key", ""):
            return None
        for candidate in self._used(plugin):
            if self.definition(candidate) is None:
                continue
            data = {"via": self._use_spec(plugin, candidate), "interface_task": task, "note": "", "item": item.key}
            try:
                resolved = self._interface_request(plugin, data)
                check_about(self.store.read(), self.task_kind(resolved["task"]), resolved.get("about"), self.store)
            except (StoreError, KeyError):
                continue
            about = resolved.get("about")
            return (about["kind"], about["id"]) if about else None
        return None

    def _used(self, plugin: str) -> list[str]:
        return [u.interface.split("@")[0] for u in self.manifests[plugin].interfaces.uses]

    def _item_about(self, plugin: str, name: str, key: str, task: str = "") -> dict[str, str]:
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
            args = [reader, self.registrars[provider].config.model_copy(deep=True), deepcopy(raw)]
            if _positional_count(provision.about) >= 4:
                args.append(task)
            found = provision.about(*args)
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
            about = self._item_about(plugin, name, data["item"], data["interface_task"])
            if self._items[data["item"]][0] != offering[0]:
                raise StoreError("the item comes from another provider than the one offering that work")
        return {"task": task, "note": data["note"], **({"about": about} if about else {})}

    # ---- Today lines, panels and jobs -----------------------------------------------------------------------------

    def today(self) -> list[tuple[str, Any]]:
        """(plugin, TodayLine) from every running plugin's Today contributors, each checked."""
        from engine.plugin_api import CORE_LINE_ACTIONS, ReadView, TodayLine

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
                        if line.action in CORE_LINE_ACTIONS:
                            needs = CORE_LINE_ACTIONS[line.action]
                            if line.about is None or (needs is not None and line.about[0] != needs):
                                raise ValueError(f"the core's {line.action} needs about=({needs or 'kind'!r}, id)")
                            if line.action == "move-stage" and not (
                                self.stages.types.get(line.about[0]) and self.stages.types[line.about[0]].stages
                            ):
                                raise ValueError(f"{line.about[0]} has no stages to move")
                        elif line.action is not None and line.action not in registrar.actions | registrar.tasks:
                            raise ValueError(
                                f"{line.action} isn't one of this plugin's actions or task kinds, or a core action"
                            )
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

    def sign_ins(self) -> dict[str, Any]:
        """Every running plugin's sign-ins, by name."""
        return {
            name: sign_in
            for plugin, registrar in sorted(self.registrars.items())
            if self.active(plugin)
            for name, sign_in in registrar.sign_ins.items()
        }

    def plugin_secret(self, plugin: str, name: str, workspace_root: Any) -> str | None:
        """A secret a plugin declares: the workspace's reference to it, else the copy kept on this computer."""
        from engine.secrets import SecretError, resolve_secret

        ref = self.cfg.workspace.plugins.secrets.get(plugin, {}).get(name)
        if ref:
            try:
                return resolve_secret(ref)
            except SecretError:
                return None
        kept = Path(workspace_root) / ".cockpit" / "keys" / plugin / name
        return kept.read_text(encoding="utf-8").strip() if kept.is_file() else None

    def sign_in_app(self, sign_in: Any, workspace_root: Any) -> tuple[str | None, str | None, str]:
        """The app registration a sign-in uses, as (client id, client secret, source): the workspace's references
        when it sets the client id, else values the person pasted on this computer, else the add-on's own. The id
        and the secret always come from the same place."""
        from engine.secrets import SecretError, resolve_secret

        plugin = sign_in.plugin
        refs = self.cfg.workspace.plugins.secrets.get(plugin, {})
        if refs.get(sign_in.client_id):
            try:
                client_id = resolve_secret(refs[sign_in.client_id])
                ref = refs.get(sign_in.client_secret) if sign_in.client_secret else None
                return client_id, resolve_secret(ref) if ref else None, "workspace"
            except SecretError:
                return None, None, "workspace"
        keys = Path(workspace_root) / ".cockpit" / "keys" / plugin
        pasted = keys / sign_in.client_id
        if pasted.is_file():
            secret = keys / sign_in.client_secret if sign_in.client_secret else None
            return (
                pasted.read_text(encoding="utf-8").strip(),
                secret.read_text(encoding="utf-8").strip() if secret is not None and secret.is_file() else None,
                "pasted",
            )
        if sign_in.default_client_id and self.default_app_fits(sign_in):
            return sign_in.default_client_id, sign_in.default_client_secret, "add-on"
        return None, None, "none"

    def default_app_fits(self, sign_in: Any) -> bool:
        """Whether the add-on's own registration allows this app's callback address."""
        from engine.sign_in import address_allowed, redirect_uri

        return address_allowed(redirect_uri(self.cfg.server), sign_in.default_redirects)

    def sign_in_token(self, name: str, workspace_root: Any) -> str:
        """A current access token for a sign-in, renewed when needed; ConnectorError("auth") when the person needs
        to sign in."""
        from engine.connectors import ConnectorError
        from engine.net import WebClient
        from engine.sign_in import SignInError, access_token

        sign_in = self.sign_ins().get(name)
        if sign_in is None:
            raise ConnectorError("auth", f"{name} isn't a sign-in of a running add-on")
        plugin = sign_in.plugin
        client_id, client_secret, _ = self.sign_in_app(sign_in, workspace_root)
        keys = Path(workspace_root) / ".cockpit" / "keys" / plugin
        web = WebClient(list(self.manifests[plugin].requires.network))
        try:
            return access_token(keys, sign_in, web, client_id, client_secret)
        except SignInError as err:
            if err.refused:
                self.tell_sign_in_refused(sign_in)
            raise ConnectorError("auth", str(err)) from None
        finally:
            web.close()

    def tell_sign_in_refused(self, sign_in: Any) -> None:
        """Ask the person once to sign in again, unless a question about this sign-in is already open."""
        from engine.storage import WriteContext

        pm = self.cfg.workspace.user.person
        if not pm or self.store.read().get("person", pm) is None:
            return
        resolves = {"kind": "sign_in", "name": sign_in.name}
        if any(
            q.data.get("resolves") == resolves and q.data["status"] == "open"
            for q in self.store.read().list("question")
        ):
            return
        with self.store.transaction() as tx:
            tx.create(
                "question",
                {
                    "to": pm,
                    "title": f"Sign in to {sign_in.label} again",
                    "text": f"{sign_in.label} stopped accepting this app's sign-in, so it can't be read. Sign in "
                    "again from Settings, under Sign-ins.",
                    "kind": "decision",
                    "resolves": resolves,
                },
                WriteContext(actor="engine", trust="trusted", op="sign_in.refused"),
            )

    def signed_in(self, sign_in: Any, workspace_root: Any) -> str | None:
        """After signing in: close the question asking to, and name the account when the plugin can. Returns it."""
        from engine.connectors import ConnectorError
        from engine.sign_in import keep, kept
        from engine.storage import WriteContext

        resolves = {"kind": "sign_in", "name": sign_in.name}
        open_ones = [
            q
            for q in self.store.read().list("question")
            if q.data.get("resolves") == resolves and q.data["status"] == "open"
        ]
        if open_ones:
            with self.store.transaction() as tx:
                for q in open_ones:
                    tx.update(
                        "question",
                        q.id,
                        {"status": "dropped"},
                        WriteContext(actor="engine", trust="trusted", op="sign_in.done"),
                        read_version=q.version,
                    )
        if sign_in.account is None:
            return None
        context = self.connector_context(sign_in.plugin, workspace_root)
        where = f"account name for {sign_in.name}"
        try:
            name = sign_in.account(context)
            if not isinstance(name, str) or not name.strip():
                raise ValueError("account returns the account's name as text")
        except ConnectorError:
            return None
        except Exception as err:
            self.failed(sign_in.plugin, where, err)
            return None
        finally:
            if context.web is not None:
                context.web.close()
        self.succeeded(sign_in.plugin, where)
        keys = Path(workspace_root) / ".cockpit" / "keys" / sign_in.plugin
        tokens = kept(keys, sign_in)
        if tokens is not None:
            keep(keys, sign_in, {**tokens, "account": " ".join(name.split())[:120]})
        return name

    @property
    def value_lists(self) -> dict[str, dict[str, Any]]:
        """Every running plugin's value lists, by name, with their label and first values."""
        return {
            name: entry
            for plugin, registrar in sorted(self.registrars.items())
            if self.active(plugin)
            for name, entry in registrar.value_lists.items()
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

    def connector_context(self, plugin: str, workspace_root: Any) -> Any:
        """What a plugin's connector gets: a web client for its declared hosts, and its declared secrets."""
        from engine.connectors import ConnectorContext
        from engine.net import WebClient

        requires = self.manifests[plugin].requires
        web = WebClient(list(requires.network)) if requires.network else None
        declared = set(requires.secrets)
        keys = Path(workspace_root) / ".cockpit" / "keys" / plugin

        def secret(name: str) -> str | None:
            from engine.plugin_api import PluginMisuse

            if name not in declared:
                raise PluginMisuse(f"{name} isn't one of the secrets this add-on says it needs")
            return self.plugin_secret(plugin, name, workspace_root)

        own_sign_ins = set(self.registrars[plugin].sign_ins) if plugin in self.registrars else set()

        def token(name: str) -> str:
            from engine.plugin_api import PluginMisuse

            if name not in own_sign_ins:
                raise PluginMisuse(f"{name} isn't a sign-in this plugin registers")
            return self.sign_in_token(name, workspace_root)

        def allowed(name: str) -> set[str]:
            from engine.plugin_api import PluginMisuse
            from engine.sign_in import granted

            if name not in own_sign_ins:
                raise PluginMisuse(f"{name} isn't a sign-in this plugin registers")
            return granted(keys, self.registrars[plugin].sign_ins[name])

        def keep_secret(name: str, value: str) -> None:
            import os

            from engine.plugin_api import PluginMisuse
            from engine.state_file import write_whole

            if name not in declared:
                raise PluginMisuse(f"{name} isn't one of the secrets this add-on says it needs")
            keys.mkdir(parents=True, exist_ok=True)
            os.chmod(keys, 0o700)
            target = keys / name
            write_whole(target, value.strip() + "\n", mode=0o600)

        return ConnectorContext(
            workspace_root=Path(workspace_root),
            web=web,
            secret=secret if declared else None,
            keep_secret=keep_secret if declared else None,
            access_token=token if own_sign_ins else None,
            granted=allowed if own_sign_ins else None,
        )

    def poll_connector(self, connector: Any, settings: Any, state: dict[str, Any], context: Any) -> Any:
        """Read a plugin's connector: its ConnectorError passes through; anything else is contained like a job."""
        from engine.connectors import ConnectorError, checked_poll

        plugin = connector.name.split("/", 1)[0]
        where = f"connector {connector.name}"
        context = self.connector_context(plugin, context.workspace_root)
        try:
            poll = checked_poll(connector.poll(settings, deepcopy(state), context))
        except ConnectorError:
            raise
        except Exception as err:
            self.failed(plugin, where, err)
            raise ConnectorError("outage", f"the add-on {plugin} failed reading it: {err}") from None
        finally:
            if context.web is not None:
                context.web.close()
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
        args = [reader, registrar.config.model_copy(deep=True)]
        if _positional_count(step.done) >= 3:
            args.append(self.setup_state(plugin, step))
        try:
            done = bool(step.done(*args))
        except Exception as err:
            self.failed(plugin, f"setup step {step.name}", err)
            return False
        self.succeeded(plugin, f"setup step {step.name}")
        return done

    def setup_state(self, plugin: str, step: Any) -> Any:
        """What a setup step's `done` sees besides records: its secrets that are set, the effective values of the
        settings it suggests (from the files as they are now), AI accounts per role, and its programs."""
        import os

        from engine.config import ConfigError, load_config
        from engine.plugin_api import SetupState

        root = Path(self.store.path).parent
        declared = self.manifests[plugin].requires.secrets
        try:
            current = load_config(root / "config", env=dict(os.environ))
        except ConfigError:
            current = self.cfg
        settings = {key: current.value(key) for key in step.settings}
        tools = {tool.name for tool in self.manifests[plugin].requires.tools}
        box = self.tool_box(plugin) if tools else None
        return SetupState(
            (n for n in declared if self.plugin_secret(plugin, n, root)),
            settings=settings,
            accounts=_accounts_per_role(current.ai),
            tool_available=(lambda name: name in tools and box.available(name)) if box else None,
        )

    def panel(self, name: str) -> Any | None:
        plugin = name.split("/", 1)[0]
        registrar = self.registrars.get(plugin)
        return registrar.panels.get(name) if registrar and self.active(plugin) else None

    def panel_document(self, name: str, project: str | None = None) -> list[dict[str, Any]] | None:
        """A document panel's blocks for the project in view (or the workspace), from the plugin's Markdown; None
        when it has nothing to show yet. A failure is contained, noted on the plugin, and raised as StoreError."""
        from engine.documents import DocumentError, blocks
        from engine.plugin_api import ReadView

        panel = self.panel(name)
        if panel is None or panel.view != "document":
            raise StoreError(f"there is no document {name} running now")
        plugin = name.split("/", 1)[0]
        view = self.store.read()
        reader = self._with_files(ReadView(view, plugin))
        where = f"document {name}"

        def can_link(kind: str, record_id: str) -> bool:
            if "/" in kind and not kind.startswith(plugin + "/"):
                return False
            return view.get(kind, record_id) is not None

        record = view.get("project", project) if project else None
        try:
            settings = self.registrars[plugin].config.model_copy(deep=True)
            text = panel.render(reader, settings, deepcopy(record) if record is not None else None)
            found = None if text is None else blocks(text, can_link)
        except (DocumentError, Exception) as err:
            self.failed(plugin, where, err)
            raise StoreError(f"{panel.title} couldn't be shown: {err}") from None
        self.succeeded(plugin, where)
        return found

    def panel_rows(self, name: str, project: str | None = None) -> list[dict[str, Any]]:
        """The rows of a running plugin's panel: records of its kind matching its filter, with its columns."""
        panel = self.panel(name)
        if panel is None or panel.view == "document":
            raise StoreError(f"there is no panel {name} running now")
        from engine.plugin_api import ReadView

        plugin = name.split("/", 1)[0]
        view = self.store.read()
        model = self.records.get(panel.kind)
        has_project = model is not None and "project" in model.model_fields
        via = getattr(model, "layout_project", None)
        equals = dict(panel.filter) | ({"project": project} if project and has_project else {})
        records = view.find(panel.kind, equals) if equals else view.list(panel.kind)
        if project and not has_project:
            if not via:
                raise StoreError(f"{panel.kind} isn't kept per project, so this panel can't be filtered by one")
            records = [r for r in records if self._project_through(view, panel.kind, via, r) == project]
        reader = self._with_files(ReadView(view, plugin)) if panel.computed else None
        settings = self.registrars[plugin].config if panel.computed else None
        shared: dict[str, dict] = {column: {} for column in panel.computed}
        rows = []
        for r in records:
            values = {}
            for column in panel.columns:
                fn = panel.computed.get(column)
                values[column] = (
                    r.data.get(column)
                    if fn is None
                    else self._computed(plugin, panel, column, r, reader, settings, shared[column])
                )
            rows.append({"id": r.id, "values": values})
        return rows

    def _project_through(self, view: Any, kind: str, via: str, record: Any) -> str | None:
        """The project of the record a reference field points at, for a kind kept under another record's project."""
        from engine.records import ref_fields

        target = dict(ref_fields(self.records[kind])).get(via)
        referred = view.get(target, record.data.get(via) or "") if target else None
        return referred.data.get("project") if referred is not None else None

    def _computed(
        self, plugin: str, panel: Any, column: str, record: Any, reader: Any, settings: Any, shared: dict
    ) -> Any:
        """One computed cell: a short value, or None when the function fails (contained, noted on the plugin). A
        function taking a fourth argument gets `shared`, one dict for every cell of the column in this listing."""
        where = f"panel {panel.name} column {column}"
        fn = panel.computed[column]
        try:
            args = [deepcopy(record), reader, settings.model_copy(deep=True)]
            if _positional_count(fn) >= 4:
                args.append(shared)
            value = fn(*args)
            if value is not None and not isinstance(value, str | int | float | bool):
                raise ValueError("a computed column returns a short str, a number, a bool or None")
            if isinstance(value, str) and (len(value) > 200 or "\n" in value):
                raise ValueError("a computed column's text is one short line")
        except Exception as err:
            self.failed(plugin, where, err)
            return None
        self.succeeded(plugin, where)
        return value

    def panel_shown_for(self, panel: Any, project: str) -> bool:
        """Whether a panel is listed on a project: its `show_for`, contained (a failure hides it)."""
        from engine.plugin_api import ReadView

        if panel.show_for is None:
            return True
        plugin = panel.name.split("/", 1)[0]
        view = self.store.read()
        record = view.get("project", project)
        if record is None:
            return False
        try:
            shown = bool(panel.show_for(deepcopy(record), self._with_files(ReadView(view, plugin))))
        except Exception as err:
            self.failed(plugin, f"panel {panel.name} show_for", err)
            return False
        return shown

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
            try:
                manifest = read_manifest(path)
            except ValidationError as err:
                raise ValueError(plain_error(err, MANIFEST_PARTS)) from None
            if manifest.name != name:
                raise ValueError("manifest name must match its discovery name")
            self.manifests[name] = manifest
            self.status[name] = PluginStatus(name, "loading", manifest.version, notes=list(self.notes.get(name, [])))
            if Version(PLUGIN_API_VERSION) not in SpecifierSet(manifest.plugin_api):
                raise ValueError(
                    f"this add-on was made for another version of the add-on interface (it asks for "
                    f"{manifest.plugin_api}; this app has {PLUGIN_API_VERSION})"
                )
            if manifest.provides.data and not (path.parent / manifest.provides.data).is_dir():
                raise ValueError(f"the data folder {manifest.provides.data} that this add-on ships is missing")
            for key in NOT_YET:
                section, _, attribute = key.partition(".")
                if getattr(getattr(manifest, section), attribute):
                    log.warning(
                        "Add-on %s uses %s, which version %s doesn't provide yet", name, key, PLUGIN_API_VERSION
                    )
                    raise ValueError("this add-on uses something this version of the app doesn't provide yet")
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
                raise ValueError("this add-on's settings aren't built the way the app requires")
            for key, info in schema.model_fields.items():
                if info.is_required() or not info.description:
                    raise ValueError(f"the setting {key} needs a default and a description")
            config_path = self.store.path.parent / "config" / "plugins" / f"{name}.yaml"
            raw = load_yaml(config_path.read_text()) if config_path.exists() else {}
            try:
                config = schema.model_validate({} if raw is None else raw)
            except ValidationError as err:
                raise ValueError(plain_error(err)) from None
            for new_name, old_name in schema.renamed_keys(raw):
                self.status[name].notes.append(
                    f"its settings use the old name {old_name}; it now reads as {new_name}. Saving its "
                    "settings on the Settings screen writes the new name."
                )
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
                f"(see Settings, Files), so it accepts {', '.join(kept) if kept else 'no files at all'}"
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
            raise ValueError("this add-on lists the same program more than once")
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
            raise ValueError("this add-on's settings aren't built the way the app requires")
        return schema

    def _importer(self, root: Path, top: str):
        namespace = "_cockpit_plugin_" + uuid.uuid4().hex
        self._modules.append(namespace)
        init = root / "__init__.py"
        if init.exists():
            # A plugin may import its own package by name, as it would when installed: it is loaded under that name,
            # unless something else already has it.
            if top and top not in sys.modules and importlib.util.find_spec(top) is None:
                self._modules.append(top)
                namespace = top
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
            ("sign_ins", registrar.sign_ins),
            ("value_lists", registrar.value_lists),
            ("data_forms", registrar.data_forms),
        ):
            declared = set(getattr(expected, key))
            if f"{registrar.name}/*" in declared:
                # Identifiers the plugin's own settings define: any of its namespace, and only those.
                if not all(n.startswith(registrar.name + "/") for n in actual):
                    raise ValueError(f"registered {key} must be in the plugin's own namespace")
                continue
            if declared != set(actual):
                raise ValueError(f"registered {key} does not match provides exactly")
        from engine.lists import core_lists
        from engine.records import list_fields

        core = set(core_lists())
        for kind, model in registrar.records.items():
            for field, name, _ in list_fields(model):
                if name not in core and name not in registrar.value_lists:
                    raise ValueError(
                        f"{kind}.{field} takes values from {name}, which is neither its own list nor the core's"
                    )
        for sign_in in registrar.sign_ins.values():
            from engine.sign_in import check_addresses

            check_addresses(sign_in, list(manifest.requires.network))
            for secret in (sign_in.client_id, sign_in.client_secret):
                if secret is not None and secret not in manifest.requires.secrets:
                    raise ValueError(f"sign-in {sign_in.name} reads {secret}, which the add-on doesn't say it needs")
            for source in sign_in.sources:
                connector = registrar.connectors.get(source["connector"])
                if connector is None:
                    raise ValueError(f"sign-in {sign_in.name} starts {source['connector']}, which isn't its connector")
                try:
                    connector.settings.model_validate(source["settings"])
                except Exception as err:
                    raise ValueError(f"sign-in {sign_in.name}: settings for {source['connector']}: {err}") from None
        said = {name: c.reads for name, c in registrar.connectors.items() if c.reads}
        if said != dict(expected.connector_reads):
            raise ValueError("the connectors it registers don't read what it says they read")
        if set(manifest.interfaces.defines) != set(registrar.interface_definitions):
            raise ValueError("the interfaces it registers to define don't match the ones it says it defines")
        provided = {f"{p.interface}@{p.major}" for p in registrar.interface_provisions.values()}
        if set(manifest.interfaces.provides) != provided:
            raise ValueError("the interfaces it registers to provide don't match the ones it says it provides")
        if set(manifest.events()) != set(registrar.handlers):
            raise ValueError("the events it registers handlers for don't match the events it says it handles")
        if len(manifest.events()) != len(set(manifest.events())):
            raise ValueError("handle each event once; one handler can route the kinds it gets")
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
            if model.learning not in ("core", "own"):
                raise ValueError('learning must be "core" or "own"')
            if model.data_level not in manifest.requires.data_levels:
                raise ValueError(
                    f"{model.record_kind} holds {model.data_level} material, which the add-on doesn't say it keeps"
                )
            for field, target in ref_fields(model):
                if target not in REGISTRY and target not in registrar.records:
                    raise ValueError(f"{field} refers to an unknown record kind {target}")
        for file_kind in registrar.file_kinds.values():
            if file_kind.data_level is not None and file_kind.data_level not in manifest.requires.data_levels:
                raise ValueError(
                    f"{file_kind.name} holds {file_kind.data_level} material, which the add-on doesn't say it keeps"
                )
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
            if panel.view == "document":
                continue
            model = registrar.records.get(panel.kind) or REGISTRY.get(panel.kind)
            if model is None:
                raise ValueError(f"panel {panel.name} lists {panel.kind}, which is neither core nor the plugin's own")
            for field_name in (*[c for c in panel.columns if c not in panel.computed], *panel.filter):
                if field_name not in model.model_fields:
                    raise ValueError(f"panel {panel.name}: {panel.kind} has no field {field_name}")
            clash = [c for c in panel.computed if c in model.model_fields]
            if clash:
                raise ValueError(f"panel {panel.name}: computed column {clash[0]} is already a field of {panel.kind}")
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
        outer, self._in_stage_check = self._in_stage_check, True
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
        finally:
            self._in_stage_check = outer

    def lint_findings(
        self, op: Any, view: Any, severity: Any = None, origin: dict[str, Any] | None = None
    ) -> list[tuple[str, str, Any]]:
        """(lint name, severity, finding) for every running plugin's lint on this op. `severity(name, default)` gives
        the workspace's severity; a lint switched off isn't called. A lint taking a fourth argument gets the run's
        `origin`. A lint that raises or returns something else turns its plugin off and finds nothing."""
        from engine.plugin_api import LintFinding

        found = []
        for name, registrar in self.registrars.items():
            if not self.active(name):
                continue
            for lint in registrar.lints.values():
                if op.op not in lint.ops:
                    continue
                level = severity(lint.name, lint.severity) if severity is not None else lint.severity
                if level == "off":
                    continue
                try:
                    read = self._with_files(ReadView(view, name))
                    args = [op.model_copy(deep=True), read, registrar.config.model_copy(deep=True)]
                    if _positional_count(lint.fn) >= 4:
                        args.append(dict(origin or {}))
                    result = lint.fn(*args)
                    if not isinstance(result, list) or any(not isinstance(f, LintFinding) for f in result):
                        raise ValueError("lints return a list of LintFinding")
                    found += [(lint.name, level, f) for f in result]
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
        view.find_interface_about = lambda item, task: self.interface_about(plugin, item, task)
        view.user = self.cfg.workspace.user.person
        view.stage_status_of = self._stage_status
        return view

    def _stage_status(self, record: Any) -> Any:
        """A record's place in the effective stages, for ReadView.stage_status; refused inside a stage check, whose
        own result it would need."""
        from engine.plugin_api import PluginMisuse, StageStatus
        from engine.stages import record_status

        if self._in_stage_check:
            raise PluginMisuse("a stage check can't ask for stage status, which runs the stage checks")
        settings = self.stages.types.get(record.kind)
        if settings is None or not settings.stages:
            return None
        status = record_status(self.store, record)
        return StageStatus(
            current=status["current"],
            stages=tuple(s["id"] for s in status["stages"]),
            next=status["next"]["id"] if status["next"] else None,
            checks={c["id"]: StageCheckResult(c["passed"], c["reason"]) for c in status["checks"]},
            ready=status["ready"],
            current_label=status["current_label"],
            next_label=status["next"]["label"] if status["next"] else None,
        )

    def wording(self) -> dict[str, str]:
        """What the screens call running plugins' own things: each AI task kind's label as `task.<kind>`, then the
        plugins' wording files. A key must name something in its plugin's namespace; other keys and values that
        aren't short text are left out and noted on the plugin."""
        from engine.yaml_load import load_yaml

        found: dict[str, str] = {}
        for plugin in sorted(self.manifests):
            if not self.active(plugin):
                continue
            registrar = self.registrars.get(plugin)
            for name, kind in (registrar.tasks if registrar else {}).items():
                if kind.label:
                    found[f"task.{name}"] = kind.label
            for relative in self.manifests[plugin].provides.wording:
                path = self.candidates[plugin].parent / relative
                try:
                    data = load_yaml(path.read_text(encoding="utf-8")) or {}
                except (OSError, yaml.YAMLError) as err:
                    self._note(plugin, f"its wording file {relative} can't be read: {err}")
                    continue
                if not isinstance(data, dict):
                    self._note(plugin, f"its wording file {relative} isn't a map of key to text")
                    continue
                for key, text in data.items():
                    if (
                        not isinstance(key, str)
                        or f"{plugin}/" not in key
                        or not _wording_key_known(key)
                        or not isinstance(text, str)
                        or not text.strip()
                        or len(text) > WORDING_MAX
                    ):
                        self._note(
                            plugin,
                            f"its wording {key!r} was left out: it isn't a key the screens read for its own things "
                            "(see the guide), or the text isn't short",
                        )
                        continue
                    found[key] = " ".join(text.split())
        return found

    def help_sections(self) -> list[Any]:
        """Every running plugin's help, one section per `##` heading, titled "<plugin>: <heading>"."""
        from engine.help import Section, guide_sections

        found = []
        for plugin in sorted(self.manifests):
            if not self.active(plugin):
                continue
            for relative in self.manifests[plugin].provides.help:
                path = self.candidates[plugin].parent / relative
                if not path.is_file():
                    self._note(plugin, f"its help file {relative} isn't there")
                    continue
                found += [Section(f"{plugin}: {s.title}", s.text) for s in guide_sections(path)]
        return found

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
        take a third argument); a validator with a `settings` parameter gets the plugin's settings by keyword."""
        problems = []
        origin = {
            "task": None,
            "about": None,
            "request": None,
            "part": None,
            **(origin or {"actor": "pm", "trust": "trusted", "via": "screen"}),
        }
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
                    extra = {"settings": registrar.config.model_copy(deep=True)} if _takes_settings(fn) else {}
                    if takes == "keyword":
                        result = fn(op.model_copy(deep=True), read, origin=dict(origin), **extra)
                    elif takes == "positional":
                        result = fn(op.model_copy(deep=True), read, dict(origin), **extra)
                    else:
                        result = fn(op.model_copy(deep=True), read, **extra)
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
            self.store,
            self.cfg,
            People(self.store, self.cfg),
            own,
            Inputs(request.id, None, "", "", "untrusted"),
            via="job" if event.startswith("job:") else "handler",
        )
        return apply_changeset(changeset, [], ctx, run=None)

    def _checked_request(self, name: str, tx: Any, data: dict[str, Any]) -> dict[str, Any]:
        """A request a handler or job queued, resolved (through an interface) and checked; StoreError says why not."""
        via = "via" in data
        if via:
            data = self._interface_request(name, data)
        elif "task" not in data:
            raise StoreError("a request names a task kind")
        task = data["task"]
        if "/" in task and not task.startswith(name + "/") and not via:
            raise StoreError("requesting another plugin requires an interface")
        check_about(tx, self.task_kind(task), data.get("about"), self.store)
        if data.get("part") is not None:
            from engine.texts import check_part

            try:
                data["part"] = check_part(self.task_kind(task), data["part"])
            except ValueError as err:
                raise StoreError(str(err)) from None
        return data

    def _write_commands(self, name: str, commands: list, event: str = "", payload: dict | None = None) -> None:
        context = WriteContext(actor="plugin", trust="untrusted", op=f"{name}/event")
        with self.store.transaction() as tx:
            for kind, data in commands:
                allowed_fields = {
                    "request": {
                        "task",
                        "note",
                        "about",
                        "via",
                        "interface_task",
                        "provider",
                        "needs_go",
                        "item",
                        "part",
                    },
                    "question": {"title", "text"},
                }
                if kind not in allowed_fields or not set(data) <= allowed_fields[kind]:
                    raise PluginMisuse("event handlers may only queue requests or file questions")
                needs_go = bool(data.pop("needs_go", False)) if kind == "request" else False
                if kind == "request":
                    try:
                        data = self._checked_request(name, tx, data)
                    except PluginMisuse:
                        raise
                    except StoreError as err:
                        # One refused request is skipped and noted; the handler's other work still goes ahead.
                        self._note(name, f"a request it queued was skipped: {err}")
                        continue
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


def check_about(view: Any, kind: Any, about: dict[str, str] | None, store: Any = None, starting: bool = False) -> None:
    """A request for a task kind declared `on` a record kind must name a live record of that kind that its `where`
    matches (and its `start_where`, when the person is `starting` it); others name none."""
    if kind.on is None:
        if about is not None:
            raise StoreError(f"{kind.name} doesn't work on a record")
        return
    from engine.records import REGISTRY, kind_label

    models = store.plugins.records if store is not None else REGISTRY
    what = kind_label(models.get(kind.on), kind.on)
    if about is None or about.get("kind") != kind.on:
        raise StoreError(f"{kind.label or kind.name} works on a {what}")
    record = view.get(about["kind"], about["id"])
    if record is None:
        raise StoreError(f"there is no {what} {about['id']}")
    texts = None
    if store is not None:
        from engine.texts import text_presence

        texts = text_presence(store, view, record)
    if not (kind.startable_on(record, texts) if starting else kind.offered_on(record, texts)):
        raise StoreError(f"{kind.label or kind.name} isn't for this {what}")


def _accounts_per_role(ai: Any) -> dict[str, int]:
    """How many distinct accounts can do each role's work: those of the tier the role names (its main account and
    fallbacks), else of every tier. An account is counted only when it is set up in `ai.providers`."""

    def accounts(tier: Any) -> set[str]:
        refs = [tier.use, *tier.fallback] if tier is not None else []
        return {ref.split("/", 1)[0] for ref in refs if ref and ref.split("/", 1)[0] in ai.providers}

    found = {}
    for role in type(ai.roles).model_fields:
        named = getattr(ai.roles, role).tier
        tiers = [ai.tiers.get(named)] if named else list(ai.tiers.values())
        found[role] = len(set().union(*(accounts(t) for t in tiers)) if tiers else set())
    return found


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


def _takes_settings(fn: Any) -> bool:
    """Whether a validator takes the plugin's settings: a parameter named `settings`, or `**kwargs`."""
    import inspect

    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "settings" or p.kind == p.VAR_KEYWORD for p in params)


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
