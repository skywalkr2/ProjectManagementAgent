"""The `cockpit` command."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from engine.config import ConfigError
from engine.local_guards import local_address_problem
from engine.shipped import DEMOS, demo
from engine.storage import Store, StoreError
from engine.storage.export import commit_export, export_data, import_data
from engine.storage.lease import Lease, LeaseHeld
from engine.workspace import Workspace, WorkspaceError, init_workspace, resolve
from engine.yaml_load import load_yaml

STALE_BUILD = "The web screens are out of date. Run: npm --prefix web run build"
TEMP_FOLDER = "This folder is emptied when the computer restarts. Keep workspaces in your home folder."
_TEMP_NAMES = ("/tmp", "/private/tmp")


def repo_root() -> Path:
    """The folder this package was run from, found from the package's own location, not the current directory."""
    return Path(__file__).resolve().parents[1]


def web_build_notice(root: Path) -> str | None:
    """A notice when the built web screens are missing or older than the newest file under `web/src`."""
    source = root / "web" / "src"
    if not source.is_dir():
        return None
    built = root / "web" / "dist" / "index.html"
    if not built.is_file():
        return STALE_BUILD
    newest = max((f.stat().st_mtime for f in source.rglob("*") if f.is_file()), default=0.0)
    return STALE_BUILD if newest > built.stat().st_mtime else None


def system_temp_roots() -> tuple[Path, ...]:
    """Folders the computer empties on its own."""
    return tuple(Path(p).resolve() for p in (tempfile.gettempdir(), *_TEMP_NAMES))


