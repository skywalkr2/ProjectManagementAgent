"""A server for the browser tests: a fresh copy of the imprint fixture whose stand-in AI answers each pasted case with
that case's ideal answer, so the run checks the UI and the pipeline rather than a model.

    uv run python -m tests.e2e_server --port 8781 --base-path /

It also serves the cases at /__e2e/cases so the browser test reads names from the fixture instead of writing them out.
"""

from __future__ import annotations

import argparse
import json
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

TOKEN = "e2e-token"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--base-path", default="/")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="cockpit-e2e-"))
    ws = init_workspace(tmp / "ws", template=DEMO_B, git=False)
    flags = {
        "server.base_path": args.base_path,
        "server.port": args.port,
        "ai.tiers.routine.use": "stub/default",
        "ai.tiers.routine.fallback": [],
        "storage.backups.targets": [{"path": str(tmp / "offsite"), "label": "test folder"}],
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

    async def case_list(_request):
        return JSONResponse(cases)

    outer = Starlette(routes=[Route("/__e2e/cases", case_list), Mount("/", app=app)], lifespan=_lifespan(app))
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
