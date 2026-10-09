"""Layered config loading: built-in defaults, then config files, then environment variables, then command-line flags.

Each layer may set any key. The effective value of every key, and the layer it came from, is kept so that
`cockpit config show` can explain it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from engine.config.schema import CURRENT_VERSIONS, FILES, FileModel

ENV_PREFIX = "COCKPIT__"
LAYERS = ("default", "file", "env", "flag")


class ConfigError(Exception):
    """A config file or value can't be used. The message says which file and key, and why."""


@dataclass
class Config:
    """The effective configuration: one validated model per file, plus where each key's value came from."""

    files: dict[str, FileModel]
    sources: dict[str, str] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        files = self.__dict__.get("files", {})
        if name in files:
            return files[name]
        raise AttributeError(name)

    def flat(self) -> list[tuple[str, Any, str]]:
        """Every key as (dotted path, value, layer), in file order."""
        rows: list[tuple[str, Any, str]] = []
        for name, model in self.files.items():
            for path, value in _flatten(model.model_dump(mode="json"), name):
                rows.append((path, value, self.sources.get(path, "default")))
        return rows


def load_config(
    config_dir: Path | None,
    *,
    env: Mapping[str, str] | None = None,
    flags: Mapping[str, Any] | None = None,
) -> Config:
    """Build the effective config. `flags` maps dotted keys (e.g. "server.port") to values from the command line."""
    env = os.environ if env is None else env
    raw: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}

    for name in FILES:
        data: dict[str, Any] = {}
        if config_dir is not None:
            path = config_dir / f"{name}.yaml"
            if path.exists():
                data = _read_yaml(path)
                _check_version(name, data, path)
                for key, _ in _flatten(data, name):
                    sources[key] = "file"
        raw[name] = data

    for key, value in _env_values(env).items():
        _set_dotted(raw, key, value)
        sources[key] = "env"

    for key, value in (flags or {}).items():
        if value is None:
            continue
        _set_dotted(raw, key, value)
        sources[key] = "flag"

    files: dict[str, FileModel] = {}
    for name, model in FILES.items():
        try:
            files[name] = model.model_validate(raw[name])
        except ValidationError as err:
            raise ConfigError(_describe(name, err)) from None
    return Config(files=files, sources=sources)


def defaults() -> dict[str, FileModel]:
    """A fresh default model for every config file."""
    return {name: model() for name, model in FILES.items()}


def render_default_file(name: str) -> str:
    """The YAML text of a config file at its defaults, with every key's description as a comment above it."""
    model = FILES[name]
    lines = [f"# {name}.yaml: every key has a default; delete a key to go back to it."]
    lines += _render_model(model(), model, 0)
    return "\n".join(lines) + "\n"


# ---- internals -------------------------------------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise ConfigError(f"{path.name}: not valid YAML ({err})") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: the top level must be a set of keys")
    return data


def _check_version(name: str, data: dict[str, Any], path: Path) -> None:
    version = data.get("version", 1)
    if not isinstance(version, int):
        raise ConfigError(f"{path.name}: version must be a whole number")
    if version > CURRENT_VERSIONS[name]:
        raise ConfigError(
            f"{path.name} is version {version}, newer than this program understands "
            f"({CURRENT_VERSIONS[name]}). Upgrade the program before using this workspace."
        )


def _env_values(env: Mapping[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, text in env.items():
        if not key.startswith(ENV_PREFIX):
            continue
        parts = [p.lower() for p in key[len(ENV_PREFIX) :].split("__") if p]
        if len(parts) < 2 or parts[0] not in FILES:
            continue
        values[".".join(parts)] = yaml.safe_load(text) if text != "" else ""
    return values


def _set_dotted(raw: dict[str, dict[str, Any]], dotted: str, value: Any) -> None:
    name, *path = dotted.split(".")
    if name not in raw:
        raise ConfigError(f"unknown config file in {dotted!r}")
    node = raw[name]
    for part in path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[path[-1]] = value


def _flatten(data: Mapping[str, Any], prefix: str) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in data.items():
        path = f"{prefix}.{key}"
        if isinstance(value, Mapping) and value:
            rows += _flatten(value, path)
        else:
            rows.append((path, value))
    return rows


def _describe(name: str, err: ValidationError) -> str:
    problems = []
    for item in err.errors():
        where = ".".join(str(p) for p in item["loc"]) or "(file)"
        problems.append(f"{name}.{where}: {item['msg']}")
    return f"{name}.yaml has problems:\n  " + "\n  ".join(problems)


def _render_model(instance: BaseModel, model: type[BaseModel], indent: int) -> list[str]:
    lines: list[str] = []
    pad = "  " * indent
    for key, info in model.model_fields.items():
        value = getattr(instance, key)
        if info.description:
            lines.append(f"{pad}# {info.description}")
        if isinstance(value, BaseModel):
            lines.append(f"{pad}{key}:")
            lines += _render_model(value, type(value), indent + 1)
        else:
            dumped = yaml.safe_dump({key: value}, default_flow_style=True, sort_keys=False).strip()
            lines.append(f"{pad}{dumped.removeprefix('{').removesuffix('}')}")
    return lines
