"""The `cockpit` command."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

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

    sp = sub.add_parser("ai", help="check the AI setup")
    ws_arg(sp)
    sp.add_argument("action", choices=["test"], help="test: one small live call per tier and account")
    sp.set_defaults(func=cmd_ai)

    sp = sub.add_parser("backup", help="copy the workspace to the configured backup folders now")
    ws_arg(sp)
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser("evaluate", help="score an AI account on a fictional workspace's cases")
    sp.add_argument("--from", dest="template", type=Path, required=True, help="workspace whose evals/ to run")
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
    from engine.ai.smoke import untested_since_change

    if untested_since_change(ws):
        print("Note: the AI settings haven't passed `cockpit ai test` since they last changed.", file=sys.stderr)
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

    app = create_app(ws, cfg, token, on_shutdown=shut_down, start_worker=True)

    class Server(uvicorn.Server):
        def handle_exit(self, sig: int, frame: Any) -> None:
            # Live streams end first, so the server isn't kept waiting on open connections.
            app.state.events.close()
            super().handle_exit(sig, frame)

    server = Server(uvicorn.Config(app, host=cfg.server.host, port=cfg.server.port, log_level="warning"))
    try:
        server.run()
    except KeyboardInterrupt:
        pass
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


def cmd_ai(args: argparse.Namespace) -> int:
    from engine.ai.smoke import record, smoke_test

    ws = resolve(args.workspace)
    cfg = ws.config()
    results = smoke_test(cfg, os.environ)
    for r in results:
        role = "main" if r.main else "fallback"
        print(f"{'ok  ' if r.ok else 'FAIL'}  {r.tier:<10} {role:<8} {r.account or '-'}: {r.detail}")
    record(ws, results)
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


def cmd_evaluate(args: argparse.Namespace) -> int:
    from engine.config import load_config
    from engine.evaluate import evaluate

    template = args.template
    if not (template / "evals").is_dir():
        print(f"cockpit: {template} has no evals/ folder.", file=sys.stderr)
        return 1
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
    )
    print(report.as_json() if args.json else report.text())
    return 0 if report.pass_rate() >= settings.min_score else 1


def cmd_selfcheck(args: argparse.Namespace) -> int:
    from engine.selfcheck import run

    return run(private_workspace=Path(args.workspace) if args.workspace else None)


if __name__ == "__main__":
    raise SystemExit(main())
