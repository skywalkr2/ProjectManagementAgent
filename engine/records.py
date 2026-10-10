"""Core record types.

Records refer to each other by id, never by name; names live on their own record and are rendered where shown.
Each type has a kind (its table name in exports) and an id prefix. Plugins add record types through the plugin API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    """Base for every stored record."""

    model_config = ConfigDict(extra="forbid")

    record_kind: ClassVar[str]
    prefix: ClassVar[str]
    #: Field values only the person may set; an op from anyone else that sets one is held for the person.
    person_only: ClassVar[dict[str, tuple[Any, ...]]] = {}
    #: Field groups whose values must be unique among live records of this kind.
    unique: ClassVar[tuple[tuple[str, ...], ...]] = ()
    #: How sensitive these records are: packets that include them go only to accounts allowed this level.
    data_level: ClassVar[str] = "internal"

    id: str
    stage: str | None = Field(None, description="Current configured stage id; wording lives in stages.yaml.")
    ext: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Fields added by plugins, by plugin name.")


@dataclass(frozen=True)
class RefTo:
    """Marks a field as holding the id of another record: `Annotated[str | None, RefTo("project")]`."""

    kind: str


def ref_fields(model: type[BaseModel]) -> list[tuple[str, str]]:
    """(field, kind it points to) for every field marked with RefTo."""
    found = []
    for name, info in model.model_fields.items():
        for meta in info.metadata:
            if isinstance(meta, RefTo):
                found.append((name, meta.kind))
    return found


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class Evidence(BaseModel):
    """The exact words in a source that justify a claim."""

    model_config = ConfigDict(extra="forbid")

    source: str
    quote: str = Field(min_length=1)


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: date
    text: str = Field(min_length=1)


class Owner(BaseModel):
    """An action owner: always a person, optionally with the team they act for."""

    model_config = ConfigDict(extra="forbid")

    person: str
    team: str | None = None


class Person(Record):
    record_kind: ClassVar[str] = "person"
    prefix: ClassVar[str] = "PER"

    full_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    role: str | None = None
    team: str | None = None
    org: str | None = None
    how_to_reach: dict[str, str] = Field(default_factory=dict)
    why_they_matter: str | None = None
    track_only: bool = False
    status: Literal["active", "left"] = "active"


class Team(Record):
    record_kind: ClassVar[str] = "team"
    prefix: ClassVar[str] = "TEAM"

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)


class Project(Record):
    record_kind: ClassVar[str] = "project"
    prefix: ClassVar[str] = "PRJ"

    name: str = Field(min_length=1)
    group: str | None = None
    status: str | None = None
    phase: str | None = None
    target: date | None = None
    priority: str | None = None
    summary: str | None = None
    owner: str | None = None
    links: list[Link] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)


class Action(Record):
    record_kind: ClassVar[str] = "action"
    prefix: ClassVar[str] = "ACT"

    project: str | None = None
    text: str = Field(min_length=1)
    owners: list[Owner] = Field(default_factory=list)
    due: date | None = None
    status: Literal["held", "open", "done"] = "open"
    notes: str | None = None
    told: dict[str, date] = Field(default_factory=dict)
    source: str | None = None
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def _owners_unless_held(self) -> Action:
        if self.status != "held" and not self.owners:
            raise ValueError("an action needs at least one owner unless it is held for one")
        return self


class Question(Record):
    record_kind: ClassVar[str] = "question"
    prefix: ClassVar[str] = "Q"

    to: str
    title: str = Field(min_length=1)
    text: str = ""
    links: list[Link] = Field(default_factory=list)
    kind: Literal["question", "decision", "action-notice", "routing", "impact"] = "question"
    projects: list[str] = Field(default_factory=list)
    batch: Literal["now", "later"] = "now"
    status: Literal["open", "sent", "answered", "dropped"] = "open"
    sent_at: datetime | None = None
    answer: str | None = None
    source: str | None = None
    options: list[str] = Field(default_factory=list, description="Choices offered, for routing and decisions.")
    resolves: dict[str, Any] | None = Field(None, description="What answering it releases, e.g. a held op.")


class Source(Record):
    record_kind: ClassVar[str] = "source"
    prefix: ClassVar[str] = "SRC"

    received_at: datetime
    kind: str
    title: str
    content_hash: str
    trust: Literal["trusted", "untrusted"]
    projects: list[str] = Field(default_factory=list)
    url: str | None = None


class File(Record):
    """A file a person added or a program wrote. The bytes live in the workspace's files folder under their hash."""

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
    trust: Literal["trusted", "untrusted"] = "trusted"
    replaces: str | None = Field(None, description="The earlier file this one is a new version of.")
    added_at: datetime


class StageStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    record: str
    stage: str
    changeset: str | None = None


class Request(Record):
    """A unit of work for the assistant."""

    record_kind: ClassVar[str] = "request"
    prefix: ClassVar[str] = "REQ"

    task: str
    stage_start: StageStart | None = Field(None, description="The stage entry that requested this task.")
    approval: Literal["required", "granted"] | None = Field(
        None,
        description="Needs the person's go before dispatch: stage tasks, and runs above the amount to confirm.",
    )
    estimate_usd: float | None = Field(None, description="What the run was estimated to cost when it asked for a go.")
    note: str | None = None
    source: str | None = None
    origin: Literal["pm", "input", "schedule"]
    state: Literal["queued", "running", "review", "done", "needs_you", "failed"] = "queued"
    waiting: str | None = Field(None, description="Why it is waiting and until when, in plain words.")
    attempts: int = 0
    created_at: datetime
    changeset: str | None = None
    previous: str | None = Field(None, description="The request this one redoes after the PM sent it back.")
    dismissed: bool = Field(
        False, description="The PM set this aside without trying again; it no longer counts as needing attention."
    )
    dismissed_from: Literal["queued", "running", "review", "done", "needs_you", "failed"] | None = Field(
        None, description="The state the request was in when it was dismissed, put back by undoing the dismissal."
    )


class Changeset(Record):
    """What the assistant proposed for one request, how it was checked and what was applied."""

    record_kind: ClassVar[str] = "changeset"
    prefix: ClassVar[str] = "CS"

    request: str
    summary: str = ""
    ops: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["applied", "held", "rejected", "undone", "partly_undone"]
    problems: list[dict[str, Any]] = Field(default_factory=list)
    trust: Literal["trusted", "untrusted"]
    reviewed: bool = False
    run: str | None = None
    created_at: datetime


class Fact(Record):
    record_kind: ClassVar[str] = "fact"
    prefix: ClassVar[str] = "FACT"

    text: str = Field(min_length=1)
    project: str | None = None
    source: str | None = None
    evidence: Evidence | None = None
    trust: Literal["trusted", "untrusted"] = "trusted"


class Note(Record):
    record_kind: ClassVar[str] = "note"
    prefix: ClassVar[str] = "NOTE"

    text: str = Field(min_length=1)
    project: str | None = None
    source: str | None = None
    trust: Literal["trusted", "untrusted"] = "trusted"


class Run(Record):
    """One call to an AI provider."""

    record_kind: ClassVar[str] = "run"
    prefix: ClassVar[str] = "RUN"

    request: str
    task: str
    provider: str
    model: str
    tier: str
    input_chars: int = 0
    output_chars: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cost_usd: float | None = None
    seconds: float = 0.0
    outcome: Literal["ok", "invalid_output", "error"]
    error_kind: str | None = None
    error_detail: str | None = None
    started_at: datetime


class Signal(Record):
    """A correction by the PM, the measure of how well the assistant does."""

    record_kind: ClassVar[str] = "signal"
    prefix: ClassVar[str] = "SIG"

    kind: Literal["sent_back", "undone", "dropped", "reworded", "pulled_back", "draft_edited", "held_declined"]
    refs: list[str] = Field(default_factory=list)
    note: str | None = None
    at: datetime


#: Record kind to its model. The order is the export order.
REGISTRY: dict[str, type[Record]] = {
    model.record_kind: model
    for model in (Person, Team, Project, Action, Question, Source, Request, Changeset, Fact, Note, Run, Signal, File)
}

#: Fields that hold ids of other records, per kind, as (field, kind it points to). Used to check references.
REFERENCES: dict[str, list[tuple[str, str]]] = {
    "person": [("team", "team")],
    "team": [("members[]", "person")],
    "project": [("owner", "person")],
    "action": [("project", "project"), ("owners[].person", "person"), ("owners[].team", "team"), ("source", "source")],
    "question": [("to", "person"), ("projects[]", "project"), ("source", "source")],
    "source": [("projects[]", "project")],
    "request": [("source", "source"), ("changeset", "changeset"), ("previous", "request")],
    "changeset": [("request", "request"), ("run", "run")],
    "fact": [("project", "project"), ("source", "source")],
    "note": [("project", "project"), ("source", "source")],
    "run": [("request", "request")],
    "file": [("project", "project"), ("replaces", "file")],
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
