"""The first-run setup (design 7.8): a short list of steps, each skippable and repeatable, plus the steps plugins add.

A step is done when the workspace shows it (a name and the person's own name, an AI account that passed its test, mail
or a calendar being read, a backup folder, a few people, a first note); skipping is remembered on this computer, in the
workspace's private folder. The new-start walkthrough is a view of these steps: each belongs to one of its screens
(`group`), the ones that count toward finishing are marked, and the screen the person is on is kept beside the skips so
it resumes where they left it, also after a restart.
Also here: checking a folder for backups, listing folders to pick one on this computer, and adding an AI account, whose
pasted key is kept in the private folder and referred to from `ai.yaml`, never written there.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from engine.connectors import CORE, declared_reads, reads
from engine.shipped import shipped
from engine.state_file import write_whole
from engine.storage import StoreError
from engine.yaml_load import load_yaml

STATE_FILE = "setup.json"
CORE_STEPS = ("workspace", "ai", "mail", "backup", "people", "template", "first_note", "addons")
#: The walkthrough's screens, in order. "promises" is the first result (the look back over the mail and the promises
#: found, `engine/first_promises.py`), right after mail, so nothing that asks about more comes before it; it has no
#: setup step of its own. The last screen lists what was set up and what is optional.
WALKTHROUGH_STEPS = ("you", "ai", "mail", "promises", "backup", "people", "done")
#: The walkthrough screen a core step belongs to; a core step not listed is an optional extra, on the last screen.
CORE_GROUPS = {"workspace": "you", "ai": "ai", "mail": "mail", "backup": "backup", "people": "people"}
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
    group: str = "done"  # the walkthrough screen it belongs to (one of WALKTHROUGH_STEPS)
    counted: bool = False  # whether it counts toward finishing the walkthrough


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
    files: list[str] = field(default_factory=list)


# ---- steps -----------------------------------------------------------------------------------------------------------


def _state(ws: Any) -> dict[str, Any]:
    try:
        data = json.loads((ws.private_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"skipped": []}
    return data if isinstance(data, dict) else {"skipped": []}


def _save_state(ws: Any, data: dict[str, Any]) -> None:
    """Write the whole file in one step, so a read never finds it half written."""
    write_whole(ws.private_dir / STATE_FILE, json.dumps(data, indent=2) + "\n")


#: Held while the state is read, changed and written, so changes made at the same moment (a screen sends several when it
#: opens) are applied one after the other and none is lost.
_STATE_LOCK = threading.RLock()


@contextmanager
def _changing(ws: Any) -> Iterator[dict[str, Any]]:
    """The state for one change: the block edits it, and it is written when the block ends without an error."""
    with _STATE_LOCK:
        state = _state(ws)
        yield state
        _save_state(ws, state)


def mail_plugins(store: Any) -> set[str]:
    """The running add-ons that provide a source of mail or of a calendar."""
    return {
        name
        for name, manifest in store.plugins.manifests.items()
        if any(reads(connector, manifest.provides.connector_reads) for connector in manifest.provides.connectors)
    }


def steps(ws: Any, cfg: Any, store: Any) -> list[Step]:
    """Every setup step with whether it is done or skipped: the core's, then each running plugin's. An add-on's own
    steps and sign-ins belong to the mail and calendar screen when it provides a source of mail or of a calendar."""
    from engine.ai.smoke import ai_state
    from engine.sign_in import status

    state = _state(ws)
    skipped = set(state.get("skipped", []))
    view = store.read()
    people = view.list("person")
    mail_addons = mail_plugins(store)
    sign_ins = store.plugins.sign_ins()
    signed = {
        name: status(ws.root / ".cockpit" / "keys" / sign_in.plugin, sign_in) == "signed_in"
        for name, sign_in in sign_ins.items()
    }
    mail_signed = any(signed[name] for name, sign_in in sign_ins.items() if sign_in.plugin in mail_addons)
    said = declared_reads({**CORE, **store.plugins.connectors()})
    mail_read = any(source.enabled and reads(source.connector, said) for source in cfg.watch.sources)
    done = {
        "workspace": _pm_named(cfg, view),  # the workspace's own name is optional; naming yourself is what counts
        "template": bool(state.get("template")) or _template_in_use(ws, cfg),
        "ai": ai_state(ws, cfg, store)[0] == "ok",
        "mail": mail_signed or mail_read,
        "backup": bool(cfg.storage.backups.targets),
        "people": len(people) >= 2,
        "first_note": any(r.data.get("origin") == "pm" for r in view.list("request")),
        "addons": not set(addons_off(ws, cfg)) - set(state.get("addons_decided", [])),
    }
    found = [
        Step(
            step,
            done[step],
            step in skipped and not done[step],
            group=CORE_GROUPS.get(step, "done"),
            counted=step in CORE_GROUPS,
        )
        for step in CORE_STEPS
    ]
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
                group="mail" if plugin in mail_addons else "done",
            )
        )
    for name, sign_in in sign_ins.items():
        found.append(
            Step(
                name,
                signed[name],
                name in skipped and not signed[name],
                label=sign_in.label,
                explanation="; ".join(sign_in.allows),
                plugin=sign_in.plugin,
                sign_in=name,
                group="mail" if sign_in.plugin in mail_addons else "done",
            )
        )
    return found


def finished(found: list[Step]) -> bool:
    """Every step that counts toward finishing is done or skipped. The optional extras never count."""
    return all(s.done or s.skipped for s in found if s.counted)


# ---- the walkthrough -------------------------------------------------------------------------------------------------


@dataclass
class Walkthrough:
    open: bool  # it should open by itself now
    step: str  # the screen to open at (one of WALKTHROUGH_STEPS)
    closed: bool  # the person chose Finish later
    finished: bool  # the person pressed the last button


def missing_essentials(cfg: Any, found: list[Step]) -> bool:
    """Whether something the assistant can't work without is missing: the person hasn't named themselves, or no AI
    account has been chosen for any kind of work. An account that fails its test is said on Today, not here."""
    named = next((s.done for s in found if s.id == "workspace"), True)
    return not named or not any(tier.use for tier in cfg.ai.tiers.values())


def walkthrough(ws: Any, cfg: Any, found: list[Step]) -> Walkthrough:
    """Where the walkthrough stands. It opens by itself on every visit while an essential is missing (naming yourself,
    choosing an AI account), even after Finish later; otherwise only on the first visit to a workspace whose setup isn't
    finished, so the optional steps wait on Today's setup line. Never on the sandbox workspaces. It resumes at the
    screen kept from the last visit, else at the first one with a step still to do."""
    mine = _state(ws).get("walkthrough")
    mine = mine if isinstance(mine, dict) else {}
    closed, ended, started = bool(mine.get("closed")), bool(mine.get("finished")), bool(mine.get("started"))
    step = mine.get("step")
    if step not in WALKTHROUGH_STEPS:
        todo = next((s for s in found if s.counted and not (s.done or s.skipped)), None)
        step = todo.group if todo else "done"
    return Walkthrough(
        open=not cfg.workspace.demo
        and (missing_essentials(cfg, found) or not (started or closed or ended or finished(found))),
        step=step,
        closed=closed,
        finished=ended,
    )


def keep_walkthrough(ws: Any, step: str | None = None, closed: bool | None = None, ended: bool | None = None) -> None:
    """Keep where the walkthrough stands: the screen the person is on, that they closed it for now (it then stays closed
    until they open it again), or that they finished it."""
    if step is not None and step not in WALKTHROUGH_STEPS:
        raise StoreError(f"there is no walkthrough screen {step}")
    with _changing(ws) as state:
        mine = dict(state["walkthrough"]) if isinstance(state.get("walkthrough"), dict) else {}
        if step is not None:
            mine["step"], mine["started"] = step, True
        if closed is not None:
            mine["closed"] = closed
        if ended is not None:
            mine["finished"] = ended
        state["walkthrough"] = mine


def addons_off(ws: Any, cfg: Any) -> list[str]:
    """Add-ons the person installed on this computer (in the workspace's plugins folder or as packages) that aren't
    turned on. The ones that come with the app aren't the person's to decide about here."""
    from engine.plugin_manifest import declared_plugins, shipped_plugins

    enabled = set(cfg.workspace.plugins.enabled)
    try:
        installed = {m.name for m in declared_plugins(ws.config_dir, None)}
    except Exception:  # an add-on whose manifest doesn't read is listed on the Add-ons screen, not here
        return []
    return sorted(installed - enabled - shipped_plugins())


def decide_addons(ws: Any, names: list[str]) -> None:
    """Remember that the person chose about these add-ons (turned on, turned off or left off), so the add-ons step
    stops asking about them."""
    with _changing(ws) as state:
        state["addons_decided"] = sorted(set(state.get("addons_decided", [])) | set(names))


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
    with _changing(ws) as state:
        names = [s for s in state.get("skipped", []) if s != step]
        state["skipped"] = [*names, step] if skipped else names


def template_applied(ws: Any, template: str) -> None:
    with _changing(ws) as state:
        state["template"] = template


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


def list_folders(raw: str | None, files: str | None = None) -> FolderList:
    """The folders inside one folder on this computer, to pick a backup or synced folder, and with `files` (endings
    such as `.ics`, separated by commas) the files that end that way, to pick a file. Hidden ones are left out. Only
    offered when the app runs on the person's own computer."""
    folder = Path(raw).expanduser() if raw else Path.home()
    endings = tuple(e.strip().lower() for e in (files or "").split(",") if e.strip())
    try:
        folder = folder.resolve(strict=True)
        inside = [p for p in folder.iterdir() if not p.name.startswith(".")]
        names = sorted((p.name for p in inside if p.is_dir()), key=str.lower)
        found = sorted(
            (p.name for p in inside if endings and p.is_file() and p.name.lower().endswith(endings)), key=str.lower
        )
    except OSError as err:
        raise StoreError(f"that folder can't be opened: {err.strerror or err}") from None
    parent = str(folder.parent) if folder.parent != folder else None
    return FolderList(str(folder), parent, names[:500], found[:500])


# ---- AI accounts -----------------------------------------------------------------------------------------------------


def known_endpoints() -> list[dict[str, Any]]:
    """The kinds of AI account the Add account screen offers, from the product's catalog: id, name, adapter,
    base_url, key_url, needs_key, local, allowed_data, settings (a new account's starting provider settings) and a
    note. Entries missing an id, a name or an adapter are left out."""
    try:
        data = load_yaml(CATALOG.read_text(encoding="utf-8")) or {}
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
    "offline": "There is no network connection. Check it, then try again.",
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


SECRET_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,80}")


