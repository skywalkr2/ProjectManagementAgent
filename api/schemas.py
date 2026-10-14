"""Response and request models for the API. The web client's types are generated from these through OpenAPI, so a
changed field here fails the web build instead of breaking the UI at run time.

Models carry data, not wording: the UI words everything through its wording sheet.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.screen_text import ScreenText

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
    undo_first: bool = Field(True, description="Undo what the assistant did before it tries again (the default).")


class UndoChoice(BaseModel):
    ops: list[int] | None = Field(None, description="Indices of the items to undo; all of them when left out.")


class PersonChoice(BaseModel):
    person: str | None = None


class SentText(BaseModel):
    text: str | None = Field(None, description="The message as the PM sent it, to notice edits.")


class Answer(BaseModel):
    text: str | None = Field(
        None,
        description="A written answer; with a person chosen, a note that goes with the choice (it is read).",
    )
    person: str | None = Field(None, description="The person chosen, for questions that ask who.")


class Reply(BaseModel):
    text: str = Field(description="The reply as received, pasted by the PM.")


class ActionState(BaseModel):
    status: Literal["open", "done"]
    note: str = Field(
        "", description="Anything the person wrote with the change, in their own words; the assistant reads it."
    )


class NoteIn(BaseModel):
    note: str = Field(
        "",
        description="Anything the person wrote with the change; the assistant reads it. On a button that relays "
        "another person it is what they report about that person.",
    )


class OwnerPick(BaseModel):
    person: str | None = None
    note: str = Field(
        "", description="Anything the person wrote with the choice, in their own words; the assistant reads it."
    )


class Unfollow(BaseModel):
    on: str = Field(description="The day the chase was recorded, from the response that recorded it.")
    previous_told: str | None = Field(None, description="The day they were told before the chase, if any.")


class HoldIn(BaseModel):
    waiting_for: str = Field(min_length=1, description="What the action waits for, in plain words.")


class HoldState(BaseModel):
    waiting_for: str = Field(description="What the action waits for.")
    since: str = Field(description="The day it was put on hold (a date).")


class HoldRestore(BaseModel):
    hold: HoldState | None = Field(
        None, description="What the action's hold was before the change that is being undone; none for off hold."
    )


# ---- responses -------------------------------------------------------------------------------------------------------


class Ok(BaseModel):
    ok: str


class Noted(BaseModel):
    ok: str
    request: str | None = Field(
        None, description="The work queued for the assistant from the note that came with the change, if there was one."
    )


class FollowedUp(BaseModel):
    on: str = Field(description="The day the chase was recorded (a date).")
    previous_told: str | None = Field(None, description="The day they were told before it, for undoing the chase.")
    request: str | None = Field(
        None, description="The work queued for the assistant from the note that came with the chase, if there was one."
    )


class HoldChanged(BaseModel):
    ok: str
    previous: HoldState | None = Field(
        None, description="What the action's hold was before the change, for undoing it (none: it was not on hold)."
    )


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
    last_error: ScreenText | None


class RequestCounts(BaseModel):
    queued: int
    running: int
    review: int
    needs_you: int


class NetworkWait(BaseModel):
    """Work waiting for the network connection to come back."""

    count: int = Field(description="How many requests wait for the network.")
    since: str = Field(description="When the oldest of them first found no network, an ISO time.")


class AiState(BaseModel):
    """Whether the assistant can do its work: set up, tested, and answering."""

    state: Literal["ok", "untested", "failing", "not_set_up", "stand_in"]
    detail: ScreenText | None = Field(None, description="The provider's own reason when there is one, shortened.")


class SpendStatus(BaseModel):
    """What the assistant's work has cost today and this month (UTC), against the configured limits."""

    today_usd: float
    month_usd: float
    per_day_usd: float
    per_month_usd: float
    warn: bool = Field(description="Either total has reached the configured share of its limit.")
    warn_today: bool = Field(description="Today's total has reached that share of the daily limit.")
    warn_month: bool = Field(description="This month's total has reached that share of the monthly limit.")


class AssistantAccountRuns(BaseModel):
    account: str = Field(description="The account's name in the settings.")
    count: int = Field(description="Calls made to it today that reached it.")
    failed: int = Field(description="Of those, the ones that didn't end in an answer that was used.")


class AssistantChain(BaseModel):
    tier: str
    accounts: list[str] = Field(description="The accounts the tier tries, in order, by their names in the settings.")


class AssistantPaused(BaseModel):
    account: str
    until: datetime = Field(description="When its usage limit resets, on the person's own clock (their time zone).")


