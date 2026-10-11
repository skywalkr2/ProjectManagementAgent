"""Settings from the screens (design 4.0, 7.9): every config key described for a form, and the person's changes saved
into the config files.

A save names the fingerprint of the files the form was built from, so two saves never race; it refuses keys locked by an
environment variable or a flag, and keys that only the files or flags set (the server's address and mode, the storage
backend). The changed files are checked as a whole config before anything is written, written keeping their comments,
committed to the workspace's git when it has one, and each change is recorded as a `setting_change`. A running app
restarts itself to use saved settings (6.14).
"""

from __future__ import annotations

import hashlib
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

from engine.config import ConfigError, load_config
from engine.config.schema import FILES
from engine.config.yaml_edit import get_key, has_key, remove_key, set_key
from engine.storage import StoreError, WriteContext

#: Keys shown first; the rest sit behind "More settings".
BASIC = frozenset(
    {
        "workspace.name",
        "workspace.assistant_name",
        "workspace.user.full_name",
        "workspace.user.aliases",
        "workspace.user.timezone",
        "workspace.language",
        "storage.backups.every_hours",
        "storage.backups.keep",
        "storage.backups.automatic",
        "storage.sync.folder",
        "ai.budgets.per_run_usd",
        "ai.budgets.confirm_above_usd",
        "ai.budgets.confirm_unpriced",
        "ai.budgets.per_day_usd",
        "ai.budgets.per_month_usd",
        "ui.toast_seconds",
    }
)
#: Keys the screens never change: a wrong value would stop the app from being reached or starting.
FILE_ONLY = ("server.", "storage.backend")

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


@dataclass
class Saved:
    changes: list[dict[str, Any]] = field(default_factory=list)  # key, before, after, was_default, is_default
    fingerprint: str = ""


def fingerprint(config_dir: Path) -> str:
    """A hash of the config files the screens edit."""
    digest = hashlib.sha256()
    for name in FILES:
        path = config_dir / f"{name}.yaml"
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.exists() else b"-")
    return digest.hexdigest()


def describe(cfg: Any) -> list[Setting]:
    """Every key of every config file, for the Settings forms."""
    found: list[Setting] = []
    for name, model in FILES.items():
        defaults = model().model_dump(mode="json")
        values = getattr(cfg, name).model_dump(mode="json")
        _walk(model, [name], values, defaults, cfg.sources, found)
    return found


def _walk(
    model: type[BaseModel], path: list[str], values: Any, defaults: Any, sources: dict[str, str], out: list[Setting]
) -> None:
    for key, info in model.model_fields.items():
        if key == "version" and len(path) == 1:
            continue
        here = [*path, key]
        dotted = ".".join(here)
        inner = _model_of(info.annotation)
        if inner is not None:
            _walk(inner, here, (values or {}).get(key), (defaults or {}).get(key), sources, out)
            continue
        kind, options = _kind(info.annotation)
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
                editable=kind != "other" and not locked and not dotted.startswith(FILE_ONLY),
            )
        )


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
        raise SettingsError(f"the settings files have a problem to fix first: {err}") from None
    if not changes and not reset:
        return Saved(fingerprint=fingerprint(config_dir))
    shown = {s.key: s for s in describe(cfg)}
    for key in [*changes, *reset]:
        _check_key(key, shown, cfg, allow)
    texts: dict[str, str] = {}
    before: dict[str, tuple[Any, bool]] = {}
    for key in [*changes, *reset]:
        name, *path = key.split(".")
        if name not in texts:
            source = config_dir / f"{name}.yaml"
            texts[name] = source.read_text(encoding="utf-8") if source.exists() else "version: 1\n"
        data = yaml.safe_load(texts[name]) or {}
        before[key] = (_effective(cfg, key), not has_key(data, path))
    for key, value in changes.items():
        name, *path = key.split(".")
        texts[name] = set_key(texts[name], path, value)
    for key in reset:
        name, *path = key.split(".")
        texts[name] = remove_key(texts[name], path)
    checked = _check_whole(config_dir, texts, env)
    for name, text in texts.items():
        target = config_dir / f"{name}.yaml"
        temporary = target.with_suffix(".yaml.saving")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)
    saved = Saved(fingerprint=fingerprint(config_dir))
    now = datetime.now(UTC)
    with store.transaction() as tx:
        for key in [*changes, *reset]:
            after = _effective(checked, key)
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
            saved.changes.append({k: v for k, v in entry.items() if k != "at"})
    if cfg.storage.export.commit:
        _commit(ws.root, [config_dir / f"{name}.yaml" for name in texts], [c["key"] for c in saved.changes])
    return saved


def _effective(cfg: Any, key: str) -> Any:
    """A key's value in a loaded config, or None where it doesn't exist (a map entry not yet added)."""
    name, *path = key.split(".")
    data = getattr(cfg, name).model_dump(mode="json")
    return get_key(data, path) if has_key(data, path) else None


def _check_key(key: str, shown: dict[str, Setting], cfg: Any, allow: tuple[str, ...]) -> None:
    name = key.split(".", 1)[0]
    if name not in FILES or "." not in key:
        raise SettingsError(f"there is no setting {key}")
    if key.startswith(FILE_ONLY):
        raise SettingsError(f"{key} is set in {name}.yaml or with a flag, not here")
    setting = shown.get(key)
    if setting is None and not key.startswith(allow):
        raise SettingsError(f"{key} isn't a setting the screens change")
    if setting is not None and setting.locked:
        raise SettingsError(f"{key} is set by {'an environment variable' if setting.source == 'env' else 'a flag'}")
    if setting is not None and not setting.editable and not key.startswith(allow):
        raise SettingsError(f"{key} is changed in {name}.yaml")
    if setting is None:
        for other, layer in cfg.sources.items():
            overlaps = other == key or other.startswith(key + ".") or key.startswith(other + ".")
            if layer in ("env", "flag") and overlaps:
                raise SettingsError(f"{other} is set by {'an environment variable' if layer == 'env' else 'a flag'}")


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
            raise SettingsError(str(err)) from None


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
