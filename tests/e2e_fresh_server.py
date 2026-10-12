"""Starts the app for the journey tests the way a person does: `cockpit init` with no template, then `cockpit serve`.

    uv run python -m tests.e2e_fresh_server --port 8783 --state /path/to/state

This script only prepares what the person's computer would already have, then replaces itself with the real serve
command, so the journeys run the real start-up (including Restart now, which needs the process `cockpit serve` started):

- a new workspace made by `cockpit init` with no template, no account and nothing set;
- a folder for backups that exists (the person picks it on screen) and a folder to read as a source;
- the file `info.json` in the state folder, which the fake services (`tests.fake_services`) serve to the browser tests:
  the app's token, those two folders and the workspace.

Nothing is set in the workspace's settings; the developer switch for the wording check is the only thing added to the
environment, as in every test.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from engine.cli import main as cockpit
from engine.workspace import Workspace

# The browser tests run with the wording check on, so a message that names a file, a key or a command fails there too.
os.environ["COCKPIT_CHECK_WORDING"] = "1"


def prepare(state: Path) -> Workspace:
    """A clean state folder holding the workspace `cockpit init` makes, and the two folders the journeys use."""
    shutil.rmtree(state, ignore_errors=True)
    state.mkdir(parents=True)
    for name in ("offsite", "source"):
        (state / name).mkdir()
    path = state / "workspace"
    if cockpit(["init", str(path)]) != 0:
        raise SystemExit("cockpit init failed")
    ws = Workspace(path)
    info = {
        "token": ws.install_token(),
        "workspace": str(path),
        "backup_folder": str(state / "offsite"),
        "source_folder": str(state / "source"),
    }
    (state / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return ws


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    ws = prepare(args.state.resolve())
    command = [sys.executable, "-m", "engine.cli", "serve", "-w", str(ws.root), "--port", str(args.port), "--no-open"]
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, command)  # noqa: S606 - the real serve command takes over this process


if __name__ == "__main__":
    main()