def temp_folder_notice(path: Path, roots: Iterable[Path] | None = None) -> str | None:
    """A notice when a workspace folder is inside one of the system's temporary folders."""
    resolved = Path(path).expanduser().resolve()
    for root in system_temp_roots() if roots is None else roots:
        if resolved == Path(root).resolve() or Path(root).resolve() in resolved.parents:
            return TEMP_FOLDER
    return None


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if argv is None and Path(sys.argv[0]).name == "cockpit":
        # Run as the command from a source checkout (`uv run cockpit`): make `cockpit` work in any folder from now on.
        link_command(repo_root(), Path(sys.executable).parent / "cockpit", os.environ, print)
    if not getattr(args, "func", None):
        # `cockpit` on its own starts the person's workspace: the one used last, or a new one in their home folder.
        args = parser.parse_args(["start"])
    try:
        return args.func(args) or 0
    except (WorkspaceError, ConfigError, StoreError, LeaseHeld) as err:
        print(f"cockpit: {err}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cockpit", description="PM Cockpit")
    sub = p.add_subparsers(metavar="command")

    def ws_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--workspace", "-w", help="workspace folder (default: $COCKPIT_WORKSPACE)")

    sp = sub.add_parser("init", help="create a workspace")
    sp.add_argument("path", type=Path)
    sp.add_argument(
        "--from",
        dest="template",
        type=Path,
        help="copy config and data from this workspace. The fictional workspaces are for trying things and for "
        "tests, not for a real start; leave this out to begin with an empty workspace",
    )
    sp.add_argument("--no-git", action="store_true", help="don't make the workspace a git repository")
    sp.add_argument("--you", help="your full name: you become the first person and the workspace's user")
    sp.add_argument("--name", help="the workspace's display name")
    sp.add_argument("--assistant", help="the assistant's display name")
    sp.add_argument(
        "--sync", type=Path, help="a synced folder that already holds the workspace: set this computer up from it"
    )
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser(
        "start", help="start your workspace and open it (the default): the one used last, or a new one if there is none"
    )
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("serve", help="run the app on this computer")
    ws_arg(sp)
    sp.add_argument("--host", help="address to listen on (server.host)")
    sp.add_argument("--port", type=int, help="port to listen on (server.port)")
    sp.add_argument("--base-path", help="path to serve under (server.base_path)")
    _open_args(sp)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser(
        "demo",
        help="try an add-on on a demo workspace of made-up data (the fictional workspaces are for trying things and "
        "for tests, not for real work)",
    )
    sp.add_argument(
        "folder",
        type=Path,
        nargs="?",
        default=Path("~/cockpit-demo"),
        help="where the demo lives",
    )
    sp.add_argument("--which", choices=DEMOS, default="demo-b", help="which demo to start from (default: %(default)s)")
    sp.add_argument("--fresh", action="store_true", help="start over: replace the demo folder with a new copy")
    sp.add_argument(
        "--plugin",
        action="append",
        default=[],
        help="try a plugin in the demo: its folder (linked, so edits show after a restart) or an installed plugin's "
        "name; repeat for more",
    )
    _open_args(sp, default=True)
    sp.set_defaults(func=cmd_demo, host=None, port=None, base_path=None)

    sp = sub.add_parser("update", help="bring this source checkout up to date and rebuild the screens")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("restore", help="make a new workspace from one dated backup folder")
    sp.add_argument("--backup", type=Path, required=True, help="the dated backup folder (it holds cockpit.db)")
    sp.add_argument("path", type=Path, help="the new workspace folder; it must not hold any files")
    sp.add_argument(
        "--key",
        help="for an encrypted backup, where its key is kept: env:NAME or file:/path (asked for when left out)",
    )
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("export", help="write the readable export to data/ and commit it")
    ws_arg(sp)
    sp.add_argument("--no-commit", action="store_true")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("import", help="load an export into an empty workspace database")
    ws_arg(sp)
    sp.add_argument(
        "data_dir", type=Path, nargs="?", help="export folder or synced folder (default: the workspace's data/)"
    )
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("sync", help="settle a workspace both computers changed while they couldn't sync")
    ws_arg(sp)
    sp.add_argument("action", choices=["keep"])
    which = sp.add_mutually_exclusive_group(required=True)
    which.add_argument("--here", action="store_true", help="keep this computer's copy; the folder's is backed up")
    which.add_argument("--folder", action="store_true", help="keep the synced folder's copy; this one is backed up")
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("template", help="list, apply or save workspace templates")
    ws_arg(sp)
    sp.add_argument("action", choices=["list", "apply", "save"])
    sp.add_argument("name", nargs="?", help="apply: a starting template's id or a file; save: the file to write")
    sp.add_argument("--title", default="My template", help="save: the template's name")
    sp.add_argument("--description", default="", help="save: one line on what it sets up")
    sp.add_argument("--plugin", action="append", default=[], help="save: a plugin whose settings to include")
    sp.set_defaults(func=cmd_template)

    sp = sub.add_parser("config", help="show the effective configuration")
    ws_arg(sp)
    sp.add_argument("action", choices=["show"])
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("takeover", help="take this workspace from a copy that stopped without closing")
    ws_arg(sp)
    sp.add_argument("--force", action="store_true", help="take it even if the other copy still seems to be running")
    sp.set_defaults(func=cmd_takeover)

    sp = sub.add_parser("ai", help="check the AI setup")
    ws_arg(sp)
    sp.add_argument("action", choices=["test"], help="test: one small live call per tier and account")
    sp.set_defaults(func=cmd_ai)

    sp = sub.add_parser("backup", help="copy the workspace to the configured backup folders now")
    ws_arg(sp)
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser("install", help="install an add-on from its package file (.whl)")
    sp.add_argument("file", type=Path, help="the add-on's package file")
    sp.set_defaults(func=cmd_install)

    sp = sub.add_parser("pack", help="check a pack before asking for it to be published")
    sp.add_argument("action", choices=["check"])
    sp.add_argument(
        "plugin", help="the pack's plugin folder (the one holding plugin.yaml), or an installed plugin's name"
    )
    sp.add_argument("--entry", type=Path, help="its catalog entry (catalog/pack.yaml), to compare with plugin.yaml")
    sp.set_defaults(func=cmd_pack)

    sp = sub.add_parser("evaluate", help="score an AI account on a fictional workspace's cases")
    sp.add_argument("--from", dest="template", type=Path, help="workspace whose evals/ to run (default: --workspace)")
    sp.add_argument(
        "--workspace", "-w", type=Path, help="use this workspace's AI setup, and its evals/ unless --from is given"
    )
    sp.add_argument("--account", help="provider/model to test (default: the configured routine tier)")
    sp.add_argument("--ai-config", type=Path, help="use this ai.yaml instead of the cases' own AI setup")
    sp.add_argument("--runs", type=int, help="runs per case (default: ai.evaluation.runs)")
    sp.add_argument("--case", action="append", dest="only", help="run only this case (repeatable)")
    sp.add_argument("--stub", action="store_true", help="answer each case ideally; checks the cases, not a model")
    sp.add_argument("--json", action="store_true", help="print the report as JSON")
    sp.set_defaults(func=cmd_evaluate)

    sp = sub.add_parser("selfcheck", help="run the product's own checks")
    sp.add_argument("--workspace", "-w", help="also scan code against this private workspace's specifics")
    sp.set_defaults(func=cmd_selfcheck)
    return p


