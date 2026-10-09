"""The HTTP application.

Everything is served under the configured base path. In local mode every route except the health check needs the
install token, presented once as `?token=` (which sets a cookie scoped to the base path) or as a bearer header.
"""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp

from engine import __version__
from engine.config import Config
from engine.workspace import Workspace

COOKIE = "cockpit_token"
OPEN_PATHS = {"/api/health"}


def create_app(ws: Workspace, cfg: Config, token: str, *, on_shutdown: Callable[[], None] | None = None) -> ASGIApp:
    """Build the app for a workspace. The returned app serves the base path from the config.

    `on_shutdown` runs while the server shuts down, before the process exits on a stop signal, so cleanup such as
    releasing the instance lease always happens."""
    base_path = cfg.server.base_path

    @asynccontextmanager
    async def lifespan(_app: Any) -> AsyncIterator[None]:
        try:
            yield
        finally:
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

    @inner.get("/")
    def root() -> dict[str, str]:
        return {"status": "running", "ui": "not built yet"}

    if base_path == "/":
        return inner
    return Starlette(routes=[Mount(base_path, app=inner)], lifespan=lifespan)


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