class AssistantStatus(BaseModel):
    """Whether the assistant is alive, for the header's status line. Times are on the person's own clock."""

    last_run_at: datetime | None = Field(
        None, description="When the assistant last called an account; none before the first."
    )
    last_run_failed: bool = Field(description="That last call ended in an error and its account isn't paused.")
    runs_today: list[AssistantAccountRuns] = Field(description="Today's calls by account, in the person's day.")
    queued: int = Field(
        description="Requests waiting for the assistant now, not counting ones that wait for the person."
    )
    oldest_queued_since: datetime | None = Field(None, description="When the oldest of them was made.")
    chains: list[AssistantChain] = Field(description="For each tier with an account, the order its accounts are tried.")
    paused: list[AssistantPaused] = Field(description="Accounts waiting for a usage limit to reset.")


class Status(BaseModel):
    backup: BackupStatus
    ai: AiState
    assistant: AssistantStatus
    spend: SpendStatus
    requests: RequestCounts
    network_wait: NetworkWait | None = Field(
        None,
        description="Set while any request waits for the network connection, which it does with no tries used up.",
    )
    version: int
    restart_needed: ScreenText | None = Field(
        None, description="Why new work waits until the cockpit restarts, if it does."
    )
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
    reason: ScreenText | None
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


class ItemTitle(BaseModel):
    """An item's title in parts (design 7.14); the screen puts them into words: "{kind} from {person} · {topic}"."""

    kind: Literal["email", "calendar", "change", "note", "pasted", "task"] = Field(
        description="email, calendar or change (another watched item); note: the person's own words; pasted: "
        "someone else's words handed in; task: work the app started."
    )
    person: str | None = Field(None, description="The id of who it came from, when known.")
    person_name: str | None = Field(None, description="That person's full name.")
    sender: str | None = Field(None, description="Who it came from as written, when not a known person.")
    topic: str = Field("", description="A few words on what it is about; may be empty.")


class StopCauseView(BaseModel):
    """Why a stopped request waits, when the screen has one action that clears it."""

    kind: Literal["data_level", "no_person"] = Field(
        description="data_level: no AI account may see the material, so `account` can be allowed to "
        "(POST /api/requests/{id}/allow-data). no_person: no one is set as the person the app is for; the setup "
        "step 'workspace' names them, and the request runs again by itself once they are."
    )
    level: Literal["open", "internal", "restricted"] | None = Field(
        None, description="For data_level: the data level of the material."
    )
    account: str | None = Field(
        None,
        description="For data_level: the short name of the account the tier would use first, which the action lets "
        "see that level.",
    )


class ChangeItem(BaseModel):
    id: str
    version: int
    dismissed: bool
    state: Literal["queued", "running", "review", "done", "needs_you", "failed"]
    waiting: ScreenText | None
    created_at: str
    note: str | None
    source: str | None
    source_title: str | None
    approval: Literal["required", "granted"] | None = Field(
        None, description="Whether the request waits for the person's go or has had it."
    )
    stage_task: bool = Field(False, description="The request was started by a stage, so the stage views show its go.")
    first_go: bool = Field(
        False, description="The request waits for the person's first go in the workspace, which starts every such run."
    )
    estimate_usd: float | None = Field(None, description="What the run was estimated to cost when it asked for a go.")
    refused: bool = Field(
        False, description="The account declined it under its own policy; it can be sent to another account."
    )
    cause: StopCauseView | None = Field(None, description="For a stopped request: the cause an action can clear.")
    follows: str | None = Field(None, description="The change (changeset id) this work followed from, if any.")
    follows_summary: str | None = Field(None, description="That change's one-line summary, for the row.")
    changeset: ChangesetView | None
    title: ItemTitle | None = Field(None, description="The item's title, by the title rule.")
    mail_item: str | None = Field(
        None, description="For work on a mail message the app is holding: its id, for 'Set aside' on the row."
    )


class UndoReport(BaseModel):
    restored: list[Any]
    skipped: list[Any]


class Link(BaseModel):
    label: str
    url: str


class Origin(BaseModel):
    """Where an action, a question or a decision came from, for its "Where it came from" link. `link`: the original
    page (`url`, shown with its real domain). `source`: the saved text of the input (`source`, read from
    GET /api/sources/{id}). `change`: the change that made the item (`changeset`) and the request behind it
    (`request`), shown in What changed. An item with none of these has no origin (null)."""

    kind: Literal["link", "source", "change"]
    url: str | None = Field(None, description="The page's address, for a link.")
    source: str | None = Field(None, description="The input's id, for a link or a source.")
    changeset: str | None = Field(None, description="The change that made the item, for a change.")
    request: str | None = Field(None, description="The request behind that change, for a change.")


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
    chase_due: bool = Field(
        False, description="Whether it has gone unanswered as long as the follow-up rule says, so chasing is next."
    )
    about: str | None
    options: list[Option]
    origin: Origin | None = Field(None, description="Where the question came from, for its link.")


