"""Core record types.

Records refer to each other by id, never by name; names live on their own record and are rendered where shown.
Each type has a kind (its table name in exports) and an id prefix. Plugins add record types through the plugin API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    """Base for every stored record. A plugin's record type subclasses it and sets `record_kind` ("<plugin>/<name>")
    and `prefix` (the id prefix, capital letters). Fields are pydantic fields; unknown fields are refused. Every record
    also carries the core's `ext` and `stage` fields, which a record type may not redefine."""

    model_config = ConfigDict(extra="forbid")

    #: The kind's id: "<plugin>/<name>" for a plugin's record type.
    record_kind: ClassVar[str]
    #: The id prefix, capital letters, unique in the workspace: ids are "<prefix>-<number>" and never reused.
    prefix: ClassVar[str]
    #: What one record of this kind is called on screen and in messages ("chapter"); empty: made from the kind's id.
    record_label: ClassVar[str] = ""
    #: Field values only the person may set; an op from anyone else that sets one is held for the person.
    person_only: ClassVar[dict[str, tuple[Any, ...]]] = {}
    #: Field groups whose values must be unique among live records of this kind.
    unique: ClassVar[tuple[tuple[str, ...], ...]] = ()
    #: How sensitive these records are: packets that include them go only to accounts allowed this level.
    data_level: ClassVar[str] = "internal"
    #: The field (a list of ids from ai.content_levels) holding the content levels the person set on a record; work on
    #: the record goes only to accounts that take them. Only the person sets it.
    content_levels_field: ClassVar[str | None] = None
    #: Where each record is written in the synced folder, relative to its project's folder (or the workspace's, for
    #: a record in no project), without an extension: "plan/chapters/{order:02}-{slug}". `{field}` and
    #: `{field:format}` take the record's own values (and `{id}`); a missing value becomes the id. The core adds
    #: the extension: a record with one long text field is a Markdown file, its other fields as front matter and the
    #: current text as the body; a record with none is a YAML file; one with several is a folder holding
    #: `record.yaml` and a file per field. Every version of its long text is kept beside it, in `.versions/`. None:
    #: the record is only in the folder's machine copy.
    layout: ClassVar[str | None] = None
    #: With a layout, write every record whose path renders the same into one YAML file: a list of entries, each with
    #: its id. Not for record types with long text. Edits made outside come back per entry: a changed entry as a
    #: field edit and a removed one as a delete, both waiting for the person; an added entry is reported, not created.
    layout_collection: ClassVar[bool] = False
    #: The field a collection's entries are sorted by (the id when unset); numbers sort as numbers.
    layout_sort: ClassVar[str | None] = None
    #: For a record with no project of its own: the reference field whose record's project it is placed under in the
    #: synced folder (a chapter's entry, under the chapter's book).
    layout_project: ClassVar[str | None] = None
    #: Fields that never change once the record is made: no edit, the person's included, may set them.
    fixed_fields: ClassVar[tuple[str, ...]] = ()

    id: str = Field(description='The record\'s id: "<prefix>-<number>", never reused.')
    stage: str | None = Field(None, description="Current configured stage id; its wording is set with the stages.")
    ext: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Fields added by plugins, by plugin name.")


@dataclass(frozen=True)
class RefTo:
    """Marks a field as holding the id of another record: `Annotated[str | None, RefTo("project")]`. Honored up to six
    levels into a record (its own fields, then models nested in them); a reference deeper than that is a plain id,
    which the plugin's own validator must check."""

    kind: str


@dataclass(frozen=True)
class InList:
    """Marks a field whose values come from a value list (design 5.1): `Annotated[str | None, InList("project-status")]`
    or a list of them. A value not on the list is refused wherever the record is written; a value already on the
    record stays valid after it is retired from the list."""

    name: str


def list_fields(model: type[BaseModel]) -> list[tuple[str, str, bool]]:
    """(field, list name, holds many) for every top-level field marked with InList."""
    from typing import Annotated, Union, get_args, get_origin

    def marks(annotation: Any) -> list[str]:
        if get_origin(annotation) is Annotated:
            return [m.name for m in annotation.__metadata__ if isinstance(m, InList)]
        return []

    found = []
    for name, info in model.model_fields.items():
        direct = [m.name for m in info.metadata if isinstance(m, InList)]
        annotation = info.annotation
        origin = get_origin(annotation)
        members = get_args(annotation) if origin is Union or type(annotation).__name__ == "UnionType" else ()
        single = direct + [n for arg in members for n in marks(arg)] + marks(annotation)
        many = []
        for arg in (annotation, *members):
            if get_origin(arg) in (list, tuple, set):
                many += [n for inner in get_args(arg) for n in marks(inner)]
        found += [(name, n, False) for n in dict.fromkeys(single)]
        found += [(name, n, True) for n in dict.fromkeys(many)]
    return found


#: How many levels of nested models references are found in (a record's own fields are the first level).
MAX_REF_DEPTH = 6


