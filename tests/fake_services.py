"""Fake outside services for the journey tests: one small process on 127.0.0.1 that plays every service the app talks
to, so a browser can walk a person's whole path with nothing real on the other end.

    uv run python -m tests.fake_services --port 8790 --state /path/to/state

Each service is a list of routes under its own prefix, added to `SERVICES`; the next one (a sign-in, a mail and calendar
API, an add-on catalog) is one more entry. Today:

- `/ai/v1/...` speaks the common chat format: a model list with prices, and chat completions whose answer is the
  stand-in's answer to the packet it was sent (`engine.ai.adapters.stand_in`), so the journey checks the app, not a
  model. Every chat request is recorded.
- `/__e2e/...` are the helpers the browser tests read: what the AI service was asked, the people in the fictional
  workspace to write notes about, a folder the app may read as a source (and a route that puts a file in it), and the
  token the app was started with.

The folder the app's own process works in is passed as `--state`; `tests.e2e_fresh_server` writes `info.json` there.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from engine.ai.adapters import stand_in
from tests.conftest import DEMO_B, fixture_records

HOST = "127.0.0.1"

#: Fictional model names with a price per token, as a service's own model list gives them.
MODELS = {
    "fake-small": {"prompt": "0.0000005", "completion": "0.0000015", "context_length": 128000},
    "fake-large": {"prompt": "0.000003", "completion": "0.000015", "context_length": 200000},
}


class State:
    """What the fake services remember: the chat requests received, and where the app's own folders are."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.chats: list[dict] = []

    def info(self) -> dict:
        """What the app's start-up script wrote: the token, the source folder and the backup folder."""
        try:
            return json.loads((self.folder / "info.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


# ---- the AI service --------------------------------------------------------------------------------------------------


def answer_to(system: str, user: str) -> str:
    """The text a model would send back for this packet, from the stand-in's rules."""
    if "Reply with exactly this JSON" in user:
        return json.dumps({"ok": True})
    if "<question>" in user:
        return json.dumps(stand_in.answer(user, system))
    if "<untrusted" in user or "<note>" in user:
        return json.dumps(stand_in.read(user))
    return json.dumps({"summary": "Nothing to do.", "ops": []})


def ai_routes(state: State) -> list[Route]:
    async def models(_request: Request) -> JSONResponse:
        data = [
            {
                "id": name,
                "context_length": info["context_length"],
                "pricing": {"prompt": info["prompt"], "completion": info["completion"]},
            }
            for name, info in MODELS.items()
        ]
        return JSONResponse({"object": "list", "data": data})

    async def chat(request: Request) -> JSONResponse:
        body = await request.json()
        messages = body.get("messages") or []
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        state.chats.append({"model": body.get("model"), "at": time.time(), "smoke": "Reply with exactly" in user})
        text = answer_to(system, user)
        usage = {"prompt_tokens": max(1, len(system + user) // 4), "completion_tokens": max(1, len(text) // 4)}
        return JSONResponse(
            {
                "id": f"fake-{len(state.chats)}",
                "object": "chat.completion",
                "model": body.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": usage,
            }
        )

    return [Route("/models", models), Route("/chat/completions", chat, methods=["POST"])]


# ---- the helpers the browser tests read ------------------------------------------------------------------------------

#: A fictional file the source folder is given: a meeting note in the stand-in's own sentence shapes.
SOURCE_FILE = "folder-note.txt"


def helper_routes(state: State, base: str) -> list[Route]:
    async def info(_request: Request) -> JSONResponse:
        people = [p["full_name"] for p in fixture_records(DEMO_B, "person")]
        return JSONResponse({**state.info(), "ai_base_url": f"{base}/ai/v1", "people": people})

    async def requests(_request: Request) -> JSONResponse:
        work = [c for c in state.chats if not c["smoke"]]
        return JSONResponse({"total": len(state.chats), "smoke": len(state.chats) - len(work), "work": len(work)})

    async def put_source_file(request: Request) -> JSONResponse:
        body = await request.json()
        folder = Path(state.info()["source_folder"])
        (folder / SOURCE_FILE).write_text(str(body["text"]), encoding="utf-8")
        return JSONResponse({"file": SOURCE_FILE})

    return [
        Route("/__e2e/info", info),
        Route("/__e2e/ai-requests", requests),
        Route("/__e2e/source-file", put_source_file, methods=["POST"]),
    ]


# ---- assembling ------------------------------------------------------------------------------------------------------

#: Every fake service: its prefix and the function that makes its routes. A new service is one more entry.
SERVICES: dict[str, Callable[[State], list[Route]]] = {"/ai/v1": ai_routes}


def build_app(state: State, port: int) -> Starlette:
    routes = [
        Route(f"{prefix}{r.path}", r.endpoint, methods=sorted(r.methods or []))
        for prefix, make in SERVICES.items()
        for r in make(state)
    ]
    routes += helper_routes(state, f"http://{HOST}:{port}")
    return Starlette(routes=routes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    uvicorn.run(build_app(State(args.state), args.port), host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
