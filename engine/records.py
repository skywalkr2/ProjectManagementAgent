"""Core record types.

Records refer to each other by id, never by name; names live on their own record and are rendered where shown.
Each type has a kind (its table name in exports) and an id prefix. Plugins add record types through the plugin API.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


class Record(BaseModel):
    """Base for every stored record. A plugin's record type subclasses it and sets `record_kind` ("<plugin>/<name>")
    and `prefix` (the id prefix, capital letters). Fields are pydantic fields; unknown fields are refused. Every record
    also carries the core's `ext` and `stage` fields, which a record type may not redefine. A field declared with an
    `alias` takes the alias as input and is stored, read back and named in reference paths by its field name, in the
    record and in any model nested in it; only a model whose config sets `serialize_by_alias` is stored by alias."""

    model_config = ConfigDict(extra="forbid")

    #: The kind's id: "<plugin>/<name>" for a plugin's record type.
    record_kind: ClassVar[str]
    #: The id prefix, capital letters, unique in the workspace: ids are "<prefix>-<number>" and never reused.
    prefix: ClassVar[str]
    #: What one record of this kind is called on screen and in messages ("chapter"); empty: made from the kind's id.
    record_label: ClassVar[str] = ""
    #: Field values only the person may set; an op from anyone else that sets one is held for the person. An empty
    #: tuple means every value of that field.
    person_only: ClassVar[dict[str, tuple[Any, ...]]] = {}
    #: Field groups whose values must be unique among live records of this kind.
    unique: ClassVar[tuple[tuple[str, ...], ...]] = ()
    #: How sensitive these records are: packets that include them go only to accounts allowed this level.
    data_level: ClassVar[str] = "internal"
    #: "core" (the default) or "own". A pack whose records are not workspace knowledge (a story's cast and plan)
    #: declares "own": the core's learning from inputs, new-term scan, first-name resolution against people and fact
    #: ranking into the workspace's facts then don't run on work about these records. The pack keeps its own plan
    #: records; its task kinds can still ask for the person's rules and lessons (`view.knowledge`).
    learning: ClassVar[str] = "core"
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

    @classmethod
    def needs_person(cls, field: str, value: Any) -> bool:
        """Whether only the person may set this field to this value (see `person_only`)."""
        values = cls.person_only.get(field)
        return values is not None and (not values or value in values)


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
    """The reference paths of a model, worked out once per model class (they depend only on the class) and copied for
    each caller. See `_ref_fields`."""
    return list(_ref_fields(model, _prefix, _depth))


@functools.cache
def _ref_fields(model: type[BaseModel], _prefix: str = "", _depth: int = 0) -> tuple[tuple[str, str], ...]:
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
        # A reference path names the key the record is stored under: the alias only for a model stored by alias.
        path = f"{_prefix}{info.alias if info.alias and model.model_config.get('serialize_by_alias') else name}"
        for meta in info.metadata:
            if isinstance(meta, RefTo):
                found.append((path, meta.kind))
        found += [(path, kind) for kind in single_in_union(info.annotation)]
        found += [
            (f"{path}[]", kind) for kind in in_list(info.annotation) if kind not in single_in_union(info.annotation)
        ]
        if _depth < MAX_REF_DEPTH - 1:
            for inner, many in nested(info.annotation):
                found += _ref_fields(inner, f"{path}[]." if many else f"{path}.", _depth + 1)
    return tuple(found)


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


class OnHold(BaseModel):
    """What an action waits for before it can go on. Set and cleared by the person; an action on hold is never due,
    overdue or chased."""

    model_config = ConfigDict(extra="forbid")

    waiting_for: str = Field(min_length=1, description="What it waits for, in plain words.")
    since: date = Field(description="The day it was put on hold.")


class Person(Record):
    """Someone the workspace works with or tracks. Added by `person.add`; role, org and why_they_matter change through
    `record.set`; the person edits the rest in the app."""

    record_kind: ClassVar[str] = "person"
    prefix: ClassVar[str] = "PER"
    layout: ClassVar[str | None] = "people/{full_name}"

    full_name: str = Field(min_length=1, description="The name shown wherever the person appears.")
    first_name: str | None = Field(
        None,
        description="The name a greeting to them uses, as they write it; empty means the first word of the full name.",
    )
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
    name_verified: bool = Field(
        False,
        description="True when the name's spelling came from the person, a signed header address or a record the "
        "person made; false when it was read from outside content and not yet confirmed.",
    )
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
    the person edits the rest in the app, and only the person sets its content levels, budget and priority (the
    assistant's `record.set` of the priority waits for the person)."""

    record_kind: ClassVar[str] = "project"
    prefix: ClassVar[str] = "PRJ"
    content_levels_field: ClassVar[str | None] = "content_levels"
    person_only: ClassVar[dict[str, tuple[Any, ...]]] = {"priority": ()}

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
    """Something a person will do. Added by `action.add`, closed by `action.close`, dropped by `action.drop`;
    `record.set` changes text, due and notes, `action.hold` or the person puts it on hold and the person takes it off,
    and sending a notice marks who was told. A chase adds a day to `followed_up`; closing records who did the work and
    who said it was done; dropping records why it is no longer needed and credits no one."""

    record_kind: ClassVar[str] = "action"
    prefix: ClassVar[str] = "ACT"
    layout: ClassVar[str | None] = "actions/{id}"

    project: str | None = Field(None, description="The id of the project it belongs to.")
    text: str = Field(min_length=1, description="What is to be done, starting with a verb.")
    owners: list[Owner] = Field(
        default_factory=list, description="The people who do it; required unless the action is held."
    )
    due: date | None = Field(None, description="The day it is due.")
    status: Literal["held", "open", "done", "dropped"] = Field(
        "open",
        description="held: waiting for an owner to be picked. open: to be done. done: finished. dropped: closed "
        "because it is no longer needed; never done, never credited, never chased.",
    )
    dropped_reason: str | None = Field(None, description="Why it was dropped, in plain words; set when it is dropped.")
    notes: str | None = Field(None, description="Extra detail about the action.")
    on_hold: OnHold | None = Field(
        None,
        description="Set while the action waits for something outside the person's control; the person sets and "
        "clears it. An action on hold is never counted as due, overdue or in need of a follow-up, and keeps its due "
        "date for when it comes off hold.",
    )
    told: dict[str, date] = Field(
        default_factory=dict, description="Who has been told about it: a person id mapped to the day they were told."
    )
    followed_up: dict[str, list[date]] = Field(
        default_factory=dict,
        description="Who has been chased about it: a person id mapped to the days they were chased, oldest first. "
        "A chase is not a notice (`told`) and never closes the action.",
    )
    done_by: list[str] = Field(
        default_factory=list, description="The ids of the people who did the work, set when the action is closed."
    )
    reported_by: str | None = Field(
        None, description="The id of the person who said it was done, set when the action is closed."
    )
    source: str | None = Field(None, description="The id of the source it came from, if any.")
    evidence: Evidence | None = Field(None, description="The words in the source that justify the action.")

    @model_validator(mode="after")
    def _owners_unless_held(self) -> Action:
        if self.status not in ("held", "dropped") and not self.owners:
            raise ValueError("an action needs at least one owner unless it is held for one or dropped")
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
    matters_for: str | None = Field(
        None,
        description="Which of the person's decisions, designs or dated items depends on the answer, by id or in "
        "words. A question to anyone but the person says it.",
    )
    dropped_reason: str | None = Field(None, description="Why the person dropped it, when they did.")


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
    fixed_fields: ClassVar[tuple[str, ...]] = (
        "received_at",
        "kind",
        "content_hash",
        "trust",
        "url",
        "watched",
        "author",
    )
    person_only: ClassVar[dict[str, tuple[Any, ...]]] = {"sensitivity": ()}

    received_at: datetime = Field(
        description="When the input arrived: a mail's own received time, else when it was handed in or first read."
    )
    kind: str = Field(description="How it arrived, such as pasted.")
    title: str = Field(description="A short name for it, shown in lists.")
    content_hash: str = Field(description="Hash of its text; the saved text is named by it in the sources folder.")
    trust: Literal["trusted", "untrusted"] = Field(
        description="untrusted: outside content, material to read and never instructions. trusted: the person's own."
    )
    projects: list[str] = Field(default_factory=list, description="The ids of the projects it is about.")
    url: str | None = Field(None, description="Where it came from, when it has an address.")
    author: str | None = Field(
        None,
        description="The id of the person whose words it is, when that is known: the person running the app for a note "
        "they wrote, the person it is reported about for a note that relays what someone else did or said.",
    )
    reported: bool = Field(
        False,
        description="A note that is content the person reports: typed on a button that relays someone else, or "
        "repeating what someone else said. Facts from it apply; a change to how the product behaves from it waits for "
        "the person.",
    )
    watched: Watched | None = Field(None, description="For an input a watcher found: where and what changed.")
    excerpts: Literal["allowed", "never"] = Field(
        "allowed",
        description="never: the person allows using this source but never quoting it beyond a word or two; checks "
        "that compare drafts with sources apply a stricter limit to it. Set by the person only.",
    )
    sensitivity: Literal["open", "internal", "restricted"] = Field(
        "internal",
        description="Its data level, how sensitive its text is: it goes only to AI accounts allowed this level. From "
        "the person's choice when they handed it in, or the watched source's setting. Only the person changes it.",
    )


