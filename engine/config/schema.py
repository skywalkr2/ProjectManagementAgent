"""Config file schemas.

Each config file is one model. Every field has a default and a description: the description feeds the comment block
written into new config files, the settings forms and `cockpit config show`.
"""

from __future__ import annotations

import re
import string
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.secrets import SecretHint


class ConfigModel(BaseModel):
    """Base for config models: unknown keys are errors, so a typo never silently does nothing."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class FileModel(ConfigModel):
    """Base for a whole config file."""

    version: int = Field(1, description="Format version of this file. Older files are migrated at start.")


# ---- config/workspace.yaml -------------------------------------------------------------------------------------------


class UserSettings(ConfigModel):
    person: str | None = Field(
        None,
        description="The PM's own person record id, e.g. PER-1. Their name and other names live on that record only.",
    )
    timezone: str = Field(
        "UTC",
        description="The PM's time zone, as an IANA name such as Europe/Lisbon.",
        json_schema_extra={"choices": "time_zones"},
    )


class ToolSettings(ConfigModel):
    timeout_seconds: float = Field(120, gt=0, description="How long a plugin's program may run if it sets no limit.")
    max_timeout_seconds: float = Field(
        1800, gt=0, description="The longest any program may run; plugins can't ask more."
    )
    probe_timeout_seconds: float = Field(10, gt=0, description="How long a program's version check may take.")
    output_kb: int = Field(512, gt=0, description="How much of a program's output and error stream is kept, in KB.")
    collect_file_mb: float = Field(25, gt=0, description="Largest file a program wrote that is returned to the plugin.")
    collect_total_mb: float = Field(100, gt=0, description="Most a program's returned files may add up to, in MB.")


class ActionSettings(ConfigModel):
    keep_minutes: float = Field(60, gt=0, description="How long a reviewed proposal waits for the person's go.")
    preview_mb: float = Field(5, gt=0, description="Largest single preview an action may show, in MB.")
    max_previews: int = Field(20, ge=0, description="Most previews one action may show.")
    max_items: int = Field(
        2000, ge=0, description="Most items one action may offer to keep or drop (a long file gives many)."
    )
    max_requests: int = Field(
        100, ge=0, description="Most pieces of follow-up work one action may queue for the assistant at once."
    )


class JobSettings(ConfigModel):
    enabled: bool = Field(True, description="Off: the job doesn't run.")
    every_minutes: int | None = Field(None, ge=5, description="How often it runs; unset means the plugin's default.")


class CatalogSettings(ConfigModel):
    enabled: bool = Field(True, description="Show the packs catalog feeds list on the Add-ons screen.")
    shipped_feed: bool = Field(
        True,
        description="Include the catalog feed this build of the app came with, if any.",
        json_schema_extra={"enabled_by": "enabled"},
    )
    feeds: list[str] = Field(
        default_factory=list,
        description="More catalog feeds to read, as https addresses (a team's own, say).",
        json_schema_extra={"enabled_by": "enabled"},
    )
    refresh_hours: int = Field(
        24,
        ge=1,
        le=720,
        description="How old the kept copy of a feed may be before opening the screen reads it again.",
        json_schema_extra={"enabled_by": "enabled"},
    )
    release_tokens: dict[str, str] = Field(
        default_factory=dict,
        description=SecretHint(
            "Read tokens for hosts that keep private packs' release files, by host name, as references "
            "(env:NAME or file:/path, never the token itself); sent only to that host when installing."
        ),
    )

    @field_validator("release_tokens")
    @classmethod
    def _references(cls, value: dict[str, str]) -> dict[str, str]:
        for host, ref in value.items():
            if not str(ref).startswith(("env:", "file:")):
                raise ValueError(f"{host}: a read token is a reference to where it is kept, never the token itself")
        return value

    @field_validator("feeds")
    @classmethod
    def _https(cls, value: list[str]) -> list[str]:
        for url in value:
            if not url.startswith("https://"):
                raise ValueError(f"{url}: a catalog feed is an https address")
        return value


class PluginSettings(ConfigModel):
    enabled: list[str] = Field(default_factory=list, description="Plugins enabled in this workspace, by name.")
    actions: ActionSettings = Field(
        default_factory=ActionSettings, description="How person actions from plugins are reviewed."
    )
    tools: ToolSettings = Field(
        default_factory=ToolSettings,
        description="Limits on the outside programs plugins run (where they are found is set per computer, not here).",
    )
    jobs: dict[str, JobSettings] = Field(
        default_factory=dict, description="Plugins' scheduled work, by job name: on or off, and how often."
    )
    secrets: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description=SecretHint(
            "Each plugin's secrets, by plugin then secret name, as references (env:NAME or file:/path), "
            "never the secret itself."
        ),
    )
    failures_before_off: int = Field(
        3,
        ge=1,
        description="How many times in a row a plugin's Today lines, interface items, event handler or job may fail "
        "before the plugin is turned off; each failure is noted on the plugin.",
    )
    catalog: CatalogSettings = Field(
        default_factory=CatalogSettings, description="Where the Add-ons screen finds packs to tell you about."
    )


class WorkspaceFile(FileModel):
    name: str = Field("Workspace", description="The workspace's display name.")
    assistant_name: str = Field("Assistant", description="The assistant's display name; the only name people see.")
    user: UserSettings = Field(default_factory=UserSettings, description="Who the PM is.")
    owner_format: str = Field(
        "{full_name}",
        description='How an action owner is shown: {full_name} and, if you like, {team}, e.g. "{team} ({full_name})". '
        "An owner with no team is shown by the full name alone.",
    )
    language: str = Field(
        "en-US",
        pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
        description="The language and variety work is written in, as a language tag (en-US, en-GB, fr-CA); a project "
        "may set its own.",
    )
    plugins: PluginSettings = Field(default_factory=PluginSettings, description="Which plugins run in this workspace.")
    our_accounts: list[str] = Field(
        default_factory=list,
        description="The names the PM and this app use on watched sources, so changes by them read as ours.",
    )
    demo: bool = Field(
        False,
        description="Made-up example data: every screen says so, so nobody mistakes it for real work.",
    )

    @field_validator("owner_format")
    @classmethod
    def _owner_format_names_the_person(cls, value: str) -> str:
        fields = {name for _, name, _, _ in string.Formatter().parse(value) if name is not None}
        if "full_name" not in fields or not fields <= {"full_name", "team"}:
            raise ValueError("write the owner with {full_name}, and {team} if you like, such as {team} ({full_name})")
        return value


# ---- config/server.yaml ----------------------------------------------------------------------------------------------


class ServerFile(FileModel):
    mode: Literal["local", "hosted"] = Field(
        "local",
        description="local: only this computer can reach the app. hosted: runs behind sign-in and deploy checks.",
    )
    host: str = Field("127.0.0.1", description="Address to listen on.")
    port: int = Field(8765, ge=1, le=65535, description="Port to listen on.")
    base_path: str = Field("/", description="Path the app is served under, e.g. /admin. Every route and link uses it.")
    public_url: str | None = Field(None, description="The address people use to reach the app. Required when hosted.")
    open_browser: bool = Field(
        False, description="Open the app in this computer's browser when it starts (local mode only)."
    )

    @field_validator("base_path")
    @classmethod
    def _base_path_shape(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("must start with /")
        if value != "/" and value.endswith("/"):
            raise ValueError("must not end with / (except the root itself)")
        return value


# ---- config/storage.yaml ---------------------------------------------------------------------------------------------


class ExportSettings(ConfigModel):
    every_minutes: int = Field(
        60,
        ge=1,
        description="How often, in minutes, the readable export in data/ is written and committed while the app runs. "
        "A workspace with no repository is not exported on a schedule.",
    )
    commit: bool = Field(True, description="Commit the export and config to the workspace's git repository.")
    remote: str | None = Field(
        None,
        description="A private repository address for an off-site copy of the export. Not used yet: nothing is sent.",
    )


class BackupTarget(ConfigModel):
    path: str = Field(
        "", description="A folder off this computer: a synced folder, an external drive or a network share."
    )
    label: str = Field("", description='What to call this target on screen, e.g. "cloud folder".')


class BackupSettings(ConfigModel):
    automatic: bool = Field(
        True,
        description="Make backups on schedule while the app runs, with nothing to click; off means only on request.",
    )
    targets: list[BackupTarget] = Field(default_factory=list, description="Where full backups go. Use at least one.")
    every_hours: int = Field(
        24, ge=1, description="How often a full backup is made.", json_schema_extra={"enabled_by": "automatic"}
    )
    keep: int = Field(14, ge=1, description="How many backups to keep in each target.")
    retry_minutes: int = Field(
        60,
        ge=5,
        description="After a failed backup (a drive not connected, say), how long before trying again.",
        json_schema_extra={"enabled_by": "automatic"},
    )


class FileLimits(ConfigModel):
    max_file_mb: float = Field(50, gt=0, description="The largest single file that can be added, in megabytes.")
    max_total_mb: float = Field(2000, gt=0, description="The most all added files may take together, in megabytes.")
    accepted_types: list[str] = Field(
        default_factory=lambda: [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/epub+zip",
            "font/otf",
            "font/ttf",
            "font/woff",
            "font/woff2",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        description="Media types a file may have; a file kind can narrow this further.",
    )


class SyncSettings(ConfigModel):
    folder: str = Field(
        "",
        description="A folder a file-sync service keeps in step between your computers. After every change the "
        "workspace is written there, one folder per project, readable in any editor. Empty: off. The workspace "
        "itself must not be inside it.",
        json_schema_extra={"picker": "folder"},
    )
    watch_outside_edits: bool = Field(
        True,
        description="Bring back edits made to the folder's files in other programs, as changes for you to review. "
        "Off: they are only reported, and the files are left as they are.",
        json_schema_extra={"enabled_by": "folder"},
    )
    shared: bool = Field(
        False,
        description="Whether anyone else can change the files in this folder (a team drive, a family folder). When "
        "they can, an edit found in the folder is treated as outside content to check, not as your own words.",
        json_schema_extra={"enabled_by": "folder"},
    )
    lease_stale_after_minutes: int = Field(
        10,
        ge=1,
        description="How long after the other computer was last seen the workspace can be opened here without it "
        "closing first (when it went to sleep or lost power, say).",
        json_schema_extra={"enabled_by": "folder"},
    )


class StorageFile(FileModel):
    backend: Literal["sqlite"] = Field("sqlite", description="Where records live. Postgres comes later.")
    export: ExportSettings = Field(default_factory=ExportSettings, description="The readable export and its history.")
    backups: BackupSettings = Field(default_factory=BackupSettings, description="Full backups to somewhere else.")
    files: FileLimits = Field(default_factory=FileLimits, description="Limits on files people and programs add.")
    sync: SyncSettings = Field(
        default_factory=SyncSettings, description="Handing the workspace between computers through a synced folder."
    )


# ---- config/ai.yaml --------------------------------------------------------------------------------------------------

DataLevel = Literal["open", "internal", "restricted"]


class AgentOutputFields(ConfigModel):
    text: str = Field("", description="Dotted path to the answer in the agent's JSON output; empty: the whole output.")
    input_tokens: str = Field("", description="Dotted path to the input token count, if the agent reports it.")
    output_tokens: str = Field("", description="Dotted path to the output token count, if the agent reports it.")
    cached_input_tokens: str = Field("", description="Dotted path to the cached input token count, if reported.")
    cost_usd: str = Field("", description="Dotted path to the cost the agent reports for the run, if any.")
    model: str = Field("", description="Dotted path to the model the agent says it used, if any.")


class AgentErrorPatterns(ConfigModel):
    auth: list[str] = Field(default_factory=list, description="Patterns in the error stream meaning: not signed in.")
    rate_limited: list[str] = Field(
        default_factory=list, description="Patterns in the error stream meaning: too many requests, try later."
    )
    quota: list[str] = Field(
        default_factory=list, description="Patterns in the error stream meaning: the plan's usage limit is reached."
    )
    reset: list[str] = Field(
        default_factory=list,
        description="Patterns in the error stream for a limit's reset time: the first group is a number of seconds "
        "from now or a date and time (ISO 8601). Used for a usage limit or a request to wait.",
    )
    exit_codes: dict[int, Literal["auth", "rate_limited", "quota", "provider_down"]] = Field(
        default_factory=dict, description="Exit codes the agent documents, mapped to what they mean."
    )
    report_on_output: bool = Field(
        False,
        description="The agent prints its errors on its output, not only its error stream: when a run fails, its "
        "output is read as its error report, before the error stream (never for a run that succeeded).",
    )


class AgentSettings(ConfigModel):
    command: list[str] = Field(
        default_factory=list,
        description="The program and its arguments, locked-down flags included. Placeholders: {model}, {packet} "
        "(the packet file), {prompt} (the packet's text, for packet_via: argument), {outbox} (the folder for the "
        "answer), {scratch} (the run's folder).",
    )
    packet_via: Literal["stdin", "file", "argument"] = Field(
        "stdin",
        description="How the agent gets the packet: on its input, as a file named by {packet}, or as the argument "
        "{prompt} (for a program that takes its prompt only on the command line).",
    )
    output_via: Literal["stdout", "outbox"] = Field(
        "stdout", description="Where the agent puts its answer: its output, or a file in {outbox}."
    )
    output_json: bool = Field(False, description="The agent prints JSON; output_fields says where the answer is.")
    output_fields: AgentOutputFields = Field(
        default_factory=AgentOutputFields, description="Where the answer and usage are in the agent's JSON output."
    )
    pass_env: list[str] = Field(
        default_factory=list,
        description="Environment variables the agent may see besides PATH, HOME and the language settings.",
    )
    key_env: str | None = Field(
        None, description="The environment variable the agent reads its key from, when the account uses a key."
    )
    errors: AgentErrorPatterns = Field(
        default_factory=AgentErrorPatterns,
        description="How to read the agent's exit code and error stream (never its answer).",
    )
    sign_in_hint: str = Field(
        "", description="What to do when the agent isn't signed in, such as its login command; shown with the question."
    )
    home: Literal["shared", "fresh"] = Field(
        "shared",
        description="shared: the agent uses this user's home folder, where it may keep memory between runs. fresh: "
        "each run gets an empty home folder with only home_files copied in, so nothing one run keeps reaches the next.",
    )
    home_files: list[str] = Field(
        default_factory=list,
        description="With a fresh home: the files or folders, relative to this user's home, the agent needs to stay "
        "signed in (its credentials), copied into each run's home.",
    )


class ProviderSettings(ConfigModel):
    adapter: str = Field("stub", description="Which installed adapter talks to this account.")
    kind: str | None = Field(
        None, description="The kind of account from the app's list it was made from (its id), for showing its name."
    )
    base_url: str | None = Field(None, description="The API address, for adapters that need one.")
    auth: str | None = Field(
        None, description=SecretHint("A secret reference (env:NAME or file:/path), never the secret itself.")
    )
    models: dict[str, str] = Field(default_factory=dict, description="Short names for this account's models.")

    @field_validator("models", mode="before")
    @classmethod
    def _space_after_colon(cls, value: Any) -> Any:
        """`name:model-id` without a space reads as one name with no model; say so instead of a type error."""
        if isinstance(value, dict):
            for key, model in value.items():
                if model is None and ":" in str(key):
                    name, _, rest = str(key).partition(":")
                    raise ValueError(f"put a space after the colon: write '{name}: {rest}', not '{key}'")
        return value

    allowed_data: list[DataLevel] = Field(
        default_factory=lambda: ["open"], description="The most sensitive material this account may see."
    )
    content_levels: list[str] | None = Field(
        None,
        description="The content levels this account takes (those defined for AI); unset means it takes every level.",
    )
    timeout_seconds: int = Field(90, ge=5, description="How long to wait for an answer.")
    json_mode: bool = Field(True, description="Ask the provider for JSON output when it supports that.")
    agent: AgentSettings | None = Field(
        None, description="For a command-line agent account: how to start it, pass the packet and read its answer."
    )


class TierSettings(ConfigModel):
    use: str = Field(
        "", description="provider/model short name that does this tier's work; empty means no account is set up yet."
    )
    fallback: list[str] = Field(default_factory=list, description="Tried in order when the main one can't serve.")
    escalate_to: str | None = Field(None, description="A stronger tier to retry on when checks keep failing.")


class TaskSettings(ConfigModel):
    tier: str = Field("routine", description="Which tier this kind of work uses.")
    temperature: float = Field(
        0.0, ge=0, le=2, description="Randomness: near zero for extraction, a little for drafting."
    )
    max_output: int = Field(4000, ge=256, description="The most tokens an answer may use.")
    expected_output: int = Field(
        800, ge=1, description="Typical answer size in tokens, for estimates until there are past runs to go by."
    )
    same_account: bool | None = Field(
        None,
        description="For a check: accept a run on an account that wrote the work, as a fresh run that sees only its "
        "packet, when no other account can take it. Unset follows the same choice for checks in general.",
    )


class RoleSettings(ConfigModel):
    tier: str | None = Field(
        None, description="The tier for every kind of work in this role, unless tasks.<kind>.tier says otherwise."
    )
    same_account: bool = Field(
        False,
        description="For checks: accept a run on an account that wrote the work, as a fresh run that sees only its "
        "packet, when no other account can take it. The check then says it came from the same account.",
    )


class Roles(ConfigModel):
    write: RoleSettings = Field(default_factory=RoleSettings, description="Work that writes or changes things.")
    check: RoleSettings = Field(
        default_factory=RoleSettings,
        description="Independent second opinions on work already done, on an account other than the one that did it.",
    )
    research: RoleSettings = Field(default_factory=RoleSettings, description="Work that gathers from sources.")


class TaskBudget(ConfigModel):
    per_day_usd: float | None = Field(
        None, ge=0, description="Stop new runs of this kind for the day above this total."
    )
    per_month_usd: float | None = Field(
        None, ge=0, description="Stop new runs of this kind for the month above this total."
    )


class Budgets(ConfigModel):
    per_run_usd: float = Field(0.25, ge=0, description="Never start a single run estimated above this cost.")
    confirm_unpriced: bool = Field(
        False,
        description="Ask for a go before a run whose cost can't be estimated (an account with no prices, such as a "
        "subscription), too.",
    )
    first_go: bool = Field(
        True,
        description="Until you give your first go in a workspace, AI runs wait. Today shows one line with how many "
        "items are waiting and about what they cost, and one Go starts them all. After that, the amount to ask "
        "above applies.",
    )
    confirm_above_usd: float = Field(
        0.10,
        ge=0,
        description="Ask for a go before a run estimated above this cost; below it, runs start on their own.",
    )
    per_task: dict[str, TaskBudget] = Field(
        default_factory=dict, description="Limits for one kind of work, on top of the overall ones."
    )
    per_day_usd: float = Field(2.0, ge=0, description="Stop new runs for the day above this total.")
    per_month_usd: float = Field(30.0, ge=0, description="Stop new runs for the month above this total.")
    warn_at: float = Field(0.8, gt=0, le=1, description="Warn when this share of a budget is used.")


class Price(ConfigModel):
    input_per_million: float = Field(0.0, ge=0, description="Price in USD per million input tokens.")
    output_per_million: float = Field(0.0, ge=0, description="Price in USD per million output tokens.")
    cached_input_per_million: float | None = Field(
        None,
        ge=0,
        description="Price per million input tokens served from the provider's cache; empty means the input price.",
    )


class EvaluationSettings(ConfigModel):
    runs: int = Field(3, ge=1, description="How many times each evaluation case runs.")
    min_score: float = Field(0.9, ge=0, le=1, description="Pass rate a model needs to be approved for a tier.")


def _default_tiers() -> dict[str, TierSettings]:
    return {"routine": TierSettings(), "deep": TierSettings()}


def _default_tasks() -> dict[str, TaskSettings]:
    return {"notes": TaskSettings()}


class RateLimitSettings(ConfigModel):
    tries: int = Field(3, ge=1, le=6, description="How many times one account is tried when it says to slow down.")
    max_wait_seconds: float = Field(
        30, ge=0, le=300, description="The longest wait before trying again; a longer requested wait moves on."
    )
    pause_seconds: int = Field(
        600,
        ge=60,
        le=86400,
        description="How long an account is left alone, and its work waits or moves to the next account, when it keeps "
        "asking to slow down without saying for how long. A longer wait it asks for is used instead.",
    )


class RouteWhen(ConfigModel):
    task: str | None = Field(None, description="Only for this kind of work.")
    input_chars_over: int | None = Field(None, ge=0, description="Only when the input is longer than this.")
    quoted_messages_over: int | None = Field(
        None, ge=0, description="Only when the input quotes more earlier messages than this (long reply chains)."
    )
    data_level: Literal["open", "internal", "restricted"] | None = Field(
        None, description="Only for material at this data level."
    )


class RouteRule(ConfigModel):
    when: RouteWhen = Field(default_factory=RouteWhen, description="What the request must match; all given parts.")
    tier: str = Field("deep", description="The tier that does the work when the rule matches.")


class AiFile(FileModel):
    providers: dict[str, ProviderSettings] = Field(
        default_factory=dict, description="Every AI account this workspace may use (none until one is added)."
    )
    tiers: dict[str, TierSettings] = Field(default_factory=_default_tiers, description="What the work needs.")
    tasks: dict[str, TaskSettings] = Field(default_factory=_default_tasks, description="Tier and settings per task.")
    roles: Roles = Field(
        default_factory=Roles, description="Tiers by the role a kind of work plays: write, check or research."
    )
    budgets: Budgets = Field(default_factory=Budgets, description="Spending limits across all accounts.")
    prices: dict[str, Price] = Field(
        default_factory=dict, description="Prices by provider/model, for models whose provider doesn't publish them."
    )
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings, description="How models are compared.")
    catalog_refresh_hours: float = Field(
        24, ge=0, description="How often each account's model list and prices are fetched again from the provider."
    )
    rate_limits: RateLimitSettings = Field(
        default_factory=RateLimitSettings, description="Waiting and trying again when an account says to slow down."
    )
    routing: list[RouteRule] = Field(
        default_factory=list,
        description="Rules checked in order before a call that send some requests to another tier; first match wins.",
    )
    content_levels: dict[str, str] = Field(
        default_factory=dict,
        description="Kinds of material some accounts won't take, by id, each with what it covers. A project (or a "
        "plugin's record) is marked with the levels its material carries, and routing skips accounts that don't "
        "take them all.",
    )

    @model_validator(mode="after")
    def _tiers_name_real_accounts(self) -> AiFile:
        """A tier may be empty (no account yet), but never name an account or tier that doesn't exist."""
        problems = []
        for name, provider in self.providers.items():
            unknown = sorted(set(provider.content_levels or []) - set(self.content_levels))
            if unknown:
                problems.append(f"the account {name!r} takes content levels that aren't defined: {', '.join(unknown)}")
        for name, tier in self.tiers.items():
            for ref in ([tier.use] if tier.use else []) + tier.fallback:
                provider = ref.partition("/")[0]
                if provider not in self.providers:
                    problems.append(f"the {name!r} tier names {ref!r}, but there is no account {provider!r}")
            if tier.escalate_to and tier.escalate_to not in self.tiers:
                problems.append(f"the {name!r} tier escalates to {tier.escalate_to!r}, which isn't a tier")
        for index, rule in enumerate(self.routing):
            if rule.tier not in self.tiers:
                problems.append(f"routing rule {index + 1} names the tier {rule.tier!r}, which isn't a tier")
        for kind, task in self.tasks.items():
            if task.tier not in self.tiers:
                problems.append(f"the kind of work {kind!r} names the tier {task.tier!r}, which isn't a tier")
        for role in Roles.model_fields:
            tier = getattr(self.roles, role).tier
            if tier is not None and tier not in self.tiers:
                problems.append(f"the {role!r} role names the tier {tier!r}, which isn't a tier")
        if problems:
            raise ValueError("; ".join(problems))
        return self


