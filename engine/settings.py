"""Settings from the screens (design 4.0, 7.9): every config key described for a form, and the person's changes saved
into the config files.

A save names the fingerprint of the files the form was built from, so two saves never race; it refuses keys locked by an
environment variable or a flag, and keys that only the files or flags set (the server's address and mode, the storage
backend). The changed files are checked as a whole config before anything is written, written keeping their comments,
committed to the workspace's git when it has one, and each change is recorded as a `setting_change`. Settings read at
the moment of use apply at once; any other change waits for the person to choose a restart (6.14).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
import typing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from engine import audit
from engine.config import ConfigError, load_config
from engine.config.loader import plain_label, refusal_text
from engine.config.schema import FILES
from engine.config.yaml_edit import get_key, has_key, remove_key, set_key
from engine.references import join_watch_changes
from engine.secrets import SecretHint
from engine.storage import StoreError, WriteContext
from engine.yaml_load import load_yaml

log = logging.getLogger(__name__)

#: Keys shown first; the rest sit behind "More settings".
BASIC = frozenset(
    {
        "workspace.name",
        "workspace.assistant_name",
        "workspace.user.timezone",
        "workspace.language",
        "storage.backups.every_hours",
        "storage.backups.keep",
        "storage.backups.automatic",
        "storage.sync.folder",
        "ai.budgets.per_run_usd",
        "ai.budgets.first_go",
        "ai.budgets.confirm_above_usd",
        "ai.budgets.per_day_usd",
        "ai.budgets.per_month_usd",
        "ui.toast_seconds",
        "ui.theme",
        "ui.density",
        "ui.brand.color",
        "ui.brand.logo",
        "ui.notifications.enabled",
        "ui.notifications.browser",
    }
)
#: Keys the screens never change: a wrong value would stop the app from being reached or starting, or the setting is
#: not offered yet (the export's remote).
FILE_ONLY = ("server.", "storage.backend", "storage.export.remote")

Kind = Literal["text", "number", "integer", "yes_no", "choice", "list", "other"]


class SettingsError(StoreError):
    """A save that can't be made; the message says which key and why."""


class SettingsConflict(SettingsError):
    """The files changed since the form was built."""


@dataclass
class Setting:
    key: str
    file: str
    group: str
    description: str
    type: Kind
    options: list[str]
    value: Any
    default: Any
    source: str  # default, file, env or flag
    locked: bool
    basic: bool
    editable: bool
    enabled_by: str | None = None  # the switch (yes/no) or field (set or empty) this one only matters with
    picker: str | None = None  # "folder" or "file": the screen offers a chooser instead of typing a path
    plugin: str | None = None  # the add-on whose settings these are; None for the app's own
    choices: str | None = None  # the named list a text setting picks from (a key of CHOICE_LISTS), when it has one
    secret: bool = False  # the value is a reference to a secret (a password, a key, a private address)
    advanced: bool = (
        False  # technical: the screens list it only behind Advanced, in the words the person who set it up uses
    )
    file_types: list[str] = field(default_factory=list)  # with picker "file": the endings it offers (".ics")


@dataclass
class Saved:
    changes: list[dict[str, Any]] = field(default_factory=list)  # key, before, after, was_default, is_default
    fingerprint: str = ""


PLUGIN_PREFIX = "plugins/"


def screen_name(setting: Setting | None) -> str:
    """What to call a setting in a message the screen shows: the first sentence of its description, without a
    parenthetical, as the form labels it when the wording sheet has no shorter label."""
    if setting is None:
        return "that setting"
    first = plain_label(setting.description)
    return f"“{first}”" if first else "that setting"


HANDLE_PREFIX = "s-"
HANDLE_LENGTH = 6


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def handle_of(key: str, length: int = HANDLE_LENGTH) -> str:
    """A setting's short handle: a fixed prefix and the first characters of a hash of its key. It stays the same
    while the key does, and says nothing about where the setting lives."""
    return HANDLE_PREFIX + _digest(key)[:length]


