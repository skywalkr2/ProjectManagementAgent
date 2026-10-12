"""A server for the browser tests: a fresh copy of the imprint fixture whose stand-in AI answers each pasted case with
that case's ideal answer, so the run checks the UI and the pipeline rather than a model.

    uv run python -m tests.e2e_server --port 8781 --base-path /

It also serves the cases at /__e2e/cases so the browser test reads names from the fixture instead of writing them out,
and a few read-only checks of what no screen shows: the ledger of a record, whether the rules and settings are as they
were, and the export round trip of the workspace as it stands. /__e2e/backup-targets switches the configured backup
folder off and on, for the step about having none.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.cleaning import normalize
from engine.evaluate import load_cases
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip

TOKEN = "e2e-token"

# The browser tests run with the wording check on, so a message that names a file, a key or a command fails there too.
os.environ["COCKPIT_CHECK_WORDING"] = "1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--base-path", default="/")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="cockpit-e2e-"))
    ws = init_workspace(tmp / "ws", template=DEMO_B, git=False)
    (tmp / "offsite").mkdir(exist_ok=True)
    flags = {
        "server.base_path": args.base_path,
        "server.port": args.port,
        "ai.tiers.routine.use": "stub/default",
        "ai.tiers.routine.fallback": [],
        "storage.backups.targets": [{"path": str(tmp / "offsite"), "label": "test folder"}],
        # Backups only on request, so the browser tests see the state before the first one.
        "storage.backups.automatic": False,
        # A stage that starts work when entered, so the browser tests can exercise waiting for the go.
        "stages.types.project.stages": [
            {"id": "planned", "label": "Planned"},
            {"id": "active", "label": "In progress", "starts": ["notes"]},
            {"id": "complete", "label": "Complete"},
        ],
    }
    cfg = ws.config(env={}, flags=flags)
    cases = load_cases(DEMO_B)
    project = fixture_records(DEMO_B, "project")[0]["id"]

    def responder(task):  # the case whose longest pasted line is in the request
        request = normalize(task.request)
        for case in cases:
            longest = max(case.get("pasted", "").splitlines() or [""], key=len)
            if longest.strip() and normalize(longest) in request:
                return json.dumps(case["stub_answer"])
        # A note that says it belongs to a project is filed under the fixture's first one; any other is filed loose.
        note = {"op": "note", "text": "Noted.", **({"project": project} if "under the project" in request else {})}
        return json.dumps({"summary": "Filed as a note.", "ops": [note]})

    set_responder(responder)
    app = create_app(ws, cfg, TOKEN, start_worker=True)

    store = app.state.store
    folder_targets = list(cfg.storage.backups.targets)

    async def case_list(_request):
        return JSONResponse(cases)

    async def ledger(request):
        """The ledger rows of one record, oldest first."""
        kind, record_id = request.query_params["kind"], request.query_params["id"]
        return JSONResponse(store.read().ledger(kind=kind, record_id=record_id))

    async def standing(_request):
        """What the rules and settings are: how many rules, and a hash of the settings files and of the settings as the
        app reads them, plus how many changes to settings were proposed or made."""
        files = sorted(ws.config_dir.rglob("*"))
        on_disk = hashlib.sha256(b"".join(p.read_bytes() for p in files if p.is_file())).hexdigest()
        effective = hashlib.sha256(json.dumps(cfg.flat(), default=str).encode()).hexdigest()
        reader = store.read()
        return JSONResponse(
            {
                "rules": len(cfg.rules.rules),
                "settings_files": on_disk,
                "settings": effective,
                "setting_proposals": len(reader.list("setting_proposal", include_deleted=True)),
                "setting_changes": len(reader.list("setting_change", include_deleted=True)),
            }
        )

    async def export_round_trip(_request):
        """Export the workspace as it stands, load that into a fresh database and compare."""
        with tempfile.TemporaryDirectory(prefix="cockpit-e2e-round-trip-") as work:
            return JSONResponse(round_trip(store, cfg, Path(work)))

    async def backup_targets(request):
        """Turn the configured backup folder off (`configured=0`) or back on (`configured=1`)."""
        cfg.storage.backups.targets = folder_targets if request.query_params["configured"] == "1" else []
        return JSONResponse({"configured": len(cfg.storage.backups.targets)})

    outer = Starlette(
        routes=[
            Route("/__e2e/cases", case_list),
            Route("/__e2e/ledger", ledger),
            Route("/__e2e/standing", standing),
            Route("/__e2e/round-trip", export_round_trip),
            Route("/__e2e/backup-targets", backup_targets, methods=["POST"]),
            Mount("/", app=app),
        ],
        lifespan=_lifespan(app),
    )
    uvicorn.run(outer, host="127.0.0.1", port=args.port, log_level="warning")


def _lifespan(app):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_outer):
        async with app.router.lifespan_context(app):
            yield

    return lifespan


if __name__ == "__main__":
    main()