# ---- config/dispatch.yaml --------------------------------------------------------------------------------------------


class CleaningSettings(ConfigModel):
    remove_quoted: bool = Field(True, description="Remove quoted earlier messages in email threads before AI calls.")
    signature_markers: list[str] = Field(
        default_factory=lambda: ["-- ", "Sent from my "],
        description="A line starting with one of these ends the message: the rest is a signature.",
    )
    remove_patterns: list[str] = Field(
        default_factory=lambda: [r"(?is)^(confidentiality notice|this e-?mail and any attachments).*"],
        description="Regular expressions for disclaimers and footers to remove.",
    )


class DispatchFile(FileModel):
    max_input_chars: int = Field(60000, ge=1000, description="The largest input sent in one call; longer ones split.")
    fix_rounds: int = Field(1, ge=0, le=3, description="How many times a failing answer goes back to the AI.")
    retries: int = Field(
        2,
        ge=0,
        le=5,
        description="How many times a run that gave no usable answer, or failed, is tried again by itself before it "
        "goes to you with why.",
    )
    retry_wait_seconds: int = Field(
        30,
        ge=1,
        le=3600,
        description="The wait before the first automatic retry; each later one waits twice as long as the one before.",
    )
    offline_check_seconds: int = Field(
        60,
        ge=5,
        le=3600,
        description="How long work that found no network connection waits before the assistant looks again. Being "
        "offline never uses up the automatic tries.",
    )
    offline_line_after_minutes: int = Field(
        60,
        ge=1,
        le=1440,
        description="How long work may wait for the network before Today asks you to check the connection. Most "
        "waits clear within minutes of opening the lid, so the default is an hour.",
    )
    cleaning: CleaningSettings = Field(default_factory=CleaningSettings, description="Input cleaning before AI calls.")


