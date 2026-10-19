"""Response and request models for the API. The web client's types are generated from these through OpenAPI, so a
changed field here fails the web build instead of breaking the UI at run time.

Models carry data, not wording: the UI words everything through its wording sheet.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.screen_text import ScreenText
from engine.records import KnowledgeEvidence, Scope

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


class NudgeSent(BaseModel):
    """A follow-up message the PM sent: what it listed (from `FollowupSection.nudge`) and its text as sent, to notice
    edits."""

    text: str | None = Field(None, description="The message as the PM sent it, to notice edits.")
    question_ids: list[str] = []
    action_ids: list[str] = []


class NudgeUnsent(BaseModel):
    """What undoes a follow-up marked as sent: the response that recorded it, sent back."""

    question_ids: list[str] = []
    action_ids: list[str] = []
    on: str = Field(description="The day the chases were recorded.")
    previous_told: dict[str, str | None] = Field(
        default_factory=dict, description="The day each action's person was told before the chase, by action id."
    )
    signal_at: str | None = Field(None, description="When the edit of the message was recorded, if it was edited.")


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


class QuestionRewordIn(BaseModel):
    title: str | None = Field(None, min_length=1, description="The new title; left out, it stays as it is.")
    text: str | None = Field(None, description="The new text, in the person's own words; left out, it stays as it is.")


class QuestionRerouteIn(BaseModel):
    to: str = Field(min_length=1, description="The person to ask instead, by id or name.")


class QuestionDropIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500, description="Why the question isn't needed, in plain words.")


class ActionDropIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500, description="Why the action isn't needed, in plain words.")


class ActionReplyIn(BaseModel):
    text: str | None = Field(
        None,
        min_length=1,
        description="The person's own wording of the reply; left out, the drafted reply is approved as it is.",
    )


class FoldIn(BaseModel):
    into: str = Field(min_length=1, description="The id of the open action to add the one waiting for an owner to.")
    read_version: int = Field(description="The version of that action as the person saw it.")


class NewPersonIn(BaseModel):
    """The form that answers a "Who is this?" question with a new person."""

    full_name: str = Field(min_length=1, description="The person's full name.")
    first_name: str | None = Field(None, description="The name a greeting to them uses, when it isn't the first word.")
    org: str | None = Field(
        None, description="The organization's name or id; a name no record has makes a new organization."
    )
    role: str | None = Field(None, description="Their job or part in the work.")
    contact_kind: str | None = Field(
        None, description="What kind of contact detail the value is, from the offered kinds."
    )
    contact_value: str | None = Field(None, description="A way to reach them, of that kind.")


class NewPersonPrefillView(BaseModel):
    """What the "Add a new person" form starts with, from the question and the input it came from."""

    full_name: str = Field(description="The name as the input wrote it.")
    first_name: str
    org: str = Field(description="The organization the input gives, by name; empty when it gives none.")
    role: str = Field(description="The role the input gives; empty when it gives none.")
    contact_kind: str = Field(description="The kind of the detail the input gives for them; empty when none.")
    contact_value: str = Field(description="The contact detail the input gives for them; empty when none.")
    contact_kinds: list[str] = Field(description="The kinds of contact detail to pick from.")


class NewPersonDone(BaseModel):
    """A new person was added and the work waiting on the name went ahead."""

    person: str = Field(description="The new person's id.")
    name: str = Field(description="Their full name.")
    undo: list[str] = Field(description="The changes that add them, newest first, to undo after the released items.")
    changeset: str | None = Field(None, description="The change whose held items went ahead.")
    released: list[int] = Field(description="The positions of the held items that went ahead.")


class PartOfIn(BaseModel):
    project: str = Field(min_length=1, description="The id of the project the held project is part of.")


class QuestionSentIn(BaseModel):
    on: date | None = Field(None, description="The day the person sent it themselves; today when left out.")


class ChangeIn(BaseModel):
    note: str = Field(
        min_length=1,
        description="What to change about it, in the person's own words; the assistant reads it. Required: a change "
        "with no words is never sent.",
    )


class ChangeRequested(BaseModel):
    ok: str = Field(description="The id of the item the change was asked for.")
    request: str | None = Field(None, description="The work queued for the assistant from the note.")
    signal: str = Field(description="The id of the correction recorded for it.")


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


class NudgeRecorded(BaseModel):
    questions: int
    actions: int
    question_ids: list[str]
    action_ids: list[str]
    on: str = Field(description="The day the chases were recorded (a date).")
    previous_told: dict[str, str | None] = Field(
        description="The day each action's person was told before, by action id."
    )
    signal_at: str | None = Field(None, description="When an edit of the message was recorded, if it was edited.")


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
    encrypted: bool = Field(False, description="Whether every backup copy is encrypted (a key is set for it).")


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


class OwnerSuggestionView(BaseModel):
    """What the workspace's own records suggest for an action that has no owner. The person still picks."""

    person: str | None = Field(None, description="The id of the person a routing entry says does this kind of work.")
    person_name: str | None = Field(None, description="That person's full name.")
    entry: str | None = Field(None, description="The id of the routing entry that says so.")
    why: str | None = Field(None, description='The routing entry\'s own words, for "because you told me ...".')
    fold_into: str | None = Field(
        None, description="The id of the open action this one most nearly repeats, to fold it into."
    )
    fold_into_text: str | None = Field(None, description="That action's text.")
    fold_version: int | None = Field(
        None, description="That action's version as read, to send back when adding this action to it."
    )


class Ask(BaseModel):
    """A question to the PM that an item waits on: who a name is, or who owns an action."""

    id: str
    status: str
    about: Literal["held-op", "owner", "other"]
    name: str | None = Field(None, description="The name the assistant couldn't place, for who-is questions.")
    options: list[Option]
    suggestion: OwnerSuggestionView | None = Field(
        None, description="For owner questions: who the routing entries suggest and the nearest open action."
    )


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
    name: str | None = Field(None, description="The name of what the op proposes to add, such as a project.")
    role: str | None = Field(None, description="The part in a project that the op sets: run, design or watch.")


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


class AppliedEntryView(BaseModel):
    """A piece of what the assistant knew that a run said it applied (design 6.20, 7.18): a lesson, glossary entry,
    routing entry, style note, standing rule or fact, with what is needed to narrow or retire it from the work's
    card."""

    id: str
    kind: Literal["lesson", "glossary_entry", "routing_entry", "style_note", "rule", "fact"]
    version: int = Field(description="The entry's version, to send back with Narrow or Retire.")
    text: str = Field(description="The entry in plain words.")
    status: str = Field(description="active, retired and so on; a fact is always active.")
    applies_to: Scope | None = Field(None, description="What it applies to; a fact applies to its project only.")


class MadeView(BaseModel):
    """A draft or file a change made, for the "Made:" link on the change's card: `label` says what it is for (the
    record a draft is for, or the file's name) and `record` is where the person opens it."""

    kind: Literal["draft", "file"]
    id: str = Field(description="The draft's version, or the file.")
    label: str
    record: RecordRef


