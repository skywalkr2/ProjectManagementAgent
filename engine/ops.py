"""Op types: what the assistant may propose, with each op's tier and shape (design 6.7).

The AI writes ops in this shape. People may be named by full name, alias or id; the applier resolves names to ids.
Evidence is the exact words from the input that justify the op.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator, model_validator

Tier = Literal["data", "outbound", "system"]


class OpModel(BaseModel):
    """Base for every op: one change the applier checks, records in the ledger and can undo. A plugin's op subclasses
    it with a single literal `op` id and a `writes` class variable; see `Registrar.op`.

    An op that doesn't match its model (a missing, unknown or wrongly typed field) makes the whole answer or proposal
    unreadable: an AI answer goes back to the assistant with the reason for a fix round, and a person action fails with
    the reason. An op that matches but is refused (by a validator, a rule, or StoreError in its apply) is refused
    alone, and the others still apply."""

    model_config = ConfigDict(extra="forbid")

    group: str | None = Field(None, description="Ops that must be undone together share a group name.")

    def describe(self) -> str | None:
        """A one-line plain label for this op in review lists; plugin ops may override it. A plugin op may instead
        define `describe(self, view)` to read records for the label (a read view of core and its own records). The
        label is made against the records as they stand before the changeset applies."""
        return None


class EvidenceIn(BaseModel):
    """The exact words from the input that justify a claim; the applier checks they are there."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=3, description="The exact words from the input that justify this op.")

    @model_validator(mode="before")
    @classmethod
    def _plain_quote(cls, value: Any) -> Any:
        """Accept the shapes models commonly write for the same thing: a bare string, or extra keys beside the quote.
        Only the quote is kept, and it is still checked word for word against the input."""
        if isinstance(value, str):
            return {"quote": value}
        if isinstance(value, dict) and set(value) - {"quote"}:
            if "quote" in value:
                return {"quote": value["quote"]}
            texts = [v for v in value.values() if isinstance(v, str)]
            if len(texts) == 1:
                return {"quote": texts[0]}
        return value


class LinkIn(BaseModel):
    """A labeled web link to attach to a question."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="What the link is, in words for the reader.")
    url: str = Field(description="The address to open; a question to someone else needs one the recipient can open.")


class NoteOp(OpModel):
    """Keep something from the input that isn't a fact, action or question. Creates a note record."""

    op: Literal["note"]
    text: str = Field(min_length=1, description="What to keep.")
    project: str | None = Field(None, description="Project id, if the note is about one.")


class FactOp(OpModel):
    """Record something the input states as true. Creates a fact record; evidence is required."""

    op: Literal["fact"]
    text: str = Field(min_length=1, description="The fact, as a statement.")
    project: str | None = Field(None, description="Project id, if the fact is about one.")
    evidence: EvidenceIn = Field(description="The exact words from the input that justify this op.")


class RecordSetOp(OpModel):
    """Change one field of an existing record. Allowed fields: project status, phase, target, priority, summary, parent
    (the id of the project it belongs to), language (a tag such as en-US) and owner (a person's id);
    action text, due and notes; question title and text; person role, org and why_they_matter. The new value must
    be valid for the field. Evidence is required for due, status, owners, target and owner."""

    op: Literal["record.set"]
    kind: Literal["project", "action", "question", "person"] = Field(description="The kind of record to change.")
    id: str = Field(description="The id of the record to change.")
    field: str = Field(description="The field to set; only the fields listed for this kind are allowed.")
    value: Any = Field(description="The new value, in the field's own type; a date is written YYYY-MM-DD.")
    evidence: EvidenceIn | None = Field(
        None, description="The words that justify the change; see the fields needing it."
    )


class RecordLogOp(OpModel):
    """Add a dated line to a project's update log. The line is dated the day it is applied."""

    op: Literal["record.log"]
    project: str = Field(description="The id of the project whose log gets the line.")
    text: str = Field(min_length=1, description="The line to add.")


class ActionAddOp(OpModel):
    """A new action: something a person will do. Owners are people (name or id); leave empty if nobody is named.
    With no owner the action is held and the PM is asked to pick one. Evidence is required."""

    op: Literal["action.add"]
    text: str = Field(
        min_length=1, description="A verb that does something, e.g. 'Send the final file to the printer'."
    )
    owners: list[str] = Field(
        default_factory=list,
        description="The people who do it, each by name or id; empty if nobody is named. A name that isn't one "
        "known person waits for the PM to say who.",
    )
    due: date | None = Field(None, description="The day it is due, if one is stated.")
    project: str | None = Field(None, description="Project id, if the action belongs to one.")
    evidence: EvidenceIn = Field(description="The exact words from the input that justify this op.")