class FollowupAction(BaseModel):
    id: str
    text: str
    due: str | None
    project_name: str
    told: str | None
    told_days: int | None
    followed_up: str | None = Field(None, description="The day the person was last chased about it (a date).")
    on_hold: str | None = Field(
        None, description="What the action waits for while it is on hold; an action on hold is never chased."
    )
    chase_due: bool = Field(
        False,
        description="Whether the follow-up rule says chasing is the next step: its due date is near or past, "
        "or it has waited long enough with no word, and it is not on hold.",
    )
    origin: Origin | None = Field(None, description="Where the action came from, for its link.")


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
    first_name: str | None = Field(None, description="The name a greeting to them uses; empty means the first word.")
    role: str | None
    org: str | None = Field(None, description="The id of the organization they work for.")
    org_name: str | None = Field(None, description="That organization's name, for showing.")
    aliases: list[str] = []
    status: Literal["active", "left"] = "active"
    is_pm: bool = False
    track_only: bool = False
    open_items: int = Field(0, description="Open actions and questions with them.")
    last_contact: str | None = Field(None, description="When something was last sent or told to them (a date).")


class PersonIn(BaseModel):
    full_name: str = Field(min_length=1)
    first_name: str | None = Field(
        None, description="The name a greeting uses; empty means the first word of the name."
    )
    role: str | None = None
    org: str | None = Field(None, description="An organization's id, from GET /api/organizations.")
    aliases: list[str] = []


class PersonPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1)
    first_name: str | None = Field(None, description="The name a greeting uses; null clears it.")
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
    open_actions: int = 0
    open_questions: int = 0
    last_change: str | None = Field(None, description="When the project record last changed.")


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
    last_error: ScreenText | None


class RuntimeConfig(BaseModel):
    base_path: str
    api_base: str
    assistant_name: str
    assistant_named: bool = Field(
        True, description="The assistant has a name of its own; false while it still has the default name."
    )
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
    brand_color: str | None = Field(None, description="The accent color as #rrggbb; none uses the app's own.")
    logo: bool = Field(False, description="The workspace has a logo, served at the API's brand/logo address.")
    theme: Literal["system", "light", "dark"] = Field("system", description="The workspace's default theme.")
    density: Literal["comfortable", "compact"] = Field("comfortable", description="The workspace's default density.")


class PluginStatusView(BaseModel):
    name: str
    state: str
    version: str | None = None
    reason: ScreenText | None = None
    tools: dict[str, ScreenText] = Field(default_factory=dict, description="Each declared program and what was found.")
    notes: list[ScreenText] = Field(default_factory=list, description="What the person should know, though it loaded.")


class RecordReference(BaseModel):
    kind: str
    id: str


class StageLabel(BaseModel):
    id: str
    label: str


class StageCheckView(BaseModel):
    id: str
    passed: bool
    reason: ScreenText


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


class RecordRefName(BaseModel):
    kind: str
    id: str
    name: str


class RecordDetail(BaseModel):
    """One field of a record, with any references in it resolved to names."""

    field: str
    value: Any
    type: Literal["date", "number", "bool", "enum", "list", "map", "text"]
    refs: list[RecordRefName] = Field(default_factory=list)


class OpenAction(BaseModel):
    id: str
    text: str
    due: str | None = None
    owners: list[str] = Field(default_factory=list, description="The owners, written in the workspace's owner format.")
    project: str | None = None
    project_name: str | None = None
    origin: Origin | None = Field(None, description="Where the action came from, for its link.")


class OpenQuestion(BaseModel):
    id: str
    title: str
    to: str | None = None
    to_name: str | None = None
    status: str | None = None
    kind: str | None = None
    origin: Origin | None = Field(None, description="Where the question came from, for its link.")


class ActivityEntry(BaseModel):
    """One change to the record, or to something open with it."""

    at: str
    kind: str
    id: str
    name: str
    op: str
    field: str | None = None
    actor: str
    by_assistant: bool


