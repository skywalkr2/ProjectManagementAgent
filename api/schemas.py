"""Response and request models for the API. The web client's types are generated from these through OpenAPI, so a
changed field here fails the web build instead of breaking the UI at run time.

Models carry data, not wording: the UI words everything through its wording sheet.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---- requests --------------------------------------------------------------------------------------------------------


class HandIn(BaseModel):
    note: str = ""
    pasted: str = ""
    data_level: Literal["open", "internal", "restricted"] | None = Field(
        None, description="How sensitive it is, when the person says it is more than the usual."
    )
    project: str | None = Field(None, description="The project it is about, when the person says.")


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


class RequestChanged(BaseModel):
    ok: str
    version: int = Field(description="The request's version after the change, for undoing it.")


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


class AiState(BaseModel):
    """Whether the assistant can do its work: set up, tested, and answering."""

    state: Literal["ok", "untested", "failing", "not_set_up", "stand_in"]
    detail: str | None = Field(None, description="The provider's own reason when there is one, shortened.")


class SpendStatus(BaseModel):
    """What the assistant's work has cost today and this month (UTC), against the configured limits."""

    today_usd: float
    month_usd: float
    per_day_usd: float
    per_month_usd: float
    warn: bool = Field(description="Either total has reached the configured share of its limit.")
    warn_today: bool = Field(description="Today's total has reached that share of the daily limit.")
    warn_month: bool = Field(description="This month's total has reached that share of the monthly limit.")


class Status(BaseModel):
    backup: BackupStatus
    ai: AiState
    spend: SpendStatus
    requests: RequestCounts
    version: int
    restart_needed: str | None = Field(None, description="Why new work waits until the cockpit restarts, if it does.")
    can_restart: bool = Field(
        False, description="The app can start itself again when the person asks (POST /api/restart)."
    )
    restart_for: list[str] = Field(
        default_factory=list,
        description='What waits for the restart: settings keys (their labels are in GET /api/settings), and "code" '
        "when the app itself was updated while running.",
    )


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
    second_opinion: Literal["other_account", "same_account"] | None = Field(
        None,
        description="For an independent check: run on an account other than the one that wrote the work, or on the "
        "same account as a fresh run the person accepted.",
    )


class ChangeItem(BaseModel):
    id: str
    version: int
    dismissed: bool
    state: Literal["queued", "running", "review", "done", "needs_you", "failed"]
    waiting: str | None
    created_at: str
    note: str | None
    source: str | None
    source_title: str | None
    approval: Literal["required", "granted"] | None = Field(
        None, description="Whether the request waits for the person's go or has had it."
    )
    stage_task: bool = Field(False, description="The request was started by a stage, so the stage views show its go.")
    estimate_usd: float | None = Field(None, description="What the run was estimated to cost when it asked for a go.")
    refused: bool = Field(
        False, description="The account declined it under its own policy; it can be sent to another account."
    )
    follows: str | None = Field(None, description="The change (changeset id) this work followed from, if any.")
    follows_summary: str | None = Field(None, description="That change's one-line summary, for the row.")
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
    sent: str | None
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
    org: str | None = Field(None, description="The id of the organization they work for.")
    org_name: str | None = Field(None, description="That organization's name, for showing.")
    aliases: list[str] = []
    status: Literal["active", "left"] = "active"
    is_pm: bool = False


class PersonIn(BaseModel):
    full_name: str = Field(min_length=1)
    role: str | None = None
    org: str | None = Field(None, description="An organization's id, from GET /api/organizations.")
    aliases: list[str] = []


class PersonPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1)
    role: str | None = None
    org: str | None = Field(None, description="An organization's id; null for none.")
    aliases: list[str] | None = None
    status: Literal["active", "left"] | None = None


class OrganizationView(BaseModel):
    id: str
    name: str
    aliases: list[str] = []
    notes: str | None = None
    people: int = Field(0, description="How many people on file work for it.")


class OrganizationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    aliases: list[str] = []
    notes: str | None = None


class OrganizationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1)
    aliases: list[str] | None = None
    notes: str | None = None