class File(Record):
    """A file a person added or a program wrote. The bytes live in the workspace's files folder under their hash. A
    person adds one by upload or `file.add`; a new version is a new record that points at the one it replaces."""

    record_kind: ClassVar[str] = "file"
    prefix: ClassVar[str] = "FILE"
    person_only: ClassVar[dict[str, tuple[Any, ...]]] = {"sensitivity": ()}

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
    sensitivity: Literal["open", "internal", "restricted"] = Field(
        "internal",
        description="Its data level, how sensitive its content is: it goes only to AI accounts allowed this level. "
        "From the person's choice when they added it. Only the person changes it.",
    )


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
    bulk: bool | None = None
    categories: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)


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
    changed_at: str | None = Field(
        None,
        description="When the item last changed or arrived, as the source said (a file's modified time, say), so "
        "'Look at the last day' can find what is already there.",
    )
    event: SnapshotEvent | None = Field(None, description="For a calendar item: when and where, for the agenda.")
    message: SnapshotMessage | None = Field(None, description="For a mail item: from whom and when.")
    closed_by: str | None = Field(
        None, description="The triage rule that closed its latest change, so Today leaves it out (a newsletter, say)."
    )
    set_aside: dict[str, str] | None = Field(
        None,
        description="For a mail item set aside as not work: {section (personal or sales), rule, reason}, and "
        "{confirmed_at} once the person confirmed it (it is then deleted from the app after a short while). Today "
        "leaves it out and counts it until it is confirmed; the Set aside folder lists it.",
    )
    deleted: bool = Field(
        False,
        description="The person confirmed the message was rightly set aside and its content was deleted from the app. "
        "Only a marker is kept (the source, key, sender address, date, section and rule), so a later read doesn't "
        "hand it in again.",
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


class AuditEntry(Record):
    """One sign-in, sign-out or turning an add-on on or off, made from the screens. The engine writes it as it happens;
    nothing changes it. It never holds a token, a secret or the signed-in account's name."""

    record_kind: ClassVar[str] = "audit_entry"
    prefix: ClassVar[str] = "AUD"

    kind: Literal["sign_in", "sign_out", "plugin_on", "plugin_off"] = Field(
        description="What happened: signed in to a service, signed out of one (or lost the sign-in because its app "
        "registration changed), turned an add-on on, or turned one off."
    )
    subject: str = Field(description="The sign-in's name, or the add-on's name, as the add-on declares it.")
    label: str | None = Field(None, description="The sign-in's label for the person, when it has one.")
    detail: str | None = Field(None, description="A few plain words when the entry needs them.")
    at: datetime = Field(description="When it happened.")


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


class StopCause(BaseModel):
    """Why a request stopped, in a form the screen can act on."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["data_level", "no_person", "paused", "retry", "offline"] = Field(
        description="data_level: no AI account may see the request's material, and `accounts` would take it if "
        "allowed. no_person: the workspace has no person set yet, so the work waits before any AI call. paused: "
        "every account that could take it is waiting for a usage limit to reset (`account`, `until`); the request "
        "stays queued and runs again by itself then. retry: a run that gave no usable answer is tried again by "
        "itself at `until`. offline: no AI account could be reached for want of a network connection; the request "
        "stays queued since `since` and is looked at again at `until`, and no try is counted."
    )
    level: Literal["open", "internal", "restricted"] | None = Field(
        None, description="For data_level: the data level of the material."
    )
    accounts: list[str] = Field(
        default_factory=list,
        description='For data_level: the accounts ("provider/model") that would take the material if allowed its '
        "level, in the order the tier tries them.",
    )
    account: str | None = Field(None, description="For paused: the account whose limit resets first.")
    until: datetime | None = Field(
        None, description="For paused, retry and offline: when the request runs again by itself."
    )
    since: datetime | None = Field(None, description="For offline: when the request first found no network.")

    @model_serializer(mode="wrap")
    def _leave_out_unset_times(self, handler: Any) -> dict[str, Any]:
        """The account and the times are written only for the causes that have them."""
        data = handler(self)
        for key in ("account", "until", "since"):
            if data.get(key) is None:
                data.pop(key, None)
        return data


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
    cause: StopCause | None = Field(
        None,
        description="Why a request waits, when there is more to it than its words: for one waiting on the person, the "
        "cause the screen can offer an action for; for one queued, the time it is waiting for.",
    )
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
    set_aside: dict[str, str | None] | None = Field(
        None,
        description="For a watched mail item set aside as not work: {section, rule, reason}, and for one the person "
        "set aside after it was handed in, {from_state, from_waiting} to put it back. It is never queued for the "
        "assistant while this is set. This is work clears it.",
    )
    folded_into: str | None = Field(
        None, description="The newer request this one's change was folded into, so they are read in order, once."
    )
    attempts: int = Field(0, description="How many times the assistant has started on it.")
    retries: int = Field(
        0, description="How many times it was tried again by itself after a run that gave no usable answer."
    )
    created_at: datetime = Field(description="When the request was made.")
    changeset: str | None = Field(None, description="The id of the changeset the assistant proposed for it.")
    previous: str | None = Field(None, description="The request this one redoes after the PM sent it back.")
    superseded_by: str | None = Field(
        None,
        description="The later request that redid this one and applied, which retired this attempt: it is done, its "
        "held items and open proposals are closed, and nothing is run or shown for it again.",
    )
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
    applied: list[str] = Field(
        default_factory=list,
        description="The ids of the knowledge entries the run said it applied, kept only when the run was given them "
        "(its knowledge log). A checked citation, never the model's say-so alone.",
    )
    applied_dropped: int = Field(
        0, description="How many ids the run named as applied that it had not been given, which were left out."
    )
    missing: list[str] = Field(
        default_factory=list,
        description="What the run needed and no op could do, each in a few words, for the weekly missing-op list.",
    )
    first_on_account: str | None = Field(
        None,
        description="The name of the AI account when this was the first run on an account that stands in a "
        "fallback chain, so its cards can say so.",
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
    key: bool = Field(False, description="True for the facts that matter most, which are always shown first.")
    as_of: date | None = Field(
        None,
        description="The day the fact was true as of: the day the input it came from was received, unless a later "
        "input says otherwise.",
    )
    supersedes: str | None = Field(
        None,
        description="The id of the fact this one replaces. The older fact stays on record and is shown as replaced "
        "by this one.",
    )
    fixed_fields: ClassVar[tuple[str, ...]] = ("supersedes",)


class Scope(BaseModel):
    """What a rule or a piece of knowledge applies to: one shape for both. Empty lists mean no narrowing. `scope` is
    "workspace" (everywhere, less the projects in `except`) or "projects" (only those in `projects`)."""

    #: Stored by alias, so the key is `except`; a model that doesn't ask for this is stored by its field names.
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    task_kinds: list[str] = Field(default_factory=list, description="Task kinds it applies to; empty means all.")
    records: list[str] = Field(
        default_factory=list, description="Record types or type.field targets it applies to; empty means all."
    )
    filter: dict[str, Any] = Field(default_factory=dict, description="Exact field values narrowing the record targets.")
    projects: list[Annotated[str, RefTo("project")]] = Field(
        default_factory=list, description="With scope projects, the projects it is for."
    )
    people: list[Annotated[str, RefTo("person")]] = Field(
        default_factory=list, description="The people it is about; empty means anyone."
    )
    scope: Literal["workspace", "projects"] = Field(
        "workspace",
        description="workspace: everywhere, except the projects in `except`. projects: only the projects listed in "
        "`projects`.",
    )
    except_: list[Annotated[str, RefTo("project")]] = Field(
        default_factory=list,
        alias="except",
        description="With scope workspace, the projects it does not apply to. Dumped by alias, so the key is `except`.",
    )

    @model_validator(mode="before")
    @classmethod
    def _projects_mean_projects(cls, data: Any) -> Any:
        """Naming projects without a scope means the scope is those projects."""
        if isinstance(data, dict) and "scope" not in data and data.get("projects"):
            return {**data, "scope": "projects"}
        return data

    @model_validator(mode="after")
    def _coherent(self) -> Scope:
        if self.scope == "projects" and not self.projects:
            raise ValueError("a scope of projects names the projects it is for")
        if self.scope == "projects" and self.except_:
            raise ValueError("projects it doesn't apply to can be left out only from the whole workspace")
        if self.scope == "workspace" and self.projects:
            raise ValueError("name the projects only when the scope is those projects")
        return self


class Rule(Record):
    """A standing instruction the assistant follows, kept as a record so changing one has history and Undo. The
    starting set comes from the workspace's rules file; after that the records are the truth. Added by `rule.add`
    and ended by `rule.retire`."""

    record_kind: ClassVar[str] = "rule"
    prefix: ClassVar[str] = "RULE"
    layout: ClassVar[str | None] = "rules/{id}"
    unique: ClassVar[tuple[tuple[str, ...], ...]] = (("name",),)
    #: Where a rule came from and when never change after it is made.
    fixed_fields: ClassVar[tuple[str, ...]] = ("origin", "trust", "learned_at", "evidence", "more_evidence")

    name: str = Field(
        min_length=1,
        description="The rule's own name, which stage entry checks and the rules file refer to; never reused.",
    )
    text: str = Field("", description="The rule in the person's wording; it is also its explanation.")
    applies_to: Scope = Field(default_factory=Scope, description="What the rule applies to.")
    check: str | None = Field(
        None,
        description="A deterministic check that implements the rule; a rule with none is prose, and prose alone never "
        "lets a stage move.",
    )
    origin: Literal["seed", "person", "input", "assistant", "pack", "import"] = Field(
        description="Where it came from: seed (the starting set), person (the person's own words), input (content), "
        "assistant (its own generalization), pack or import."
    )
    trust: Literal["trusted", "untrusted"] = Field(
        "trusted", description="untrusted when it was proposed from outside content, until the person keeps it."
    )
    status: Literal["proposed", "active", "discarded", "expired", "retired"] = Field(
        "active",
        description="proposed: waiting for the person. active: in use. discarded: the person said no. expired: a "
        "proposal nobody reviewed in time. retired: it was active and no longer is.",
    )
    discard_reason: str | None = Field(
        None, description="Why it was discarded: what the person said, or that it was close to one they discarded."
    )
    more_evidence: list[KnowledgeEvidence] = Field(
        default_factory=list,
        description="What other proposals of the same rule were learned from, merged into this one.",
    )
    source: str | None = Field(None, description="Where it came from, in words.")
    evidence: Evidence | None = Field(None, description="The words that justify it, when it came from an input.")
    learned_at: datetime | None = Field(None, description="When the rule was learned or added.")
    kept_by: str | None = Field(None, description="The id of the person who made it active.")
    kept_at: datetime | None = Field(None, description="When it was made active.")
    constrains: list[str] = Field(
        default_factory=list,
        description="What it is about, so a run's log can tell a rule that applied from one that was only present: "
        "op kinds (`question.add`) or op fields (`action.add.owners`). Empty means nothing is checked, so the rule "
        "is only ever present.",
    )
    reviewed_at: datetime | None = Field(
        None,
        description="When the person last chose to keep it in a review; the clock for its next review starts here.",
    )


class CalendarEntry(Record):
    """Something dated in the app's own calendar: a day or a moment, or a range of days or moments. Added by
    `event.add` from what came in, and by plugins and the person later; never written to a calendar service."""

    record_kind: ClassVar[str] = "event"
    prefix: ClassVar[str] = "EVT"
    record_label: ClassVar[str] = "calendar entry"
    layout: ClassVar[str | None] = "calendar/{id}"

    title: str = Field(min_length=1, description="What the entry is, in a few words.")
    start: str = Field(
        description="When it starts: a day (2026-10-12) or a date-time (2026-10-12T09:30:00+01:00), in ISO 8601 text. "
        "A day means an all-day entry; a date-time with no offset is in the person's time zone."
    )
    end: str | None = Field(
        None,
        description="When it ends, in the same forms. Set, it makes a range, and the last day or moment is included.",
    )
    project: str | None = Field(None, description="The id of the project it is about, if any.")
    source: str | None = Field(None, description="The id of the source it came from, if any.")
    evidence: Evidence | None = Field(None, description="The words that justify it.")
    trust: Literal["trusted", "untrusted"] = Field(
        "trusted", description="untrusted when it came from outside content."
    )

    @model_validator(mode="after")
    def _readable_times(self) -> CalendarEntry:
        if (problem := entry_problem(self.start, self.end)) is not None:
            raise ValueError(problem)
        return self


def entry_time(value: str) -> date | datetime:
    """An ISO 8601 day or date-time. Raises ValueError for anything else."""
    text = value.strip()
    if len(text) == 10:
        return date.fromisoformat(text)
    return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)


def entry_problem(start: str, end: str | None) -> str | None:
    """Why a calendar entry's start and end can't stand, in plain words; None when they can."""
    try:
        first = entry_time(start)
    except ValueError:
        return f"{start!r} isn't a day such as 2026-10-12 or a date-time such as 2026-10-12T09:30:00+01:00"
    if end is None:
        return None
    try:
        last = entry_time(end)
    except ValueError:
        return f"{end!r} isn't a day such as 2026-10-12 or a date-time such as 2026-10-12T09:30:00+01:00"
    both_times = isinstance(first, datetime) and isinstance(last, datetime)
    if both_times and (first.tzinfo is None) == (last.tzinfo is None):
        before = last < first
    else:
        before = (last.date() if isinstance(last, datetime) else last) < (
            first.date() if isinstance(first, datetime) else first
        )
    return "it ends before it starts" if before else None


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


class KnowledgeEvidence(BaseModel):
    """What a piece of knowledge was learned from, kept apart from its own wording: the exact words, and the records
    that show where they came from."""

    model_config = ConfigDict(extra="forbid")

    quote: str | None = Field(
        None, min_length=1, description="The exact words in the source that the entry rests on, as they appear there."
    )
    source: Annotated[str | None, RefTo("source")] = Field(
        None, description="The input the words come from, when it was saved as one."
    )
    request: Annotated[str | None, RefTo("request")] = Field(
        None, description="The request whose work produced the entry."
    )
    signal: Annotated[str | None, RefTo("signal")] = Field(
        None, description="The correction the entry was learned from."
    )
    changeset: Annotated[str | None, RefTo("changeset")] = Field(
        None, description="The change the correction was about."
    )

    @model_validator(mode="after")
    def _says_something(self) -> KnowledgeEvidence:
        if not any((self.quote, self.source, self.request, self.signal, self.changeset)):
            raise ValueError("evidence names the words or the record they came from")
        return self


Rule.model_rebuild()


class KnowledgeRecord(Record):
    """What the four kinds of knowledge share (design 6.22). Not a record type itself. The assistant proposes an entry
    or the person states it; it guides runs only once active. `text` is the entry's own wording, in plain words;
    the evidence is kept beside it, never mixed in."""

    #: Where an entry came from and when never change after it is made.
    fixed_fields: ClassVar[tuple[str, ...]] = ("origin", "pack", "trust", "learned_at", "evidence", "more_evidence")

    text: str = Field(min_length=1, description="The entry in plain words: what is kept, and what is shown.")
    evidence: KnowledgeEvidence | None = Field(
        None, description="What it was learned from: the exact words and the records they came from."
    )
    more_evidence: list[KnowledgeEvidence] = Field(
        default_factory=list,
        description="What other proposals of the same entry were learned from, merged into this one.",
    )
    origin: Literal["person", "input", "assistant", "pack", "seed", "import"] = Field(
        description="person: the person's own words. input: proposed from content. assistant: the assistant's own "
        "generalization. pack: a pack's guidance (see `pack`). seed: shipped as a starting entry. import: loaded "
        "from a file."
    )
    pack: str | None = Field(None, description="For a pack's guidance, the pack's name.")
    trust: Literal["trusted", "untrusted"] = Field(
        "trusted", description="untrusted when it came from outside content."
    )
    learned_at: datetime = Field(description="When the entry was made.")
    status: Literal["proposed", "active", "discarded", "expired", "retired"] = Field(
        "proposed",
        description="proposed: waits for the person's Keep. active: guides runs. discarded: the person said no. "
        "expired: a proposal nobody reviewed in time. retired: was active, and no longer is.",
    )
    discard_reason: str | None = Field(None, description="Why the person discarded it, if they said.")
    kept_by: Annotated[str | None, RefTo("person")] = Field(
        None, description="The person who made it active, and so the author of its wording."
    )
    kept_at: datetime | None = Field(None, description="When it was made active.")
    applies_to: Scope = Field(default_factory=Scope, description="What it applies to.")

    @model_validator(mode="after")
    def _states_hold_together(self) -> KnowledgeRecord:
        if self.status == "active" and (self.kept_by is None or self.kept_at is None):
            raise ValueError("an active entry says who kept it and when")
        if self.discard_reason is not None and self.status != "discarded":
            raise ValueError("only a discarded entry has a reason for it")
        if (self.origin == "pack") != (self.pack is not None):
            raise ValueError("a pack's guidance names the pack, and nothing else does")
        return self


class Lesson(KnowledgeRecord):
    """What went wrong, why, and the guard that prevents a repeat. Added by `lesson.add`, changed by `lesson.update`,
    ended by `knowledge.retire`; the person keeps or discards a proposal."""

    record_kind: ClassVar[str] = "lesson"
    prefix: ClassVar[str] = "LES"

    guard: str | None = Field(None, description="The check or behavior that prevents a repeat, in plain words.")
    signal: Annotated[str | None, RefTo("signal")] = Field(None, description="The correction it came from.")


class GlossaryEntry(KnowledgeRecord):
    """A term or acronym and what it means here. Added by `glossary.add`, changed by `glossary.update`."""

    record_kind: ClassVar[str] = "glossary_entry"
    prefix: ClassVar[str] = "GLOSS"
    record_label: ClassVar[str] = "glossary entry"

    term: str = Field(min_length=1, description="The term, acronym or name as it is written.")
    meaning: str = Field(min_length=1, description="What it means.")
    confidence: Literal["confirmed", "assumed", "unknown"] = Field(
        "assumed", description="confirmed: someone who knows said so. assumed: a reasonable reading. unknown: not yet."
    )
    project: Annotated[str | None, RefTo("project")] = Field(
        None, description="The project it is about; none means it holds everywhere."
    )
    id_patterns: list[str] = Field(
        default_factory=list, description="Patterns for splitting compound ids that use the term."
    )


class RoutingEntry(KnowledgeRecord):
    """Who answers a kind of question, or who doesn't. Added by `routing.add`."""

    record_kind: ClassVar[str] = "routing_entry"
    prefix: ClassVar[str] = "ROUTE"
    record_label: ClassVar[str] = "routing entry"

    topic: str = Field(min_length=1, description="The topic, area or kind of question.")
    person: Annotated[str | None, RefTo("person")] = Field(None, description="The person it is about.")
    team: Annotated[str | None, RefTo("team")] = Field(None, description="The team it is about, instead of a person.")
    negative: bool = Field(False, description="True when they don't answer this.")
    look_up: str | None = Field(None, description="Where to look it up instead, in plain words.")

    @model_validator(mode="after")
    def _names_who(self) -> RoutingEntry:
        if self.person is None and self.team is None:
            raise ValueError("a routing entry names the person or the team")
        return self


class StyleNote(KnowledgeRecord):
    """What a recipient or audience wants or avoids in what is written for them. Added by `style.add`."""

    record_kind: ClassVar[str] = "style_note"
    prefix: ClassVar[str] = "STYLE"
    record_label: ClassVar[str] = "style note"

    audience: str = Field(min_length=1, description="A person's id, or a kind of audience in words.")
    observation: str = Field(min_length=1, description="What they want or avoid.")


class RunSearch(BaseModel):
    """One search a run asked for, and how many results came back."""

    model_config = ConfigDict(extra="forbid")

    words: str = Field("", description="The words searched for.")
    kinds: list[str] = Field(default_factory=list, description="The kinds searched: facts, inputs, records, knowledge.")
    results: int = Field(0, description="How many results came back.")


class RunKnowledge(BaseModel):
    """The knowledge log of one run (design 6.22): what it was given and what it searched for, so a bad result can be
    traced to knowledge that was missing or ignored."""

    model_config = ConfigDict(extra="forbid")

    given: list[str] = Field(
        default_factory=list, description="The ids of the knowledge entries and rules it was given."
    )
    left_out_by_scope: list[str] = Field(
        default_factory=list,
        description="The ids of rules and entries left out because their scope excludes the input.",
    )
    facts_left_out: int = Field(0, description="How many facts of the input's projects didn't fit the facts budget.")
    stable_chars: int = Field(0, description="The size of the knowledge sent with every run, in characters.")
    rules_applied: list[str] = Field(
        default_factory=list,
        description="The ids of the rules it was given that the run's changeset, the check on its output or a later "
        "correction shows were applied. Never the model's own claim.",
    )
    rules_present: list[str] = Field(
        default_factory=list, description="The ids of the rules it was given that were not shown to apply."
    )
    rules_moved: list[str] = Field(
        default_factory=list,
        description="The ids of the rules moved out of the always-sent part because it passed its size budget.",
    )
    searches: list[RunSearch] = Field(default_factory=list, description="The searches it asked for.")
    refused_checks: list[str] = Field(
        default_factory=list,
        description="The names of the checks that refused this call's answer, each once, including refusals the answer "
        "was sent back to fix.",
    )


class Run(Record):
    """One call to an AI provider. The engine writes it after each call, for usage and cost reports; nothing changes
    it."""

    record_kind: ClassVar[str] = "run"
    prefix: ClassVar[str] = "RUN"

    request: str | None = Field(
        None,
        description="The id of the request the call was made for; none for a call that serves no request (sorting "
        "mail headers).",
    )
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
    knowledge: RunKnowledge | None = Field(None, description="What it was given from what was learned, and searched.")


class Signal(Record):
    """A correction by the PM, the measure of how well the assistant does. The engine records one when the person
    sends work back, undoes it, edits a draft or similar; nothing changes it."""

    record_kind: ClassVar[str] = "signal"
    prefix: ClassVar[str] = "SIG"

    kind: Literal[
        "sent_back",
        "undone",
        "dropped",
        "reworded",
        "pulled_back",
        "draft_edited",
        "held_declined",
        "routed",
        "set_aside",
        "put_on_hold",
        "taken_off_hold",
        "kept",
        "discarded",
        "retired",
        "narrowed",
        "just_this_time",
        "change_requested",
        "answered_assistant",
    ] = Field(
        description="What the person did: sent_back, undone, dropped or reworded something the assistant made; "
        "pulled_back an automatic change; draft_edited a draft before approving it; held_declined a held op; "
        "routed, said who a name or an owner is; set_aside, moved a mail item to the Set aside folder by hand; "
        "put_on_hold or taken_off_hold, changed whether an action waits for something; kept, discarded or retired "
        "a piece of what the assistant learned (a lesson, glossary entry, routing entry, style note or standing rule); "
        "narrowed, limited what a rule applies to; just_this_time, said a proposed piece of learning was right for "
        "this case but is not a pattern; change_requested, asked for something the assistant made to be changed, in a "
        "note on its row; answered_assistant, wrote an answer to a question the assistant asked them."
    )
    refs: list[str] = Field(default_factory=list, description="The ids of the records the correction is about.")
    run: str | None = Field(None, description="The id of the AI run whose work was corrected, when there was one.")
    changeset: str | None = Field(
        None, description="The id of the changeset the correction is about, when there is one."
    )
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
        Rule,
        CalendarEntry,
        Note,
        Lesson,
        GlossaryEntry,
        RoutingEntry,
        StyleNote,
        Run,
        Signal,
        File,
        ToolRun,
        JobRun,
        SettingChange,
        AuditEntry,
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

#: The references in the evidence merged into an entry from other proposals of it.
MORE_EVIDENCE_REFERENCES: list[tuple[str, str]] = [
    ("more_evidence[].source", "source"),
    ("more_evidence[].request", "request"),
    ("more_evidence[].signal", "signal"),
    ("more_evidence[].changeset", "changeset"),
]

#: The references every kind of knowledge has: what it was learned from, who kept it, what it applies to.
KNOWLEDGE_REFERENCES: list[tuple[str, str]] = [
    ("evidence.source", "source"),
    ("evidence.request", "request"),
    ("evidence.signal", "signal"),
    ("evidence.changeset", "changeset"),
    *MORE_EVIDENCE_REFERENCES,
    ("kept_by", "person"),
    ("applies_to.projects[]", "project"),
    ("applies_to.people[]", "person"),
    ("applies_to.except[]", "project"),
]

#: Fields that hold ids of other records, per kind, as (field, kind it points to). Used to check references.
REFERENCES: dict[str, list[tuple[str, str]]] = {
    "person": [("team", "team"), ("org", "organization")],
    "team": [("members[]", "person")],
    "project": [("owner", "person"), ("parent", "project")],
    "action": [
        ("project", "project"),
        ("owners[].person", "person"),
        ("owners[].team", "team"),
        ("done_by[]", "person"),
        ("reported_by", "person"),
        ("source", "source"),
    ],
    "question": [("to", "person"), ("projects[]", "project"), ("source", "source")],
    "source": [("projects[]", "project"), ("author", "person")],
    "request": [
        ("source", "source"),
        ("changeset", "changeset"),
        ("previous", "request"),
        ("follows", "changeset"),
        ("folded_into", "request"),
        ("superseded_by", "request"),
        ("project", "project"),
    ],
    "changeset": [("request", "request"), ("run", "run")],
    "fact": [("project", "project"), ("source", "source"), ("supersedes", "fact")],
    "rule": [
        *MORE_EVIDENCE_REFERENCES,
        ("kept_by", "person"),
        ("applies_to.projects[]", "project"),
        ("applies_to.people[]", "person"),
        ("applies_to.except[]", "project"),
    ],
    "signal": [("run", "run"), ("changeset", "changeset")],
    "event": [("project", "project"), ("source", "source")],
    "note": [("project", "project"), ("source", "source")],
    "lesson": [*KNOWLEDGE_REFERENCES, ("signal", "signal")],
    "glossary_entry": [*KNOWLEDGE_REFERENCES, ("project", "project")],
    "routing_entry": [*KNOWLEDGE_REFERENCES, ("person", "person"), ("team", "team")],
    "style_note": list(KNOWLEDGE_REFERENCES),
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