class ActionCloseOp(OpModel):
    """Close an open action the input says is done. Refused if the action doesn't exist or is already done; evidence
    is required."""

    op: Literal["action.close"]
    id: str = Field(description="The id of the open action that is done.")
    evidence: EvidenceIn = Field(description="The exact words from the input that justify this op.")


class QuestionAddOp(OpModel):
    """A question for a person, written for its reader. Decisions are questions to the PM. A question to anyone else
    needs at least one link the recipient can open."""

    op: Literal["question.add"]
    to: str = Field(description="The person, by name or id.")
    title: str = Field(min_length=1, description="The question in one line.")
    text: str = Field("", description="The detail the reader needs to answer.")
    links: list[LinkIn] = Field(default_factory=list, description="Pages the reader can open to see what it is about.")
    project: str | None = Field(None, description="Project id, if the question is about one.")
    kind: Literal["question", "decision"] = Field(
        "question", description="question: an ordinary question. decision: a choice for the PM to make."
    )


class QuestionDoneOp(OpModel):
    """Record the answer to an open question and close it. Also records the answer as a fact. Refused if the question
    doesn't exist or is already closed; evidence is required."""

    op: Literal["question.done"]
    id: str = Field(description="The id of the open question that was answered.")
    answer: str = Field(min_length=1, description="The answer, in words.")
    evidence: EvidenceIn = Field(description="The exact words from the input that justify this op.")


class PersonAddOp(OpModel):
    """Someone the input names who isn't on file yet. From outside content it waits for the PM to confirm."""

    op: Literal["person.add"]
    full_name: str = Field(min_length=1, description="The person's full name.")
    role: str | None = Field(None, description="Their job or part in the work, if stated.")
    org: str | None = Field(None, description="The organization they work for, if stated.")
    aliases: list[str] = Field(default_factory=list, description="Other names the input uses for them.")


class RecordRef(BaseModel):
    """A reference to one record by kind and id."""

    model_config = ConfigDict(extra="forbid")
    kind: str = Field(description="The record kind, such as project or a plugin's own kind.")
    id: str = Field(description="The record's id.")


class StageMoveOp(OpModel):
    """Propose entering a configured stage. Always waits for the person's confirmation."""

    op: Literal["stage.move"] = "stage.move"
    record: RecordRef = Field(description="The record to move.")
    to: str = Field(min_length=1, description="The id of the stage to enter.")
    read_version: int = Field(
        ge=1, description="The version of the record that was read; the move fails if it changed."
    )


class RecordDeleteOp(OpModel):
    """Delete a record. Refused while another live record refers to it, or if it changed since it was read; Undo brings
    it back. A system op: from the assistant it waits for the person; never part of extracting notes."""

    op: Literal["record.delete"] = "record.delete"
    record: RecordRef = Field(description="The record to delete.")
    read_version: int = Field(
        ge=1, description="The version of the record that was read; the delete fails if it changed."
    )


class FileAddOp(OpModel):
    """Record a file whose bytes the host already stored under their hash, such as one a person action built. Only
    person actions offer it; Undo removes the record (the bytes stay, unused). The record is marked untrusted and as
    written by a program."""

    op: Literal["file.add"] = "file.add"
    id: str = Field(pattern=r"^FILE-[0-9]+$", description="The id the host set aside for this file.")
    name: str = Field(min_length=1, description="The file's name, for showing and downloading.")
    media_type: str = Field(description="What kind of content it is, such as image/png.")
    size: int = Field(ge=0, description="Size in bytes; it must match the stored bytes.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the bytes, which must already be stored.")
    file_kind: str = Field("attachment", description="What the file is for: the core's attachment or a declared kind.")
    project: str | None = Field(None, description="The project it belongs to; none means the whole workspace.")
    meta: dict[str, Any] = Field(default_factory=dict, description="Details the file kind asks for, validated on add.")
    replaces: str | None = Field(None, description="The earlier file this one is a new version of.")

    def describe(self) -> str | None:
        return f"Add the file {self.name}"