class ProjectView(BaseModel):
    id: str
    name: str
    group: str | None
    status: str | None
    phase: str | None
    priority: str | None = None
    target: str | None
    owner: str | None
    owner_name: str | None
    summary: str | None
    parent: str | None = Field(None, description="The project this one belongs to.")
    language: str = Field("en-US", description="The language work on it is written in, its own or inherited.")
    language_own: bool = Field(False, description="Whether the language is set on this project rather than inherited.")
    content_levels: list[str] = Field(default_factory=list)
    budget_usd: float | None = None
    spent_usd: float = Field(0.0, description="What AI work on it and everything in it has cost.")


class NoteView(BaseModel):
    id: str
    text: str
    project: str | None
    project_name: str | None
    created_at: str | None = Field(None, description="When the note was filed, from the first record of it.")
    trust: Literal["trusted", "untrusted"]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1)
    group: str | None = Field(None, description="From the project-group list.")
    status: str | None = Field(None, description="From the project-status list.")
    phase: str | None = Field(None, description="From the project-phase list.")
    priority: str | None = Field(None, description="From the project-priority list.")
    target: str | None = Field(None, description="A date, YYYY-MM-DD.")
    owner: str | None = None
    summary: str | None = None
    parent: str | None = None
    language: str | None = Field(None, description="A language tag such as en-US; unset to inherit.")
    budget_usd: float | None = Field(None, ge=0)
    content_levels: list[str] = Field(default_factory=list)


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1)
    parent: str | None = None
    language: str | None = Field(None, description="A language tag such as en-US; null to inherit.")
    budget_usd: float | None = Field(None, ge=0, description="null for no cap.")
    content_levels: list[str] | None = Field(
        None, description="Content levels its material carries, from the AI settings; the person's choice."
    )
    group: str | None = None
    status: str | None = None
    phase: str | None = None
    priority: str | None = None
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
    demo: bool = Field(False, description="The workspace holds made-up example data; every screen says so.")
    instance: str | None = Field(
        None, description="Changes every time the app starts, so a screen can tell it restarted."
    )
    feedback_to: str | None = Field(None, description="Where the feedback button writes its email, if anywhere.")


class PluginStatusView(BaseModel):
    name: str
    state: str
    version: str | None = None
    reason: str | None = None
    tools: dict[str, str] = Field(default_factory=dict, description="Each declared program and what was found.")
    notes: list[str] = Field(default_factory=list, description="What the person should know, though it loaded.")


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
    title: str
    version: int
    current: str | None
    current_label: str | None
    next: StageLabel | None
    stages: list[StageLabel]
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
    estimate_usd: float | None = Field(None, description="What the run was estimated to cost, once it has an estimate.")


class FileView(BaseModel):
    """A file a person added or a program wrote; its content is fetched separately."""

    id: str
    version: int
    name: str
    media_type: str
    size: int
    file_kind: str
    kind_label: str = Field(description="What to call the file kind on screen.")
    project: str | None
    meta: dict[str, Any]
    origin: Literal["upload", "tool"]
    replaces: str | None
    added_at: str


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use: str | None = Field(None, description='Another account to try, as "provider/model" from the AI settings.')


class AccountChoice(BaseModel):
    """An AI account the person may send this request to; named as in their settings, never by model."""

    use: str
    label: str


class TextVersionView(BaseModel):
    id: str
    number: int
    version: int = Field(description="The record version, to state when reviewing it.")
    status: str
    source: str
    words: int
    base: int | None
    note: str | None
    unmapped: list[str] = Field(
        default_factory=list, description="Taken back from a working copy: what couldn't be read back, to show."
    )
    questions: list[str] = Field(default_factory=list, description="A draft's questions for the person, to show.")
    created_at: str


class AuthorSpan(BaseModel):
    start: int
    end: int
    kind: str = Field(description="person, assistant (drafted) or assistant_edit (the person's text changed).")
    words: int = 0


class TextFieldView(BaseModel):
    """A long text field: its current text, who wrote what, and every version."""

    text: str
    current: int | None
    authorship: list[AuthorSpan]
    versions: list[TextVersionView]


