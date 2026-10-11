"""The public plugin contract: the only module a plugin imports from the host.

A plugin is a Python package with a `plugin.yaml` beside it. At startup the host reads the manifest, validates the
plugin's settings, and calls its entry function with a `Registrar`. What the plugin registers must match the manifest's
`provides` and `subscribes` exactly; registration is all or nothing.

Plugins change knowledge only through ops, which the applier checks, records in the ledger and can undo. Ops get a
writer limited to what they declare; validators, stage checks and event handlers get read-only views; person actions
return a proposal the person reviews. Plugins read core records and their own, never another plugin's. Every identifier
is namespaced `<plugin>/<name>`.

Plugins run in the host's process: enabling one trusts its code. A plugin that breaks its contract, or whose callback
raises an unexpected exception, is turned off for the run with the reason in its status; core work and other plugins
carry on.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from engine.config.schema import StageDefinition, TypeStages
from engine.ops import EvidenceIn, OpModel, Tier
from engine.records import Record, RefTo, ref_fields, values_at
from engine.storage import Stored, StoreError, WriteContext
from engine.tasks import TaskKind
from engine.texts import LongText, Unit
from engine.tools import ToolBox, ToolError, ToolResult

PLUGIN_API_VERSION = "0.3.8"


class Settings(BaseModel):
    """Base for a plugin's settings, read from `config/plugins/<plugin>.yaml`. Every field needs a default and a
    description; unknown keys are refused. Handlers and actions get a copy as `context.config`. A field may be a nested
    model (shown as its own section on the Settings screen; keep it to one level) and may use an alias when its name
    in the file can't be a Python name."""

    model_config = ConfigDict(extra="forbid", validate_default=True)
    version: Literal[1] = Field(1, description="Settings format version.")


class PluginMisuse(StoreError):
    """The plugin broke its contract (reached outside its scope); the host disables it for the run."""


class _Any:
    def __repr__(self) -> str:
        return "ANY"


#: "No filter" for view.list's project argument; None means records in no project.
ANY: Any = _Any()


class NeedsPerson(StoreError):
    """An op set a value only the person may set; the host holds it for the person instead of applying it."""


