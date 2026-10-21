"""Op types: what the assistant may propose, with each op's tier and shape (design 6.7).

The AI writes ops in this shape. People may be named by full name, alias or id; the applier resolves names to ids.
Evidence is the exact words from the input that justify the op.
"""

from __future__ import annotations

import json
import types
from datetime import date
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator, model_validator

from engine.id_words import KNOWLEDGE_KINDS, named, named_one_of, named_text_of
from engine.records import RefTo, Scope, canonical_time, entry_problem

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
        label is made against the records as they stand before the changeset applies. A label names a record by its
        title in quotes, never by its id."""
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
    question: Annotated[str | None, RefTo("question")] = Field(
        None, description="The id of the open question it adds to, when the input says more about one."
    )


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
    basis: Literal["inferred", "said"] | None = Field(
        None,
        description="Who the fact rests on, when it isn't what the input's origin says (leave it out then: the "
        "person's own note is the person's word, and content from outside is said by its sender). inferred: the "
        "input doesn't say this outright; you worked it out from the words you quote. said: someone else said it, "
        "named in said_by.",
    )
    said_by: str | None = Field(
        None, description="With basis said: who said it, by name or id, when the input names someone."
    )
    event: Annotated[str | None, RefTo("event")] = Field(
        None, description="The calendar entry it is for, when the input ties it to one."
    )
    series: Annotated[str | None, RefTo("series")] = Field(
        None, description="The series of a repeating meeting it is for; it sits on the next instance."
    )
    reaches_children: bool = Field(
        False,
        description="True only for a fact about a project that holds for every project inside it too (a fact about a "
        "series that is true of each of its books); needs the project. Left false, it is about that project alone.",
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
    series: Annotated[str | None, RefTo("series")] = Field(
        None, description="The id of the series this entry is an instance of, if any."
    )
    evidence: EvidenceIn = Field(description="The exact words from the input that give the date.")

    @field_validator("start", "end")
    @classmethod
    def _readable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if (why := entry_problem(text, None)) is not None:
            raise ValueError(why)
        return canonical_time(text)


class EventSetOp(OpModel):
    """Move a calendar entry that is in the list: a new start, a new end, or both, when the input says that real event
    now happens at another time ("the walkthrough moved to Tuesday at 3 pm"). Never add a second entry for it. Leave out
    what doesn't change. A new time as the input states it; a vague time ("next week", "later") is not one. Evidence is
    required."""

    op: Literal["event.set"]
    id: Annotated[str, RefTo("event")] = Field(description="The id of the calendar entry that moves.")
    start: str | None = Field(
        None,
        description="The new start, written YYYY-MM-DD, or a date-time with its offset when the input gives a time; "
        "leave out when the start doesn't change.",
    )
    end: str | None = Field(
        None,
        description="The new end (the last day or moment), in the same form as start; leave out when the end doesn't "
        "change.",
    )
    evidence: EvidenceIn = Field(description="The exact words from the input that give the new time.")

    @field_validator("start", "end")
    @classmethod
    def _readable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if (why := entry_problem(text, None)) is not None:
            raise ValueError(why)
        return canonical_time(text)

    @model_validator(mode="after")
    def _moves_something(self) -> EventSetOp:
        if self.start is None and self.end is None:
            raise ValueError("give the new start, the new end or both")
        return self

    def describe(self, view: Any = None) -> str | None:
        parts = [f"starts {self.start}" if self.start else None, f"ends {self.end}" if self.end else None]
        return f"Change the time of {named(view, 'event', self.id)}: " + " and ".join(p for p in parts if p)


class SeriesAddOp(OpModel):
    """A meeting or check-in that repeats, when the input says so ("every Tuesday"). `events` names existing entries
    that are instances of it. Never add one that is already in the lists. Evidence is required."""

    op: Literal["series.add"]
    title: str = Field(min_length=1, description="What the series is, in a few words.")
    repeats: str | None = Field(None, description="How often, in the input's words.")
    project: str | None = Field(None, description="Project id, if the series belongs to one.")
    events: list[Annotated[str, RefTo("event")]] = Field(
        default_factory=list, description="The ids of existing entries that are instances of it."
    )
    evidence: EvidenceIn = Field(description="The exact words from the input that say it repeats.")

    def describe(self) -> str | None:
        return f"Series {' '.join(self.title.split())[:60]}"


class SeriesLinkOp(OpModel):
    """Make an existing calendar entry an instance of a series, or take it out of its series (leave `series` out).
    Evidence is required."""

    op: Literal["series.link"]
    event: Annotated[str, RefTo("event")] = Field(description="The id of the calendar entry.")
    series: Annotated[str | None, RefTo("series")] = Field(
        None, description="The id of the series; leave out to take the entry out of its series."
    )
    evidence: EvidenceIn = Field(description="The exact words from the input that say so.")

    def describe(self, view: Any = None) -> str | None:
        entry = named(view, "event", self.event)
        return (
            f"Put {entry} in {named(view, 'series', self.series)}" if self.series else f"Take {entry} out of its series"
        )


class AgendaAddOp(OpModel):
    """Put an action, a question or a note on a meeting's agenda, linked to it, when the input says it is to be taken up
    at that meeting ("we'll cover it at the print sync"): the calendar entry (`event`) or the series of a repeating
    meeting (`series`), whichever the words name. The item is not changed, closed or moved; it is listed on the meeting.
    Never add one that is already on it. Evidence is required."""

    op: Literal["agenda.add"] = "agenda.add"
    event: Annotated[str | None, RefTo("event")] = Field(None, description="The id of the calendar entry.")
    series: Annotated[str | None, RefTo("series")] = Field(
        None, description="The id of the series, for a repeating meeting named in general."
    )
    action: Annotated[str | None, RefTo("action")] = Field(None, description="The id of the action to put on it.")
    question: Annotated[str | None, RefTo("question")] = Field(None, description="The id of the question to put on it.")
    note: Annotated[str | None, RefTo("note")] = Field(None, description="The id of the note to put on it.")
    text: str | None = Field(
        None, description="The words it is on the agenda under; left out, the item's own words are used."
    )
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that say it is for the meeting."
    )

    @model_validator(mode="after")
    def _one_meeting_one_item(self) -> AgendaAddOp:
        if (self.event is None) == (self.series is None):
            raise ValueError("name one meeting: a calendar entry or a series")
        if sum(x is not None for x in (self.action, self.question, self.note)) != 1:
            raise ValueError("name one action, question or note to put on it")
        return self

    def describe(self, view: Any = None) -> str | None:
        kind, item = next(
            (k, v) for k, v in (("action", self.action), ("question", self.question), ("note", self.note)) if v
        )
        meeting = named(view, "event", self.event) if self.event else named(view, "series", self.series)
        return f"Put {named(view, kind, item)} on the agenda of {meeting}"


class RecordSetOp(OpModel):
    """Change one field of an existing record. Allowed fields: project status, phase, target, priority, summary, parent
    (the id of the project it belongs to), language (a tag such as en-US) and owner (a person's id);
    action text, due and notes; the entry (event) or series an action, question or fact belongs to (an id, or null);
    question title and text; person role, org, why_they_matter, side (personal, business or both) and relation
    (how they relate to the person, such as "my sister"). The new value must
    be valid for the field. Evidence is required for due, status, owners, target and owner."""

    op: Literal["record.set"]
    kind: Literal["project", "action", "question", "person", "fact"] = Field(
        description="The kind of record to change."
    )
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
    due_words: str | None = Field(
        None,
        max_length=120,
        description="The exact words the date comes from ('by Friday', 'early next week'), copied from the input. The "
        "rules read the date from them, and their date wins over `due`.",
    )
    promised_to: list[str] = Field(
        default_factory=list,
        description="For a promise: the people it was promised to, each by name or id (the person this app is for, "
        "when someone else promised them something). Empty for a plain to-do.",
    )
    basis: Literal["inferred", "said"] | None = Field(
        None,
        description="For a promise: said, when someone said it outright; inferred, when you read it between the lines.",
    )
    said_by: str | None = Field(None, description="Who said it, by name or id, when the input names them.")
    waiting_for: str | None = Field(
        None,
        max_length=200,
        description="For a promise that holds only once something happens ('once the keys arrive', 'if the board "
        "agrees'): the condition, in plain words. The action starts on hold until it is met.",
    )
    due_at_event: bool = Field(
        False,
        description="The date is the calendar entry's in `event` ('by Thursday's meeting', 'after the review'): it is "
        "due on the entry's day and moves when the entry moves.",
    )
    project: str | None = Field(None, description="Project id, if the action belongs to one.")
    reply: str | None = Field(
        None,
        description="For an action that is a reply the person owes: the drafted reply, ready to copy, only when a "
        "recorded fact holds the answer, naming the fact it comes from. Left out when nothing recorded holds the "
        "answer. It stays marked as a draft until the person approves it.",
    )
    reply_owed: bool = Field(
        False,
        description="True for the one action that is the reply the person owes to a message that asks them something "
        "(owned by the person). The rules then read the message: automatic mail, mail the person sent and a message "
        "that says no reply is needed are refused. Leave it false for any other action.",
    )
    event: Annotated[str | None, RefTo("event")] = Field(
        None, description="The calendar entry it is for, when the input ties it to one."
    )
    series: Annotated[str | None, RefTo("series")] = Field(
        None, description="The series of a repeating meeting it is for; it sits on the next instance."
    )
    evidence: EvidenceIn = Field(description="The exact words from the input that justify this op.")


class ActionReplyOp(OpModel):
    """Approve the drafted reply of an action as it is, or replace it with the person's own words; either marks it
    reviewed. Only the person uses it; Undo puts the reply and its mark back."""

    op: Literal["action.reply"] = "action.reply"
    id: str = Field(description="The id of the action.")
    text: str | None = Field(
        None, min_length=1, description="The person's own wording of the reply; left out, the draft is approved."
    )

    def describe(self, view: Any = None) -> str | None:
        what = named(view, "action", self.id)
        return f"Approve the reply of {what}" if self.text is None else f"Reword the reply of {what}"


class ActionCloseOp(OpModel):
    """Close an open action the input says is done. Refused if the action doesn't exist or is already done; evidence
    is required (the input's words, or the person's note)."""

    op: Literal["action.close"]
    id: str = Field(description="The id of the open action that is done.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )


class ActionHoldOp(OpModel):
    """Put an open action on hold: it waits for something outside the person's control and is never due, overdue or
    chased while it does. Say what it waits for in plain words. Refused if the action doesn't exist or isn't open;
    evidence is required (the input's words, or the person's note)."""

    op: Literal["action.hold"] = "action.hold"
    id: str = Field(description="The id of the open action to put on hold.")
    waiting_for: str = Field(min_length=1, max_length=200, description="What it waits for, in plain words.")
    on: str | None = Field(
        None,
        description="When the input names what blocks it, the id of that person, action or question (one the context "
        "lists); the action is then blocked on it. Leave it out when the wait is only words.",
    )
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self, view: Any = None) -> str | None:
        return f"Put {named(view, 'action', self.id)} on hold"


class ActionUnholdOp(OpModel):
    """Take an action off hold when the input says the thing it was waiting for has happened: it is due, chased and
    shown again by its own due date. Refused if the action doesn't exist, isn't open or isn't on hold; evidence is
    required (the input's words, or the person's note)."""

    op: Literal["action.unhold"] = "action.unhold"
    id: str = Field(description="The id of the action that is on hold and no longer waits.")
    due_words: str | None = Field(
        None, max_length=120, description="The exact words of its new date, when the input gives one ('by Monday')."
    )
    due: date | None = Field(None, description="Its new date, when there are no words to read it from.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self, view: Any = None) -> str | None:
        return f"Take {named(view, 'action', self.id)} off hold"


class ActionDropOp(OpModel):
    """Drop an action that is no longer needed, with the reason. It stays on record as dropped: never done, never
    credited to its owners, never chased, and gone from to-do lists. Refused if the action doesn't exist or is already
    done or dropped; evidence is required (the input's words, or the person's note). When the words say it moved into
    a meeting ("we'll cover it at the print sync"), name that meeting in `event` or `series`: the action is put on its
    agenda, linked, so it isn't lost."""

    op: Literal["action.drop"] = "action.drop"
    id: str = Field(description="The id of the action that is no longer needed.")
    reason: str = Field(min_length=1, max_length=500, description="Why it is no longer needed, in plain words.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )
    event: Annotated[str | None, RefTo("event")] = Field(
        None, description="The id of the calendar entry it moved into, when the words say it did."
    )
    series: Annotated[str | None, RefTo("series")] = Field(
        None,
        description="The id of the series of a repeating meeting it moved into, when the words name it in general.",
    )

    @model_validator(mode="after")
    def _one_meeting(self) -> ActionDropOp:
        if self.event is not None and self.series is not None:
            raise ValueError("name one meeting: a calendar entry or a series")
        return self

    def describe(self, view: Any = None) -> str | None:
        return f"Drop {named(view, 'action', self.id)}"


class ActionMoveOp(OpModel):
    """The input says an open action's date changed: give the new date's exact words, or a date. Refused if the action
    doesn't exist or isn't open; evidence is required (the input's words, or the person's note)."""

    op: Literal["action.move"] = "action.move"
    id: str = Field(description="The id of the open action whose date changed.")
    due_words: str | None = Field(
        None, max_length=120, description="The exact words of the new date, copied from the input ('next Tuesday')."
    )
    due: date | None = Field(None, description="The new date, when there are no words to read it from.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    @model_validator(mode="after")
    def _a_date(self) -> ActionMoveOp:
        if not (self.due_words or "").strip() and self.due is None:
            raise ValueError("give the new date's words or the date")
        return self

    def describe(self, view: Any = None) -> str | None:
        return f"Move the date of {named(view, 'action', self.id)}"


class ActionPartOp(OpModel):
    """The input says part of an open action was delivered: say what was delivered and what is left. What was
    delivered is credited in its news; the action's text becomes what is left, which stays open. Refused if the action
    doesn't exist or isn't open; evidence is required (the input's words, or the person's note)."""

    op: Literal["action.part"] = "action.part"
    id: str = Field(description="The id of the open action that was partly delivered.")
    delivered: str = Field(min_length=1, max_length=300, description="What was delivered, in plain words.")
    left: str = Field(min_length=1, max_length=300, description="What is left to do, starting with a verb.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self, view: Any = None) -> str | None:
        return f"Mark part of {named(view, 'action', self.id)} delivered"


class ActionNewsOp(OpModel):
    """News about an open action that doesn't end it or change its date, such as a reply that didn't answer: it stays
    open and says why. Refused if the action doesn't exist or isn't open; evidence is required."""

    op: Literal["action.news"] = "action.news"
    id: str = Field(description="The id of the open action the news is about.")
    text: str = Field(min_length=1, max_length=300, description="What was heard, in plain words.")
    evidence: EvidenceIn = Field(description="The exact words from the input that justify this op.")

    def describe(self, view: Any = None) -> str | None:
        return f"Add news to {named(view, 'action', self.id)}"


class QuestionAddOp(OpModel):
    """A question for a person, written for its reader. A decision is a question to whoever decides, the PM when
    nobody is named. A question to anyone else needs at least one link the recipient can open."""

    op: Literal["question.add"]
    to: str = Field(description="The person, by name or id.")
    title: str = Field(min_length=1, description="The question in one line.")
    text: str = Field("", description="The detail the reader needs to answer.")
    links: list[LinkIn] = Field(default_factory=list, description="Pages the reader can open to see what it is about.")
    project: str | None = Field(None, description="Project id, if the question is about one.")
    event: Annotated[str | None, RefTo("event")] = Field(
        None, description="The calendar entry it is for, when the input ties it to one."
    )
    series: Annotated[str | None, RefTo("series")] = Field(
        None, description="The series of a repeating meeting it is for; it sits on the next instance."
    )
    asks_about: Literal["date", "decision", "design", "mistake", "other"] = Field(
        "other",
        description="What the question asks about: date (chasing when something will be done, or a promise), "
        "decision, design (how they do their own work, or its detail), mistake (an apparent contradiction with a "
        "recorded decision or fact: link both sides), or other.",
    )
    kind: Literal["question", "decision"] = Field(
        "question",
        description="question: an ordinary question. decision: a choice for whoever decides, the PM when nobody is "
        "named.",
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

    def describe(self, view: Any = None) -> str | None:
        return f"Reword {named(view, 'question', self.id)}"


class QuestionMoveOp(OpModel):
    """Ask someone else instead: the question goes to another person, by name or id, and keeps its kind: a decision
    stays a decision for the new person. Only the person uses it; Undo sends it back to the one it was for."""

    op: Literal["question.move"] = "question.move"
    id: str = Field(description="The id of the question.")
    to: str = Field(min_length=1, description="The person it goes to now, by name or id.")

    def describe(self, view: Any = None) -> str | None:
        return f"Ask someone else instead: {named(view, 'question', self.id)}"


class QuestionDropOp(OpModel):
    """Drop a question that isn't needed, with the reason. It stays on record as dropped; Undo opens it again. Use it
    only when the input or the person's note says the question is no longer needed; evidence is required."""

    op: Literal["question.drop"] = "question.drop"
    id: str = Field(description="The id of the question.")
    reason: str = Field(min_length=1, max_length=500, description="Why it is dropped, in plain words.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that justify this op; required unless the person makes it."
    )

    def describe(self, view: Any = None) -> str | None:
        return f"Drop {named(view, 'question', self.id)}"


class QuestionMarkSentOp(OpModel):
    """Record that the person already sent an open question themselves, the day they did (today when left out). The
    person uses it, or the assistant when the person's own note says they asked; Undo makes it open again."""

    op: Literal["question.mark_sent"] = "question.mark_sent"
    id: str = Field(description="The id of the open question.")
    on: date | None = Field(None, description="The day it was sent, written YYYY-MM-DD; today when left out.")

    def describe(self, view: Any = None) -> str | None:
        return f"Mark {named(view, 'question', self.id)} as sent"


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
    first_name: str | None = Field(
        None, description="The name a greeting to them uses, if the input shows how they sign it."
    )


class PersonContactOp(OpModel):
    """A way to reach a person that the input gives, such as a phone number or an address in their signature. It always
    waits for the person to confirm it, whoever proposes it: a detail from outside content would otherwise become a way
    to reach someone. Confirming sets the detail of that kind on the person, replacing one of the same kind. The kind is
    one of the contact kinds the workspace offers; evidence is required."""

    op: Literal["person.contact"] = "person.contact"
    person: str = Field(description="The id of the person the detail belongs to.")
    kind: str = Field(min_length=1, description="What the detail is: one of the contact kinds listed in the request.")
    value: str = Field(min_length=1, max_length=300, description="The detail itself, as the input gives it.")
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that give it; required unless the person makes it."
    )

    @field_validator("value", mode="after")
    @classmethod
    def _one_line(cls, value: str) -> str:
        text = " ".join(value.split())
        if not text:
            raise ValueError("name the detail")
        return text

    def describe(self, view: Any = None) -> str | None:
        return f"Add a {self.kind} for {named(view, 'person', self.person)}"


class PersonStanceOp(OpModel):
    """Who a person is to the person, proposed from a correction such as "not my job to ask them" or "we are not their
    boss". A system op: it changes what the assistant may draft or ask them, so from anyone but the person's own words
    it waits for the person's Keep. The four stances mean: manage (questions about what the person tracks, design detail
    included, and chasing their dates), alongside (follow-ups on promises made to the person and a clear mistake with
    links to both sides, nothing about how they do their own work), report_to (no chasing and no question unless the
    person asks), watch (nothing is drafted to them). Propose it instead of a lesson when the person rejects asking
    someone at all; evidence is required."""

    op: Literal["person.stance"] = "person.stance"
    id: str = Field(description="The id of the person whose stance this is.")
    stance: Literal["manage", "alongside", "report_to", "watch"] = Field(
        description="Who they are to the person: manage, alongside, report_to or watch."
    )
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the request that give it; required unless the person makes it."
    )

    def describe(self, view: Any = None) -> str | None:
        return f"Change who {named(view, 'person', self.id)} is to you"


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
    status: str | None = Field(
        None,
        description="Where the project stands, only when the input states it, with those words as evidence. A status "
        'nobody stated is left out and stays unknown: never write "not started" or a guess.',
    )
    link: str | None = Field(
        None,
        description="The page the project was added from, when the input gave one. It is kept as a link on the "
        "project; the project's details are filled from it only when something set up can read it.",
    )
    evidence: EvidenceIn | None = Field(
        None,
        description="The exact words from the input that name the project, when an input is where it came from; "
        "required when a status is given, and then the words that state the status.",
    )

    def describe(self) -> str | None:
        return f"Start the project {self.name}"


class ProjectRoleOp(OpModel):
    """Set a person's part in a project: they run it, design for it, or only watch it. Propose it when the input
    says who runs, designs or watches a project now ("I'm running it now", "they want me to take it over"). A system
    op: from the assistant it waits for the person, who may set it on the project's own page. Evidence is required."""

    op: Literal["project.role"] = "project.role"
    project: str = Field(description="The id of the project the role is on.")
    person: str = Field(description="The person whose part it is, by name or id.")
    role: Literal["run", "design", "watch"] = Field(
        description="run: they run it. design: they design for it. watch: they only watch it, so only facts are "
        "recorded about it."
    )
    evidence: EvidenceIn | None = Field(
        None, description="The exact words from the input that say it; required unless the person makes it."
    )

    def describe(self) -> str | None:
        return "Set a role on a project"


class RecordEditOp(OpModel):
    """The person's own change to fields of any record (core or a plugin's), such as an edit made to the record's
    file in the synced folder: it waits for the person's review there, and applies as theirs. Long text, the stage,
    the id and plugin extension fields aren't changed this way. Only the person uses it."""

    op: Literal["record.edit"] = "record.edit"
    record: RecordRef = Field(description="The record to change.")
    fields: dict[str, Any] = Field(description="The new values, by field name.")
    read_version: int = Field(ge=1, description="The record's version the edit was made from.")

    def describe(self, view: Any = None) -> str | None:
        return f"Change {', '.join(sorted(self.fields))} of {named(view, self.record.kind, self.record.id)}"


class TextEditOp(OpModel):
    """The person's own new text for a long text field, written here: it becomes the field's text at once, with the
    person as author of every passage it changes. Only the person (an edit on screen or their own action) uses it."""

    op: Literal["text.edit"] = "text.edit"
    record: RecordRef = Field(description="The record whose field it is.")
    field: str = Field(description="The long text field.")
    text: str = Field(description="The whole new text.")

    def describe(self, view: Any = None) -> str | None:
        return f"Change the text of {named(view, self.record.kind, self.record.id)}"


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

    def describe(self, view: Any = None) -> str | None:
        return f"Propose new text for {named(view, self.record.kind, self.record.id)}"


class TextAcceptOp(OpModel):
    """Accept a pending version, change by change: the result becomes the field's text, with authorship following the
    choices. Changes not listed are accepted; rejecting every change discards it. Only the person uses it."""

    op: Literal["text.accept"] = "text.accept"
    version: str = Field(description="The id of the pending text version.")
    read_version: int = Field(ge=1, description="The version of that record that was reviewed.")
    choices: dict[str, Literal["accept", "reject"]] = Field(
        default_factory=dict, description="Per change id (c1, c2, ...): accept or reject."
    )

    def describe(self, view: Any = None) -> str | None:
        return f"Accept the new text of {named_text_of(view, self.version)}"


class TextDiscardOp(OpModel):
    """Set a pending version aside without changing the field. Only the person uses it."""

    op: Literal["text.discard"] = "text.discard"
    version: str = Field(description="The id of the pending text version.")
    read_version: int = Field(ge=1, description="The version of that record that was reviewed.")

    def describe(self, view: Any = None) -> str | None:
        return f"Set aside the new text of {named_text_of(view, self.version)}"


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

    def describe(self, view: Any = None) -> str | None:
        return f"Draft new text for {named(view, self.record.kind, self.record.id)}"


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
    tone: Literal["ok", "warn", "danger", "neutral"] | None = Field(
        None, description="How the value is colored. Left out, the suggestion for its wording is used."
    )
    meaning: Literal["not_started", "open", "at_risk", "blocked", "done"] | None = Field(
        None,
        description="For a status list, what the value means. Left out, the suggestion for its wording is used, and "
        "open work when there is none. A list with no meanings refuses one.",
    )

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

    def describe(self, view: Any = None) -> str | None:
        return f"Bring back {named(view, 'snapshot', self.snapshot)} from the Set aside folder"


class SourceLimitOp(OpModel):
    """Narrow who may see a message to a group the message names ("only the print team"). The limit only narrows: the
    group must be among the people the message went to and came from, or within the limit it already has. Applies at
    once, with Undo; only the person widens it."""

    op: Literal["source.limit"] = "source.limit"
    id: str = Field(description="The id of the message's source: the input this run was given.")
    people: list[str] = Field(min_length=1, description="The people in the group, each by name or id.")
    group: str = Field(min_length=1, max_length=120, description="The group, in the message's own words.")
    evidence: EvidenceIn = Field(description="The exact words from the message that name the group.")

    def describe(self, view: Any = None) -> str | None:
        return f"Limit {named(view, 'source', self.id)} to {self.group}"


class SourceWidenOp(OpModel):
    """Widen who may see a message: add people to its audience, or remove the limit. Only the person uses it; Undo puts
    the narrower audience back."""

    op: Literal["source.widen"] = "source.widen"
    id: str = Field(description="The id of the message's source.")
    people: list[str] = Field(default_factory=list, description="The people to add, each by name or id.")
    open: bool = Field(False, description="True to remove the limit, so anyone may see it.")

    @model_validator(mode="after")
    def _one_way(self) -> SourceWidenOp:
        if self.open == bool(self.people):
            raise ValueError("name the people to add, or set open to remove the limit, not both and not neither")
        return self

    def describe(self, view: Any = None) -> str | None:
        what = named(view, "source", self.id)
        return f"Remove the limit on {what}" if self.open else f"Widen the limit on {what}"


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

    def describe(self, view: Any = None) -> str | None:
        return f"Retire {named(view, 'rule', self.id)}"


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

    def describe(self, view: Any = None) -> str | None:
        return f"Change {named(view, 'lesson', self.id)}"


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

    def describe(self, view: Any = None) -> str | None:
        return f"Change {named(view, 'glossary_entry', self.id)}"


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

    def describe(self, view: Any = None) -> str | None:
        return f"Retire {named_one_of(view, KNOWLEDGE_KINDS, self.id)}"


Op = Annotated[
    NoteOp
    | FactOp
    | EventAddOp
    | EventSetOp
    | SeriesAddOp
    | SeriesLinkOp
    | AgendaAddOp
    | RecordSetOp
    | RecordLogOp
    | ActionAddOp
    | ActionReplyOp
    | ActionCloseOp
    | ActionHoldOp
    | ActionUnholdOp
    | ActionDropOp
    | ActionMoveOp
    | ActionPartOp
    | ActionNewsOp
    | QuestionAddOp
    | QuestionDoneOp
    | QuestionUpdateOp
    | QuestionMoveOp
    | QuestionDropOp
    | QuestionMarkSentOp
    | PersonAddOp
    | PersonContactOp
    | PersonStanceOp
    | StageMoveOp
    | RecordDeleteOp
    | FileAddOp
    | ProjectAddOp
    | ProjectRoleOp
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
    | SourceLimitOp
    | SourceWidenOp
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
    "event.set": EventSetOp,
    "series.add": SeriesAddOp,
    "series.link": SeriesLinkOp,
    "agenda.add": AgendaAddOp,
    "record.set": RecordSetOp,
    "record.log": RecordLogOp,
    "action.add": ActionAddOp,
    "action.reply": ActionReplyOp,
    "action.close": ActionCloseOp,
    "action.hold": ActionHoldOp,
    "action.unhold": ActionUnholdOp,
    "action.drop": ActionDropOp,
    "action.move": ActionMoveOp,
    "action.part": ActionPartOp,
    "action.news": ActionNewsOp,
    "question.add": QuestionAddOp,
    "question.done": QuestionDoneOp,
    "question.update": QuestionUpdateOp,
    "question.move": QuestionMoveOp,
    "question.drop": QuestionDropOp,
    "question.mark_sent": QuestionMarkSentOp,
    "person.add": PersonAddOp,
    "person.contact": PersonContactOp,
    "person.stance": PersonStanceOp,
    "stage.move": StageMoveOp,
    "record.delete": RecordDeleteOp,
    "file.add": FileAddOp,
    "project.add": ProjectAddOp,
    "project.role": ProjectRoleOp,
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
    "source.limit": SourceLimitOp,
    "source.widen": SourceWidenOp,
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
    "action.reply",
    "question.update",
    "question.move",
    "question.mark_sent",
    "source.widen",
}

TIERS: dict[str, Tier] = (
    {name: "data" for name in OP_MODELS}
    | {
        "record.delete": "system",
        "project.add": "system",
        "project.role": "system",
        "list.add": "system",
        "list.rename": "system",
        "list.merge": "system",
        "list.retire": "system",
        "mail.restore": "system",
        "rule.add": "system",
        "rule.retire": "system",
        "person.stance": "system",
        "agenda.add": "system",
    }
    | {name: "system" for name in KNOWLEDGE_OPS}
)

#: Ops whose evidence is required (record.set requires it for the fields in EVIDENCE_FIELDS).
NEEDS_EVIDENCE = {
    "fact",
    "event.add",
    "event.set",
    "series.add",
    "series.link",
    "agenda.add",
    "action.add",
    "action.close",
    "action.hold",
    "action.unhold",
    "action.drop",
    "action.move",
    "action.part",
    "action.news",
    "question.drop",
    "question.done",
    "person.contact",
    "person.stance",
    "project.role",
    "source.limit",
}
#: Ops that need evidence from the assistant but not when the person makes them: their own act is not a claim from an
#: input, so a person's action or screen may use them without a quote.
EVIDENCE_UNLESS_PERSON = {
    "agenda.add",
    "action.close",
    "action.hold",
    "action.unhold",
    "action.drop",
    "action.move",
    "action.part",
    "question.drop",
}
EVIDENCE_FIELDS = {"due", "status", "owners", "target", "owner", "event", "series"}

#: Fields record.set may change, per kind.
SETTABLE: dict[str, set[str]] = {
    "project": {"status", "phase", "target", "priority", "summary", "parent", "language", "owner"},
    "action": {"text", "due", "notes", "event", "series"},
    "question": {"title", "text", "event", "series"},
    "fact": {"event", "series"},
    "person": {"role", "org", "why_they_matter", "side", "relation"},
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


def _field_line(name: str, info: Any, depth: int = 0) -> str:
    """A field as the reference lists it: its key, `?` when it may be left out, and its shape when its name alone
    doesn't give it (the keys of a nested object, the values a choice allows, the kind of id a reference holds)."""
    ref = next((m for m in info.metadata if isinstance(m, RefTo)), None)
    shape = f"{ref.kind} id" if ref is not None else _shape(info.annotation, depth)
    return f"{name}{'' if info.is_required() else '?'}" + (f": {shape}" if shape else "")


#: What an item of a list of plain values is called in the reference.
_PLAIN: dict[Any, str] = {str: "text", int: "number", float: "number", bool: "true or false", date: "date"}


def _shape(annotation: Any, depth: int = 0) -> str | None:
    """The shape of a value for the reference, or None when the field's name says enough (text, numbers, dates)."""
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *marks = get_args(annotation)
        ref = next((m for m in marks if isinstance(m, RefTo)), None)
        return f"{ref.kind} id" if ref is not None else _shape(base, depth)
    if origin in (Union, types.UnionType):
        options = [a for a in get_args(annotation) if a is not type(None)]
        return _shape(options[0], depth) if len(options) == 1 else None
    if origin is Literal:
        return " | ".join(json.dumps(value) for value in get_args(annotation))
    if origin in (list, tuple, set, frozenset):
        inner = get_args(annotation)[0] if get_args(annotation) else Any
        return f"[{_shape(inner, depth) or _PLAIN.get(inner, 'value')}]"
    if origin is dict or annotation is dict:
        return "{field: value}"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if depth >= 2:
            return "{...}"
        keys = [_field_line(info.alias or key, info, depth + 1) for key, info in annotation.model_fields.items()]
        return "{" + ", ".join(keys) + "}"
    return None


def reach_choices(plugins: Any = None) -> dict[str, list[str]]:
    """The values a reach (`applies_to`) may name: the kinds of work and the record types there are, the plugins' own
    included when `plugins` (the workspace's plugin host) is given."""
    from engine.records import REGISTRY
    from engine.tasks import TASKS

    tasks = plugins.tasks if plugins is not None else TASKS
    records = plugins.records if plugins is not None else REGISTRY
    return {"task_kinds": sorted(tasks), "records": sorted(records)}


def reach_problem(scope: Any, choices: dict[str, list[str]], records: dict[str, Any] | None = None) -> str | None:
    """Why a reach names something that doesn't exist, or None: each task kind must be a kind of work there is, and
    each record target a record type there is, or `type.field` with a field of that type. A reach that named something
    else would apply nowhere, silently."""
    if scope is None:
        return None
    unknown = [t for t in scope.task_kinds if t not in choices["task_kinds"]]
    if unknown:
        return f"{', '.join(unknown)} isn't a kind of work; applies_to.task_kinds takes only these: " + ", ".join(
            choices["task_kinds"]
        )
    for target in scope.records:
        kind, _, field = target.partition(".")
        model = (records or {}).get(kind)
        if kind not in choices["records"]:
            return f"{kind} isn't a record type; applies_to.records takes only these: " + ", ".join(choices["records"])
        if field and model is not None and field not in getattr(model, "model_fields", {}):
            return f"{kind} has no field {field}"
    return None


def reference_for(
    op_names: list[str],
    registry: dict | None = None,
    invariants: dict | None = None,
    reach: dict[str, list[str]] | None = None,
) -> str:
    """A readable op reference for the prompt: each op, what it's for and its fields, with the one-line constraint of
    each invariant that applies to it under it. Constraints that apply to every op follow the list once. It opens with
    the shape every op takes, since the reference is all a model sees of it and no prompt may be relied on to say so.
    When an op has a reach (`applies_to`), the values it may name follow the list: `reach` (from `reach_choices`), else
    the core's own."""
    from engine import invariants as shipped

    known = invariants if invariants is not None else shipped.load()
    lines = []
    if op_names:
        lines.append(
            'Each op is one JSON object: an "op" field naming it, beside its fields, for example '
            f'{{"op": "{op_names[0]}", ...}}.'
        )
    for name in op_names:
        model = (registry or OP_MODELS)[name]
        fields = []
        for key, info in model.model_fields.items():
            if key in ("op", "group"):
                continue
            fields.append(_field_line(info.alias or key, info))
        doc = (model.__doc__ or "").strip()
        lines.append(f'- "{name}": {doc} Fields: {", ".join(fields)}.')
        lines += [f"  Always checked: {line}" for line in shipped.lines_for(name, known)]
    models = [(registry or OP_MODELS)[name] for name in op_names]
    if any("applies_to" in m.model_fields for m in models):
        values = reach or reach_choices()
        lines.append(
            "In applies_to, task_kinds name kinds of work, only these: "
            + ", ".join(values["task_kinds"])
            + "; records name record types, only these: "
            + ", ".join(values["records"])
            + "."
        )
    if op_names:
        lines += [f"Every op is checked: {line}" for line in shipped.lines_for_every_op(known)]
    return "\n".join(lines)