class TextRegion(BaseModel):
    id: str = Field(description="The change's id for the choices; empty for the current text's own changes (kept).")
    side: str = Field(description="pending, current (kept as is) or both (a conflict).")
    base: str
    current: str
    pending: str


class TextReview(BaseModel):
    """What reviewing a pending version needs."""

    version: TextVersionView
    current: int | None
    three_way: bool = Field(description="The text moved on since the version's base; changes are against both.")
    regions: list[TextRegion]
    pending_text: str


class TextChoices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read_version: int = Field(ge=1)
    choices: dict[str, Literal["accept", "reject"]] = Field(default_factory=dict)


class TextEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    id: str
    field: str
    text: str


class Applied(BaseModel):
    changeset: str


class WorkingCopyFormatView(BaseModel):
    name: str
    label: str
    extension: str


class WorkingCopyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str
    kind: str
    id: str
    field: str


class WorkingCopyView(BaseModel):
    """A long text field handed out as a file, and what came back."""

    id: str
    format: str
    label: str
    field: str
    base: int | None
    status: str
    stale: bool = Field(description="The text moved on since it was handed out; taking it back merges three ways.")
    file: str = Field(description="The file handed out; download it from /files/<id>/content.")
    proposal: str | None
    handed_at: str
    returned_at: str | None


class TakenBack(BaseModel):
    unchanged: bool = Field(description="The file came back untouched, so nothing was proposed.")
    version: str | None = Field(description="The text version it became, to review.")
    unmapped: list[str] = Field(description="What couldn't be read back into the text.")


class FieldView(BaseModel):
    name: str
    description: str = ""
    long_text: str | None = Field(None, description="The long text format, for a long text field.")
    refers_to: str | None = Field(None, description="The kind of record the field holds an id of.")
    type: Literal["text", "long_text", "number", "yes_no", "date", "choice", "reference", "list", "other"] = Field(
        "other", description="What kind of value it holds, for the edit form."
    )
    options: list[str] = Field(default_factory=list, description="For a choice: the values allowed.")
    value_list: str | None = Field(
        None, description="For a field whose values come from a value list: its name, so the form can add to it."
    )
    required: bool = False
    editable: bool = Field(True, description="The person can change it with a field edit (not the id or stage).")


class ValueListView(BaseModel):
    """A value list: what a field's dropdown offers."""

    id: str
    name: str
    label: str
    values: list[str] = Field(description="The values offered, in order.")
    retired: list[str] = Field(description="Values no longer offered that records may still hold.")
    used_by: list[str] = Field(description="The fields that take their values from it, as kind.field.")


class ListValueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=80)


class ListRenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1)
    to: str = Field(min_length=1, max_length=80)


class KindView(BaseModel):
    """What a kind of record holds, for screens that show any record."""

    kind: str
    fields: list[FieldView]


class RecordEdit(BaseModel):
    """The person's own change to fields of a shown record."""

    model_config = ConfigDict(extra="forbid")
    kind: str
    id: str
    fields: dict[str, Any]
    read_version: int = Field(ge=1)


class GenericRecordView(BaseModel):
    """Any shown record: its ordinary fields and the names of its long text fields (read those from /texts)."""

    kind: str
    id: str
    version: int
    fields: dict[str, Any]
    long_text: list[str]


class OutsideEditView(BaseModel):
    path: str = Field(description="The file in the synced folder.")
    proposal: str | None = Field(None, description="The changeset it became, to review.")
    version: str | None = Field(None, description="The text version it became, to review.")
    problem: str | None = Field(None, description="Why it couldn't be read back.")


class SyncView(BaseModel):
    """The synced folder's state."""

    folder: str = Field(description="The configured folder; empty when off.")
    problem: str | None = Field(description="Why it can't be written now, if it can't.")
    stopped: bool = Field(description="Another computer opened the workspace; this copy stopped writing.")
    changed_outside: list[str]
    removed_outside: list[str]
    rebuilt: list[str]
    outside_edits: list[OutsideEditView]
    conflict_copies: list[str]