def _open_args(sp: argparse.ArgumentParser, default: bool | None = None) -> None:
    which = sp.add_mutually_exclusive_group()
    which.add_argument("--open", dest="open_browser", action="store_true", help="open the app in the browser")
    which.add_argument("--no-open", dest="open_browser", action="store_false", help="don't open the browser")
    sp.set_defaults(open_browser=default)


def cmd_demo(args: argparse.Namespace) -> int:
    """Copy a demo workspace into the folder if it isn't there yet (or with --fresh), then serve it."""
    folder = args.folder.expanduser().resolve()
    if (folder / "config" / "workspace.yaml").is_file():
        ws = Workspace(folder)
        if not ws.config().workspace.demo:
            print(f"cockpit: {folder} holds a workspace that isn't a demo. Choose another folder.", file=sys.stderr)
            return 1
        if args.fresh:
            store = Store(ws.db_path)
            try:
                Lease(store).acquire()  # refuses while the demo is running elsewhere
            finally:
                store.close()
            shutil.rmtree(folder)
    if not folder.exists() or not any(folder.iterdir()):
        init_workspace(folder, template=demo(args.which))
        print(f"Made a demo workspace at {folder}. Everything in it is made up.")
    for plugin in args.plugin:
        print(f"Trying the plugin {add_plugin(Workspace(folder), plugin)} in the demo.")
    args.workspace = str(folder)
    return cmd_serve(args)


def add_plugin(ws: Workspace, plugin: str) -> str:
    """Turn a plugin on in a workspace: a folder holding plugin.yaml is linked into the workspace's plugins/ (copied
    where links aren't allowed); anything else is taken as an installed plugin's name. Returns the plugin's name."""
    from engine.config.yaml_edit import set_key

    source = Path(plugin).expanduser()
    if (source / "plugin.yaml").is_file():
        manifest = load_yaml((source / "plugin.yaml").read_text(encoding="utf-8")) or {}
        name = str(manifest.get("name") or source.resolve().name)
        target = ws.root / "plugins" / name
        target.parent.mkdir(exist_ok=True)
        if target.is_symlink() and target.resolve() != source.resolve():
            raise WorkspaceError(f"The demo already tries another plugin named {name}. Start over with --fresh.")
        if not target.is_symlink():
            if target.exists():
                shutil.rmtree(target)  # an earlier copy: take the plugin as it is now
            try:
                target.symlink_to(source.resolve(), target_is_directory=True)
            except OSError:
                shutil.copytree(source, target)
    elif "/" in plugin or "\\" in plugin or Path(plugin).suffix:
        raise WorkspaceError(f"{plugin} isn't a plugin folder (it has no plugin.yaml) or an installed plugin's name.")
    else:
        name = plugin
    path = ws.config_dir / "workspace.yaml"
    text = path.read_text(encoding="utf-8")
    enabled = list((load_yaml(text) or {}).get("plugins", {}).get("enabled", []))
    if name not in enabled:
        path.write_text(set_key(text, ["plugins", "enabled"], [*enabled, name]), encoding="utf-8")
    return name


def cmd_install(args: argparse.Namespace) -> int:
    """Install an add-on's package file into this copy of the app, with the same checks as the Add-ons screen's Install:
    pure Python, needs the app already has, nothing outside its own folders. Works the same for a source copy and an
    installed one, and `cockpit update` keeps it."""
    from engine import pack_install

    path = args.file.expanduser()
    if not path.is_file():
        print(f"cockpit: there is no file at {path}.", file=sys.stderr)
        return 1
    try:
        done = pack_install.install(path.read_bytes())
    except pack_install.InstallError as err:
        print(f"cockpit: {err}.", file=sys.stderr)
        return 1
    print(f"Installed {done.name} {done.version}.")
    print("Turn it on in the app (Add-ons, or the walkthrough's Mail and calendar step); it starts after a restart.")
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    from engine.pack_check import check

    report = check(args.plugin, args.entry)
    print("\n".join(report.lines()))
    print("All checks pass." if report.ok else f"{len(report.failed)} check(s) failed.")
    return 0 if report.ok else 1


