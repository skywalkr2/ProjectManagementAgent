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

from engine.storage import StoreError

STATE_FILE = "setup.json"
CORE_STEPS = ("workspace", "template", "ai", "backup", "people", "first_note")
CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "ai-endpoints.yaml"


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
        "workspace": bool(cfg.workspace.user.full_name.strip()) and cfg.workspace.name != "Workspace",
        "template": bool(state.get("template")),
        "ai": ai_state(ws, cfg, store)[0] == "ok",
        "backup": bool(cfg.storage.backups.targets),
        "people": len(people) >= 2,
        "first_note": any(r.data.get("origin") == "pm" for r in view.list("request")),
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
    return found


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


def known_endpoints() -> list[dict[str, str]]:
    """The endpoints the Add account screen offers: name, base_url and a note, from the product's catalog."""
    try:
        data = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return [
        {
            "id": str(e["id"]),
            "name": str(e["name"]),
            "adapter": str(e["adapter"]),
            "base_url": str(e.get("base_url") or ""),
            "note": str(e.get("note") or ""),
        }
        for e in data.get("endpoints", [])
        if isinstance(e, dict) and e.get("id") and e.get("name") and e.get("adapter")
    ]


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