class AgendaItemView(BaseModel):
    """An event from a watched calendar, on today or the next configured days."""

    snapshot: str
    source: str = Field(description="The watched source's id; its label is in GET /api/sources.")
    title: str
    start: str = Field(description="ISO 8601: a date-time with its offset, or a date for an all-day event.")
    end: str | None = None
    all_day: bool
    where: str | None = None
    link: str | None = Field(None, description="Where to open it; untrusted, so show its real domain.")
    cancelled: bool = Field(description="The organizer called it off.")
    days: list[date] = Field(description="The days it falls on, in the person's time zone.")


class ArrivedView(BaseModel):
    """A message from a watched mailbox, received within the configured hours."""

    snapshot: str
    source: str
    title: str
    sender: str | None = None
    received: str = Field(description="ISO 8601 date-time with its offset.")
    unread: bool | None = None
    link: str | None = None


class TodoView(BaseModel):
    """One of the person's own open actions."""

    action: str = Field(description="The action's id; its record is at GET /api/records/{id}.")
    text: str
    project: str | None = None
    due: date | None = None
    overdue: bool


class InboxView(BaseModel):
    items: list[ArrivedView]
    left_out: int = Field(description="Messages in the same hours that a triage rule closed (newsletters, say).")


class TodayLineView(BaseModel):
    """A line a plugin adds to Today."""

    plugin: str
    id: str
    text: str
    about: RecordReference | None = None
    action: str | None = Field(None, description="The one thing to do from it: a person action or a kind of work.")
    action_is: Literal["action", "task"] | None = Field(
        None, description="action: run it as a person action (/plugin-actions); task: start it as AI work."
    )
    why: str = ""
    until: str | None = None


class PanelView(BaseModel):
    """A plugin's screen, described as data (design 7.2)."""

    name: str
    title: str
    tab: str
    kind: str
    view: str
    columns: list[str]
    primary_action: str | None
    row_actions: list[str]
    new_action: str | None = Field(None, description="A person action on the workspace that adds one, shown above.")


class PanelRow(BaseModel):
    id: str
    values: dict[str, Any]


class JobView(BaseModel):
    """A plugin's scheduled work and its last run."""

    name: str
    plugin: str
    enabled: bool
    every_minutes: int
    last_run_at: str | None
    last_outcome: str | None
    last_error: str | None


class TaskKindView(BaseModel):
    """AI work the person can start, on a record of kind `on` or on the whole workspace."""

    name: str
    label: str
    on: str | None


class TaskStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    about: RecordReference | None = None
    note: str = Field("", description="Anything the person wants to say about this run; their own words.")


class TaskStarted(BaseModel):
    request: str


class PersonActionView(BaseModel):
    """Something a person can start on a record, a file or the workspace."""

    name: str
    label: str
    on: str | None = Field(description="The record kind it works on; none means the whole workspace.")


class ActionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: RecordReference | None = None
    choices: dict[str, str | bool] = Field(default_factory=dict)
    previous: str | None = Field(
        None, description="The review this one replaces; its ticks carry over to unchanged items."
    )
    kept: dict[str, bool] = Field(default_factory=dict, description="Items to keep (true) or drop (false), by id.")


class ActionApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    kept: dict[str, bool] = Field(default_factory=dict, description="The person's final ticks, by item id.")
    kept_requests: dict[str, bool] = Field(
        default_factory=dict, description="The person's final ticks on the AI work it would queue, by request id."
    )


class ChoiceOption(BaseModel):
    value: str
    label: str


class ActionChoice(BaseModel):
    id: str
    label: str
    value: str | bool
    options: list[ChoiceOption] = Field(description="The values to pick from; none means on or off.")
    help: str = ""
    group: str | None = None
    text: bool = Field(False, description="The person types the value, up to max_length characters.")
    max_length: int = 200


class ActionGroup(BaseModel):
    id: str
    heading: str
    explanation: str = ""


class ActionItem(BaseModel):
    """A change the person keeps or drops without running the action again."""

    id: str
    label: str
    group: str | None = None
    kept: bool
    ops: list[ProposedOp]
    refused: str | None = Field(None, description="Why this would be refused if applied now; it starts dropped.")


