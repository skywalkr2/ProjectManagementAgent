"""Op types: what the assistant may propose, with each op's tier and shape (design 6.7).

The AI writes ops in this shape. People may be named by full name, alias or id; the applier resolves names to ids.
Evidence is the exact words from the input that justify the op.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator

Tier = Literal["data", "outbound", "system"]


class OpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: str | None = Field(None, description="Ops that must be undone together share a group name.")


class EvidenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=3, description="The exact words from the input that justify this op.")


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class NoteOp(OpModel):
    """Keep something from the input that isn't a fact, action or question."""

    op: Literal["note"]
    text: str = Field(min_length=1)
    project: str | None = Field(None, description="Project id, if the note is about one.")


class FactOp(OpModel):
    """Record something the input states as true."""

    op: Literal["fact"]
    text: str = Field(min_length=1)
    project: str | None = None
    evidence: EvidenceIn


class RecordSetOp(OpModel):
    """Change one field of an existing record."""

    op: Literal["record.set"]
    kind: Literal["project", "action", "question", "person"]
    id: str
    field: str
    value: Any
    evidence: EvidenceIn | None = None


class RecordLogOp(OpModel):
    """Add a dated line to a project's update log."""

    op: Literal["record.log"]
    project: str
    text: str = Field(min_length=1)


class ActionAddOp(OpModel):
    """A new action: something a person will do. Owners are people (name or id); leave empty if nobody is named."""

    op: Literal["action.add"]
    text: str = Field(
        min_length=1, description="A verb that does something, e.g. 'Send the final file to the printer'."
    )
    owners: list[str] = Field(default_factory=list)
    due: date | None = None
    project: str | None = None
    evidence: EvidenceIn


class ActionCloseOp(OpModel):
    """Close an open action the input says is done."""

    op: Literal["action.close"]
    id: str
    evidence: EvidenceIn


class QuestionAddOp(OpModel):
    """A question for a person, written for its reader. Decisions are questions to the PM."""

    op: Literal["question.add"]
    to: str = Field(description="The person, by name or id.")
    title: str = Field(min_length=1)
    text: str = ""
    links: list[LinkIn] = Field(default_factory=list)
    project: str | None = None
    kind: Literal["question", "decision"] = "question"


class QuestionDoneOp(OpModel):
    """Record the answer to an open question and close it."""

    op: Literal["question.done"]
    id: str
    answer: str = Field(min_length=1)
    evidence: EvidenceIn


class PersonAddOp(OpModel):
    """Someone the input names who isn't on file yet."""

    op: Literal["person.add"]
    full_name: str = Field(min_length=1)
    role: str | None = None
    org: str | None = None
    aliases: list[str] = Field(default_factory=list)


Op = Annotated[
    NoteOp
    | FactOp
    | RecordSetOp
    | RecordLogOp
    | ActionAddOp
    | ActionCloseOp
    | QuestionAddOp
    | QuestionDoneOp
    | PersonAddOp,
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
}

TIERS: dict[str, Tier] = {name: "data" for name in OP_MODELS}

#: Ops whose evidence is required (record.set requires it for the fields in EVIDENCE_FIELDS).
NEEDS_EVIDENCE = {"fact", "action.add", "action.close", "question.done"}
EVIDENCE_FIELDS = {"due", "status", "owners", "target", "owner"}

#: Fields record.set may change, per kind.
SETTABLE: dict[str, set[str]] = {
    "project": {"status", "phase", "target", "priority", "summary"},
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
