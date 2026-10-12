"""API routes for signing in to a service an add-on connects to: the sign-ins add-ons declare and whether each is
signed in, starting one (the screen opens the service's page), the address the service sends the person back to, and
signing out."""

from __future__ import annotations

import logging
from html import escape
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from api.schemas import Ok, SignInApp, SignInStarted, SignInStep, SignInView
from engine import sign_in as flow
from engine.config import Config
from engine.connectors import ConnectorError
from engine.storage import Store
from engine.workspace import Workspace

log = logging.getLogger(__name__)


def build_sign_in_router(ws: Workspace, cfg: Config, store: Store) -> APIRouter:
    r = APIRouter(prefix="/api")
    host = store.plugins
    prefix = "" if cfg.server.base_path == "/" else cfg.server.base_path

    def keys(plugin: str):
        return ws.root / ".cockpit" / "keys" / plugin

    def find(name: str) -> flow.SignIn:
        found = host.sign_ins().get(name)
        if found is None:
            raise HTTPException(status_code=404, detail=f"there is no sign-in {name}")
        return found

    local = cfg.server.mode == "local"

    def view(s: flow.SignIn) -> SignInView:
        client_id, _, source = host.sign_in_app(s, ws.root)
        status = flow.status(keys(s.plugin), s)
        return SignInView(
            name=s.name,
            label=s.label,
            status=status,
            ready=bool(client_id),
            callback=flow.redirect_uri(cfg.server),
            allows=list(s.allows),
            account=(flow.kept(keys(s.plugin), s) or {}).get("account"),
            missing=flow.missing(s, flow.granted(keys(s.plugin), s)) if status == "signed_in" else [],
            app=source,  # type: ignore[arg-type]
            app_note=s.default_app_note if source == "add-on" else None,
            can_paste=local and source != "workspace",
            needs_secret=bool(s.client_secret),
            set_aside=(keys(s.plugin) / f"{s.client_id}.set-aside").is_file(),
            default_unusable=bool(s.default_client_id) and not host.default_app_fits(s),
            own_app_steps=[SignInStep(text=text, link=link) for text, link in s.own_app_steps],
        )

    @r.get("/sign-ins")
    def sign_ins() -> list[SignInView]:
        return [view(s) for s in host.sign_ins().values()]

    @r.post("/sign-ins/{name:path}/app")
    def paste_app(name: str, body: SignInApp) -> SignInView:
        """Use the person's own app registration for this sign-in, kept on this computer. Signing in starts over."""
        s = find(name)
        if not local:
            raise HTTPException(
                status_code=400,
                detail="On a hosted app, set the registration in the workspace's settings as env: or file: references.",
            )
        if host.sign_in_app(s, ws.root)[2] == "workspace":
            raise HTTPException(status_code=409, detail="The workspace's settings already set this registration.")
        if s.client_secret and not (body.client_secret or "").strip():
            raise HTTPException(status_code=400, detail="This service also gives a client secret: paste it too.")
        flow.paste_app(keys(s.plugin), s, body.client_id, body.client_secret if s.client_secret else None)
        return view(s)

    @r.post("/sign-ins/{name:path}/app/set-aside")
    def set_aside_app(name: str) -> SignInView:
        """Stop using the pasted registration (the add-on's own is used, if it has one); it can be brought back."""
        s = find(name)
        if not flow.set_aside_app(keys(s.plugin), s):
            raise HTTPException(status_code=404, detail="No registration was pasted for this sign-in.")
        return view(s)

    @r.post("/sign-ins/{name:path}/app/bring-back")
    def bring_back_app(name: str) -> SignInView:
        s = find(name)
        if not flow.bring_back_app(keys(s.plugin), s):
            raise HTTPException(status_code=404, detail="There is no registration to bring back.")
        return view(s)

    @r.post("/sign-ins/{name:path}/start")
    def start(name: str) -> SignInStarted:
        s = find(name)
        try:
            url = flow.start(s, host.sign_in_app(s, ws.root)[0] or "", flow.redirect_uri(cfg.server))
        except flow.SignInError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        return SignInStarted(url=url)

    def back(query: str) -> HTMLResponse:
        """A page that takes the person back into the app. A navigation that starts on this site carries the
        person's cookie, which a redirect from the service's page would not."""
        target = escape(f"{prefix}/?{query}", quote=True)
        page = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={target}"><title>Back to the app</title></head>'
            f'<body><p><a href="{target}">Back to the app</a></p></body></html>'
        )
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    @r.get("/sign-ins/callback", include_in_schema=False)
    def callback(state: str = "", code: str = "", error: str = "", error_description: str = "") -> HTMLResponse:
        """The service sends the person back here; the screen then says how it went, with the service's own code
        and words when it refused (shown as text). Served without the person's cookie (see OPEN_PATHS): only a
        state this app issued, unexpired and unused, does anything."""
        s = flow.pending_sign_in(state)
        if error:
            if s is not None:
                flow.drop_pending(state)
            words = urlencode(
                {"sign_in": "refused", "error": error[:80], "detail": " ".join(error_description.split())[:300]}
            )
            return back(words)
        if s is None or not code:
            return back("sign_in=expired")
        from engine.net import WebClient

        web = WebClient(list(host.manifests[s.plugin].requires.network))
        try:
            client_id, client_secret, _ = host.sign_in_app(s, ws.root)
            done, tokens = flow.finish(state, code, web, client_id or "", client_secret)
            flow.keep(keys(done.plugin), done, tokens)
        except (flow.SignInError, ConnectorError):
            return back(f"sign_in=failed&name={quote(s.name)}")
        finally:
            web.close()
        host.signed_in(done, ws.root)
        from engine.sign_in_sources import start_sources

        try:
            start_sources(ws, cfg, store, done)
        except Exception as err:  # the sign-in stands; the person can still add the sources by hand
            log.warning("Couldn't start the sources for %s: %s", done.name, err)
        return back(f"sign_in=done&name={quote(s.name)}")

    @r.delete("/sign-ins/{name:path}")
    def sign_out(name: str) -> Ok:
        s = find(name)
        if s.revoke_url:
            from engine.net import WebClient

            web = WebClient(list(host.manifests[s.plugin].requires.network))
            try:
                flow.revoke(web, s, flow.kept(keys(s.plugin), s), host.sign_in_app(s, ws.root)[0])
            finally:
                web.close()
        flow.forget(keys(s.plugin), s)
        return Ok(ok="signed_out")

    return r