class ActionPreviewItem(BaseModel):
    name: str
    media_type: str
    caption: str = ""
    alt: str = Field("", description="What an image shows, for people who can't see it.")
    data_base64: str = Field(description="The preview's bytes; pictures or plain text only.")


class ProposedFile(BaseModel):
    name: str
    media_type: str
    size: int
    file_kind: str


class ProposedOp(BaseModel):
    op: str
    label: str


class ActionRequestView(BaseModel):
    id: str = Field(description="Its id in this review, for keeping or dropping it.")
    task: str
    label: str
    about: RecordReference | None = None
    note: str = ""
    kept: bool = True
    group: str | None = Field(None, description="The group it belongs to, so setting a group sets it too.")
    item: str | None = Field(None, description="The item it goes with: dropping that item drops it too.")


class ActionProposalView(BaseModel):
    """One action's proposal for the person's review; applying it needs the token."""

    token: str
    action: str
    summary: str
    ops: list[ProposedOp] = Field(description="Everything that applies with the ticks as they are now.")
    items: list[ActionItem] = Field(default_factory=list)
    groups: list[ActionGroup] = Field(default_factory=list)
    files: list[ProposedFile]
    previews: list[ActionPreviewItem]
    choices: list[ActionChoice]
    notes: list[str]
    requests: list[ActionRequestView] = Field(
        default_factory=list, description="AI work queued when it is applied, each waiting for the person's go."
    )
    problems: list[str] = Field(
        default_factory=list, description="Why parts outside the items would be refused if it were applied now."
    )
    expires_at: str


class ActionApplied(BaseModel):
    changeset: str
    applied: int
    held: int
    refused: int


class FileKindView(BaseModel):
    """A kind of file that can be added, with the details it asks for (as a JSON schema) and what it accepts."""

    name: str
    label: str
    accept: list[str]
    max_mb: float
    details_schema: dict[str, Any]


# ---- settings and setup ----------------------------------------------------------------------------------------------


class SettingItem(BaseModel):
    """One config key, for the Settings forms."""

    key: str = Field(description="Its dotted key, as in `cockpit config show`.")
    file: str
    group: str = Field(description="The section it belongs to: the file, or the file and its first part.")
    description: str
    type: Literal["text", "number", "integer", "yes_no", "choice", "list", "other"]
    options: list[str] = Field(default_factory=list)
    value: Any = None
    default: Any = None
    source: Literal["default", "file", "env", "flag"]
    locked: bool = Field(description="Set by an environment variable or a flag, so the screen can't change it.")
    basic: bool = Field(description="Shown first; the rest sit behind More settings.")
    editable: bool = Field(description="The screen can change it; others are changed in the file.")
    enabled_by: str | None = Field(
        None,
        description="The key of the switch this setting only matters with: shown after it, and greyed while that "
        "switch is off (a yes/no) or empty (a folder, say).",
    )
    picker: Literal["folder", "file"] | None = Field(
        None, description="Offer a chooser for this path instead of typing it."
    )
    plugin: str | None = Field(
        None,
        description="The add-on whose setting this is (its file is plugins/<name>); its name and label are in "
        "GET /api/plugins. None for the app's own settings.",
    )


class SettingsView(BaseModel):
    fingerprint: str = Field(description="Send it back with a save, so two saves never race.")
    items: list[SettingItem]


class SettingsSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: dict[str, Any] = Field(default_factory=dict, description="Key to its new value.")
    reset: list[str] = Field(default_factory=list, description="Keys going back to their defaults.")
    fingerprint: str


class SettingChangeView(BaseModel):
    key: str
    before: Any = None
    after: Any = None
    was_default: bool
    is_default: bool


class SettingsSaved(BaseModel):
    changes: list[SettingChangeView] = Field(description="What changed, for the read-back and Undo.")
    fingerprint: str
    needs_restart: bool = Field(
        description="These settings take effect after a restart. Nothing restarts until the person chooses to: ask "
        "them first, then POST /api/restart. False when the change is in use already (AI accounts are)."
    )