def cmd_init(args: argparse.Namespace) -> int:
    if args.sync is not None and (args.template or args.you or args.name or args.assistant):
        print(
            "cockpit: --sync takes everything from the synced folder; leave out --from and the names.", file=sys.stderr
        )
        return 1
    ws = init_workspace(
        args.path, template=args.template, git=not args.no_git, you=args.you, name=args.name, assistant=args.assistant
    )
    if args.sync is not None:
        from engine.handover import Refused, open_workspace

        storage = load_yaml((ws.config_dir / "storage.yaml").read_text(encoding="utf-8")) or {}
        storage.setdefault("sync", {})["folder"] = str(args.sync.expanduser().resolve())
        (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage, sort_keys=False), encoding="utf-8")
        try:
            opened = open_workspace(ws, ws.config())
        except Refused as err:
            print(f"cockpit: {err}", file=sys.stderr)
            return 1
        if opened.action not in ("loaded", "first"):
            print(f"cockpit: the synced folder couldn't be loaded. {opened.message}", file=sys.stderr)
            return 1
        from engine.handover import release

        release(ws, ws.config())
    store = Store(ws.db_path)
    try:
        count = sum(len(store.read().list(kind)) for kind in store.read().kinds())
    finally:
        store.close()
    if count:
        print(f"Loaded {count} records.")
    if notice := temp_folder_notice(ws.root, system_temp_roots()):
        print(notice, file=sys.stderr)
    print(f"Workspace ready at {ws.root}")
    print(f"Start it with: cockpit serve --workspace {ws.root}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    from engine.backup import KeyNeeded, RestoreError, restore_backup
    from engine.secrets import SecretError, resolve_secret

    key = None
    if args.key:
        try:
            key = resolve_secret(args.key)
        except SecretError as err:
            print(f"cockpit: the backup's key can't be read: {err}", file=sys.stderr)
            return 1
    try:
        try:
            restored = restore_backup(args.backup, args.path, key)
        except KeyNeeded as err:
            if key is not None or not sys.stdin.isatty():
                print(f"cockpit: {err} Give --key with where it is kept (env:NAME or file:/path).", file=sys.stderr)
                return 1
            import getpass

            restored = restore_backup(args.backup, args.path, getpass.getpass("Key for this backup: "))
    except RestoreError as err:
        print(f"cockpit: {err}", file=sys.stderr)
        return 1
    root = restored.workspace.root
    print(f"Restored {restored.records} records ({restored.ledger} changes in the log) into {root}")
    print("The backup was not changed.")
    if notice := temp_folder_notice(root, system_temp_roots()):
        print(notice, file=sys.stderr)
    print(f"Start it with: cockpit serve -w {root}")
    return 0


#: Runs one command in a folder and returns its exit code and, when asked to capture, what it printed. Updating takes
#: one, so a test can stand in for the real thing.
Runner = Callable[[list[str], Path, bool], tuple[int, str]]

INSTALL_STEP = (
    "This copy of PM Cockpit isn't a source checkout, so `cockpit update` can't update it. To update an installed "
    "copy, run the install step again with the newer package file (docs/install.md):\n"
    "  sh install.sh pm_cockpit-<version>-py3-none-any.whl                                  # macOS, Linux\n"
    "  powershell -ExecutionPolicy Bypass -File install.ps1 pm_cockpit-<version>-py3-none-any.whl   # Windows\n"
    "Your workspaces are separate folders and aren't touched."
)
LOCAL_CHANGES = (
    "This copy has changes of its own, so it was not updated. Save or set aside your changes, then run "
    "`cockpit update` again."
)
NO_NODE = (
    "The screens were not rebuilt: Node (npm) isn't installed. Install Node 22.12 or newer and run `cockpit update` "
    "again to rebuild them."
)
RESTART_NOTE = "If the app is running, it shows Restart now."


def run_command(command: list[str], cwd: Path, capture: bool) -> tuple[int, str]:
    """Run a command in a folder. Its output shows as it comes, unless it is captured and returned. A program that
    can't be started gives exit code 127."""
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=capture, text=True, check=False)  # noqa: S603
    except OSError as err:
        print(f"cockpit: couldn't start {command[0]} ({err}).", file=sys.stderr)
        return 127, ""
    return done.returncode, (done.stdout or "") if capture else ""


