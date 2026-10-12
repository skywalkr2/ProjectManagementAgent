"""The HTTP application.

Everything is served under the configured base path. In local mode every route except the health check needs the
install token, presented once as `?token=` (which sets a cookie scoped to the base path) or as a bearer header.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp

from api.ask_routes import build_ask_router
from api.data_form_routes import build_data_form_router
from api.pack_routes import build_pack_router
from api.routes import build_router
from api.schemas import RuntimeConfig
from api.setup_routes import build_setup_router
from api.sign_in_routes import build_sign_in_router
from api.watch_routes import build_watch_router
from engine import __version__
from engine.ai.router import Router
from engine.config import Config
from engine.local_guards import allowed_hosts, allowed_origins
from engine.shipped import product, shipped
from engine.storage import Store
from engine.worker import Events, Worker
from engine.workspace import Workspace

UI_DIST = shipped("web")

COOKIE = "cockpit_token"
#: Paths served without the person's cookie. The sign-in callback is reached from the service's own page, so the
#: browser leaves the strict cookie off; it is protected instead by the single-use state only this app issued (with
#: PKCE), and it answers with a page that takes the person back into the app from this site, where the cookie is sent.
OPEN_PATHS = {"/api/health", "/api/sign-ins/callback"}
#: Methods that don't change anything, so the origin rule doesn't apply to them.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# The UI loads nothing from elsewhere and runs no inline script, so the policy can be strict (design 12.5). The UI's
# component library adds two fixed style rules (touch handling for pressable elements, and scroll locking on touch
# screens); they are allowed by their exact hash, so nothing else inline can apply. The browser tests fail if a
# library update changes them.
UI_STYLE_HASHES = (
    "'sha256-38RhXrc7EdReTKsOm23ZPOCUgniTUUcjky8QOOrQx6o='",
    "'sha256-gYiS/BvZvRcK27JIXTuwhZ3hs2+VJ1X+2gUlE+farlg='",
)
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        f"style-src 'self' {' '.join(UI_STYLE_HASHES)}; img-src 'self' data:; connect-src 'self'; "
        "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


log = logging.getLogger(__name__)


def create_app(
    ws: Workspace,
    cfg: Config,
    token: str,
    *,
    on_shutdown: Callable[[], None] | None = None,
    start_worker: bool = False,
    router_factory: Callable[[], Router] | None = None,
    ui_dist: Path | None = None,
    on_restart: Callable[[], None] | None = None,
) -> ASGIApp:
    """Build the app for a workspace. The returned app serves the base path from the config.

    `on_shutdown` runs while the server shuts down, before the process exits on a stop signal, so cleanup such as
    releasing the instance lease always happens. With `start_worker`, queued requests are processed in the background;
    otherwise they wait until `app.state.worker.run_pending()` is called (tests). `on_restart` is called when saved
    settings or new code need the process to start again; without it, waiting work says a restart is needed."""
    from engine.sync import placement_problem

    base_path = cfg.server.base_path
    placed = placement_problem(ws, cfg)
    if placed:
        raise RuntimeError(f"Can't start: {placed} (storage.sync.folder).")
    store = Store(ws.db_path, cfg=cfg)
    events = Events()
    if cfg.moved:
        from engine.migrate import move_identity

        move_identity(ws, store, cfg)
    from engine.lists import ensure as ensure_lists
    from engine.organizations import move_names

    move_names(store)
    ensure_lists(store)
    worker = Worker(ws, store, cfg, events, router_factory, on_restart)
    from engine.sign_in_sources import start_signed_in

    try:
        # Sources a sign-in declares, for sign-ins made before their add-on declared them; the worker takes them in.
        start_signed_in(ws, cfg, store)
    except Exception as err:  # never stops the app from starting
        log.warning("Couldn't start the sources of sign-ins made earlier: %s", err)
    instance = uuid.uuid4().hex
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

    hosts = allowed_hosts(cfg.server)
    origins = allowed_origins(cfg.server)

    # Added after the token check, so it runs first: a request for another address, or a change asked for by another
    # web page, is refused before anything else looks at it. It covers every path, including the open ones.
    @inner.middleware("http")
    async def local_guards(request: Request, call_next: Any) -> Any:
        if request.headers.get("host", "").lower() not in hosts:
            return _refused("This address isn't the app's. Open the link the app printed when it started.")
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            cross_site = request.headers.get("sec-fetch-site", "").lower() == "cross-site"
            if cross_site or (origin is not None and origin.lower() not in origins):
                return _refused("This request came from another web page, so the app didn't act on it.")
        return await call_next(request)

    # Added last so it wraps everything, including the sign-in redirects and refusals above.
    @inner.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @inner.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @inner.get("/api/runtime-config")
    def runtime_config() -> RuntimeConfig:
        """What the UI needs before anything else: where it is served, what to call things, and its settings."""
        prefix = "" if base_path == "/" else base_path
        return RuntimeConfig(
            base_path=base_path,
            api_base=f"{prefix}/api",
            assistant_name=cfg.workspace.assistant_name,
            workspace_name=cfg.workspace.name,
            version=__version__,
            pm=cfg.workspace.user.person,
            narrow_below_px=cfg.ui.narrow_below_px,
            toast_seconds=cfg.ui.toast_seconds,
            shortcuts=cfg.ui.shortcuts,
            wording={**store.plugins.wording(), **cfg.ui.wording},
            demo=cfg.workspace.demo,
            instance=instance,
            feedback_to=cfg.ui.feedback_to or product().get("feedback_to") or None,
            brand_color=cfg.ui.brand.color,
            logo=_logo(ws, cfg) is not None,
            theme=cfg.ui.theme,
            density=cfg.ui.density,
        )

    @inner.get("/api/brand/logo", include_in_schema=False)
    def brand_logo() -> Any:
        """The workspace's logo image from its config folder, when one is set and present."""
        found = _logo(ws, cfg)
        if found is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        response = FileResponse(found, media_type=_LOGO_TYPES[found.suffix.lower()])
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
        response.headers["Cache-Control"] = "no-cache"
        return response

    inner.include_router(build_router(ws, cfg, store, events, worker))
    inner.include_router(build_setup_router(ws, cfg, store, events, worker))
    inner.include_router(build_ask_router(ws, cfg, store, events, worker))
    inner.include_router(build_watch_router(ws, cfg, store, events, worker))
    inner.include_router(build_sign_in_router(ws, cfg, store))
    inner.include_router(build_pack_router(ws, cfg, store))
    inner.include_router(build_data_form_router(store))
    inner.state.worker = worker
    inner.state.store = store
    inner.state.events = events

    @inner.get("/{path:path}", include_in_schema=False)
    def ui(path: str) -> Any:
        """The built UI: files by path, and index.html for every other route so the UI's own router takes over."""
        if path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        index = dist / "index.html"
        if not index.exists():
            return JSONResponse({"status": "running", "ui": "not built yet"})
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()) and candidate != index.resolve():
            return FileResponse(candidate)
        return HTMLResponse(
            _with_base(index.read_text(encoding="utf-8"), base_path), headers={"Cache-Control": "no-store"}
        )

    if base_path == "/":
        return inner
    outer = Starlette(routes=[Mount(base_path, app=inner)], lifespan=lifespan)
    outer.state.worker = worker
    outer.state.store = store
    outer.state.events = events
    return outer


_LOGO_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def _logo(ws: Workspace, cfg: Config) -> Path | None:
    """The logo file `ui.brand.logo` names in the workspace's config folder, when it is there."""
    name = cfg.ui.brand.logo
    if not name:
        return None
    folder = ws.config_dir.resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file() or path.suffix.lower() not in _LOGO_TYPES:
        return None
    return path


def _with_base(html: str, base_path: str) -> str:
    """Point the page's relative paths (assets, API calls) at the configured base path."""
    href = base_path if base_path.endswith("/") else base_path + "/"
    return html.replace("<head>", f'<head>\n    <base href="{escape(href, quote=True)}" />', 1)


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


def _refused(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=403)
