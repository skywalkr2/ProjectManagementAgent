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
carry on. Today lines, interface items, event handlers and jobs are contained per call: a failing call is skipped and
noted, and the plugin is turned off only after `workspace.plugins.failures_before_off` failures in a row there.
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

PLUGIN_API_VERSION = "0.3.26"


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


def _data_path(path: str) -> str:
    from pathlib import PurePosixPath

    clean = PurePosixPath(path.replace("\\", "/"))
    if not path or clean.is_absolute() or ".." in clean.parts or re.match(r"^[A-Za-z]:", path):
        raise StoreError(f"{path!r} must be a relative path inside the plugin's data")
    return str(clean)


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
    #: Set by the host: the items of an interface this plugin uses.
    read_interface: Callable[..., list[Any]] | None = None
    #: Set by the host: the id of the person this workspace belongs to (the PM), when set up.
    user: str | None = None

    def person_name(self, person_id: str | None = None) -> str:
        """A person's display name (the workspace's own person when no id is given), for a byline or a signature;
        empty when there is no such person."""
        person = self.get("person", person_id or self.user or "")
        return person.data["full_name"] if person is not None else ""

    def interface(self, interface: str, /, *, project: Any = ANY) -> list[InterfaceItem]:
        """The items every running provider offers for an interface this plugin declares in `interfaces.uses`
        ("<name>@<major>[.<minor>]"), each checked against the interface's definition. With `project`, only items for
        that project. Items above the data levels this plugin declares are left out. Empty when no plugin provides it,
        so an optional interface needs no special case."""
        if self.read_interface is None:
            return []
        return self.read_interface(interface, project)

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
    #: Set by the host: the plugin's data layers, shipped first and the most specific last.
    data_layers: Callable[[str | None], list[Path]] | None = None

    def data(self, path: str, *, project: str | None = None) -> bytes | None:
        """A data file by relative path ("templates/classic.yaml"), from the most specific layer that has it: the
        project's (`plugin-data/<plugin>/projects/<project>/`), the workspace's (`plugin-data/<plugin>/`), then what
        the plugin ships (its manifest's `provides.data` folder). None when no layer has it. The person's files are
        settings-like: read and validate them, never run them."""
        rel = _data_path(path)
        for layer in reversed(self.data_layers(project) if self.data_layers else []):
            candidate = layer / rel
            if candidate.is_file() and candidate.resolve().is_relative_to(layer.resolve()):
                return candidate.read_bytes()
        return None

    def data_files(self, folder: str = "", *, project: str | None = None) -> list[str]:
        """Relative paths of the data files under a folder, across all layers, each once, sorted."""
        rel = _data_path(folder) if folder else ""
        found = set()
        for layer in self.data_layers(project) if self.data_layers else []:
            base = layer / rel if rel else layer
            if base.is_dir():
                for item in base.rglob("*"):
                    if item.is_file() and not item.is_symlink():
                        found.add(item.relative_to(layer).as_posix())
        return sorted(found)

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

    def text_version(self, record: Stored, field: str) -> Stored | None:
        """The `text_version` record of a long text field's current text (its latest accepted version), or None."""
        return self._text_version(record, field, None)

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
        self.emitted: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        """Raise an event of an interface this plugin provides ("<interface>.<event>"), published to the plugins
        that use it once the change commits. The payload is checked against the interface's definition."""
        checker = getattr(self, "check_emit", None)
        if checker is None:
            raise PluginMisuse("events can only be raised from an op")
        self.emitted.append((event, checker(event, payload)))

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

    def queue_request(
        self, task: str, note: str, about: Stored | tuple[str, str] | None = None, *, needs_go: bool = False
    ) -> None:
        """Queue AI work of one of this plugin's task kinds (or a core one). `about` is the record it works on, as a
        record or (kind, id), required for a task kind declared `on` a kind. The note reaches the assistant as
        untrusted material, and system ops from it wait for the person. After a stage move, or with `needs_go`, it
        waits for the person's go whatever it costs."""
        data: dict[str, Any] = {"task": task, "note": note}
        if needs_go:
            data["needs_go"] = True
        if about is not None:
            kind, record_id = (about.kind, about.id) if isinstance(about, Stored) else about
            self._allow(kind)
            data["about"] = {"kind": kind, "id": record_id}
        self.commands.append(("request", data))

    def request_from(
        self,
        interface: str,
        task: str,
        note: str,
        about: Stored | tuple[str, str] | None = None,
        *,
        provider: str | None = None,
        needs_go: bool = False,
        item: InterfaceItem | None = None,
    ) -> None:
        """Queue AI work another plugin offers through an interface this plugin uses: `task` is the interface's
        task kind name ("short-blurb"). It runs as that plugin's task, under its prompt and playbook, with the usual
        estimate, go and review (with `needs_go`, it waits for the go whatever it costs). `provider` picks one when
        several plugins offer it. The note is untrusted material. Name what the work is about with `about` (a record)
        or with `item` (an InterfaceItem read from `view.interface`): its provider then says which of its records the
        item stands for, and the work goes to that provider."""
        data: dict[str, Any] = {"via": interface, "interface_task": task, "note": note}
        if needs_go:
            data["needs_go"] = True
        if item is not None:
            if about is not None or not isinstance(item, InterfaceItem) or not item.key:
                raise PluginMisuse("name what the work is about with about= or with an item read from view.interface")
            data["item"] = item.key
            provider = provider or item.provider
        if provider is not None:
            data["provider"] = provider
        if about is not None:
            kind, record_id = (about.kind, about.id) if isinstance(about, Stored) else about
            data["about"] = {"kind": kind, "id": record_id}
        self.commands.append(("request", data))

    def apply_op(self, op: dict[str, Any]) -> None:
        """Stage one of this plugin's own ops (a dict, as in a Proposal), applied through the applier after this
        handler or job returns, as a changeset from the plugin the person sees and can undo: a check result, a
        record that something ran. It is treated like work from outside content: a system op, a person-only value
        or anything a validator refuses waits for the person or is refused; core ops can't be staged this way."""
        self.commands.append(("op", dict(op)))

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        """Raise an event of an interface this plugin provides ("<interface>.<event>"), after this handler returns,
        to the plugins that use it (for an event that follows a core change such as a stage move). The payload is
        checked against the interface's definition."""
        self.commands.append(("emit", {"event": event, "payload": dict(payload)}))

    def file_question(self, title: str, text: str = "") -> None:
        """File a question for the configured PM; sending is never part of handling an event."""
        self.commands.append(("question", {"title": title, "text": text}))


