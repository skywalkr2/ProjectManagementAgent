"""A workspace: one deployment's folder of config, data, sources and the database.

Real workspaces live outside this repository, each in its own git repository. The path comes from `--workspace` or the
`COCKPIT_WORKSPACE` environment variable.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from engine.config import FILES, Config, load_config, render_default_file
from engine.rules import seed_rules
from engine.state_file import changing, write_whole
from engine.storage import Store
from engine.storage.export import commit_export, export_data, import_data

ENV_WORKSPACE = "COCKPIT_WORKSPACE"
#: The folder of a template that holds its history: a full export (`data/`, ledger included) and the texts of the
#: inputs in it (`sources/`).
HISTORY = "history"
WORKSPACE_GITIGNORE = "cockpit.db\ncockpit.db-*\n.cockpit/\nsources/\ntexts/\n"


class WorkspaceError(Exception):
    """The workspace can't be found or used."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def sources_dir(self) -> Path:
        return self.root / "sources"

    @property
    def db_path(self) -> Path:
        return self.root / "cockpit.db"

    @property
    def private_dir(self) -> Path:
        """Files that never leave this computer (the install token)."""
        return self.root / ".cockpit"

    def config(self, *, env: dict[str, str] | None = None, flags: dict[str, object] | None = None) -> Config:
        return load_config(self.config_dir, env=env, flags=flags)

    def install_token(self) -> str:
        """The token the browser presents in local mode, created on first use and readable only by this user."""
        path = self.private_dir / "token"
        with changing(path):
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
            token = secrets.token_urlsafe(32)
            write_whole(path, token + "\n", mode=0o600)
            return token


def resolve(path: str | os.PathLike[str] | None) -> Workspace:
    """Find the workspace from an explicit path or the environment."""
    chosen = path or os.environ.get(ENV_WORKSPACE)
    if not chosen:
        raise WorkspaceError(f"No workspace given. Pass --workspace PATH or set {ENV_WORKSPACE}.")
    root = Path(chosen).expanduser().resolve()
    if not (root / "config").is_dir():
        raise WorkspaceError(f"{root} isn't a workspace (it has no config folder). Create one with `cockpit init`.")
    return Workspace(root)


def init_workspace(
    path: Path,
    *,
    template: Path | None = None,
    git: bool = True,
    you: str | None = None,
    name: str | None = None,
    assistant: str | None = None,
    history: bool = False,
    personal: bool = True,
) -> Workspace:
    """Create a workspace folder and its database. With a template, copy its config and data and load the data (with
    `history`, and a template that has one, its history instead of its starting records alone, for a demo);
    otherwise write default config files. Without a template, `you` (the PM's full name) becomes the first person and
    the workspace's user, `name` and `assistant` set the display names, and the Personal project is made unless
    `personal` is off (a computer joining a synced folder takes the folder's own). The new workspace is committed to its
    own git repository."""
    if template is not None and (you or name or assistant):
        raise WorkspaceError("Your name and the workspace's names come from the template; leave them out with --from.")
    root = path.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise WorkspaceError(f"{root} isn't empty. Choose a new folder for the workspace.")
    root.mkdir(parents=True, exist_ok=True)
    ws = Workspace(root)
    if template is not None:
        for folder in ("config", "data", "prompts", "docs", "plugins", "evals", "inbox"):
            src = template / folder
            if src.is_dir():
                shutil.copytree(src, root / folder)
    if template is not None and history and (template / HISTORY).is_dir():
        # The template's own history (a full export made by the app, and the texts of the inputs in it) is what a demo
        # opens on, in place of the starting records alone.
        shutil.rmtree(root / "data", ignore_errors=True)
        for folder in ("data", "sources"):
            if (template / HISTORY / folder).is_dir():
                shutil.copytree(template / HISTORY / folder, root / folder)
    ws.config_dir.mkdir(exist_ok=True)
    for file_name in FILES:
        target = ws.config_dir / f"{file_name}.yaml"
        if not target.exists():
            target.write_text(render_default_file(file_name), encoding="utf-8")
    ws.data_dir.mkdir(exist_ok=True)
    ws.sources_dir.mkdir(exist_ok=True)
    (root / ".gitignore").write_text(WORKSPACE_GITIGNORE, encoding="utf-8")
    if git and shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)

    store = Store(ws.db_path)
    try:
        imported = any(ws.data_dir.glob("*.json"))
        if imported:
            import_data(store, ws.data_dir)
        if seed_rules(store) or imported:
            export_data(store, ws.data_dir)
        if template is None and (personal or you or name or assistant):
            _set_identity(ws, store, you, name, assistant, personal=personal)
            export_data(store, ws.data_dir)
    finally:
        store.close()
    commit_export(root, "Create workspace")
    return ws


def _set_identity(
    ws: Workspace, store: Store, you: str | None, name: str | None, assistant: str | None, *, personal: bool = True
) -> None:
    """For a workspace with no template: make the person's own project (Personal, design 6.32) unless `personal` is
    off, the PM the first person when named, and write the workspace's names and the personal project into
    config/workspace.yaml."""
    from engine.config.schema import UserSettings, WorkspaceFile
    from engine.sides import make_personal
    from engine.storage import WriteContext

    settings = WorkspaceFile()
    if you:
        with store.transaction() as tx:
            person = tx.create(
                "person",
                {"full_name": you.strip(), "name_verified": True},
                WriteContext(actor="pm", trust="trusted", op="init"),
            )
        settings.user = UserSettings(person=person.id)
    if name:
        settings.name = name.strip()
    if assistant:
        settings.assistant_name = assistant.strip()
    if personal:
        settings.project.personal = make_personal(store)
    (ws.config_dir / "workspace.yaml").write_text(render_default_file("workspace", settings), encoding="utf-8")