class SetupStepView(BaseModel):
    id: str = Field(
        description='A core step ("workspace", "template", "ai", "backup", "people", "first_note") or a plugin\'s step.'
    )
    done: bool
    skipped: bool
    label: str = Field("", description="A plugin step's own words; core steps take theirs from the wording sheet.")
    explanation: str = ""
    action: str | None = Field(None, description="A plugin step's person action, if it has one.")
    plugin: str | None = None
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Core settings a plugin step suggests, applied with the step's Apply."
    )
    sign_in: str | None = Field(None, description="For a step the core adds per sign-in: the sign-in's name.")


class SetupView(BaseModel):
    steps: list[SetupStepView]
    finished: bool = Field(description="Every step is done or skipped.")
    local: bool = Field(description="The app runs on the person's own computer, so folders can be picked here.")


class TemplateAdds(BaseModel):
    name: str = Field(description="What the list it adds is called, such as Requests.")
    fields: list[str] = Field(description="What each entry in it holds, by label.")
    stages: list[str] = Field(description="The steps an entry goes through, in order.")


class TemplateView(BaseModel):
    id: str
    name: str
    description: str
    adds: list[TemplateAdds] = Field(default_factory=list, description="What applying it sets up.")
    set_up: bool = Field(False, description="This workspace already has everything it adds.")


class TemplateApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str


class TemplateApplied(BaseModel):
    plugins: list[str]
    needs_restart: bool = Field(description="The template's add-ons start after a restart the person chooses.")


class RestartAsked(BaseModel):
    restarting: bool = Field(description="The app is restarting now; it is back in a few seconds.")


class FolderCheckView(BaseModel):
    path: str
    ok: bool
    problem: str | None = None
    free_mb: float | None = None


class FolderListView(BaseModel):
    path: str
    parent: str | None = None
    folders: list[str]


class BackupFolderAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    label: str = ""
    fingerprint: str


class EndpointView(BaseModel):
    id: str
    name: str = Field(description="The service's name, as the person knows it.")
    adapter: str = Field(description="The adapter to send when adding an account of this kind.")
    base_url: str = Field(description="Its address; empty when the person enters it.")
    key_url: str = Field("", description="Where the person makes a key, to open in a new tab; empty when none.")
    needs_key: bool = False
    local: bool = Field(False, description="A server on this computer: nothing leaves it.")
    allowed_data: list[Literal["open", "internal", "restricted"]] = Field(
        default_factory=lambda: ["open"], description="The data levels offered by default for an account of this kind."
    )
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Provider settings a new account of this kind starts with."
    )
    program: str = Field("", description="For a command-line agent: the program it runs.")
    installed: bool | None = Field(
        None, description="Whether that program is on this computer (None when it can't be told: a hosted app)."
    )
    model_examples: list[str] = Field(default_factory=list, description="Model names the program accepts.")
    model_optional: bool = Field(False, description="The program picks its own model when none is named.")
    note: str = ""


class AiAccountView(BaseModel):
    """An AI account in the settings, for the screens: never its key."""

    name: str = Field(description="Its short name in ai.yaml.")
    kind: str | None = Field(None, description="The kind of account it was made from (GET /api/ai/endpoints).")
    adapter: str
    base_url: str | None = None
    models: dict[str, str]
    used_for: list[str] = Field(description="The tiers whose main account it is.")
    has_key: bool = Field(description="A key or a reference to one is set.")


class AiAccountChange(BaseModel):
    """A change to an existing account: a new key, other models, or the work it does."""

    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(None, description="A new pasted key; kept on this computer.")
    key_ref: str | None = Field(None, description="Or where the key is now: env:NAME or file:/path.")
    models: dict[str, str] | None = Field(None, description="Its models, replacing the ones it has.")
    use: dict[str, str] = Field(default_factory=dict, description="Tiers to one of its models by short name.")
    fingerprint: str


