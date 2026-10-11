"""Editing a plugin's data files through forms: the `.yaml` files of a declared kind, across the plugin's data layers
(what it ships, the workspace's, a project's), each checked against the kind's schema. A save never touches the
shipped layer: it writes the workspace's or a project's copy, and returns the copy's text from before so it can be
undone. The plugin goes on reading the files through `view.data`."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from engine.storage import StoreError

LAYERS = ("shipped", "workspace", "project")
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\.yaml")


def _form(host: Any, name: str) -> Any:
    plugin = name.split("/", 1)[0]
    registrar = host.registrars.get(plugin)
    form = registrar.data_forms.get(name) if registrar is not None and host.active(plugin) else None
    if form is None:
        raise StoreError(f"there is no data form {name} running now")
    return form


def _layers(host: Any, name: str, project: str | None) -> dict[str, Path]:
    """The data folders by layer, for this form's folder."""
    form = _form(host, name)
    plugin = name.split("/", 1)[0]
    found = host.data_layers(plugin, project)
    shipped = bool(host.manifests[plugin].provides.data)
    names = (["shipped"] if shipped else []) + ["workspace"] + (["project"] if project else [])
    return {layer: folder / form.folder for layer, folder in zip(names, found, strict=False)}


def _file_name(file: str) -> str:
    if not _NAME.fullmatch(file or ""):
        raise StoreError("a data file is named with lowercase letters, digits, - or _, ending in .yaml")
    return file


def files(host: Any, name: str, project: str | None = None) -> list[dict[str, Any]]:
    """Every file of the form's kind: {file, layers (those holding it), layer (the one in effect), problem}."""
    form = _form(host, name)
    layers = _layers(host, name, project)
    names: set[str] = set()
    for folder in layers.values():
        if folder.is_dir():
            names |= {p.name for p in folder.glob("*.yaml") if p.is_file() and _NAME.fullmatch(p.name)}
    found = []
    for file in sorted(names):
        holding = [layer for layer, folder in layers.items() if (folder / file).is_file()]
        values, problem = _load(layers[holding[-1]] / file, form.schema)
        found.append({"file": file, "layers": holding, "layer": holding[-1], "problem": problem})
    return found


def _load(path: Path, schema: Any) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return schema.model_validate(data).model_dump(mode="json"), None
    except (OSError, yaml.YAMLError) as err:
        return None, f"it can't be read: {err}"
    except ValidationError as err:
        first = err.errors()[0]
        return None, f"{'.'.join(map(str, first['loc']))}: {first['msg']}"


def read(host: Any, name: str, file: str, project: str | None = None) -> dict[str, Any]:
    """One file as the form shows it: {values (in effect, or the schema's defaults for a new file), layer, layers,
    problem, defaults}."""
    form = _form(host, name)
    file = _file_name(file)
    layers = _layers(host, name, project)
    holding = [layer for layer, folder in layers.items() if (folder / file).is_file()]
    defaults = form.schema().model_dump(mode="json")
    if not holding:
        return {"values": defaults, "layer": None, "layers": [], "problem": None, "defaults": defaults}
    values, problem = _load(layers[holding[-1]] / file, form.schema)
    return {"values": values, "layer": holding[-1], "layers": holding, "problem": problem, "defaults": defaults}


def _set(data: dict[str, Any], dotted: str, value: Any) -> None:
    *parents, last = dotted.split(".")
    for part in parents:
        data = data.setdefault(part, {})
        if not isinstance(data, dict):
            raise StoreError(f"{dotted} isn't a field of this form")
    data[last] = value


def save(
    host: Any, name: str, file: str, layer: str, changes: dict[str, Any], project: str | None = None
) -> dict[str, Any]:
    """Write the file to the workspace's or a project's layer: the values in effect (or the defaults, for a new
    file) with `changes` (dotted field names) laid over, checked against the schema. Returns {before} (the layer's
    text before, None when it had no copy) for Undo."""
    form = _form(host, name)
    file = _file_name(file)
    if layer not in ("workspace", "project") or (layer == "project" and not project):
        raise StoreError("a data file is saved to the workspace's layer or a project's, never the shipped one")
    target = _layers(host, name, project).get(layer)
    if target is None:
        raise StoreError(f"there is no {layer} layer here")
    current = read(host, name, file, project)
    values = dict(current["values"] or current["defaults"])
    for key, value in changes.items():
        _set(values, key, value)
    try:
        checked = form.schema.model_validate(values).model_dump(mode="json")
    except ValidationError as err:
        first = err.errors()[0]
        raise StoreError(f"{'.'.join(map(str, first['loc']))}: {first['msg']}") from None
    path = target / file
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, yaml.safe_dump(checked, sort_keys=False, allow_unicode=True))
    return {"before": before}


def remove(host: Any, name: str, file: str, layer: str, project: str | None = None) -> dict[str, Any]:
    """Remove the workspace's or a project's copy, so the less specific one is in effect again. Returns {before}."""
    _form(host, name)
    file = _file_name(file)
    if layer not in ("workspace", "project"):
        raise StoreError("only the workspace's or a project's copy can be removed")
    target = _layers(host, name, project).get(layer)
    path = target / file if target is not None else None
    if path is None or not path.is_file():
        raise StoreError(f"there is no {layer} copy of {file}")
    before = path.read_text(encoding="utf-8")
    path.unlink()
    return {"before": before}


def restore(host: Any, name: str, file: str, layer: str, before: str | None, project: str | None = None) -> None:
    """Undo a save or a removal: put the layer's copy back as it was (or remove it, when there was none)."""
    form = _form(host, name)
    file = _file_name(file)
    if layer not in ("workspace", "project"):
        raise StoreError("only the workspace's or a project's copy can be restored")
    target = _layers(host, name, project).get(layer)
    if target is None:
        raise StoreError(f"there is no {layer} layer here")
    path = target / file
    if before is None:
        path.unlink(missing_ok=True)
        return
    try:
        form.schema.model_validate(yaml.safe_load(before) or {})
    except (yaml.YAMLError, ValidationError):
        raise StoreError("that copy doesn't fit the form any more") from None
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, before)


def _write(path: Path, text: str) -> None:
    temporary = path.with_suffix(".yaml.saving")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
