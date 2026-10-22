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

from engine.due_phrases import (
    DEFAULT_BEFORE_WORDS,
    DEFAULT_CONDITION_WORDS,
    DEFAULT_HOLD_WORDS,
    DEFAULT_LEAD_WORDS,
    DEFAULT_ORDINAL_SUFFIXES,
    DEFAULT_TASK_VERBS,
)
from engine.endings import (
    DEFAULT_CALLED_OFF_WORDS,
    DEFAULT_CLOSED_WORDS,
    DEFAULT_DELIVERY_WORDS,
    DEFAULT_MEETING_WORDS,
)
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
        json_schema_extra={"choices": "people"},
    )
    timezone: str = Field(
        "UTC",
        description="The time zone your own dates and times are read and shown in: pick the city nearest you.",
        json_schema_extra={"choices": "time_zones"},
    )
    accounts: list[str] = Field(
        default_factory=list,
        description="The names you sign in or edit under on watched sources, so a change made under one reads as your "
        "own work. The app's own names go under our accounts, which are kept apart from these.",
    )


class ProjectSettings(ConfigModel):
    summary_max_lines: int = Field(
        3,
        ge=1,
        le=50,
        description="The most lines a project's summary may have. A summary says where the project stands; what was "
        "found goes to facts, and a longer one is returned to the assistant to shorten.",
    )
    completed_status: str = Field(
        "Done",
        description="The project status that means a project is finished. Projects with it are listed under "
        "Completed at the bottom of the projects list, with everything about them kept; nothing is removed.",
        json_schema_extra={"choices": "project_status"},
    )
    personal: str | None = Field(
        None,
        description="The project that holds the person's own life (family, home, friends): what names only people on "
        "the personal side, and, while no business is set, everything filed under no project, goes there. Made when "
        "the workspace is set up; empty means none, and items stay unfiled.",
        json_schema_extra={"choices": "projects"},
    )
    business: str | None = Field(
        None,
        description="The top project of the person's business or job, when they have one: what names only people on "
        "the business side is filed under it, and what can't be placed asks which side it belongs to. Empty means "
        "no business, and everything unplaced goes to the personal project.",
        json_schema_extra={"choices": "projects"},
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
        json_schema_extra={"advanced": True},
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
        json_schema_extra={"advanced": True},
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
        json_schema_extra={"choices": "owner_formats"},
    )
    language: str = Field(
        "en-US",
        pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
        description="Which kind of English the assistant writes in for you: its spelling, punctuation and dates. The "
        "app's own screens stay in English. A project may set its own.",
        json_schema_extra={"choices": "languages"},
    )
    project: ProjectSettings = Field(default_factory=ProjectSettings, description="How a project's own record is kept.")
    plugins: PluginSettings = Field(default_factory=PluginSettings, description="Which plugins run in this workspace.")
    contact_kinds: list[str] = Field(
        default_factory=lambda: ["email", "phone", "address"],
        description="The kinds of contact detail a person's record can hold, such as email or phone. A detail the "
        "assistant finds in a signature is offered under one of these, and the person picks from them when adding "
        "someone.",
    )
    phone_min_digits: int = Field(
        7,
        ge=3,
        le=15,
        description="The fewest digits a run of digits, spaces, dashes, dots and brackets in a mail signature needs to "
        "be offered as the sender's phone number (a leading plus sign is allowed). A shorter run is a year, a room or "
        "a house number, not a number to call.",
    )
    our_accounts: list[str] = Field(
        default_factory=list,
        description="The names this app uses on watched sources, so changes the app published read as ours. Your own "
        "names go under your accounts, which are kept apart from these.",
    )
    demo: bool = Field(
        False,
        description="Made-up example data: every screen says so, so nobody mistakes it for real work.",
    )

    @field_validator("contact_kinds")
    @classmethod
    def _kinds_are_words(cls, value: list[str]) -> list[str]:
        kinds = [" ".join(k.split()) for k in value]
        if any(not k for k in kinds):
            raise ValueError("a kind of contact detail can't be blank")
        if len({k.casefold() for k in kinds}) != len(kinds):
            raise ValueError("each kind of contact detail is listed once")
        return kinds

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
        json_schema_extra={"advanced": True},
    )
    host: str = Field("127.0.0.1", description="Address to listen on.", json_schema_extra={"advanced": True})
    port: int = Field(8765, ge=1, le=65535, description="Port to listen on.", json_schema_extra={"advanced": True})
    base_path: str = Field(
        "/",
        description="Path the app is served under, e.g. /admin. Every route and link uses it.",
        json_schema_extra={"advanced": True},
    )
    public_url: str | None = Field(
        None,
        description="The address people use to reach the app. Required when hosted.",
        json_schema_extra={"advanced": True},
    )
    open_browser: bool = Field(
        False,
        description="Open the app in this computer's browser when it starts (local mode only).",
        json_schema_extra={"advanced": True},
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


class CloudFolder(ConfigModel):
    name: str = Field("", description="What the cloud drive is called on screen.")
    macos: list[str] = Field(
        default_factory=list,
        description="Where its folder is on a Mac, as places inside the home folder; a * matches any characters in a "
        "name. The first place that exists is used.",
    )
    windows: list[str] = Field(
        default_factory=list, description="Where its folder is on Windows, in the same form as for a Mac."
    )
    linux: list[str] = Field(
        default_factory=list, description="Where its folder is on Linux, in the same form as for a Mac."
    )


def shipped_cloud_folders() -> list[CloudFolder]:
    """The cloud drives the app looks for unless the workspace lists its own (the app's shipped list)."""
    from engine.cloud_folders import shipped

    return shipped()


class BackupSettings(ConfigModel):
    automatic: bool = Field(
        True,
        description="Make backups on schedule while the app runs, with nothing to click; off means only on request.",
    )
    targets: list[BackupTarget] = Field(default_factory=list, description="Where full backups go. Use at least one.")
    cloud_folders: list[CloudFolder] = Field(
        default_factory=shipped_cloud_folders,
        description="The cloud drives the setup guide looks for on this computer and offers for backups, in the order "
        "they are offered. The first one found is recommended.",
    )
    cloud_path: list[str] = Field(
        default_factory=lambda: ["Backups", "PM Cockpit"],
        description="The folders, one inside the next, that the guide makes inside a cloud drive for backups. They are "
        "shown to the person by name, joined with arrows.",
    )
    every_hours: int = Field(
        24, ge=1, description="How often a full backup is made.", json_schema_extra={"enabled_by": "automatic"}
    )
    keep: int = Field(14, ge=1, description="How many backups to keep in each target.")
    encrypt: str = Field(
        "",
        description=SecretHint(
            "Where the key that encrypts every backup copy is kept, as a reference (env:NAME or file:/path), never the "
            "key itself. Empty: backups aren't encrypted. A lost key means a backup that can't be read: keep the key "
            "somewhere other than the backup folder, and restoring asks for it."
        ),
        json_schema_extra={"advanced": True},
    )
    retry_minutes: int = Field(
        60,
        ge=5,
        description="After a failed backup (a drive not connected, say), how long before trying again.",
        json_schema_extra={"enabled_by": "automatic"},
    )

    @field_validator("encrypt")
    @classmethod
    def _key_reference(cls, value: str) -> str:
        if value and not value.startswith(("env:", "file:")):
            raise ValueError("the key is named as a reference to where it is kept, never the key itself")
        return value


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
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ],
        description="The kinds of file that may be added; a file kind can narrow this further.",
        json_schema_extra={"choices": "media_types"},
    )
    read_max_mb: float = Field(
        25,
        gt=0,
        description="The largest file whose text is read, in megabytes. A larger attachment or watched file is named "
        "as not read.",
    )
    read_max_chars: int = Field(
        30000,
        ge=1000,
        description="The most text taken from one file. A file with more is cut there, with a mark saying so.",
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


class KeptSecretSettings(ConfigModel):
    keep_days: int = Field(
        30,
        ge=1,
        le=3650,
        description="How many days an old password or key that nothing refers to any more is kept on this computer "
        "before it is removed (after one is replaced, the old one is kept so Undo works). Backup keys are never "
        "removed, because older backups need them.",
    )
    undo_grace_minutes: int = Field(
        10,
        ge=0,
        le=1440,
        description="How many minutes after a change a password or key it stopped using stays on this computer, so "
        "Undo can bring it back. Removing a source or an account removes the passwords and keys kept for it when this "
        "time has passed; 0 removes them at once.",
    )


class StorageFile(FileModel):
    backend: Literal["sqlite"] = Field("sqlite", description="Where records live. Postgres comes later.")
    export: ExportSettings = Field(default_factory=ExportSettings, description="The readable export and its history.")
    backups: BackupSettings = Field(default_factory=BackupSettings, description="Full backups to somewhere else.")
    files: FileLimits = Field(default_factory=FileLimits, description="Limits on files people and programs add.")
    sync: SyncSettings = Field(
        default_factory=SyncSettings, description="Handing the workspace between computers through a synced folder."
    )
    kept_secrets: KeptSecretSettings = Field(
        default_factory=KeptSecretSettings, description="How long passwords and keys typed on a screen are kept."
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
    unsupported: list[str] = Field(
        default_factory=list,
        description="Patterns in the error stream meaning: the service no longer lets this program be used with this "
        "kind of account, so signing in again does not help. The account is told to pick another or use a key.",
    )
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
    no_work: list[str] = Field(
        default_factory=list,
        description="Patterns in the error stream meaning: the program ran but did no work (it only printed a banner "
        "or a sign-in prompt, or was cut off). Such a run is no try and is never sent back as a mistake. A run that "
        "fails with nothing at all on its error stream counts the same.",
    )
    exit_codes: dict[int, Literal["auth", "unsupported", "rate_limited", "quota", "provider_down", "no_work"]] = Field(
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
    effort_option: list[str] = Field(
        default_factory=list,
        description="The arguments added to the command when the tier's work has an effort (low, medium or high), "
        "with {effort} replaced by it, such as an option name followed by {effort}. Empty: the program has no such "
        "option, or it isn't confirmed for it, and the effort is never passed on.",
    )
    system_option: list[str] = Field(
        default_factory=list,
        description="The arguments that give the program its system instructions from a file, with {system} replaced "
        "by the file's path, such as an option name followed by {system}. Set: the task's instructions and the stable "
        "part of its packet go in that file, in place of the program's own default instructions, and only the request "
        "is sent as the packet. Empty: everything is sent as the packet.",
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
    version_command: list[str] = Field(
        default_factory=list,
        description="The program and arguments that print the agent's version, so a report can say which version "
        "ran. Empty: the agent's program with --version.",
    )
    version_timeout_seconds: float = Field(
        10, gt=0, description="How long the agent's version check may take before the version is left unknown."
    )
    identity_command: list[str] = Field(
        default_factory=list,
        description="The program and arguments that print which account the agent is signed in as, so Settings can "
        "say whose sign-in it runs as and Today can ask when that changes. Empty: the program has no way to say, and "
        "the account shows that it can't tell.",
    )
    identity_field: str = Field(
        "",
        description="When the identity command prints JSON: the dotted path to the account in it. Empty: the output is "
        "read by line.",
    )
    identity_line: int = Field(
        1, ge=1, description="Without identity_field: the line of the output that holds the account, counting from 1."
    )
    identity_pattern: str = Field(
        "",
        description="A regular expression whose first group is the account within that line. Empty: the whole line.",
    )
    identity_timeout_seconds: float = Field(
        10, gt=0, description="How long the identity command may take before the sign-in is left unknown."
    )
    identity_recheck_seconds: float = Field(
        600,
        ge=0,
        description="How long a sign-in read stays current when runs look for a change: a run reads it again only "
        "after this many seconds. Zero reads it before every run.",
    )


class ProviderSettings(ConfigModel):
    adapter: str = Field("stub", description="Which installed adapter talks to this account.")
    label: str = Field(
        "",
        description="The name the person gave this account, shown in lists and messages. Empty: the screens use the "
        'service\'s name followed by "account".',
    )
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
    work_data: Literal["", "not_now"] = Field(
        "",
        description="What the person answered when asked whether this account may read their work mail and notes: "
        "not_now keeps asking on Today until they allow it; empty means they were not asked here, or allowed it.",
    )
    content_levels: list[str] | None = Field(
        None,
        description="The content levels this account takes (those defined for AI); unset means it takes every level.",
    )
    identity_level: list[DataLevel] | None = Field(
        None,
        description="For a command-line agent: the data levels the sign-in it runs as may see, such as a personal "
        "sign-in set for open and internal material only. Work above them waits for you, even where the account is "
        "allowed more. Unset: the sign-in adds no limit of its own.",
    )
    timeout_seconds: int = Field(90, ge=5, description="How long to wait for an answer.")
    json_mode: bool = Field(True, description="Ask the provider for JSON output when it supports that.")
    send_temperature: bool = Field(
        True,
        description="Send each kind of work's temperature with the request. Off for a service whose current models "
        "refuse any temperature they don't set themselves; the model then uses its own.",
    )
    max_tokens_param: str = Field(
        "max_tokens",
        description="The request setting this service takes the most tokens an answer may have in. Some services "
        "refuse the older name on their newer models and want max_completion_tokens instead.",
    )
    auth_reasons: list[str] = Field(
        default_factory=list,
        description="Reason codes in an error answer's details (never its wording) that mean the service refused the "
        "key, for a service that answers a refused key with a status that also means any other bad request. Empty: "
        "the status alone says whether the key was refused.",
    )
    key_refused_status_on_models: list[int] = Field(
        default_factory=list,
        description="Statuses that, on the request for the service's model list (which takes no arguments, so it can "
        "only be about the key), mean the key was refused, for a service that answers a refused key with a status "
        "that also means any other bad request. The same status on a request for work is not read this way. Empty: "
        "the status alone says whether the key was refused.",
    )
    model_list_pages: int = Field(
        10,
        ge=1,
        le=100,
        description="The most pages of a service's model list that are read when it says there are more, so a long "
        "list is read in full but a service that never stops paging can't keep the request going.",
    )
    effort_param: str = Field(
        "",
        description="The request setting this service takes the effort of a tier's work in (low, medium or high), "
        "such as reasoning_effort. Empty: the service has no such setting, or it isn't confirmed for it, and the "
        "effort is never sent.",
    )
    thinking_room: int = Field(
        8000,
        ge=0,
        description="Tokens added to a kind of work's most output for a model this service says thinks on its own, "
        "because that thinking is counted in the answer's limit and can use it up before the answer starts. The limit "
        "never goes past what the model allows. Zero adds none; it applies only to a service that lists what each "
        "model can do.",
    )
    agent: AgentSettings | None = Field(
        None, description="For a command-line agent account: how to start it, pass the packet and read its answer."
    )
    credential_expires: date | None = Field(
        None,
        description="The day this account's key stops working, when the service gives one. Today says so ahead of "
        "that day (see how many days ahead in the AI settings), naming every place the same key is used. Empty: "
        "the key has no known end.",
    )
    accepted_unchecked: bool = Field(
        False,
        description="Accept this account as a fallback for a kind of work without its connection check. An account "
        "that stands in for another is a switch nobody chose in the moment, so only a checked account may do it "
        "unless you accept it here.",
    )


class TierSettings(ConfigModel):
    use: str = Field(
        "", description="provider/model short name that does this tier's work; empty means no account is set up yet."
    )
    fallback: list[str] = Field(default_factory=list, description="Tried in order when the main one can't serve.")
    escalate_to: str | None = Field(
        None,
        description="A stronger tier to retry on when checks keep failing.",
        json_schema_extra={"screen_edit": True},
    )
    effort: Literal["low", "medium", "high"] | None = Field(
        None,
        description="How much thinking this tier's work asks of the model (low, medium or high). It is passed on only "
        "to an account that says how (effort_param, or the agent's effort_option); empty: the model's own default.",
    )
    thinking: Literal["default", "off"] = Field(
        "default",
        description="Whether this tier's work lets the model think as it would by itself (default) or asks it not to "
        "(off). Off is applied only to a model the account's service says can do without thinking at this tier's "
        "effort; for any other the connection test says why it wasn't.",
    )


class TaskSettings(ConfigModel):
    tier: str = Field(
        "routine", description="Which tier this kind of work uses.", json_schema_extra={"screen_edit": True}
    )
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
        None,
        description="The tier for every kind of work in this role, unless tasks.<kind>.tier says otherwise.",
        json_schema_extra={"choices": "tiers"},
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
        None, ge=0, description="Stop starting new work of this kind for the day above this total."
    )
    per_month_usd: float | None = Field(
        None, ge=0, description="Stop starting new work of this kind for the month above this total."
    )


class Budgets(ConfigModel):
    per_run_usd: float = Field(
        0.25, ge=0, description="Never start one piece of work estimated to cost more than this."
    )
    confirm_unpriced: bool = Field(
        False,
        description="Ask me before starting work whose cost can't be estimated (an account with no prices, such as a "
        "subscription), too.",
        json_schema_extra={"advanced": True},
    )
    first_go: bool = Field(
        True,
        description="Until you start the assistant for the first time in a workspace, its work waits. Today shows one "
        "line with how many items are waiting and about what they cost, and one Go starts them all. After that, the "
        "amount to ask above applies.",
    )
    confirm_above_usd: float = Field(
        0.10,
        ge=0,
        description="Ask me before starting work estimated to cost more than this; below it, work starts on its own.",
    )
    per_task: dict[str, TaskBudget] = Field(
        default_factory=dict, description="Limits for one kind of work, on top of the overall ones."
    )
    per_day_usd: float = Field(2.0, ge=0, description="Stop starting new work for the day above this total.")
    per_month_usd: float = Field(30.0, ge=0, description="Stop starting new work for the month above this total.")
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
    extra_allowance: float = Field(
        1.0,
        ge=0,
        le=20,
        description="How much an evaluation run may do beyond what its case expects and still pass. A fact the case "
        "didn't expect costs nothing, any other extra change that stays with the person costs 0.5, and anything that "
        "reaches another person fails the run whatever this is. A run passes while its extras together cost no "
        "more than this; 0 means no extra change at all, as before.",
    )


class SkillSettings(ConfigModel):
    min_score: float = Field(
        0.8,
        ge=0,
        le=1,
        description="The share of runs a model must get right for a skill before it counts as able to do that work. "
        "Skills below it are marked in the accounts list.",
    )
    stale_days: int = Field(
        60,
        ge=1,
        le=3650,
        description="How many days a measurement of what a model can do is trusted. After that it is shown as out "
        "of date and counts as unknown until it is measured again.",
    )


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
    tasks: dict[str, TaskSettings] = Field(
        default_factory=_default_tasks,
        description="Tier and settings per task.",
        json_schema_extra={"new_entries": True},
    )
    roles: Roles = Field(
        default_factory=Roles, description="Tiers by the role a kind of work plays: write, check or research."
    )
    budgets: Budgets = Field(default_factory=Budgets, description="Spending limits across all accounts.")
    prices: dict[str, Price] = Field(
        default_factory=dict, description="Prices by provider/model, for models whose provider doesn't publish them."
    )
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings, description="How models are compared.")
    skills: SkillSettings = Field(
        default_factory=SkillSettings, description="How measurements of what each model can do are judged."
    )
    catalog_refresh_hours: float = Field(
        24, ge=0, description="How often each account's model list and prices are fetched again from the provider."
    )
    rate_limits: RateLimitSettings = Field(
        default_factory=RateLimitSettings, description="Waiting and trying again when an account says to slow down."
    )
    routing: list[RouteRule] = Field(
        default_factory=list,
        description="Rules checked in order before a call that send some requests to another tier; first match wins.",
        json_schema_extra={"screen_edit": True},
    )
    borrow_other_tier: Literal["ask", "never"] = Field(
        "ask",
        description="When every account a kind of work can use is waiting for its usage limit to reset and an account "
        "set up for another kind of work is free: ask means Today asks whether to use it until the reset (nothing "
        "is borrowed without a yes); never means the work always waits.",
    )
    credential_warn_days: int = Field(
        7,
        ge=0,
        le=365,
        description="How many days before a key or sign-in with a known end date stops working Today says so, naming "
        "everywhere the same key is used.",
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


class RefusalsToPacketSettings(ConfigModel):
    share: float = Field(
        0.05,
        ge=0,
        le=1,
        description="When a check refused at least this share of a kind of work's recent runs, its fuller guidance is "
        "added to that kind of work's packets. It leaves again once the share drops below it.",
    )
    of_last: int = Field(
        50,
        ge=1,
        le=1000,
        description="How many of a kind of work's most recent runs are counted when working out which checks refuse "
        "it often.",
    )
    min_runs: int = Field(
        10,
        ge=1,
        le=1000,
        description="How many recent runs of a kind of work must be counted before any check's guidance is added to "
        "its packets, so a few early refusals don't decide it.",
    )
    floor: int = Field(
        3,
        ge=1,
        le=1000,
        description="How many times within the floor window the same check may refuse a kind of work before its fuller "
        "guidance is added to that kind of work's packets, whatever the share and however few runs there have been, "
        "so rare work isn't left out because it never reaches the minimum.",
    )
    floor_days: int = Field(
        7, ge=1, le=365, description="How many days back the floor counts the same check's refusals of a kind of work."
    )


class KnowledgeSettings(ConfigModel):
    glossary_all_below: int = Field(
        150,
        ge=0,
        le=5000,
        description="The whole glossary goes in every packet while it has fewer terms than this; past it, only the "
        "terms an input uses.",
    )
    facts_budget: int = Field(
        4000,
        ge=0,
        le=100000,
        description="Characters of ranked facts per input. The rest are counted, said in the packet, and searchable.",
    )
    routing_match: float = Field(
        0.67,
        gt=0,
        le=1,
        description="How much of a routing entry's topic an input's words must share for the entry to go with it, "
        'compared word by word with plurals folded ("reviewers" matches "reviewer"). 1 means every word.',
    )
    stable_budget: int = Field(
        8000,
        ge=500,
        le=200000,
        description="Characters of standing rules, lessons and glossary sent with every run. Past it, the narrowest "
        "rules move to the part sent only to the runs they cover. Every run logs the size, so this can be set from "
        "real numbers.",
    )
    search_rounds: int = Field(
        2, ge=0, le=5, description="How many times a run may ask to search the workspace before it must answer."
    )
    search_results: int = Field(20, ge=1, le=200, description="Results returned for each search a run asks for.")
    refusals_to_packet: RefusalsToPacketSettings = Field(
        default_factory=RefusalsToPacketSettings,
        description="When a check that always refuses keeps refusing a kind of work, its fuller guidance joins that "
        "kind of work's packets.",
    )
    rule_review_days: int = Field(
        30,
        ge=1,
        le=730,
        description="How many days a standing rule may be given to runs without ever applying before it is offered "
        "for review. Keeping it starts the count again.",
    )
    rule_review_every_days: int = Field(
        7,
        ge=1,
        le=365,
        description="How many days must pass after you act on the review of standing rules before Today offers it "
        "again.",
    )
    discards_hold_days: int = Field(
        90,
        ge=0,
        le=3650,
        description="For how many days after you discard something the assistant learned, a new suggestion close to "
        "it is not shown again.",
    )
    discard_similarity: float = Field(
        0.8,
        ge=0,
        le=1,
        description="How alike a new suggestion's words must be to something you discarded for it to count as close "
        "to it: 0 counts any shared word, 1 only the same words.",
    )
    proposals_expire_days: int = Field(
        14,
        ge=1,
        le=730,
        description="How many days a suggestion from an input waits for your review before it expires. Suggestions "
        "from your own corrections never expire.",
    )
    catch_up_max: int = Field(
        20,
        ge=0,
        le=500,
        description="The most things from corrections made before the assistant could learn from them that are "
        "offered in one catch-up list, most repeated first. The rest expire with their number shown.",
    )
    learn: bool = Field(
        True,
        description="Whether the assistant looks at each correction you make (a send back, an undo, an edited "
        "message) and proposes one lesson from it. Off: corrections are still recorded, and nothing is proposed.",
    )
    learn_every_minutes: int = Field(
        30,
        ge=1,
        le=1440,
        description="How often the assistant learns from corrections you made without writing anything (an undo, an "
        "edited message, a change you pulled back). What you wrote with a correction is looked at at once.",
    )
    learn_input_chars: int = Field(
        6000,
        ge=500,
        le=100000,
        description="The most characters of an earlier input that the assistant is shown when it learns from a "
        "correction. Longer inputs are cut and say so.",
    )
    follow_on: bool = Field(
        True,
        description="Whether a save that moves a dated record (a calendar entry's day or time, an action's due day) or "
        "replaces a fact makes one request to the assistant to bring what is tied to it in line. Changes to your own "
        "items apply with Undo; anything someone was already sent gets a drafted correction that waits for you. Off: "
        "nothing follows a move.",
    )
    follow_on_max_tied: int = Field(
        20,
        ge=1,
        le=200,
        description="The most records tied to a moved date or a replaced fact that one follow-on request shows the "
        "assistant: those that name the entry first, then those whose words give the old day or repeat the replaced "
        "fact.",
    )
    follow_on_match: float = Field(
        0.67,
        gt=0,
        le=1,
        description="How much of a replaced fact's words another item on the same project must share for it to count "
        "as repeating the fact, compared word by word with plurals folded. 1 means every word.",
    )
    check_on_switch: bool = Field(
        True,
        description="Offer to check the assistant's work on the new choice, with its cost shown first, whenever you "
        "change the account or model that does a kind of work. A check that finds problems comes to Today with a way "
        "to switch back.",
    )
    new_terms_per_input: int = Field(
        3,
        ge=0,
        le=50,
        description="The most unknown terms (acronyms and system names the glossary lacks) the assistant suggests "
        "adding to the glossary from one input, found by the patterns in the language settings. 0 turns the scan off.",
    )
    learn_later_inputs: int = Field(
        5,
        ge=0,
        le=50,
        description="How many inputs that arrived after the corrected work, about the same items, the assistant is "
        "shown when it learns from a correction, so a change in the world isn't taken for a mistake.",
    )
    quality_window_days: int = Field(
        28,
        ge=7,
        le=365,
        description="How many days back the quality figures look: how often the assistant's work used what it was "
        "given, how many corrections repeated a mistake it had already been taught about, and how many closes nobody "
        "saw out of all closes.",
    )
    min_corrections_per_week: int = Field(
        10,
        ge=1,
        le=1000,
        description="The fewest corrections a week needs, for one kind of work, before its repeat-correction rate is "
        "shown. A week with fewer is too small to say anything.",
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
    no_work_tries: int = Field(
        5,
        ge=0,
        le=20,
        description="How many runs in a row may do no work (the program only printed a banner, or the call was cut "
        "off by the computer sleeping) before the request comes to you. Such a run is no try and uses up no automatic "
        "retry; each waits, with the wait doubling, then runs again.",
    )
    sleep_gap_seconds: int = Field(
        30,
        ge=1,
        le=3600,
        description="How much longer a failed call's clock time may be than the time the computer was awake before the "
        "call is taken as cut off by the computer sleeping. A call cut off that way did no work.",
    )
    cleaning: CleaningSettings = Field(default_factory=CleaningSettings, description="Input cleaning before AI calls.")
    knowledge: KnowledgeSettings = Field(
        default_factory=KnowledgeSettings, description="What each run is given from what the assistant has learned."
    )


# ---- config/checks.yaml and config/language.yaml ---------------------------------------------------------------------

Severity = Literal["refuse", "return", "warn", "off"]


def _default_lints() -> dict[str, Severity]:
    return {
        "blocked-wording": "return",
        "run-on-list": "return",
        "near-duplicate-action": "warn",
        "evidence-fit": "return",
        "already-known": "return",
        "near-duplicate-question": "warn",
        "several-questions": "return",
        "question-without-stake": "return",
        "unnamed-recipient": "return",
        "unverified-quote": "return",
        "unverified-name": "warn",
        "unknown-link": "return",
        "version-number": "return",
        "summary-is-status": "return",
        "unlinked-made": "return",
        "watched-project": "return",
        "other-team-item": "return",
        "stance": "return",
        "rejected-ask": "return",
        "bookkeeping": "return",
        "long-quote": "return",
        "action-stands-alone": "return",
        "reasoning-in-title": "return",
        "question-is-statement": "return",
        "thread-promise-unanswered": "return",
        "own-request-not-promise": "return",
        "own-promise-missed": "return",
        "team-we-one-owner": "return",
    }


class NearDuplicateActionTuning(ConfigModel):
    similarity: float = Field(
        0.8,
        ge=0,
        le=1,
        description="How alike a new action's words must be to an open or done action to count as a near-duplicate: "
        "0 flags any action that shares a word, 1 only one with the same words.",
    )
    date_window_days: int = Field(
        3,
        ge=0,
        le=60,
        description="How many days apart two sources' dates for the same promise may be and still be one promise; a "
        "repeat further apart is a new promise.",
    )


class NearDuplicateMeetingTuning(ConfigModel):
    similarity: float = Field(
        0.8,
        ge=0,
        le=1,
        description="How alike a meeting added in one line must be to one already on the calendar to count as the "
        "same one: 0 counts any shared word, 1 only the same words.",
    )
    minutes: int = Field(
        30,
        ge=0,
        le=720,
        description="How many minutes apart two meetings with alike words may start and still be the same meeting.",
    )


class AlreadyKnownTuning(ConfigModel):
    similarity: float = Field(
        0.7,
        ge=0,
        le=1,
        description="How much of a question's or report's subject a recorded fact or a piece of knowledge must hold "
        "for it to count as already answering it: 0 counts any shared words, 1 only a fact holding every word.",
    )


class NearDuplicateQuestionTuning(ConfigModel):
    similarity: float = Field(
        0.8,
        ge=0,
        le=1,
        description="How alike a new question's words must be to an open question to the same person, or one answered "
        "recently, to count as a near-duplicate: 0 flags any question that shares a word, 1 only one with the same "
        "words.",
    )
    days: int = Field(
        14,
        ge=0,
        le=3650,
        description="How many days back a question answered by the same person is still compared with a new one. "
        "Open questions are always compared.",
    )


class SeveralQuestionsTuning(ConfigModel):
    minimum: int = Field(
        2,
        ge=2,
        le=20,
        description="How many numbered questions in one question's or decision's text make it several questions: "
        "each is asked on its own, so each has its own answer.",
    )


class OwnerSuggestionTuning(ConfigModel):
    match: float = Field(
        0.5,
        gt=0,
        le=1,
        description="How much of a routing entry's topic an action's words must hold for the entry to suggest who "
        "owns it: 0 counts any shared word, 1 only an action that holds every word of the topic.",
    )


class UnverifiedQuoteTuning(ConfigModel):
    min_words: int = Field(
        3,
        ge=1,
        le=50,
        description="How many words a passage in quotation marks must have for the check that quoted words are in the "
        "material cited: shorter ones are taken as a name or a term in quotation marks, not as a quote.",
    )


class LongQuoteTuning(ConfigModel):
    max_words: int = Field(
        25,
        ge=3,
        le=200,
        description="The most words a passage in quotation marks may have in text written for someone else; anything "
        "longer is a link or a summary instead.",
    )


class ActionStandsAloneTuning(ConfigModel):
    min_words: int = Field(
        2,
        ge=1,
        le=20,
        description="The fewest words an action may have: one with fewer is a bare verb that says nothing about what "
        "to do it to.",
    )


class LintTuning(ConfigModel):
    """Settings of the core lints that have more than a severity: one entry per lint, named as the lint is in `lints`
    with underscores for hyphens, so each setting has a plain dotted key and environment variable."""

    near_duplicate_action: NearDuplicateActionTuning = Field(
        default_factory=NearDuplicateActionTuning, description="Settings of the near-duplicate action check."
    )
    near_duplicate_question: NearDuplicateQuestionTuning = Field(
        default_factory=NearDuplicateQuestionTuning, description="Settings of the near-duplicate question check."
    )
    near_duplicate_meeting: NearDuplicateMeetingTuning = Field(
        default_factory=NearDuplicateMeetingTuning,
        description="Settings of the check that a meeting added in one line isn't one already on the calendar.",
    )
    already_known: AlreadyKnownTuning = Field(
        default_factory=AlreadyKnownTuning,
        description="Settings of the check that a question or report isn't about something already recorded.",
    )
    several_questions: SeveralQuestionsTuning = Field(
        default_factory=SeveralQuestionsTuning,
        description="Settings of the check that a question or decision holds one question.",
    )
    owner_suggestion: OwnerSuggestionTuning = Field(
        default_factory=OwnerSuggestionTuning,
        description="Settings of the suggestion made for an action that has no owner.",
    )
    unverified_quote: UnverifiedQuoteTuning = Field(
        default_factory=UnverifiedQuoteTuning,
        description="Settings of the check that words in quotation marks are in the material cited.",
    )
    action_stands_alone: ActionStandsAloneTuning = Field(
        default_factory=ActionStandsAloneTuning,
        description="Settings of the check that an action is worded to be read on its own.",
    )
    long_quote: LongQuoteTuning = Field(
        default_factory=LongQuoteTuning,
        description="Settings of the check that text for someone else doesn't quote long passages back.",
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
    nudge_intro: str = Field(
        "Following up on {count} things from my note on {date}:",
        description="The line above the list in a follow-up message: {count} is how many things it lists and {date} "
        "is when the first message about them went out.",
    )
    nudge_intro_one: str = Field(
        "Following up on one thing from my note on {date}:",
        description="The same line when the follow-up message lists one thing.",
    )
    nudge_ask: str = Field(
        "A quick yes or no, or a date, for each is plenty.",
        description="The line under the list in a follow-up message, asking for the smallest useful reply.",
    )
    nudge_ask_one: str = Field(
        "A quick yes or no, or a date, is plenty.",
        description="The same line when the follow-up message lists one thing.",
    )
    nudge_overdue: str = Field(
        "(it was due {date})",
        description="What follows an action in a follow-up message when its due date has passed: {date} is that date.",
    )
    nudge_second_intro: str = Field(
        "Checking in again on what I first asked on {date}:",
        description="The line above the list in a second or later follow-up message: {date} is when the first message "
        "went out.",
    )
    nudge_second_ask: str = Field(
        "Is there someone else I should ask, or a date I can plan around?",
        description="The line under the list in a second or later follow-up message.",
    )
    called_off_notice: str = Field(
        "No longer needed, thanks: {item}",
        description="The one line drafted for someone who was already told about an action when it is called off, for "
        "you to send: {item} is the action. Nothing is sent by itself.",
    )
    source_by_person: str = Field(
        "{who}, {date}",
        description="What a history line's source says when the evidence is one known person (an input from them, or "
        "the person's own note): {who} is their name and {date} the day. Never the assistant.",
    )
    source_input: str = Field(
        "the {date} {what}",
        description="What a history line's source says when the evidence is an input that is not from one known "
        "person: {date} is the day it came in and {what} its title. Never the assistant.",
    )
    source_recorded: str = Field(
        "recorded {date}",
        description="What a history line's source says when nothing shows where the change came from: {date} is the "
        "day it was recorded.",
    )
    source_date_format: str = Field(
        "%b %d",
        description="How the day in a history line's source is written: pick one; each shows today's date written "
        "that way.",
        json_schema_extra={"choices": "date_formats"},
    )
    withheld_where: str = Field(
        "the message to {name}",
        description="How a message to one person is named in the reason it is held back: {name} is the person.",
    )
    resourced_summary: str = Field(
        "Took the assistant's name out of {count} history lines and said where each came from",
        description="The line saying what the sweep did when it re-sourced history lines that named the assistant: "
        "{count} is how many lines.",
    )
    resourced_label: str = Field(
        "Put where the change came from in a history line instead of the assistant's name",
        description="The line for one project's history lines in that change.",
    )
    withheld_name: str = Field(
        "Held back: {where} names {name}. Take the name out before this goes to anyone.",
        description="Why a message for someone else is not offered to copy: {where} says which part names the "
        "assistant and {name} is the name it holds.",
    )
    folded_note: str = Field(
        "Also came up: {text} (\u201c{quote}\u201d)",
        description="The line added to an action's notes when another action is added to it instead of being kept "
        "apart: {text} is the other action and {quote} the words it came from.",
    )
    merged_note: str = Field(
        "Merged with: {text}",
        description="The line added to an action's notes when another action that said the same is merged into it: "
        "{text} is the other action.",
    )
    merged_reason: str = Field(
        "Merged into \u201c{text}\u201d",
        description="Why an action that was merged into another is closed as dropped: {text} is the action it went "
        "into.",
    )
    folded_reason: str = Field(
        "Added to \u201c{text}\u201d instead",
        description="Why an action that was added to another one is closed as dropped: {text} is the action it "
        "went into.",
    )
    link_not_read: str = Field(
        "Not read: nothing set up can open this link",
        description="What a project added from a link is labeled when no source set up reads that address, so the "
        "project is not filled in from the link's words alone.",
    )
    part_of_meaning: str = Field(
        "A name for {project}.",
        description="What the glossary entry says when the person tells the assistant that words it took for a new "
        "project are a name for an existing one: {project} is that project's name.",
    )
    part_of_reason: str = Field(
        "Filed under {project} instead",
        description="Why a proposed project is set aside when the person says it is part of another: {project} is "
        "the project the work went under.",
    )
    not_a_project_meaning: str = Field(
        "Not a project.",
        description="What the glossary entry says when the person tells the assistant that words it took for a "
        "project are not one.",
    )
    not_a_project_reason: str = Field(
        "You said this isn't a project",
        description="Why a proposed project is set aside when the person says the words aren't a project.",
    )
    date_format: str = Field(
        "%a, %b %d",
        description="How dates appear in messages: pick one; each shows today's date written that way.",
        json_schema_extra={"choices": "date_formats"},
    )
    date_time_format: str = Field(
        "%a, %b %d, %Y, %H:%M",
        description="How a date and time appear in the assistant's notes and other text it writes, in your time "
        "zone: pick one; each shows the present moment written that way.",
        json_schema_extra={"choices": "date_time_formats"},
    )


DEFAULT_SELF_WORDS = ("me", "myself", "I")
DEFAULT_OWED_WORDS = ("you", "your", "please send", "me")
DEFAULT_REQUEST_WORDS = ("can", "could", "will", "would", "please", "need to", "needs to", "should", "must")


DEFAULT_CHAT_LINE_PATTERNS = (
    # a time, then who wrote it and a colon: "[10:32] Name: ...", "10:32 - Name: ..."
    r"^\s*[\[(]?\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?(?:,\s?[\d/.-]{6,10})?"
    r"[^\w\n:]{0,4}[^\W\d_][\w'’. -]{0,40}:\s+\S",
    # who wrote it, then the time with am or pm, alone on the line: "Name  10:32 AM"
    r"^\s*[^\W\d_][\w'’.-]*(?:\s+[^\W\d_][\w'’.-]*){0,2}\s+[\[(]?\d{1,2}:\d{2}(?::\d{2})?\s?[AaPp][Mm][\])]?\s*$",
)


class ReportedSpeech(ConfigModel):
    verbs: list[str] = Field(
        default_factory=lambda: [
            *("said", "says", "confirmed", "confirms", "told", "wrote", "writes", "asked", "wants"),
            *("mentioned", "replied", "responded", "noted", "commented", "pinged"),
        ],
        description="Words that, after a name or other speaker, mark a note as repeating someone else's words: "
        '"<name> said ...". Matched as whole words, ignoring case.',
    )
    lead_words: list[str] = Field(
        default_factory=lambda: ["per", "according to"],
        description="Words that, before a name or other speaker, mark a note as repeating someone else's words: "
        '"per <name> ...". The speaker has to start with a capital letter, so "per week" is not a speaker. Matched '
        "as whole words, ignoring case.",
    )
    own_speakers: list[str] = Field(
        default_factory=lambda: ["I", "we"],
        description='Speakers that are the person themselves, so "I said" and "I told <name>" stay the person\'s own '
        "words.",
    )
    request_words: list[str] = Field(
        default_factory=lambda: ["me to", "us to"],
        description="Words that, right after one of the speech words, mean the speaker is asking the person to do "
        'something: "<name> asked me to ..." is a request to the person, not content they report. Matched as whole '
        "words, ignoring case.",
    )
    quote_min_words: int = Field(
        3,
        ge=1,
        le=50,
        description="Text in quotation marks with at least this many words is someone else's words.",
    )
    chat_line_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CHAT_LINE_PATTERNS),
        description="Patterns (regular expressions, matched at the start of a line) for a line of a pasted chat: a "
        "time and the name of who wrote it. A note with enough such lines is a chat pasted in, which is someone "
        "else's words as a whole.",
    )
    chat_min_lines: int = Field(
        2,
        ge=1,
        le=20,
        description="How many lines that look like a chat make a note a pasted chat, reported as a whole.",
    )


DEFAULT_NEW_TERM_PATTERNS = [r"\b[A-Z]{2,}[0-9]*\b", r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"]
DEFAULT_NEW_TERM_IGNORE = [
    *("OK", "FYI", "ASAP", "TBD", "TBC", "EOD", "ETA", "AM", "PM", "RE", "FW", "CC", "BCC", "NB", "PS"),
    *("URGENT", "NOTE", "UPDATE", "REMINDER"),
]


DEFAULT_VERSION_PATTERNS = [
    r"\b[vV]\d+(?:\.\d+){0,3}\b",
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}(?:\.\d{1,5})?\b",
    r"(?i)\b(?:version|ver\.?|release|build)\s+\d+(?:\.\d+)*\b",
]
#: How a day is written in running text, as patterns with {iso}, {day}, {month} (the month's full or short name) and
#: {year} filled in for the day being looked for.
DEFAULT_DATE_PATTERNS = [
    r"{iso}",
    r"\b{day}(?:st|nd|rd|th)?\s+(?:of\s+)?{month}\b",
    r"\b{month}\.?\s+{day}(?:st|nd|rd|th)?\b",
    r"\bthe\s+{day}(?:st|nd|rd|th)\b",
]
DEFAULT_FINDINGS_WORDS = [
    *("found", "finding", "findings", "discovered", "discrepancy", "discrepancies"),
    *("inconsistency", "inconsistencies", "mismatch", "turns out"),
]
DEFAULT_MADE_PHRASES = [
    *("drafted", "wrote up", "write-up", "writeup"),
    *("created a draft", "made a draft", "prepared a draft", "saved a draft"),
    *("created a file", "made a file", "saved a file", "generated a file"),
    *("created a document", "made a document", "saved a document"),
    *("created minutes", "wrote minutes", "made minutes"),
]
DEFAULT_NAME_SKIP_WORDS = [
    *("the", "a", "an", "this", "that", "these", "those", "our", "your", "my", "his", "her", "their", "its"),
    *("hi", "hello", "hey", "dear", "thanks", "thank", "please", "also", "and", "but", "so", "if", "when", "as"),
    *("for", "to", "from", "with", "on", "in", "at", "by", "of", "is", "are", "was", "were", "we", "i", "it", "do"),
]


class LanguageFile(FileModel):
    messages: MessageSettings = Field(default_factory=MessageSettings, description="Wording of copied messages.")
    self_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SELF_WORDS),
        description='The words the language uses for the person themselves ("assign it to me"). A name written as one '
        "of these means the person, whatever case it is in.",
    )
    internal_terms: list[str] = Field(
        default_factory=lambda: [
            "changeset",
            "ledger",
            "applier",
            "the assistant noticed",
            "the assistant found",
        ],
        description="Words of the app's own workings that never belong in text written for someone else (a question "
        "to them, a reply). Matched as whole words, ignoring case.",
    )
    rejecting_words: list[str] = Field(
        default_factory=lambda: [
            "not my job",
            "not my place",
            "why are we asking",
            "don't ask",
            "do not ask",
            "no need to ask",
            "we are not their boss",
            "not ours to ask",
        ],
        description="Words in your note on a question that reject asking it at all, not its wording. The question is "
        "then dropped with your words as the reason, never reworded into a politer version of the same ask. Matched "
        "as whole words, ignoring case.",
    )
    owed_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_OWED_WORDS),
        description="Words that, in the quoted words of an action for someone on another team, show the person owes "
        'it something: a request addressed to them, such as "can you send it" or "please send the plan". Without '
        "one of them, or the person's or their team's name followed by a request word, such an action is recorded as "
        "a fact instead. Matched as whole words, ignoring case.",
    )
    request_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUEST_WORDS),
        description="Words that, right after the person's name or their team's (a comma or colon may come between), "
        'make the words a request addressed to them: "<name>, can you ..." or "<team> will need ...". A name with '
        "none of them after it only says who something is for. Matched as whole words, ignoring case.",
    )
    blocked_phrases: list[str] = Field(
        default_factory=lambda: ["confirm", "check whether", "check if", "TBD?"],
        description="Wording not allowed in actions and shared text; actions say what to do.",
    )
    unanchored_words: list[str] = Field(
        default_factory=lambda: [
            "it",
            "this",
            "that",
            "them",
            "these",
            "those",
            "him",
            "her",
            "the above",
            "the same",
            "as discussed",
            "as agreed",
        ],
        description="Words that point at something the reader can't see, so an action built on them can't be read on "
        'its own ("send it", "follow up on that"). A single word counts as the thing the action is done to, right '
        "after its first word and the lead words, or as its last word after a lead word; a phrase counts anywhere. "
        "Matched as whole words, ignoring case.",
    )
    unanchored_lead_words: list[str] = Field(
        default_factory=lambda: ["up", "on", "to", "with", "about", "for", "back", "out", "off", "over", "at"],
        description="Words that may come between an action's first word and the thing it is done to, such as the "
        "'up on' of 'follow up on'.",
    )
    reasoning_phrases: list[str] = Field(
        default_factory=lambda: [
            *("no recorded fact", "no fact gives", "nothing recorded", "not recorded"),
            *("couldn't find", "could not find", "not stated", "not mentioned"),
            *("I assume", "I think"),
        ],
        description="Words and phrases that mark the assistant's reasoning, so a to-do's or a question's title that "
        "holds one is returned: a title says what to do or ask, and the reasoning belongs in the change's summary. "
        "Matched as whole words, ignoring case; words quoted from the input don't count.",
    )
    question_marks: list[str] = Field(
        default_factory=lambda: ["?", "\uff1f", "\u061f"],
        description="The characters that end a question in the language. A question's title that doesn't end in one "
        "(a closing quote or bracket may follow) is a statement, and is returned to be asked as a question.",
    )
    ask_lead_words: list[str] = Field(
        default_factory=lambda: ["Can you", "Could you", "Would you", "Please"],
        description="Words a sentence starts with when it asks someone to do something. In mail the person sent, an "
        "action quoting such a sentence (or one that ends in a question mark) is the person asking someone else, not "
        "their own promise. Matched as whole words, ignoring case.",
    )
    asking_words: list[str] = Field(
        default_factory=lambda: [
            *("when", "what", "which", "where", "will", "would", "could", "should"),
            *("tell", "know", "does", "have", "there", "please", "about", "confirm"),
        ],
        description="Words that frame a question rather than say what it is about; they are left out when checking "
        "whether a recorded fact already answers it.",
    )
    own_promise_words: list[str] = Field(
        default_factory=lambda: ["I'll", "I will"],
        description="Words that make a sentence the person's own promise even when it also asks something: a request "
        "holding one of them is not counted as the person asking someone else. Matched as whole words, ignoring case.",
    )
    team_promise_words: list[str] = Field(
        default_factory=lambda: ["we'll", "we will", "we're going to"],
        description="Words that make a promise a team's rather than one person's. An action quoting one of them, owned "
        "by the message's sender alone though the words don't name them, is sent back to leave its owners empty. "
        "Matched as whole words, ignoring case.",
    )
    title_min_words: int = Field(
        3,
        ge=1,
        le=12,
        description="The fewest words a title's topic may have: a shorter one from the assistant (a bare 'Noted.') "
        "gives way to the first meaningful line of what came in, but only when that line fits whole; with no whole "
        "line a short topic of two words or more stays, and with none the title says its topic is missing.",
    )
    run_on_separators: list[str] = Field(
        default_factory=lambda: [" / ", "; "],
        description="Separators that mean several items were crammed in one line.",
    )
    rule_report_phrases: list[str] = Field(
        default_factory=lambda: [
            "from now on",
            "going forward",
            "from here on",
            "in future",
            "should never",
            "should always",
            "don't ask",
            "do not ask",
        ],
        description="Phrases that mark a draft report to the product's maintainers as a standing rule for the "
        "assistant rather than a request for a change to the product. Such a report is sent back to be proposed as "
        "a rule, which waits for you.",
    )
    new_term_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NEW_TERM_PATTERNS),
        description="Patterns (regular expressions) for words in an input that look like the name of a system or an "
        "acronym: by default two or more capital letters in a row, or a word of several capitalized parts. A word "
        "that matches and is not in the glossary, the people or the projects is suggested as a new term.",
    )
    new_term_ignore: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NEW_TERM_IGNORE),
        description="Words that match a new-term pattern but are everyday abbreviations, never suggested as new "
        "terms. Case is ignored.",
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
    already_sent_phrases: list[str] = Field(
        default_factory=lambda: [
            *("I sent", "I've sent", "I have sent", "I just sent", "I emailed", "I've emailed"),
            *("I forwarded", "I've forwarded", "we sent", "we've sent"),
        ],
        description="Phrases that say the person already sent something. When an input says so and names no one it "
        "went to, a question or action that names a recipient for it is returned: the assistant asks the person "
        "who it went to instead of guessing.",
    )
    due_lead_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LEAD_WORDS),
        description="Words that may begin the words a due date is read from and say only that a date follows "
        '("by", "on", "due", "due by", "no later than"). The date reader steps past them, so "due Oct 22" and '
        '"on the 3rd" read as the date alone. Case is ignored.',
    )
    due_ordinal_suffixes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ORDINAL_SUFFIXES),
        description='The endings that make a number the day of a month ("st", "nd", "rd" and "th" of "the 25th"). '
        'With none, "the 25th" is not read as a date. Case is ignored.',
    )
    due_condition_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CONDITION_WORDS),
        description='Words that make a promise\'s due a condition or leave it open ("once the keys arrive", "after the '
        'workshop", "soon"). Due words with one of them, as whole words, that the date reader can\'t read as a date '
        "keep their words and have no date, whatever date the assistant gave. Other due words the reader can't read "
        "keep the assistant's own date, marked for you to check. Case is ignored.",
    )
    due_hold_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_HOLD_WORDS),
        description='The condition words that wait for something to happen ("once the keys arrive", "after the '
        'workshop", "until you publish it"). A promise whose due words hold one, and that the date reader can\'t read '
        "as a date, is put on hold from the start, waiting for those words. Condition words not listed here only leave "
        "the date open. Case is ignored.",
    )
    due_before_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BEFORE_WORDS),
        description='The condition words after which a calendar entry may be named ("before the print sync"). When the '
        "words that follow name one entry that is still ahead, the promise is due at that entry and moves with it; "
        "when they name none, or more than one, it has no date and keeps its words. Case is ignored.",
    )
    task_verbs: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TASK_VERBS),
        description='The verbs a task\'s title starts with ("pay", "send", "book"). A plain calendar entry (nobody '
        'else invited, no description) whose first word is one of them is offered as a to-do with one click ("Pay '
        'the deposit"); other entries are just kept in the calendar. Case is ignored.',
    )
    delivery_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DELIVERY_WORDS),
        description='The words that say something was delivered ("sent", "finished", "it\'s in", "did it", "done"). '
        "An ending the assistant reads as done stands, and credits the people who owed it, only when the words it "
        "quotes hold one of these and none of the called-off words. Case is ignored.",
    )
    called_off_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CALLED_OFF_WORDS),
        description="The words that say something was learned another way, moved to a meeting or no longer matters "
        '("moot", "covered by", "no longer needed", "we\'ll get it in", "will cover"). An ending whose words hold one '
        "of these and none of the delivery words is called off instead of done: nobody is credited, and your words "
        "are the reason. Case is ignored.",
    )
    meeting_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_MEETING_WORDS),
        description="The words that say something moved into a meeting ('we'll cover it', 'in the planning sessions', "
        "'take it up at'). An ending that is called off, whose words hold one of these and name a meeting the "
        "workspace knows (a calendar entry still ahead, or a series), also puts the action on that meeting's agenda, "
        "linked to it. Case is ignored.",
    )
    closed_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CLOSED_WORDS),
        description='The words that only say something is closed ("close", "closed", "mark it closed"). Closed with '
        'neither delivery words nor called-off words is neither done nor called off: you are asked "Done by the owner, '
        'or no longer needed?", even for your own note. Case is ignored.',
    )
    limit_markings: list[str] = Field(
        default_factory=lambda: [
            *("internal only", "do not forward", "don't forward", "not for the client"),
            *("not for distribution", "confidential", "for your eyes only"),
        ],
        description="Phrases (whole words, ignoring case) with which a sender limits who may see a message. When the "
        "new text of a message holds one, the message is limited to the people it went to and came from: a question "
        "or reply drafted from it to anyone else is refused, until the person widens the limit.",
    )
    version_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_VERSION_PATTERNS),
        description="Patterns (regular expressions) for a tool's version number, such as v2.3 or build 1042. A "
        "question or draft for someone else that holds one is returned: it names the page, links it and says what "
        "changed or when. A version that is part of a name the workspace knows (a glossary term, a project, an "
        "organization or a team) passes.",
    )
    date_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DATE_PATTERNS),
        description="Patterns (regular expressions) for how a day is written in running text, with {iso} (2026-10-22), "
        "{day}, {month} (the month's full or short name) and {year} standing for the day being looked for. When a "
        "date moves, records on the same project whose words match the old day are brought to the assistant as "
        "tied to it. Case is ignored.",
    )
    findings_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_FINDINGS_WORDS),
        description="Words that show a project's summary holds findings instead of its status (a discrepancy found, "
        "a mismatch). The summary says where the project stands; what was found goes to facts. Case is ignored.",
    )
    made_phrases: list[str] = Field(
        default_factory=lambda: list(DEFAULT_MADE_PHRASES),
        description="Phrases that say a change made a draft, a write-up or a file. When a change's summary says so "
        "and the change holds nothing it made, it is returned: the draft or file is made where the person can open "
        "it, or the summary stops claiming it.",
    )
    name_skip_words: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NAME_SKIP_WORDS),
        description="Everyday words that can start a sentence or a phrase and are never part of a person's name. The "
        "check that names are spelled as the workspace has them ignores them at the edges of a capitalized phrase. "
        "Case is ignored.",
    )
    bare_confirmation_words: int = Field(
        4,
        ge=1,
        le=20,
        description="A note typed on a button (Mark done, They finished it, Followed up, an answer) with fewer words "
        "than this and no link is a bare confirmation: it is kept with the change and not sent to the assistant. A "
        "longer note, or one with a link, is handed in as the person's own words.",
    )

    @field_validator("title_skip", "new_term_patterns", "version_patterns")
    @classmethod
    def _patterns_compile(cls, value: list[str]) -> list[str]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"{pattern!r} is not a regular expression: {exc}") from exc
        return value

    @field_validator("date_patterns")
    @classmethod
    def _date_patterns_compile(cls, value: list[str]) -> list[str]:
        for pattern in value:
            filled = pattern
            for name, sample in (("iso", "2026-01-02"), ("day", "2"), ("month", "January"), ("year", "2026")):
                filled = filled.replace("{" + name + "}", sample)
            try:
                re.compile(filled)
            except re.error as exc:
                raise ValueError(f"{pattern!r} is not a date pattern: {exc}") from exc
        return value


