"""Core record types.

Records refer to each other by id, never by name; names live on their own record and are rendered where shown.
Each type has a kind (its table name in exports) and an id prefix. Plugins add record types through the plugin API.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    """Base for every stored record."""

    model_config = ConfigDict(extra="forbid")

    record_kind: ClassVar[str]
    prefix: ClassVar[str]

    id: str
    ext: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Fields added by plugins, by plugin name.")


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


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


#: Record kind to its model. The order is the export order.
REGISTRY: dict[str, type[Record]] = {
    model.record_kind: model for model in (Person, Team, Project, Action, Question, Source)
}

#: Fields that hold ids of other records, per kind, as (field, kind it points to). Used to check references.
REFERENCES: dict[str, list[tuple[str, str]]] = {
    "person": [("team", "team")],
    "team": [("members[]", "person")],
    "project": [("owner", "person")],
    "action": [("project", "project"), ("owners[].person", "person"), ("owners[].team", "team")],
    "question": [("to", "person"), ("projects[]", "project")],
    "source": [("projects[]", "project")],
}


def model_for(kind: str) -> type[Record]:
    try:
        return REGISTRY[kind]
    except KeyError:
        raise KeyError(f"unknown record kind {kind!r}") from None