def update_checkout(
    root: Path,
    run: Runner = run_command,
    which: Callable[[str], str | None] = shutil.which,
    say: Callable[[str], None] = print,
) -> int:
    """Bring a source checkout up to date: a fast-forward pull, the Python environment (keeping add-ons installed from
    the screen), then the web tools and the screens' build. Refuses when the checkout has changes of its own, stops at
    the first failing step, and says what changed and that a running app offers a restart."""
    if not (root / ".git").exists():
        say(INSTALL_STEP)
        return 1
    code, changes = run(["git", "status", "--porcelain", "--untracked-files=no"], root, True)
    if code != 0:
        say(f"cockpit: couldn't read the state of {root} (exit code {code}).")
        return 1
    if changes.strip():
        say(f"cockpit: {LOCAL_CHANGES}")
        return 1
    _, before = run(["git", "rev-parse", "--short", "HEAD"], root, True)
    steps: list[tuple[str, list[str]]] = [
        ("Getting the latest version", ["git", "pull", "--ff-only"]),
        ("Updating the Python environment", ["uv", "sync", "--inexact"]),
    ]
    npm = which("npm") if (root / "web").is_dir() else None
    if (root / "web").is_dir() and npm:
        steps += [
            ("Installing the web tools", [npm, "--prefix", "web", "install"]),
            ("Building the screens", [npm, "--prefix", "web", "run", "build"]),
        ]
    for number, (name, command) in enumerate(steps, start=1):
        say(f"[{number}/{len(steps)}] {name} ({' '.join(command)})")
        code, _ = run(command, root, False)
        if code != 0:
            say(f'cockpit: the step "{name}" failed (exit code {code}). Nothing after it was run.')
            return 1
    if (root / "web").is_dir() and not npm:
        say(NO_NODE)
    _, after = run(["git", "rev-parse", "--short", "HEAD"], root, True)
    before, after = before.strip(), after.strip()
    say("Already up to date." if before == after else f"Updated from {before} to {after}.")
    say(RESTART_NOTE)
    return 0


def command_folder(env: Mapping[str, str]) -> Path:
    """Where uv puts the commands of the programs it installs, by its own rules: UV_TOOL_BIN_DIR, then XDG_BIN_HOME,
    then the folder beside XDG_DATA_HOME, then `.local/bin` in the home folder."""
    if env.get("UV_TOOL_BIN_DIR"):
        return Path(env["UV_TOOL_BIN_DIR"]).expanduser()
    if env.get("XDG_BIN_HOME"):
        return Path(env["XDG_BIN_HOME"]).expanduser()
    if env.get("XDG_DATA_HOME"):
        return Path(env["XDG_DATA_HOME"]).expanduser().parent / "bin"
    return Path(env.get("HOME") or Path.home()).expanduser() / ".local" / "bin"


def link_command(root: Path, script: Path, env: Mapping[str, str], say: Callable[[str], None]) -> None:
    """From a source checkout on macOS or Linux: link `cockpit` in uv's command folder to this checkout's own command,
    so it works in any folder. An installed copy, or a link to another checkout that still exists, is left alone; a
    link to one that is gone is replaced. Says so once, when the link is made. Failing to make it changes nothing."""
    if os.name == "nt" or not (root / ".git").exists() or not script.is_file():
        return
    folder = command_folder(env)
    target = folder / "cockpit"
    if target.is_symlink():
        if target.exists() and target.resolve() == script.resolve():
            return
        if target.exists():
            return  # another checkout's command
    elif target.exists():
        return  # an installed copy
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.symlink_to(script.resolve())
    except OSError:
        return
    on_path = str(folder) in (env.get("PATH") or "").split(os.pathsep)
    then = "" if on_path else " Open a new terminal first; if it still isn't found there, run: uv tool update-shell"
    say(f"From now on, `cockpit` works in any folder (it runs this copy, {root}).{then}")


def cmd_update(args: argparse.Namespace) -> int:
    return update_checkout(repo_root(), run_command, shutil.which)


#: Where `cockpit` on its own makes a workspace the first time, inside the person's home folder.
DEFAULT_FOLDER = "Cockpit"
#: The per-person file that remembers the workspace started last, so `cockpit` alone reopens it.
LAST_FILE = Path(".pm-cockpit") / "last-workspace"