def ref_fields(model: type[BaseModel], _prefix: str = "", _depth: int = 0) -> list[tuple[str, str]]:
    """References are honored (checked on write, guarded on delete, rendered as names) up to MAX_REF_DEPTH levels into
    a record: its own fields, models in them, and models in those, and so on.

    (path, kind it points to) for every field marked with RefTo: "field" for a single reference, "field[]" for a
    list of references (`list[Annotated[str, RefTo("kind")]]`), optional or not, and paths into nested models such as
    "relations[].person" for a list of models whose `person` field is a reference."""
    from typing import Annotated, Union, get_args, get_origin

    def ref_meta(annotation: Any) -> list[RefTo]:
        if get_origin(annotation) is Annotated:
            return [m for m in annotation.__metadata__ if isinstance(m, RefTo)]
        return []

    def in_list(annotation: Any) -> list[str]:
        origin = get_origin(annotation)
        if origin in (list, tuple, set):
            return [m.kind for arg in get_args(annotation) for m in ref_meta(arg)]
        if origin is Union or type(annotation).__name__ == "UnionType":
            return [k for arg in get_args(annotation) for k in in_list(arg)]
        return []

    def single_in_union(annotation: Any) -> list[str]:
        """A single reference written as one member of a union: `Annotated[str, RefTo("k")] | None`."""
        origin = get_origin(annotation)
        if origin is Union or type(annotation).__name__ == "UnionType":
            return [m.kind for arg in get_args(annotation) for m in ref_meta(arg)]
        return []

    def nested(annotation: Any) -> list[tuple[type[BaseModel], bool]]:
        """Models a field holds directly ("") or in a list ("[]")."""
        origin = get_origin(annotation)
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [(annotation, False)]
        if origin in (list, tuple, set):
            return [(m, True) for arg in get_args(annotation) for m, _ in nested(arg)]
        if origin is Union or type(annotation).__name__ == "UnionType" or origin is Annotated:
            return [found for arg in get_args(annotation) for found in nested(arg)]
        return []

    found = []
    for name, info in model.model_fields.items():
        path = f"{_prefix}{name}"
        for meta in info.metadata:
            if isinstance(meta, RefTo):
                found.append((path, meta.kind))
        found += [(path, kind) for kind in single_in_union(info.annotation)]
        found += [
            (f"{path}[]", kind) for kind in in_list(info.annotation) if kind not in single_in_union(info.annotation)
        ]
        if _depth < MAX_REF_DEPTH - 1:
            for inner, many in nested(info.annotation):
                found += ref_fields(inner, f"{path}[]." if many else f"{path}.", _depth + 1)
    return found


class Link(BaseModel):
    """A labeled web link, kept on a project or a question."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="What the link is, in words for the reader.")
    url: str = Field(description="The address to open.")


class Evidence(BaseModel):
    """The exact words in a source that justify a claim."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description='The id of the source the words come from, or "note" for the person\'s own note.')
    quote: str = Field(min_length=1, description="The exact words, as they appear in that source.")


class LogEntry(BaseModel):
    """One dated line in a project's update log."""

    model_config = ConfigDict(extra="forbid")

    on: date = Field(description="The day the line was added.")
    text: str = Field(min_length=1, description="What the line says.")


class Owner(BaseModel):
    """An action owner: always a person, optionally with the team they act for."""

    model_config = ConfigDict(extra="forbid")

    person: str = Field(description="The id of the person who owns the action.")
    team: str | None = Field(None, description="The id of the team the person acts for here, if any.")


class Person(Record):
    """Someone the workspace works with or tracks. Added by `person.add`; role, org and why_they_matter change through
    `record.set`; the person edits the rest in the app."""

    record_kind: ClassVar[str] = "person"
    prefix: ClassVar[str] = "PER"
    layout: ClassVar[str | None] = "people/{full_name}"

    full_name: str = Field(min_length=1, description="The name shown wherever the person appears.")
    aliases: list[str] = Field(
        default_factory=list, description="Other names that mean this person, such as a first name or nickname."
    )
    role: str | None = Field(None, description="Their job or part in the work, in plain words.")
    team: str | None = Field(None, description="The id of the team they belong to.")
    org: Annotated[str | None, RefTo("organization")] = Field(
        None, description="The id of the organization they work for; its name lives on that record."
    )
    how_to_reach: dict[str, str] = Field(
        default_factory=dict, description="How to reach them: a channel name mapped to the address or handle for it."
    )
    why_they_matter: str | None = Field(None, description="Why this person matters to the work, in plain words.")
    track_only: bool = Field(
        False, description="True for someone inside the tracked area who is only observed, not given work."
    )
    status: Literal["active", "left"] = Field(
        "active", description="active: still around. left: no longer part of the work."
    )


class Organization(Record):
    """A company, client, supplier or other body people work for (design 5.1). Its name lives here only: people refer
    to it by id, so a rename shows everywhere at once."""

    record_kind: ClassVar[str] = "organization"
    prefix: ClassVar[str] = "ORG"
    unique: ClassVar[tuple[tuple[str, ...], ...]] = (("name",),)

    name: str = Field(min_length=1, description="The name shown wherever the organization appears.")
    aliases: list[str] = Field(default_factory=list, description="Other names that mean this organization.")
    notes: str | None = Field(None, description="Anything worth knowing about it, in plain words.")


class Team(Record):
    """A group of people. The person edits it in the app; no core op changes it."""

    record_kind: ClassVar[str] = "team"
    prefix: ClassVar[str] = "TEAM"
    layout: ClassVar[str | None] = "teams/{name}"

    name: str = Field(min_length=1, description="The name shown wherever the team appears.")
    aliases: list[str] = Field(default_factory=list, description="Other names that mean this team.")
    members: list[str] = Field(default_factory=list, description="The ids of the people in the team.")