class ProjectAddOp(OpModel):
    """Start a new project, optionally inside another (a book in its series). A system op: from the assistant it waits
    for the person. The name must not be another live project's."""

    op: Literal["project.add"] = "project.add"
    name: str = Field(min_length=1, description="The project's name.")
    summary: str | None = Field(None, description="A short description of what the project is.")
    parent: str | None = Field(None, description="The id of the project it belongs to, if any.")
    language: str | None = Field(
        None, description="Its language tag, if it differs from its parent's or the workspace's."
    )
    children: list[str] = Field(
        default_factory=list,
        description="Ids of existing projects to move inside the new one (books into a new series), in the same op.",
    )

    def describe(self) -> str | None:
        return f"Start the project {self.name}"


class RecordEditOp(OpModel):
    """The person's own change to fields of any record (core or a plugin's), such as an edit made to the record's
    file in the synced folder: it waits for the person's review there, and applies as theirs. Long text, the stage,
    the id and plugin extension fields aren't changed this way. Only the person uses it."""

    op: Literal["record.edit"] = "record.edit"
    record: RecordRef = Field(description="The record to change.")
    fields: dict[str, Any] = Field(description="The new values, by field name.")
    read_version: int = Field(ge=1, description="The record's version the edit was made from.")

    def describe(self) -> str | None:
        return f"Change {', '.join(sorted(self.fields))} of {self.record.kind} {self.record.id}"


class TextEditOp(OpModel):
    """The person's own new text for a long text field, written here: it becomes the field's text at once, with the
    person as author of every passage it changes. Only the person (an edit on screen or their own action) uses it."""

    op: Literal["text.edit"] = "text.edit"
    record: RecordRef = Field(description="The record whose field it is.")
    field: str = Field(description="The long text field.")
    text: str = Field(description="The whole new text.")

    def describe(self) -> str | None:
        return f"Change the text of {self.record.kind} {self.record.id}"


class TextProposeOp(OpModel):
    """The person's own work on a long text field arriving from outside (a working copy handed back, a file edited
    elsewhere): a pending version for review, made from version `base` (the current one if unset)."""

    op: Literal["text.propose"] = "text.propose"
    record: RecordRef = Field(description="The record whose field it is.")
    field: str = Field(description="The long text field.")
    text: str = Field(description="The whole proposed text.")
    base: int | None = Field(None, description="The number of the version it was made from.")
    note: str | None = Field(None, description="Where it came from, for the review.")
    unmapped: list[str] = Field(
        default_factory=list, description="What couldn't be mapped back into the text, shown beside the proposal."
    )

    def describe(self) -> str | None:
        return f"Propose new text for {self.record.kind} {self.record.id}"


class TextAcceptOp(OpModel):
    """Accept a pending version, change by change: the result becomes the field's text, with authorship following the
    choices. Changes not listed are accepted; rejecting every change discards it. Only the person uses it."""

    op: Literal["text.accept"] = "text.accept"
    version: str = Field(description="The id of the pending text version.")
    read_version: int = Field(ge=1, description="The version of that record that was reviewed.")
    choices: dict[str, Literal["accept", "reject"]] = Field(
        default_factory=dict, description="Per change id (c1, c2, ...): accept or reject."
    )

    def describe(self) -> str | None:
        return f"Accept text version {self.version}"


class TextDiscardOp(OpModel):
    """Set a pending version aside without changing the field. Only the person uses it."""

    op: Literal["text.discard"] = "text.discard"
    version: str = Field(description="The id of the pending text version.")
    read_version: int = Field(ge=1, description="The version of that record that was reviewed.")

    def describe(self) -> str | None:
        return f"Set aside text version {self.version}"


class TextDraftOp(OpModel):
    """The assistant's draft for a long text field, made by the core from a draft task's prose answer: a pending
    version for the person's review, never the field's text until accepted. Draft tasks only."""

    op: Literal["text.draft"] = "text.draft"
    record: RecordRef = Field(description="The record whose field it is.")
    field: str = Field(description="The long text field.")
    text: str = Field(description="The whole drafted text.")
    base: int | None = Field(None, description="The number of the version it was made from.")
    run: str | None = Field(None, description="The AI run that wrote it.")
    paragraph_map: list[dict[str, Any]] = Field(
        default_factory=list,
        description="For an anchored draft, per paragraph in order, the base units it came from: {from: [p1, ...]}.",
    )
    questions: list[str] = Field(
        default_factory=list, description="Questions for the person the draft ended with, shown beside it."
    )

    def describe(self) -> str | None:
        return f"Draft new text for {self.record.kind} {self.record.id}"


