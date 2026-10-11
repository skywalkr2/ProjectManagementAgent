"""Manifests are read and checked before importing plugin code."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dependency(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str

    @field_validator("version")
    @classmethod
    def version_range(cls, value: str) -> str:
        SpecifierSet(value)
        return value


class InterfaceUse(Strict):
    interface: str
    optional: bool = False


class Interfaces(Strict):
    provides: list[str] = Field(default_factory=list)
    uses: list[InterfaceUse] = Field(default_factory=list)


class Tool(Strict):
    name: str
    min_version: str
    probe: str
    optional: bool = False
    features: list[str] = Field(default_factory=list)


class Requires(Strict):
    network: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    data_levels: list[Literal["open", "internal", "restricted"]] = Field(default_factory=lambda: ["open", "internal"])
    tools: list[Tool] = Field(default_factory=list)


class Provides(Strict):
    record_types: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    stage_checks: list[str] = Field(default_factory=list)
    ops: list[str] = Field(default_factory=list)
    op_validators: list[str] = Field(default_factory=list)
    ai_task_kinds: list[str] = Field(default_factory=list)
    file_kinds: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    today: list[str] = Field(default_factory=list)
    jobs: list[str] = Field(default_factory=list)
    playbook: str | None = None


class Subscription(Strict):
    event: str
    kinds: list[str] = Field(default_factory=list, description="Only records of these kinds; empty means every kind.")


class Manifest(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str
    plugin_api: str
    description: str
    depends_on: list[Dependency] = Field(default_factory=list)
    interfaces: Interfaces = Field(default_factory=Interfaces)
    subscribes: list[str | Subscription] = Field(default_factory=list)
    provides: Provides = Field(default_factory=Provides)
    config_schema: str
    requires: Requires = Field(default_factory=Requires)
    entry: str

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
            "panels",
            "today",
            "jobs",
        )
        for category in categories:
            names = getattr(self.provides, category)
            if len(set(names)) != len(names):
                raise ValueError(f"duplicate {category}")
            if any(not re.fullmatch(re.escape(self.name) + r"/[a-z][a-z0-9_.-]*", n) for n in names):
                raise ValueError(f"{category} identifiers must be namespaced {self.name}/<name>")
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
        module = ep.value.split(":")[0].split(".")[0]
        paths.append((ep.name, Path(ep.dist.locate_file(module)) / "plugin.yaml"))
    for name, path in paths:
        if name in enabled:
            try:
                yield read_manifest(path)
            except (ValueError, OSError):
                # The host reports invalid plugins; stage references still fail closed.
                continue