class Project(Record):
    """A piece of work being run, possibly inside another (a book in its series). `project.add` starts one;
    `record.set` changes status, phase, target, priority, summary, parent and language; `record.log` adds to its log;
    the person edits the rest in the app, and only the person sets its content levels and budget."""

    record_kind: ClassVar[str] = "project"
    prefix: ClassVar[str] = "PRJ"
    content_levels_field: ClassVar[str | None] = "content_levels"

    name: str = Field(min_length=1, description="The name shown wherever the project appears.")
    group: Annotated[str | None, InList("project-group")] = Field(
        None, description="The portfolio grouping the project is listed under, from the project-group list."
    )
    status: Annotated[str | None, InList("project-status")] = Field(
        None, description="Where the project stands now, from the project-status list."
    )
    phase: Annotated[str | None, InList("project-phase")] = Field(
        None, description="The part of its life the project is in, from the project-phase list."
    )
    target: date | None = Field(None, description="The day the project is meant to be finished.")
    priority: Annotated[str | None, InList("project-priority")] = Field(
        None, description="How important the project is, from the project-priority list."
    )
    summary: str | None = Field(None, description="A short description of what the project is.")
    owner: str | None = Field(None, description="The id of the person responsible for the project.")
    links: list[Link] = Field(default_factory=list, description="Pages that belong to the project.")
    tags: list[str] = Field(default_factory=list, description="Free labels for finding the project.")
    content_levels: list[str] = Field(
        default_factory=list,
        description="Content levels (those defined for AI) its material carries, set by the person; AI work on it "
        "goes only to accounts that take them all.",
    )
    parent: str | None = Field(
        None, description="The id of the project this one belongs to (a book in its series); never itself or below it."
    )
    language: str | None = Field(
        None,
        pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
        description="The language tag work on it is written in; unset means its parent's, else the workspace's.",
    )
    budget_usd: float | None = Field(
        None,
        ge=0,
        description="The most AI work on it and everything in it may cost, set by the person; none for no cap.",
    )
    log: list[LogEntry] = Field(
        default_factory=list, description="The update log, oldest first; `record.log` adds a line dated that day."
    )


class Action(Record):
    """Something a person will do. Added by `action.add`, closed by `action.close`; `record.set` changes text, due and
    notes, and sending a notice marks who was told."""

    record_kind: ClassVar[str] = "action"
    prefix: ClassVar[str] = "ACT"
    layout: ClassVar[str | None] = "actions/{id}"

    project: str | None = Field(None, description="The id of the project it belongs to.")
    text: str = Field(min_length=1, description="What is to be done, starting with a verb.")
    owners: list[Owner] = Field(
        default_factory=list, description="The people who do it; required unless the action is held."
    )
    due: date | None = Field(None, description="The day it is due.")
    status: Literal["held", "open", "done"] = Field(
        "open", description="held: waiting for an owner to be picked. open: to be done. done: finished."
    )
    notes: str | None = Field(None, description="Extra detail about the action.")
    told: dict[str, date] = Field(
        default_factory=dict, description="Who has been told about it: a person id mapped to the day they were told."
    )
    source: str | None = Field(None, description="The id of the source it came from, if any.")
    evidence: Evidence | None = Field(None, description="The words in the source that justify the action.")

    @model_validator(mode="after")
    def _owners_unless_held(self) -> Action:
        if self.status != "held" and not self.owners:
            raise ValueError("an action needs at least one owner unless it is held for one")
        return self


class Question(Record):
    """A question for a person; a decision is a question to the PM. Added by `question.add` or by the engine, closed by
    `question.done`; the person sends, drops or answers them in the app."""

    record_kind: ClassVar[str] = "question"
    prefix: ClassVar[str] = "Q"
    layout: ClassVar[str | None] = "questions/{id}"

    to: str = Field(description="The id of the person being asked.")
    title: str = Field(min_length=1, description="The question in one line.")
    text: str = Field("", description="The detail the reader needs to answer.")
    links: list[Link] = Field(default_factory=list, description="Pages the reader can open to see what it is about.")
    kind: Literal["question", "decision", "action-notice", "routing", "impact"] = Field(
        "question",
        description=(
            "question: an ordinary question. decision: a choice for the PM to make. action-notice: tells someone "
            "about an action. routing: asks the PM who or what something is. impact: asks another area's contact "
            "how a change affects them."
        ),
    )
    projects: list[str] = Field(default_factory=list, description="The ids of the projects it is about.")
    batch: Literal["now", "later"] = Field(
        "now", description="Whether it is ready to go out now or waits for a later batch."
    )
    status: Literal["open", "sent", "answered", "dropped"] = Field(
        "open",
        description="open: not yet sent. sent: marked as sent, waiting for an answer. answered: closed with an "
        "answer. dropped: closed without one.",
    )
    sent_at: datetime | None = Field(None, description="When it was marked as sent.")
    answer: str | None = Field(None, description="The answer, once answered.")
    source: str | None = Field(None, description="The id of the source it came from, if any.")
    options: list[str] = Field(default_factory=list, description="Choices offered, for routing and decisions.")
    resolves: dict[str, Any] | None = Field(None, description="What answering it releases, e.g. a held op.")


