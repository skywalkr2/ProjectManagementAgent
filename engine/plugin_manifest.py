"""A plugin's manifest, `plugin.yaml`, beside its package. It is read and checked before any plugin code is imported:
unknown keys are errors, and what the code registers must match `provides` and `subscribes` exactly."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from engine.yaml_load import load_yaml


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
    network: list[str] = Field(
        default_factory=list,
        description="Hosts the plugin's connectors may reach through the core's web client (\"api.example.com\", "
        '"*.example.com"); nothing else is reachable.',
    )
    secrets: list[str] = Field(
        default_factory=list,
        description="Names of the secrets the plugin may read (a key, a sign-in token): set per workspace in "
        "workspace.plugins.secrets, or kept on this computer by the plugin itself.",
    )

    @field_validator("network")
    @classmethod
    def _hosts(cls, value: list[str]) -> list[str]:
        for host in value:
            if not re.fullmatch(r"(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+|localhost", host):
                raise ValueError(f"{host!r} isn't a host name (write api.example.com or *.example.com)")
        return value

    @field_validator("secrets")
    @classmethod
    def _secret_names(cls, value: list[str]) -> list[str]:
        for name in value:
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", name):
                raise ValueError(f"{name!r} isn't a secret name (lowercase letters, digits, dashes)")
        return value

    data_levels: list[Literal["open", "internal", "restricted"]] = Field(
        default_factory=lambda: ["open", "internal"],
        description="Every data level the plugin's record types and file kinds use, the default internal included.",
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
    extractors: list[str] = Field(
        default_factory=list, description="Readers that turn files of some media types into text."
    )
    derived_files: list[str] = Field(
        default_factory=list, description="Files the plugin generates from its records into each project's folder."
    )
    panels: list[str] = Field(default_factory=list, description="Screens listing records, described as data.")
    today: list[str] = Field(default_factory=list, description="Contributors of lines on Today.")
    jobs: list[str] = Field(default_factory=list, description="Work run on a schedule while the app runs.")
    setup_steps: list[str] = Field(default_factory=list, description="Steps added to the first-run setup.")
    data_forms: list[str] = Field(
        default_factory=list, description="Kinds of data file the screens offer a form for, checked by a schema."
    )
    connectors: list[str] = Field(default_factory=list, description="Places the assistant can keep reading.")
    connector_reads: dict[str, Literal["mail", "calendar"]] = Field(
        default_factory=dict,
        description="What each of the plugin's connectors reads, by connector: mail or calendar. The setup "
        "walkthrough offers an add-on that signs in and reads mail or a calendar as a service to connect, also "
        "before it is installed. A connector left out is told apart by its name.",
    )
    triage_matchers: list[str] = Field(default_factory=list, description="Rule kinds for triaging watched changes.")
    scorers: list[str] = Field(
        default_factory=list,
        description="Deterministic scorers for what only the plugin can judge, which a case in its evaluation folder "
        "names with `score:`.",
    )
    value_lists: list[str] = Field(
        default_factory=list, description="Value lists the plugin's record fields take their values from."
    )
    sign_ins: list[str] = Field(
        default_factory=list, description="Sign-ins to a service, through its own sign-in page, as the person."
    )
    help: list[str] = Field(
        default_factory=list,
        description="Help files the plugin ships (Markdown, one section per ## heading, paths relative to its "
        "manifest) that asking the assistant reads and cites, like the user guide. Only ## sections are read: text "
        "before the first ## heading is left out.",
    )

    wording: list[str] = Field(
        default_factory=list,
        description="Wording files the plugin ships (YAML maps from a wording key to its text, paths relative to its "
        "manifest): what the screens call the plugin's own kinds, e.g. stages.group.<plugin>/<kind>. Every key "
        "names something in the plugin's namespace; the workspace's ui.wording overrides any of them.",
    )

    @field_validator("connector_reads")
    @classmethod
    def _reads_name_connectors(cls, value: dict[str, str], info: ValidationInfo) -> dict[str, str]:
        listed = info.data.get("connectors", [])
        wild = tuple(item[:-1] for item in listed if item.endswith("/*"))
        unknown = sorted(name for name in value if name not in listed and not name.startswith(wild))
        if unknown:
            raise ValueError(f"{', '.join(unknown)}: connector_reads names only connectors listed in connectors")
        return value

    @field_validator("help")
    @classmethod
    def _help_paths(cls, value: list[str]) -> list[str]:
        for path in value:
            if path.startswith("/") or ".." in Path(path).parts or not path.endswith(".md"):
                raise ValueError(f"{path!r}: a help file is a .md path inside the plugin")
        return value

    @field_validator("wording")
    @classmethod
    def _wording_paths(cls, value: list[str]) -> list[str]:
        for path in value:
            if path.startswith("/") or ".." in Path(path).parts or not path.endswith((".yaml", ".yml")):
                raise ValueError("a wording file must be a YAML file inside the plugin")
        return value

    playbook: str | None = Field(None, description="The plugin's own playbook. Not yet available.")
    evals: str | None = Field(
        None,
        description="A folder beside plugin.yaml holding the plugin's own evaluation cases, in the core's format; "
        "`cockpit evaluate` runs them while the plugin is enabled.",
    )
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
            "extractors",
            "derived_files",
            "panels",
            "today",
            "jobs",
            "scorers",
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


#: What each part of a manifest is called in a message a person reads.
MANIFEST_PARTS = {
    "name": "its name",
    "version": "its version",
    "plugin_api": "the versions of the app it works with",
    "description": "its description",
    "depends_on": "the add-ons it needs",
    "interfaces": "how it works with other add-ons",
    "subscribes": "the events it handles",
    "provides": "what it provides",
    "config_schema": "its settings",
    "requires": "what it may reach and needs",
    "entry": "where it starts",
}


def _position(loc: list[str]) -> list[str]:
    return [f"item {int(x) + 1}" if x.isdigit() else x for x in loc]


def plain_error(err: ValidationError, parts: dict[str, str] | None = None) -> str:
    """A validation failure in plain words: where it is (a named part of the manifest, else a setting), then what is
    wrong. Nothing of the validator's own wording (error types, links, echoed input) is kept."""
    lines = []
    for found in err.errors():
        loc = [str(x) for x in found["loc"]]
        if found["type"] == "missing":
            what = "is missing"
        elif found["type"] == "extra_forbidden":
            what = "isn't something this app knows" if parts else "isn't a setting it has"
        else:
            what = found["msg"].removeprefix("Value error, ")
        if parts:
            where = parts.get(loc[0], f"'{loc[0]}'") if loc else "it"
        else:
            where = f"the setting '{loc[0]}'" if loc else "its settings"
        rest = _position(loc[1:])
        lines.append(f"{where}{' (' + ', '.join(rest) + ')' if rest else ''}: {what}")
    return "; ".join(lines)


