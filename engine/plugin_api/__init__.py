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

To try a plugin without touching a real workspace, run `cockpit demo --plugin <its folder>`: it makes (or reuses) a
demo workspace of made-up data, links the plugin folder into it, turns the plugin on and serves it. Edits show after a
restart; `--fresh` starts the demo over, and an installed plugin is named instead of its folder.

For a plugin's own tests, install the host from its repository without the web screens, which need npm to build:
`PM_COCKPIT_WITHOUT_SCREENS=1 uv pip install "pm-cockpit @ git+<the host's repository address>@<branch or tag>"`.
Test connectors with `engine.plugin_api.testing` (see Connectors), never the host's internals.

One distribution may ship several plugins. They may share a helper package of their own (a module neither plugin
registers from); what a plugin may not do is import another plugin's registered package or read its records.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.config.schema import StageDefinition, TypeStages
from engine.ops import EvidenceIn, OpModel, Tier
from engine.records import InList, Record, RefTo, ref_fields, values_at
from engine.storage import Stored, StoreError, WriteContext
from engine.tasks import TaskKind
from engine.texts import LongText, Unit
from engine.tools import ToolBox, ToolError, ToolResult

PLUGIN_API_VERSION = "0.3.72"


class Settings(BaseModel):
    """Base for a plugin's settings, read from `config/plugins/<plugin>.yaml`. Every field needs a default and a
    description; unknown keys are refused. Handlers and actions get a copy as `context.config`. A field may be a nested
    model (shown as its own section on the Settings screen; keep it to one level) and may use an alias when its name
    in the file can't be a Python name."""

    model_config = ConfigDict(extra="forbid", validate_default=True)
    version: Literal[1] = Field(1, description="Settings format version.")

    @model_validator(mode="before")
    @classmethod
    def _renamed(cls, data: Any) -> Any:
        """Read a key under its old name for a field declaring `json_schema_extra={"renamed_from": "<old>"}` (or a
        list of old names): the value moves to the new name unless the new one is set, and the old key is dropped.
        Saving the add-on's settings on the Settings screen writes the new name; `renamed_keys(data)` says which old
        names a file still uses."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name, old in cls.renamed_keys(data):
            value = data.pop(old)
            data.setdefault(name, value)
        return data

    @classmethod
    def renamed_keys(cls, data: Any) -> list[tuple[str, str]]:
        """(new name, old name) for every old name a settings mapping still uses."""
        found = []
        for name, info in cls.model_fields.items():
            extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
            olds = extra.get("renamed_from") or ()
            for old in [olds] if isinstance(olds, str) else list(olds):
                if isinstance(data, dict) and old in data and old not in cls.model_fields:
                    found.append((info.alias or name, old))
        return found


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

    def list(
        self,
        kind: str,
        /,
        *,
        project: Any = ANY,
        ancestors: bool = False,
        descendants: bool = False,
        **equals: Any,
    ) -> list[Stored]:
        """Live records of a kind, optionally only those in one project (`project=None` for records in no project) or
        with given field values, matched exactly (case-sensitive) in the database. An unknown field is refused. The
        kind is positional, so a field called `kind` can be matched too. With a project id, `ancestors=True` also
        takes records in the projects above it (its parent, the parent's parent: a series a book belongs to) and
        `descendants=True` those in every project below it; the project's own come first, then nearest first."""
        self._allow(kind)
        if project is not ANY and (ancestors or descendants):
            if not isinstance(project, str):
                raise PluginMisuse("ancestors and descendants need a project id")
            found = []
            for pid in self._family(project, ancestors, descendants):
                found += self.__view.find(kind, {**equals, "project": pid})
            return found
        if project is not ANY:
            equals = {**equals, "project": project}
        return self.__view.find(kind, equals) if equals else self.__view.list(kind)

    def _family(self, project: str, ancestors: bool, descendants: bool) -> list[str]:
        """The project, then its ancestors nearest first, then its descendants nearest first; each once."""
        order = [project]
        if ancestors:
            at = self.__view.get("project", project)
            while at is not None and at.data.get("parent") and at.data["parent"] not in order:
                order.append(at.data["parent"])
                at = self.__view.get("project", at.data["parent"])
        if descendants:
            level = [project]
            while level:
                below = [
                    p.id for pid in level for p in self.__view.find("project", {"parent": pid}) if p.id not in order
                ]
                order += below
                level = below
        return order

    #: Set by the host: reads a file's bytes by id, checked against its hash.
    read_file: Callable[[str], bytes] | None = None
    #: Set by the host: the items of an interface this plugin uses.
    read_interface: Callable[..., list[Any]] | None = None
    find_interface_about: Callable[..., Any] | None = None
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

    def interface_about(self, item: Any, task: str) -> tuple[str, str] | None:
        """The record a request for `task` (the interface's task name) about this InterfaceItem would work on, as
        (kind, id), or None when its provider has none or the work isn't offered on it; check before
        `request_from(..., item=item)` to avoid a refusal."""
        if self.find_interface_about is None:
            return None
        return self.find_interface_about(item, task)

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

    #: Set by the host: a record's place in the effective stages.
    stage_status_of: Callable[[Stored], StageStatus | None] | None = None

    def stage_status(self, record: Stored) -> StageStatus | None:
        """Where a record of a core kind or this plugin's own stands in the workspace's effective stages, with the
        next stage's entry checks run now; None for a kind with no stages. Not available inside a stage check, which
        is itself part of this answer (it raises PluginMisuse there)."""
        self._allow(record.kind)
        if self.stage_status_of is None:
            return None
        return self.stage_status_of(record)

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
            for field in model.person_only:
                if field in data and model.needs_person(field, data[field]):
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
        self,
        task: str,
        note: str,
        about: Stored | tuple[str, str] | None = None,
        *,
        needs_go: bool = False,
        part: dict[str, Any] | None = None,
    ) -> None:
        """Queue AI work of one of this plugin's task kinds (or a core one). `about` is the record it works on, as a
        record or (kind, id), required for a task kind declared `on` a kind. The note reaches the assistant as
        untrusted material, and system ops from it wait for the person. After a stage move, or with `needs_go`, it
        waits for the person's go whatever it costs.

        `part` limits a draft to part of its long text. For an anchored draft, `{"first": n, "last": m}`: the run
        sees and must account for paragraphs p<n>..p<m> only (numbered as in the whole text), and the pending version
        is the whole text with that span replaced. For any other draft, `{"after": n}` (0 for the start, "end" for
        the end): the run writes only new text, and the pending version is the text with it added there. Add
        `"base": <version number>` so a text that moved on since the part was chosen refuses the run instead of
        revising the wrong paragraphs. The packet function adds whatever read-only context the run needs."""
        data: dict[str, Any] = {"task": task, "note": note}
        if needs_go:
            data["needs_go"] = True
        if part is not None:
            data["part"] = dict(part)
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
    request). A note from anyone but the person is shown to the run as untrusted material. `request` is the run's
    request id and `part` the part of the record it names (as given to `queue_request(part=)`), or None."""

    def __init__(
        self, view: Any, plugin: str, origin: str, request: str | None = None, part: dict[str, Any] | None = None
    ):
        super().__init__(view, plugin)
        self.origin = origin
        self.request = request
        self.part = dict(part) if part else None

    #: Set by the host: builds the knowledge section for `knowledge`.
    read_knowledge: Callable[[str, list[str]], KnowledgeParts] | None = None

    def knowledge(self, text: str = "", *, projects: Sequence[str] = ()) -> KnowledgeParts:
        """What the workspace has learned that applies to this run, as two parts the packet places: the standing
        rules, the lessons for this task kind and a small glossary (the `stable` part, the same for every run of the
        kind), and the rules, lessons, routing, glossary terms and facts that depend on this run (the `per_input`
        part). Put `stable` in `PacketParts.stable` and `per_input` in `PacketParts.request`; the core logs on the
        run what the parts gave it, as for its own tasks, and refuses a packet that puts a part in the wrong list.
        `text` is the words that decide which terms and facts apply (a chapter's text, say); it is only read, never
        sent. The run's projects are the request's project and the one the record is in; `projects` adds others. A
        rule or lesson whose scope excludes every one of them is left out, and lessons and rules aimed at this task
        kind (by its `<plugin>/<name>`) reach it. For work declared `learning` "own" (a task kind, or the record type
        it works on), facts are left out and no names are matched against people. A packet that never calls this gets
        nothing new."""
        if not isinstance(text, str):
            raise PluginMisuse("the text knowledge is chosen by must be a string")
        named = list(projects) if isinstance(projects, (list, tuple)) else None
        if named is None or not all(isinstance(p, str) for p in named):
            raise PluginMisuse("projects must be a list of project ids")
        if self.read_knowledge is None:
            return KnowledgeParts(
                KnowledgePart("Knowledge", "", True, section="stable"), KnowledgePart("Knowledge", "")
            )
        return self.read_knowledge(text, named)


class ActionContext(ReadView):
    """What a person action sees: core and own records, file bytes, the plugin's settings and its declared programs.
    It changes nothing itself; it returns a Proposal the person reviews. `limits` holds the workspace's limits a
    proposal works within: max_items (items offered to keep or drop), max_requests (entries in `Proposal.requests`),
    max_previews, preview_mb, keep_minutes, max_file_mb, max_total_mb, room_mb (what is left of max_total_mb for new
    files) and accepted_types (media types files may have). `now` (aware) and
    `today` are the workspace's clock in its time zone, so an action that stamps a date stays deterministic in tests."""

    def __init__(
        self,
        view: Any,
        plugin: str,
        config: Settings,
        tools: Any,
        limits: dict[str, Any] | None = None,
        now: datetime | None = None,
        estimator: Callable[..., float | None] | None = None,
    ):
        super().__init__(view, plugin)
        self.config = config.model_copy(deep=True)
        self.tools = tools
        self.limits = dict(limits or {})
        self.now = now or datetime.now(UTC)
        self.today = self.now.date()
        self._estimator = estimator
        self._own = plugin

    def estimate(self, task: str, input_tokens: int, output_tokens: int | None = None) -> float | None:
        """What one run of a task kind (core or this plugin's own) would cost in USD with this many tokens read (and
        written: by default its typical answer), priced on the account it would use first, as the request's go will
        price it. None when the price isn't known (a subscription or a local model) or no account takes the work.
        Sum it over the runs an action queues to say what the whole series would cost; each run still waits for the
        person's go."""
        if "/" in task and not task.startswith(self._own + "/"):
            raise PluginMisuse("an action estimates core work or its own plugin's")
        if self._estimator is None:
            return None
        return self._estimator(task, int(input_tokens), None if output_tokens is None else int(output_tokens))


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
    #: A few words naming what it is about, for its title on Today and What changed (cut at a word to 60 characters).
    topic: str = ""
    files: list[NewFile] = field(default_factory=list)
    previews: list[Preview] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)  # applied only while kept
    groups: list[Group] = field(default_factory=list)
    #: The ops only make sense together (an import): if any is refused when applied, none applies.
    all_or_nothing: bool = False
    #: AI work to queue when the person applies it: {"task": one of this plugin's task kinds, "about": (kind, id)
    #: or None, "note": "", "part": the part of a text it is about, "group": a group id}. Each waits for the
    #: person's go, whatever it costs. The person keeps or drops each one on the review (a request in a group is
    #: set with its group); one about an item is dropped with that item. A group stays on the review while it has
    #: items, choices or requests, even when all are dropped, so the person can keep them again; dropping them all
    #: queues nothing for it. An item's ops can't name a record a main op creates by id: they apply after the main
    #: ops in the same transaction, so an own op's `apply` finds that record by its natural key (`writer.find`).
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