class Watched(BaseModel):
    """Where a watched input came from: the source in watch.yaml, the item's key there, and what happened to it."""

    source: str = Field(description="The id of the watched source.")
    key: str = Field(description="The item's key within that source.")
    change: Literal["new", "changed", "removed"] = Field(description="What happened to the item.")
    author: str | None = Field(None, description="Who changed it last, as the source says.")
    by_us: bool = Field(False, description="The author is one of the workspace's own accounts.")


class Source(Record):
    """One input the workspace received, such as pasted text; the text is kept by its hash. The engine adds it when
    something is handed in, and its content never changes; the person may mark how it may be quoted."""

    record_kind: ClassVar[str] = "source"
    prefix: ClassVar[str] = "SRC"
    fixed_fields: ClassVar[tuple[str, ...]] = ("received_at", "kind", "content_hash", "trust", "url", "watched")

    received_at: datetime = Field(description="When the input arrived.")
    kind: str = Field(description="How it arrived, such as pasted.")
    title: str = Field(description="A short name for it, shown in lists.")
    content_hash: str = Field(description="Hash of its text; the saved text is named by it in the sources folder.")
    trust: Literal["trusted", "untrusted"] = Field(
        description="untrusted: outside content, material to read and never instructions. trusted: the person's own."
    )
    projects: list[str] = Field(default_factory=list, description="The ids of the projects it is about.")
    url: str | None = Field(None, description="Where it came from, when it has an address.")
    watched: Watched | None = Field(None, description="For an input a watcher found: where and what changed.")
    excerpts: Literal["allowed", "never"] = Field(
        "allowed",
        description="never: the person allows using this source but never quoting it beyond a word or two; checks "
        "that compare drafts with sources apply a stricter limit to it. Set by the person only.",
    )


class File(Record):
    """A file a person added or a program wrote. The bytes live in the workspace's files folder under their hash. A
    person adds one by upload or `file.add`; a new version is a new record that points at the one it replaces."""

    record_kind: ClassVar[str] = "file"
    prefix: ClassVar[str] = "FILE"

    name: str = Field(min_length=1, description="The file's name as added, for showing and downloading.")
    media_type: str = Field(description="What kind of content it is, such as image/png.")
    size: int = Field(ge=0, description="Size in bytes.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the bytes; also where they are stored.")
    file_kind: str = Field("attachment", description="What the file is for: the core's attachment or a declared kind.")
    project: str | None = Field(None, description="The project it belongs to; none means the whole workspace.")
    meta: dict[str, Any] = Field(default_factory=dict, description="Details the file kind asks for, validated on add.")
    origin: Literal["upload", "tool"] = Field("upload", description="Added by the person, or written by a program.")
    trust: Literal["trusted", "untrusted"] = Field(
        "trusted", description="untrusted: its content is material to read, never instructions."
    )
    replaces: str | None = Field(None, description="The earlier file this one is a new version of.")
    added_at: datetime = Field(description="When the record was added.")


class JobRun(Record):
    """One run of a plugin's scheduled job. The engine writes it after each run; nothing changes it."""

    record_kind: ClassVar[str] = "job_run"
    prefix: ClassVar[str] = "JOBRUN"

    plugin: str = Field(description="The plugin the job belongs to.")
    job: str = Field(description="The job's name.")
    started_at: datetime = Field(description="When the run started.")
    seconds: float = Field(0.0, description="How long it took.")
    outcome: Literal["ok", "failed"] = Field(
        description="ok: it finished. failed: it raised; repeated failures turn the plugin off."
    )
    error: str | None = Field(None, description="What went wrong, for a failed run.")


class Cite(BaseModel):
    """Words an answer rests on, and where they come from."""

    quote: str = Field(description="The exact words.")
    source: str | None = Field(None, description="Where they are: the help material, or a saved source's id.")


class Answer(Record):
    """The assistant's answer to a question the PM asked, with the words it rests on."""

    record_kind: ClassVar[str] = "answer"
    prefix: ClassVar[str] = "ANS"

    request: str = Field(description="The ask it answers.")
    text: str = Field(description="The answer.")
    cites: list[Cite] = Field(default_factory=list, description="The words the answer rests on.")


class SettingProposal(Record):
    """A setting change the assistant suggested in an answer; the PM applies it or sets it aside."""

    record_kind: ClassVar[str] = "setting_proposal"
    prefix: ClassVar[str] = "SETPROP"

    request: str = Field(description="The ask it came from.")
    key: str = Field(description="The setting's dotted key.")
    value: Any = Field(None, description="The suggested value.")
    why: str = Field(description="Why it answers the question.")
    status: Literal["open", "applied", "dismissed"] = Field(
        "open", description="open: waiting for the PM. applied: saved. dismissed: set aside."
    )


class Report(Record):
    """A report to the product's maintainers the assistant drafted for something the product can't do (design
    6.13). The PM reviews it and sends it themselves."""

    record_kind: ClassVar[str] = "report"
    prefix: ClassVar[str] = "RPT"

    request: str = Field(description="The ask it came from.")
    title: str = Field(description="What is missing, in one line.")
    text: str = Field(description="The report.")
    status: Literal["draft", "sent", "dismissed"] = Field(
        "draft", description="draft: not yet reviewed. sent: the PM sent it. dismissed: set aside."
    )