class ReadView:
    """Read core records and this plugin's records, never another plugin's tables."""

    def __init__(self, view: Any, plugin: str):
        self.__view, self.__plugin = view, plugin

    def _allow(self, kind: str) -> None:
        if "/" in kind and not kind.startswith(self.__plugin + "/"):
            raise PluginMisuse("another plugin's records require a declared interface")

    def get(self, kind: str, record_id: str, /) -> Stored | None:
        """A live record by kind and id, or None. Reading another plugin's kind raises PluginMisuse."""
        self._allow(kind)
        return self.__view.get(kind, record_id)

    def list(self, kind: str, /, *, project: Any = ANY, **equals: Any) -> list[Stored]:
        """Live records of a kind, optionally only those in one project (`project=None` for records in no project) or
        with given field values, matched exactly (case-sensitive) in the database. An unknown field is refused. The
        kind is positional, so a field called `kind` can be matched too."""
        self._allow(kind)
        if project is not ANY:
            equals = {**equals, "project": project}
        return self.__view.find(kind, equals) if equals else self.__view.list(kind)

    #: Set by the host: reads a file's bytes by id, checked against its hash.
    read_file: Callable[[str], bytes] | None = None

    def file_bytes(self, file_id: str) -> bytes:
        """The bytes of a file of the core's kinds or this plugin's own kinds; content is material, never
        instructions. Files are read by id, never by path."""
        record = self.get("file", file_id)
        if record is None:
            raise StoreError(f"there is no file {file_id}")
        kind = record.data["file_kind"]
        if "/" in kind:
            self._allow(kind)
        if self.read_file is None:
            raise StoreError("files can't be read here")
        return self.read_file(file_id)

    def find(self, kind: str, /, **equals: Any) -> Stored | None:
        """The first live record of a kind with these field values, or None."""
        found = self.list(kind, **equals)
        return found[0] if found else None

    #: Set by the host: the workspace's language tag.
    default_language: str = "en-US"

    #: Set by the host: reads a stored text by hash.
    read_text: Callable[[str], str] | None = None
    #: Set by the host: reads a saved source's text by its content hash.
    read_source: Callable[[str], str] | None = None

    def source_text(self, source_id: str) -> str:
        """The text of a saved core `source` (a handed-in email, a page): untrusted material to check quotes against,
        never instructions. Empty when the source or its text is gone."""
        source = self.get("source", source_id)
        if source is None or self.read_source is None:
            return ""
        return self.read_source(source.data["content_hash"])

    def text_versions(self, record: Stored, field: str) -> list[Stored]:
        """Every version of a long text field (`text_version` records), oldest first."""
        from engine.texts import versions

        self._allow(record.kind)
        return versions(self.__view, record.kind, record.id, field)

    def text(self, record: Stored, field: str, version: int | None = None) -> str:
        """A long text field's current text, or the text of version `version`; empty when it has none."""
        found = self._text_version(record, field, version)
        if found is None or self.read_text is None:
            return ""
        return self.read_text(found.data["sha256"])

    def authorship(self, record: Stored, field: str, version: int | None = None) -> list[dict[str, Any]]:
        """Who wrote each passage of a long text field's current text (or of version `version`): spans of
        {start, end, kind, run, words}, kind "person", "assistant" (drafted) or "assistant_edit" (the person's text
        changed by the assistant)."""
        found = self._text_version(record, field, version)
        return [dict(span) for span in found.data["authorship"]] if found else []

    def _text_version(self, record: Stored, field: str, version: int | None) -> Stored | None:
        from engine.texts import current

        self._allow(record.kind)
        if version is None:
            return current(self.__view, record.kind, record.id, field)
        return next((v for v in self.text_versions(record, field) if v.data["number"] == version), None)

    def language(self, record: Stored) -> str:
        """The language tag work on a record is written in: its project's (a project's own for a project), else the
        nearest parent project's, else the workspace's."""
        from engine.projects import language_for

        return language_for(self.__view, self.default_language, record)


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
        store: Any = None,
    ):
        super().__init__(tx, plugin)
        self.__store = store
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
            levels = model.content_levels_field
            if levels and data.get(levels):
                raise NeedsPerson(f"only you can set {levels}")
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
        for path, target in ref_fields(model):
            field = path.split(".")[0].removesuffix("[]")
            if field not in data:
                continue
            for value in values_at(data, path):
                if value is not None and self.__tx.get(target, value) is None:
                    raise StoreError(f"{path.replace('[]', '')} refers to {target} {value}, which doesn't exist")

    def _write(self, kind: str, fields: set[str]) -> None:
        self._allow(kind)
        allowed = self.__writes.get(kind, ())
        if not allowed or ("*" not in allowed and not fields <= set(allowed)):
            raise PluginMisuse("op attempted to write outside its declared fields")

    def create(self, kind: str, data: dict[str, Any]) -> Stored:
        """Create one of this plugin's records (the op declares `("*",)` for the kind). The record type's rules are
        enforced: person-only values from anyone but the person hold the op, unique groups and references refuse it."""
        if kind == "request" and (data.get("stage_start") is not None or data.get("approval") is not None):
            raise PluginMisuse("stage task approval belongs to the core")
        if data.get("stage") is not None:
            raise PluginMisuse("stage changes require stage.move")
        self._write(kind, {"*"})
        self._no_long_text(kind, data)
        self._declared(kind, None, data)
        result = self.__tx.create(kind, data, self.__context)
        self.touched.append({"kind": kind, "id": result.id})
        return result

    def _no_long_text(self, kind: str, data: dict[str, Any]) -> None:
        from engine.texts import long_text_fields

        model = self.__models.get(kind)
        written = set(long_text_fields(model)) & {k for k, v in data.items() if v is not None} if model else set()
        if written:
            raise PluginMisuse(f"{', '.join(sorted(written))} is long text: write it with writer.set_text")

    def set_text(self, kind: str, record_id: str, field: str, text: str) -> Stored:
        """Write a new version of one of this plugin's long text fields (the op declares the field in `writes`). From
        the person (their own action) it becomes the field's text at once, written by the person; from anyone else it
        is a draft waiting for the person's review, written by the assistant. Returns the `text_version` record."""
        from engine.texts import new_version

        self._write(kind, {field})
        person = self.__context.actor == "pm"
        version = new_version(
            self.__store,
            self.__tx,
            self.__context,
            kind,
            record_id,
            field,
            text,
            source="import" if person else "draft",
            by="person" if person else "assistant",
            accept=person,
        )
        self.touched.append({"kind": kind, "id": record_id})
        return version

    def update(self, kind: str, record_id: str, changes: dict[str, Any], *, read_version: int) -> Stored:
        """Change fields of one of this plugin's records, stating the version that was read; a newer version refuses
        the op. Only fields the op declares in `writes` may change; long text fields change with `set_text`."""
        if kind == "request" and {"approval", "stage_start"} & set(changes):
            raise PluginMisuse("stage task approval belongs to the core")
        if "stage" in changes:
            raise PluginMisuse("stage changes require stage.move")
        self._write(kind, set(changes))
        self._no_long_text(kind, changes)
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
    """What an event handler gets: a read view, the plugin's settings, and two commands the core carries out after the
    handler returns (never direct writes or sends). If the handler raises, its commands are dropped."""

    def __init__(self, view: Any, plugin: str, config: Settings):
        super().__init__(view, plugin)
        self.config = config.model_copy(deep=True)
        self.commands: list[tuple[str, dict[str, Any]]] = []

    def queue_request(self, task: str, note: str, about: Stored | tuple[str, str] | None = None) -> None:
        """Queue AI work of one of this plugin's task kinds (or a core one). `about` is the record it works on, as a
        record or (kind, id), required for a task kind declared `on` a kind. The note reaches the assistant as
        untrusted material, and system ops from it wait for the person. After a stage move, it waits for the go."""
        data: dict[str, Any] = {"task": task, "note": note}
        if about is not None:
            kind, record_id = (about.kind, about.id) if isinstance(about, Stored) else about
            self._allow(kind)
            data["about"] = {"kind": kind, "id": record_id}
        self.commands.append(("request", data))

    def file_question(self, title: str, text: str = "") -> None:
        """File a question for the configured PM; sending is never part of handling an event."""
        self.commands.append(("question", {"title": title, "text": text}))