class PacketContext(ReadView):
    """The read view a task kind's packet function gets, with `origin`, who started the run: "pm" (the person, so the
    note is their own words), "input" (an outside input) or "schedule" (a schedule, a stage entry or a plugin's
    request). A note from anyone but the person is shown to the run as untrusted material."""

    def __init__(self, view: Any, plugin: str, origin: str):
        super().__init__(view, plugin)
        self.origin = origin


class ActionContext(ReadView):
    """What a person action sees: core and own records, file bytes, the plugin's settings and its declared programs.
    It changes nothing itself; it returns a Proposal the person reviews. `limits` holds the workspace's limits a
    proposal works within: max_items, max_previews, preview_mb, keep_minutes, max_file_mb, max_total_mb, room_mb
    (what is left of max_total_mb for new files) and accepted_types (media types files may have)."""

    def __init__(self, view: Any, plugin: str, config: Settings, tools: Any, limits: dict[str, Any] | None = None):
        super().__init__(view, plugin)
        self.config = config.model_copy(deep=True)
        self.tools = tools
        self.limits = dict(limits or {})


@dataclass
class Choice:
    """A named choice the person can flip on the review; the action runs again with the new value before anything
    applies. `options` are (value, label) pairs; none means on or off. `value` is the value the action used: the
    choices it was given can name a choice it no longer offers (dropped) or a value it no longer offers (report the
    value you fell back to). With `text=True` the person types the value (a name, a title), up to `max_length`
    characters; `value` is the default, and the action runs again with what was typed."""

    id: str
    label: str
    value: str | bool
    options: list[tuple[str, str]] = field(default_factory=list)
    help: str = ""
    group: str | None = None  # the id of a Group in the proposal's groups
    text: bool = False
    max_length: int = 200