class AiModelsAsk(BaseModel):
    """Ask a service for its models before the account is saved, with the key the person just pasted."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(description="The kind of account, from GET /api/ai/endpoints.")
    base_url: str | None = Field(None, description="Its address, for a kind whose address the person enters.")
    key: str | None = Field(None, description="A pasted key; used for this request only and never kept.")
    key_ref: str | None = Field(None, description="Or where the key is: env:NAME or file:/path.")


class AiModelView(BaseModel):
    id: str
    context_tokens: int | None = None
    input_per_million: float | None = Field(None, description="Its price per million tokens read, when listed.")
    output_per_million: float | None = Field(None, description="Its price per million tokens written, when listed.")


class AiModelsView(BaseModel):
    models: list[AiModelView] = Field(default_factory=list)
    problem: str | None = Field(None, description="Why the list couldn't be read, in plain words.")


class LocalServerView(BaseModel):
    """A model server found running on this computer."""

    endpoint: str = Field(description="Its kind of account, from GET /api/ai/endpoints.")
    name: str
    models: list[str]


class AiAccountAdd(BaseModel):
    """A new AI account from the Add account screen. A pasted key is kept on this computer, never in ai.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The account's short name in ai.yaml: lowercase letters, digits and dashes.")
    adapter: str = Field(description="The adapter of the kind of account chosen, from GET /api/ai/endpoints.")
    endpoint: str | None = Field(
        None, description="The kind of account chosen; its starting provider settings are added to the account's."
    )
    base_url: str | None = None
    key: str | None = Field(None, description="A key pasted on the screen; kept in this computer's private folder.")
    key_ref: str | None = Field(None, description="Or a reference: env:NAME or file:/path.")
    models: dict[str, str] = Field(description="Short names for the account's models, to their ids.")
    allowed_data: list[Literal["open", "internal", "restricted"]] = Field(default_factory=lambda: ["open"])
    agent: dict[str, Any] | None = Field(None, description="For a command-line agent: its `agent` settings.")
    use_for: list[str] = Field(
        default_factory=list, description='Tiers this account\'s first model should do ("routine", "deep").'
    )
    use: dict[str, str] = Field(
        default_factory=dict,
        description="Tiers to one of this account's models by its short name, such as an everyday model for "
        "routine and a stronger one for deep; it wins over use_for for the tiers it names.",
    )
    fingerprint: str


class AiTestResult(BaseModel):
    """One kind of work's account, tested: whether it answered, in plain words."""

    tier: str = Field(description='The kind of work: "routine" (everyday) or "deep" (harder), or another tier.')
    account: str = Field(description="The account's short name, as the person named it.")
    main: bool = Field(description="It is the tier's main account; otherwise a fallback.")
    ok: bool
    detail: str = Field(description='"answered", or what went wrong in plain words.')


# ---- asking the assistant --------------------------------------------------------------------------------------------


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class CiteView(BaseModel):
    quote: str
    source: str | None = None


class AnswerView(BaseModel):
    text: str
    cites: list[CiteView]


class SettingProposalView(BaseModel):
    id: str
    version: int
    key: str
    value: Any = None
    why: str
    status: Literal["open", "applied", "dismissed"]


class ReportView(BaseModel):
    id: str
    version: int
    title: str
    text: str
    status: Literal["draft", "sent", "dismissed"]


class AskView(BaseModel):
    """One question the PM asked and what came of it."""

    id: str
    question: str
    state: Literal["queued", "running", "review", "done", "needs_you", "failed"]
    waiting: str | None = None
    created_at: str
    changeset: str | None = None
    answer: AnswerView | None = None
    proposals: list[SettingProposalView] = Field(default_factory=list)
    reports: list[ReportView] = Field(default_factory=list)


class ProposalApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    read_version: int


class WatchRunView(BaseModel):
    started_at: str
    outcome: Literal["ok", "baseline", "failed", "offline", "throttled"]
    retry_at: str | None = Field(None, description="For a throttled read: not read again before this time.")
    error_kind: str | None = None
    error: str | None = None
    new: int = 0
    changed: int = 0
    removed: int = 0