class ActionContext(ReadView):
    """What a person action sees: core and own records, file bytes, the plugin's settings and its declared programs.
    It changes nothing itself; it returns a Proposal the person reviews."""

    def __init__(self, view: Any, plugin: str, config: Settings, tools: Any):
        super().__init__(view, plugin)
        self.config = config.model_copy(deep=True)
        self.tools = tools


@dataclass
class Choice:
    """A named choice the person can flip on the review; the action runs again with the new value before anything
    applies. `options` are (value, label) pairs; none means on or off."""

    id: str
    label: str
    value: str | bool
    options: list[tuple[str, str]] = field(default_factory=list)
    help: str = ""
    group: str | None = None  # the id of a Group in the proposal's groups


@dataclass
class Group:
    """A heading and a short explanation shared by the choices and items under it, so a long review reads as a few
    groups with counts."""

    id: str
    heading: str
    explanation: str = ""


@dataclass
class Item:
    """A change the person keeps or drops without the action running again: one judgment call, made of one or more
    ops (dicts) that apply together. `id` is stable across runs, so the person's tick carries over to an unchanged
    item when a choice reruns the action. An item's ops undo together; an op that sets its own `group` keeps it, so
    several items can share one Undo."""

    id: str
    label: str
    ops: list[dict[str, Any]]
    group: str | None = None
    kept: bool = True


@dataclass
class Preview:
    """Something to look at on the review (an image the plugin rendered, or plain text). Shown, never saved or sent."""

    name: str
    media_type: str
    data: bytes
    caption: str = ""


@dataclass
class NewFile:
    """A file the action made. Applying the proposal adds it; ops refer to it as "$file:<index in files>"."""

    name: str
    media_type: str
    data: bytes
    file_kind: str = "attachment"
    project: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    replaces: str | None = None


@dataclass
class Proposal:
    """One action's result for one review: what it would change (ops, as dicts), files it made, what to look at,
    choices the person can flip, and anything the person should know (notes)."""

    summary: str
    ops: list[dict[str, Any]] = field(default_factory=list)  # always applied
    files: list[NewFile] = field(default_factory=list)
    previews: list[Preview] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)  # applied only while kept
    groups: list[Group] = field(default_factory=list)