class SnapshotEvent(BaseModel):
    """A calendar item's details as its source gave them (see EventDetails in the connectors)."""

    model_config = ConfigDict(extra="forbid")

    start: str
    end: str | None = None
    all_day: bool = False
    where: str | None = None
    cancelled: bool = False
    repeats: str | None = None


class SnapshotMessage(BaseModel):
    """A mail item's details as its source gave them (see MessageDetails in the connectors)."""

    model_config = ConfigDict(extra="forbid")

    sender: str | None = None
    received: str | None = None
    unread: bool | None = None


class Snapshot(Record):
    """What a watched item looked like when last read: its text is kept in the sources folder by hash. The watcher
    writes it; nothing else changes it."""

    record_kind: ClassVar[str] = "snapshot"
    prefix: ClassVar[str] = "SNAP"

    source: str = Field(description="The id of the watched source.")
    key: str = Field(description="The item's key within the source.")
    title: str = Field(description="The item's title when last read.")
    content_hash: str = Field(description="Hash of its text when last read.")
    author: str | None = Field(None, description="Who changed it last, as the source said.")
    seen_at: datetime = Field(description="When this version was first seen.")
    gone: bool = Field(False, description="It was no longer in the source at the last complete read.")
    link: str | None = Field(None, description="Where the person can open it, as the source gave it.")
    event: SnapshotEvent | None = Field(None, description="For a calendar item: when and where, for the agenda.")
    message: SnapshotMessage | None = Field(None, description="For a mail item: from whom and when.")
    closed_by: str | None = Field(
        None, description="The triage rule that closed its latest change, so Today leaves it out (a newsletter, say)."
    )


class WatchRun(Record):
    """One read of a watched source and what came of it. The watcher writes it; nothing changes it."""

    record_kind: ClassVar[str] = "watch_run"
    prefix: ClassVar[str] = "WRUN"

    source: str = Field(description="The id of the watched source.")
    started_at: datetime = Field(description="When the read started.")
    seconds: float = Field(0.0, description="How long it took.")
    outcome: Literal["ok", "baseline", "failed", "offline", "throttled"] = Field(
        description="ok: read and compared. baseline: a first read that only noted what is there. failed: it "
        "couldn't be read. offline: no network here, so it wasn't tried. throttled: the service asked to wait."
    )
    retry_at: datetime | None = Field(None, description="For a throttled read: not read again before this time.")
    error_kind: str | None = Field(None, description="For a failed read: auth, no_access, not_found or outage.")
    error: str | None = Field(None, description="What went wrong, in the connector's words.")
    new: int = Field(0, description="Items handed in as new.")
    changed: int = Field(0, description="Items handed in as changed.")
    removed: int = Field(0, description="Items handed in as gone.")
    state: dict[str, Any] = Field(default_factory=dict, description="What the connector keeps between reads.")


class SettingChange(Record):
    """One setting the person changed from the screens: which key, what it was and what it became. Written with the
    config file; nothing changes it."""

    record_kind: ClassVar[str] = "setting_change"
    prefix: ClassVar[str] = "SETCHG"

    key: str = Field(description="Which setting changed.")
    before: Any = Field(None, description="Its value before the change.")
    after: Any = Field(None, description="Its value after the change.")
    was_default: bool = Field(False, description="It was at its default before the change (set in no file).")
    is_default: bool = Field(False, description="The change put it back to its default (removed from the file).")
    at: datetime = Field(description="When it was changed.")


class ToolRun(Record):
    """One run of an outside program a plugin declared: what ran, how it ended and what it returned. The engine writes
    it after each run; nothing changes it."""

    record_kind: ClassVar[str] = "tool_run"
    prefix: ClassVar[str] = "TOOL"

    plugin: str = Field(description="The name of the plugin that ran the program.")
    tool: str = Field(description="The program's name, as the plugin declared it.")
    version: str | None = Field(None, description="The program's version, from its version check.")
    args: list[str] = Field(default_factory=list, description="The arguments it was run with.")
    inputs: list[str] = Field(default_factory=list, description="Names of the files given to the program.")
    returncode: int = Field(description="The program's exit code.")
    timed_out: bool = Field(False, description="True when it was stopped for running too long.")
    output_cut: bool = Field(False, description="True when its output was cut short for being too large.")
    seconds: float = Field(0, description="How long it ran, in seconds.")
    collected: list[dict[str, Any]] = Field(default_factory=list, description="Files returned: {name, size}.")
    omitted: list[dict[str, Any]] = Field(default_factory=list, description="Files matched but not returned.")
    stderr_tail: str = Field("", description="The end of the program's error stream, for diagnosing a failure.")
    ran_at: datetime = Field(description="When it was run.")