# ---- config/checks.yaml and config/language.yaml ---------------------------------------------------------------------

Severity = Literal["refuse", "return", "warn", "off"]


def _default_lints() -> dict[str, Severity]:
    return {
        "blocked-wording": "return",
        "run-on-list": "return",
        "near-duplicate-action": "warn",
        "evidence-fit": "return",
    }


class NearDuplicateActionTuning(ConfigModel):
    similarity: float = Field(
        0.8,
        ge=0,
        le=1,
        description="How alike a new action's words must be to an open or done action to count as a near-duplicate: "
        "0 flags any action that shares a word, 1 only one with the same words.",
    )


class LintTuning(ConfigModel):
    """Settings of the core lints that have more than a severity: one entry per lint, named as the lint is in `lints`
    with underscores for hyphens, so each setting has a plain dotted key and environment variable."""

    near_duplicate_action: NearDuplicateActionTuning = Field(
        default_factory=NearDuplicateActionTuning, description="Settings of the near-duplicate action check."
    )


class ChecksFile(FileModel):
    lints: dict[str, Severity] = Field(default_factory=_default_lints, description="How strict each soft check is.")
    projects: dict[str, dict[str, Severity]] = Field(
        default_factory=dict,
        description="Severities for one project's work, by project id then check, over the ones above (a rule "
        "switched off for one piece of work only).",
    )
    tuning: LintTuning = Field(
        default_factory=LintTuning, description="Settings of the soft checks that have more than a severity."
    )


