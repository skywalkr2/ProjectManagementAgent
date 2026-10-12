"""Layered config loading: built-in defaults, then config files, then environment variables, then command-line flags.

Each layer may set any key. The effective value of every key, and the layer it came from, is kept so that
`cockpit config show` can explain it.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from engine.config.schema import CURRENT_VERSIONS, FILES, FileModel

ENV_PREFIX = "COCKPIT__"
LAYERS = ("default", "file", "env", "flag")


class ConfigError(Exception):
    """A config file or value can't be used. The message says which file and key, and why; it is for the terminal.
    `plain` says the same without a file name, key or command, for the screen."""

    def __init__(self, message: str, plain: str | None = None) -> None:
        super().__init__(message)
        self.plain = plain or "a settings file has a value that isn't allowed"


@dataclass
class Config:
    """The effective configuration: one validated model per file, plus where each key's value came from."""

    files: dict[str, FileModel]
    sources: dict[str, str] = field(default_factory=dict)
    #: Values found under keys that moved to records (one source of truth), by dotted key; the app moves them at start.
    moved: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        files = self.__dict__.get("files", {})
        if name in files:
            return files[name]
        raise AttributeError(name)

    def value(self, key: str) -> Any:
        """The effective value at a dotted key ("ai.content_levels"), a whole mapping included; None when unset."""
        name, _, rest = key.partition(".")
        model = self.files.get(name)
        if model is None:
            return None
        data: Any = model.model_dump(mode="json")
        for part in rest.split(".") if rest else []:
            if not isinstance(data, Mapping) or part not in data:
                return None
            data = data[part]
        return data

    def flat(self) -> list[tuple[str, Any, str]]:
        """Every key as (dotted path, value, layer), in file order."""
        rows: list[tuple[str, Any, str]] = []
        for name, model in self.files.items():
            for path, value in _flatten(model.model_dump(mode="json"), name):
                rows.append((path, value, self.sources.get(path, "default")))
        return rows


#: Keys whose data now lives on a record (one source of truth): the PM's name and aliases are on their person record.
MOVED_TO_RECORDS = ("workspace.user.full_name", "workspace.user.aliases")


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

    moved: dict[str, Any] = {}
    for name in FILES:
        data: dict[str, Any] = {}
        if config_dir is not None:
            path = config_dir / f"{name}.yaml"
            if path.exists():
                data = _read_yaml(path)
                _check_version(name, data, path)
                for key in MOVED_TO_RECORDS:
                    file, *rest = key.split(".")
                    holder = data if file == name else None
                    for part in rest[:-1]:
                        holder = holder.get(part) if isinstance(holder, dict) else None
                    if isinstance(holder, dict) and rest[-1] in holder:
                        moved[key] = holder.pop(rest[-1])
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
            raise _describe(name, err) from None
    cfg = Config(files=files, sources=sources, moved=moved)
    from engine.config.stages import validate_declared

    validate_declared(cfg, config_dir)
    return cfg


def defaults() -> dict[str, FileModel]:
    """A fresh default model for every config file."""
    return {name: model() for name, model in FILES.items()}


def render_default_file(name: str, values: FileModel | None = None) -> str:
    """The YAML text of a config file (at its defaults, or with the given values), with every key's description as a
    comment above it."""
    model = FILES[name]
    lines = [f"# {name}.yaml: every key has a default; delete a key to go back to it."]
    lines += _render_model(values if values is not None else model(), model, 0)
    return "\n".join(lines) + "\n"


# ---- internals -------------------------------------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise ConfigError(f"{path.name}: not valid YAML ({err})", "a settings file isn't written correctly") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: the top level must be a set of keys", "a settings file isn't laid out right")
    return data


def _check_version(name: str, data: dict[str, Any], path: Path) -> None:
    version = data.get("version", 1)
    if not isinstance(version, int):
        raise ConfigError(f"{path.name}: version must be a whole number", "a settings file's version isn't a number")
    if version > CURRENT_VERSIONS[name]:
        raise ConfigError(
            f"{path.name} is version {version}, newer than this program understands "
            f"({CURRENT_VERSIONS[name]}). Upgrade the program before using this workspace.",
            "a settings file is from a newer version of the app; update the app before using this workspace",
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


def plain_label(description: str) -> str:
    """What to call a setting on screen: the first sentence of its description, minus any parenthetical."""
    first = re.split(r"(?<=[.!?])\s+", description.strip())[0].rstrip(".!?")
    return re.sub(r"\s*\([^)]*\)", "", first).strip()


def field_label(model: type[BaseModel], loc: Iterable[Any]) -> str | None:
    """The plain label of the setting a validation error points at (the innermost field known by name), or None."""
    current: Any = model
    label = None
    for part in loc:
        fields = getattr(current, "model_fields", None)
        if not fields or part not in fields:
            break
        info = fields[part]
        label = plain_label(info.description) if info.description else label
        current = info.annotation
    return label or None


def refusal_text(model: type[BaseModel], err: ValidationError) -> str:
    """A validation error as one sentence for the screen: which setting, and what is wrong with its value."""
    first = err.errors()[0]
    msg = first["msg"].removeprefix("Value error, ")
    label = field_label(model, first["loc"])
    more = f" ({len(err.errors()) - 1} more)" if len(err.errors()) > 1 else ""
    return (f"“{label}” isn't allowed: {msg}" if label else f"a setting isn't allowed: {msg}") + more


def _describe(name: str, err: ValidationError) -> ConfigError:
    problems = []
    for item in err.errors():
        where = ".".join(str(p) for p in item["loc"]) or "(file)"
        problems.append(f"{name}.{where}: {item['msg']}")
    return ConfigError(f"{name}.yaml has problems:\n  " + "\n  ".join(problems), plain=refusal_text(FILES[name], err))


def _render_model(instance: BaseModel, model: type[BaseModel], indent: int) -> list[str]:
    lines: list[str] = []
    pad = "  " * indent
    plain = instance.model_dump(mode="json")
    for key, info in model.model_fields.items():
        value = getattr(instance, key)
        if info.description:
            lines.append(f"{pad}# {info.description}")
        if isinstance(value, BaseModel):
            lines.append(f"{pad}{key}:")
            lines += _render_model(value, type(value), indent + 1)
        elif isinstance(plain[key], (dict, list)) and plain[key]:
            dumped = yaml.safe_dump({key: plain[key]}, sort_keys=False, default_flow_style=None).rstrip("\n")
            lines += [pad + line for line in dumped.splitlines()]
        else:
            lines.append(f"{pad}{key}: {json.dumps(plain[key], ensure_ascii=False)}")
    return lines
