"""Config file schemas.

Each config file is one model. Every field has a default and a description: the description feeds the comment block
written into new config files, the settings forms and `cockpit config show`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigModel(BaseModel):
    """Base for config models: unknown keys are errors, so a typo never silently does nothing."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class FileModel(ConfigModel):
    """Base for a whole config file."""

    version: int = Field(1, description="Format version of this file. Older files are migrated at start.")


# ---- config/workspace.yaml -------------------------------------------------------------------------------------------


class UserSettings(ConfigModel):
    person: str | None = Field(None, description="The PM's own person record id, e.g. PER-1.")
    full_name: str = Field("", description="The PM's full name, as it should appear to others.")
    aliases: list[str] = Field(default_factory=list, description='Other names that mean the PM (a first name, "me").')
    timezone: str = Field("UTC", description="The PM's time zone, as an IANA name such as Europe/Lisbon.")


class PluginSettings(ConfigModel):
    enabled: list[str] = Field(default_factory=list, description="Plugins enabled in this workspace, by name.")


class WorkspaceFile(FileModel):
    name: str = Field("Workspace", description="The workspace's display name.")
    assistant_name: str = Field("Assistant", description="The assistant's display name; the only name people see.")
    user: UserSettings = Field(default_factory=UserSettings, description="Who the PM is.")
    owner_format: str = Field("{full_name}", description='How an action owner is written, e.g. "{team} ({full_name})".')
    plugins: PluginSettings = Field(default_factory=PluginSettings, description="Which plugins run in this workspace.")


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
    every_minutes: int = Field(60, ge=1, description="How often the readable export in data/ is written.")
    commit: bool = Field(True, description="Commit the export and config to the workspace's git repository.")
    remote: str | None = Field(None, description="A private git remote to push the export to, for an off-site copy.")


class BackupTarget(ConfigModel):
    path: str = Field(
        "", description="A folder off this computer: a synced folder, an external drive or a network share."
    )
    label: str = Field("", description='What to call this target on screen, e.g. "cloud folder".')


class BackupSettings(ConfigModel):
    targets: list[BackupTarget] = Field(default_factory=list, description="Where full backups go. Use at least one.")
    every_hours: int = Field(24, ge=1, description="How often a full backup is made.")
    keep: int = Field(14, ge=1, description="How many backups to keep in each target.")


class StorageFile(FileModel):
    backend: Literal["sqlite"] = Field("sqlite", description="Where records live. Postgres comes later.")
    export: ExportSettings = Field(default_factory=ExportSettings, description="The readable export and its history.")
    backups: BackupSettings = Field(default_factory=BackupSettings, description="Full backups to somewhere else.")


# ---- config/ai.yaml --------------------------------------------------------------------------------------------------

DataLevel = Literal["open", "internal", "restricted"]


class ProviderSettings(ConfigModel):
    adapter: str = Field("stub", description="Which installed adapter talks to this account.")
    base_url: str | None = Field(None, description="The API address, for adapters that need one.")
    auth: str | None = Field(None, description="A secret reference (env:NAME or file:/path), never the secret itself.")
    models: dict[str, str] = Field(default_factory=dict, description="Short names for this account's models.")
    allowed_data: list[DataLevel] = Field(
        default_factory=lambda: ["open"], description="The most sensitive material this account may see."
    )
    timeout_seconds: int = Field(90, ge=5, description="How long to wait for an answer.")
    json_mode: bool = Field(True, description="Ask the provider for JSON output when it supports that.")


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


class Budgets(ConfigModel):
    per_run_usd: float = Field(0.25, ge=0, description="Stop a single run above this cost.")
    per_day_usd: float = Field(2.0, ge=0, description="Stop new runs for the day above this total.")
    per_month_usd: float = Field(30.0, ge=0, description="Stop new runs for the month above this total.")
    warn_at: float = Field(0.8, gt=0, le=1, description="Warn when this share of a budget is used.")


class Price(ConfigModel):
    input_per_million: float = Field(0.0, ge=0, description="Price in USD per million input tokens.")
    output_per_million: float = Field(0.0, ge=0, description="Price in USD per million output tokens.")


class EvaluationSettings(ConfigModel):
    runs: int = Field(3, ge=1, description="How many times each evaluation case runs.")
    min_score: float = Field(0.9, ge=0, le=1, description="Pass rate a model needs to be approved for a tier.")


