"""Config file schemas.

Each config file is one model. Every field has a default and a description: the description feeds the comment block
written into new config files, the settings forms and `cockpit config show`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigModel(BaseModel):
    """Base for config models: unknown keys are errors, so a typo never silently does nothing."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class FileModel(ConfigModel):
    """Base for a whole config file."""

    version: int = Field(1, description="Format version of this file. Older files are migrated at start.")


# ---- config/workspace.yaml -------------------------------------------------------------------------------------------


class UserSettings(ConfigModel):
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


class StorageFile(FileModel):
    backend: Literal["sqlite"] = Field("sqlite", description="Where records live. Postgres comes later.")
    export: ExportSettings = Field(default_factory=ExportSettings, description="The readable export and its history.")


# ---- registry --------------------------------------------------------------------------------------------------------

#: Config file name (without .yaml) to its model, in the order `config show` lists them.
FILES: dict[str, type[FileModel]] = {
    "workspace": WorkspaceFile,
    "server": ServerFile,
    "storage": StorageFile,
}

#: The newest version each file format has reached.
CURRENT_VERSIONS: dict[str, int] = {name: 1 for name in FILES}