def handles(keys: list[str]) -> dict[str, str]:
    """The handle of each key in a list. Keys whose short handles would be the same all get longer ones, just long
    enough to tell them apart, so a handle names one setting among the keys given."""
    digests = {key: _digest(key) for key in keys}
    out = {}
    for key, digest in digests.items():
        length = HANDLE_LENGTH
        while length < len(digest) and any(o[:length] == digest[:length] for k, o in digests.items() if k != key):
            length += 1
        out[key] = HANDLE_PREFIX + digest[:length]
    return out


def resolve_handle(handle: str, items: list[Setting]) -> Setting:
    """The setting a handle names among the settings now, or a refusal in plain words."""
    wanted = handle.strip().lower()
    by_handle = handles([i.key for i in items])
    for item in items:
        if by_handle[item.key] == wanted:
            return item
    raise SettingsError("that isn't one of the settings; use a setting code from the settings list")


def fingerprint(config_dir: Path) -> str:
    """A hash of the config files the screens edit, the add-ons' settings files included."""
    digest = hashlib.sha256()
    for name in FILES:
        path = config_dir / f"{name}.yaml"
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.exists() else b"-")
    for path in sorted((config_dir / "plugins").glob("*.yaml")):
        digest.update(f"plugins/{path.name}".encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def changed_at(config_dir: Path) -> datetime | None:
    """When the config files the screens edit were last written (the newest of them), so a refused save can say when
    what the person was looking at changed underneath them. None when there are no files."""
    paths = [config_dir / f"{name}.yaml" for name in FILES] + sorted((config_dir / "plugins").glob("*.yaml"))
    times = [p.stat().st_mtime for p in paths if p.exists()]
    return datetime.fromtimestamp(max(times), UTC) if times else None


def describe(
    cfg: Any, plugins: Any = None, config_dir: Path | None = None, live: dict[str, list[str]] | None = None
) -> list[Setting]:
    """Every key of every config file, for the Settings forms; with the plugin host and the config folder, also each
    running add-on's settings (file `plugins/<name>`, as read from its file now). `live` holds the choices of the
    named lists that come from the workspace's own records (a value list), by the name a setting gives."""
    found: list[Setting] = []
    for name, model in FILES.items():
        defaults = model().model_dump(mode="json")
        values = getattr(cfg, name).model_dump(mode="json")
        _walk(model, [name], values, defaults, cfg.sources, found, live)
    for plugin, model in (plugin_models(plugins) if config_dir is not None else {}).items():
        file = PLUGIN_PREFIX + plugin
        raw = _plugin_raw(config_dir, plugin)
        try:
            values = model.model_validate(raw).model_dump(mode="json")
        except Exception:  # a file the add-on refuses: show the defaults; saving checks again
            values = model().model_dump(mode="json")
        sources = {f"{file}.{'.'.join(path)}": "file" for path in _leaf_paths(raw)}
        start = len(found)
        _walk(model, [file], values, model().model_dump(mode="json"), sources, found)
        for setting in found[start:]:
            setting.plugin = plugin
    return found


def plugin_models(plugins: Any) -> dict[str, type[BaseModel]]:
    """The settings model of each running add-on, by name."""
    if plugins is None:
        return {}
    return {
        name: type(registrar.config)
        for name, registrar in sorted(plugins.registrars.items())
        if plugins.active(name) and isinstance(registrar.config, BaseModel)
    }


def _plugin_raw(config_dir: Path, plugin: str) -> dict[str, Any]:
    path = config_dir / "plugins" / f"{plugin}.yaml"
    if not path.exists():
        return {}
    try:
        data = load_yaml(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _leaf_paths(data: Any, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if isinstance(data, dict) and data:
        return [p for k, v in data.items() for p in _leaf_paths(v, (*prefix, str(k)))]
    return [prefix] if prefix else []


def _walk(
    model: type[BaseModel],
    path: list[str],
    values: Any,
    defaults: Any,
    sources: dict[str, str],
    out: list[Setting],
    live: dict[str, list[str]] | None = None,
) -> None:
    for key, info in model.model_fields.items():
        if key == "version" and len(path) == 1:
            continue
        here = [*path, key]
        dotted = ".".join(here)
        inner = _model_of(info.annotation)
        if inner is not None:
            _walk(inner, here, (values or {}).get(key), (defaults or {}).get(key), sources, out, live)
            continue
        kind, options = _kind(info.annotation)
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        list_name = str(extra["choices"]) if extra.get("choices") else None
        named = CHOICE_LISTS.get(list_name) if list_name else None
        if list_name and (live or {}).get(list_name):
            named = (live or {})[list_name].copy
        if named is not None and (listed := named()):
            if kind == "list":
                # Several values from a known set are ticked, never typed; one already held stays on the list.
                held = [v for v in ((values or {}).get(key) or []) if isinstance(v, str) and v not in listed]
                options = [*listed, *held]
            else:
                kind, options = "choice", _with_current(listed, (values or {}).get(key))
        else:
            list_name = None
        switch = extra.get("enabled_by")
        if isinstance(switch, str) and "." not in switch:
            switch = ".".join([*path, switch])
        source = _source(dotted, sources)
        locked = source in ("env", "flag")
        out.append(
            Setting(
                key=dotted,
                file=path[0],
                group=".".join(path[:2]) if len(path) > 1 else path[0],
                description=info.description or "",
                type=kind,
                options=options,
                value=(values or {}).get(key),
                default=(defaults or {}).get(key),
                source=source,
                locked=locked,
                basic=dotted in BASIC,
                editable=(kind != "other" or extra.get("screen_edit") is True)
                and not locked
                and not dotted.startswith(FILE_ONLY),
                enabled_by=switch if isinstance(switch, str) else None,
                picker=extra.get("picker") if isinstance(extra.get("picker"), str) else None,
                choices=list_name,
                secret=isinstance(info.description, SecretHint),
                advanced=extra.get("advanced") is True,
                file_types=[str(x) for x in extra.get("file_types") or [] if isinstance(x, str)],
            )
        )


def secret_fields(model: type[BaseModel]) -> list[str]:
    """The dotted names of a settings model's fields whose value is a reference to a secret."""
    found: list[Setting] = []
    _walk(model, ["settings"], {}, {}, {}, found)
    return [s.key.removeprefix("settings.") for s in found if s.secret]


def picked_fields(model: type[BaseModel], picker: str) -> list[str]:
    """The dotted names of a settings model's fields the screen fills with a chooser of this kind ("folder" or
    "file"): paths on the computer the app runs on."""
    found: list[Setting] = []
    _walk(model, ["settings"], {}, {}, {}, found)
    return [s.key.removeprefix("settings.") for s in found if s.picker == picker]


def _with_current(options: list[str], value: Any) -> list[str]:
    """A named list with the setting's current value in it when it isn't there, so a list never shows a wrong value."""
    return [*options, value] if isinstance(value, str) and value and value not in options else options


def _time_zones() -> list[str]:
    """The time zones this computer knows, by their IANA names, for a setting that holds one."""
    import zoneinfo

    try:
        return sorted(zoneinfo.available_timezones())
    except Exception:  # no time zone data on this computer: the setting stays a typed name
        return []


def _times_of_day() -> list[str]:
    """The times of a day every quarter hour, as 24-hour clock text, for a setting that holds one."""
    return [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 15, 30, 45)]


LANGUAGES_FILE = Path(__file__).parent / "defaults" / "languages.yaml"


def _languages() -> list[str]:
    """The language tags the core offers, from its shipped list."""
    data = load_yaml(LANGUAGES_FILE.read_text(encoding="utf-8")) or {}
    return [str(tag) for tag in data.get("languages") or []]


DATE_FORMATS_FILE = Path(__file__).parent / "defaults" / "date_formats.yaml"


def _date_formats_of(name: str) -> list[str]:
    data = load_yaml(DATE_FORMATS_FILE.read_text(encoding="utf-8")) or {}
    return [str(code) for code in data.get(name) or []]


CHOICES_FILE = Path(__file__).parent / "defaults" / "choices.yaml"


def _choices_of(name: str) -> list[str]:
    data = load_yaml(CHOICES_FILE.read_text(encoding="utf-8")) or {}
    return [str(value) for value in data.get(name) or []]


def _owner_formats() -> list[str]:
    """The ways an action's owner can be shown, from the shipped list."""
    return _choices_of("owner_formats")


def _media_types() -> list[str]:
    """The kinds of file that can be allowed, by media type, from the shipped list."""
    return _choices_of("media_types")


def _date_formats() -> list[str]:
    """The ways a date can be written (strftime codes), from the shipped list."""
    return _date_formats_of("date_formats")


def _date_time_formats() -> list[str]:
    """The ways a date and time can be written (strftime codes), from the shipped list."""
    return _date_formats_of("date_time_formats")


#: Lists of choices a text setting can name (`json_schema_extra={"choices": ...}`), so the screens offer a list
#: instead of a box to type in.
CHOICE_LISTS = {
    "time_zones": _time_zones,
    "languages": _languages,
    "times_of_day": _times_of_day,
    "date_formats": _date_formats,
    "date_time_formats": _date_time_formats,
    "owner_formats": _owner_formats,
    "media_types": _media_types,
}


def _source(dotted: str, sources: dict[str, str]) -> str:
    """The layer that set a key, or one of its children for a key that holds a mapping."""
    if dotted in sources:
        return sources[dotted]
    layers = {layer for key, layer in sources.items() if key.startswith(dotted + ".")}
    for layer in ("flag", "env", "file"):
        if layer in layers:
            return layer
    return "default"


def _model_of(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _entry_model_of(annotation: Any) -> type[BaseModel] | None:
    """The settings model each entry of a map holds (a map of names to models), when the annotation is one."""
    args = typing.get_args(annotation)
    if typing.get_origin(annotation) is dict and len(args) == 2:
        return _model_of(args[1])
    return None


def source_of(cfg: Any, key: str) -> str:
    """The layer that set a key in a loaded config: default, file, env or flag."""
    return _source(key, cfg.sources)


def opened_to_screens(key: str, cfg: Any) -> bool:
    """Whether a key sits below a field the schema opens to the screens, though no form lists it on its own: a setting
    of one entry of a map (`json_schema_extra={"screen_edit": True}` on the setting itself). The entry must already
    exist unless its map says new ones may be added (`"new_entries": True`)."""
    name, *path = key.split(".")
    model = FILES.get(name)
    data: Any = getattr(cfg, name).model_dump(mode="json") if model is not None else None
    while model is not None and path:
        info = model.model_fields.get(path[0])
        if info is None:
            return False
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        here, path = path[0], path[1:]
        data = (data or {}).get(here) if isinstance(data, dict) else None
        if (inner := _model_of(info.annotation)) is not None:
            model = inner
            continue
        if (entry := _entry_model_of(info.annotation)) is not None:
            if len(path) < 2 or (path[0] not in (data or {}) and extra.get("new_entries") is not True):
                return False
            data = (data or {}).get(path[0])
            model, path = entry, path[1:]
            continue
        return not path and extra.get("screen_edit") is True
    return False


def _kind(annotation: Any) -> tuple[Kind, list[str]]:
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    origin = typing.get_origin(annotation)
    if origin is Literal:
        return "choice", [str(a) for a in typing.get_args(annotation)]
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)) and len(args) == 1:
        return _kind(args[0])
    if annotation is bool:
        return "yes_no", []
    if annotation is int:
        return "integer", []
    if annotation is float:
        return "number", []
    if annotation is str:
        return "text", []
    if origin is list and args == [str]:
        return "list", []
    if origin is list and len(args) == 1 and typing.get_origin(args[0]) is Literal:
        # A list drawn from a fixed set of values: the screens offer the values to tick, never a box to type in.
        return "list", [str(a) for a in typing.get_args(args[0])]
    return "other", []


# ---- saving ----------------------------------------------------------------------------------------------------------


def save(
    ws: Any,
    cfg: Any,
    store: Any,
    *,
    changes: dict[str, Any],
    reset: list[str],
    read_fingerprint: str,
    env: dict[str, str] | None = None,
    allow: tuple[str, ...] = (),
) -> Saved:
    """Write the person's changes (`changes`: key to value; `reset`: keys going back to their defaults). `allow` lists
    key prefixes a guided step may set although no form shows them (an AI account, a backup folder)."""
    config_dir = ws.config_dir
    if read_fingerprint != fingerprint(config_dir):
        raise SettingsConflict("The settings changed since you opened them. Look again, then save.")
    # What the files hold now, which may be newer than what the running app started with.
    try:
        cfg = load_config(config_dir, env=env)
    except ConfigError as err:
        log.warning("A save found the settings files unreadable: %s", err)
        raise SettingsError(f"your settings have a problem to fix first: {err.plain}") from None
    if not changes and not reset:
        return Saved(fingerprint=fingerprint(config_dir))
    plugins = getattr(store, "plugins", None)
    models = {PLUGIN_PREFIX + name: model for name, model in plugin_models(plugins).items()}
    shown = {s.key: s for s in describe(cfg, plugins, config_dir)}
    for key in [*changes, *reset]:
        _check_key(key, shown, cfg, allow, models)
    try:
        # Records the watch settings name are held by id; a name typed here is resolved, or refused with its own words.
        changes = join_watch_changes(store.read(), changes)
    except StoreError as err:
        raise SettingsError(str(err)) from None
    texts: dict[str, str] = {}
    before: dict[str, tuple[Any, bool]] = {}
    for key in [*changes, *reset]:
        name, *path = key.split(".")
        if name not in texts:
            source = config_dir / f"{name}.yaml"
            texts[name] = source.read_text(encoding="utf-8") if source.exists() else "version: 1\n"
        data = load_yaml(texts[name]) or {}
        before[key] = (_value(key, cfg, models, texts[name]), not has_key(data, path))
    for key, value in changes.items():
        name, *path = key.split(".")
        texts[name] = set_key(texts[name], path, value)
    for key in reset:
        name, *path = key.split(".")
        texts[name] = remove_key(texts[name], path)
    for name in texts:
        if name in models and hasattr(models[name], "renamed_keys"):
            # An add-on's renamed setting is written under its new name, and the old name goes.
            data = load_yaml(texts[name]) or {}
            for new_name, old_name in models[name].renamed_keys(data):
                texts[name] = remove_key(texts[name], [old_name])
                if new_name not in data:
                    texts[name] = set_key(texts[name], [new_name], data[old_name])
    core = {name: text for name, text in texts.items() if name not in models}
    checked = _check_whole(config_dir, core, env) if core else cfg
    if "ai" in core:
        from engine.ai.checked import chain_problems

        if problems := chain_problems(ws, cfg, checked):
            log.warning("A save was refused: %s", problems[0])
            raise SettingsError(problems[0])
    for name, text in texts.items():
        if name in models:
            _check_plugin(models[name], text)
    for name, text in texts.items():
        target = config_dir / f"{name}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".yaml.saving")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)
    saved = Saved(fingerprint=fingerprint(config_dir))
    now = datetime.now(UTC)
    with store.transaction() as tx:
        for key in [*changes, *reset]:
            after = _value(key, checked, models, texts[key.split(".")[0]])
            was, was_default = before[key]
            entry = {
                "key": key,
                "before": was,
                "after": after,
                "was_default": was_default,
                "is_default": key in reset,
                "at": now.isoformat(),
            }
            tx.create("setting_change", entry, WriteContext("pm", "trusted", "config.set"))
            if key == PLUGINS_ENABLED:
                audit.plugin_changes(tx, list(was or []), list(after or []))
            saved.changes.append({k: v for k, v in entry.items() if k != "at"})
    if any(c["key"] == "workspace.assistant_name" for c in saved.changes):
        _resource_history(store, checked)
    if cfg.storage.export.commit:
        _commit(ws.root, [config_dir / f"{name}.yaml" for name in texts], [c["key"] for c in saved.changes])
    return saved


def _resource_history(store: Any, cfg: Any) -> None:
    """After the assistant is renamed, history lines that name it (now or before) are re-sourced from the ledger. A
    failure here never undoes the save."""
    from engine.outward import sweep

    try:
        sweep(store, cfg)
    except Exception as err:
        log.warning("Couldn't re-source history lines after the assistant's rename: %s", err)


#: The setting that lists the add-ons that run; changing it is audited.
PLUGINS_ENABLED = "workspace.plugins.enabled"


def _effective(cfg: Any, key: str) -> Any:
    """A key's value in a loaded config, or None where it doesn't exist (a map entry not yet added)."""
    name, *path = key.split(".")
    data = getattr(cfg, name).model_dump(mode="json")
    return get_key(data, path) if has_key(data, path) else None


def _value(key: str, cfg: Any, models: dict[str, type[BaseModel]], text: str) -> Any:
    """A key's value: from the loaded config for the app's own files, from the file's text for an add-on's."""
    name, *path = key.split(".")
    if name not in models:
        return _effective(cfg, key)
    try:
        data = models[name].model_validate(load_yaml(text) or {}).model_dump(mode="json")
    except Exception:  # an add-on's file it refuses: no value to show
        return None
    return get_key(data, path) if has_key(data, path) else None


def _check_plugin(model: type[BaseModel], text: str) -> None:
    """An add-on's settings file, checked against its settings model."""
    from pydantic import ValidationError

    try:
        model.model_validate(load_yaml(text) or {})
    except ValidationError as err:
        first = err.errors()[0]
        log.warning("An add-on's settings were refused at %s: %s", ".".join(map(str, first["loc"])), first["msg"])
        raise SettingsError(refusal_text(model, err)) from None


def _check_key(
    key: str, shown: dict[str, Setting], cfg: Any, allow: tuple[str, ...], models: dict[str, Any] | None = None
) -> None:
    name = key.split(".", 1)[0]
    setting = shown.get(key)
    if (name not in FILES and name not in (models or {})) or "." not in key:
        log.warning("A save named a setting that doesn't exist: %s", key)
        raise SettingsError("there is no such setting")
    if key.startswith(FILE_ONLY):
        log.warning("A save named a setting only the files or flags set: %s", key)
        raise SettingsError(f"{screen_name(setting)} is set when the app starts, not here")
    if setting is None and not key.startswith(allow) and not opened_to_screens(key, cfg):
        log.warning("A save named a setting the screens don't change: %s", key)
        raise SettingsError("that isn't a setting the screens change")
    if setting is not None and setting.locked:
        raise SettingsError(
            f"{screen_name(setting)} is set by {'an environment variable' if setting.source == 'env' else 'a flag'}"
        )
    if setting is not None and not setting.editable and not key.startswith(allow):
        raise SettingsError(f"{screen_name(setting)} can't be changed here")
    if setting is None:
        for other, layer in cfg.sources.items():
            overlaps = other == key or other.startswith(key + ".") or key.startswith(other + ".")
            if layer in ("env", "flag") and overlaps:
                log.warning("A save named a setting that %s sets: %s", layer, other)
                raise SettingsError(f"that is set by {'an environment variable' if layer == 'env' else 'a flag'}")


def _check_whole(config_dir: Path, texts: dict[str, str], env: dict[str, str] | None) -> Any:
    """The whole config with these files changed, or SettingsError with the reason."""
    with tempfile.TemporaryDirectory(prefix="cockpit-settings-") as folder:
        trial = Path(folder) / "config"
        shutil.copytree(config_dir, trial)
        for name, text in texts.items():
            (trial / f"{name}.yaml").write_text(text, encoding="utf-8")
        try:
            return load_config(trial, env=env)
        except ConfigError as err:
            log.warning("A save was refused: %s", err)
            raise SettingsError(err.plain) from None


def _commit(root: Path, paths: list[Path], keys: list[str]) -> None:
    """Commit the changed config files to the workspace's git repository, when there is one."""
    if not (root / ".git").exists():
        return
    git = ["git", "-C", str(root), "-c", "user.name=PM Cockpit", "-c", "user.email=cockpit@localhost"]
    files = [str(p.relative_to(root)) for p in paths if p.exists()]
    try:
        subprocess.run([*git, "add", "--", *files], check=True, capture_output=True)
        staged = subprocess.run([*git, "diff", "--cached", "--quiet", "--", *files], capture_output=True)
        if staged.returncode != 0:
            message = "Settings: " + ", ".join(keys)
            subprocess.run([*git, "commit", "-q", "-m", message[:200], "--", *files], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return  # the files are written; the next export's commit picks them up
