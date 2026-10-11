"""The first-run setup (design 7.8): a short list of steps, each skippable and repeatable, plus the steps plugins add.

A step is done when the workspace shows it (a name and the person's own name, an AI account that passed its test, a
backup folder, a few people, a first note); skipping is remembered on this computer, in the workspace's private folder.
Also here: checking a folder for backups, listing folders to pick one on this computer, and adding an AI account, whose
pasted key is kept in the private folder and referred to from `ai.yaml`, never written there.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from engine.shipped import shipped
from engine.storage import StoreError

STATE_FILE = "setup.json"
CORE_STEPS = ("workspace", "template", "ai", "backup", "people", "first_note", "addons")
CATALOG = shipped("catalog") / "ai-endpoints.yaml"


@dataclass
class Step:
    id: str  # a core step's id, or a plugin's "<plugin>/<name>"
    done: bool
    skipped: bool
    label: str = ""  # a plugin step's own wording; core steps take theirs from the wording sheet
    explanation: str = ""
    action: str | None = None  # a plugin step's person action, if it has one
    plugin: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)  # core settings a plugin step suggests
    sign_in: str | None = None  # a step the core adds per sign-in: the sign-in's name


@dataclass
class FolderCheck:
    path: str
    ok: bool
    problem: str | None = None
    free_mb: float | None = None


@dataclass
class FolderList:
    path: str
    parent: str | None
    folders: list[str] = field(default_factory=list)


# ---- steps -----------------------------------------------------------------------------------------------------------


def _state(ws: Any) -> dict[str, Any]:
    try:
        data = json.loads((ws.private_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"skipped": []}
    return data if isinstance(data, dict) else {"skipped": []}


def _save_state(ws: Any, data: dict[str, Any]) -> None:
    ws.private_dir.mkdir(parents=True, exist_ok=True)
    (ws.private_dir / STATE_FILE).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def steps(ws: Any, cfg: Any, store: Any) -> list[Step]:
    """Every setup step with whether it is done or skipped: the core's, then each running plugin's."""
    from engine.ai.smoke import ai_state

    state = _state(ws)
    skipped = set(state.get("skipped", []))
    view = store.read()
    people = view.list("person")
    done = {
        "workspace": _pm_named(cfg, view) and cfg.workspace.name != "Workspace",
        "template": bool(state.get("template")) or _template_in_use(ws, cfg),
        "ai": ai_state(ws, cfg, store)[0] == "ok",
        "backup": bool(cfg.storage.backups.targets),
        "people": len(people) >= 2,
        "first_note": any(r.data.get("origin") == "pm" for r in view.list("request")),
        "addons": not addons_off(ws, cfg),
    }
    found = [Step(step, done[step], step in skipped and not done[step]) for step in CORE_STEPS]
    for plugin, step in store.plugins.setup_steps():
        finished = store.plugins.setup_step_done(plugin, step)
        found.append(
            Step(
                step.name,
                finished,
                step.name in skipped and not finished,
                label=step.label,
                explanation=step.explanation,
                action=step.action,
                plugin=plugin,
                settings=dict(step.settings),
            )
        )
    from engine.sign_in import status

    for name, sign_in in store.plugins.sign_ins().items():
        signed = status(ws.root / ".cockpit" / "keys" / sign_in.plugin, sign_in) == "signed_in"
        found.append(
            Step(
                name,
                signed,
                name in skipped and not signed,
                label=sign_in.label,
                explanation="; ".join(sign_in.allows),
                plugin=sign_in.plugin,
                sign_in=name,
            )
        )
    return found


def addons_off(ws: Any, cfg: Any) -> list[str]:
    """Add-ons installed on this computer (in the workspace's plugins folder or as packages) that aren't turned on."""
    from engine.plugin_manifest import declared_plugins

    enabled = set(cfg.workspace.plugins.enabled)
    try:
        installed = {m.name for m in declared_plugins(ws.config_dir, None)}
    except Exception:  # an add-on whose manifest doesn't read is listed on the Add-ons screen, not here
        return []
    return sorted(installed - enabled)


def _template_in_use(ws: Any, cfg: Any) -> bool:
    from engine import templates

    try:
        return templates.in_use(ws, list(cfg.workspace.plugins.enabled)) is not None
    except templates.TemplateError:
        return False


def _pm_named(cfg: Any, view: Any) -> bool:
    """The PM is a person record with a name: the one place their name is kept."""
    person = view.get("person", cfg.workspace.user.person) if cfg.workspace.user.person else None
    return person is not None and bool(str(person.data.get("full_name", "")).strip())


def skip(ws: Any, step: str, skipped: bool = True) -> None:
    """Skip a step for now, or bring it back."""
    state = _state(ws)
    names = [s for s in state.get("skipped", []) if s != step]
    state["skipped"] = [*names, step] if skipped else names
    _save_state(ws, state)


def template_applied(ws: Any, template: str) -> None:
    state = _state(ws)
    state["template"] = template
    _save_state(ws, state)


# ---- folders ---------------------------------------------------------------------------------------------------------


def check_backup_folder(ws: Any, raw: str) -> FolderCheck:
    """Whether a folder can take backups: a full path, there now, outside the workspace, and writable."""
    text = raw.strip()
    if not text:
        return FolderCheck(raw, False, "Choose a folder.")
    folder = Path(text).expanduser()
    if not folder.is_absolute():
        return FolderCheck(raw, False, "Give the folder's full path.")
    folder = folder.resolve()
    root = ws.root.resolve()
    if folder == root or folder.is_relative_to(root) or root.is_relative_to(folder):
        return FolderCheck(str(folder), False, "Choose a folder outside the workspace, so the backup is a real copy.")
    if not folder.is_dir():
        return FolderCheck(str(folder), False, "That folder isn't there. Connect the drive, or create the folder.")
    probe = folder / ".cockpit-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return FolderCheck(str(folder), False, "This app can't write in that folder.")
    free = shutil.disk_usage(folder).free / (1024 * 1024)
    return FolderCheck(str(folder), True, None, round(free, 1))


def list_folders(raw: str | None) -> FolderList:
    """The folders inside one folder on this computer, to pick a backup or synced folder. Hidden folders are left
    out. Only offered when the app runs on the person's own computer."""
    folder = Path(raw).expanduser() if raw else Path.home()
    try:
        folder = folder.resolve(strict=True)
        names = sorted((p.name for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")), key=str.lower)
    except OSError as err:
        raise StoreError(f"that folder can't be opened: {err.strerror or err}") from None
    parent = str(folder.parent) if folder.parent != folder else None
    return FolderList(str(folder), parent, names[:500])


# ---- AI accounts -----------------------------------------------------------------------------------------------------


def known_endpoints() -> list[dict[str, Any]]:
    """The kinds of AI account the Add account screen offers, from the product's catalog: id, name, adapter,
    base_url, key_url, needs_key, local, allowed_data, settings (a new account's starting provider settings) and a
    note. Entries missing an id, a name or an adapter are left out."""
    try:
        data = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    found = []
    for e in data.get("endpoints", []):
        if not (isinstance(e, dict) and e.get("id") and e.get("name") and e.get("adapter")):
            continue
        levels = [str(x) for x in e.get("allowed_data") or ["open"] if str(x) in ("open", "internal", "restricted")]
        found.append(
            {
                "id": str(e["id"]),
                "name": str(e["name"]),
                "adapter": str(e["adapter"]),
                "base_url": str(e.get("base_url") or ""),
                "key_url": str(e.get("key_url") or ""),
                "needs_key": bool(e.get("needs_key", False)),
                "local": bool(e.get("local", False)),
                "allowed_data": levels or ["open"],
                "settings": dict(e.get("settings") or {}),
                "program": str(e.get("program") or ""),
                "model_examples": [str(m) for m in e.get("model_examples") or []],
                "model_optional": bool(e.get("model_optional", False)),
                "note": str(e.get("note") or ""),
            }
        )
    return found


def endpoint(endpoint_id: str) -> dict[str, Any] | None:
    return next((e for e in known_endpoints() if e["id"] == endpoint_id), None)


#: What the screen says when a service's model list can't be read, by the kind of failure.
LIST_PROBLEMS = {
    "auth": "The service didn't accept the key. Check that it was copied whole and is still active.",
    "no_key": "This service needs a key.",
    "quota": "The service says the account has no credit or has reached its limit.",
    "rate_limited": "The service asked to wait a moment. Try again shortly.",
    "timeout": "The service didn't answer in time. Try again.",
    "provider_down": "The service couldn't be reached. Check the address, or start it if it runs on this computer.",
    "invalid_output": "The service answered, but not with a model list. Check the address.",
}


def list_models(entry: dict[str, Any], base_url: str, key: str | None) -> tuple[list[tuple[str, Any]], str | None]:
    """Ask a service for its models with a key that isn't saved yet: the models (id and what the service says about
    each, sorted by id) or a problem in plain words. Nothing is kept."""
    from engine.ai.adapters import make_adapter
    from engine.ai.task import AiError
    from engine.config.schema import ProviderSettings

    if entry["needs_key"] and not key:
        return [], LIST_PROBLEMS["no_key"]
    settings = ProviderSettings.model_validate(
        {**entry["settings"], "adapter": entry["adapter"], "base_url": base_url, "timeout_seconds": 15}
    )
    try:
        adapter = make_adapter(entry["adapter"], settings, key)
        if not hasattr(adapter, "list_models"):
            return [], None  # this kind of account doesn't list models: the person names one
        models = adapter.list_models()
    except AiError as err:
        return [], LIST_PROBLEMS.get(err.kind, "The service answered with an error. Check the address and the key.")
    return sorted(models.items()), None


def keep_key(ws: Any, account: str, key: str) -> str:
    """Keep a pasted key in the workspace's private folder on this computer, readable only by this user. Returns the
    reference `ai.yaml` holds."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", account):
        raise StoreError("an account's name is lowercase letters, digits and dashes")
    folder = ws.private_dir / "keys"
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    path = folder / account
    path.write_text(key.strip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return f"file:{path.resolve()}"