@dataclass
class Group:
    """A heading and a short explanation shared by the choices and items under it, so a long review reads as a few
    groups with counts. A group has no value of its own: setting a whole group on screen sets each choice in it, and
    the action runs again with every one of those choice ids in `choices` (for example {"tone-ch1": "plain",
    "tone-ch2": "plain"}); keeping or dropping a whole group's items ticks each item, with no rerun."""

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
    """Something to look at on the review (an image the plugin rendered, or plain text). Shown, never saved or sent.
    `alt` describes an image for people who can't see it; without it, the caption is used."""

    name: str
    media_type: str
    data: bytes
    caption: str = ""
    alt: str = ""


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
    #: The ops only make sense together (an import): if any is refused when applied, none applies.
    all_or_nothing: bool = False
    #: AI work to queue when the person applies it: {"task": one of this plugin's task kinds, "about": (kind, id)
    #: or None, "note": ""}. Each waits for the person's go, whatever it costs.
    requests: list[dict[str, Any]] = field(default_factory=list)


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
class TakeBack:
    """What a working-copy format read back from a file: the whole text, and anything it couldn't map (a comment, a
    style it doesn't know), in plain words, shown beside the proposal and never dropped silently."""

    text: str
    unmapped: list[str] = field(default_factory=list)


class WorkingCopyContext(ReadView):
    """What a working-copy format sees: the record, the field, the version handed out, the language, the plugin's
    settings and its data files."""

    def __init__(self, view: Any, plugin: str, config: Settings, record: Stored, field: str, version: int | None):
        super().__init__(view, plugin)
        self.config = config.model_copy(deep=True)
        self.record, self.field, self.version = record, field, version


@dataclass
class TodayLine:
    """One line a plugin adds to Today: `text` is one plain line for the person (no internal terms); `about` is the
    record it is about, as (kind, id); `action` is the one thing to do from it, a person action or a task kind of
    this plugin's, on that record or the workspace; `why` and `until` say why it is waiting and until when, when it
    is. `id` is stable across calls, so the same line isn't shown twice."""

    id: str
    text: str
    about: tuple[str, str] | None = None
    action: str | None = None
    why: str = ""
    until: str | None = None  # an ISO date


@dataclass(frozen=True)
class TodayRegistration:
    """A registered Today contributor (host side)."""

    name: str
    lines: Callable


@dataclass(frozen=True)
class PanelRegistration:
    """A registered panel (host side)."""

    name: str
    title: str
    kind: str
    view: str
    columns: tuple[str, ...]
    filter: dict[str, Any]
    primary_action: str | None
    row_actions: tuple[str, ...]
    tab: str
    new_action: str | None = None


@dataclass(frozen=True)
class JobRegistration:
    """A registered job (host side)."""

    name: str
    every_minutes: int
    run: Callable


@dataclass(frozen=True)
class SetupStepRegistration:
    """A registered setup step (host side)."""

    name: str
    label: str
    explanation: str
    done: Callable
    action: str | None


@dataclass(frozen=True)
class InterfaceItem:
    """One item a provider offers through an interface: who provides it and its fields, as the definition shapes
    them. Read-only: it is a copy, never the provider's record. Put it in a packet with
    `Part(..., data_level=item.data_level)` so the run's account is allowed it."""

    provider: str
    data: dict[str, Any]
    key: str = ""  # the host's stable key for the item as the provider gave it; pass the item to request_from

    @property
    def data_level(self) -> str:
        return str(self.data.get("data_level") or "internal")


@dataclass(frozen=True)
class InterfaceDefinition:
    """A registered interface definition (host side)."""

    name: str
    version: str
    item: type[BaseModel]
    events: dict[str, type[BaseModel]]
    task_kinds: tuple[str, ...]

    @property
    def major(self) -> int:
        return int(self.version.split(".")[0])

    @property
    def minor(self) -> int:
        return int(self.version.split(".")[1])


@dataclass(frozen=True)
class InterfaceProvision:
    """A registered interface provider (host side)."""

    interface: str
    major: int
    items: Callable
    task_kinds: dict[str, str]
    about: Callable | None = None