class TextVersion(Record):
    """One version of a long text field: its text (stored once by hash in the workspace's texts folder), where it came
    from, whether it is waiting for review, and who wrote each passage. Written by the text ops and `writer.set_text`;
    the person accepts or discards pending ones."""

    record_kind: ClassVar[str] = "text_version"
    prefix: ClassVar[str] = "TXT"

    owner_kind: str = Field(description="The kind of the record whose field this is a version of.")
    owner_id: str = Field(description="The id of that record.")
    field: str = Field(description="The long text field.")
    number: int = Field(ge=1, description="The version's number for this field: 1, 2, 3...; never reused.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the text; also where it is stored.")
    format: str = Field(description="The text format its units come from.")
    words: int = Field(0, ge=0, description="How many words it has.")
    source: Literal["edit", "draft", "proposal", "merge", "import"] = Field(
        description="edit: the person wrote it here. draft: the assistant wrote it. proposal: the person's own work "
        "arriving from outside (a working copy, a file). merge: the result of accepting changes. import: loaded by a "
        "person's action."
    )
    status: Literal["pending", "accepted", "merged", "discarded"] = Field(
        description="pending: waiting for review. accepted: it became the field's text. merged: some of its changes "
        "were accepted into a newer version. discarded: set aside."
    )
    base: int | None = Field(None, description="The number of the version it was made from.")
    replaces: int | None = Field(None, description="For an accepted version, the number of the one it replaced.")
    authorship: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Who wrote each passage: {start, end, kind, run}, kind person, assistant (drafted) or "
        "assistant_edit (the person's text changed by the assistant), with the AI run for the assistant's.",
    )
    paragraph_map: list[dict[str, Any]] = Field(
        default_factory=list, description="For an anchored draft, which base units each new unit came from."
    )
    note: str | None = Field(None, description="Where it came from, in words, when that helps the review.")
    unmapped: list[str] = Field(
        default_factory=list,
        description="For a version taken back from a working copy, what the format couldn't map, shown beside it.",
    )
    questions: list[str] = Field(
        default_factory=list, description="For a draft, the questions for the person it ended with, shown beside it."
    )
    run: str | None = Field(None, description="The AI run that wrote it, for a draft.")
    created_at: datetime = Field(description="When it was written.")


class WorkingCopy(Record):
    """A long text field handed out as a file for the person's own tool (a word processor), and what came back. The
    host writes it when the person hands a field out or brings a file back."""

    record_kind: ClassVar[str] = "working_copy"
    prefix: ClassVar[str] = "WC"

    owner_kind: str = Field(description="The kind of the record whose field was handed out.")
    owner_id: str = Field(description="That record's id.")
    field: str = Field(description="The long text field.")
    format: str = Field(description="The working-copy format that made the file.")
    base: int | None = Field(None, description="The number of the version handed out; none if the field was empty.")
    file: str = Field(description="The id of the file handed out.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the file handed out, to tell an untouched one.")
    status: Literal["out", "returned", "dropped"] = Field(
        "out",
        description="out: handed out. returned: a file came back as a proposal. dropped: set aside by the person.",
    )
    returned_file: str | None = Field(None, description="The id of the last file brought back.")
    proposal: str | None = Field(None, description="The id of the text version the last file back became.")
    handed_at: datetime = Field(description="When it was handed out.")
    returned_at: datetime | None = Field(None, description="When a file last came back.")


class StageStart(BaseModel):
    """Which stage entry asked for a task."""

    model_config = ConfigDict(extra="forbid")
    kind: str = Field(description="The kind of the record that entered the stage.")
    record: str = Field(description="The id of the record that entered the stage.")
    stage: str = Field(description="The id of the stage entered.")
    changeset: str | None = Field(None, description="The id of the changeset that made the move, if known.")


class About(BaseModel):
    """The record a request's work is about, as it was when the work was asked for."""

    model_config = ConfigDict(extra="forbid")
    kind: str = Field(description="The record's kind.")
    id: str = Field(description="The record's id.")


class Request(Record):
    """A unit of work for the assistant. The engine creates it when something is handed in, a stage starts a task or
    a schedule fires, and moves it through its states; the person can send back or dismiss it."""

    record_kind: ClassVar[str] = "request"
    prefix: ClassVar[str] = "REQ"

    task: str = Field(description="The kind of work to do, as an AI task kind id.")
    stage_start: StageStart | None = Field(None, description="The stage entry that requested this task.")
    about: About | None = Field(None, description="The record the work is about, for a task kind that works on one.")
    use: str | None = Field(
        None, description='The account the person picked for this request ("provider/model"), in place of its tier.'
    )
    approval: Literal["required", "granted"] | None = Field(
        None,
        description="Needs the person's go before dispatch: stage tasks, and runs above the amount to confirm.",
    )
    estimate_usd: float | None = Field(None, description="What the run was estimated to cost when it asked for a go.")
    note: str | None = Field(None, description="The person's own words that came with the request.")
    source: str | None = Field(None, description="The id of the source the request is about, if any.")
    origin: Literal["pm", "input", "schedule"] = Field(
        description="Who started it: pm, the person (handing something in or sending work back); input, an outside "
        "input; schedule, a schedule or a stage entry."
    )
    state: Literal["queued", "running", "review", "done", "needs_you", "failed"] = Field(
        "queued",
        description="queued: waiting its turn. running: with the assistant. review: its changeset awaits the "
        "person. done: finished. needs_you: stopped until the person acts. failed: ended with an error.",
    )
    waiting: str | None = Field(None, description="Why it is waiting and until when, in plain words.")
    follows: str | None = Field(
        None, description="The change (a changeset id) whose event a plugin answered with this work, if any."
    )
    sensitivity: Literal["open", "internal", "restricted"] | None = Field(
        None, description="How sensitive the person said what they handed in is; it only ever raises the level."
    )
    part: dict[str, Any] | None = Field(
        None,
        description="The part of a long text the work is about: {first, last} paragraphs (by number) an anchored "
        'draft revises or other work reads, or {after} a draft adds new text after (0: at the start; "end": at the '
        "end); with the {base} version number they refer to.",
    )
    project: str | None = Field(None, description="The project the person said a hand-in is about, if they did.")
    auto_closed: dict[str, str] | None = Field(
        None, description="For a watched change a triage rule closed: {rule, reason}. Taking a closer look clears it."
    )
    folded_into: str | None = Field(
        None, description="The newer request this one's change was folded into, so they are read in order, once."
    )
    attempts: int = Field(0, description="How many times the assistant has started on it.")
    created_at: datetime = Field(description="When the request was made.")
    changeset: str | None = Field(None, description="The id of the changeset the assistant proposed for it.")
    previous: str | None = Field(None, description="The request this one redoes after the PM sent it back.")
    dismissed: bool = Field(
        False, description="The PM set this aside without trying again; it no longer counts as needing attention."
    )
    dismissed_from: Literal["queued", "running", "review", "done", "needs_you", "failed"] | None = Field(
        None, description="The state the request was in when it was dismissed, put back by undoing the dismissal."
    )