DEFAULT_TITLE_SKIP = (
    r"(hi|hello|hey|dear|good (morning|afternoon|evening)|greetings)\b",
    r"(from|to|cc|bcc|sent|date|subject|reply-to)\s*:",
    r"(thanks|thank you|best|regards|cheers|sincerely)\b[ ,!.]*$",
    r"-{2,}|_{2,}|>",
)


class MessageSettings(ConfigModel):
    greeting: str = Field("Hi {first_name},", description="The first line of a copied message.")
    actions_heading: str = Field("Action items with you:", description="The line above someone's action items.")
    closing: str = Field("Thanks!", description="The last line of a copied message.")
    date_format: str = Field("%a, %b %d", description="How dates appear in messages (strftime codes).")
    date_time_format: str = Field(
        "%a, %b %d, %Y, %H:%M",
        description="How a date and time appear in the assistant's notes and other text it writes (strftime codes), "
        "in your time zone.",
    )


DEFAULT_SELF_WORDS = ("me", "myself", "I")


class ReportedSpeech(ConfigModel):
    verbs: list[str] = Field(
        default_factory=lambda: ["said", "says", "confirmed", "confirms", "told", "wrote", "writes", "asked", "wants"],
        description="Words that, after a name or other speaker, mark a note as repeating someone else's words: "
        '"<name> said ...". Matched as whole words, ignoring case.',
    )
    own_speakers: list[str] = Field(
        default_factory=lambda: ["I", "we"],
        description='Speakers that are the person themselves, so "I said" stays the person\'s own words.',
    )
    quote_min_words: int = Field(
        3,
        ge=1,
        le=50,
        description="Text in quotation marks with at least this many words is someone else's words.",
    )