@dataclass(frozen=True)
class DerivedFileRegistration:
    """A registered generated file (host side)."""

    name: str
    path: str
    depends_on: tuple[str, ...]
    render: Callable


@dataclass(frozen=True)
class WorkingCopyRegistration:
    """A registered working-copy format (host side)."""

    name: str
    label: str
    extension: str
    media_type: str
    text_formats: tuple[str, ...]
    hand_out: Callable
    take_back: Callable


@dataclass
class Part:
    """One piece of what an AI run sees, in a task kind's packet. Untrusted content (the default; `trusted` only for the
    person's own words) is marked in the packet as material, never instructions, and any untrusted part makes the run's
    changeset untrusted, so its system ops wait for the person. A `reference_only` part informs the run but is marked
    not to be quoted or reproduced. Evidence may quote any part that isn't reference-only, and is cited as
    "<kind>:<id>" of the record the run is about. `no_copy` marks material the run may describe and quote as evidence
    (in a finding) but must not copy into new text, such as a character's entry. `data_level` marks content more
    sensitive than the record the
    run is about (an interface item's level, say): the run goes only to accounts allowed the highest level among
    the record and its parts."""

    title: str
    text: str
    trusted: bool = False
    reference_only: bool = False
    data_level: str | None = None
    no_copy: bool = False


@dataclass
class PacketParts:
    """What a run of a plugin's task kind sees beyond its instructions. `stable` parts are the same on every run of the
    kind for the same record (a style sheet, the summaries around a chapter) and go first, so providers can reuse a
    cached prefix; `request` parts are this run's material (the chapter) and go last."""

    stable: list[Part] = field(default_factory=list)
    request: list[Part] = field(default_factory=list)


def _narrowed(where: dict[str, Any] | None, on: str | None) -> dict[str, tuple[Any, ...]]:
    """A `where` filter as {field: (values...)}, checked to be plain values on a record kind."""
    if where is not None and (on is None or not where):
        raise ValueError("where narrows the records of kind `on`; it needs `on` and at least one field")
    narrowed = {}
    for key, value in (where or {}).items():
        values = tuple(value) if isinstance(value, (list, tuple, set, frozenset)) else (value,)
        if not values or not all(v is None or isinstance(v, (str, int, float, bool)) for v in values):
            raise ValueError("where matches fields against plain values")
        narrowed[str(key)] = values
    return narrowed


@dataclass(frozen=True)
class ActionRegistration:
    """A registered person action (host side)."""

    name: str
    label: str
    on: str | None
    run: Callable
    file_kinds: tuple[str, ...] = ()
    where: dict[str, tuple[Any, ...]] = field(default_factory=dict)

    def offered_on(self, record: Any) -> bool:
        """Whether this action applies to a record (of kind `on`): every `where` field holds one of its values."""
        return all(record.data.get(key) in values for key, values in self.where.items())