def read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(load_yaml(path.read_text(encoding="utf-8")))


def shipped_plugins() -> set[str]:
    """The add-ons that come with the app itself (its own `plugins` folder): samples and building kits for trying things
    and making add-ons, not ones the person installed."""
    root = Path(__file__).resolve().parents[1] / "plugins"
    return {path.parent.name for path in root.glob("*/plugin.yaml")}


def plugin_paths(config_dir: Path | None, enabled: list[str] | None):
    """Where each available plugin's manifest is, as (name, path), without executing plugin code: the enabled
    plugins', or with `enabled` None, every installed plugin's."""
    from importlib.metadata import entry_points

    roots = [Path(__file__).resolve().parents[1] / "plugins"]
    if config_dir is not None:
        roots.append(config_dir.parent / "plugins")
    paths = [(path.parent.name, path) for root in roots for path in root.glob("*/plugin.yaml")]
    for ep in entry_points(group="pm_cockpit.plugins"):
        if ep.name not in {name for name, _ in paths}:
            paths.append((ep.name, installed_manifest(ep)))
    for name, path in paths:
        if enabled is None or name in enabled:
            yield name, path


def declared_plugins(config_dir: Path | None, enabled: list[str] | None):
    """Read available declarations without executing plugin code: the enabled plugins', or with `enabled` None,
    every installed plugin's."""
    for _name, path in plugin_paths(config_dir, enabled):
        try:
            yield read_manifest(path)
        except (ValueError, OSError):
            # The host reports invalid plugins; stage references still fail closed.
            continue