class ChangesetView(BaseModel):
    id: str
    summary: str
    status: str
    reviewed: bool
    trust: Literal["trusted", "untrusted"]
    ops: list[OpView]
    made: list[MadeView] = Field(
        default_factory=list,
        description="The drafts and files this change made that still exist, in the order made, so its card links "
        "each without opening the details.",
    )
    applied: list[AppliedEntryView] = Field(
        default_factory=list,
        description="What the run was given from what was learned and showed it applied, for the line 'Because you "
        "told me'.",
    )
    first_on_account: str | None = Field(
        None,
        description="The name of the AI account when this was the first run on an account that stands in a fallback "
        "chain, so the card can say so.",
    )
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
    range_usd: list[float] | None = Field(
        None, description="What the whole request was estimated to cost, low and high; none when it couldn't be priced."
    )
    spent_usd: float | None = Field(
        None,
        description="What its AI work has cost so far, leaving out runs an outage cut off; none when nothing priced "
        "ran.",
    )
    refused: bool = Field(
        False, description="The account declined it under its own policy; it can be sent to another account."
    )
    cause: StopCauseView | None = Field(None, description="For a stopped request: the cause an action can clear.")
    follows: str | None = Field(None, description="The change (changeset id) this work followed from, if any.")
    follows_summary: str | None = Field(None, description="That change's one-line summary, for the row.")
    redoes: str | None = Field(
        None,
        description="The change (changeset id) this work redoes after the person sent it back, so what was learned "
        "from the send-back shows on this row too.",
    )
    changeset: ChangesetView | None
    title: ItemTitle | None = Field(None, description="The item's title, by the title rule.")
    mail_item: str | None = Field(
        None, description="For work on a mail message the app is holding: its id, for 'Set aside' on the row."
    )
    intake: str | None = Field(
        None,
        description="The id of the newly added source whose first read (or look further back) took this in, so its "
        "results can be listed together.",
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
    project_name: str | None = Field(None, description="The projects it is about, by name, joined with commas.")
    sent: str | None = Field(description="The day it was first sent; chases never change it.")
    followed_up: str | None = Field(None, description="The day the person was last chased about it (a date).")
    chases: int = Field(0, description="How many times the person was chased about it after it was sent.")
    waiting_days: int | None = Field(
        description="Days since the last word to the person: the message, or the latest chase."
    )
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
    links: list[Link] = Field(
        default_factory=list, description="Pages that belong to the action's project, for the copied table."
    )
    told: str | None
    told_days: int | None
    followed_up: str | None = Field(None, description="The day the person was last chased about it (a date).")
    chases: int = Field(0, description="How many times the person was chased about it.")
    on_hold: str | None = Field(
        None, description="What the action waits for while it is on hold; an action on hold is never chased."
    )
    chase_due: bool = Field(
        False,
        description="Whether the follow-up rule says chasing is the next step: its due date is near or past, "
        "or it has waited long enough with no word, and it is not on hold.",
    )
    origin: Origin | None = Field(None, description="Where the action came from, for its link.")


class NudgeView(BaseModel):
    """A drafted follow-up message for one person (built from a template, no AI run): what has gone unanswered as long
    as the follow-up rule says. `round` is which follow-up it is: 1, or 2 and up once the person was chased before, when
    it lists less and asks who else to ask. The ids are what it lists, and what Mark sent records a chase on."""

    text: str
    round: int
    question_ids: list[str]
    action_ids: list[str]


class FollowupSection(BaseModel):
    person: str
    name: str
    is_pm: bool
    questions: list[FollowupQuestion]
    actions: list[FollowupAction]
    message: str
    to_send: int
    nudge: NudgeView | None = Field(None, description="The follow-up message to draft, when anything is due one.")


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
    how_to_reach: dict[str, str] = Field(
        default_factory=dict, description="How to reach them: a channel name mapped to its address or handle."
    )


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
    role: Literal["run", "design", "watch"] = Field(
        "run", description="The person's part in the project; a project with no role for them is one they run."
    )
    content_levels: list[str] = Field(default_factory=list)
    budget_usd: float | None = None
    spent_usd: float = Field(0.0, description="What AI work on it and everything in it has cost.")
    open_actions: int = 0
    open_questions: int = 0
    last_change: str | None = Field(None, description="When the project record last changed.")
    completed: bool = Field(
        False,
        description="Its status is the one the settings say means finished: it is listed under Completed, not removed.",
    )


class NoteView(BaseModel):
    id: str
    text: str
    project: str | None
    project_name: str | None
    created_at: str | None = Field(None, description="When the note was filed, from the first record of it.")
    trust: Literal["trusted", "untrusted"]


class UnfiledItem(BaseModel):
    kind: Literal["note", "action", "question", "fact"]
    id: str
    version: int
    text: str = Field(
        description="The item in one line: a note's or fact's words, an action's text, a question's title."
    )
    created_at: str | None = Field(None, description="When the assistant filed it.")
    trust: Literal["trusted", "untrusted"] = "trusted"


class UnfiledView(BaseModel):
    """What the assistant filed under no project (design 7.14), newest first. `count` is the length of `items`, so the
    screen never shows a zero: it shows nothing when there is none."""

    count: int
    items: list[UnfiledItem]


class UnfiledRef(BaseModel):
    kind: Literal["note", "action", "question", "fact"]
    id: str
    read_version: int | None = Field(
        None,
        description="The version of the item the person was looking at; the filing is refused if it changed since. "
        "Left out, the current version is used.",
    )


class UnfiledFile(BaseModel):
    project: str = Field(description="The project to file them under, from GET /api/projects.")
    items: list[UnfiledRef] = Field(min_length=1)


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


class ProjectRoleIn(BaseModel):
    """The person's own part in a project."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["run", "design", "watch"] = Field(description="run, design or watch.")


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
    series: str | None = Field(None, description="The series of meetings it is for, when it is on one.")
    series_title: str | None = None
    meeting_on: str | None = Field(
        None, description='The day of the meeting it sits on (YYYY-MM-DD), for "for Thursday\'s print sync".'
    )


class OpenQuestion(BaseModel):
    id: str
    title: str
    to: str | None = None
    to_name: str | None = None
    status: str | None = None
    kind: str | None = None
    origin: Origin | None = Field(None, description="Where the question came from, for its link.")
    series: str | None = None
    series_title: str | None = None
    meeting_on: str | None = None


class CompletedAction(BaseModel):
    """Finished work: credited to who did it, with who said it was done (a nudge is never completion)."""

    id: str
    text: str
    project: str | None = None
    project_name: str | None = None
    done_by: list[str] = Field(default_factory=list, description="Names of the people who did the work.")
    reported_by: str | None = Field(None, description="Name of the person who said it was done.")
    done_on: str | None = Field(None, description="The day it was closed, YYYY-MM-DD.")


class FactSource(BaseModel):
    """Who a fact rests on and where it came from, for the label in its meta line (never part of copied or published
    text). `basis` is person (the person said it), said (someone else did: `by`, reported by `reported_by` when another
    person's input carried it) or inferred (the assistant worked it out, so it feeds the record only until the person
    confirms it); null for a fact recorded before this was kept."""

    basis: Literal["person", "inferred", "said"] | None = None
    by: str | None = Field(None, description="Name of the person who said it, when someone else did.")
    reported_by: str | None = Field(None, description="Name of the person whose input carried what was said.")
    input: str | None = Field(None, description="The input it came from, by its short name.")
    on: str | None = Field(None, description="The day it was confirmed, true as of, or filed, YYYY-MM-DD.")
    origin: Origin | None = Field(None, description="Where it came from, for the link that is the label.")


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


class SeriesMeeting(BaseModel):
    """One meeting of a series: its calendar entry, when it starts (as written) and its day in the person's zone."""

    id: str
    title: str
    start: str
    on: str | None = Field(None, description="The day it falls on, YYYY-MM-DD.")


class SeriesItem(BaseModel):
    kind: Literal["action", "question"]
    id: str
    text: str = Field(description="An action's words or a question's title.")
    status: str | None = None
    due: str | None = None
    rolled_from: SeriesMeeting | None = Field(
        None, description="The meeting the item sat on before it moved to this one, when it moved."
    )


class SeriesMovedItem(BaseModel):
    kind: Literal["action", "question"]
    id: str
    text: str
    status: str | None = None
    to: SeriesMeeting | None = Field(None, description="The meeting it moved to.")


class SeriesPersonGroup(BaseModel):
    person: str | None = Field(None, description="The person the items are with; null when it is not known.")
    name: str | None = None
    is_pm: bool = Field(description='The person themselves, listed last and shown as "You".')
    items: list[SeriesItem]


class SeriesNext(SeriesMeeting):
    open: int = Field(description="How many open items sit on it.")
    groups: list[SeriesPersonGroup]


class SeriesPast(SeriesMeeting):
    settled: list[SeriesMovedItem]
    moved: list[SeriesMovedItem]


class SeriesPageView(BaseModel):
    """A series' page (design 7.14): the next meeting's open items by person, then the meetings that passed."""

    id: str
    title: str
    repeats: str | None = Field(None, description="How often it repeats, in the person's own words.")
    project: str | None = None
    project_name: str | None = None
    next: SeriesNext | None = Field(None, description="The next meeting; null when none is scheduled.")
    past: list[SeriesPast] = Field(description="Meetings that passed, newest first.")
    open_without_next: int = Field(0, description="Open items waiting when no later meeting exists.")


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
    completed_actions: list[CompletedAction] = Field(
        default_factory=list,
        description="Finished actions credited to this person (who did the work) or in this project, newest first.",
    )
    fact_source: FactSource | None = Field(None, description="For a fact: who it rests on and where it came from.")
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


class ListMergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, description="The value that goes away.")
    into: str = Field(min_length=1, description="The value that takes its place; it must be offered on the list.")