@dataclass(frozen=True)
class OpRegistration:
    """A registered op (host side)."""

    model: type[OpModel]
    tier: Tier
    apply: Callable
    writes: dict[str, tuple[str, ...]]
    notes: bool = False


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
        self.working_copies: dict[str, WorkingCopyRegistration] = {}
        self.derived_files: dict[str, DerivedFileRegistration] = {}
        self.interface_definitions: dict[str, InterfaceDefinition] = {}
        self.today_lines: dict[str, TodayRegistration] = {}
        self.panels: dict[str, PanelRegistration] = {}
        self.jobs: dict[str, JobRegistration] = {}
        self.setup_steps: dict[str, SetupStepRegistration] = {}
        self.connectors: dict[str, Any] = {}
        self.triage_matchers: dict[str, Callable] = {}
        self.interface_provisions: dict[str, InterfaceProvision] = {}

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

    def op(self, model: type[OpModel], tier: Tier, apply: Callable, *, notes: bool = False) -> None:
        """Register an op: an `OpModel` subclass with a single literal `op` id and a `writes` class variable mapping
        own record kinds to the fields it may change (`("*",)` to create or delete). `tier` is "data" or "system"
        (system ops from the assistant wait for the person). `apply(op, writer, settings)` makes the change through
        the `OpWriter`; raising StoreError refuses this op only. With `notes=True` the op is also offered to the
        core's reading of notes, so the assistant can use it on what the person hands in: give it an `EvidenceIn`
        field, which the core checks against the input, for anything it claims."""
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
        self.ops[name] = OpRegistration(model, tier, apply, writes, bool(notes))

    def op_validator(self, op_name: str, fn: Callable) -> None:
        """Check a core or own op before it applies: `fn(op, view, origin)` (or `fn(op, view)`; `origin` may also be
        keyword-only) returns a list of refusal messages, empty to let it through. The view is the changeset so far.
        `origin` is {"actor": "pm" | "assistant" | "rule", "trust": "trusted" | "untrusted", "via": "screen" | "note" |
        "input" | "task" | "rule" | "action", "task": the run's task kind, "about": the record it works on as
        {"kind", "id"} or None}. Before anything applies, the core dry-runs the whole changeset in order
        (text writes included) and rolls it back, so a validator sees what earlier ops in it created; with the check
        at the write boundary, a validator usually runs about three times per op, so it must be pure and quick."""
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
        anchored: bool = False,
        questions: int = 0,
        where: dict[str, Any] | None = None,
        role: str = "write",
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
        what the run sees (without it, the run sees what reading notes sees); `view` is a PacketContext, whose `origin`
        says who started the run. It runs before every call, so it must be deterministic and quick; raising StoreError
        stops the run with that message for the person. `where` narrows which records of kind `on` the work is
        offered on and may start on: {field: value} or {field: (value, ...)}, every field matching.

        `output` is "ops" (the answer is a changeset of `ops`) or "draft": the answer is plain prose for the long text
        field `field` of the record the run is about (`on` is required). The core wraps it as a pending `text.draft`
        version for the person's review, runs lints on it (lints on the op "text.draft"), sends a "return" finding
        back for one fix round, and continues a draft cut off at the output limit once before holding it. With
        `anchored=True` the draft revises the current text: the run sees it with an id on each unit, starts every
        paragraph it writes with the ids it came from, and a core check refuses a draft that leaves a unit unaccounted
        for, names an unknown id, or splits or merges an atomic unit; the paragraph map is kept with the version.
        `questions=N` lets a draft end with up to N questions for the person, in a `<questions>` block the core takes
        off the text and keeps on the version (`questions`), shown beside it; more than N gets a fix round.

        `role` is "write" (the default: work that writes or changes things), "check" (an independent second opinion on
        work already done) or "research" (gathering from sources). The workspace maps roles to tiers (`ai.roles`). A
        check never runs on an account that wrote the record it is about (its accepted and pending text versions and
        the changes AI runs made to it), unless the person accepts the same account for checks; the run then records
        which kind of independence it had (`Run.independence`). With no account to take it, the check waits for the
        person and says why. The packet decides what a check sees: give it the work, never the writing run's own
        material.

        `tier`, `max_output` (the most tokens an answer may use), `expected_output` (typical answer size, for estimates
        before there are past runs) and `temperature` are defaults; the workspace's `ai.tasks.<kind>` overrides them."""
        from engine.config.schema import TaskSettings

        self._name(name)
        if output not in ("ops", "draft"):
            raise ValueError('a task kind\'s output is "ops" or "draft"')
        if (anchored or questions) and output != "draft":
            raise ValueError("only a draft task kind is anchored or asks questions")
        if role not in ("write", "check", "research"):
            raise ValueError('a task kind\'s role is "write", "check" or "research"')
        if not isinstance(questions, int) or not 0 <= questions <= 20:
            raise ValueError("questions is how many a draft may ask, from 0 to 20")
        narrowed = _narrowed(where, on)
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
            anchored=anchored,
            questions=questions,
            where=narrowed,
            role=role,
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
        self,
        name: str,
        *,
        label: str,
        run: Callable,
        on: str | None = None,
        file_kinds: tuple[str, ...] = (),
        where: dict[str, Any] | None = None,
    ) -> None:
        """Something the person starts: on a record of kind `on` (core or own; "file" with optional `file_kinds`), or
        on the workspace when `on` is None. `where` narrows the records of kind `on` it is offered on and may run on,
        as for task kinds: {field: value} or {field: (value, ...)}, every field matching. `run(target, context,
        choices) -> Proposal` is deterministic work (it may run declared programs through `context.tools`); the person
        reviews the proposal, and what they approve applies as theirs. Raising StoreError or ToolError shows its
        message to the person; any other exception turns the plugin off."""
        self._name(name)
        if name in self.actions or not callable(run) or not label.strip():
            raise ValueError("duplicate action, missing label or invalid callback")
        if file_kinds and on != "file":
            raise ValueError("file_kinds applies only to actions on files")
        self.actions[name] = ActionRegistration(name, label.strip(), on, run, tuple(file_kinds), _narrowed(where, on))

    def text_format(self, name: str, units: Callable) -> None:
        """A long text format: `units(text) -> list[Unit]`, spans that cover the text exactly, in order, each with a
        kind and whether it is atomic (never split or merged). Pure and deterministic; the core checks the coverage.
        The core ships "plain" (blank-line paragraphs) and "markdown" (its blocks)."""
        self._name(name)
        if name in self.text_formats or not callable(units):
            raise ValueError("duplicate text format or invalid callback")
        self.text_formats[name] = units

    def working_copy(
        self,
        name: str,
        *,
        label: str,
        extension: str,
        media_type: str,
        hand_out: Callable,
        take_back: Callable,
        text_formats: tuple[str, ...] = (),
    ) -> None:
        """A file format people edit long text in with their own tools. `hand_out(text, context) -> bytes` makes the
        file from a version; `take_back(data, base_text, context) -> TakeBack` reads a file back, given the text of the
        version it was handed out from. Both are deterministic, with no AI; anything take_back can't map goes in
        `unmapped`, never dropped. Handing out an untouched file and taking it back must give the same text: the core
        reads every file back as it hands it out, and refuses to hand out one that doesn't. A
        returned file becomes a `text.propose` made from the handed-out version, so the review is three-way when the
        text moved on. `text_formats` limits it to long text in those formats (empty: any). The media type must be
        one the workspace accepts (storage.files.accepted_types)."""
        self._name(name)
        if name in self.working_copies or not callable(hand_out) or not callable(take_back) or not label.strip():
            raise ValueError("duplicate working-copy format, missing label or invalid callback")
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", extension):
            raise ValueError("a working-copy extension is like .docx")
        self.working_copies[name] = WorkingCopyRegistration(
            name, label.strip(), extension, media_type, tuple(text_formats), hand_out, take_back
        )

    def define_interface(
        self,
        name: str,
        *,
        version: str,
        item: type[BaseModel],
        events: dict[str, type[BaseModel]] | None = None,
        task_kinds: tuple[str, ...] = (),
    ) -> None:
        """Define a versioned interface other plugins provide or use (listed in `interfaces.defines`): `item` is the
        pydantic model of one item, `events` the events providers raise with their payload models, and `task_kinds`
        the work a provider may offer for others to request. `version` is "<major>.<minor>": add only optional
        fields within a major version, and bump the major to change anything else. A plugin that defines an interface
        may also provide and use it."""
        self._name(name)
        if name in self.interface_definitions:
            raise ValueError("duplicate interface definition")
        if not re.fullmatch(r"[0-9]+\.[0-9]+", version):
            raise ValueError('an interface version is "<major>.<minor>", like "1.0"')
        if not isinstance(item, type) or not issubclass(item, BaseModel):
            raise ValueError("an interface's item is a pydantic model")
        for event, model in (events or {}).items():
            if (
                not re.fullmatch(r"[a-z][a-z0-9_]*", event)
                or not isinstance(model, type)
                or not issubclass(model, BaseModel)
            ):
                raise ValueError("interface events are lowercase names with pydantic payload models")
        for kind in task_kinds:
            if not re.fullmatch(r"[a-z][a-z0-9-]*", kind):
                raise ValueError("an interface's task kinds are short lowercase names like short-blurb")
        self.interface_definitions[name] = InterfaceDefinition(
            name, version, item, dict(events or {}), tuple(task_kinds)
        )

    def provide_interface(
        self,
        interface: str,
        *,
        items: Callable,
        task_kinds: dict[str, str] | None = None,
        about: Callable | None = None,
    ) -> None:
        """Provide an interface ("<name>@<major>", listed in `interfaces.provides`), defined here or by another
        plugin. `items(view, settings, project) -> list[dict]` returns what this plugin offers through it: for one
        project when `project` is an id, everything when it is None (a function taking only `view, settings` is
        called for everything and filtered). Each item is checked against the definition when read; include
        `project` (an id) for items that belong to one, and `data_level` when it isn't "internal". It must be quick
        and deterministic. `task_kinds` maps the interface's task kind names to this plugin's own task kinds, so
        others can request them. `about(view, settings, item) -> record | (kind, id) | None` says which of this
        plugin's records an item (as `items` returned it) stands for, so a user can request work on the item itself;
        the record must be of the kind the requested task kind is `on`. Raise the interface's events from an op with
        `writer.emit`, or from an event handler with `context.emit`. With no plugin defining the interface running,
        nothing reads it."""
        match = re.fullmatch(r"([a-z0-9-]+/[a-z0-9-]+)@([0-9]+)", interface)
        if match is None:
            raise ValueError('provide an interface as "<plugin>/<name>@<major>"')
        if match.group(1) in self.interface_provisions or not callable(items):
            raise ValueError("duplicate interface provision or invalid items function")
        for own in (task_kinds or {}).values():
            if not own.startswith(self.name + "/"):
                raise ValueError("an interface offers this plugin's own task kinds")
        if about is not None and not callable(about):
            raise ValueError("an interface's about is a function")
        self.interface_provisions[match.group(1)] = InterfaceProvision(
            match.group(1), int(match.group(2)), items, dict(task_kinds or {}), about
        )

    def today(self, name: str, *, lines: Callable) -> None:
        """Lines for the Today list (listed in `provides.today`): `lines(view, settings) -> list[TodayLine]`, called
        whenever Today is shown, so it must be quick and deterministic and never call AI. A line's `action` must be
        one of this plugin's person actions or task kinds."""
        self._name(name)
        if name in self.today_lines or not callable(lines):
            raise ValueError("duplicate Today contributor or invalid lines function")
        self.today_lines[name] = TodayRegistration(name, lines)

    def panel(
        self,
        name: str,
        *,
        title: str,
        kind: str,
        columns: tuple[str, ...],
        view: str = "table",
        filter: dict[str, Any] | None = None,
        primary_action: str | None = None,
        row_actions: tuple[str, ...] = (),
        tab: str = "work",
        new_action: str | None = None,
    ) -> None:
        """A screen listing records (listed in `provides.panels`), described as data so it looks and behaves like
        the core's (design 7.2): the records of `kind` (core or own) whose fields equal `filter`, shown as `view`
        ("list", "table" or "board"; a board groups by the first column) with `columns` (fields of the kind).
        `primary_action` is the one action on a row and `row_actions` the rest, in its menu: this plugin's person
        actions or task kinds on that kind. `new_action` is a person action of this plugin's on the workspace (`on`
        None) shown above the rows, to add one. Rows are read through the core, and actions run as they always do."""
        self._name(name)
        if name in self.panels or not title.strip() or not columns:
            raise ValueError("duplicate panel, missing title or no columns")
        if view not in ("list", "table", "board"):
            raise ValueError('a panel view is "list", "table" or "board"')
        if tab not in ("today", "work", "people", "settings"):
            raise ValueError('a panel tab is "today", "work", "people" or "settings"')
        self.panels[name] = PanelRegistration(
            name,
            title.strip(),
            kind,
            view,
            tuple(columns),
            dict(filter or {}),
            primary_action,
            tuple(row_actions),
            tab,
            new_action,
        )

    def job(self, name: str, *, every_minutes: int, run: Callable) -> None:
        """Work on a schedule (listed in `provides.jobs`): `run(context)` with an `EventContext`, every
        `every_minutes` by default; the workspace changes it or turns the job off in
        `workspace.plugins.jobs.<name>`. Like an event handler it reads, queues requests, files questions, raises
        interface events and stages its own ops; it never writes records directly and never calls AI itself. It runs
        only while the app runs, and each run is recorded."""
        self._name(name)
        if name in self.jobs or not callable(run) or not isinstance(every_minutes, int) or every_minutes < 5:
            raise ValueError("duplicate job, invalid run function, or a schedule under 5 minutes")
        self.jobs[name] = JobRegistration(name, every_minutes, run)

    def connector(self, name: str, *, label: str, settings: type[BaseModel], poll: Callable) -> None:
        """A place the assistant can keep reading (listed in `provides.connectors`). A workspace watches it by naming
        it in `watch.yaml` with its settings, which `settings` (a pydantic model) checks. `poll(settings, state,
        context) -> Poll` lists what the source holds now as `SourceItem`s (a stable key, a title, the text, who
        changed it last) and returns the `state` to keep for the next read; set `complete=False` when it lists only
        what changed.
        Raise `ConnectorError(kind, detail)` with kind `auth`, `no_access`, `not_found`, `outage` or `offline`. The
        core compares, keeps snapshots and hands in what is new, changed or gone; the connector never writes
        records. It must not reach the network until `requires.network` is available."""
        self._name(name)
        if name in self.connectors or not callable(poll):
            raise ValueError("duplicate connector or invalid poll function")
        if not isinstance(settings, type) or not issubclass(settings, BaseModel):
            raise ValueError("a connector's settings are a pydantic model")
        from engine.connectors import Connector

        self.connectors[name] = Connector(name, " ".join(str(label).split()) or name, settings, poll)

    def triage_matcher(self, name: str, *, match: Callable) -> None:
        """A rule kind for triage in `watch.yaml` (listed in `provides.triage_matchers`): `match(change, params) ->
        reason | None` closes a watched change before the assistant reads it when it returns a reason in plain words.
        `change` has source, key, title, change (new, changed or removed), author, before, now, added and removed
        (lines) and our_accounts; `params` are the rule's own. Deterministic and quick; it never calls AI. The person
        sees what it closed and why, and can take a closer look."""
        self._name(name)
        if name in self.triage_matchers or not callable(match):
            raise ValueError("duplicate triage matcher or invalid match function")
        self.triage_matchers[name] = match

    def setup_step(
        self, name: str, *, label: str, done: Callable, explanation: str = "", action: str | None = None
    ) -> None:
        """A step of the first-run setup (listed in `provides.setup_steps`), shown after the core's steps: `label` says
        what to do in a few words, `explanation` why, and `done(view, settings) -> bool` whether it is done, called
        whenever setup is shown, so it must be quick and deterministic. `action` is one of this plugin's person
        actions on the workspace, offered as the step's button; without one, the step points to the plugin's
        settings. The person can skip it and come back to it later."""
        self._name(name)
        label = " ".join(str(label).split())
        if name in self.setup_steps or not callable(done) or not label or len(label) > 80:
            raise ValueError("duplicate setup step, invalid done function, or a label that isn't one short line")
        self.setup_steps[name] = SetupStepRegistration(name, label, " ".join(str(explanation).split()), done, action)

    def derived_file(self, name: str, *, path: str, depends_on: tuple[str, ...], render: Callable) -> None:
        """A read-only file generated from records into each project's folder in the synced folder (an overview, a
        sheet of facts). `path` is relative to the project's folder, with an extension ("views/overview.md").
        `render(project, view, settings) -> str | None` makes its text for one project; None writes nothing. It runs
        for every project that has records of a kind in `depends_on` (core or own; "project" means every project),
        each time the folder is written, so it must be pure and quick and never call AI. The file is marked
        generated: an edit made outside is reported and overwritten, never proposed or loaded."""
        from engine.sync import check_derived_path

        self._name(name)
        if name in self.derived_files or not callable(render) or not depends_on:
            raise ValueError("duplicate generated file, invalid render function or nothing it depends on")
        check_derived_path(path)
        self.derived_files[name] = DerivedFileRegistration(name, path, tuple(depends_on), render)

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


from engine.connectors import ConnectorError, Poll, SourceItem  # noqa: E402 - part of the plugin API

__all__ = [
    "ConnectorError",
    "Poll",
    "SourceItem",
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
    "TakeBack",
    "WorkingCopyContext",
    "InterfaceItem",
    "TodayLine",
    "PacketContext",
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