class RecordPageView(BaseModel):
    """A record's page (design 7.14): its name, details in declared order with names resolved, what is open with
    it, and its activity, newest first."""

    kind: str
    id: str
    version: int
    name: str
    details: list[RecordDetail]
    open_actions: list[OpenAction]
    open_questions: list[OpenQuestion]
    activity: list[ActivityEntry]


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
    waiting: ScreenText | None
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
    data_level: Literal["open", "internal", "restricted"] = Field(
        "internal", description="How sensitive its content is: it goes only to AI accounts allowed this level."
    )


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
    description: ScreenText = ""
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
    origin: Origin | None = Field(
        None, description="For an action or a question: where it came from, for its link. Null for any other record."
    )


class OutsideEditView(BaseModel):
    path: str = Field(description="The file in the synced folder.")
    proposal: str | None = Field(None, description="The changeset it became, to review.")
    version: str | None = Field(None, description="The text version it became, to review.")
    problem: ScreenText | None = Field(None, description="Why it couldn't be read back.")


class SyncView(BaseModel):
    """The synced folder's state."""

    folder: str = Field(description="The configured folder; empty when off.")
    problem: ScreenText | None = Field(description="Why it can't be written now, if it can't.")
    stopped: bool = Field(description="Another computer opened the workspace; this copy stopped writing.")
    changed_outside: list[str]
    removed_outside: list[str]
    rebuilt: list[str]
    outside_edits: list[OutsideEditView]
    conflict_copies: list[str]
    shared: bool = Field(description="Anyone else can change the folder, so outside edits are content to check.")
    handover: Literal["diverged", "chosen", "elsewhere"] | None = Field(
        None,
        description="Why the folder isn't being written, when the person has something to settle "
        "(GET /api/sync/handover).",
    )


class HandoverSideView(BaseModel):
    """What one side has that the other lacks."""

    computer: str = Field(description="The computer that made the changes; empty when it isn't known.")
    changes: int = Field(description="How many changes the other side doesn't have.")
    latest: datetime | None = Field(None, description="When the latest of them was made, on the person's own clock.")


class HandoverView(BaseModel):
    """Why the synced folder isn't being used and what the person can do about it (design 5.0). `diverged`: this
    computer and the folder each changed while they couldn't sync; the person chooses which copy to keep, and the
    choice is carried out at the next start (`chosen` once noted). `elsewhere`: another computer opened the workspace
    (`computer`, `last_seen`, `minutes_left` until it can be opened here without it closing first); there is nothing to
    choose. `clear`: nothing to settle."""

    state: Literal["clear", "diverged", "chosen", "elsewhere"]
    here: HandoverSideView | None = Field(None, description="This computer's side (diverged, chosen).")
    folder: HandoverSideView | None = Field(None, description="The synced folder's side (diverged, chosen).")
    computer: str = Field("", description="The other computer (elsewhere).")
    last_seen: datetime | None = Field(None, description="When the other computer was last seen (elsewhere).")
    minutes_left: int = Field(0, description="Minutes until the workspace can be opened here (elsewhere).")
    chosen: Literal["here", "folder"] | None = Field(None, description="The copy the person chose to keep.")


class HandoverChoice(BaseModel):
    which: Literal["here", "folder"] = Field(description="Keep this computer's copy or the synced folder's.")


class AgendaItemView(BaseModel):
    """An event from a watched calendar, or an entry in the app's own calendar, on today or the next configured days."""

    snapshot: str = Field(description="The item's id: the snapshot of a watched event, or the id of an own entry.")
    source: str = Field(
        description="The watched source's id; its label is in GET /api/sources. For an own entry, the source it came "
        "from, or empty."
    )
    title: str
    start: str = Field(description="ISO 8601: a date-time with its offset, or a date for an all-day event.")
    end: str | None = None
    all_day: bool
    where: str | None = None
    link: str | None = Field(None, description="Where to open it; untrusted, so show its real domain.")
    cancelled: bool = Field(description="The organizer called it off.")
    days: list[date] = Field(description="The days it falls on, in the person's time zone.")
    own: bool = Field(
        False,
        description="An entry in the app's own calendar (recorded from what came in), not an event read from a "
        "connected calendar. Its end is the last day or moment, included.",
    )


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
    overdue: bool = Field(description="Whether it is past its due date; never true while it is on hold.")
    on_hold: str | None = Field(None, description="What it waits for while it is on hold; its due date is kept.")
    origin: Origin | None = Field(None, description="Where the action came from, for its link.")


