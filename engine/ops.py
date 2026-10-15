"""Op types: what the assistant may propose, with each op's tier and shape (design 6.7).

The AI writes ops in this shape. People may be named by full name, alias or id; the applier resolves names to ids.
Evidence is the exact words from the input that justify the op.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator, model_validator

from engine.records import Scope, entry_problem

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
    key: bool = Field(False, description="True only for a fact that matters most to the project; it is shown first.")
    as_of: date | None = Field(
        None,
        description="The day the fact was true as of, written YYYY-MM-DD, when the input or the person's note names "
        "one (a note often reports something said earlier); left out, it is the day the input was received or the "
        "note was typed.",
    )
    supersedes: str | None = Field(
        None,
        description="The id of an existing fact this one replaces (the same thing, newer). The older fact stays on "
        "record.",
    )


class EventAddOp(OpModel):
    """A date or a range of dates the input gives for something (a delivery window, a deadline, an appointment, a
    launch), in the app's own calendar. Beside the fact or action it belongs to, with the same quoted words. Dates only
    as the input states them; evidence is required."""

    op: Literal["event.add"]
    title: str = Field(min_length=1, description="What happens on that date, in a few words.")
    start: str = Field(
        description="The day it starts, written YYYY-MM-DD, or a date-time with its offset when the input gives a time."
    )
    end: str | None = Field(
        None, description="The last day of a range (or the end time), in the same form as start; leave out for one day."
    )
    project: str | None = Field(None, description="Project id, if the entry belongs to one.")
    evidence: EvidenceIn = Field(description="The exact words from the input that give the date.")

    @field_validator("start", "end")
    @classmethod
    def _readable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if (why := entry_problem(text, None)) is not None:
            raise ValueError(why)
        return text


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


class ActionHoldOp(OpModel):
    """Put an open action on hold: it waits for something outside the person's control and is never due, overdue or
    chased while it does. Say what it waits for in plain words. Refused if the action doesn't exist or isn't open;
    evidence is required (the input's words, or the person's note)."""

    op: Literal["action.hold"] = "action.hold"
    id: str = Field(description="The id of the open action to put on hold.")
    waiting_for: str = Field(min_length=1, max_length=200, description="What it waits for, in plain words.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self) -> str | None:
        return f"Put action {self.id} on hold"


class ActionUnholdOp(OpModel):
    """Take an action off hold when the input says the thing it was waiting for has happened: it is due, chased and
    shown again by its own due date. Refused if the action doesn't exist, isn't open or isn't on hold; evidence is
    required (the input's words, or the person's note)."""

    op: Literal["action.unhold"] = "action.unhold"
    id: str = Field(description="The id of the action that is on hold and no longer waits.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self) -> str | None:
        return f"Take action {self.id} off hold"


class ActionDropOp(OpModel):
    """Drop an action that is no longer needed, with the reason. It stays on record as dropped: never done, never
    credited to its owners, never chased, and gone from to-do lists. Refused if the action doesn't exist or is already
    done or dropped; evidence is required (the input's words, or the person's note)."""

    op: Literal["action.drop"] = "action.drop"
    id: str = Field(description="The id of the action that is no longer needed.")
    reason: str = Field(min_length=1, max_length=500, description="Why it is no longer needed, in plain words.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self) -> str | None:
        return f"Drop action {self.id}"


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
    matters_for: str | None = Field(
        None,
        description="For a question to anyone but the PM: which of the PM's decisions, designs or dated items depends "
        "on the answer, by id or in words. Without one the question isn't asked: record it as a fact instead and say "
        "so in the change's note.",
    )


class QuestionUpdateOp(OpModel):
    """Reword a question: its title, its text or both. Only the person uses it; Undo puts the old wording back."""

    op: Literal["question.update"] = "question.update"
    id: str = Field(description="The id of the question.")
    title: str | None = Field(None, min_length=1, description="The new title.")
    text: str | None = Field(None, description="The new text.")

    @model_validator(mode="after")
    def _changes_something(self) -> QuestionUpdateOp:
        if self.title is None and self.text is None:
            raise ValueError("name what to change")
        return self

    def describe(self) -> str | None:
        return f"Reword question {self.id}"


class QuestionMoveOp(OpModel):
    """Ask someone else instead: the question goes to another person, by name or id. A decision moved off the PM
    becomes an ordinary question. Only the person uses it; Undo sends it back to the one it was for."""

    op: Literal["question.move"] = "question.move"
    id: str = Field(description="The id of the question.")
    to: str = Field(min_length=1, description="The person it goes to now, by name or id.")

    def describe(self) -> str | None:
        return f"Ask someone else instead: question {self.id}"


class QuestionDropOp(OpModel):
    """Drop a question that isn't needed, with the reason. It stays on record as dropped; Undo opens it again. Use it
    only when the input or the person's note says the question is no longer needed; evidence is required."""

    op: Literal["question.drop"] = "question.drop"
    id: str = Field(description="The id of the question.")
    reason: str = Field(min_length=1, max_length=500, description="Why it is dropped, in plain words.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self) -> str | None:
        return f"Drop question {self.id}"


class QuestionMarkSentOp(OpModel):
    """Record that the person already sent an open question themselves, the day they did (today when left out). Only
    the person uses it; Undo makes it open again."""

    op: Literal["question.mark_sent"] = "question.mark_sent"
    id: str = Field(description="The id of the open question.")
    on: date | None = Field(None, description="The day it was sent, written YYYY-MM-DD; today when left out.")

    def describe(self) -> str | None:
        return f"Mark question {self.id} as sent"


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


class AnswerOp(OpModel):
    """Answer the PM's question from the material given: the user guide, the settings, what this install can do and
    the records. Every claim the answer makes cites the exact words it comes from. Creates an answer record."""

    op: Literal["answer"]
    text: str = Field(min_length=1, max_length=4000, description="The answer, in plain words, for the PM.")
    cites: list[EvidenceIn] = Field(
        min_length=1, max_length=10, description="The exact words from the material that the answer rests on."
    )

    def describe(self) -> str | None:
        return "Answer: " + " ".join(self.text.split())[:150]


class SettingProposeOp(OpModel):
    """Propose a change to one setting, when the answer is a setting the PM can change. Nothing changes until the PM
    applies it. The setting is named by its setting code from the settings list."""

    op: Literal["setting.propose"]
    setting: str = Field(description="The setting's code, exactly as the settings list gives it.")
    value: Any = Field(description="Its new value, of the type the settings list shows for it.")
    why: str = Field(min_length=1, max_length=500, description="Why this change answers the question, in one line.")

    def describe(self) -> str | None:
        return f"Suggest setting {self.setting}"


class ListAddOp(OpModel):
    """Add a value to a value list, or offer a retired one again. A system op: from the assistant it waits for the
    person."""

    op: Literal["list.add"] = "list.add"
    list: str = Field(min_length=1, description='The list\'s name, such as "project-status".')
    value: str = Field(min_length=1, max_length=80, description="The value to offer.")

    def describe(self) -> str | None:
        return f"Add {' '.join(self.value.split())!r} to the list {self.list}"


class ListRenameOp(OpModel):
    """Rename a value on a list and on every record that holds it, in one step."""

    op: Literal["list.rename"] = "list.rename"
    list: str = Field(min_length=1, description="The list's name.")
    value: str = Field(min_length=1, description="The value as it is now.")
    to: str = Field(min_length=1, max_length=80, description="Its new wording.")

    def describe(self) -> str | None:
        return f"Rename {self.value!r} to {' '.join(self.to.split())!r} on the list {self.list}"


class ListMergeOp(OpModel):
    """Merge one value of a value list into another: every record that holds the first now holds the second, and the
    first leaves the list. A system op: from the assistant it waits for the person."""

    op: Literal["list.merge"] = "list.merge"
    list: str = Field(min_length=1, description="The list's name.")
    value: str = Field(min_length=1, description="The value that goes away.")
    into: str = Field(min_length=1, description="The value that stays and takes its place.")

    def describe(self) -> str | None:
        return f"Merge {self.value!r} into {self.into!r} on the list {self.list}"


class MailRestoreOp(OpModel):
    """Bring back a mail item that was set aside as not work: it leaves the Set aside folder and the assistant reads
    it. A system op: from the assistant it waits for the person."""

    op: Literal["mail.restore"] = "mail.restore"
    snapshot: str = Field(description="The id of the set-aside mail item.")

    def describe(self) -> str | None:
        return f"Bring back {self.snapshot} from the Set aside folder"


class ListRetireOp(OpModel):
    """Stop offering a value; records that hold it keep it."""

    op: Literal["list.retire"] = "list.retire"
    list: str = Field(min_length=1, description="The list's name.")
    value: str = Field(min_length=1, description="The value to stop offering.")

    def describe(self) -> str | None:
        return f"Stop offering {self.value!r} on the list {self.list}"


class RuleAddOp(OpModel):
    """Add a standing rule: an instruction the assistant follows from now on. A system op: from the person's own words
    the rule is active at once; from anyone else it is added as a proposal that changes nothing until the person keeps
    it. A rule that names a deterministic `check` can gate a stage; a rule with none is prose."""

    op: Literal["rule.add"] = "rule.add"
    text: str = Field(min_length=1, max_length=500, description="The rule, in the person's wording.")
    name: str | None = Field(
        None,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
        description="A short name other settings can refer to; made from the rule's id when left out.",
    )
    applies_to: Scope = Field(default_factory=Scope, description="What the rule applies to; empty means all.")
    check: str | None = Field(
        None, description="The id of a deterministic check that implements the rule, when one exists."
    )
    constrains: list[str] = Field(
        default_factory=list,
        description="What the rule is about: op kinds (`question.add`) or op fields (`action.add.owners`).",
    )
    evidence: EvidenceIn | None = Field(None, description="The words from the input that justify the rule, if any.")

    def describe(self) -> str | None:
        return f"Add the rule: {' '.join(self.text.split())}"


class RuleRetireOp(OpModel):
    """Stop following an active rule; the record stays, marked retired. A system op."""

    op: Literal["rule.retire"] = "rule.retire"
    id: str = Field(description="The id of the rule, such as RULE-3.")

    def describe(self) -> str | None:
        return f"Retire the rule {self.id}"


class ReportDraftOp(OpModel):
    """Draft a report to the product's maintainers when the PM asks for something the product can't do: what was
    wanted, what happens now, and why it would help. The PM reviews and sends it."""

    op: Literal["report.draft"]
    title: str = Field(min_length=1, max_length=120, description="One line naming what is missing.")
    text: str = Field(min_length=1, max_length=4000, description="The report, written for the maintainers.")

    def describe(self) -> str | None:
        return "Draft a report: " + " ".join(self.title.split())


def _named_changes(op: OpModel) -> dict[str, Any]:
    """What an update op changes: each field it gives a value, as plain data. A field left null stays as it is."""
    data = op.model_dump(mode="json", exclude={"op", "group", "id"}, exclude_none=True, by_alias=True)
    return dict(sorted(data.items()))


class LessonAddOp(OpModel):
    """Keep a lesson: what went wrong, why, and the guard that stops it happening again, written as the general case
    in plain words. From the person's own words it is active at once; from anything else it is a proposal the person
    keeps or discards, and changes nothing until kept. `signal` is the correction it came from."""

    op: Literal["lesson.add"] = "lesson.add"
    text: str = Field(min_length=1, description="The lesson in plain words, as the general case.")
    guard: str | None = Field(None, description="The check or behavior that prevents a repeat, in plain words.")
    signal: str | None = Field(None, description="The id of the correction it came from, if there is one.")
    applies_to: Scope = Field(default_factory=Scope, description="What it applies to.")
    evidence: EvidenceIn | None = Field(None, description="The exact words from the input it rests on, if any.")

    def describe(self) -> str | None:
        return "Lesson: " + " ".join(self.text.split())[:150]


class LessonUpdateOp(OpModel):
    """Change a lesson that is proposed or active: its wording, its guard or what it applies to. A system op: it
    changes how the assistant behaves, so from anyone but the person it waits for them. Name only what changes."""

    op: Literal["lesson.update"] = "lesson.update"
    id: str = Field(description="The id of the lesson.")
    text: str | None = Field(None, min_length=1, description="The new wording.")
    guard: str | None = Field(None, description="The new guard.")
    applies_to: Scope | None = Field(None, description="What it now applies to, in full.")

    @model_validator(mode="after")
    def _changes_something(self) -> LessonUpdateOp:
        if not self.changes():
            raise ValueError("name what to change")
        return self

    def changes(self) -> dict[str, Any]:
        """The fields to change, by name, with their new values."""
        return _named_changes(self)

    def describe(self) -> str | None:
        return f"Change lesson {self.id}"


class GlossaryAddOp(OpModel):
    """Keep a glossary entry: a term or acronym and what it means here. From the person's own words it is active at
    once; from anything else it is a proposal the person keeps or discards."""

    op: Literal["glossary.add"] = "glossary.add"
    text: str = Field(min_length=1, description="The entry in plain words, such as the term and what it stands for.")
    term: str = Field(min_length=1, description="The term, acronym or name as it is written.")
    meaning: str = Field(min_length=1, description="What it means.")
    confidence: Literal["confirmed", "assumed", "unknown"] = Field(
        "assumed", description="confirmed: someone who knows said so. assumed: a reasonable reading. unknown: not yet."
    )
    project: str | None = Field(None, description="Project id, if the term is about one project only.")
    id_patterns: list[str] = Field(
        default_factory=list, description="Patterns for splitting compound ids that use the term."
    )
    applies_to: Scope = Field(default_factory=Scope, description="What it applies to.")
    evidence: EvidenceIn | None = Field(None, description="The exact words from the input it rests on, if any.")

    def describe(self) -> str | None:
        return f"Glossary: {' '.join(self.term.split())[:60]}"


class GlossaryUpdateOp(OpModel):
    """Change a glossary entry that is proposed or active. A system op: from anyone but the person it waits for
    them. Name only what changes."""

    op: Literal["glossary.update"] = "glossary.update"
    id: str = Field(description="The id of the glossary entry.")
    text: str | None = Field(None, min_length=1, description="The new wording.")
    meaning: str | None = Field(None, min_length=1, description="The new meaning.")
    confidence: Literal["confirmed", "assumed", "unknown"] | None = Field(None, description="The new confidence.")
    project: str | None = Field(None, description="The project it is about.")
    id_patterns: list[str] | None = Field(None, description="The new patterns for splitting compound ids.")
    applies_to: Scope | None = Field(None, description="What it now applies to, in full.")

    @model_validator(mode="after")
    def _changes_something(self) -> GlossaryUpdateOp:
        if not self.changes():
            raise ValueError("name what to change")
        return self

    def changes(self) -> dict[str, Any]:
        """The fields to change, by name, with their new values."""
        return _named_changes(self)

    def describe(self) -> str | None:
        return f"Change glossary entry {self.id}"


class RoutingAddOp(OpModel):
    """Keep a routing entry: who answers a kind of question, or who doesn't (`negative`), and where to look it up
    instead. Name the person or the team by id. From the person's own words it is active at once; from anything
    else it is a proposal the person keeps or discards."""

    op: Literal["routing.add"] = "routing.add"
    text: str = Field(min_length=1, description="The entry in plain words.")
    topic: str = Field(min_length=1, description="The topic, area or kind of question.")
    person: str | None = Field(None, description="The person's id.")
    team: str | None = Field(None, description="The team's id, instead of a person.")
    negative: bool = Field(False, description="True when they don't answer this.")
    look_up: str | None = Field(None, description="Where to look it up instead, in plain words.")
    applies_to: Scope = Field(default_factory=Scope, description="What it applies to.")
    evidence: EvidenceIn | None = Field(None, description="The exact words from the input it rests on, if any.")

    def describe(self) -> str | None:
        return f"Routing: {' '.join(self.topic.split())[:60]}"


class StyleAddOp(OpModel):
    """Keep a style note: what a recipient or audience wants or avoids in what is written for them. `audience` is a
    person's id or a kind of audience in words. From the person's own words it is active at once; from anything else
    it is a proposal the person keeps or discards."""

    op: Literal["style.add"] = "style.add"
    text: str = Field(min_length=1, description="The note in plain words.")
    audience: str = Field(min_length=1, description="A person's id, or a kind of audience in words.")
    observation: str = Field(min_length=1, description="What they want or avoid.")
    applies_to: Scope = Field(default_factory=Scope, description="What it applies to.")
    evidence: EvidenceIn | None = Field(None, description="The exact words from the input it rests on, if any.")

    def describe(self) -> str | None:
        return f"Style note for {' '.join(self.audience.split())[:60]}"


class KnowledgeRetireOp(OpModel):
    """Retire an active lesson, glossary entry, routing entry or style note, named by its id: it stops guiding runs
    and stays on record. A system op: from anyone but the person it waits for them."""

    op: Literal["knowledge.retire"] = "knowledge.retire"
    id: str = Field(description="The id of the entry, such as a lesson's.")

    def describe(self) -> str | None:
        return f"Retire {self.id}"


Op = Annotated[
    NoteOp
    | FactOp
    | EventAddOp
    | RecordSetOp
    | RecordLogOp
    | ActionAddOp
    | ActionCloseOp
    | ActionHoldOp
    | ActionUnholdOp
    | ActionDropOp
    | QuestionAddOp
    | QuestionDoneOp
    | QuestionUpdateOp
    | QuestionMoveOp
    | QuestionDropOp
    | QuestionMarkSentOp
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
    | TextDraftOp
    | AnswerOp
    | SettingProposeOp
    | ListAddOp
    | ListRenameOp
    | ListMergeOp
    | ListRetireOp
    | MailRestoreOp
    | ReportDraftOp
    | LessonAddOp
    | LessonUpdateOp
    | GlossaryAddOp
    | GlossaryUpdateOp
    | RoutingAddOp
    | StyleAddOp
    | KnowledgeRetireOp
    | RuleAddOp
    | RuleRetireOp,
    Field(discriminator="op"),
]

OP_MODELS: dict[str, type[OpModel]] = {
    "note": NoteOp,
    "fact": FactOp,
    "event.add": EventAddOp,
    "record.set": RecordSetOp,
    "record.log": RecordLogOp,
    "action.add": ActionAddOp,
    "action.close": ActionCloseOp,
    "action.hold": ActionHoldOp,
    "action.unhold": ActionUnholdOp,
    "action.drop": ActionDropOp,
    "question.add": QuestionAddOp,
    "question.done": QuestionDoneOp,
    "question.update": QuestionUpdateOp,
    "question.move": QuestionMoveOp,
    "question.drop": QuestionDropOp,
    "question.mark_sent": QuestionMarkSentOp,
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
    "answer": AnswerOp,
    "setting.propose": SettingProposeOp,
    "list.add": ListAddOp,
    "list.rename": ListRenameOp,
    "list.merge": ListMergeOp,
    "list.retire": ListRetireOp,
    "mail.restore": MailRestoreOp,
    "rule.add": RuleAddOp,
    "rule.retire": RuleRetireOp,
    "report.draft": ReportDraftOp,
    "lesson.add": LessonAddOp,
    "lesson.update": LessonUpdateOp,
    "glossary.add": GlossaryAddOp,
    "glossary.update": GlossaryUpdateOp,
    "routing.add": RoutingAddOp,
    "style.add": StyleAddOp,
    "knowledge.retire": KnowledgeRetireOp,
}

#: The ops that keep what the assistant learned (design 6.22).
KNOWLEDGE_OPS = {
    "lesson.add",
    "lesson.update",
    "glossary.add",
    "glossary.update",
    "routing.add",
    "style.add",
    "knowledge.retire",
}
#: The ops that add an entry, a standing rule included. Whatever tier they have, one that doesn't come from the
#: person's own words still applies, as a proposal: an entry changes nothing until the person keeps it.
KNOWLEDGE_ADD_OPS = {"lesson.add", "glossary.add", "routing.add", "style.add", "rule.add"}

#: Ops only the person makes: from anyone else they are refused, never held.
PERSON_ONLY_OPS = {
    "text.edit",
    "text.accept",
    "text.discard",
    "record.edit",
    "question.update",
    "question.move",
    "question.mark_sent",
}

TIERS: dict[str, Tier] = (
    {name: "data" for name in OP_MODELS}
    | {
        "record.delete": "system",
        "project.add": "system",
        "list.add": "system",
        "list.rename": "system",
        "list.merge": "system",
        "list.retire": "system",
        "mail.restore": "system",
        "rule.add": "system",
        "rule.retire": "system",
    }
    | {name: "system" for name in KNOWLEDGE_OPS}
)

#: Ops whose evidence is required (record.set requires it for the fields in EVIDENCE_FIELDS).
NEEDS_EVIDENCE = {
    "fact",
    "event.add",
    "action.add",
    "action.close",
    "action.hold",
    "action.unhold",
    "action.drop",
    "question.drop",
    "question.done",
}
#: Ops that need evidence from the assistant but not when the person makes them: their own act is not a claim from an
#: input, so a person's action or screen may use them without a quote.
EVIDENCE_UNLESS_PERSON = {"action.hold", "action.unhold", "action.drop", "question.drop"}
EVIDENCE_FIELDS = {"due", "status", "owners", "target", "owner"}

#: Fields record.set may change, per kind.
SETTABLE: dict[str, set[str]] = {
    "project": {"status", "phase", "target", "priority", "summary", "parent", "language", "owner"},
    "action": {"text", "due", "notes"},
    "question": {"title", "text"},
    "person": {"role", "org", "why_they_matter"},
}


TOPIC_MAX = 60
#: The longest one entry of `applied` or `missing` is kept, and the most entries of either that one answer keeps.
CLAIM_MAX = 200
CLAIMS_MAX = 20


class ChangesetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    topic: str = ""
    ops: list[Any] = Field(default_factory=list)
    #: Reading notes only: the person's own note is a question to the assistant, not material to record.
    ask: bool = False
    #: The ids of the knowledge entries the run says it applied. The dispatcher keeps only those the run was given.
    applied: list[str] = Field(default_factory=list)
    #: What the run needed and no op could do, each in a few words, instead of improvising with another op.
    missing: list[str] = Field(default_factory=list)

    @field_validator("applied", "missing", mode="before")
    @classmethod
    def short_list(cls, value: Any) -> list[str]:
        """A list of short words: anything else a model sends is dropped, blanks and repeats go, and each entry is
        kept to one line."""
        if not isinstance(value, list):
            return []
        found: list[str] = []
        for item in value:
            words = " ".join(item.split()) if isinstance(item, str) else ""
            words = words[:CLAIM_MAX]
            if words and words not in found:
                found.append(words)
        return found[:CLAIMS_MAX]

    @field_validator("topic", mode="before")
    @classmethod
    def short_topic(cls, value: Any) -> str:
        """A few words naming what the input is about, for its title: kept to one line and cut at a word."""
        words = " ".join(str(value or "").split())
        if len(words) <= TOPIC_MAX:
            return words
        return words[:TOPIC_MAX].rsplit(" ", 1)[0].rstrip(" ,;:-")

    @field_validator("ops", mode="before")
    @classmethod
    def parse_ops(cls, values: Any, info: ValidationInfo) -> list[OpModel]:
        models = (info.context or {}).get("op_models", OP_MODELS)
        if not isinstance(values, list):
            raise ValueError("ops must be a list")
        parsed = []
        for index, value in enumerate(values):
            data = value.model_dump() if isinstance(value, OpModel) else value
            name = data.get("op") if isinstance(data, dict) else None
            if name is None:
                raise ValueError(f'op {index} has no "op" field naming one of the ops in the op reference')
            if name not in models:
                raise ValueError(f"op {index} names {name!r}, which isn't in the op reference")
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
            "topic": {"type": "string"},
            "ops": {"type": "array", "items": {"anyOf": [m.model_json_schema() for m in models]}},
            "applied": {"type": "array", "items": {"type": "string"}},
            "missing": {"type": "array", "items": {"type": "string"}},
        },
    }


def reference_for(op_names: list[str], registry: dict | None = None, invariants: dict | None = None) -> str:
    """A readable op reference for the prompt: each op, what it's for and its fields, with the one-line constraint of
    each invariant that applies to it under it. Constraints that apply to every op follow the list once."""
    from engine import invariants as shipped

    known = invariants if invariants is not None else shipped.load()
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
        lines += [f"  Always checked: {line}" for line in shipped.lines_for(name, known)]
    if op_names:
        lines += [f"Every op is checked: {line}" for line in shipped.lines_for_every_op(known)]
    return "\n".join(lines)
