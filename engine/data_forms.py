"""Editing a plugin's data files through forms: the `.yaml` files of a declared kind (those in its folder matching its
pattern), across the plugin's data layers (what it ships, the workspace's, a project's), each checked against the
kind's schema with its defaults checked too. A save never touches the shipped layer: it writes the workspace's or a
project's copy with only the keys that file had plus those the person set, and returns the copy's text from before so
it can be undone. The plugin goes on reading the files through `view.data`."""

from __future__ import annotations

import logging
import re
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from engine.storage import StoreError

log = logging.getLogger(__name__)

LAYERS = ("shipped", "workspace", "project")
_PART = r"[a-z0-9][a-z0-9_-]{0,63}"
_NAME = re.compile(rf"({_PART}/)?{_PART}\.yaml")


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


def _file_name(form: Any, file: str) -> str:
    """A file of this form: a name (or folder/name) of lowercase letters, digits, - and _, matching its pattern."""
    if not _NAME.fullmatch(file or ""):
        raise StoreError(
            "a data file is named with lowercase letters, digits, - or _, ending like the others of its kind"
        )
    if not fnmatchcase(file, form.pattern) or file.count("/") != form.pattern.count("/"):
        raise StoreError("that isn't a file of this kind: its name doesn't fit how the others are named")
    return file


@lru_cache(maxsize=64)
def _checked(schema: type[BaseModel]) -> type[BaseModel]:
    """The schema with its defaults validated too, so a required value left at an empty default is a problem, as
    it is when the plugin uses the file."""
    return type(schema.__name__, (schema,), {"model_config": ConfigDict(**schema.model_config, validate_default=True)})


def _problem(err: ValidationError) -> str:
    """A refusal in words: the field and what is wrong with it, or the file's own rule when a model-level check
    refused it (it has no field)."""
    first = err.errors()[0]
    message = str(first["msg"]).removeprefix("Value error, ").removeprefix("Assertion failed, ")
    where = ".".join(map(str, first["loc"]))
    return f"{where}: {message}" if where else message


def _raw(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """A file's own content (only the keys it has), or why it can't be read."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as err:
        log.warning("A data file couldn't be read: %s", err)
        return None, "it can't be read"
    if not isinstance(data, dict):
        return None, "it isn't a set of named values"
    return data, None


def _load(path: Path, schema: Any) -> tuple[dict[str, Any] | None, str | None]:
    data, problem = _raw(path)
    if data is None:
        return None, problem
    try:
        return _checked(schema).model_validate(data).model_dump(mode="json"), None
    except ValidationError as err:
        return None, _problem(err)


def files(host: Any, name: str, project: str | None = None) -> list[dict[str, Any]]:
    """Every file of the form's kind: {file, layers (those holding it), layer (the one in effect, None for a single
    file not made yet), problem (checked as the plugin's loader would)}."""
    form = _form(host, name)
    layers = _layers(host, name, project)
    names: set[str] = set()
    for folder in layers.values():
        if folder.is_dir():
            for path in folder.glob(form.pattern):
                relative = path.relative_to(folder).as_posix()
                if path.is_file() and _NAME.fullmatch(relative):
                    names.add(relative)
    if form.single:
        names.add(form.pattern)
    found = []
    for file in sorted(names):
        holding = [layer for layer, folder in layers.items() if (folder / file).is_file()]
        if not holding:
            found.append({"file": file, "layers": [], "layer": None, "problem": None})
            continue
        _, problem = _load(layers[holding[-1]] / file, form.schema)
        found.append({"file": file, "layers": holding, "layer": holding[-1], "problem": problem})
    return found


def read(host: Any, name: str, file: str, project: str | None = None) -> dict[str, Any]:
    """One file as the form shows it: {values (in effect, or the schema's defaults for a new file), layer, layers,
    problem, defaults}."""
    form = _form(host, name)
    file = _file_name(form, file)
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


def _in_effect(layers: dict[str, Path], file: str) -> Path | None:
    holding = [folder / file for folder in layers.values() if (folder / file).is_file()]
    return holding[-1] if holding else None


def save(
    host: Any,
    name: str,
    file: str,
    layer: str,
    changes: dict[str, Any],
    project: str | None = None,
    start_from: str | None = None,
) -> dict[str, Any]:
    """Write the file to the workspace's or a project's layer: the keys of the copy in effect (for a new file, of
    `start_from`, another file of the kind, or nothing) with `changes` (dotted field names) laid over, checked
    against the schema. Only those keys are written, never the schema's defaults. Returns {before} (the layer's
    text before, None when it had no copy) for Undo."""
    form = _form(host, name)
    file = _file_name(form, file)
    if layer not in ("workspace", "project") or (layer == "project" and not project):
        raise StoreError("a data file is saved to the workspace's layer or a project's, never the shipped one")
    layers = _layers(host, name, project)
    target = layers.get(layer)
    if target is None:
        raise StoreError(f"there is no {layer} layer here")
    base = _in_effect(layers, file)
    if base is None and start_from:
        base = _in_effect(layers, _file_name(form, start_from))
        if base is None:
            raise StoreError("there is no file by that name to start from")
    values: dict[str, Any] = {}
    if base is not None:
        raw, problem = _raw(base)
        if raw is None:
            raise StoreError(f"the file to start from {problem}")
        values = raw
    for key, value in changes.items():
        _set(values, key, value)
    try:
        _checked(form.schema).model_validate(values)
    except ValidationError as err:
        raise StoreError(_problem(err)) from None
    path = target / file
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, yaml.safe_dump(values, sort_keys=False, allow_unicode=True))
    return {"before": before}


def remove(host: Any, name: str, file: str, layer: str, project: str | None = None) -> dict[str, Any]:
    """Remove the workspace's or a project's copy, so the less specific one is in effect again. Returns {before}."""
    form = _form(host, name)
    file = _file_name(form, file)
    if layer not in ("workspace", "project"):
        raise StoreError("only the workspace's or a project's copy can be removed")
    target = _layers(host, name, project).get(layer)
    path = target / file if target is not None else None
    if path is None or not path.is_file():
        raise StoreError(f"there is no {layer} copy of that file")
    before = path.read_text(encoding="utf-8")
    path.unlink()
    return {"before": before}


def restore(host: Any, name: str, file: str, layer: str, before: str | None, project: str | None = None) -> None:
    """Undo a save or a removal: put the layer's copy back as it was (or remove it, when there was none)."""
    form = _form(host, name)
    file = _file_name(form, file)
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
        yaml.safe_load(before)
    except yaml.YAMLError:
        raise StoreError("that copy can't be read any more") from None
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, before)


def _write(path: Path, text: str) -> None:
    temporary = path.with_suffix(".yaml.saving")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