class QueueLineView(BaseModel):
    """One line of Today's queue (design 7.7), in rank order. The screen words it from `kind` and the counts. `restart`
    is work held until the person restarts the app (`count` waiting; the screen offers Restart now, which is
    POST /api/restart); `paused` is an AI account waiting for its usage limit to reset (`account`, `until`, `count`
    waiting), after which the work runs again by itself; `offline` is work that has waited for the network longer than
    the configured time (`count` waiting, `waiting_since`), which runs again by itself once the network is back."""

    key: str = Field(description="Stable while the thing it stands for waits.")
    group: Literal["decide", "risk", "review", "send"]
    kind: Literal[
        "decision",
        "question",
        "who_is",
        "owner",
        "held",
        "go",
        "first_go",
        "refused",
        "restart",
        "handover",
        "failed",
        "paused",
        "offline",
        "overdue",
        "review",
        "send",
        "nudge",
    ]
    count: int
    text: str | None = Field(None, description="The decision, question, name or held item in one line.")
    title: ItemTitle | None = Field(None, description="The input the line is about.")
    person: str | None = Field(None, description="Whom the line is about (send, nudge).")
    person_name: str | None = None
    project: str | None = None
    project_name: str | None = None
    due: date | None = None
    waiting_days: int | None = None
    waiting: ScreenText | None = Field(None, description="Why the work stopped, in plain words.")
    request: str | None = None
    changeset: str | None = None
    question: str | None = None
    op: int | None = Field(None, description="The held item's index in its changeset.")
    actions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    outcome: dict[str, int] = Field(
        default_factory=dict,
        description="What the assistant did, counted: actions_added, actions_closed, questions, notes, recorded, "
        "people, projects, drafts, other; and held, refused.",
    )
    untrusted: bool = Field(False, description="Built from outside content.")
    estimate_usd: float | None = Field(
        None, description="The estimated cost of everything the line starts (first_go), when any has a price."
    )
    unpriced: int = Field(0, description="How many of the things the line starts have no price (first_go).")
    account: str | None = Field(None, description="The AI account waiting for its limit to reset (paused).")
    until: datetime | None = Field(
        None,
        description="When the account's limit resets and the work waiting on it runs again by itself (paused), on the "
        "person's own clock (their time zone).",
    )
    waiting_since: datetime | None = Field(
        None,
        description="When the oldest request waiting for the network began waiting (offline), on the person's own "
        "clock (their time zone).",
    )
    state: Literal["diverged", "chosen", "elsewhere"] | None = Field(
        None,
        description="For a handover line: diverged (this computer and the synced folder each changed; the person "
        "chooses which copy to keep), chosen (the choice waits for the restart) or elsewhere (another computer opened "
        "the workspace, so this copy stopped writing to the folder). `text` is the other computer's name.",
    )


class FirstGoStarted(BaseModel):
    started: int = Field(description="How many runs the first go started.")


class FirstGoSorting(BaseModel):
    """The sorting run the first go also makes, for mail handed in unsorted while the go was pending."""

    runs: int = Field(description="How many sorting runs the go makes; none when no mail waits for sorting.")
    estimate_usd: float | None = Field(
        None, description="What the runs that have a price cost together; none when none has one."
    )
    unpriced: int = Field(0, description="How many of the runs have no price (they use the plan's allowance).")


class InboxView(BaseModel):
    items: list[ArrivedView]
    left_out: int = Field(description="Messages in the same hours that a triage rule closed (newsletters, say).")
    set_aside: int = Field(0, description="Messages in the same hours that are in the Set aside folder.")


class InboxCheckView(InboxView):
    """Came in after reading every source now, with what the read found."""

    new_items: int = Field(
        description="Everything the sources handed in during this read (new, changed or gone), wherever it shows: in "
        "Came in or only in What changed."
    )
    sources_read: int = Field(description="How many sources were read.")
    sources_failed: int = Field(description="Sources that could not be read this time; their problem shows on Sources.")
    sources_busy: int = Field(description="Sources that were already being read, so this read left them alone.")


class TodayLineView(BaseModel):
    """A line a plugin adds to Today."""

    plugin: str
    id: str
    text: str
    about: RecordReference | None = None
    action: str | None = Field(None, description="The one thing to do from it: a person action or a kind of work.")
    action_is: Literal["action", "task", "core"] | None = Field(
        None,
        description="action: run it as a person action (/plugin-actions); task: start it as AI work; core: one of the "
        "core's own (open, review, go, answer, move-stage) on `about`.",
    )
    why: ScreenText = ""
    until: str | None = None