def secret_name(*parts: str) -> str:
    """A safe file name for a kept secret, made from the words that say what it is for (a source's id and a field's
    name, say): lowercase letters, digits and dashes."""
    return "-".join(w for w in re.sub(r"[^a-z0-9]+", "-", " ".join(parts).lower()).split("-") if w)


def secret_path(ws: Any, name: str) -> Path:
    """Where a secret of that name is kept on this computer: the workspace's private keys folder."""
    if not SECRET_NAME.fullmatch(name):
        raise StoreError("a kept secret's name is lowercase letters, digits and dashes")
    return ws.private_dir / "keys" / name


def keep_secret(ws: Any, name: str, value: str, *, owner: str | None = None, forever: bool = False) -> str:
    """Keep a pasted password, key or private address in the workspace's private folder on this computer, readable only
    by this user. Returns the reference the setting holds. Keeping a name again replaces what was kept. `owner` says
    what it was kept for (`source:<id>`, `ai:<account>`), so removing that takes it away too; `forever` marks one
    that is never removed (the backup key). Both are noted in `engine.kept_secrets`."""
    if not value.strip():
        raise StoreError("there is nothing to keep")
    path = secret_path(ws, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    write_whole(path, value.strip() + "\n", mode=0o600)
    from engine import kept_secrets

    kept_secrets.record(ws, name, owner=owner, forever=forever)
    return f"file:{path.resolve()}"


def kept_here(ws: Any, reference: str | None) -> bool:
    """Whether a secret reference points at a file this app keeps in its own private folder."""
    scheme, _, where = (reference or "").partition(":")
    if scheme != "file" or not where:
        return False
    try:
        return Path(where).expanduser().resolve().parent == (ws.private_dir / "keys").resolve()
    except OSError:
        return False


def secret_where(ws: Any, reference: str | None) -> tuple[str, str | None]:
    """Where a secret reference is read from, for a screen: ("none", None) for no reference, ("kept", None) for a value
    this app keeps in its own private folder, ("env", variable name), ("file", path) or ("other", None)."""
    if not reference:
        return "none", None
    if kept_here(ws, reference):
        return "kept", None
    scheme, _, name = reference.partition(":")
    return (scheme, name) if scheme in ("env", "file") else ("other", None)


def unused_secret_name(ws: Any, name: str) -> str:
    """The name, or the name with the next free number, that no kept secret has yet. A pasted value is kept under a
    name of its own, so a refused save never touches the value in use, and Undo's earlier reference still works."""
    if not secret_path(ws, name).exists():
        return name
    return next(f"{name}-{n}" for n in itertools.count(2) if not secret_path(ws, f"{name}-{n}").exists())


def secret_reference(ws: Any, name: str) -> str:
    """The reference a setting holds for the secret kept under this name."""
    return f"file:{secret_path(ws, name).resolve()}"


def key_name(ws: Any, account: str) -> str:
    """The unused name a pasted AI key for this account is kept under (see `unused_secret_name`)."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", account):
        raise StoreError("an account's name is lowercase letters, digits and dashes")
    return unused_secret_name(ws, account)


def keep_key(ws: Any, account: str, key: str) -> str:
    """Keep a pasted AI key (see `keep_secret`), under the account's name. Returns the reference `ai.yaml` holds."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", account):
        raise StoreError("an account's name is lowercase letters, digits and dashes")
    return keep_secret(ws, account, key, owner=f"ai:{account}")