def last_workspace() -> Path | None:
    """The workspace started last on this computer, when it still exists."""
    try:
        path = Path((Path.home() / LAST_FILE).read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return path if (path / "config").is_dir() else None


def remember_workspace(root: Path) -> None:
    """Remember the workspace just started, for the next `cockpit` on its own. Failing to write it changes nothing."""
    try:
        file = Path.home() / LAST_FILE
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(str(root) + "\n", encoding="utf-8")
    except OSError:
        pass


def cmd_start(args: argparse.Namespace) -> int:
    """Start the person's workspace with nothing to remember: the one named by the environment, else the one started
    last, else the `Cockpit` folder in their home folder, made the first time (the walkthrough opens there)."""
    from engine.workspace import ENV_WORKSPACE, init_workspace

    chosen = os.environ.get(ENV_WORKSPACE)
    root = Path(chosen).expanduser() if chosen else last_workspace() or Path.home() / DEFAULT_FOLDER
    if not (root / "config").is_dir():
        if root.exists() and any(root.iterdir()):
            print(
                f"cockpit: {root} already holds other files, so a workspace can't be made there. Move them, or start "
                "a workspace elsewhere with: cockpit init <a new folder>",
                file=sys.stderr,
            )
            return 1
        init_workspace(root)
        print(f"Made your workspace in {root}.")
    return cmd_serve(_parser().parse_args(["serve", "-w", str(root), "--open"]))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from api.app import create_app

    ws = resolve(args.workspace)
    flags = {
        "server.host": args.host,
        "server.port": args.port,
        "server.base_path": args.base_path,
        "server.open_browser": args.open_browser,
    }
    cfg = ws.config(flags=flags)
    if cfg.server.mode == "hosted":
        print("cockpit: hosted mode isn't available yet; set server.mode to local.", file=sys.stderr)
        return 1
    if problem := local_address_problem(cfg.server):
        print(f"cockpit: {problem}", file=sys.stderr)
        return 1
    from engine.handover import Refused, open_or_hold

    try:
        opened = open_or_hold(ws, cfg)
    except Refused as err:
        print(f"cockpit: {err}", file=sys.stderr)
        return 1
    remember_workspace(ws.root)
    if opened.kept:
        which, saved = opened.kept
        side = "this computer" if which == "here" else "the synced folder"
        print(f"Kept {side}'s copy. The other was saved to {saved}.")
    if opened.action == "loaded":
        print(f"Loaded the newer copy from the synced folder (this computer's copy was saved to {opened.backup}).")
    if opened.message:
        print(f"Note: {opened.message}", file=sys.stderr)
    if opened.conflict_copies:
        print(
            "Note: the synced folder has copies its sync service made on a conflict; they were not loaded:\n  "
            + "\n  ".join(opened.conflict_copies),
            file=sys.stderr,
        )
    store = Store(ws.db_path)
    lease = Lease(store)
    lease.acquire()
    lease.keep_alive(on_lost=lambda: print("cockpit: another copy took over this workspace.", file=sys.stderr))
    if note := untested_ai_note(ws, cfg, store):
        print(note, file=sys.stderr)
    for notice in (web_build_notice(repo_root()), temp_folder_notice(ws.root, system_temp_roots())):
        if notice:
            print(notice, file=sys.stderr)
    token = ws.install_token()
    prefix = "" if cfg.server.base_path == "/" else cfg.server.base_path
    url = f"http://{cfg.server.host}:{cfg.server.port}{prefix}/?token={token}"
    print(f"Open {url}")
    if cfg.server.open_browser and not os.environ.pop(RESTARTED, ""):
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    released = False

    def shut_down() -> None:
        nonlocal released
        if not released:
            released = True
            lease.release()
            store.close()

    restart = threading.Event()

    def ask_restart() -> None:
        restart.set()
        server.stop()

    app = create_app(
        ws,
        cfg,
        token,
        on_shutdown=shut_down,
        start_worker=True,
        on_restart=ask_restart,
        sync_held=opened.action == "held",
    )

    class CockpitServer(uvicorn.Server):
        """The web server, with live streams ended first on the way out so it isn't kept waiting on them."""

        def handle_exit(self, sig: int, frame: Any) -> None:
            app.state.events.close()
            super().handle_exit(sig, frame)

        def stop(self) -> None:
            """Stop serving from any thread without a signal: a signal the server catches is raised again once it
            has stopped, which would end the process before it could start itself again."""
            app.state.events.close()
            self.should_exit = True

    server = CockpitServer(uvicorn.Config(app, host=cfg.server.host, port=cfg.server.port, log_level="warning"))
    try:
        server.run()
    except KeyboardInterrupt:
        restart.clear()
    finally:
        shut_down()
    if restart.is_set():
        return restart_self()
    return 0


#: Set in the environment of a process that started itself again, so it doesn't open another browser tab.
RESTARTED = "COCKPIT_RESTARTED"
#: Options that act once, at the start the person typed, never again on a restart: starting the demo over would erase
#: everything done in it since.
ONCE_ONLY = ("--fresh",)


def untested_ai_note(ws: Any, cfg: Any, store: Any) -> str | None:
    """A note for the terminal when an AI account exists and hasn't passed its test since its settings changed. A new
    workspace has no account yet, and its walkthrough adds and tests one, so it gets no note."""
    from engine.ai.smoke import ai_state, untested_since_change

    if not untested_since_change(ws) or ai_state(ws, cfg, store)[0] == "not_set_up":
        return None
    return (
        "Note: the AI account hasn't passed its test since its settings changed. Press Test on its screen, or run "
        "`cockpit ai test`."
    )


def restart_args(args: list[str]) -> list[str]:
    """The command line to start again with: the same, without the options that act only once."""
    return [a for a in args if a not in ONCE_ONLY]


def restart_self() -> int:
    """Start this same command again to use new settings: the process replaces itself where the system allows it,
    and elsewhere (Windows) starts a new one and ends. If neither works, it says how to start it again."""
    command = [sys.executable, *restart_args(sys.orig_argv[1:])]
    os.environ[RESTARTED] = "1"  # the browser is already open on the app
    print("Restarting to use the new settings.", file=sys.stderr)
    sys.stderr.flush()
    sys.stdout.flush()
    try:
        if os.name == "nt":
            import subprocess

            subprocess.Popen(command)  # noqa: S603 - this same program again
            return 0
        os.execv(sys.executable, command)  # noqa: S606 - this same program again
    except OSError as err:
        shown = " ".join(restart_args(sys.orig_argv[1:])) or "cockpit serve"
        print(f"cockpit: couldn't restart by itself ({err}). Start it again with: {shown}", file=sys.stderr)
        return 1
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    ws = resolve(args.workspace)
    cfg = ws.config()
    store = Store(ws.db_path)
    try:
        files = export_data(store, ws.data_dir)
    finally:
        store.close()
    committed = False
    if cfg.storage.export.commit and not args.no_commit:
        committed = commit_export(ws.root, "Export")
    print(f"Wrote {len(files)} files to {ws.data_dir}" + (" and committed them." if committed else "."))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    ws = resolve(args.workspace)
    store = Store(ws.db_path)
    try:
        source = args.data_dir or ws.data_dir
        if (source / ".cockpit" / "export").is_dir():
            from engine.sync import load_folder

            count = load_folder(store, source)
        else:
            count = import_data(store, source)
    finally:
        store.close()
    print(f"Loaded {count} records.")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    from engine.handover import Refused, keep

    ws = resolve(args.workspace)
    cfg = ws.config()
    if not cfg.storage.sync.folder.strip():
        print("cockpit: no synced folder is set (storage.sync.folder).", file=sys.stderr)
        return 1
    try:
        saved = keep(ws, cfg, "here" if args.here else "folder")
    except Refused as err:
        print(f"cockpit: {err}", file=sys.stderr)
        return 1
    print(f"Kept {'this computer' if args.here else 'the synced folder'}'s copy. The other was saved to {saved}.")
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    from engine import templates

    if args.action == "list":
        for t in templates.shipped():
            print(f"{t['id']:<20} {t['name']}: {t['description']}")
        return 0
    ws = resolve(args.workspace)
    if not args.name:
        print("cockpit: name the template (apply) or the file to write (save).", file=sys.stderr)
        return 1
    try:
        if args.action == "apply":
            plugins = templates.apply(ws, args.name)
            print(f"Applied {args.name}: set up {', '.join(plugins) or 'nothing'}. Restart the app to use it.")
        else:
            if not args.plugin:
                print("cockpit: name the plugins whose settings to save with --plugin.", file=sys.stderr)
                return 1
            path = templates.save(ws, Path(args.name), args.title, args.description, args.plugin)
            print(f"Saved the template to {path}.")
    except templates.TemplateError as err:
        print(f"cockpit: {err}", file=sys.stderr)
        return 1
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    ws = resolve(args.workspace)
    cfg = ws.config()
    width = max(len(path) for path, _, _ in cfg.flat())
    for path, value, layer in cfg.flat():
        print(f"{path:<{width}}  {value!r:<30}  ({layer})")
    return 0


def cmd_takeover(args: argparse.Namespace) -> int:
    ws = resolve(args.workspace)
    store = Store(ws.db_path)
    try:
        lease = Lease(store)
        held = lease.current()
        try:
            lease.acquire(force=args.force)
        except LeaseHeld as err:
            print(
                f"cockpit: the copy on {err.info.host} still looks alive (last heartbeat {err.info.heartbeat}). "
                "Stop it, or run `cockpit takeover --force` if you're sure it has stopped.",
                file=sys.stderr,
            )
            return 1
        lease.release()
    finally:
        store.close()
    print("This workspace is free to open here." if held else "Nobody was holding this workspace.")
    return 0


def cmd_ai(args: argparse.Namespace) -> int:
    from engine.ai.checked import remember
    from engine.ai.smoke import lift_pauses, record, smoke_test

    ws = resolve(args.workspace)
    cfg = ws.config()
    store = Store(ws.db_path)
    try:
        results = smoke_test(cfg, os.environ, store=store)
    finally:
        store.close()
    for r in results:
        role = "main" if r.main else "fallback"
        print(f"{'ok  ' if r.ok else 'FAIL'}  {r.tier:<10} {role:<8} {r.account or '-'}: {r.detail}")
        if r.key_source:
            print(f"      ({r.key_source})")
    record(ws, results)
    remember(ws, cfg, results)
    lift_pauses(ws, results)
    failed = [r for r in results if r.main and not r.ok]
    print("All tiers answered." if not failed else f"{len(failed)} tier(s) can't run; fix ai.yaml and test again.")
    return 1 if failed else 0


def cmd_backup(args: argparse.Namespace) -> int:
    from engine.backup import run_backup, state

    ws = resolve(args.workspace)
    cfg = ws.config()
    if not cfg.storage.backups.targets:
        print("cockpit: no backup folder is set; add one under storage.backups.targets.", file=sys.stderr)
        return 1
    status = run_backup(ws, cfg)
    for path, result in status.items():
        print(
            f"{result.get('label') or path}: " + (f"failed: {result['last_error']}" if result["last_error"] else "ok")
        )
    print(state(ws, cfg).message)
    return 1 if any(r["last_error"] for r in status.values()) else 0


def _eval_progress(result, done: int, total: int) -> None:
    """One line per finished case on stderr, so a long run shows it is moving; the report itself goes to stdout."""
    outcome = "not run" if result.not_run else "passed" if result.passed else "failed"
    print(f"[{done}/{total}] {result.case}: {outcome} ({result.seconds:.0f}s)", file=sys.stderr, flush=True)


def cmd_evaluate(args: argparse.Namespace) -> int:
    from engine.config import load_config
    from engine.evaluate import evaluate

    workspace = args.workspace.expanduser() if args.workspace else None
    template = args.template or workspace
    if template is None:
        print("cockpit: say which cases to run: --workspace <your workspace> or --from <a workspace>.", file=sys.stderr)
        return 1
    if not (template / "evals").is_dir():
        print(
            f"cockpit: {template} has no evals/ folder. Add --from with a workspace that has one, "
            "for example the fictional workspaces/demo-b in the repository.",
            file=sys.stderr,
        )
        return 1
    if workspace is not None and not args.ai_config:
        args.ai_config = workspace / "config" / "ai.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = template / "config"
        if args.ai_config:
            config_dir = Path(tmp)
            shutil.copyfile(args.ai_config, config_dir / "ai.yaml")
        settings = load_config(config_dir, env={}).ai.evaluation
    report = evaluate(
        template,
        account=args.account,
        runs=args.runs or settings.runs,
        stub=args.stub,
        only=args.only,
        ai_config=args.ai_config,
        progress=_eval_progress,
        notice=lambda line: print(line, file=sys.stderr, flush=True),
    )
    print(report.as_json() if args.json else report.text())
    return 0 if report.pass_rate() >= settings.min_score else 1


def cmd_selfcheck(args: argparse.Namespace) -> int:
    from engine.selfcheck import run

    return run(private_workspace=Path(args.workspace) if args.workspace else None)


if __name__ == "__main__":
    raise SystemExit(main())
