"""A small fictional plugin demonstrating a ledger-backed op and a safe event reaction."""

from typing import ClassVar, Literal

from pydantic import Field

from engine.plugin_api import EventContext, OpModel, OpWriter, ReadView, Record, Registrar, Settings, StageCheckResult


class Config(Settings):
    draft_label: str = Field("Recorded", description="Default wording for the initial reminder stage.")
    ready_label: str = Field("Ready for review", description="Default wording for the review stage.")
    check_pass: str = Field("The reminder has text.", description="Reason shown when the entry check passes.")
    check_fail: str = Field("Add text to the reminder first.", description="Reason shown when the entry check fails.")
    ask_on_add: bool = Field(True, description="File a question for the PM when a reminder is added.")
    question: str = Field("Review the new reminder?", description="Title of the question filed for the PM.")


class Reminder(Record):
    record_kind: ClassVar[str] = "example/reminder"
    prefix: ClassVar[str] = "REM"
    text: str = Field(min_length=1)


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


def register(registrar: Registrar) -> None:
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
