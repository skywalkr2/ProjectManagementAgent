"""Response and request models for the API. The web client's types are generated from these through OpenAPI, so a
changed field here fails the web build instead of breaking the UI at run time.

Models carry data, not wording: the UI words everything through its wording sheet.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    group: str | None = None
    status: str | None = None
    phase: str | None = None
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
    required: bool = False
    editable: bool = Field(True, description="The person can change it with a field edit (not the id or stage).")


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
    task: str
    label: str
    about: RecordReference | None = None
    note: str = ""


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
    restarts: bool = Field(description="The app restarts in a moment to use the new settings.")


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


class SetupView(BaseModel):
    steps: list[SetupStepView]
    finished: bool = Field(description="Every step is done or skipped.")
    local: bool = Field(description="The app runs on the person's own computer, so folders can be picked here.")


class TemplateView(BaseModel):
    id: str
    name: str
    description: str


class TemplateApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str


class TemplateApplied(BaseModel):
    plugins: list[str]
    restarts: bool


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
    name: str
    adapter: str = Field(description="The adapter to send when adding an account of this kind.")
    base_url: str
    note: str = ""


class AiAccountAdd(BaseModel):
    """A new AI account from the Add account screen. A pasted key is kept on this computer, never in ai.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The account's short name in ai.yaml: lowercase letters, digits and dashes.")
    adapter: str = Field(description="The adapter of the kind of account chosen, from GET /api/ai/endpoints.")
    base_url: str | None = None
    key: str | None = Field(None, description="A key pasted on the screen; kept in this computer's private folder.")
    key_ref: str | None = Field(None, description="Or a reference: env:NAME or file:/path.")
    models: dict[str, str] = Field(description="Short names for the account's models, to their ids.")
    allowed_data: list[Literal["open", "internal", "restricted"]] = Field(default_factory=lambda: ["open"])
    agent: dict[str, Any] | None = Field(None, description="For a command-line agent: its `agent` settings.")
    use_for: list[str] = Field(
        default_factory=list, description='Tiers this account\'s first model should do ("routine", "deep").'
    )
    fingerprint: str


class AiTestResult(BaseModel):
    tier: str
    account: str
    main: bool
    ok: bool
    detail: str


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
    outcome: Literal["ok", "baseline", "failed", "offline"]
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