class Changeset(Record):
    """What the assistant proposed for one request, how it was checked and what was applied. The applier writes it
    and updates it on release or undo; the person marks it reviewed."""

    record_kind: ClassVar[str] = "changeset"
    prefix: ClassVar[str] = "CS"

    request: str = Field(description="The id of the request it answers.")
    summary: str = Field("", description="One line saying what the changeset does.")
    topic: str = Field("", description="A few words naming what the input was about, for the item's title.")
    ops: list[dict[str, Any]] = Field(
        default_factory=list,
        description="One outcome per op: its index, the op, its status (applied, held, refused or undone), group, "
        "the records it touched and the reason it was held or refused.",
    )
    status: Literal["applied", "held", "rejected", "undone", "partly_undone"] = Field(
        description="applied: all ops went through. held: some wait for the person. rejected: set aside. undone: all "
        "applied ops were undone. partly_undone: some were."
    )
    problems: list[dict[str, Any]] = Field(
        default_factory=list, description="Problems that belong to the changeset as a whole rather than to one op."
    )
    trust: Literal["trusted", "untrusted"] = Field(
        description="Whether the input it was made from was trusted; records its ops create carry the same mark."
    )
    reviewed: bool = Field(False, description="True once the person has looked at it and accepted it.")
    run: str | None = Field(None, description="The id of the AI run that produced it, if any.")
    action: dict[str, Any] | None = Field(
        None, description="The person action this came from: its name, target and the choices the person made."
    )
    created_at: datetime = Field(description="When the changeset was recorded.")


class Fact(Record):
    """Something recorded as true, with the words that show it. Added by `fact` and by `question.done`; never edited."""

    record_kind: ClassVar[str] = "fact"
    prefix: ClassVar[str] = "FACT"
    layout: ClassVar[str | None] = "facts/{id}"

    text: str = Field(min_length=1, description="The fact, as a statement.")
    project: str | None = Field(None, description="The id of the project it is about, if any.")
    source: str | None = Field(None, description="The id of the source it came from, if any.")
    evidence: Evidence | None = Field(None, description="The words that justify it.")
    trust: Literal["trusted", "untrusted"] = Field(
        "trusted", description="untrusted when it came from outside content."
    )


class Note(Record):
    """Something kept from an input that is not a fact, action or question. Added by `note`; never edited."""

    record_kind: ClassVar[str] = "note"
    prefix: ClassVar[str] = "NOTE"
    layout: ClassVar[str | None] = "notes/{id}"

    text: str = Field(min_length=1, description="What was kept.")
    project: str | None = Field(None, description="The id of the project it is about, if any.")
    source: str | None = Field(None, description="The id of the source it came from, if any.")
    trust: Literal["trusted", "untrusted"] = Field(
        "trusted", description="untrusted when it came from outside content."
    )


class Run(Record):
    """One call to an AI provider. The engine writes it after each call, for usage and cost reports; nothing changes
    it."""

    record_kind: ClassVar[str] = "run"
    prefix: ClassVar[str] = "RUN"

    request: str = Field(description="The id of the request the call was made for.")
    task: str = Field(description="The kind of task asked.")
    provider: str = Field(description="The configured provider that was called.")
    model: str = Field(description="The model that answered, as the provider reported it.")
    tier: str = Field(description="The configured tier the call was made on.")
    input_chars: int = Field(0, description="Characters sent.")
    output_chars: int = Field(0, description="Characters received.")
    input_tokens: int | None = Field(None, description="Tokens sent, when the provider reports them.")
    output_tokens: int | None = Field(None, description="Tokens received, when the provider reports them.")
    cached_input_tokens: int | None = Field(None, description="Tokens sent that were read from the provider's cache.")
    cost_usd: float | None = Field(None, description="What the call cost in US dollars; none when it can't be told.")
    seconds: float = Field(0.0, description="How long the call took, in seconds.")
    outcome: Literal["ok", "invalid_output", "error", "refused"] = Field(
        description="ok: an answer came back. invalid_output: the answer wasn't in the expected shape. error: the "
        "call failed. refused: the provider said it refused the work under its own policy (its reason is in "
        "error_detail)."
    )
    independence: Literal["other_account", "same_account"] | None = Field(
        None,
        description="For a check: other_account, run on an account that didn't write the work; same_account, on one "
        "that did, as a fresh run the person accepted. None for other work.",
    )
    error_kind: str | None = Field(None, description="How the call failed, from the runner's own error; none if ok.")
    error_detail: str | None = Field(None, description="The error's own text, for diagnosing a failure.")
    started_at: datetime = Field(description="When the call started.")