def _default_tiers() -> dict[str, TierSettings]:
    return {"routine": TierSettings(), "deep": TierSettings()}


def _default_tasks() -> dict[str, TaskSettings]:
    return {"notes": TaskSettings()}


class AiFile(FileModel):
    providers: dict[str, ProviderSettings] = Field(
        default_factory=dict, description="Every AI account this workspace may use (none until one is added)."
    )
    tiers: dict[str, TierSettings] = Field(default_factory=_default_tiers, description="What the work needs.")
    tasks: dict[str, TaskSettings] = Field(default_factory=_default_tasks, description="Tier and settings per task.")
    budgets: Budgets = Field(default_factory=Budgets, description="Spending limits across all accounts.")
    prices: dict[str, Price] = Field(
        default_factory=dict, description="Prices by provider/model, for models whose provider doesn't publish them."
    )
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings, description="How models are compared.")

    @model_validator(mode="after")
    def _tiers_name_real_accounts(self) -> AiFile:
        """A tier may be empty (no account yet), but never name an account or tier that doesn't exist."""
        problems = []
        for name, tier in self.tiers.items():
            for ref in ([tier.use] if tier.use else []) + tier.fallback:
                provider = ref.partition("/")[0]
                if provider not in self.providers:
                    problems.append(f"tiers.{name} names {ref!r}, but there is no account {provider!r} in providers")
            if tier.escalate_to and tier.escalate_to not in self.tiers:
                problems.append(f"tiers.{name}.escalate_to names {tier.escalate_to!r}, which isn't a tier")
        for kind, task in self.tasks.items():
            if task.tier not in self.tiers:
                problems.append(f"tasks.{kind}.tier names {task.tier!r}, which isn't a tier")
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


class ChecksFile(FileModel):
    lints: dict[str, Severity] = Field(default_factory=_default_lints, description="How strict each soft check is.")


class MessageSettings(ConfigModel):
    greeting: str = Field("Hi {first_name},", description="The first line of a copied message.")
    actions_heading: str = Field("Action items with you:", description="The line above someone's action items.")
    closing: str = Field("Thanks!", description="The last line of a copied message.")
    date_format: str = Field("%a, %b %d", description="How dates appear in messages (strftime codes).")


class LanguageFile(FileModel):
    messages: MessageSettings = Field(default_factory=MessageSettings, description="Wording of copied messages.")
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
}


class UiFile(FileModel):
    wording: dict[str, str] = Field(
        default_factory=dict,
        description="Overrides for the UI's wording sheet, by key (see web/src/wording/en.json for the keys).",
    )
    shortcuts: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_SHORTCUTS),
        description="Single-key shortcuts by action; they never fire while typing.",
    )
    narrow_below_px: int = Field(900, ge=320, description="Below this width the screen uses one column.")
    toast_seconds: float = Field(7, ge=0, description="How long an undo toast stays; 0 keeps toasts until dismissed.")

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
    id: str = Field("", min_length=1, description="Stable stage identifier, unique within this record type.")
    label: str = Field("", description="Editable wording for this stage; changing it does not change stored data.")
    entry: list[str] = Field(
        default_factory=list, description="Deterministic check or standing rule ids required on entry."
    )
    starts: list[str] = Field(
        default_factory=list, description="Task kinds requested on entry, waiting for the person's go."
    )


class TypeStages(ConfigModel):
    moves: Literal["person", "rule"] | None = Field(None, description="Override the workspace move mode for this type.")
    stages: list[StageDefinition] = Field(
        default_factory=list, description="Ordered stages; an empty list removes pack stages."
    )

    @model_validator(mode="before")
    @classmethod
    def list_form(cls, value):
        return {"stages": value} if isinstance(value, list) else value

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [stage.id for stage in self.stages]
        if len(ids) != len(set(ids)):
            raise ValueError("stage ids must be unique within a record type")
        return self


class StagesFile(FileModel):
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
        for key in set(value) - {"version", "moves", "types"}:
            if key in types:
                raise ValueError(f"record type {key} is configured twice")
            types[key] = value.pop(key)
        value["types"] = types
        return value


# ---- registry --------------------------------------------------------------------------------------------------------

#: Config file name (without .yaml) to its model, in the order `config show` lists them.
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
}

#: The newest version each file format has reached.
CURRENT_VERSIONS: dict[str, int] = {name: 1 for name in FILES}