class DroppedQuestionView(BaseModel):
    """A question that is closed as dropped, kept on record."""

    id: str
    title: str
    text: str
    to: str = Field(description="The id of the person it was for.")
    to_name: str
    reason: str | None = Field(None, description="Why the person dropped it; none when the app closed it itself.")
    dropped_at: datetime | None = Field(None, description="When it was dropped.")
    projects: list[str] = Field(default_factory=list)
    origin: Origin | None = Field(None, description="Where the question came from, for its link.")


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
    series: str | None = Field(None, description="For an own entry: the series it is one meeting of.")
    open_items: int = Field(
        0, description="For a meeting of a series: how many open actions and questions sit on it (never shown as zero)."
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


class HeldAsk(BaseModel):
    """A held item as the question the person is asked (design 7.6): `ask` is what is proposed (close an item, change
    its date, give it to another owner, send a question to someone else instead, or drop it), `item` the words of what
    it is about, `value` and `from_value` the new and the present date, `to_name` the person it would go to, `told`
    the people a drop would leave out of the loop (told on `told_on`) and `quote` the words the assistant rested it
    on. The screen words the title and the two answers from these."""

    ask: Literal["close", "date", "owner", "routing", "drop"]
    item: str
    value: str | None = None
    from_value: str | None = None
    to_name: str | None = None
    told: list[str] = Field(default_factory=list)
    told_on: str | None = None
    quote: str | None = None


class AfterMove(BaseModel):
    """The move a question (or a group of them) came after (design 7.7): the record that moved, by its own name, the day
    it moved to and whether that is earlier than where it was. `others` names the people the same follow-on run asked
    questions of; those wait in Follow-ups."""

    kind: str = Field(description="What moved: event, action or fact.")
    record: str
    title: str
    to: str | None = Field(None, description="The day it moved to, YYYY-MM-DD.")
    earlier: bool = False
    by: Literal["assistant", "pm"] = Field(description="Whether the person or the assistant (from an input) moved it.")
    replaced: bool = Field(False, description="A fact that was replaced rather than a date that moved.")
    request: str
    changeset: str | None = Field(None, description="The follow-on run's own change, which Undo takes back.")
    others: list[str] = Field(default_factory=list)


class QueueLineView(BaseModel):
    """One line of Today's queue (design 7.7), in rank order. The screen words it from `kind` and the counts. `restart`
    is work held until the person restarts the app (`count` waiting; the screen offers Restart now, which is
    POST /api/restart); `paused` is an AI account waiting for its usage limit to reset (`account`, `until`, `count`
    waiting), after which the work runs again by itself; `borrow` asks whether another kind of work's free account
    (`account`, `model`) may take the `tier`'s work that waits on the paused account named in `text`, until `until`,
    when that account's limit resets (`count` waiting items it would take, `estimate_usd`, `unpriced`; the answer is
    POST /api/ai/borrow); `offline` is work that has waited for the network longer than
    the configured time (`count` waiting, `waiting_since`), which runs again by itself once the network is back;
    `catch_up_go` is the learning runs for the catch-up list held together for one go (`count`, `estimate_usd`,
    `unpriced`; the go is POST /api/knowledge/catch-up/go); `intake_go` is a newly added source (`source`, `subject` its
    label) whose first read is held for one go (`count` items, `estimate_usd` and `unpriced` for the total, `days` how
    far back its mail was read, none for a source with no mail; the go is POST /api/watch/{source}/intake/go);
    `intake_review` is what the first read of a newly added source found (`source`, `subject`, `count` items with
    something to look over, `outcome` their results counted), one line in place of a line for each until the list is
    opened (POST /api/watch/{source}/intake/seen); `credential` is a key or sign-in that stops working on
    `due` or already has (`credential_kind`, `credential_name`, `waiting_days` left, below zero once past, and
    `places`, everywhere the same credential is used); `switch_failed` is a switch of the `tier`'s account or model
    whose check found problems or couldn't finish (the new `account`, the earlier one in `text`, `count` and `names`
    of what didn't come out right, `check_failed` when it couldn't finish; Switch back is POST
    /api/ai/switch/{tier}/back and Keep it POST /api/ai/switch/{tier}/keep); `no_account` is work with no AI account
    at all (`count` kinds of work, their tiers in `names`, the first in `tier`); `extractor` is a kind of file that
    isn't being read (`file_kind`, and `text` says why), which clears once a file of that kind reads well;
    `source_unread` is a watched source that has failed for longer than its usual gap (`source` its id, `subject` its
    label, `problem_kind` the kind of failure, `text` what went wrong and what to do, `waiting_since` when it was last
    read, or first tried when it never was), which clears once it is read again; `unfiled` is
    what the assistant filed under no project (`count` items, never zero: with none there is no line; they are listed
    by GET /api/unfiled)."""

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
        "catch_up_go",
        "intake_go",
        "intake_review",
        "refused",
        "restart",
        "handover",
        "failed",
        "paused",
        "borrow",
        "offline",
        "overdue",
        "account_check",
        "switch_failed",
        "credential",
        "no_account",
        "extractor",
        "source_unread",
        "review",
        "rule_review",
        "learned",
        "catch_up",
        "send",
        "nudge",
        "unfiled",
        "moved",
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
    subject: str | None = Field(
        None,
        description="The one thing's own words when a review or overdue line covers exactly one, which the screen "
        "uses as the line's title; null when the line groups several.",
    )
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
        None,
        description="The estimated cost of everything the line starts (first_go, catch_up_go, intake_go), when any has "
        "a price.",
    )
    unpriced: int = Field(
        0, description="How many of the things the line starts have no price (first_go, catch_up_go, intake_go)."
    )
    account: str | None = Field(None, description="The AI account waiting for its limit to reset (paused).")
    until: datetime | None = Field(
        None,
        description="When the account's limit resets and the work waiting on it runs again by itself (paused), or "
        "when the line comes back if the person says Not now (rule_review), on the person's own clock (their time "
        "zone).",
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
    rules: list[str] = Field(
        default_factory=list, description="For a rule_review line: the ids of the rules flagged, most present first."
    )
    stable_size: int | None = Field(
        None,
        description="For a rule_review line: the size of what every run is sent, in characters, on the latest run.",
    )
    stable_budget: int | None = Field(
        None, description="For a rule_review line: the size that section may be before rules move out of it."
    )
    moved: int | None = Field(
        None,
        description="For a rule_review line: how many rules the latest run had moved out of the always-sent part, so "
        "they go only to the runs they cover.",
    )
    days: int | None = Field(
        None,
        description="For a rule_review line: how many days the flagged rules have been given and never applied. For "
        "an intake_go line: how many days back the source's mail was read; none when it holds no mail.",
    )
    origins: dict[str, int] = Field(
        default_factory=dict,
        description="For a learned line: how many of the proposals came from an input (`input`) and how many from one "
        "of the person's corrections (`correction`).",
    )
    expired: int | None = Field(
        None,
        description="For a learned line: how many proposals from inputs expired unreviewed since the person last "
        "looked at what was learned.",
    )
    left_out: int | None = Field(
        None,
        description="For a catch_up line: how many kinds of earlier correction were too many for the list and expired "
        "unread.",
    )
    file_kind: str | None = Field(
        None,
        description="For an extractor line: the kind of file that isn't being read (document, spreadsheet, "
        "presentation, pdf or text), or the label an add-on gave its own kind. `text` says why.",
    )
    source: str | None = Field(
        None, description="For a source_unread line: the watched source's id; its label is in GET /api/watch."
    )
    problem_kind: str | None = Field(
        None,
        description="For a source_unread line: the kind of failure (auth, no_access, not_found, outage, or another "
        "kind a connector reports), which the screen words as what to do.",
    )
    credential_kind: Literal["account", "sign_in"] | None = Field(
        None, description="For a credential line: an AI account's key or an add-on's sign-in."
    )
    credential_name: str | None = Field(
        None, description="For a credential line: the account's short name or the sign-in's name."
    )
    places: list[str] = Field(
        default_factory=list,
        description="For a credential line: every place the same credential is used, in plain words.",
    )
    tier: str | None = Field(
        None,
        description="For an account_check line: the tier whose fallback chain holds the account. For a switch_failed "
        "line: the tier that was switched.",
    )
    names: list[str] = Field(
        default_factory=list,
        description="For a switch_failed line: what the check found didn't come out right, by name, the first few.",
    )
    model: str | None = Field(
        None, description="For an account_check line: the short name of the account's model in that chain."
    )
    check_failed: bool | None = Field(
        None,
        description="For an account_check line: true when the account's last check failed, false when it was never "
        "checked for that work. For a switch_failed line: true when the check couldn't finish.",
    )
    suggestion: OwnerSuggestionView | None = Field(
        None,
        description="For an owner line: who the routing entries suggest owns the action and why, and the nearest open "
        "action to fold it into; none when nothing applies.",
    )
    after_move: AfterMove | None = Field(
        None,
        description="For a question the person was asked after something moved, and for the moved line that groups "
        "several: the move it came after. A moved line's `questions` are its rows and `changeset` is the follow-on "
        "run's change.",
    )
    held: HeldAsk | None = Field(
        None,
        description="For a held line that rests on an inference or would drop something that reached someone: the "
        "question it asks. Keeping things as they are is POST /api/changesets/{id}/ops/{index}/decline.",
    )


class FirstGoStarted(BaseModel):
    started: int = Field(description="How many runs the first go started.")


class CatchUpStarted(BaseModel):
    started: int = Field(description="How many learning runs for the catch-up list the go started.")


class IntakeStarted(BaseModel):
    started: int = Field(description="How many requests of the source's intake the go started.")


class IntakeSeen(BaseModel):
    requests: list[str] = Field(
        description="The requests of the source's intake marked seen, which Undo "
        "(POST /api/watch/{source}/intake/unseen) gives back."
    )


class IntakeUnseenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: list[str] = Field(description="The requests POST /api/watch/{source}/intake/seen marked.")


class IntakeUnseen(BaseModel):
    restored: int = Field(description="How many requests were put back as not yet seen.")


class LookBackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, description="How many days further back to look, one of the source's choices.")


