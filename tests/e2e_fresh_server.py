"""Starts the app for the journey tests the way a person does: `cockpit init` with no template, then `cockpit serve`.

    uv run python -m tests.e2e_fresh_server --port 8783 --state /path/to/state [--https-port 8791] [--mail] [--add-ons]

This script only prepares what the person's computer would already have, then replaces itself with the real serve
command, so the journeys run the real start-up (including Restart now, which needs the process `cockpit serve` started):

- a new workspace made by `cockpit init` with no template, no account and nothing set;
- a folder for backups that exists (the person picks it on screen) and a folder to read as a source;
- the file `info.json` in the state folder, which the fake services (`tests.fake_services`) serve to the browser tests:
  the app's token, those two folders and the workspace.

With `--https-port` the fake services also answer over HTTPS. The app is made to trust their throwaway authority the
standard way, through `SSL_CERT_FILE` in its environment; nothing in the app changes for it.

- `--mail` turns on a mail and calendar add-on, as an add-on the person had already installed and turned on would be.
- `--add-ons` points the Add-ons screen at the fake catalog (and away from the one the app came with), and runs the app
  in a throwaway virtual environment that sees the project's packages, so an install from the screen goes into the
  throwaway one and never into the project's own.
- `--catalog-by-environment` (with `--add-ons`) names the fake catalog through the app's environment settings and
  leaves the workspace's settings files exactly as `cockpit init` wrote them.
- `--log` keeps what the app prints in `app.log` in the state folder (named in `info.json`), so a test can count the
  restarts the app made.

Nothing else is set in the workspace's settings; the developer switch for the wording check is the only other thing
added to the environment, as in every test.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import yaml

from engine.cli import add_plugin
from engine.cli import main as cockpit
from engine.config.yaml_edit import set_key
from engine.workspace import Workspace

# The browser tests run with the wording check on, so a message that names a file, a key or a command fails there too.
os.environ["COCKPIT_CHECK_WORDING"] = "1"

PLUGINS = Path(__file__).parent / "fixtures" / "plugins"
LOOPBACK = "127.0.0.1"


def prepare(state: Path) -> Workspace:
    """A clean state folder holding the workspace `cockpit init` makes, and the two folders the journeys use."""
    shutil.rmtree(state, ignore_errors=True)
    state.mkdir(parents=True)
    for name in ("offsite", "source"):
        (state / name).mkdir()
    path = state / "workspace"
    if cockpit(["init", str(path)]) != 0:
        raise SystemExit("cockpit init failed")
    return Workspace(path)


def trust_services(state: Path, https_port: int) -> str:
    """Make the app trust the fake services' authority the standard way and tell the mail add-on where its service is.
    The authority's file is written by the fake services when they start, after this script; it is read when needed.
    Local addresses are never sent through a proxy. Returns the services' address."""
    address = f"https://{LOOPBACK}:{https_port}"
    os.environ["SSL_CERT_FILE"] = str(state / "tls" / "authority.pem")
    os.environ.pop("SSL_CERT_DIR", None)
    os.environ["JOURNEY_SERVICE_ADDRESS"] = address
    for name in ("NO_PROXY", "no_proxy"):
        hosts = [h for h in os.environ.get(name, "").split(",") if h]
        if LOOPBACK not in hosts:
            os.environ[name] = ",".join([*hosts, LOOPBACK])
    return address


def use_catalog(ws: Workspace, address: str) -> None:
    """The workspace's catalog setting names the fake feed and not the one the app came with."""
    path = ws.config_dir / "workspace.yaml"
    text = set_key(path.read_text(encoding="utf-8"), ["plugins", "catalog", "feeds"], [f"{address}/catalog/packs.yaml"])
    text = set_key(text, ["plugins", "catalog", "shipped_feed"], False)
    path.write_text(text, encoding="utf-8")


def use_catalog_by_environment(address: str) -> None:
    """The same, through the app's environment settings; no settings file is touched."""
    os.environ["COCKPIT__WORKSPACE__PLUGINS__CATALOG__FEEDS"] = json.dumps([f"{address}/catalog/packs.yaml"])
    os.environ["COCKPIT__WORKSPACE__PLUGINS__CATALOG__SHIPPED_FEED"] = "false"


def throwaway_python(state: Path) -> tuple[Path, Path]:
    """A virtual environment in the state folder that sees the project's packages (a `.pth` file lists the project's
    own search path), so packs installed from the screen land in this one. Returns its interpreter and the project's
    folder for installed packages, which an install must never touch."""
    venv = state / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)  # noqa: S603
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    own = json.loads(
        subprocess.run(
            [python, "-c", "import json,sys;print(json.dumps(sys.path))"], capture_output=True, text=True, check=True
        ).stdout  # noqa: S603
    )
    site = Path(
        subprocess.run(
            [python, "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )  # noqa: S603
    project = [p for p in sys.path if p and p not in own and Path(p).is_dir()]
    (site / "project.pth").write_text("\n".join(project) + "\n", encoding="utf-8")
    return python, Path(sysconfig.get_paths()["purelib"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--https-port", type=int, default=0)
    parser.add_argument("--mail", action="store_true")
    parser.add_argument("--add-ons", action="store_true")
    parser.add_argument("--catalog-by-environment", action="store_true")
    parser.add_argument("--log", action="store_true")
    args = parser.parse_args()
    state = args.state.resolve()
    ws = prepare(state)
    info = {
        "token": ws.install_token(),
        "workspace": str(ws.root),
        "backup_folder": str(state / "offsite"),
        "source_folder": str(state / "source"),
    }
    python = Path(sys.executable)
    if args.https_port:
        address = trust_services(state, args.https_port)
        if args.add_ons:
            (use_catalog_by_environment(address) if args.catalog_by_environment else use_catalog(ws, address))
    if args.mail:
        add_plugin(ws, str(PLUGINS / "journey_mail"))
    if args.add_ons:
        python, project_site = throwaway_python(state)
        info["project_site"] = str(project_site)
        info["install_target"] = yaml.safe_load(
            subprocess.run(  # noqa: S603
                [python, "-c", "import sysconfig,json;print(json.dumps(sysconfig.get_paths()['purelib']))"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    if args.log:
        info["log"] = str(state / "app.log")
    (state / "info.json").write_text(json.dumps(info), encoding="utf-8")
    if args.log:
        # What the app prints goes to the file, through the serve command that replaces this process.
        with open(info["log"], "ab") as log:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
    command = [str(python), "-m", "engine.cli", "serve", "-w", str(ws.root), "--port", str(args.port), "--no-open"]
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(command[0], command)  # noqa: S606 - the real serve command takes over this process


if __name__ == "__main__":
    main()