class PanelView(BaseModel):
    """A plugin's screen, described as data (design 7.2)."""

    name: str
    title: str
    tab: str
    kind: str
    view: str = Field(description='"list", "table" or "board" for records; "document" for a composed page.')
    columns: list[str]
    primary_action: str | None
    row_actions: list[str]
    new_action: str | None = Field(None, description="A person action on the workspace that adds one, shown above.")


class DocumentInline(BaseModel):
    """A run of text in a document: plain, strong, emphasis or code, or a link to a record or to a page outside."""

    text: str
    strong: bool = False
    em: bool = False
    code: bool = False
    record: RecordReference | None = Field(None, description="A record the link opens.")
    url: str | None = Field(None, description="A page outside the app; show `domain` beside it.")
    domain: str | None = None


class DocumentBlock(BaseModel):
    """One block of a document panel, drawn by the screens as their own elements (never HTML)."""

    type: Literal["heading", "paragraph", "list", "table", "rule"]
    level: int | None = Field(None, description="A heading's level, 1 to 3.")
    inlines: list[DocumentInline] = Field(default_factory=list, description="A heading's or paragraph's text.")
    ordered: bool = False
    items: list[list[DocumentInline]] = Field(default_factory=list, description="A list's items.")
    header: list[list[DocumentInline]] = Field(default_factory=list, description="A table's header cells.")
    rows: list[list[list[DocumentInline]]] = Field(default_factory=list, description="A table's rows of cells.")


