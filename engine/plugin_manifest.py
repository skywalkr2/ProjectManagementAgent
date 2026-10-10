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
    ops: list[str] = Field(default_factory=list)
    op_validators: list[str] = Field(default_factory=list)
    ai_task_kinds: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    today: list[str] = Field(default_factory=list)
    jobs: list[str] = Field(default_factory=list)
    playbook: str | None = None


class Manifest(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str
    plugin_api: str
    description: str
    depends_on: list[Dependency] = Field(default_factory=list)
    interfaces: Interfaces = Field(default_factory=Interfaces)
    subscribes: list[str] = Field(default_factory=list)
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

        for category in ("record_types", "ops", "ai_task_kinds", "panels", "today", "jobs"):
            names = getattr(self.provides, category)
            if len(set(names)) != len(names):
                raise ValueError(f"duplicate {category}")
            if any(not re.fullmatch(re.escape(self.name) + r"/[a-z][a-z0-9_.-]*", n) for n in names):
                raise ValueError(f"{category} identifiers must be namespaced {self.name}/<name>")
        if len(set(self.subscribes)) != len(self.subscribes):
            raise ValueError("duplicate event subscription")
        return self


def read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
