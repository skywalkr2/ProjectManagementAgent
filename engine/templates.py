"""Workspace templates: a name, a description and settings for plugins, applied to a workspace or saved from one.

A template file looks like:

    name: Client work
    description: One line on what it sets up.
    plugins:
      <plugin>: {<its settings>}

Applying one turns those plugins on and merges their settings into `config/plugins/<plugin>.yaml`: values already set
stay as they are, and in a list of entries with ids (item types, stages) entries are added by id and existing ones are
left alone. Every merged file is checked against the plugin's settings schema before anything is written. Starting
templates ship with the product (`engine.shipped`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from engine.shipped import shipped as shipped_folder

SHIPPED = shipped_folder("templates")


class TemplateError(Exception):
    """A template can't be read or applied; the message says why."""


def shipped() -> list[dict[str, Any]]:
    """The starting templates: {id, name, description, path} each."""
    found = []
    for path in sorted(SHIPPED.glob("*.yaml")):
        data = _read(path)
        found.append({"id": path.stem, "name": data["name"], "description": data.get("description", ""), "path": path})
    return found


def find(name_or_path: str) -> Path:
    """A shipped template by id, or a template file by path."""
    path = Path(name_or_path).expanduser()
    if path.is_file():
        return path
    shipped_path = SHIPPED / f"{name_or_path}.yaml"
    if shipped_path.is_file():
        return shipped_path
    raise TemplateError(f"there is no template {name_or_path}; see `cockpit template list`")


def _read(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as err:
        raise TemplateError(f"{path.name} can't be read: {err}") from None
    if not isinstance(data, dict) or not data.get("name") or not isinstance(data.get("plugins", {}), dict):
        raise TemplateError(f"{path.name} isn't a template: it needs a name and a plugins section")
    return data


def merge(current: Any, incoming: Any) -> Any:
    """Settings from a template laid over current ones without changing what is already set."""
    if isinstance(current, dict) and isinstance(incoming, dict):
        out = dict(current)
        for key, value in incoming.items():
            out[key] = merge(current[key], value) if key in current else value
        return out
    if isinstance(current, list) and isinstance(incoming, list):
        if all(isinstance(e, dict) and "id" in e for e in [*current, *incoming]):
            ids = {e["id"] for e in current}
            return [*current, *[e for e in incoming if e["id"] not in ids]]
        return current
    return current


def apply(ws: Any, name_or_path: str) -> list[str]:
    """Apply a template to a workspace. Returns the plugins it set up."""
    from engine.config import load_config
    from engine.plugin_host import BUNDLED

    template = _read(find(name_or_path))
    plugins: dict[str, Any] = template.get("plugins") or {}
    settings_dir = ws.config_dir / "plugins"
    merged: dict[str, Any] = {}
    for plugin, settings in plugins.items():
        path = settings_dir / f"{plugin}.yaml"
        current = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        merged[plugin] = merge(current or {}, settings or {})
        _check(plugin, merged[plugin], ws, BUNDLED)
    workspace_file = ws.config_dir / "workspace.yaml"
    text = workspace_file.read_text(encoding="utf-8")
    settings_dir.mkdir(parents=True, exist_ok=True)
    for plugin, settings in merged.items():
        (settings_dir / f"{plugin}.yaml").write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    workspace_file.write_text(_enabled(text, list(plugins)), encoding="utf-8")
    load_config(ws.config_dir)  # the whole workspace's settings still load
    return list(plugins)


def _enabled(text: str, plugins: list[str]) -> str:
    """workspace.yaml with these plugins turned on, keeping its comments and layout where the list is written on one
    line (`enabled: [a, b]`); otherwise rewritten."""
    workspace = yaml.safe_load(text) or {}
    enabled = list((workspace.get("plugins") or {}).get("enabled") or [])
    wanted = [*enabled, *[p for p in plugins if p not in enabled]]
    if wanted == enabled:
        return text
    match = re.search(r"^(\s+enabled:\s*)\[[^\]\n]*\]", text, re.M)
    if match is not None:
        return text[: match.start()] + match.group(1) + "[" + ", ".join(wanted) + "]" + text[match.end() :]
    workspace.setdefault("plugins", {})["enabled"] = wanted
    return yaml.safe_dump(workspace, sort_keys=False)


def _check(plugin: str, settings: dict[str, Any], ws: Any, bundled: Path) -> None:
    """Check merged settings against the plugin's settings schema, without starting the plugin."""
    from engine.plugin_host import PluginHost

    for root in (ws.root / "plugins", bundled):
        if (root / plugin / "plugin.yaml").is_file():
            break
    else:
        raise TemplateError(f"the template sets up {plugin}, which isn't installed")
    schema = PluginHost.settings_schema(root / plugin / "plugin.yaml")
    try:
        schema.model_validate(settings)
    except ValueError as err:
        raise TemplateError(f"the template's settings for {plugin} don't fit: {err}") from None


def save(ws: Any, path: Path, name: str, description: str, plugins: list[str]) -> Path:
    """Write the named plugins' current settings as a template file."""
    out: dict[str, Any] = {"name": name, "description": description, "plugins": {}}
    for plugin in plugins:
        settings_path = ws.config_dir / "plugins" / f"{plugin}.yaml"
        if not settings_path.exists():
            raise TemplateError(f"{plugin} has no settings in this workspace")
        out["plugins"][plugin] = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    path.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
    return path