class LanguageFile(FileModel):
    messages: MessageSettings = Field(default_factory=MessageSettings, description="Wording of copied messages.")
    self_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SELF_WORDS),
        description='The words the language uses for the person themselves ("assign it to me"). A name written as one '
        "of these means the person, whatever case it is in.",
    )
    blocked_phrases: list[str] = Field(
        default_factory=lambda: ["confirm", "check whether", "check if", "TBD?"],
        description="Wording not allowed in actions and shared text; actions say what to do.",
    )
    run_on_separators: list[str] = Field(
        default_factory=lambda: [" / ", "; "],
        description="Separators that mean several items were crammed in one line.",
    )
    never_shown: list[str] = Field(
        default_factory=list, description="Words that must never appear in anything people see (model names are added)."
    )
    title_skip: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TITLE_SKIP),
        description="Lines an item's title never comes from: greetings, quoted mail headers, sign-offs (regular "
        "expressions, matched at the start of a line, ignoring case). A title is taken from the first line left.",
    )
    reported_speech: ReportedSpeech = Field(
        default_factory=ReportedSpeech,
        description="How a typed note that repeats someone else's words is recognized. Such a note is content the "
        "person reports, whatever button it was typed on: facts and dates from it apply, but a rule or lesson from it "
        "waits for the person.",
    )
    bare_confirmation_words: int = Field(
        4,
        ge=1,
        le=20,
        description="A note typed on a button (Mark done, They finished it, Followed up, an answer) with fewer words "
        "than this and no link is a bare confirmation: it is kept with the change and not sent to the assistant. A "
        "longer note, or one with a link, is handed in as the person's own words.",
    )

    @field_validator("title_skip")
    @classmethod
    def _patterns_compile(cls, value: list[str]) -> list[str]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"{pattern!r} is not a regular expression: {exc}") from exc
        return value