class LookBackView(BaseModel):
    """What looking further back takes in (GET) or took in (POST): the items, what they cost and how far the source
    reaches."""

    days: int
    from_date: date = Field(description="The day asked for: mail from this day on is looked at.")
    count: int = Field(description="Items the look takes in (before: would take in); none that a rule closes.")
    estimate_usd: float | None = Field(
        None,
        description="About what they cost; after the look, what everything held for the source's go costs. None when "
        "no price is known.",
    )
    unpriced: int = Field(0, description="How many of the items have no price.")
    reaches: bool = Field(
        description="False when the source holds no mail as far back as asked: `available_from` is where its mail "
        "starts and nothing earlier can be taken in."
    )
    available_from: date | None = Field(None, description="The oldest mail the source has returned, when it is later.")
    taken: int = Field(0, description="After the look: the requests made.")
    started: bool = Field(
        False, description="After the look: they started at once; False when they wait for the go or none was made."
    )


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
    problems: list[ScreenText] = Field(
        default_factory=list,
        description="One sentence for each source that couldn't be read this time: why, and what to do.",
    )


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
    group: Literal["decide", "risk", "review", "send"] | None = Field(
        None,
        description="Which of the queue's groups the line sits in; none puts it under the fallback heading at the end.",
    )


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
    choices: str | None = Field(
        None, description="The name of the list a choice setting picks from (time_zones, languages), when it has one."
    )
    secret: bool | None = Field(
        None,
        description="True when the value is a reference to a secret (a password, a key, a private address): the "
        "screen offers a box to type it in, kept by the app, instead of asking where it is kept.",
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

    name: str = Field(description="Its short name in ai.yaml; an identifier, never shown to the person.")
    label: str = Field(
        "", description="The name the person gave it; empty when they gave none (the screen says the service's name)."
    )
    kind: str | None = Field(None, description="The kind of account it was made from (GET /api/ai/endpoints).")
    adapter: str
    base_url: str | None = None
    models: dict[str, str]
    used_for: list[str] = Field(description="The tiers whose main account it is.")
    backup_for: list[str] = Field(default_factory=list, description="The tiers it stands in for as a backup.")
    has_key: bool = Field(description="A key or a reference to one is set.")
    key_state: Literal["saved", "missing", "none"] = Field(
        "none",
        description="saved: its key is there to use. missing: it refers to a key that isn't there (an environment "
        "variable not set, a file not found). none: no key is set.",
    )
    key_where: ScreenText | None = Field(
        None, description="Where a missing key is looked for, in plain words; never a key."
    )
    credential_expires: date | None = Field(
        None, description="The day its key stops working, when one was entered; Today says so ahead of it."
    )
    key_ending: bool = Field(
        False, description="Its key stops working within the days Today warns ahead (`ai.credential_warn_days`)."
    )
    answered_at: datetime | None = Field(
        None, description="When it last answered a call, on the person's own clock; none before the first."
    )
    spent_today_usd: float = Field(0.0, description="What its calls cost today, in the person's day.")
    checked_for: list[str] = Field(
        default_factory=list,
        description="The kinds of work (tiers) it passed the connection check for, with their exact settings.",
    )
    check_failed_for: list[str] = Field(
        default_factory=list, description="The kinds of work (tiers) whose last check of it failed."
    )
    checked_at: datetime | None = Field(
        None, description="When it was last checked as it is set up now; none when it never was."
    )
    paused_until: datetime | None = Field(
        None, description="When the usage limit holding it resets, on the person's own clock; none when not paused."
    )
    check_usd: float | None = Field(
        None,
        description="About what one connection check of it costs, from the prices in the settings or kept from earlier "
        "runs; none when its price isn't known.",
    )


SettingLayer = Literal["default", "file", "env", "flag"]


class AiKindFit(BaseModel):
    """What the measurements hold for the model one tier uses, over the skills a kind of work needs (design 6.16)."""

    tier: str
    skills: int = Field(description="How many skills the kind of work needs, as the cases that run it name them.")
    measured: int = Field(description="Of those, how many have at least one run.")
    stale: int = Field(description="Of the measured, how many are out of date: unknown, never a pass.")
    below: int = Field(description="Of the measured, how many are under the minimum score (`ai.skills.min_score`).")
    runs: int = Field(description="All runs of those skills, out-of-date ones included.")
    passes: int
    cost_per_pass_usd: float | None = Field(None, description="What a passing run cost on average; none without one.")
    status: Literal["ok", "below_min", "stale", "not_measured"] = Field(
        description="ok: every skill measured, fresh and above the minimum. Anything else is not a pass."
    )


class AiWorkKindView(BaseModel):
    """One kind of AI work and the tier it uses now (design 7.9, which model does what)."""

    name: str = Field(description="The kind of work's name, as `ai.tasks.<name>` and the routing rules name it.")
    label: str = Field(description="The kind of work in plain words; the screen's own wording sheet may say it better.")
    tier: str = Field(description="The tier it uses now: the workspace's choice, else its role's, else its own.")
    default_tier: str = Field(description="The tier it uses when the workspace has made no choice for it.")
    custom: bool = Field(description="The workspace chose this kind of work's tier (`ai.tasks.<name>.tier` is set).")
    source: SettingLayer = Field(
        description="The layer that set `ai.tasks.<name>.tier`; env and flag can't be changed here."
    )
    fits: list[AiKindFit] = Field(description="What was measured for it, for the model each tier uses.")
    suggested_tier: str | None = Field(
        None,
        description="The cheapest tier whose model passed every skill this kind of work needs; none when none did.",
    )
    suggestion_why_not: Literal["no_accounts", "no_cases", "not_measured", "stale", "none_passes"] | None = Field(
        None, description="Why there is no suggestion: nothing to run it on, no case that measures it, or the results."
    )


class AiTierView(BaseModel):
    """One tier: the account it uses and the stronger tier it tries once more on."""

    name: str = Field(description="The tier's name in the settings; the screen words it.")
    account: str | None = Field(None, description="The short name of the account that does its work; none when unset.")
    escalate_to: str | None = Field(
        None, description="The stronger tier tried once more when the answer keeps failing the app's checks."
    )
    escalate_source: SettingLayer = Field(description="The layer that set `ai.tiers.<name>.escalate_to`.")


class AiRouteRuleView(BaseModel):
    """One routing rule: all the parts given must match, and then the request goes to the tier."""

    task: str | None = None
    input_chars_over: int | None = None
    quoted_messages_over: int | None = None
    data_level: Literal["open", "internal", "restricted"] | None = None
    tier: str


class AiRuleSuggestion(BaseModel):
    """A routing rule the measurements back, offered only; nothing is added until the person says so."""

    rule: AiRouteRuleView
    skills: list[str] = Field(description="The labels of the skills the tier in use is measured under the minimum on.")


class AiRoutingView(BaseModel):
    """Which model does what: every kind of work with its tier, the tiers with their second tries, the routing rules in
    the order they are checked, and the spending limits that apply to a stronger model."""

    kinds: list[AiWorkKindView]
    tiers: list[AiTierView]
    rules: list[AiRouteRuleView]
    rules_source: SettingLayer = Field(
        description="The layer that set `ai.routing`; env and flag can't be changed here."
    )
    rule_suggestions: list[AiRuleSuggestion] = Field(
        description="Rules the measurements back, at most one for each kind of work."
    )
    min_score: float = Field(description="`ai.skills.min_score`: the pass rate a skill needs to count.")
    confirm_above_usd: float = Field(
        description="`ai.budgets.confirm_above_usd`: work estimated above it waits for a go."
    )
    per_run_usd: float = Field(description="`ai.budgets.per_run_usd`: no single run is started above it.")


class AiSkillView(BaseModel):
    """What the measurements hold for one model and one skill (design 6.16): a skill is one kind of thing a run can get
    right or wrong. A skill nobody measured has no runs."""

    id: str
    label: ScreenText = Field(description="The skill in plain words.")
    description: ScreenText = Field(description="What the skill covers, in plain words.")
    measured: bool = Field(description="At least one run of a case that proves this skill was counted.")
    runs: int = 0
    passes: int = 0
    pass_rate: float | None = Field(None, description="Share of runs that passed, 0 to 1; none when never measured.")
    age_days: int | None = Field(None, description="Days since the last run counted; none when never measured.")
    cost_per_pass_usd: float | None = Field(
        None, description="What a passing run cost on average; none when no run passed."
    )
    stale: Literal["program", "age", "cases"] | None = Field(
        None,
        description="Why the measurement can't be trusted any more: the agent program changed, it is older than the "
        "configured number of days, or the cases that measured it changed. It counts as unknown for routing.",
    )
    below_min: bool = Field(False, description="The pass rate is under the configured minimum score.")


class AiModelSkills(BaseModel):
    model: str = Field(description="The short name the person gave the model, never its id.")
    measure: Literal["waiting", "measuring", "failed"] | None = Field(
        None,
        description="Where a measuring the person asked for stands: waiting its turn, running, or failed (then "
        "`measure_why` says why). None when none is asked for.",
    )
    measure_why: ScreenText | None = Field(None, description="Why the last measuring failed, in plain words.")
    skills: list[AiSkillView]


class AiAccountSkills(BaseModel):
    name: str = Field(description="The account's short name in ai.yaml.")
    models: list[AiModelSkills]


class AiSkillsView(BaseModel):
    """Every account's models against every skill, for the grid in Settings."""

    min_score: float = Field(description="ai.skills.min_score: the pass rate a skill needs to count as able.")
    stale_days: int = Field(description="ai.skills.stale_days: how long a measurement is trusted.")
    accounts: list[AiAccountSkills]


class AiMeasureIn(BaseModel):
    """What to measure: one of the account's models, or all of them."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(
        None, description="The short name of the model to measure; left out, every model of the account is measured."
    )
    confirmed: bool = Field(
        False,
        description="The person's go for a cost above the amount they asked to be asked about; without it such a "
        "measuring is refused.",
    )


class AiMeasureEstimate(BaseModel):
    """What measuring an account would run and cost, shown before anything is spent."""

    models: list[str] = Field(description="The short names of the models that would be measured, each on its own.")
    level: Literal["open", "internal", "restricted"] | None = Field(
        None, description="The most private material the account is allowed to see; none when it is allowed none."
    )
    cases: int = Field(description="How many cases and pairs each model runs: only those the account may see.")
    skipped: int = Field(description="How many are left out because their material is more private than allowed.")
    runs: int = Field(description="How many times each runs.")
    usd: float | None = Field(None, description="About what all of it costs; none when a model has no known price.")
    confirm_above_usd: float = Field(description="The amount above which the person is asked first.")
    needs_go: bool = Field(description="Starting it needs `confirmed`: the estimate is above that amount.")


class AiMeasureStarted(BaseModel):
    started: list[str] = Field(description="The models whose measuring was started, by short name.")
    already: list[str] = Field(description="The models already waiting or running, left as they were.")
    estimate: AiMeasureEstimate


class AiAccountChange(BaseModel):
    """A change to an existing account: a new key, other models, or the work it does."""

    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(None, description="A new pasted key; kept on this computer.")
    key_ref: str | None = Field(None, description="Or where the key is now: env:NAME or file:/path.")
    credential_expires: date | None = Field(
        None, description="The day its key stops working, when the service gives one."
    )
    clear_credential_expires: bool | None = Field(
        None, description="Forget the end date of its key (it has none, or is renewed)."
    )
    label: str | None = Field(None, description="The name the person gives it; empty clears it.")
    models: dict[str, str] | None = Field(None, description="Its models, replacing the ones it has.")
    use: dict[str, str] = Field(default_factory=dict, description="Tiers to one of its models by short name.")
    backup: dict[str, str] = Field(
        default_factory=dict,
        description="Tiers to one of its models by short name, added to each tier's backups: the accounts tried in "
        "order when the main one can't answer. An account already a backup there with another model has that entry "
        "moved to this one. Only a checked account, or one accepted unchecked, may be one.",
    )
    stop_backup: bool | None = Field(None, description="Take the account out of every kind of work's backups.")
    fingerprint: str


class AiAccountRemove(BaseModel):
    """Remove an account, saying which backup takes over the work it did."""

    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    take_over: str | None = Field(
        None,
        description="The name of a backup account that does the removed account's work in its place, for each kind of "
        "work it stands in for; left out, that work has no account until one is chosen.",
    )


class AiCheckSize(BaseModel):
    """What one account's connection check involves, for pricing it with a model's price per million tokens."""

    calls: int = Field(description="How many small calls the check makes.")
    input_tokens: int = Field(description="About how many tokens they read together.")
    output_tokens: int = Field(description="About how many tokens they write together.")


class AiSwitchEstimate(BaseModel):
    """What the check that comes with a change of account or model would cost, and whether one is offered."""

    offered: bool = Field(
        description="Whether the change switches a tier's account or model while checks on a switch are on."
    )
    usd: float | None = Field(
        None, description="About what the check would cost; none when the new choice has no known price."
    )
    cases: int = Field(0, description="How many cases the check runs, each `runs` times.")
    runs: int = Field(0, description="How many times each case runs.")


class AiSwitched(BaseModel):
    saved: SettingsSaved = Field(description="What changed in the settings, for the read-back and Undo.")
    checking: bool = Field(
        description="A check of the new choice is running in the background; a failure comes to Today."
    )


class AiBorrowAnswer(BaseModel):
    """The person's answer to the question of using another kind of work's account while the work's own are paused."""

    model_config = ConfigDict(extra="forbid")

    tier: str = Field(description="The tier whose work waits (the line's `tier`).")
    account: str = Field(description="The account the question offered (the line's `account`).")
    model: str = Field(description="Its model's short name (the line's `model`).")
    use: bool = Field(description="True: use it until the paused account's limit resets. False: keep the work waiting.")


class AiBorrowed(BaseModel):
    released: int = Field(description="How many waiting requests were let go to run on the account at once.")


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
    label: str | None = Field(
        None, description='The name the person gives it, shown in lists; left out: the service\'s name and "account".'
    )
    adapter: str = Field(description="The adapter of the kind of account chosen, from GET /api/ai/endpoints.")
    endpoint: str | None = Field(
        None, description="The kind of account chosen; its starting provider settings are added to the account's."
    )
    base_url: str | None = None
    key: str | None = Field(None, description="A key pasted on the screen; kept in this computer's private folder.")
    key_ref: str | None = Field(None, description="Or a reference: env:NAME or file:/path.")
    credential_expires: date | None = Field(
        None, description="The day its key stops working, when the service gives one."
    )
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
    error_advice: str | None = Field(
        None,
        description="For a failed read: the wording key of what to do about it, when the connector named one. The "
        "screen words it from its sheet; without one the kind's usual advice applies.",
    )
    new: int = 0
    changed: int = 0
    removed: int = 0


class SourceSecretView(BaseModel):
    """Where one of a source's secret settings (a password, a private address) is read from, never its value."""

    field: str = Field(description="The setting's dotted name, as in the kind's form items.")
    where: Literal["kept", "env", "file", "other"] = Field(
        description="kept: typed on this screen and kept by the app on this computer; env: read from a named "
        "environment variable; file: read from a file of the person's own; other: another way of keeping it."
    )
    name: str | None = Field(None, description="The variable's name, or the file's path; empty when it is kept.")


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
    author: str | None = Field(None, description="The person or team whose work all it holds is, as an id.")
    author_name: str | None = Field(None, description="Their name, for showing; empty when none is set or it is gone.")
    items: int = Field(description="Items it held at the last read.")
    last: WatchRunView | None = None
    read_at: str | None = Field(
        None, description="When it was last actually read; a try that found no network or failed doesn't count."
    )
    failures: int = Field(0, description="Failed reads in a row.")
    problem: ScreenText | None = Field(None, description="Why it can't be read, and what to do, while it fails.")
    looked_back_to: date | None = Field(
        None,
        description="For a source whose first read took it in quietly: the day before which its mail wasn't looked "
        "at. None for a source with no mail or another kind of first read.",
    )
    look_back_choices: list[int] = Field(
        default_factory=list,
        description="When `looked_back_to` is set: how many more days the person can ask to look, to pick from.",
    )
    secrets: list[SourceSecretView] = Field(
        default_factory=list, description="Where each secret setting it has set is read from."
    )


class WatchAuthorOption(BaseModel):
    """Someone a source can be credited to: the person themselves, a colleague or a team."""

    id: str
    name: str
    kind: Literal["you", "person", "team"]


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


class SilentCloseView(BaseModel):
    """Something closed, dropped, set aside or answered that the person neither made nor saw: what, when, by which rule
    or run, and why."""

    ref: str = Field(description="Names the close, for marking it seen.")
    kind: Literal["rule", "set_aside", "assistant"] = Field(
        description="rule: a triage rule closed a change before it was read. set_aside: mail set aside as not work by "
        "a rule or the assistant's sorting. assistant: an action or question the assistant closed as data."
    )
    how: Literal["closed", "set_aside", "dropped", "answered"]
    title: str = Field(description="What was closed: the change's or mail's title, the action's or question's words.")
    when: str
    why: str = Field(description="The rule's reason, the assistant's reason or the words it cited.")
    rule: str | None = Field(None, description="The rule's name, for a close a rule made.")
    run: str | None = Field(None, description="The assistant's run that made the close, if one did.")
    request: str | None = None
    changeset: str | None = None
    snapshot: str | None = Field(None, description="The mail item, for one set aside.")
    record: RecordRef | None = Field(None, description="The record that was closed.")


class CloseKindCountView(BaseModel):
    kind: Literal["rule", "set_aside", "assistant"]
    total: int = Field(description="Closes of this kind in the period.")
    silent: int = Field(description="Of those, the ones nobody has seen.")


class CloseMeasureView(BaseModel):
    """Silent closes out of all closes in the period, with the counts behind the rate."""

    days: int = Field(description="How many days back the period looks (the quality window).")
    since: str
    until: str
    total: int = Field(description="All closes in the period, the person's own and approved ones included.")
    silent: int
    by_person: int = Field(description="Closes the person made themselves.")
    approved: int = Field(description="Closes the assistant or a rule made that the person then saw and approved.")
    rate: float | None = Field(None, description="Silent over total; empty when nothing was closed.")
    kinds: list[CloseKindCountView]


class SilentClosesView(BaseModel):
    count: int = Field(description="How many closes nobody has seen, in the period.")
    closes: list[SilentCloseView] = Field(description="Those closes, newest first.")
    measure: CloseMeasureView


class SilentCloseSeen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(description="The close's `ref`, from the list.")


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
    release_host: str | None = Field(
        None,
        description="The host its release file is read from, which a read token for it is sent to; empty when it has "
        "no release.",
    )


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
    address: str | None = Field(None, description="The catalog's address, as the person gave it.")
    removable: bool | None = Field(
        None, description="The person added it (workspace.plugins.catalog.feeds), so it can be taken off again."
    )


class CatalogAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(description="A catalog's address: https://, then where its list is kept.")
    fingerprint: str


class PackTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str | None = Field(
        None,
        description="A read token typed on the screen, for the host the add-on's release file is read from. A local "
        "app keeps it in its private folder and writes only where it is kept; a hosted app refuses it. Never stored "
        "in the settings or sent back.",
    )
    reference: str | None = Field(None, description="Where the token is kept instead: env:NAME or file:/path.")
    fingerprint: str


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
    first_run: Literal["intake", "baseline", "recent", "all"] = Field(
        "intake",
        description="What the first read of a source of this kind added here does: intake takes it in quietly (one "
        "summary and one list to look over), baseline only notes what is there, recent also hands in the last day's, "
        "all hands everything in.",
    )
    items: list[SettingItem]


class WatchSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector: str = Field(description="The kind of source, from GET /api/watch/kinds.")
    label: str = ""
    every_minutes: int = Field(60, ge=5)
    project: str | None = None
    author: str | None = Field(None, description="A person's or team's id, from GET /api/watch/authors.")
    settings: dict[str, Any] = Field(default_factory=dict, description="Its settings, by field (nested as objects).")
    secrets: dict[str, str] = Field(
        default_factory=dict,
        description="Passwords, keys and private addresses typed on the screen, by the setting's dotted name. A "
        "local app keeps each in its private folder and writes only where it is kept into the settings; a hosted app "
        "refuses them. Never stored in the settings, the ledger or any answer.",
    )
    fingerprint: str


class WatchSourceChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    every_minutes: int | None = Field(None, ge=5)
    enabled: bool | None = None
    author: str | None = Field(
        None, description="A person's or team's id, from GET /api/watch/authors; empty, when sent, clears it."
    )
    settings: dict[str, Any] | None = None
    secrets: dict[str, str] = Field(
        default_factory=dict,
        description="Secret settings typed on the screen, by dotted name; see the same field when adding a source. "
        "A field not named keeps what it holds.",
    )
    fingerprint: str


class PackInstalled(BaseModel):
    name: str = Field(description="The installed package's name.")
    version: str
    needs_restart: bool = Field(description="It is used after a restart the person chooses; turning it on is separate.")


class KnowledgeUse(BaseModel):
    """How much the runs used a piece of knowledge, from their knowledge logs (design 6.22): `given` runs listed it,
    `used` runs applied it, and `last_used` is when the latest of those began. All zero for one no run was given."""

    used: int = Field(0, description="How many runs applied it.")
    given: int = Field(0, description="How many runs were given it.")
    last_used: datetime | None = Field(None, description="When the latest run that applied it began.")


class KnowledgeView(KnowledgeUse):
    """One piece of what the assistant learned: a lesson, glossary entry, routing entry or style note. `learned_from`
    says whose words it is (person, input, assistant, pack, seed or import); `origin` is the link to where it came from,
    decided on the server like an action's. The fields after `applies_to` are those of its kind and are empty for
    the others."""

    id: str
    kind: Literal["lesson", "glossary_entry", "routing_entry", "style_note"]
    version: int
    text: str = Field(description="The entry in plain words.")
    status: Literal["proposed", "active", "discarded", "expired", "retired"]
    learned_from: Literal["person", "input", "assistant", "pack", "seed", "import"]
    pack: str | None = None
    trust: Literal["trusted", "untrusted"]
    learned_at: datetime
    kept_by: str | None = Field(None, description="The person who kept it, and so the author of its wording.")
    kept_at: datetime | None = None
    discard_reason: str | None = None
    applies_to: Scope
    evidence: KnowledgeEvidence | None = Field(None, description="The words and records it was learned from.")
    origin: Origin | None = Field(None, description="Where it came from, for its link.")
    guard: str | None = None
    signal: str | None = None
    term: str | None = None
    meaning: str | None = None
    confidence: Literal["confirmed", "assumed", "unknown"] | None = None
    project: str | None = None
    id_patterns: list[str] = Field(default_factory=list)
    topic: str | None = None
    person: str | None = None
    team: str | None = None
    negative: bool | None = None
    look_up: str | None = None
    audience: str | None = None
    observation: str | None = None


class RuleView(KnowledgeUse):
    """One standing rule, as the Knowledge screen lists it: its wording, what it applies to and constrains, where it
    came from and how much the runs used it."""

    id: str
    version: int
    name: str = Field(description="The rule's own name.")
    text: str = Field(description="The rule in the person's wording.")
    status: Literal["proposed", "active", "discarded", "expired", "retired"]
    learned_from: Literal["person", "input", "assistant", "pack", "seed", "import"]
    trust: Literal["trusted", "untrusted"]
    learned_at: datetime | None = None
    kept_by: str | None = Field(None, description="The person who made it active.")
    kept_at: datetime | None = None
    discard_reason: str | None = None
    applies_to: Scope
    constrains: list[str] = Field(
        default_factory=list,
        description="What it is about: op kinds or op fields. Empty means nothing is checked, so it is only present.",
    )
    enforced: bool = Field(
        False, description="A code check enforces it, so it holds whether or not anything triggers it."
    )
    evidence: KnowledgeEvidence | None = Field(None, description="The words and records it was learned from.")
    origin: Origin | None = Field(None, description="Where it came from, for its link.")


class KnowledgeKeep(BaseModel):
    """Keep a proposed entry. A new wording or target made here is the person's own."""

    model_config = ConfigDict(extra="forbid")

    read_version: int = Field(ge=1, description="The entry's version that was read.")
    text: str | None = Field(None, min_length=1, description="The entry's wording, when the person changed it.")
    applies_to: Scope | None = Field(None, description="What it applies to, when the person changed it.")


class KnowledgeNarrow(BaseModel):
    """Narrow what a rule or entry applies to: the person's own change to its scope."""

    model_config = ConfigDict(extra="forbid")

    read_version: int = Field(ge=1, description="The entry's version that was read.")
    applies_to: Scope = Field(description="What it applies to from now on.")


class RuleReviewRule(BaseModel):
    """A standing rule offered for review: given to runs and never shown to apply."""

    id: str
    version: int = Field(description="The rule's version, to send back with Keep, Narrow or Retire.")
    name: str
    text: str = Field(description="The rule in the person's wording.")
    applies_to: Scope
    present: int = Field(description="How many runs in the window were given it without it showing as applied.")
    applied: int = Field(description="How many runs in the window showed it applied.")


class RuleReviewView(BaseModel):
    """The weekly review of standing rules (design 6.22): the rules to look over, most present first, and how large the
    always-sent section is against its budget."""

    days: int = Field(description="The window the counts cover, in days.")
    flagged: list[RuleReviewRule]
    stable_chars: int = Field(description="The size of what every run is sent, in characters, on the latest run.")
    stable_budget: int = Field(description="The size that section may be before rules move out of it.")
    moved: int = Field(description="How many rules the latest run had moved out of the always-sent part.")
    due: bool = Field(description="Whether Today offers the review now.")


class RuleReviewPutOff(BaseModel):
    """The answer to "Not now" on the rules review line: the review is off Today until this moment."""

    until: datetime = Field(description="When the review is offered again, if it still has something to show.")
    signal: str = Field(description="The id of what was recorded, which Undo takes back.")


class KnowledgeDiscard(BaseModel):
    """Discard a proposed entry; it is kept, with the reason if one is given."""

    model_config = ConfigDict(extra="forbid")

    read_version: int = Field(ge=1, description="The entry's version that was read.")
    reason: str | None = Field(None, description="Why, if the person says.")


class ProposalView(KnowledgeView):
    """One proposal waiting for the person: a piece of what the assistant learned, or a standing rule, to keep, set
    aside "just this time" or discard. `came_from` says where it came from (an input, or one of the person's
    corrections); proposals from inputs expire at `expires_at`, those from corrections never do."""

    kind: Literal["lesson", "glossary_entry", "routing_entry", "style_note", "rule"]
    name: str | None = Field(None, description="A rule's own name.")
    came_from: Literal["input", "correction"]
    batch: Literal["daily", "catch_up"] = Field(
        description="daily: reviewed on Today's one line for what was learned. catch_up: part of the one list made "
        "from corrections recorded before the assistant could learn from them."
    )
    more_evidence: list[KnowledgeEvidence] = Field(
        default_factory=list, description="What other proposals of the same thing were learned from, merged into it."
    )
    just_this_time_before: int = Field(
        0, description='How many times the person said "just this time" to the same correction before.'
    )
    expires_at: datetime | None = Field(None, description="When it expires unreviewed; none for one that never does.")
    from_changeset: str | None = Field(
        None,
        description="For one learned from a correction: the change the correction was about, so its card can show "
        "the proposal.",
    )


class LearnedLine(BaseModel):
    """What the assistant learned from one correction, for the line under that correction's card (design 7.18).
    `learning`: the assistant is still working on it (`waiting` says why and until when). `proposed`: there is a
    `proposal` to keep. `kept`: the person's own words were kept at once; `undo` is the change that makes Undo."""

    signal: str = Field(description="The id of the correction.")
    kind: str = Field(description="What the person did (sent_back, answered_assistant, change_requested and so on).")
    changeset: str | None = Field(None, description="The change the correction was about, when it was about one.")
    refs: list[str] = Field(default_factory=list, description="The records the correction was about.")
    state: Literal["learning", "proposed", "kept"]
    waiting: ScreenText | None = Field(None, description="While learning: why it waits, in plain words.")
    proposal: ProposalView | None = Field(None, description="The entry, for a proposal or one kept at once.")
    undo: str | None = Field(None, description="For one kept at once: the change to undo.")


class LearnedView(BaseModel):
    """The learning of the corrections that have something to show: still being learned, a proposal to keep, or the
    person's own words kept at once. The catch-up list's proposals are not here."""

    lines: list[LearnedLine]


class ProposalsView(BaseModel):
    """Everything the assistant learned that waits for the person, oldest first, apart from the catch-up list."""

    proposals: list[ProposalView]
    origins: dict[str, int] = Field(description="How many came from an input and how many from a correction.")
    expired: int = Field(description="How many from inputs expired unreviewed since the person last looked.")


class CatchUpView(BaseModel):
    """The one list of what the assistant learned from corrections made before it could learn from them (design
    6.22): at most the configured number of kinds of correction, the most repeated first."""

    proposals: list[ProposalView]
    made_at: datetime | None = Field(None, description="When the list was made; none before it has been.")
    waiting: int = Field(description="Kinds of correction chosen that the assistant hasn't learned from yet.")
    left_out: int = Field(description="Kinds of correction too many for the list; they expired unread.")
    most: int = Field(description="The most kinds of correction one list holds.")


class QualityKnowledgeUsed(BaseModel):
    """How often one kind of work used what it was given (design 6.20): the runs whose answer listed an entry it had
    been given, over the runs given at least one."""

    task: str = Field(description="The kind of work.")
    runs_given: int = Field(description="Runs in the window that were given at least one lesson, rule or fact.")
    runs_applied: int = Field(description="Of those, the runs whose answer listed at least one entry it was given.")
    dropped: int = Field(description="Entries answers named as applied that the run had not been given; left out.")
    rate: float | None = Field(None, description="Applied over given; none when no run was given anything.")


class QualityRepeatWeek(BaseModel):
    """One kind of work in one week: how many corrections repeated a mistake the assistant had been taught about."""

    task: str = Field(description="The kind of work that was corrected.")
    week: date = Field(description="The Monday of the week, in the person's time zone.")
    corrections: int = Field(description="Corrections of that work in the week.")
    repeats: int = Field(description="Of those, the ones whose run had been given a lesson or rule for the same item.")
    enough: bool = Field(description="Whether the week had enough corrections to say anything.")
    rate: float | None = Field(None, description="Repeats over corrections; none for a week without enough.")


class QualityMissingGroup(BaseModel):
    """What several answers said no op could do, in one wording."""

    wording: str = Field(description="What was needed, in the most recent wording.")
    count: int = Field(description="How many answers said it.")
    tasks: list[str] = Field(description="The kinds of work that said it.")
    changesets: list[str] = Field(description="The answers that said it, newest first.")
    last_seen: datetime | None = Field(None, description="When the newest answer was made.")


class QualityMissingWeek(BaseModel):
    """The missing-op list for one week, most said first."""

    week: date = Field(description="The Monday of the week, in the person's time zone.")
    groups: list[QualityMissingGroup]


class QualityView(BaseModel):
    """The quality view (design 6.20, 6.13): the knowledge-used rate, the repeat-correction rate by week and the weekly
    missing-op list, over the configured window."""

    days: int = Field(description="The window the figures cover, in days.")
    min_corrections_per_week: int = Field(description="The fewest corrections a week needs for its rate to show.")
    knowledge_used: list[QualityKnowledgeUsed]
    repeat_corrections: list[QualityRepeatWeek]
    missing: list[QualityMissingWeek]