#: The core's own actions a Today line may offer, with the kind of record each needs as `about` (None: any).
CORE_LINE_ACTIONS: dict[str, str | None] = {
    "open": None,  # open the record
    "review": None,  # review what waits on it: the assistant's answer (a changeset) or a draft on the record
    "go": "request",  # give the go to a queued run that waits for it
    "answer": "question",  # answer a question
    "move-stage": None,  # move the record to its next stage (a kind with stages)
}


@dataclass
class TodayLine:
    """One line a plugin adds to Today: `text` is one plain line for the person (no internal terms); `about` is the
    record it is about, as (kind, id); `action` is the one thing to do from it: a person action or a task kind of
    this plugin's, on that record or the workspace, or one of the core's own (`CORE_LINE_ACTIONS`): "open" the
    record, "review" what waits on it (the assistant's answer as a `changeset`, or a draft on the record), give the
    "go" to a queued `request`, "answer" a `question`, or "move-stage" (a kind with stages). A core action needs
    `about`. `why` and `until` say why it is waiting and until when, when it is. `id` is stable across calls, so the
    same line isn't shown twice."""

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
    computed: dict[str, Callable] = field(default_factory=dict)
    show_for: Callable | None = None
    render: Callable | None = None  # a document panel's `render(view, settings, project)`