@dataclass
class LintFinding:
    """One problem a lint found in an op: what is wrong, the exact passage it is about (when it is about one), and how
    to fix it. On a "return" severity the guidance goes back to the assistant for its fix round."""

    message: str
    passage: str | None = None
    guidance: str | None = None


@dataclass(frozen=True)
class LintRegistration:
    """A registered lint (host side)."""

    name: str
    fn: Callable
    ops: tuple[str, ...]
    severity: str


@dataclass
class Part:
    """One piece of what an AI run sees, in a task kind's packet. Untrusted content (the default; `trusted` only for the
    person's own words) is marked in the packet as material, never instructions, and any untrusted part makes the run's
    changeset untrusted, so its system ops wait for the person. A `reference_only` part informs the run but is marked
    not to be quoted or reproduced. Evidence may quote any part that isn't reference-only, and is cited as
    "<kind>:<id>" of the record the run is about."""

    title: str
    text: str
    trusted: bool = False
    reference_only: bool = False


@dataclass
class PacketParts:
    """What a run of a plugin's task kind sees beyond its instructions. `stable` parts are the same on every run of the
    kind for the same record (a style sheet, the summaries around a chapter) and go first, so providers can reuse a
    cached prefix; `request` parts are this run's material (the chapter) and go last."""

    stable: list[Part] = field(default_factory=list)
    request: list[Part] = field(default_factory=list)


@dataclass(frozen=True)
class ActionRegistration:
    """A registered person action (host side)."""

    name: str
    label: str
    on: str | None
    run: Callable
    file_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpRegistration:
    """A registered op (host side)."""

    model: type[OpModel]
    tier: Tier
    apply: Callable
    writes: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class StageCheckResult:
    """What a stage check returns: whether the item may enter the stage, and why, in plain words for the person."""

    passed: bool
    reason: str


