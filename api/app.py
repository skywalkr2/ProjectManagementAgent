"""The HTTP application.

Everything is served under the configured base path. In local mode every route except the health check needs the
install token, presented once as `?token=` (which sets a cookie scoped to the base path) or as a bearer header.
"""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp

from api.routes import build_router
from engine import __version__
from engine.ai.router import Router
from engine.config import Config
from engine.storage import Store
from engine.worker import Events, Worker
from engine.workspace import Workspace

UI_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

COOKIE = "cockpit_token"
OPEN_PATHS = {"/api/health"}


def create_app(
    ws: Workspace,
    cfg: Config,
    token: str,
    *,
    on_shutdown: Callable[[], None] | None = None,
    start_worker: bool = False,
    router_factory: Callable[[], Router] | None = None,
    ui_dist: Path | None = None,
) -> ASGIApp:
    """Build the app for a workspace. The returned app serves the base path from the config.

    `on_shutdown` runs while the server shuts down, before the process exits on a stop signal, so cleanup such as
    releasing the instance lease always happens. With `start_worker`, queued requests are processed in the background;
    otherwise they wait until `app.state.worker.run_pending()` is called (tests)."""
    base_path = cfg.server.base_path
    store = Store(ws.db_path)
    events = Events()
    worker = Worker(ws, store, cfg, events, router_factory)
    dist = ui_dist if ui_dist is not None else UI_DIST

    @asynccontextmanager
    async def lifespan(_app: Any) -> AsyncIterator[None]:
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()
            store.close()
            if on_shutdown is not None:
                on_shutdown()

    inner = FastAPI(
        title="PM Cockpit",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan if base_path == "/" else None,
    )

    @inner.middleware("http")
    async def require_token(request: Request, call_next: Any) -> Any:
        path = request.url.path.removeprefix(request.scope.get("root_path", "")) or "/"
        if path in OPEN_PATHS:
            return await call_next(request)
        offered = request.query_params.get("token")
        if offered is not None and request.method == "GET":
            if not hmac.compare_digest(offered, token):
                return _unauthorized()
            clean = request.url.remove_query_params("token")
            response = RedirectResponse(str(clean), status_code=303)
            response.set_cookie(
                COOKIE,
                token,
                httponly=True,
                samesite="strict",
                path=_cookie_path(base_path),
                secure=cfg.server.mode == "hosted",
            )
            return response
        presented = request.cookies.get(COOKIE) or _bearer(request)
        if presented is None or not hmac.compare_digest(presented, token):
            return _unauthorized()
        return await call_next(request)

    @inner.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @inner.get("/api/runtime-config")
    def runtime_config() -> dict[str, Any]:
        """What the UI needs before anything else: where it is served and what to call things."""
        prefix = "" if base_path == "/" else base_path
        return {
            "base_path": base_path,
            "api_base": f"{prefix}/api",
            "assistant_name": cfg.workspace.assistant_name,
            "workspace_name": cfg.workspace.name,
            "version": __version__,
        }

    inner.include_router(build_router(ws, cfg, store, events, worker))
    inner.state.worker = worker
    inner.state.store = store

    @inner.get("/{path:path}", include_in_schema=False)
    def ui(path: str) -> Any:
        """The built UI: files by path, and index.html for every other route so the UI's own router takes over."""
        if path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        index = dist / "index.html"
        if not index.exists():
            return JSONResponse({"status": "running", "ui": "not built yet"})
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    if base_path == "/":
        return inner
    outer = Starlette(routes=[Mount(base_path, app=inner)], lifespan=lifespan)
    outer.state.worker = worker
    outer.state.store = store
    return outer


def _cookie_path(base_path: str) -> str:
    return base_path if base_path != "/" else "/"


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def _unauthorized() -> JSONResponse:
    message = "Open the link printed by `cockpit serve` to sign in on this computer."
    return JSONResponse({"error": message}, status_code=401)