@dataclass(frozen=True)
class DataFormRegistration:
    """A registered kind of data file the screens edit through a form (host side)."""

    name: str
    label: str
    folder: str
    schema: type[BaseModel]
    description: str = ""
    pattern: str = "*.yaml"
    single: bool = False


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
    settings: dict[str, Any] = field(default_factory=dict)


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
    "<kind>:<id>" of the record the run is about. `reference_only` is the stricter mark: it implies `no_copy`, and the
    part may not be cited either. `no_copy` marks material the run may describe and quote as evidence
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
class KnowledgePart(Part):
    """A `Part` made by `view.knowledge`: text the core wrote, shown as it is (its own headings, entries from outside
    content marked as data) and never quotable as evidence. `section` says which list of `PacketParts` it belongs
    in."""

    section: str = "per_input"
    _given: Any = field(default=None, repr=False, compare=False)


@dataclass
class KnowledgeParts:
    """The two parts `view.knowledge` returns: `stable` for `PacketParts.stable` and `per_input` for
    `PacketParts.request`. Either text may be empty, when nothing applies; an empty part is left out of the packet."""

    stable: Part
    per_input: Part


@dataclass
class PacketParts:
    """What a run of a plugin's task kind sees beyond its instructions. `stable` parts are the same on every run of the
    kind for the same record (a style sheet, the summaries around a chapter) and go first, so providers can reuse a
    cached prefix; `request` parts are this run's material (the chapter) and go last. `max_output` and
    `expected_output` (tokens) size this run when its record says how long the answer will be (a planned word count);
    the estimate and the call use them unless the workspace sets them for the task kind in `ai.tasks`."""

    stable: list[Part] = field(default_factory=list)
    request: list[Part] = field(default_factory=list)
    max_output: int | None = None
    expected_output: int | None = None


def _narrowed(where: dict[str, Any] | None, on: str | None) -> dict[str, tuple[Any, ...]]:
    """A `where` filter as {field: (values...)}, checked to be plain values on a record kind."""
    if where is not None and (on is None or not where):
        raise ValueError("where narrows the records of kind `on`; it needs `on` and at least one field")
    narrowed = {}
    for key, value in (where or {}).items():
        values = tuple(value) if isinstance(value, (list, tuple, set, frozenset)) else (value,)
        if not values or not all(v is None or v is ANY or isinstance(v, (str, int, float, bool)) for v in values):
            raise ValueError("where matches fields against plain values, ANY (has a value) or None (has none)")
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

    def offered_on(self, record: Any, texts: Callable[[str], bool | None] | None = None) -> bool:
        """Whether this action applies to a record (of kind `on`): every `where` field holds one of its values."""
        from engine.tasks import where_matches

        return where_matches(self.where, record, texts)


@dataclass(frozen=True)
class OpRegistration:
    """A registered op (host side)."""

    model: type[OpModel]
    tier: Tier
    apply: Callable
    writes: dict[str, tuple[str, ...]]
    notes: bool = False
    candidates: Callable | None = None


@dataclass(frozen=True)
class StageCheckResult:
    """What a stage check returns: whether the item may enter the stage, and why, in plain words for the person."""

    passed: bool
    reason: str


class SetupState(frozenset):
    """What a setup step's `done` can see beyond records, as its third argument. It is the set of the plugin's
    declared secrets that are set (names only, never values), so `"client-id" in state` works; it also carries
    `settings`, the effective values of the core settings the step suggests, read from the files as they are now
    (a hand edit counts); `accounts`, how many AI accounts can do each role's work ({"write": 1, "check": 0,
    "research": 1}: the accounts of the tier the role names, else of every tier); and `tool_available(name)`,
    whether a program the plugin declares is installed here."""

    settings: dict[str, Any]
    accounts: dict[str, int]

    def __new__(
        cls,
        secrets: Any = (),
        settings: dict[str, Any] | None = None,
        accounts: dict[str, int] | None = None,
        tool_available: Callable[[str], bool] | None = None,
    ) -> SetupState:
        state = super().__new__(cls, secrets)
        state.settings = dict(settings or {})
        state.accounts = dict(accounts or {})
        state._available = tool_available
        return state

    def tool_available(self, name: str) -> bool:
        return bool(self._available and self._available(name))


@dataclass(frozen=True)
class StageStatus:
    """Where a record stands in the workspace's own stages (`stages.yaml`, else the plugin's defaults): `current` is
    its stage id (None before the first), `stages` the ids of the stages that apply to it in order, `next` the next
    one that applies (None at the end), `checks` that stage's entry checks by id, and `ready` whether all of them
    pass, so moving on is one step for the person."""

    current: str | None
    stages: tuple[str, ...]
    next: str | None
    checks: dict[str, StageCheckResult]
    ready: bool
    current_label: str | None = None  # the stages' names as the workspace calls them
    next_label: str | None = None


