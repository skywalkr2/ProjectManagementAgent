"""A plugin's manifest, `plugin.yaml`, beside its package. It is read and checked before any plugin code is imported:
unknown keys are errors, and what the code registers must match `provides` and `subscribes` exactly."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dependency(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$", description="The other plugin's name; it must be enabled too.")
    version: str = Field(description="A version range the other plugin must satisfy, such as '>=1.0,<2'.")

    @field_validator("version")
    @classmethod
    def version_range(cls, value: str) -> str:
        SpecifierSet(value)
        return value


#: Manifest keys the host refuses until the extension point behind them exists (a non-empty value refuses the plugin).
NOT_YET = {
    "requires.network": "network hosts a plugin may reach",
    "requires.secrets": "secrets a plugin may read",
    "provides.playbook": "a plugin's own playbook",
}


INTERFACE_USE = r"([a-z0-9-]+/[a-z0-9-]+)@([0-9]+)(?:\.([0-9]+))?"


class InterfaceUse(Strict):
    interface: str = Field(
        description='The interface and the oldest version that works: "<name>@<major>" or "<name>@<major>.<minor>".'
    )
    optional: bool = Field(False, description="The plugin still works when no enabled plugin provides it.")

    @field_validator("interface")
    @classmethod
    def _shape(cls, value: str) -> str:
        if not re.fullmatch(INTERFACE_USE, value):
            raise ValueError('use an interface as "<plugin>/<name>@<major>" or "@<major>.<minor>"')
        return value


class Interfaces(Strict):
    defines: list[str] = Field(default_factory=list, description="Interfaces this plugin defines, by name.")
    provides: list[str] = Field(
        default_factory=list, description='Interfaces this plugin provides, as "<plugin>/<name>@<major>".'
    )
    uses: list[InterfaceUse] = Field(default_factory=list, description="Interfaces this plugin reads or requests.")


class Tool(Strict):
    name: str = Field(description="The program's name: how it is found on the PATH and how its probe starts.")
    min_version: str = Field(description="The oldest version that works; empty accepts any version.")
    probe: str = Field(
        description="A command that prints the version, starting with the name, e.g. 'renderer --version'."
    )
    optional: bool = Field(False, description="Missing is allowed: the plugin runs and the features listed turn off.")
    features: list[str] = Field(default_factory=list, description="What turns off without it, in plain words.")


class Requires(Strict):
    network: list[str] = Field(default_factory=list, description="Hosts the plugin may reach. Not yet available.")
    secrets: list[str] = Field(default_factory=list, description="Secrets the plugin may read. Not yet available.")
    data_levels: list[Literal["open", "internal", "restricted"]] = Field(
        default_factory=lambda: ["open", "internal"],
        description="Every data level the plugin's record types use, the default internal included.",
    )
    tools: list[Tool] = Field(default_factory=list, description="Outside programs the plugin runs.")


class Provides(Strict):
    """What the plugin registers, by identifier. A list may be just `<plugin>/*` when the plugin's own settings
    define the identifiers (the kit's item types, say); the host then accepts any identifier in its namespace."""

    record_types: list[str] = Field(default_factory=list, description="Record kinds the plugin registers.")
    stages: list[str] = Field(default_factory=list, description="Own record kinds the plugin gives default stages.")
    stage_checks: list[str] = Field(default_factory=list, description="Stage entry checks the plugin registers.")
    ops: list[str] = Field(default_factory=list, description="Ops the plugin registers.")
    op_validators: list[str] = Field(
        default_factory=list, description="Core or own ops the plugin registers a validator for."
    )
    ai_task_kinds: list[str] = Field(default_factory=list, description="AI task kinds the plugin registers.")
    file_kinds: list[str] = Field(default_factory=list, description="File kinds the plugin registers.")
    actions: list[str] = Field(default_factory=list, description="Person actions the plugin registers.")
    lints: list[str] = Field(default_factory=list, description="Lints the plugin registers.")
    text_formats: list[str] = Field(default_factory=list, description="Long text formats the plugin registers.")
    working_copies: list[str] = Field(default_factory=list, description="Working-copy formats the plugin registers.")
    derived_files: list[str] = Field(
        default_factory=list, description="Files the plugin generates from its records into each project's folder."
    )
    panels: list[str] = Field(default_factory=list, description="Screens listing records, described as data.")
    today: list[str] = Field(default_factory=list, description="Contributors of lines on Today.")
    jobs: list[str] = Field(default_factory=list, description="Work run on a schedule while the app runs.")
    setup_steps: list[str] = Field(default_factory=list, description="Steps added to the first-run setup.")
    playbook: str | None = Field(None, description="The plugin's own playbook. Not yet available.")
    data: str | None = Field(
        None,
        description="A folder beside plugin.yaml holding the data files the plugin ships (templates, word lists); the "
        "workspace overrides them in plugin-data/<plugin>/ and per project in plugin-data/<plugin>/projects/<id>/.",
    )


class Subscription(Strict):
    event: str = Field(description="One of the events listed under Events.")
    kinds: list[str] = Field(
        default_factory=list,
        description="Only records of these kinds (file kinds for file.added); empty means every kind.",
    )


class Manifest(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$", description="The plugin's name and the namespace of its ids.")
    version: str = Field(description="The plugin's own version.")
    plugin_api: str = Field(description="The plugin API versions it works with, e.g. '>=0.3,<0.4'.")
    description: str = Field(description="One line saying what the plugin is for.")
    depends_on: list[Dependency] = Field(default_factory=list, description="Plugins that must be enabled first.")
    interfaces: Interfaces = Field(
        default_factory=Interfaces, description="How it works with other plugins, only through the core."
    )
    subscribes: list[str | Subscription] = Field(
        default_factory=list, description="Events the plugin handles: a name, or {event, kinds}."
    )
    provides: Provides = Field(default_factory=Provides, description="Everything the plugin registers, by id.")
    config_schema: str = Field(description="module:Class of the plugin's Settings subclass.")
    requires: Requires = Field(default_factory=Requires, description="What the plugin may reach and needs.")
    entry: str = Field(description="module:function called with the Registrar at startup.")

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        Version(value)
        return value

    @field_validator("plugin_api")
    @classmethod
    def valid_range(cls, value: str) -> str:
        SpecifierSet(value)
        return value

    @field_validator("entry", "config_schema")
    @classmethod
    def symbol(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*:[a-zA-Z_]\w*", value):
            raise ValueError("expected module:symbol")
        return value

    @model_validator(mode="after")
    def identifiers(self) -> Manifest:
        import re

        categories = (
            "record_types",
            "stages",
            "stage_checks",
            "ops",
            "ai_task_kinds",
            "file_kinds",
            "actions",
            "lints",
            "text_formats",
            "working_copies",
            "derived_files",
            "panels",
            "today",
            "jobs",
        )
        for category in categories:
            names = getattr(self.provides, category)
            if len(set(names)) != len(names):
                raise ValueError(f"duplicate {category}")
            if any(not re.fullmatch(re.escape(self.name) + r"/([a-z][a-z0-9_.-]*|\*)", n) for n in names):
                raise ValueError(f"{category} identifiers must be namespaced {self.name}/<name>")
            if f"{self.name}/*" in names and len(names) > 1:
                raise ValueError(f"{category}: {self.name}/* stands alone (identifiers its settings define)")
        if len(set(self.events())) != len(self.subscribes):
            raise ValueError("duplicate event subscription")
        return self

    def events(self) -> list[str]:
        return [s if isinstance(s, str) else s.event for s in self.subscribes]

    def kinds_for(self, event: str) -> list[str]:
        """The record kinds a subscription is limited to; empty means every kind."""
        for s in self.subscribes:
            if not isinstance(s, str) and s.event == event:
                return list(s.kinds)
        return []


def installed_manifest(entry_point: object) -> Path:
    """Where an installed plugin's plugin.yaml is: beside its top-level package, found without importing it. Works for
    built wheels and for editable (development) installs, whose package lives in the source checkout."""
    import importlib.util

    module = entry_point.value.split(":")[0].split(".")[0]
    spec = importlib.util.find_spec(module)
    if spec is not None and spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            if (Path(location) / "plugin.yaml").is_file():
                return Path(location) / "plugin.yaml"
    return Path(entry_point.dist.locate_file(module)) / "plugin.yaml"


def read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def declared_plugins(config_dir: Path | None, enabled: list[str]):
    """Read available declarations without executing plugin code."""
    from importlib.metadata import entry_points

    roots = [Path(__file__).resolve().parents[1] / "plugins"]
    if config_dir is not None:
        roots.append(config_dir.parent / "plugins")
    paths = [(path.parent.name, path) for root in roots for path in root.glob("*/plugin.yaml")]
    for ep in entry_points(group="pm_cockpit.plugins"):
        if ep.name not in {name for name, _ in paths}:
            paths.append((ep.name, installed_manifest(ep)))
    for name, path in paths:
        if name in enabled:
            try:
                yield read_manifest(path)
            except (ValueError, OSError):
                # The host reports invalid plugins; stage references still fail closed.
                continue