class DocumentView(BaseModel):
    """A document panel as it reads now; `blocks` is None when the add-on has nothing to show yet."""

    blocks: list[DocumentBlock] | None


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
    last_error: ScreenText | None


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
    refused: ScreenText | None = Field(None, description="Why this would be refused if applied now; it starts dropped.")


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
    notes: list[ScreenText]
    requests: list[ActionRequestView] = Field(
        default_factory=list, description="AI work queued when it is applied, each waiting for the person's go."
    )
    problems: list[ScreenText] = Field(
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
    description: ScreenText
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


class DataLevelAllowed(BaseModel):
    request: str = Field(description="The request, queued again.")
    account: str = Field(description="The account that was let see the level.")
    level: Literal["open", "internal", "restricted"]
    saved: SettingsSaved = Field(description="What changed in the settings, for the read-back and Undo.")


class SetupStepView(BaseModel):
    id: str = Field(
        description="A core step (workspace, ai, mail, backup, people, template, first_note, addons) or a plugin's."
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
    group: Literal["you", "ai", "mail", "backup", "people", "done"] = Field(
        "done",
        description="The walkthrough screen the step is on. A step on the last screen is an optional extra.",
    )
    counted: bool = Field(False, description="The step counts toward finishing the setup.")


WalkthroughScreen = Literal["you", "ai", "mail", "backup", "people", "done"]


class WalkthroughView(BaseModel):
    """Where the new-start walkthrough stands, kept on this computer so it resumes after a restart."""

    open: bool = Field(description="It should open by itself now: not closed, not finished, setup still to do.")
    step: WalkthroughScreen = Field(description="The screen to open at.")
    closed: bool = Field(description="The person chose Finish later; it stays closed until they open it again.")
    finished: bool = Field(description="The person pressed the last button.")


class WalkthroughIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: WalkthroughScreen | None = None
    closed: bool | None = None
    finished: bool | None = None


class SetupView(BaseModel):
    steps: list[SetupStepView]
    finished: bool = Field(description="Every step that counts is done or skipped; the optional extras never count.")
    local: bool = Field(description="The app runs on the person's own computer, so folders can be picked here.")
    walkthrough: WalkthroughView


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
    problem: ScreenText | None = None
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
    key_state: Literal["saved", "missing", "none"] = Field(
        "none",
        description="saved: its key is there to use. missing: it refers to a key that isn't there (an environment "
        "variable not set, a file not found). none: no key is set.",
    )
    key_where: ScreenText | None = Field(
        None, description="Where a missing key is looked for, in plain words; never a key."
    )


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
    problem: ScreenText | None = Field(None, description="Why the list couldn't be read, in plain words.")


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
    detail: ScreenText = Field(description='"answered", or what went wrong in plain words.')


# ---- asking the assistant --------------------------------------------------------------------------------------------


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class CiteView(BaseModel):
    quote: str = Field(description="The exact words from the cited material; the input's own text, never checked.")
    source: str | None = None


class AnswerView(BaseModel):
    text: ScreenText
    cites: list[CiteView]


class SettingProposalView(BaseModel):
    id: str
    version: int
    key: str
    value: Any = None
    why: ScreenText
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
    waiting: ScreenText | None = None
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
    error: ScreenText | None = None
    new: int = 0
    changed: int = 0
    removed: int = 0


class WatchSourceView(BaseModel):
    """One place the assistant keeps reading, from watch.yaml, with its last read."""

    id: str
    label: str
    connector: str
    connector_label: str = Field(description="What kind of place it is, in words; empty when no connector runs it.")
    reads: list[Literal["mail", "calendar"]] = Field(
        default_factory=list, description="Whether the place is mail, a calendar, or neither (empty)."
    )
    enabled: bool
    every_minutes: int
    items: int = Field(description="Items it held at the last read.")
    last: WatchRunView | None = None
    read_at: str | None = Field(
        None, description="When it was last actually read; a try that found no network or failed doesn't count."
    )
    failures: int = Field(0, description="Failed reads in a row.")
    problem: ScreenText | None = Field(None, description="Why it can't be read, and what to do, while it fails.")


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


class SetAsideView(BaseModel):
    """A mail item in the Set aside folder: left with the person, never read by the assistant."""

    id: str = Field(description="The mail item's snapshot.")
    version: int
    section: Literal["personal", "sales"]
    title: str
    sender: str | None = None
    source: str = Field(description="The watched source's label.")
    received: str | None = Field(None, description="ISO 8601 date-time with its offset, as the service gave it.")
    reason: str = Field(description="Why it was set aside, in plain words.")
    address: str = Field("", description="The sender's address, when the mail holds one.")
    domain: str | None = Field(
        None,
        description="The sender's domain, when a rule for the whole domain may be offered: empty when the mail has no "
        "address or the domain is a public mail domain.",
    )


class SetAsideFolder(BaseModel):
    items: list[SetAsideView]
    deleted: int = Field(0, description="Messages whose content the person had deleted from the app after confirming.")


class SetAsideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Literal["personal", "sales"]


class SetAsideDone(BaseModel):
    """A mail item set aside by hand, with its sender so the screen can offer a sorting rule."""

    id: str
    version: int
    section: Literal["personal", "sales"]
    address: str = Field("", description="The sender's address, when the mail holds one.")
    domain: str | None = Field(
        None,
        description="The sender's domain, when a rule for the whole domain may be offered: empty when the mail has no "
        "address or the domain is a public mail domain.",
    )


class SortingRuleIn(BaseModel):
    """Always set aside mail from these senders and domains in a section, or never set it aside (work)."""

    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    choice: Literal["personal", "sales", "never"]
    senders: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    ids: list[str] = Field(min_length=1)


class DomainOffer(BaseModel):
    domain: str
    senders: int = Field(description="How many of the confirmed senders are on it.")
    section: Literal["personal", "sales"]


class ConfirmDone(BaseModel):
    saved: SettingsSaved
    confirmed: int = Field(description="How many messages were confirmed.")
    senders: list[str] = Field(description="The distinct sender addresses a rule was written for.")
    section: Literal["personal", "sales"] | None = Field(None, description="The section, when all were in one.")
    domain_offers: list[DomainOffer] = Field(
        description="Domains that three or more of the confirmed senders share, for an 'always' rule."
    )
    ids: list[str]


class UnconfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1)


class FingerprintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str


class SignInView(BaseModel):
    name: str
    label: str = Field(description="What to call the service's sign-in on screen.")
    status: Literal["signed_in", "expired", "signed_out"]
    ready: bool = Field(description="The add-on's app registration (its client id) is set, so signing in can start.")
    callback: str = Field(description="The address the service's app registration must allow to send people back to.")
    allows: list[ScreenText] = Field(
        default_factory=list, description="What the person is asked to allow, in plain words."
    )
    account: str | None = Field(None, description="The signed-in account, when the add-on can name it.")
    missing: list[str] = Field(
        default_factory=list, description="Scopes asked for that the person didn't allow, while signed in."
    )
    app: Literal["workspace", "pasted", "add-on", "none"] = Field(
        "none",
        description="Where its app registration comes from: the workspace's settings, values pasted here, the "
        "add-on's own, or nowhere yet.",
    )
    app_note: ScreenText | None = Field(
        None, description="What using the add-on's own registration means, while in use."
    )
    can_paste: bool = Field(False, description="The person can paste their own registration here (on this computer).")
    needs_secret: bool = Field(False, description="The service issues a client secret along with the client id.")
    set_aside: bool = Field(False, description="A pasted registration was set aside and can be brought back.")
    default_unusable: bool = Field(
        False,
        description="The add-on has its own registration, but it doesn't allow this app's address (served under "
        "another path, or hosted), so the person's own is needed.",
    )
    own_app_steps: list[SignInStep] = Field(
        default_factory=list, description="How to make one's own registration with the service."
    )
    not_reading: list[ScreenText] = Field(
        default_factory=list,
        description="While signed in: what the add-on reads by default (the inbox, the calendar) that nothing reads "
        "yet; POST /api/sign-ins/{name}/sources starts them.",
    )


class SignInStep(BaseModel):
    text: str
    link: str | None = Field(None, description="The service's page for this step (https).")


class SignInApp(BaseModel):
    """A person's own app registration for a sign-in, pasted on the Sign-ins row."""

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=500)
    client_secret: str | None = Field(None, max_length=500)


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
    reads: list[Literal["mail", "calendar"]] = Field(
        default_factory=list, description="Whether the places it can keep reading are mail, a calendar, or both."
    )


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
    installable: bool | None = Field(
        None, description="True when the app can install it from here (POST /api/packs/{id}/install)."
    )
    removable: bool = Field(False, description="The app installed it from this screen, so it can take it away again.")