class WatchSourceView(BaseModel):
    """One place the assistant keeps reading, from watch.yaml, with its last read."""

    id: str
    label: str
    connector: str
    connector_label: str = Field(description="What kind of place it is, in words; empty when no connector runs it.")
    enabled: bool
    every_minutes: int
    items: int = Field(description="Items it held at the last read.")
    last: WatchRunView | None = None
    failures: int = Field(0, description="Failed reads in a row.")
    problem: str | None = Field(None, description="Why it can't be read, and what to do, while it fails.")


class AutoClosedView(BaseModel):
    """A watched change a triage rule closed before the assistant read it."""

    id: str
    version: int
    title: str
    source: str = Field(description="The watched source's label.")
    change: Literal["new", "changed", "removed"]
    rule: str
    reason: str
    created_at: str


class FingerprintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str


class SignInView(BaseModel):
    name: str
    label: str = Field(description="What to call the service's sign-in on screen.")
    status: Literal["signed_in", "expired", "signed_out"]
    ready: bool = Field(description="The add-on's app registration (its client id) is set, so signing in can start.")
    callback: str = Field(description="The address the service's app registration must allow to send people back to.")
    allows: list[str] = Field(default_factory=list, description="What the person is asked to allow, in plain words.")
    account: str | None = Field(None, description="The signed-in account, when the add-on can name it.")
    missing: list[str] = Field(
        default_factory=list, description="Scopes asked for that the person didn't allow, while signed in."
    )


class SignInStarted(BaseModel):
    url: str = Field(description="The service's sign-in page, to open in the person's browser.")


class PackAdds(BaseModel):
    item_types: list[str] = Field(description="The kinds of items it adds, in words.")
    screens: int
    today: int = Field(description="How many kinds of lines it puts on Today.")
    ai_work: int = Field(description="How many kinds of AI work it adds.")
    actions: int
    setup_steps: int
    sources: int = Field(description="Places it can keep reading.")


class PackReaches(BaseModel):
    sign_ins: list[str] = Field(description="Services it signs in to as you, in words.")
    hosts: list[str] = Field(description="Internet hosts it may reach.")
    programs: list[str] = Field(description="Programs it runs on this computer.")
    keys: int = Field(description="How many keys or passwords you provide it.")


class PackSummary(BaseModel):
    adds: PackAdds
    reaches: PackReaches
    keeps: Literal["open", "internal", "restricted"] = Field(description="The most private material it holds.")


class PackCost(BaseModel):
    label: str
    tokens: int = Field(description="The job's typical size, input and answer together.")
    usd: float | None = Field(description="Its price on this workspace's accounts, when the prices are known.")
    account: bool = Field(description="False when no AI account is set up for this kind of work.")


class PackPrice(BaseModel):
    model: Literal["free", "one_time", "subscription", "see_publisher"]
    amount: float | None
    currency: str
    period: Literal["month", "year"] | None
    note: str


class PackView(BaseModel):
    id: str
    name: str
    summary: str
    publisher: str
    maintainers: bool = Field(description="Made by the app's maintainers rather than a third party.")
    updated: str
    version: str
    price: PackPrice
    homepage: str | None
    homepage_domain: str | None = Field(description="The homepage's real domain, to show beside the link.")
    install: str = Field(description="How to install it, as the feed says (a command or a short instruction).")
    demo: bool = Field(description="It can be tried in the demo.")
    compatible: bool | None = Field(description="Works with this version of the app; None when the feed doesn't say.")
    installed_version: str | None
    enabled: bool
    what: PackSummary
    costs: list[PackCost]
    feed: str = Field(description="The domain of the feed that lists it.")


class InstalledPackView(BaseModel):
    name: str
    version: str | None
    description: str
    enabled: bool
    state: str
    reason: str | None
    what: PackSummary


class PackFeedView(BaseModel):
    domain: str
    error: str | None
    notes: list[str]
    read_at: str | None


class PacksView(BaseModel):
    enabled: bool = Field(description="The catalog is on in this workspace.")
    feeds: list[PackFeedView]
    available: list[PackView]
    installed: list[InstalledPackView]


class MeView(BaseModel):
    """The person the app is for: their own person record, the one place their name is kept."""

    person: str | None
    full_name: str


class MeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=1, max_length=200)