class Signal(Record):
    """A correction by the PM, the measure of how well the assistant does. The engine records one when the person
    sends work back, undoes it, edits a draft or similar; nothing changes it."""

    record_kind: ClassVar[str] = "signal"
    prefix: ClassVar[str] = "SIG"

    kind: Literal["sent_back", "undone", "dropped", "reworded", "pulled_back", "draft_edited", "held_declined"] = Field(
        description="What the person did: sent_back, undone, dropped or reworded something the assistant made; "
        "pulled_back an automatic change; draft_edited a draft before approving it; held_declined a held op."
    )
    refs: list[str] = Field(default_factory=list, description="The ids of the records the correction is about.")
    note: str | None = Field(None, description="What the person said or changed, if anything.")
    at: datetime = Field(description="When the correction was made.")


#: Record kind to its model. The order is the export order.
class ValueList(Record):
    """A list of the values a field may take, shown as a dropdown (design 5.1). The core and plugins ship its first
    values; the person adds, renames and retires values with `list.add`, `list.rename` and `list.retire`. A retired
    value is no longer offered, and records that have it keep it."""

    record_kind: ClassVar[str] = "value_list"
    prefix: ClassVar[str] = "LIST"
    unique: ClassVar[tuple[tuple[str, ...], ...]] = (("name",),)

    name: str = Field(
        pattern=r"^([a-z0-9][a-z0-9-]*/)?[a-z0-9][a-z0-9-]*$",
        description='The list\'s id: "project-status", or "<plugin>/<name>" for a plugin\'s list.',
    )
    label: str = Field(min_length=1, description="What the list is called on screen.")
    values: list[str] = Field(default_factory=list, description="The values offered, in the order shown.")
    retired: list[str] = Field(
        default_factory=list, description="Values no longer offered that records may still hold."
    )

    @model_validator(mode="after")
    def _distinct(self) -> ValueList:
        everything = [v.strip() for v in (*self.values, *self.retired)]
        if any(not v for v in everything):
            raise ValueError("a list's values are words, not blanks")
        if len({v.casefold() for v in everything}) != len(everything):
            raise ValueError("a list holds each value once")
        return self


REGISTRY: dict[str, type[Record]] = {
    model.record_kind: model
    for model in (
        Person,
        Organization,
        Team,
        Project,
        Action,
        Question,
        Source,
        Request,
        Changeset,
        Fact,
        Note,
        Run,
        Signal,
        File,
        ToolRun,
        JobRun,
        SettingChange,
        Answer,
        SettingProposal,
        Report,
        Snapshot,
        WatchRun,
        TextVersion,
        WorkingCopy,
        ValueList,
    )
}

#: Fields that hold ids of other records, per kind, as (field, kind it points to). Used to check references.
REFERENCES: dict[str, list[tuple[str, str]]] = {
    "person": [("team", "team"), ("org", "organization")],
    "team": [("members[]", "person")],
    "project": [("owner", "person"), ("parent", "project")],
    "action": [("project", "project"), ("owners[].person", "person"), ("owners[].team", "team"), ("source", "source")],
    "question": [("to", "person"), ("projects[]", "project"), ("source", "source")],
    "source": [("projects[]", "project")],
    "request": [
        ("source", "source"),
        ("changeset", "changeset"),
        ("previous", "request"),
        ("follows", "changeset"),
        ("folded_into", "request"),
        ("project", "project"),
    ],
    "changeset": [("request", "request"), ("run", "run")],
    "fact": [("project", "project"), ("source", "source")],
    "note": [("project", "project"), ("source", "source")],
    "run": [("request", "request")],
    "file": [("project", "project"), ("replaces", "file")],
    "working_copy": [("file", "file"), ("returned_file", "file"), ("proposal", "text_version")],
    "answer": [("request", "request")],
    "setting_proposal": [("request", "request")],
    "report": [("request", "request")],
}


def model_for(kind: str) -> type[Record]:
    try:
        return REGISTRY[kind]
    except KeyError:
        raise KeyError(f"unknown record kind {kind!r}") from None


def values_at(data: object, path: str) -> list[object]:
    """The values at a reference path such as "owner", "members[]" or "owners[].person"."""
    if not path:
        return [data]
    head, _, rest = path.partition(".")
    if head.endswith("[]"):
        items = data.get(head[:-2], []) if isinstance(data, dict) else []
        return [v for item in items for v in values_at(item, rest)]
    if not isinstance(data, dict):
        return []
    return values_at(data.get(head), rest)


def referrers(view: Any, kind: str, record_id: str) -> list[tuple[str, str]]:
    """Every live record that refers to this one, as (kind, id), from the declared references."""
    found = []
    for other_kind, refs in REFERENCES.items():
        paths = [path for path, target in refs if target == kind]
        if not paths:
            continue
        for stored in view.list(other_kind):
            if any(record_id in values_at(stored.data, p) for p in paths):
                found.append((other_kind, stored.id))
    return found


def kind_label(model: type[BaseModel] | None, kind: str) -> str:
    """What one record of a kind is called in words: its `record_label`, else its id's last part with spaces."""
    label = getattr(model, "record_label", "") if model is not None else ""
    return label or kind.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
