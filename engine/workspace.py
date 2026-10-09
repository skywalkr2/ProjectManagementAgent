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
from engine.storage import Store
from engine.storage.export import commit_export, export_data, import_data

ENV_WORKSPACE = "COCKPIT_WORKSPACE"
WORKSPACE_GITIGNORE = "cockpit.db\ncockpit.db-*\n.cockpit/\nsources/\n"


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
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        self.private_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        path.write_text(token + "\n", encoding="utf-8")
        path.chmod(0o600)
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


def init_workspace(path: Path, *, template: Path | None = None, git: bool = True) -> Workspace:
    """Create a workspace folder and its database. With a template, copy its config and data and load the data;
    otherwise write default config files. The new workspace is committed to its own git repository."""
    root = path.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise WorkspaceError(f"{root} isn't empty. Choose a new folder for the workspace.")
    root.mkdir(parents=True, exist_ok=True)
    ws = Workspace(root)
    if template is not None:
        for name in ("config", "data", "prompts", "docs"):
            src = template / name
            if src.is_dir():
                shutil.copytree(src, root / name)
    ws.config_dir.mkdir(exist_ok=True)
    for name in FILES:
        target = ws.config_dir / f"{name}.yaml"
        if not target.exists():
            target.write_text(render_default_file(name), encoding="utf-8")
    ws.data_dir.mkdir(exist_ok=True)
    ws.sources_dir.mkdir(exist_ok=True)
    (root / ".gitignore").write_text(WORKSPACE_GITIGNORE, encoding="utf-8")
    if git and shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)

    store = Store(ws.db_path)
    try:
        if any(ws.data_dir.glob("*.json")):
            import_data(store, ws.data_dir)
            export_data(store, ws.data_dir)
    finally:
        store.close()
    commit_export(root, "Create workspace")
    return ws
