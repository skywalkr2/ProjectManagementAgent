"""A small fictional plugin demonstrating a ledger-backed op and a safe event reaction."""

from typing import Annotated, ClassVar, Literal

from pydantic import Field

from engine.plugin_api import (
    ActionContext,
    Choice,
    EventContext,
    InList,
    OpModel,
    OpWriter,
    Proposal,
    ReadView,
    Record,
    Registrar,
    Settings,
    StageCheckResult,
    StoreError,
)


class Config(Settings):
    draft_label: str = Field("Recorded", description="Default wording for the initial reminder stage.")
    ready_label: str = Field("Ready for review", description="Default wording for the review stage.")
    check_pass: str = Field("The reminder has text.", description="Reason shown when the entry check passes.")
    check_fail: str = Field("Add text to the reminder first.", description="Reason shown when the entry check fails.")
    ask_on_add: bool = Field(True, description="File a question for the PM when a reminder is added.")
    question: str = Field("Review the new reminder?", description="Title of the question filed for the PM.")
    note_action_label: str = Field(
        "Make a note from this file", description="Name of the action that makes a note from a text file."
    )
    note_summary: str = Field(
        "Make a note from {name}",
        description="One line saying what the note action will do; {name} is the file's name.",
    )
    note_count_label: str = Field(
        "Include the word count", description="Label of the choice that adds the file's word count to the note."
    )
    note_count_text: str = Field(
        "({n} words)", description="What is added to the note when the word count is on; {n} is the count."
    )
    note_not_text: str = Field(
        "Only plain text files can be turned into a note.", description="Shown when the file is not plain text."
    )
    note_empty: str = Field(
        "That file has no text to make a note from.", description="Shown when the file has no text."
    )
    kinds_label: str = Field("Reminder kind", description="What the list of reminder kinds is called on screen.")
    kinds: list[str] = Field(
        default_factory=lambda: ["Call", "Email", "Errand"],
        description="The first kinds of reminder a workspace's list offers; after that the person changes the list.",
    )


class Reminder(Record):
    record_kind: ClassVar[str] = "example/reminder"
    prefix: ClassVar[str] = "REM"
    text: str = Field(min_length=1)
    kind: Annotated[str | None, InList("example/kind")] = Field(
        None, description="What sort of reminder it is, from the reminder kind list."
    )


class AddReminder(OpModel):
    op: Literal["example/reminder.add"]
    writes: ClassVar[dict[str, tuple[str, ...]]] = {Reminder.record_kind: ("*",)}
    text: str = Field(min_length=1)


def validate(op: AddReminder, view: ReadView) -> list[str]:
    return (
        ["reminder already exists"] if any(r.data["text"] == op.text for r in view.list(Reminder.record_kind)) else []
    )


def apply(op: AddReminder, writer: OpWriter, config: Config) -> None:
    writer.create(Reminder.record_kind, {"text": op.text})


def changed(event: dict, context: EventContext) -> None:
    if event["kind"] == Reminder.record_kind and event["version"] == 1 and context.config.ask_on_add:
        context.file_question(context.config.question)


def ready(record, view: ReadView, config: Config) -> StageCheckResult:
    passed = bool(record.data["text"].strip())
    return StageCheckResult(passed, config.check_pass if passed else config.check_fail)


NOTE_LENGTH = 200


def note_from_file(target, context: ActionContext, choices: dict) -> Proposal:
    config = context.config
    if target.data["media_type"] != "text/plain":
        raise StoreError(config.note_not_text)
    text = context.file_bytes(target.id).decode("utf-8", errors="replace")
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first:
        raise StoreError(config.note_empty)
    count = bool(choices.get("count", True))
    note = first[:NOTE_LENGTH].strip()
    if count:
        note = f"{note} {config.note_count_text.format(n=len(text.split()))}"
    return Proposal(
        config.note_summary.format(name=target.data["name"]),
        ops=[{"op": "note", "text": note}],
        choices=[Choice("count", config.note_count_label, count)],
    )


def reminder_words(case: dict, produced: list[dict], view: ReadView) -> list[str]:
    """Scores a run that should have added a reminder: every word the case lists is in the reminders it added."""
    added = [p for p in produced if p["status"] == "applied" and p["op"]["op"] == "example/reminder.add"]
    if not added:
        return ["no reminder was added"]
    kept = {r.id: r.data["text"].lower() for r in view.list(Reminder.record_kind)}
    texts = [kept[ref["id"]] for p in added for ref in p["records"] if ref["id"] in kept]
    return [
        f"no reminder mentions {word}" for word in case.get("words", []) if not any(word.lower() in t for t in texts)
    ]


def register(registrar: Registrar) -> None:
    registrar.value_list("example/kind", label=registrar.config.kinds_label, values=registrar.config.kinds)
    registrar.record_type(Reminder)
    registrar.stage_check("example/has-text", ready)
    registrar.stages(
        Reminder.record_kind,
        [
            {"id": "recorded", "label": registrar.config.draft_label},
            {"id": "ready", "label": registrar.config.ready_label, "entry": ["example/has-text"]},
        ],
    )
    registrar.op(AddReminder, "data", apply)
    registrar.op_validator("example/reminder.add", validate)
    registrar.task_kind("example/capture", ops=("example/reminder.add",))
    registrar.subscribe("record.changed", changed)
    registrar.action(
        "example/note-from-file",
        label=registrar.config.note_action_label,
        run=note_from_file,
        on="file",
        file_kinds=("attachment",),
    )
    registrar.scorer("example/reminder-words", reminder_words)