class Registrar:
    """A staging registry: the host installs it only after checking the manifest. `register(registrar)` may read
    `registrar.config` (the plugin's settings, already checked) to decide what to register; registration is fixed
    until the app restarts. The app never restarts on its own: a change to a plugin's settings, or turning plugins on
    or off, makes it say a restart is needed and hold new AI work until the person chooses "Restart now". Until then
    the plugin keeps the settings it registered with and isn't told of the change. Data the workspace adds later (its
    own lists, profiles) is read per call, not at registration."""

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
        self.data_forms: dict[str, DataFormRegistration] = {}
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
        self.value_lists: dict[str, dict[str, Any]] = {}
        self.sign_ins: dict[str, Any] = {}
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

    def op(
        self,
        model: type[OpModel],
        tier: Tier,
        apply: Callable,
        *,
        notes: bool = False,
        candidates: Callable | None = None,
    ) -> None:
        """Register an op: an `OpModel` subclass with a single literal `op` id and a `writes` class variable mapping
        own record kinds to the fields it may change (`("*",)` to create or delete). `tier` is "data" or "system"
        (system ops from the assistant wait for the person). `apply(op, writer, settings)` makes the change through
        the `OpWriter`; raising StoreError refuses this op only. With `notes=True` the op is also offered to the
        core's reading of notes, so the assistant can use it on what the person hands in: give it an `EvidenceIn`
        field, which the core checks against the input, for anything it claims. It is offered only when the note's
        data level covers every record type the op writes, so a note handed in as internal never writes restricted
        records. `candidates(view, settings[, project]) -> list[(id, name)]` lists records such an op may name (with a
        third argument, it gets the id of the project the note was handed in for, or None), shown to the run
        (at most 50, at the level of the record types the op writes), so it can refer to an existing one by id. With
        None the person named no project: list what the note could be about across the workspace, most likely first
        (recently changed, still open), since only the first 50 reach the run; an empty list leaves the run nothing
        to name, so it can only create."""
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
        if candidates is not None and (not notes or not callable(candidates)):
            raise ValueError("candidates is a function, for an op offered to notes")
        self.ops[name] = OpRegistration(model, tier, apply, writes, bool(notes), candidates)

    def op_validator(self, op_name: str, fn: Callable) -> None:
        """Check a core or own op before it applies: `fn(op, view, origin)` (or `fn(op, view)`; `origin` may also be
        keyword-only) returns a list of refusal messages, empty to let it through. The view is the changeset so far.
        `origin` is {"actor": "pm" | "assistant" | "rule" | "plugin", "trust": "trusted" | "untrusted", "via":
        "screen" | "note" | "input" | "task" | "rule" | "action" | "handler" | "job", "task": the run's task kind,
        "about": the record it works on as {"kind", "id"} or None, "request": the run's request id or None, "part":
        the part of the record the request names (as given to `queue_request(part=)`) or None}; ops a plugin's event
        handler or job staged with `apply_op` have actor "plugin" and via "handler" or "job". A validator with a
        parameter named `settings` (or `**kwargs`) also gets the plugin's settings by keyword, so a check that
        depends on a setting is a validator, and its refusal is fed back in a fix round like any other; a refusal
        raised from an op's `apply` refuses the op without a fix round. Before anything applies, the core dry-runs the
        whole changeset in order (text writes included) and rolls it back, so a validator sees what earlier ops in it
        created; with the check at the write boundary, a validator usually runs about three times per op, so it must
        be pure and quick. There is no cache the core keeps for a pass: the view is made anew for each call. Cache
        costly derived data by its content (a hash of the text it comes from, say, in a module-level dictionary of
        bounded size), never by record id or version alone, since the changeset so far may change what a version
        holds."""
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
        start_where: dict[str, Any] | None = None,
        role: str = "write",
        prompt: str = "notes",
        playbook: str = "notes",
        on: str | None = None,
        packet: Callable | None = None,
        tier: str | None = None,
        max_output: int | None = None,
        expected_output: int | None = None,
        temperature: float | None = None,
        all_or_nothing: bool = False,
        requires_ops: tuple[str, ...] | list[str] = (),
        learning: str = "core",
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
        stops the run with that message for the person: the request waits with it as the reason, and no retry, fix
        round or escalation follows. `where` narrows which records of kind `on` the work is offered on and may start
        on: {field: value} or {field: (value, ...)}, every field matching; ANY means the field has a value and None
        that it has none, which for a long text field asks whether the record has text in it. `start_where`, in the
        same form, narrows further only the runs the person starts (from a record, or offered to them there):
        requests a plugin, an action or a stage queues, and any request naming a `part`, check `where` alone, so a
        kind the person starts only on an empty record can still continue part by part. The packet's `max_output`
        hint is never below 256 tokens.

        `output` is "ops" (the answer is a changeset of `ops`) or "draft": the answer is plain prose for the long text
        field `field` of the record the run is about (`on` is required). The core wraps it as a pending `text.draft`
        version for the person's review, runs lints on it (lints on the op "text.draft"), sends a "return" finding
        back for one fix round, and continues a draft cut off at the output limit once before holding it. With
        `anchored=True` the draft revises the current text: the run sees it with an id on each unit, starts every
        paragraph it writes with the ids it came from, and a core check refuses a draft that leaves a unit unaccounted
        for, names an unknown id, or splits or merges an atomic unit; the paragraph map is kept with the version.
        The core adds the text with its ids after the packet's parts, as untrusted material: ids are p1, p2, ... in
        the order of the field format's units over the whole text, so a packet can name the same ids. A request's
        `part` limits a draft to a span or a place in the text (see `queue_request`).
        `questions=N` lets a draft end with up to N questions for the person, in a `<questions>` block the core takes
        off the text and keeps on the version (`questions`), shown beside it; more than N gets a fix round. In an
        anchored answer the `Removed:` line comes before the `<questions>` block, which is always last.

        `role` is "write" (the default: work that writes or changes things), "check" (an independent second opinion on
        work already done) or "research" (gathering from sources). The workspace maps roles to tiers (`ai.roles`). A
        check never runs on an account that wrote the record it is about (its accepted and pending text versions and
        the changes AI runs made to it), unless the person accepts the same account for checks; the run then records
        which kind of independence it had (`Run.independence`). With no account to take it, the check waits for the
        person and says why. The packet decides what a check sees: give it the work, never the writing run's own
        material.

        `tier`, `max_output` (the most tokens an answer may use), `expected_output` (typical answer size, for estimates
        before there are past runs) and `temperature` are defaults; the workspace's `ai.tasks.<kind>` overrides them.

        `all_or_nothing=True` applies an answer's ops together: if any is refused, none applies, and the changeset is
        recorded as refused with each op's reason, for ops that depend on each other (notes that summarize findings
        made in the same answer). Ops held for the person still wait as usual.

        `requires_ops` names ops (from `ops`) an answer must include at least one of, for work whose every answer
        reports (findings, or an explicit "nothing found"): an answer with none of them is refused like any
        invariant, which gets the usual fix round, then a stronger tier; one still without them is held for the
        person as refused.

        `learning` is "core" (the default) or "own". With "own" the core's learning from inputs, new-term scan,
        first-name resolution against people and fact ranking into the workspace's facts don't run on this work, and
        a run's knowledge section (`view.knowledge`) leaves out facts. A task kind working `on` a record type that
        declares `learning = "own"` is treated the same."""
        from engine.config.schema import TaskSettings

        self._name(name)
        if output not in ("ops", "draft"):
            raise ValueError('a task kind\'s output is "ops" or "draft"')
        if (anchored or questions) and output != "draft":
            raise ValueError("only a draft task kind is anchored or asks questions")
        if role not in ("write", "check", "research"):
            raise ValueError('a task kind\'s role is "write", "check" or "research"')
        if learning not in ("core", "own"):
            raise ValueError('a task kind\'s learning is "core" or "own"')
        if not isinstance(questions, int) or not 0 <= questions <= 20:
            raise ValueError("questions is how many a draft may ask, from 0 to 20")
        narrowed = _narrowed(where, on)
        start_narrowed = _narrowed(start_where, on)
        if output == "draft":
            if on is None or not field or ops:
                raise ValueError(
                    "a draft task kind names the record kind it works on and the long text field it drafts"
                )
            ops = ("text.draft",)
        if name in self.tasks or not ops:
            raise ValueError("duplicate task kind or empty op list")
        if not set(requires_ops) <= set(ops):
            raise ValueError("requires_ops names ops the task kind's answers may use")
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
            start_where=start_narrowed,
            role=role,
            all_or_nothing=bool(all_or_nothing),
            requires_ops=tuple(requires_ops),
            learning=learning,
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
        data_level: str | None = None,
    ) -> None:
        """Declare what a kind of file is for: the details asked for when one is added (a pydantic model), the media
        types it accepts (within the workspace's), and a size cap (never above the workspace's). `data_level` ("open",
        "internal" or "restricted"; default internal) is the level a file added under this kind gets when the person
        doesn't choose one at the upload; a level the manifest's `requires.data_levels` doesn't list refuses the
        plugin. A person's explicit choice at the upload stands, and only the person changes it afterwards."""
        from engine.files import AnyDetails, FileKind

        self._name(name)
        if name in self.file_kinds:
            raise ValueError("duplicate file kind")
        if details is not None and not issubclass(details, BaseModel):
            raise ValueError("file kind details must be a pydantic model")
        if data_level not in (None, "open", "internal", "restricted"):
            raise ValueError("a file kind's data_level must be open, internal or restricted")
        self.file_kinds[name] = FileKind(name, details or AnyDetails, tuple(accept), max_mb, label, data_level)

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
        the record must be of the kind the requested task kind is `on`. A function taking a fourth argument also gets
        the interface's task name being requested, so different task kinds can work on different records. Raise the
        interface's events from an op with `writer.emit`, or from an event handler with `context.emit`. With no
        plugin defining the interface running, nothing reads it."""
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
        whenever Today is shown, so it must be quick and deterministic and never call AI. A line's `action` is one
        of this plugin's person actions or task kinds, or one of the core's own (`CORE_LINE_ACTIONS`), which need
        `about`: "go" a `request` waiting for the go, "answer" a `question`, "move-stage" a record of a kind with
        stages, and "open" or "review" any record. A line that counts several items ("three runs wait for your go")
        names the one record its button acts on as `about`; when no single record fits, use "open" on the most
        relevant one, or leave `action` unset and let the line inform. A line naming a core action with the wrong
        `about` fails the contributor like any bad line."""
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
        computed: dict[str, Callable] | None = None,
        show_for: Callable | None = None,
    ) -> None:
        """A screen listing records (listed in `provides.panels`), described as data so it looks and behaves like
        the core's (design 7.2): the records of `kind` (core or own) whose fields equal `filter`, shown as `view`
        ("list", "table" or "board"; a board groups by the first column) with `columns` (fields of the kind, or
        names in `computed`). `primary_action` is the one action on a row and `row_actions` the rest, in its menu:
        this plugin's person actions or task kinds on that kind. `new_action` is a person action of this plugin's on
        the workspace (`on` None) shown above the rows, to add one. Rows are read through the core, and actions run
        as they always do.

        `computed` adds columns that aren't fields: {"words": fn} where `fn(record, view, settings)` returns a short
        str, a number, a bool or None (a word count, a stage, "complete for its tier", the last build). A computed
        column can't be named like a field of the kind (that is a load error). It must be quick and deterministic
        and never call AI; one that raises shows an empty cell and counts as the plugin failing (failure
        containment). A function taking a fourth argument gets a dict shared by every cell of one listing, to keep
        work it would otherwise repeat per row (an index of builds by record); it is new for each listing.

        Filtered by project, a kind with no `project` field follows its `layout_project` reference: a record is in the
        project its referenced record is in. `show_for(project, view) -> bool` lists the panel only on the projects it
        returns True for (a panel of what a parent project's children share, say); without it the panel is on every
        project."""
        self._name(name)
        if name in self.panels or not title.strip() or not columns:
            raise ValueError("duplicate panel, missing title or no columns")
        if view not in ("list", "table", "board"):
            raise ValueError('a panel view is "list", "table" or "board"')
        if tab not in ("today", "work", "people", "settings"):
            raise ValueError('a panel tab is "today", "work", "people" or "settings"')
        computed = dict(computed or {})
        if any(not isinstance(k, str) or not k or not callable(fn) for k, fn in computed.items()):
            raise ValueError("computed maps column names to functions of (record, view, settings)")
        if show_for is not None and not callable(show_for):
            raise ValueError("show_for is a function of (project, view)")
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
            computed,
            show_for,
        )

    def document(
        self,
        name: str,
        *,
        title: str,
        render: Callable,
        tab: str = "work",
        show_for: Callable | None = None,
    ) -> None:
        """A read-only document panel (listed in `provides.panels`): a page the plugin composes from many records
        (a start-here page, a beat sheet, a timeline). `render(view, settings, project) -> str | None` returns
        Markdown, built per call from the view (`project` is the record of the project in view, as `show_for` gets
        it, or None for the workspace); None
        shows that there is nothing to show yet. It must be quick and deterministic and never call AI; one that
        raises shows the panel's problem and counts as the plugin failing (failure containment).

        The screens draw a small Markdown subset as their own elements, never HTML: headings (`#` to `###`),
        paragraphs, bullet and numbered lists (one level), tables (a header row, then `|---|`), rules (`---`), and
        inline `**strong**`, `*emphasis*`, `` `code` `` and links. `[text](record:<kind>/<id>)` links to a record the
        plugin may read (core or its own; one that doesn't exist shows as its text) and opens its page;
        `[text](https://...)` links to a page outside, shown with its real domain. Anything else, raw HTML
        included, shows as the characters it is. Up to 200,000 characters. `show_for(project, view) -> bool` lists
        it only on some projects, as for record panels."""
        self._name(name)
        if name in self.panels or not str(title).strip() or not callable(render):
            raise ValueError("duplicate panel, missing title or invalid render function")
        if tab not in ("today", "work", "people", "settings"):
            raise ValueError('a panel tab is "today", "work", "people" or "settings"')
        if show_for is not None and not callable(show_for):
            raise ValueError("show_for is a function of (project, view)")
        self.panels[name] = PanelRegistration(
            name, str(title).strip(), "", "document", (), {}, None, (), tab, None, {}, show_for, render
        )

    def data_form(
        self,
        name: str,
        *,
        label: str,
        folder: str,
        schema: type[BaseModel],
        description: str = "",
        pattern: str = "*.yaml",
        single: bool = False,
    ) -> None:
        """A kind of data file the person edits through a form (listed in `provides.data_forms`): the files in
        `folder` of the plugin's data layers (`view.data`) that match `pattern`, each checked against `schema` (a
        pydantic model; every field needs a default and a description, as in `Settings`). `pattern` is a glob
        relative to the folder, ending in `.yaml`, with at most one level of subfolder: `*.yaml` (the default),
        `*/item.yaml` (one folder per item, beside its own files) or `stages.yaml`. With `single=True` the form is
        that one file (`pattern` names it): it is listed even before it exists, and no other file can be made.

        The screens list the files with the layer each comes from (shipped, the workspace's, a project's) and any
        problem each has, checked as the plugin's loader would and with defaults checked too (a required value left
        empty shows). They offer a form built from the schema, as for settings: editing a shipped file saves a copy
        in the workspace's layer (or a project's), never the shipped one; a new file starts from the schema's
        defaults or from another file of the kind ("start from"); a copy can be removed to fall back to the less
        specific one. A save writes only the keys the file already had plus those the person set, never the whole
        model with its defaults, so keys left out stay left out (a template's `extends` keeps following its base).
        Every save is checked against the schema (a refusal names the field, or says the file's own rule when the
        model's validator refused it) and offers Undo. The list shows each file's first problem; opening the file
        shows the form with it. The plugin reads the files as before, with `view.data(path, project=...)`, and must
        read them with this same schema: a key left out of a file takes the schema's default, so a loader with other
        defaults (or a field it requires that the form defaults) sees a different file than the form checked."""
        self._name(name)
        folder = str(folder).strip("/")
        if name in self.data_forms or not str(label).strip():
            raise ValueError("duplicate data form or missing label")
        if not re.fullmatch(r"[a-z0-9_-]+(/[a-z0-9_-]+)*", folder):
            raise ValueError("a data form's folder is a relative path of lowercase names, like templates")
        if not re.fullmatch(r"([a-z0-9_*-]+/)?[a-z0-9_*-]+\.yaml", str(pattern)):
            raise ValueError("a data form's pattern names YAML files and has at most one folder level")
        if single and "*" in pattern:
            raise ValueError("a single-file data form names its file in pattern, with no *")
        if not isinstance(schema, type) or not issubclass(schema, BaseModel):
            raise ValueError("a data form's schema is a pydantic model")
        for key, info in schema.model_fields.items():
            if info.is_required() or not info.description:
                raise ValueError(f"data form field {key} needs a default and a description")
        self.data_forms[name] = DataFormRegistration(
            name, " ".join(str(label).split()), folder, schema, description, str(pattern), bool(single)
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

    def connector(
        self,
        name: str,
        *,
        label: str,
        settings: type[BaseModel],
        poll: Callable,
        reads: Literal["mail", "calendar"] | None = None,
    ) -> None:
        """A place the assistant can keep reading (listed in `provides.connectors`). A workspace watches it by naming
        it in `watch.yaml` with its settings, which `settings` (a pydantic model) checks. `poll(settings, state,
        context) -> Poll` lists what the source holds now as `SourceItem`s (a stable key, a title, the text, who
        changed it last) and returns the `state` to keep for the next read; set `complete=False` when it lists only
        what changed.
        Raise `ConnectorError(kind, detail)` with kind `auth`, `no_access`, `not_found`, `outage`, `offline` or
        `throttled` (with `retry_after=` seconds). The core compares, keeps snapshots and hands in what is new,
        changed or gone (for a read that lists only changes, the keys in `Poll.removed`); the connector never writes
        records. `context.web` (when `requires.network` lists hosts) reaches only those hosts, over HTTPS:
        `context.web.get(url, params=..., headers=...)` and `.post(...)` return a response with `status`, `headers`,
        `content`, `.text` and `.json()`, and raise `ConnectorError` for no connection (offline), timeouts and 5xx
        (outage), 401 (auth), 403 (no_access), 404 (not_found), and 429 or 503 with a Retry-After (throttled, with
        the wait). Those errors carry the answer's `status`, `headers` and `body` (`err.json()`), so a connector can
        read the service's own error code and raise a better kind: a 403 that means "slow down" is `throttled`, with
        `retry_after=retry_after(err.headers)`. Every other status (410, say) comes back as a response to read, so a
        service whose expired change marker is a 404 is caught as `not_found` and one whose marker is a 410 is a
        status to check; both mean "start over with a full read". A throttled read isn't counted as a failure,
        and the source isn't read again before its wait ends. `context.secret(name)` reads a secret named in
        `requires.secrets` (None when it isn't set), `context.keep_secret(name, value)` keeps one on this computer,
        and `context.access_token(name)` gives a current token for one of the plugin's sign-ins. Test a connector
        with `engine.plugin_api.testing`.
        `reads="mail"` or `reads="calendar"` says what the connector reads, so the setup walkthrough offers its
        add-on as a mail or calendar service, also before it is installed. Say it in the manifest too, as
        `provides.connector_reads: {<connector>: mail}`, which the registration must match. A connector that says
        nothing is told apart by its name (mail, mailbox, email or inbox; calendar), and the app logs that it
        should say so."""
        self._name(name)
        if name in self.connectors or not callable(poll):
            raise ValueError("duplicate connector or invalid poll function")
        if reads not in (None, "mail", "calendar"):
            raise ValueError("a connector reads mail or a calendar, or says nothing")
        if not isinstance(settings, type) or not issubclass(settings, BaseModel):
            raise ValueError("a connector's settings are a pydantic model")
        from engine.connectors import Connector

        self.connectors[name] = Connector(name, " ".join(str(label).split()) or name, settings, poll, reads=reads)

    def sign_in(
        self,
        name: str,
        *,
        label: str,
        authorize_url: str,
        token_url: str,
        scopes: tuple[str, ...] | list[str],
        client_id: str = "client-id",
        client_secret: str | None = None,
        params: dict[str, str] | None = None,
        allows: tuple[str, ...] | list[str] = (),
        account: Callable | None = None,
        revoke_url: str | None = None,
        default_client_id: str | None = None,
        default_client_secret: str | None = None,
        default_app_note: str | None = None,
        own_app_steps: Sequence[str | tuple[str, str]] = (),
        default_redirects: Sequence[str] = (),
        sources: Sequence[dict[str, Any]] = (),
    ) -> None:
        """A sign-in to a service through its own sign-in page, as the person (listed in `provides.sign_ins`):
        OAuth 2.0 authorization code with PKCE. `authorize_url` and `token_url` are the service's HTTPS addresses, on
        hosts listed in `requires.network`; `scopes` are what it asks the person to allow; `client_id` (and
        `client_secret`, for services that issue one to apps on a computer) name secrets in `requires.secrets` that
        hold the app registration the person made with the service (the secret, when given, is sent to `token_url`
        with the code and with every renewal, beside PKCE); `params` adds parameters to the sign-in page's
        address. The person signs in from Settings; the core receives the answer at its own callback address
        (`<the app's address><base path>/api/sign-ins/callback`, which the app registration must allow: register
        exactly the address the Sign-ins section shows, since some services tell `localhost` from `127.0.0.1`, and
        register it again if the app's address or port changes), keeps the
        tokens on this computer and renews them. A connector gets a current token with
        `context.access_token(name)`; when the person needs to sign in (again) it raises `ConnectorError("auth",
        ...)`, which asks them once; naming a sign-in the plugin doesn't register raises `PluginMisuse`. The
        plugin never sees the sign-in itself or the refresh token.

        `allows` says in plain words what the person is asked to allow ("Read your mail"), shown on the Sign-ins
        row and the setup step before they leave for the service's page. `account(context) -> str`, when given, is
        called once after signing in, with a context like a connector's (`context.web`, `context.access_token`), and
        names the signed-in account ("Signed in as …"); a failure leaves it unnamed: a `ConnectorError` quietly, and
        anything else also counts as the plugin failing (failure containment). `context.granted(name)` is the set of
        scopes the person allowed (the service's answer, or everything asked when it doesn't say); the row names
        any scope asked for and not granted. It is empty while signed out, so ask `context.access_token(name)` first
        (which raises `ConnectorError("auth")` then) and check `granted` after, or a signed-out person reads as
        `no_access` instead of being asked to sign in. `revoke_url` (HTTPS, on a declared host) is where signing out
        withdraws the access at the service (RFC 7009), best effort. When the service refuses to renew a sign-in, it
        shows "Sign in again" at once and the person is told once. The core adds a setup step per sign-in, done
        while signed in.

        Which app registration is used: the workspace's references in `workspace.plugins.secrets` when it sets the
        client id; else values the person pasted on the Sign-ins row (kept on this computer, readable by its owner
        only); else the add-on's own, `default_client_id` (and `default_client_secret`), so people sign in without
        registering anything. Ship a default only for a registration the service issues to apps on a person's
        computer, whose secret the service doesn't treat as confidential, and which allows loopback addresses; a
        hosted app sets its own. `default_app_note` says in plain words what using the add-on's registration means
        (a warning page, how often to sign in again), shown while it is in use. `own_app_steps` is how a person
        makes their own registration, shown as a numbered list beside the paste boxes and the address to allow: each
        step is a line, or (line, https link) to open the service's page for it (up to 12).

        The default pair: `default_client_id` alone is a public client (the service issues no secret);
        `default_client_secret` needs `default_client_id`. `requires.secrets` still lists `client_id` (and
        `client_secret`), the names a pasted or workspace registration is kept under. `default_app_note` shows only
        while the add-on's registration is in use; say there what the service's limits mean for the person (a
        warning page, how often to sign in again, a cap on who may sign in). The note and each step are one or two
        short sentences (up to 300 characters). `default_redirects` lists the callback addresses the add-on's
        registration allows (`http://localhost/api/sign-ins/callback`, say; a loopback host matches any port): when
        the app's own address isn't one of them (served under another base path, or hosted), the add-on's
        registration isn't used and the person is asked for their own, with the reason. Without it, any address is
        assumed to be allowed.

        `sources` are what the core starts reading as soon as the person signs in, so signing in is all the setup
        there is: each is `{"connector": <one of this plugin's connectors>, "label": <a name for the list>,
        "settings": {...}, "every_minutes": 15}` (settings checked against the connector's, defaults filling the
        rest). Each is added once per sign-in, and only when the workspace reads nothing with that connector yet; a
        source the person later removes or changes stays as they left it. Choose settings that read something
        useful with no further choice (the inbox, the main calendar); the person narrows them later."""
        self._name(name)
        if name in self.sign_ins or not str(label).strip() or not scopes:
            raise ValueError("duplicate sign-in, or a sign-in without a label or scopes")
        if not all(isinstance(s, str) and s.strip() for s in scopes):
            raise ValueError("a sign-in's scopes are words")
        if len(allows) > 10 or not all(isinstance(a, str) and a.strip() and len(a) <= 80 for a in allows):
            raise ValueError("allows lists up to 10 short lines of what the person is asked to allow")
        if account is not None and not callable(account):
            raise ValueError("account is a function")
        if default_client_secret and not default_client_id:
            raise ValueError("default_client_secret comes with default_client_id")
        if default_client_id is not None and not str(default_client_id).strip():
            raise ValueError("default_client_id is the add-on's client id, not empty")
        if default_app_note is not None and not (str(default_app_note).strip() and len(default_app_note) <= 300):
            raise ValueError("default_app_note is one or two short sentences")
        steps: list[tuple[str, str | None]] = []
        for step in own_app_steps:
            text, link = (step, None) if isinstance(step, str) else tuple(step)
            if not str(text).strip() or len(text) > 300:
                raise ValueError("each of own_app_steps is a short line")
            if link is not None and not str(link).startswith("https://"):
                raise ValueError("a link in own_app_steps is an https address")
            steps.append((" ".join(str(text).split()), link))
        if len(steps) > 12:
            raise ValueError("own_app_steps lists up to 12 steps")
        if any(not str(a).startswith(("http://", "https://")) for a in default_redirects):
            raise ValueError("default_redirects are full http(s) callback addresses")
        if default_redirects and not default_client_id:
            raise ValueError("default_redirects describe default_client_id's registration")
        started = []
        for source in sources:
            if not isinstance(source, dict) or not set(source) <= {"connector", "label", "settings", "every_minutes"}:
                raise ValueError("each of sources is {connector, label, settings, every_minutes}")
            connector, title = source.get("connector"), str(source.get("label") or "").strip()
            if not isinstance(connector, str) or not connector.startswith(self.name + "/") or not title:
                raise ValueError("each of sources names one of this plugin's connectors and a label")
            every = source.get("every_minutes", 15)
            if not isinstance(every, int) or not 1 <= every <= 1440:
                raise ValueError("a source's every_minutes is a whole number from 1 to 1440")
            if not isinstance(source.get("settings", {}), dict):
                raise ValueError("a source's settings are a mapping")
            started.append(
                {
                    "connector": connector,
                    "label": title,
                    "settings": dict(source.get("settings", {})),
                    "every_minutes": every,
                }
            )
        from engine.sign_in import SignIn

        self.sign_ins[name] = SignIn(
            plugin=self.name,
            name=name,
            label=" ".join(str(label).split()),
            authorize_url=authorize_url,
            token_url=token_url,
            scopes=tuple(scopes),
            client_id=client_id,
            client_secret=client_secret,
            params=dict(params or {}),
            allows=tuple(" ".join(a.split()) for a in allows),
            account=account,
            revoke_url=revoke_url,
            default_client_id=default_client_id.strip() if default_client_id else None,
            default_client_secret=default_client_secret.strip() if default_client_secret else None,
            default_app_note=" ".join(default_app_note.split()) if default_app_note else None,
            own_app_steps=tuple(steps),
            default_redirects=tuple(str(a) for a in default_redirects),
            sources=tuple(started),
        )

    def triage_matcher(self, name: str, *, match: Callable) -> None:
        """A rule kind for triage in `watch.yaml` (listed in `provides.triage_matchers`): `match(change, params) ->
        reason | None` closes a watched change before the assistant reads it when it returns a reason in plain words.
        `change` has source, key, title, change (new, changed or removed), author, before, now, added and removed
        and our_accounts; `params` are the rule's own. `before` is the text last read ("" for a new item) and `now`
        the text read this time ("" for a removed item, whose author is None). For a changed item, `added` and
        `removed` are the lines that appeared and disappeared (a line diff of `before` and `now`); for a new or
        removed item both are empty, so read `now` or `before`. For a mail item, `message` holds its details
        (sender, received, unread, bulk, categories, participants), and is None for anything else. Deterministic and
        quick; it never calls AI. The person sees what it closed and why, and can take a closer look."""
        self._name(name)
        if name in self.triage_matchers or not callable(match):
            raise ValueError("duplicate triage matcher or invalid match function")
        self.triage_matchers[name] = match

    def value_list(self, name: str, *, label: str, values: Sequence[str] = ()) -> None:
        """A value list (listed in `provides.value_lists`): the values a field of the plugin's own record types may
        take, shown as a dropdown. Bind a field to it with `Annotated[str | None, InList("<plugin>/<name>")]` (or a
        list of those); a field may also take a core list, such as "project-status". `values` are the first values a
        workspace gets, once, the first time the list is needed, together with any values its records already hold;
        after that the list is the person's (they add, rename and retire values, with Undo), so never rely on a value
        staying on it. A value not on the list is refused wherever the record is written, a refusal the op's author
        sees; a value a record already holds stays valid after it is retired."""
        self._name(name)
        if name in self.value_lists or not str(label).strip():
            raise ValueError("duplicate value list, or a list without a label")
        cleaned = [" ".join(str(v).split()) for v in values]
        if any(not v or len(v) > 80 for v in cleaned) or len({v.casefold() for v in cleaned}) != len(cleaned):
            raise ValueError("a list's values are distinct words of up to 80 characters")
        self.value_lists[name] = {"label": " ".join(str(label).split()), "values": cleaned}

    def setup_step(
        self,
        name: str,
        *,
        label: str,
        done: Callable,
        explanation: str = "",
        action: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        """A step of the first-run setup (listed in `provides.setup_steps`), shown after the core's steps: `label` says
        what to do in a few words, `explanation` why, and `done(view, settings) -> bool` whether it is done, called
        whenever setup is shown, so it must be quick and deterministic. A `done` taking a third argument gets a
        `SetupState`: the names of its declared secrets that are set (a frozenset; never their values), the effective
        values of the settings it suggests (`state.settings`), the AI accounts per role (`state.accounts`) and
        `state.tool_available(name)` for its declared programs. The host counts `done`'s positional parameters (through
        `functools.wraps`), so a wrapper around it declares all three. `action` is one of this plugin's person actions
        on the workspace, offered as the step's button; without one, the step points to the plugin's settings.
        `settings` suggests core settings the plugin needs ({"ai.budgets.confirm_unpriced": True}): the step shows them
        with an Apply button that saves them like any settings change (checked, with Undo); the plugin never changes
        them itself. A suggested mapping is merged: its keys are added and every key the person already has keeps its
        own value, nested keys included. The person can skip it and come back to it later."""
        self._name(name)
        label = " ".join(str(label).split())
        if name in self.setup_steps or not callable(done) or not label or len(label) > 80:
            raise ValueError("duplicate setup step, invalid done function, or a label that isn't one short line")
        suggested = dict(settings or {})
        if any(not isinstance(k, str) or "." not in k or "/" in k for k in suggested):
            raise ValueError("a setup step suggests core settings by their dotted keys")
        self.setup_steps[name] = SetupStepRegistration(
            name, label, " ".join(str(explanation).split()), done, action, suggested
        )

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


from engine.connectors import (  # noqa: E402 - part of the plugin API
    ConnectorError,
    EventDetails,
    MessageDetails,
    Poll,
    SourceItem,
)
from engine.net import retry_after  # noqa: E402 - part of the plugin API

__all__ = [
    "ConnectorError",
    "retry_after",
    "Poll",
    "SourceItem",
    "EventDetails",
    "MessageDetails",
    "PLUGIN_API_VERSION",
    "Settings",
    "Record",
    "OpModel",
    "EvidenceIn",
    "ANY",
    "NeedsPerson",
    "PluginMisuse",
    "RefTo",
    "InList",
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
    "CORE_LINE_ACTIONS",
    "PacketContext",
    "LongText",
    "Unit",
    "Part",
    "KnowledgeParts",
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
    "StageStatus",
    "SetupState",
    "ToolBox",
    "ToolResult",
    "ToolError",
]