# ---- config/ui.yaml -------------------------------------------------------------------------------------------------

DEFAULT_SHORTCUTS = {
    "next": "j",
    "previous": "k",
    "primary": "a",
    "send_back": "s",
    "copy": "c",
    "edit": "e",
    "undo": "u",
    "hand_in": "n",
    "help": "?",
    "ask": "/",
    "next_pane": "]",
    "previous_pane": "[",
}


class TodaySettings(ConfigModel):
    mail_hours: int = Field(
        24, ge=1, le=336, description="How far back, in hours, Today's list of what came in reaches."
    )
    mail_max: int = Field(50, ge=1, le=500, description="The most messages Today lists at once.")
    agenda_days_ahead: int = Field(
        1, ge=0, le=14, description="How many days after today the agenda also shows (0: today only)."
    )


class FollowupsSettings(ConfigModel):
    action_due_within_days: int = Field(
        7,
        ge=0,
        le=365,
        description="Something sent to a person about an action is chased only when the action's own due date is this "
        "many days away or less, or already past. An action on hold is never chased.",
    )
    undated_after_days: int = Field(
        14,
        ge=1,
        le=365,
        description="An action with no due date is chased once this many days have passed since the person was told "
        "with no word back.",
    )
    question_after_days: int = Field(
        4,
        ge=1,
        le=365,
        description="A question sent to a person is chased once this many days have passed with no reply. A dated "
        "action is also chased only after this many days with no word.",
    )


class BrandSettings(ConfigModel):
    color: str | None = Field(
        None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="The accent color for buttons, links and the selected view, as #rrggbb. Lighter and darker shades "
        "are worked out from it; Settings warns when its contrast would fail. Empty uses the app's indigo.",
    )
    logo: str | None = Field(
        None,
        description="An image shown in place of the monogram at the top left: a PNG, JPEG, WebP or SVG file in the "
        "workspace's config folder, by name. Empty shows the workspace's initials.",
    )

    @field_validator("logo")
    @classmethod
    def _logo_file(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "/" in value or "\\" in value or value.startswith(".") or not value.strip():
            raise ValueError("the logo is a file name in the config folder, with no folder in it")
        if not value.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
            raise ValueError("the logo is a .png, .jpg, .jpeg, .webp or .svg file")
        return value


class UiFile(FileModel):
    wording: dict[str, str] = Field(
        default_factory=dict,
        description="Overrides for the UI's wording sheet, by key (by key, from the screens' wording sheet).",
    )
    shortcuts: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_SHORTCUTS),
        description="Single-key shortcuts by action; they never fire while typing.",
    )
    narrow_below_px: int = Field(
        640,
        ge=320,
        le=1200,
        description="Below this width the screen uses the phone layout: one pane and a bottom bar.",
    )
    toast_seconds: float = Field(7, ge=0, description="How long an undo toast stays; 0 keeps toasts until dismissed.")
    feedback_to: str | None = Field(
        None,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="The address the feedback button writes its email to. Empty uses the address the app was "
        "packaged with, if any; with neither, feedback is drafted to copy.",
    )
    today: TodaySettings = Field(
        default_factory=TodaySettings, description="What Today's agenda and its list of what came in cover."
    )
    followups: FollowupsSettings = Field(
        default_factory=FollowupsSettings,
        description="When something sent to a person is due a follow-up, which Today and Follow-ups both use.",
    )
    brand: BrandSettings = Field(default_factory=BrandSettings, description="The accent color and logo.")
    theme: Literal["system", "light", "dark"] = Field(
        "system",
        description="Light or dark screens; system follows the computer's setting. Each person can change it for "
        "their own device from the menu under their initials.",
    )
    density: Literal["comfortable", "compact"] = Field(
        "comfortable",
        description="How much fits on screen: comfortable rows, or compact ones that show more at once. Each person "
        "can change it for their own device; touch screens keep large targets either way.",
    )

    @field_validator("shortcuts")
    @classmethod
    def _known_shortcuts(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(value) - set(DEFAULT_SHORTCUTS))
        if unknown:
            raise ValueError(f"unknown shortcut actions {unknown}; known: {sorted(DEFAULT_SHORTCUTS)}")
        if any(len(k) != 1 for k in value.values()):
            raise ValueError("each shortcut is a single key")
        merged = {**DEFAULT_SHORTCUTS, **value}
        if len(set(merged.values())) != len(merged):
            raise ValueError("two actions share a shortcut key")
        return merged