class InstalledPackView(BaseModel):
    name: str
    version: str | None
    description: str
    enabled: bool
    state: str
    reason: ScreenText | None
    what: PackSummary
    removable: bool = Field(
        False, description="The app installed it from the Add-ons screen, so it can take it away again."
    )


class PackFeedView(BaseModel):
    domain: str
    error: ScreenText | None
    notes: list[ScreenText]
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


# ---- data-file forms -------------------------------------------------------------------------------------------------


class DataFormView(BaseModel):
    """A kind of data file an add-on lets the person edit through a form."""

    name: str
    plugin: str
    label: str
    description: str = ""
    pattern: str = Field("*.yaml", description="Which files are of this kind, relative to its folder.")
    single: bool = Field(False, description="The kind is one file, named by the pattern; no other can be made.")


class DataFile(BaseModel):
    """One file of a kind, across the data layers."""

    file: str
    layers: list[Literal["shipped", "workspace", "project"]] = Field(description="The layers that hold a copy.")
    layer: Literal["shipped", "workspace", "project"] | None = Field(
        description="The copy in effect; none for a single-file kind not made yet."
    )
    problem: ScreenText | None = Field(None, description="Why the copy in effect doesn't fit the form, if it doesn't.")


class DataFileView(BaseModel):
    """One file as a form: the schema's fields with the values in effect."""

    file: str
    layer: Literal["shipped", "workspace", "project"] | None = Field(
        description="The copy in effect; None for a new file, shown with the defaults."
    )
    layers: list[Literal["shipped", "workspace", "project"]]
    problem: ScreenText | None = None
    items: list[SettingItem]


class DataFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(description="The file's name, like classic.yaml (or folder/item.yaml for such a kind).")
    layer: Literal["workspace", "project"] = Field(description="Which copy to write or remove; never the shipped one.")
    project: str | None = Field(None, description="The project, for its layer.")
    changes: dict[str, Any] = Field(default_factory=dict, description="New values by field (dotted for groups).")
    start_from: str | None = Field(None, description="For a new file: another file of the kind to start from.")


class DataFileRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    layer: Literal["workspace", "project"]
    project: str | None = None
    before: str | None = Field(description="The copy's text from before, or None to remove it.")


class DataFileSaved(BaseModel):
    before: str | None = Field(description="The layer's copy before this change, for Undo; None when there was none.")


# ---- adding watched sources ------------------------------------------------------------------------------------------


class WatchKindView(BaseModel):
    """A kind of source the assistant can keep reading, with the form its settings take."""

    name: str
    label: str
    plugin: str | None = Field(None, description="The add-on it comes from; None for the app's own.")
    first_run: Literal["baseline", "recent", "all"] = Field(
        "baseline",
        description="What the first read of a source of this kind added here does: baseline only notes what is "
        "there, recent also hands in the last day's, all hands everything in.",
    )
    items: list[SettingItem]


class WatchSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector: str = Field(description="The kind of source, from GET /api/watch/kinds.")
    label: str = ""
    every_minutes: int = Field(60, ge=5)
    project: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict, description="Its settings, by field (nested as objects).")
    fingerprint: str


class WatchSourceChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    every_minutes: int | None = Field(None, ge=5)
    enabled: bool | None = None
    settings: dict[str, Any] | None = None
    fingerprint: str


class PackInstalled(BaseModel):
    name: str = Field(description="The installed package's name.")
    version: str
    needs_restart: bool = Field(description="It is used after a restart the person chooses; turning it on is separate.")