class Registrar:
    """A staging registry: the host installs it only after checking the manifest."""

    def __init__(self, name: str, config: Settings, root: Path | None = None):
        self.name, self.config, self.root = name, config, root
        self.records: dict[str, type[Record]] = {}
        self.ops: dict[str, OpRegistration] = {}
        self.validators: dict[str, list[Callable]] = {}
        self.tasks: dict[str, TaskKind] = {}
        self.handlers: dict[str, Callable] = {}
        self.stage_checks: dict[str, Callable] = {}
        self.stage_defaults: dict[str, TypeStages] = {}
        self.file_kinds: dict[str, Any] = {}
        self.actions: dict[str, ActionRegistration] = {}
        self.lints: dict[str, LintRegistration] = {}
        self.text_formats: dict[str, Callable] = {}

    def _name(self, name: str) -> None:
        if not re.fullmatch(re.escape(self.name) + r"/[a-z][a-z0-9_.-]*", name):
            raise ValueError(f"identifier must be namespaced {self.name}/<name>: {name}")

    def record_type(self, model: type[Record]) -> None:
        """Register a record kind: a `Record` subclass with `record_kind` ("<plugin>/<name>") and an id `prefix`
        (capital letters, unique in the workspace)."""
        if not issubclass(model, Record):
            raise ValueError("record_type requires a Record model")
        self._name(model.record_kind)
        if model.record_kind in self.records or not re.fullmatch(r"[A-Z]+", model.prefix):
            raise ValueError("duplicate record kind or invalid id prefix")
        self.records[model.record_kind] = model

    def op(self, model: type[OpModel], tier: Tier, apply: Callable) -> None:
        """Register an op: an `OpModel` subclass with a single literal `op` id and a `writes` class variable mapping
        own record kinds to the fields it may change (`("*",)` to create or delete). `tier` is "data" or "system"
        (system ops from the assistant wait for the person). `apply(op, writer, settings)` makes the change through
        the `OpWriter`; raising StoreError refuses this op only."""
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
        """Check a core or own op before it applies: `fn(op, view, origin)` (or `fn(op, view)`; `origin` may also be
        keyword-only) returns a list of refusal messages, empty to let it through. The view is the changeset so far.
        `origin` is {"actor": "pm" | "assistant" | "rule", "trust": "trusted" | "untrusted", "via": "screen" | "note" |
        "input" | "task" | "rule" | "action"}. Validators run more than once per op, so they must be pure and quick."""
        if not callable(fn):
            raise ValueError("validator must be callable")
        self.validators.setdefault(op_name, []).append(fn)

    def task_kind(
        self,
        name: str,
        *,
        ops: tuple[str, ...] = (),
        label: str = "",
        output: str = "ops",
        field: str | None = None,
        prompt: str = "notes",
        playbook: str = "notes",
        on: str | None = None,
        packet: Callable | None = None,
        tier: str | None = None,
        max_output: int | None = None,
        expected_output: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Register AI work: the core or own ops its answer may use, and `label`, what to call it on screen.

        `prompt` names the instructions: a core prompt ("notes") or the plugin's own, "<plugin>/<name>", read from
        `prompts/<name>.md` in the plugin's folder. `playbook` names its guidance the same way, from
        `guidance/<name>.md`.
        The workspace overrides a plugin's prompt with `prompts/<plugin>/<name>.md`.

        `on` is the record kind a run is about (core or own), when it works on one record: the request then carries that
        record, and the person can start it from the record. `packet(target, view, settings, note) -> PacketParts` says
        what the run sees (without it, the run sees what reading notes sees). It runs before every call, so it must be
        deterministic and quick; raising StoreError stops the run with that message for the person.

        `output` is "ops" (the answer is a changeset of `ops`) or "draft": the answer is plain prose for the long text
        field `field` of the record the run is about (`on` is required). The core wraps it as a pending `text.draft`
        version for the person's review, runs lints on it (lints on the op "text.draft"), sends a "return" finding
        back for one fix round, and continues a draft cut off at the output limit once before holding it.

        `tier`, `max_output` (the most tokens an answer may use), `expected_output` (typical answer size, for estimates
        before there are past runs) and `temperature` are defaults; the workspace's `ai.tasks.<kind>` overrides them."""
        from engine.config.schema import TaskSettings

        self._name(name)
        if output not in ("ops", "draft"):
            raise ValueError('a task kind\'s output is "ops" or "draft"')
        if output == "draft":
            if on is None or not field or ops:
                raise ValueError(
                    "a draft task kind names the record kind it works on and the long text field it drafts"
                )
            ops = ("text.draft",)
        if name in self.tasks or not ops:
            raise ValueError("duplicate task kind or empty op list")
        if packet is not None and not callable(packet):
            raise ValueError("packet must be callable")
        defaults = {
            key: value
            for key, value in (
                ("tier", tier),
                ("max_output", max_output),
                ("expected_output", expected_output),
                ("temperature", temperature),
            )
            if value is not None
        }
        TaskSettings.model_validate(defaults)
        prompt_file = self._own_file(prompt, "prompts")
        guidance_file = self._own_file(playbook, "guidance")
        self.tasks[name] = TaskKind(
            name,
            tuple(ops),
            prompt,
            playbook,
            label=label.strip(),
            on=on,
            packet=packet,
            defaults=defaults,
            prompt_file=prompt_file,
            guidance_file=guidance_file,
            output=output,
            field=field,
        )

    def _own_file(self, name: str, folder: str) -> Path | None:
        """The plugin's own prompt or guidance file for a namespaced name; None for a core name."""
        if "/" not in name:
            return None
        self._name(name)
        if self.root is None:
            raise ValueError(f"{name} needs the plugin's folder")
        path = self.root / folder / f"{name.split('/', 1)[1]}.md"
        if not path.is_file():
            raise ValueError(f"{folder}/{path.name} is missing from the plugin")
        return path

    def stage_check(self, id: str, fn: Callable) -> None:
        """Register a pure check: (record, read_view, settings) -> StageCheckResult. Never call AI. When several checks
        refuse a move, their reasons are shown joined with "; ", so write each as a short clause that reads well
        beside others."""
        self._name(id)
        if id in self.stage_checks or not callable(fn):
            raise ValueError("duplicate stage check or invalid callback")
        self.stage_checks[id] = fn

    def stages(self, record_type: str, stages: list[StageDefinition | dict], *, moves=None) -> None:
        """Default stages for one of this plugin's record types. The workspace's stages.yaml may replace them. `moves`
        is "person" (the default: only the person moves items) or "rule" (stage checks move items forward)."""
        self._name(record_type)
        if record_type in self.stage_defaults:
            raise ValueError("duplicate default stages")
        self.stage_defaults[record_type] = TypeStages(stages=stages, moves=moves)

    def file_kind(
        self,
        name: str,
        *,
        details: type[BaseModel] | None = None,
        accept: tuple[str, ...] = (),
        max_mb: float | None = None,
        label: str = "",
    ) -> None:
        """Declare what a kind of file is for: the details asked for when one is added (a pydantic model), the media
        types it accepts (within the workspace's), and a size cap (never above the workspace's)."""
        from engine.files import AnyDetails, FileKind

        self._name(name)
        if name in self.file_kinds:
            raise ValueError("duplicate file kind")
        if details is not None and not issubclass(details, BaseModel):
            raise ValueError("file kind details must be a pydantic model")
        self.file_kinds[name] = FileKind(name, details or AnyDetails, tuple(accept), max_mb, label)

    def action(
        self, name: str, *, label: str, run: Callable, on: str | None = None, file_kinds: tuple[str, ...] = ()
    ) -> None:
        """Something the person starts: on a record of kind `on` (core or own; "file" with optional `file_kinds`), or
        on the workspace when `on` is None. `run(target, context, choices) -> Proposal` is deterministic work (it may
        run declared programs through `context.tools`); the person reviews the proposal, and what they approve
        applies as theirs. Raising StoreError or ToolError shows its message to the person; any other exception turns
        the plugin off."""
        self._name(name)
        if name in self.actions or not callable(run) or not label.strip():
            raise ValueError("duplicate action, missing label or invalid callback")
        if file_kinds and on != "file":
            raise ValueError("file_kinds applies only to actions on files")
        self.actions[name] = ActionRegistration(name, label.strip(), on, run, tuple(file_kinds))

    def text_format(self, name: str, units: Callable) -> None:
        """A long text format: `units(text) -> list[Unit]`, spans that cover the text exactly, in order, each with a
        kind and whether it is atomic (never split or merged). Pure and deterministic; the core checks the coverage.
        The core ships "plain" (blank-line paragraphs) and "markdown" (its blocks)."""
        self._name(name)
        if name in self.text_formats or not callable(units):
            raise ValueError("duplicate text format or invalid callback")
        self.text_formats[name] = units

    def lint(self, name: str, fn: Callable, *, ops: tuple[str, ...], severity: str = "warn") -> None:
        """A soft check on the assistant's proposals: `fn(op, view, settings) -> list[LintFinding]` runs on every op
        named in `ops` (core or own) before it applies. It must be deterministic and quick, and never call AI.
        `severity` is the default: "return" sends the findings back to the assistant for its fix round (one more try,
        then a stronger tier), "warn" shows them on the review, "off" skips it; the workspace's
        `config/checks.yaml` (`lints: {<plugin>/<name>: ...}`) overrides it. A lint never refuses: refusing is for
        invariants, which are validators."""
        self._name(name)
        if name in self.lints or not callable(fn) or not ops:
            raise ValueError("duplicate lint, invalid callback or no ops to check")
        if severity not in ("return", "warn", "off"):
            raise ValueError('a lint\'s default severity is "return", "warn" or "off"')
        self.lints[name] = LintRegistration(name, fn, tuple(ops), severity)

    def subscribe(self, event: str, fn: Callable) -> None:
        """Handle an event after the change behind it is committed: `fn(payload, context)` with an `EventContext`.
        One handler per event; route by `payload["kind"]` when it handles several kinds."""
        if event in self.handlers or not callable(fn):
            raise ValueError("duplicate subscription or invalid handler")
        self.handlers[event] = fn


__all__ = [
    "PLUGIN_API_VERSION",
    "Settings",
    "Record",
    "OpModel",
    "EvidenceIn",
    "ANY",
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
    "ActionContext",
    "LintFinding",
    "LongText",
    "Unit",
    "Part",
    "PacketParts",
    "Proposal",
    "NewFile",
    "Preview",
    "Choice",
    "Group",
    "Item",
    "Registrar",
    "StageDefinition",
    "StageCheckResult",
    "ToolBox",
    "ToolResult",
    "ToolError",
]