# ---- config/stages.yaml ---------------------------------------------------------------------------------------------


class StageDefinition(ConfigModel):
    """One stage in a record type's steps, as a plugin's default or in the workspace's stages.yaml."""

    id: str = Field("", min_length=1, description="Stable stage identifier, unique within this record type.")
    label: str = Field(
        "", min_length=1, description="Editable wording for this stage; changing it does not change stored data."
    )
    description: str = Field(
        "", description="What being in this stage means, in plain words, shown beside the stage on screen."
    )
    entry: list[str] = Field(
        default_factory=list, description="Deterministic check or standing rule ids required on entry."
    )
    starts: list[str] = Field(
        default_factory=list, description="Task kinds requested on entry, waiting for the person's go."
    )
    applies_if: list[str] = Field(
        default_factory=list,
        description="Check or standing rule ids that must all pass for this stage to apply to a record; moves pass "
        "over a stage that doesn't apply, so a check here needn't also be an entry check. Empty: it applies to every "
        "record.",
    )


class TypeStages(ConfigModel):
    moves: Literal["person", "rule"] | None = Field(None, description="Override the workspace move mode for this type.")
    stages: list[StageDefinition] | None = Field(
        None, description="Ordered stages; leave out to keep the pack's stages, or give an empty list to remove them."
    )

    @model_validator(mode="before")
    @classmethod
    def list_form(cls, value):
        return {"stages": value} if isinstance(value, list) else value

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [stage.id for stage in self.stages or []]
        if len(ids) != len(set(ids)):
            raise ValueError("stage ids must be unique within a record type")
        return self


STAGE_WORDING = {
    "record_missing": "That item no longer exists.",
    "record_changed": "That item changed since you opened it. Look again, then move it.",
    "stage_unknown": "There is no stage called {stage} for this item.",
    "stage_same": "It is already in that stage.",
    "stage_skip": "Move it one stage at a time, so each stage's checks run.",
    "stage_not_applicable": "That stage doesn't apply to this item.",
    "person_required": "This move needs you.",
    "check_unavailable_rule": "Every stage after the first needs an entry check when rules move items.",
    "not_waiting": "this stage task is not waiting for approval",
    "request_changed": "the request changed since it was read",
    "stage_left": "the record is no longer in the stage that requested this task",
    "stage_left_before_go": "Not started: it left this stage before you gave the go.",
    "retry_blocked": "stage tasks need an explicit go before they can run",
    "type_unavailable": "The record type plugin is disabled.",
    "check_unavailable": "The entry check is unavailable.",
    "check_access": "The entry check cannot read this record type.",
    "check_failed": "The entry check failed to run.",
    "rule_inactive": "The standing rule is not active.",
    "rule_scope": "The record is outside this rule's scope.",
    "rule_prose": "This rule needs a deterministic code check before it can allow a move.",
    "confirm": "This stage move waits for you to confirm it.",
    "waiting": "Waiting for your go before starting this task.",
}