# ---- config/ui.yaml -------------------------------------------------------------------------------------------------

DEFAULT_SHORTCUTS = {
    "next": "j",
    "previous": "k",
    "primary": "a",
    "send_back": "s",
    "copy": "c",
    "edit": "e",
    "move": "m",
    "undo": "u",
    "hand_in": "n",
    "help": "?",
    "ask": "/",
    "next_pane": "]",
    "previous_pane": "[",
    "show_new": "N",
}


class TodaySettings(ConfigModel):
    mail_hours: int = Field(
        24, ge=1, le=336, description="How far back, in hours, Today's list of what came in reaches."
    )
    mail_max: int = Field(50, ge=1, le=500, description="The most messages Today lists at once.")
    agenda_days_ahead: int = Field(
        1, ge=0, le=14, description="How many days after today the agenda also shows (0: today only)."
    )
    stale_after_days: int = Field(
        21,
        ge=0,
        le=3650,
        description="One of the person's own to-dos with no date that nothing has changed for this many days is stale, "
        "and Today asks whether to keep it. Zero turns the line off.",
    )
    top_priorities_lines: int = Field(
        5,
        ge=1,
        le=50,
        description="The most lines Top priorities shows on Today, across every project. It lists the most pressing "
        "first: overdue, then due within the follow-up window, then waiting on the person, then at risk; the rest are "
        "counted, not listed.",
    )
    top_priorities_ahead_days: int = Field(
        14,
        ge=0,
        le=90,
        description="Top priorities also lists the dated to-dos that fall due in the next this many days, after its "
        "lines. Zero leaves that list out.",
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
    second_nudge_items: int = Field(
        2,
        ge=1,
        le=20,
        description="A second or later follow-up message to a person names only this many of what is still waiting, "
        "the longest-waiting first, and asks who else to ask or for a date.",
    )
    escalate_after_chases: int = Field(
        2,
        ge=0,
        le=20,
        description="Once something has had this many follow-ups and the wait has run its length again with no answer, "
        "Today suggests asking someone else about it, with a choice of who. Nothing is sent. Zero turns the suggestion "
        "off.",
    )


class WalkthroughSettings(ConfigModel):
    first_promises: int = Field(
        5,
        ge=1,
        le=20,
        description="How many of the promises found in the person's own mail the new-start walkthrough shows on its "
        "first-result screen, soonest day first. The rest are still kept and followed.",
    )


class SeriesSettings(ConfigModel):
    usually_with_share: float = Field(
        0.5,
        gt=0,
        le=1,
        description="A series' page lists, as who it is usually with, the people on more than this share of the "
        "meetings whose guest lists are known (0.5: more than half).",
    )
    usually_with_min_meetings: int = Field(
        2,
        ge=1,
        le=50,
        description="A series' page names who it is usually with only once at least this many of its meetings have a "
        "known guest list.",
    )
    usually_with_max: int = Field(
        6,
        ge=1,
        le=50,
        description="The most people a series' page lists as who it is usually with, the most regular first.",
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


class NotificationQuietHours(ConfigModel):
    start: str = Field(
        "21:00",
        description="The time notices stop. A notice that comes up in quiet hours waits and is sent, once, when they "
        "end.",
        json_schema_extra={"choices": "times_of_day"},
    )
    end: str = Field(
        "07:00",
        description="The time notices start again. Quiet hours may start in the evening and end the next morning.",
        json_schema_extra={"choices": "times_of_day"},
    )

    @field_validator("start", "end", mode="before")
    @classmethod
    def _a_time_of_day(cls, value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 24 * 60:
            value = f"{value // 60:02d}:{value % 60:02d}"
        if not isinstance(value, str) or not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            raise ValueError("pick a time of day, such as 21:00")
        return value

    @model_validator(mode="after")
    def _hours_differ(self) -> NotificationQuietHours:
        if self.start == self.end:
            raise ValueError("quiet hours must start and end at different times")
        return self


class NotificationsSettings(ConfigModel):
    enabled: bool = Field(
        False,
        description="Tell me when something needs me. A notice goes out only for what Today's Decide group holds: a "
        "decision waiting, work that stopped, a restart or a failing backup. Never for routine processing, and only "
        "to you.",
    )
    browser: bool = Field(
        True,
        description="Show the notice in this browser, on the computer that runs the app, while the app is open there. "
        "Needs the browser's permission.",
        json_schema_extra={"enabled_by": "enabled"},
    )
    webhook: str | None = Field(
        None,
        description=SecretHint(
            "A secret reference (env:NAME or file:/path) to your own address for notices, never the address itself."
        ),
        json_schema_extra={"enabled_by": "enabled", "advanced": True},
    )
    webhook_format: Literal["json", "plain"] = Field(
        "json",
        description="What the address expects. json: a small JSON message with the text in it, which chat apps take. "
        "plain: the text alone as the body, which push-notification topics take.",
        json_schema_extra={"enabled_by": "webhook", "advanced": True},
    )
    quiet_hours: NotificationQuietHours = Field(
        default_factory=NotificationQuietHours, description="When notices wait instead of going out."
    )
    retry_minutes: int = Field(
        10,
        ge=1,
        le=1440,
        description="When a notice could not be delivered, how long to wait before trying again.",
    )
    message_one: str = Field(
        "1 decision waiting for you",
        min_length=1,
        description="The notice when one thing needs you. Notices carry a count and never what an item is about.",
    )
    message_many: str = Field(
        "{count} decisions waiting for you",
        min_length=1,
        description="The notice when several things need you; {count} is how many.",
    )
    test_message: str = Field(
        "This is a test. You will get a note like this when something needs you.",
        min_length=1,
        description='The note "Send me a test" sends.',
    )

    @field_validator("message_one", "message_many", "test_message")
    @classmethod
    def _fills_in(cls, value: str) -> str:
        try:
            value.format(count=1)
        except (KeyError, IndexError, ValueError):
            raise ValueError("a notice can only use {count}") from None
        return value


#: A header link's address: a web address with no spaces.
_LINK_ADDRESS = re.compile(r"^https?://\S+$")


def _check_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    """The links as a list of {name, address}: each named (up to 40 characters) with a web address, nothing else."""
    clean = []
    for link in links:
        if set(link) != {"name", "address"}:
            raise ValueError("each link has a name and an address, and nothing else")
        name, address = link["name"].strip(), link["address"].strip()
        if not name or len(name) > 40:
            raise ValueError("a link's name is one to 40 characters")
        if len(address) > 2000 or not _LINK_ADDRESS.match(address):
            raise ValueError(f"the address for {name} must be a web address starting with http:// or https://")
        clean.append({"name": name, "address": address})
    return clean


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
    links: list[dict[str, str]] = Field(
        default_factory=list,
        max_length=12,
        description="Links to your own pages (a board, a schedule, a shared folder) shown in the header, each opening "
        "in a new tab: a name and a web address.",
        json_schema_extra={"screen_edit": True},
    )
    feedback_to: str | None = Field(
        None,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="The address the feedback button writes its email to. Empty uses the address the app was "
        "packaged with, if any; with neither, feedback is drafted to copy.",
    )
    feedback_problem_days: int = Field(
        3,
        ge=1,
        le=60,
        description="How many days back Send feedback looks for failed work to offer to add: a failed request to an "
        "AI account, account check, source read or error in the app, with its settings and the service's error text "
        "but never what you wrote or read.",
    )
    feedback_problem_max: int = Field(
        20,
        ge=1,
        le=100,
        description="The most failures Send feedback offers to add, newest first. The app also keeps five times this "
        "many app errors on this computer.",
    )

    @field_validator("links")
    @classmethod
    def _links_are_names_and_addresses(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        return _check_links(value)

    today: TodaySettings = Field(
        default_factory=TodaySettings, description="What Today's agenda and its list of what came in cover."
    )
    followups: FollowupsSettings = Field(
        default_factory=FollowupsSettings,
        description="When something sent to a person is due a follow-up, which Today and Follow-ups both use.",
    )
    walkthrough: WalkthroughSettings = Field(
        default_factory=WalkthroughSettings, description="What the new-start walkthrough shows."
    )
    series: SeriesSettings = Field(
        default_factory=SeriesSettings, description="What a series' page works out from its meetings' guest lists."
    )
    brand: BrandSettings = Field(default_factory=BrandSettings, description="The accent color and logo.")
    notifications: NotificationsSettings = Field(
        default_factory=NotificationsSettings,
        description="Notices that something needs you, sent outward to you only: off until you turn them on.",
    )
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
    "stage_left_before_go": "Not started: it left this stage before you started it.",
    "retry_blocked": "stage tasks need an explicit go before they can run",
    "type_unavailable": "The record type plugin is disabled.",
    "check_unavailable": "The entry check is unavailable.",
    "check_access": "The entry check cannot read this record type.",
    "check_failed": "The entry check failed to run.",
    "rule_inactive": "The standing rule is not active.",
    "rule_scope": "The record is outside this rule's scope.",
    "rule_prose": "This rule needs a deterministic code check before it can allow a move.",
    "confirm": "This stage move waits for you to confirm it.",
    "waiting": "Waiting for you to start it before this task runs.",
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
    constrains: list[str] = Field(
        default_factory=list,
        description="What the rule is about: op kinds (`question.add`) or op fields (`action.add.owners`). A run that "
        "produces one counts the rule as applied; a rule that constrains nothing is only ever present.",
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
    first_run: Literal["intake", "baseline", "recent", "all"] = Field(
        "intake",
        description="What the first read of a source does. intake: it is taken in quietly: nothing is reported as new "
        "one by one; the mail of the last first_run_days and everything in any other kind of source is handed in "
        "together, priced as one total, and left as one list to look over. baseline: it only notes what is there; "
        "recent: it also hands in what arrived, changed or happens within first_run_hours of the read (the last "
        "day's mail, today's meetings); all: everything there is handed in as new.",
    )
    first_run_hours: int = Field(
        24, ge=1, le=336, description="With first_run recent: how many hours around the first read count as recent."
    )
    first_run_days: int = Field(
        14,
        ge=1,
        le=365,
        description="With first_run intake, for mail: how many days back the first read looks. Older mail isn't "
        "read, and Today says so. Any other kind of source is taken in whole.",
    )
    report_removed: bool = Field(True, description="Hand in an item that disappeared from the source.")
    data_level: Literal["open", "internal", "restricted"] | None = Field(
        None,
        description="How sensitive what this source holds is: its items go only to AI accounts allowed this level. "
        "Empty: the level set for its kind of source, else the default for all sources.",
    )
    account: str | None = Field(
        None,
        description="For a source of an add-on that signs in as you: which signed-in account it reads, by its address. "
        "Empty: the only account signed in; with several signed in, a source must say which.",
    )
    author: str | None = Field(
        None,
        description="Whose work the source holds when it is all one person's or one team's: a person's id (yours "
        "makes everything in it your own work) or a team's id. Empty: the author of each change is read from the "
        "change itself.",
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
    projects: list[str] = Field(
        default_factory=list,
        description="Projects the matcher looks for by name (terms-absent, name-matches), held by id: their names now "
        "count as terms, so a rename never detaches the rule. A name typed here is saved as the project's id; a "
        "project that is gone gives no terms, and the rule then closes nothing.",
    )
    people: list[str] = Field(
        default_factory=list,
        description="People the matcher looks for by name (terms-absent, name-matches), held by id like projects: "
        "their names and other names now count as terms.",
    )
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
    look_back_choices: list[int] = Field(
        default_factory=lambda: [30, 90, 365],
        description="How many more days further back than the first read the person can ask a mail source to look, "
        "offered as a list to pick from. Each shows its item count and cost before anything is read.",
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
    unread_gap_factor: float = Field(
        2,
        ge=1,
        description="How many times a source's own read interval it may go unread, failing, before it becomes a "
        "line on Today for you to act on (1 is as soon as one interval has passed). A source with no network is "
        "not counted.",
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


# ---- config/steward.yaml ---------------------------------------------------------------------------------------------


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class RemindersSettings(ConfigModel):
    working_start: str = Field(
        "09:00",
        description="The time the working day starts. What the assistant adds on its own that came in earlier waits "
        "until then, and Tomorrow morning snoozes to it. A reminder you set for an earlier time still comes at "
        "that time.",
        json_schema_extra={"choices": "times_of_day"},
    )
    working_end: str = Field(
        "17:30",
        description="The time the working day ends. What the assistant adds on its own that came in later waits for "
        "the next working day, and Later today is left out of the snooze choices once it would fall after it. A "
        "reminder you set for a later time still comes at that time.",
        json_schema_extra={"choices": "times_of_day"},
    )
    working_first_day: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] = Field(
        "monday", description="The first day of the working week. Next week snoozes to this day."
    )
    working_last_day: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] = Field(
        "friday",
        description="The last day of the working week. The days between the first and the last are working days.",
    )
    quiet_start: str = Field(
        "21:00",
        description="The time quiet hours start. A reminder that falls in quiet hours waits and arrives with the "
        "others that waited, once they end, and so does what the assistant adds on its own.",
        json_schema_extra={"choices": "times_of_day"},
    )
    quiet_end: str = Field(
        "07:00",
        description="The time quiet hours end. They may start in the evening and end the next morning.",
        json_schema_extra={"choices": "times_of_day"},
    )
    missed: Literal["each", "summary"] = Field(
        "each",
        description="How reminders that came due while this computer was asleep arrive on waking. each: one line for "
        "each. summary: one line listing them.",
    )
    later_today_hours: int = Field(
        3, ge=1, le=12, description="How many hours from now Later today snoozes to, when that is still a working time."
    )
    evening: str = Field(
        "18:00",
        description="The time This evening snoozes to.",
        json_schema_extra={"choices": "times_of_day"},
    )
    late_after_minutes: int = Field(
        5,
        ge=1,
        le=1440,
        description="A reminder that came due this long ago or more, without being shown, is marked late: the app or "
        "the computer was not running when it came due.",
    )

    @field_validator("working_start", "working_end", "quiet_start", "quiet_end", "evening", mode="before")
    @classmethod
    def _a_time_of_day(cls, value: Any) -> Any:
        # An unquoted 17:30 is read by a YAML file as the number of minutes it is; give it back as the clock time.
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 24 * 60:
            value = f"{value // 60:02d}:{value % 60:02d}"
        if not isinstance(value, str) or not _CLOCK.match(value):
            raise ValueError("pick a time of day, such as 09:00")
        return value

    @model_validator(mode="after")
    def _hours_make_sense(self) -> RemindersSettings:
        if self.working_start >= self.working_end:
            raise ValueError("working hours must end after they start: pick a later end or an earlier start")
        if self.quiet_start == self.quiet_end:
            raise ValueError("quiet hours can't start and end at the same time: pick two different times")
        return self


class SentMatchSettings(ConfigModel):
    window_days: int = Field(
        7,
        ge=1,
        le=60,
        description="A message you sent is matched to a message you copied from the app only when it went to the same "
        "person within this many days after you copied it. The difference between the two is what the assistant "
        "learns your wording from.",
    )
    similarity: float = Field(
        0.6,
        ge=0.1,
        le=1.0,
        description="How alike a sent message and a copied one must be, from 0 to 1 (the share of their words they "
        "have in common), for them to count as the same message. Lower matches messages you rewrote heavily; higher "
        "only matches those you hardly changed.",
    )
    ask_after_days: int = Field(
        2,
        ge=1,
        le=60,
        description="A message you copied that no sent message matches gets one line on Today asking whether it went "
        "out, after this many days. Only when a mailbox's sent folder is being read. Still to send asks again after "
        "the same number of days.",
    )


class StewardFile(FileModel):
    default_stance: Literal["manage", "alongside", "report_to", "watch"] = Field(
        "alongside",
        description="Who a person is to you until you say otherwise: manage (you manage them), alongside (you work "
        "alongside them), report_to (you report to them) or watch (you only watch). It decides what the assistant "
        "may draft or ask them.",
    )
    tracks: list[Literal["dates", "decisions", "design"]] = Field(
        default_factory=lambda: ["dates", "decisions"],
        description="What you track for the work: delivery dates, decisions, and design quality. The assistant drafts "
        "no question about something you don't track, whoever it is for.",
    )
    chase_undated_days: int = Field(
        14,
        ge=1,
        le=365,
        description="A promise someone owes the person that has no date gets one line on Today after this many days "
        "with no news, counted from when it was made or from its latest news. Nothing is shown while it is on hold.",
    )
    chase_dated_days: int = Field(
        7,
        ge=0,
        le=365,
        description="A promise someone owes the person that has a date gets a line on Today only from this many days "
        "before its date, and once the date has passed. Nothing is shown while it is on hold.",
    )
    second_move_days: int = Field(
        14,
        ge=0,
        le=365,
        description="A change that only moves a date isn't shown in a record's history. A second move of the same date "
        'within this many days of the one before is shown in your own history, as "moved again" with how many times '
        "and since when; it is never in anything drafted for someone else. Zero shows no second moves.",
    )
    reminders: RemindersSettings = Field(
        default_factory=RemindersSettings, description="When a reminder on a dated thing reaches the person."
    )
    hold_outside_hours: bool = Field(
        True,
        description="Whether what the assistant or a rule adds to Today on its own waits for your working hours when "
        "its cause came in outside them or in quiet hours. What waited arrives together under one row, While you were "
        "away. A reminder you set for a time is kept as chosen, and a stop, your own note and your setup are never "
        "held. Off shows everything as it arrives.",
    )
    reply_thread_days: int = Field(
        14,
        ge=0,
        le=365,
        description="Two messages with the same subject and a person in common count as one conversation when they "
        "are no more than this many days apart and carry no thread headers. It decides whether a message you sent "
        "answers a reply you owe.",
    )
    sent_match: SentMatchSettings = Field(
        default_factory=SentMatchSettings,
        description="How a message you sent is matched to the one you copied from the app, and when you are asked "
        "whether a copied message went out.",
    )


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
    "steward": StewardFile,
}

#: The newest version each file format has reached.
CURRENT_VERSIONS: dict[str, int] = {name: 1 for name in FILES}