Op = Annotated[
    NoteOp
    | FactOp
    | RecordSetOp
    | RecordLogOp
    | ActionAddOp
    | ActionCloseOp
    | QuestionAddOp
    | QuestionDoneOp
    | PersonAddOp
    | StageMoveOp
    | RecordDeleteOp
    | FileAddOp
    | ProjectAddOp
    | RecordEditOp
    | TextEditOp
    | TextProposeOp
    | TextAcceptOp
    | TextDiscardOp
    | TextDraftOp,
    Field(discriminator="op"),
]

OP_MODELS: dict[str, type[OpModel]] = {
    "note": NoteOp,
    "fact": FactOp,
    "record.set": RecordSetOp,
    "record.log": RecordLogOp,
    "action.add": ActionAddOp,
    "action.close": ActionCloseOp,
    "question.add": QuestionAddOp,
    "question.done": QuestionDoneOp,
    "person.add": PersonAddOp,
    "stage.move": StageMoveOp,
    "record.delete": RecordDeleteOp,
    "file.add": FileAddOp,
    "project.add": ProjectAddOp,
    "record.edit": RecordEditOp,
    "text.edit": TextEditOp,
    "text.propose": TextProposeOp,
    "text.accept": TextAcceptOp,
    "text.discard": TextDiscardOp,
    "text.draft": TextDraftOp,
}

#: Ops only the person makes: from anyone else they are refused, never held.
PERSON_ONLY_OPS = {"text.edit", "text.accept", "text.discard", "record.edit"}

TIERS: dict[str, Tier] = {name: "data" for name in OP_MODELS} | {"record.delete": "system", "project.add": "system"}

#: Ops whose evidence is required (record.set requires it for the fields in EVIDENCE_FIELDS).
NEEDS_EVIDENCE = {"fact", "action.add", "action.close", "question.done"}
EVIDENCE_FIELDS = {"due", "status", "owners", "target", "owner"}

#: Fields record.set may change, per kind.
SETTABLE: dict[str, set[str]] = {
    "project": {"status", "phase", "target", "priority", "summary", "parent", "language", "owner"},
    "action": {"text", "due", "notes"},
    "question": {"title", "text"},
    "person": {"role", "org", "why_they_matter"},
}


class ChangesetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    ops: list[Any] = Field(default_factory=list)

    @field_validator("ops", mode="before")
    @classmethod
    def parse_ops(cls, values: Any, info: ValidationInfo) -> list[OpModel]:
        models = (info.context or {}).get("op_models", OP_MODELS)
        if not isinstance(values, list):
            raise ValueError("ops must be a list")
        parsed = []
        for value in values:
            data = value.model_dump() if isinstance(value, OpModel) else value
            name = data.get("op") if isinstance(data, dict) else None
            if name not in models:
                raise ValueError(f"unknown op {name!r}")
            parsed.append(models[name].model_validate(data))
        return parsed


CHANGESET = TypeAdapter(ChangesetIn)


def schema_for(op_names: list[str], registry: dict | None = None) -> dict[str, Any]:
    """The JSON schema of a changeset limited to these ops, so a task is asked for exactly what it may return."""
    models = [(registry or OP_MODELS)[n] for n in op_names]
    return {
        "type": "object",
        "required": ["summary", "ops"],
        "properties": {
            "summary": {"type": "string"},
            "ops": {"type": "array", "items": {"anyOf": [m.model_json_schema() for m in models]}},
        },
    }


def reference_for(op_names: list[str], registry: dict | None = None) -> str:
    """A readable op reference for the prompt: each op, what it's for and its fields."""
    lines = []
    for name in op_names:
        model = (registry or OP_MODELS)[name]
        fields = []
        for key, info in model.model_fields.items():
            if key in ("op", "group"):
                continue
            required = info.is_required()
            fields.append(f"{key}{'' if required else '?'}")
        doc = (model.__doc__ or "").strip()
        lines.append(f'- "{name}": {doc} Fields: {", ".join(fields)}.')
    return "\n".join(lines)
