"""The `cockpit` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.config import ConfigError
from engine.storage import Store, StoreError
from engine.storage.export import commit_export, export_data, import_data
from engine.storage.lease import Lease, LeaseHeld
from engine.workspace import WorkspaceError, init_workspace, resolve


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
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
    sp.add_argument("--from", dest="template", type=Path, help="copy config and data from this workspace (a fixture)")
    sp.add_argument("--no-git", action="store_true", help="don't make the workspace a git repository")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("serve", help="run the app on this computer")
    ws_arg(sp)
    sp.add_argument("--host", help="address to listen on (server.host)")
    sp.add_argument("--port", type=int, help="port to listen on (server.port)")
    sp.add_argument("--base-path", help="path to serve under (server.base_path)")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("export", help="write the readable export to data/ and commit it")
    ws_arg(sp)
    sp.add_argument("--no-commit", action="store_true")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("import", help="load an export into an empty workspace database")
    ws_arg(sp)
    sp.add_argument("data_dir", type=Path, nargs="?", help="export folder (default: the workspace's data/)")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("config", help="show the effective configuration")
    ws_arg(sp)
    sp.add_argument("action", choices=["show"])
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("takeover", help="take this workspace from a copy that stopped without closing")
    ws_arg(sp)
    sp.add_argument("--force", action="store_true", help="take it even if the other copy still seems to be running")
    sp.set_defaults(func=cmd_takeover)

    sp = sub.add_parser("selfcheck", help="run the product's own checks")
    sp.add_argument("--workspace", "-w", help="also scan code against this private workspace's specifics")
    sp.set_defaults(func=cmd_selfcheck)
    return p


def cmd_init(args: argparse.Namespace) -> int:
    ws = init_workspace(args.path, template=args.template, git=not args.no_git)
    store = Store(ws.db_path)
    try:
        count = sum(len(store.read().list(kind)) for kind in store.read().kinds())
    finally:
        store.close()
    if count:
        print(f"Loaded {count} records.")
    print(f"Workspace ready at {ws.root}")
    print(f"Start it with: cockpit serve --workspace {ws.root}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from api.app import create_app

    ws = resolve(args.workspace)
    flags = {"server.host": args.host, "server.port": args.port, "server.base_path": args.base_path}
    cfg = ws.config(flags=flags)
    if cfg.server.mode == "hosted":
        print("cockpit: hosted mode isn't available yet; set server.mode to local.", file=sys.stderr)
        return 1
    store = Store(ws.db_path)
    lease = Lease(store)
    lease.acquire()
    lease.keep_alive(on_lost=lambda: print("cockpit: another copy took over this workspace.", file=sys.stderr))
    token = ws.install_token()
    prefix = "" if cfg.server.base_path == "/" else cfg.server.base_path
    url = f"http://{cfg.server.host}:{cfg.server.port}{prefix}/?token={token}"
    print(f"Open {url}")
    released = False

    def shut_down() -> None:
        nonlocal released
        if not released:
            released = True
            lease.release()
            store.close()

    app = create_app(ws, cfg, token, on_shutdown=shut_down)
    try:
        uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, log_level="warning")
    finally:
        shut_down()
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
        count = import_data(store, args.data_dir or ws.data_dir)
    finally:
        store.close()
    print(f"Loaded {count} records.")
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


def cmd_selfcheck(args: argparse.Namespace) -> int:
    from engine.selfcheck import run

    return run(private_workspace=Path(args.workspace) if args.workspace else None)


if __name__ == "__main__":
    raise SystemExit(main())
