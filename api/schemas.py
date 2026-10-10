"""Response and request models for the API. The web client's types are generated from these through OpenAPI, so a
changed field here fails the web build instead of breaking the UI at run time.

Models carry data, not wording: the UI words everything through its wording sheet.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---- requests --------------------------------------------------------------------------------------------------------


class HandIn(BaseModel):
    note: str = ""
    pasted: str = ""


class SendBack(BaseModel):
    note: str


class UndoChoice(BaseModel):
    ops: list[int] | None = Field(None, description="Indices of the items to undo; all of them when left out.")


class PersonChoice(BaseModel):
    person: str | None = None


class SentText(BaseModel):
    text: str | None = Field(None, description="The message as the PM sent it, to notice edits.")


class Answer(BaseModel):
    text: str | None = Field(None, description="A written answer.")
    person: str | None = Field(None, description="The person chosen, for questions that ask who.")


class Reply(BaseModel):
    text: str = Field(description="The reply as received, pasted by the PM.")


class ActionState(BaseModel):
    status: Literal["open", "done"]


# ---- responses -------------------------------------------------------------------------------------------------------


class Ok(BaseModel):
    ok: str


class Handed(BaseModel):
    request: str
    source: str | None


class Requeued(BaseModel):
    request: str


class BackupStatus(BaseModel):
    configured: bool
    last_success: str | None
    age_hours: float | None
    needs_attention: bool
    last_error: str | None


class RequestCounts(BaseModel):
    queued: int
    running: int
    review: int
    needs_you: int


class Status(BaseModel):
    backup: BackupStatus
    requests: RequestCounts
    version: int
    restart_needed: str | None = Field(None, description="Why new work waits until the cockpit restarts, if it does.")


class Option(BaseModel):
    id: str
    name: str


class Ask(BaseModel):
    """A question to the PM that an item waits on: who a name is, or who owns an action."""

    id: str
    status: str
    about: Literal["held-op", "owner", "other"]
    name: str | None = Field(None, description="The name the assistant couldn't place, for who-is questions.")
    options: list[Option]


class RecordRef(BaseModel):
    kind: str
    id: str


class Evidence(BaseModel):
    quote: str


class OpMeta(BaseModel):
    owners: list[str] = []
    due: str | None = None
    project: str | None = None
    action_status: str | None = None
    to: str | None = None
    field: str | None = None
    value: Any = None


class OpView(BaseModel):
    index: int
    op: str
    status: Literal["applied", "held", "refused", "undone"]
    reason: str | None
    group: str
    title: str
    meta: OpMeta
    evidence: Evidence | None = None
    record: RecordRef | None = None
    ask: Ask | None = None


class ChangesetView(BaseModel):
    id: str
    summary: str
    status: str
    reviewed: bool
    trust: Literal["trusted", "untrusted"]
    ops: list[OpView]


class ChangeItem(BaseModel):
    id: str
    state: Literal["queued", "running", "review", "done", "needs_you", "failed"]
    waiting: str | None
    created_at: str
    note: str | None
    source: str | None
    source_title: str | None
    changeset: ChangesetView | None


class UndoReport(BaseModel):
    restored: list[Any]
    skipped: list[Any]


class Link(BaseModel):
    label: str
    url: str


class SourceView(BaseModel):
    id: str
    title: str
    kind: str
    trust: Literal["trusted", "untrusted"]
    received_at: str
    url: str | None
    text: str


class FollowupQuestion(BaseModel):
    id: str
    title: str
    text: str
    links: list[Link]
    kind: str
    status: Literal["open", "sent"]
    waiting_days: int | None
    about: str | None
    options: list[Option]


class FollowupAction(BaseModel):
    id: str
    text: str
    due: str | None
    project_name: str
    told: str | None
    told_days: int | None


class FollowupSection(BaseModel):
    person: str
    name: str
    is_pm: bool
    questions: list[FollowupQuestion]
    actions: list[FollowupAction]
    message: str
    to_send: int


class SentCounts(BaseModel):
    questions: int
    actions: int
    question_ids: list[str]
    action_ids: list[str]


class Unmark(BaseModel):
    question_ids: list[str] = []
    action_ids: list[str] = []


class PersonView(BaseModel):
    id: str
    name: str
    role: str | None
    org: str | None = None
    aliases: list[str] = []
    status: Literal["active", "left"] = "active"
    is_pm: bool = False


class PersonIn(BaseModel):
    full_name: str = Field(min_length=1)
    role: str | None = None
    org: str | None = None
    aliases: list[str] = []


class PersonPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1)
    role: str | None = None
    org: str | None = None
    aliases: list[str] | None = None
    status: Literal["active", "left"] | None = None


class ProjectView(BaseModel):
    id: str
    name: str
    group: str | None
    status: str | None
    phase: str | None
    target: str | None
    owner: str | None
    owner_name: str | None
    summary: str | None


class ProjectIn(BaseModel):
    name: str = Field(min_length=1)
    group: str | None = None
    status: str | None = None
    phase: str | None = None
    target: str | None = Field(None, description="A date, YYYY-MM-DD.")
    owner: str | None = None
    summary: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1)
    group: str | None = None
    status: str | None = None
    phase: str | None = None
    target: str | None = None
    owner: str | None = None
    summary: str | None = None


class Created(BaseModel):
    id: str


class BackupTarget(BaseModel):
    label: str | None
    last_success: str | None
    last_error: str | None


class RuntimeConfig(BaseModel):
    base_path: str
    api_base: str
    assistant_name: str
    workspace_name: str
    version: str
    pm: str | None
    narrow_below_px: int
    toast_seconds: float
    shortcuts: dict[str, str]
    wording: dict[str, str]


class PluginStatusView(BaseModel):
    name: str
    state: str
    version: str | None = None
    reason: str | None = None


class RecordReference(BaseModel):
    kind: str
    id: str


class StageLabel(BaseModel):
    id: str
    label: str


class StageCheckView(BaseModel):
    id: str
    passed: bool
    reason: str


class StageView(BaseModel):
    record: RecordReference
    version: int
    current: str | None
    current_label: str | None
    next: StageLabel | None
    checks: list[StageCheckView]
    ready: bool


class StageHistoryEntry(BaseModel):
    sequence: int
    at: str
    from_stage: str | None
    to_stage: str | None
    version: int
    actor: str
    op: str
    changeset: str | None
    request: str | None
    source: dict[str, Any] | None


class RecordView(BaseModel):
    kind: str
    id: str
    version: int
    data: dict[str, Any]
    stages: StageView
    stage_history: list[StageHistoryEntry]


class StageMove(BaseModel):
    record: RecordReference
    to: str = Field(min_length=1)
    read_version: int = Field(ge=1)


class StageMoved(BaseModel):
    changeset: str
    stages: StageView


class ReadVersion(BaseModel):
    read_version: int = Field(ge=1)


class StageTaskOrigin(BaseModel):
    kind: str
    record: str
    stage: str
    changeset: str


class StageRequestView(BaseModel):
    id: str
    version: int
    task: str
    state: str
    approval: Literal["required", "granted"]
    waiting: str | None
    stage_start: StageTaskOrigin