class StagesFile(FileModel):
    wording: dict[str, str] = Field(
        default_factory=lambda: dict(STAGE_WORDING),
        description="Stage explanations by key; workspace values override the default wording.",
    )
    moves: Literal["person", "rule"] = Field(
        "person", description="Who advances records: the person, or deterministic rules."
    )
    types: dict[str, TypeStages] = Field(
        default_factory=dict, description="Stages by record type; each supplied list replaces pack defaults."
    )

    @model_validator(mode="before")
    @classmethod
    def record_type_keys(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        types = dict(value.get("types", {}))
        for key in set(value) - {"version", "moves", "types", "wording"}:
            if key in types:
                raise ValueError(f"record type {key} is configured twice")
            types[key] = value.pop(key)
        value["types"] = types
        return value


# ---- config/rules.yaml ----------------------------------------------------------------------------------------------


class RuleScope(ConfigModel):
    task_kinds: list[str] = Field(
        default_factory=list, description="Task kinds this standing rule applies to; empty means all."
    )
    records: list[str] = Field(
        default_factory=list, description="Record types or type.field targets of this standing rule."
    )
    filter: dict[str, object] = Field(
        default_factory=dict, description="Exact field values narrowing the rule's record targets."
    )


class StandingRule(ConfigModel):
    id: str = Field("", min_length=1, description="Stable standing rule identifier.")
    text: str = Field("", description="The person's wording of the rule, used as its explanation.")
    applies_to: RuleScope = Field(default_factory=RuleScope, description="The structured target of this rule.")
    source: str | None = Field(None, description="Request or other provenance for this rule.")
    added: date | None = Field(None, description="Date this rule was added, in ISO form.")
    status: Literal["active", "retired", "promoted"] = Field(
        "active", description="Whether the standing rule is active."
    )
    check: str | None = Field(
        None,
        description="Optional deterministic code check implementing this rule; prose alone cannot pass a stage gate.",
    )


class RulesFile(FileModel):
    rules: list[StandingRule] = Field(
        default_factory=list, description="Standing instructions, identified separately for overrides and retirement."
    )

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        return self


# ---- registry --------------------------------------------------------------------------------------------------------

#: Config file name (without .yaml) to its model, in the order `config show` lists them.
# ---- config/watch.yaml ----------------------------------------------------------------------------------------------


class WatchSource(ConfigModel):
    id: str = Field(
        "", pattern=r"^[a-z0-9][a-z0-9-]*$", description="The source's short name: lowercase letters, digits, dashes."
    )
    connector: str = Field(
        "", min_length=1, description='What reads it: a core connector ("folder") or a plugin\'s ("<plugin>/<name>").'
    )
    label: str = Field("", description="What to call it on screen.")
    enabled: bool = Field(True, description="Off keeps its history and stops reading it.")
    every_minutes: int = Field(60, ge=5, description="How often it is read while the app runs.")
    project: str | None = Field(None, description="The project its changes are about, if they all are.")
    first_run: Literal["baseline", "recent", "all"] = Field(
        "baseline",
        description="baseline: the first read only notes what is there; recent: it also hands in what arrived, "
        "changed or happens within first_run_hours of the read (the last day's mail, today's meetings); all: "
        "everything there is handed in as new.",
    )
    first_run_hours: int = Field(
        24, ge=1, le=336, description="With first_run recent: how many hours around the first read count as recent."
    )
    report_removed: bool = Field(True, description="Hand in an item that disappeared from the source.")
    data_level: Literal["open", "internal", "restricted"] | None = Field(
        None,
        description="How sensitive what this source holds is: its items go only to AI accounts allowed this level. "
        "Empty: the level set for its kind of source, else the default for all sources.",
    )
    settings: dict[str, Any] = Field(
        default_factory=dict, description="The connector's own settings (a folder's path, say), checked by it."
    )


class TriageRule(ConfigModel):
    name: str = Field("", min_length=1, description="What the rule is called, shown with what it closed.")
    kind: str = Field(
        "",
        min_length=1,
        description="The matcher: cosmetic, by-us, terms-absent, name-matches, bulk-mail, service-category, "
        'sender-rule, or a plugin\'s ("<plugin>/<name>").',
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="The matcher's settings (terms, patterns, senders, domains, categories)."
    )
    why: str = Field("", description="What the person reads; {reason} is the matcher's own words. Empty: just those.")
    sources: list[str] = Field(default_factory=list, description="The sources it applies to; empty: all of them.")
    set_aside: Literal["personal", "sales", "never"] | None = Field(
        None,
        description="With a match, put mail in the Set aside folder (personal, or sales and promotions) instead of "
        "plainly closing it; never keeps the mail with the assistant, over any set-aside rule after it and over the "
        "built-in sorting. Empty: the rule closes the change as usual.",
    )


class WatchFile(FileModel):
    sources: list[WatchSource] = Field(default_factory=list, description="The places the assistant keeps reading.")
    triage: list[TriageRule] = Field(
        default_factory=list,
        description="Rules, in order, that close a watched change before the assistant reads it; the first match wins.",
    )
    set_aside_defaults: bool = Field(
        True,
        description="Set aside mail the mail itself says is not work, with no AI run: mailing lists and bulk mail, and "
        "mail the mail service files under promotions, social or forums. It applies after the rules above, so a rule "
        "that keeps mail from a sender wins.",
    )
    sorting: Literal["ai", "rules"] = Field(
        "ai",
        description="How mail that none of the rules above place is sorted. ai: one small, low-cost run reads only "
        "each message's sender, subject line and the mail service's category (never the text) and says work, "
        "personal or sales; unsure counts as work, so nothing is hidden on a guess. rules: no run; only the rules "
        "set mail aside.",
    )
    sorting_batch: int = Field(
        25,
        ge=1,
        le=100,
        description="How many messages one sorting run covers: the unsorted mail of a read goes in groups of this "
        "size, one run for each group.",
    )
    set_aside_keep_seconds: int = Field(
        60,
        ge=0,
        description="After you confirm set-aside mail is not work for you, how long the app keeps its copy so Undo can "
        "bring it back; then the copy is deleted from the app (it stays in your mailbox). 0 deletes at once.",
    )
    public_mail_domains_extra: list[str] = Field(
        default_factory=list,
        description="Mail domains anyone can have an address at, added to the ones the app already knows. No sorting "
        "rule is offered for a whole domain listed here or known to the app; a rule for one sender still is.",
    )
    failures_before_asking: int = Field(
        3,
        ge=1,
        description="Failed reads in a row before the person is asked about a source; one question, not one per read.",
    )
    default_data_level: Literal["open", "internal", "restricted"] = Field(
        "internal",
        description="How sensitive what a watched source holds is, when the source and its kind say nothing.",
    )
    connector_data_levels: dict[str, Literal["open", "internal", "restricted"]] = Field(
        default_factory=dict,
        description="The data level for each kind of source (by its connector name), for sources that set none.",
    )

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        return self


FILES: dict[str, type[FileModel]] = {
    "workspace": WorkspaceFile,
    "server": ServerFile,
    "storage": StorageFile,
    "ai": AiFile,
    "dispatch": DispatchFile,
    "checks": ChecksFile,
    "language": LanguageFile,
    "ui": UiFile,
    "stages": StagesFile,
    "rules": RulesFile,
    "watch": WatchFile,
}

#: The newest version each file format has reached.
CURRENT_VERSIONS: dict[str, int] = {name: 1 for name in FILES}
