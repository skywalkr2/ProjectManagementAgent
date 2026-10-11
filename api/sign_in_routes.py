"""API routes for signing in to a service an add-on connects to: the sign-ins add-ons declare and whether each is
signed in, starting one (the screen opens the service's page), the address the service sends the person back to, and
signing out."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from api.schemas import Ok, SignInStarted, SignInView
from engine import sign_in as flow
from engine.config import Config
from engine.connectors import ConnectorError
from engine.storage import Store
from engine.workspace import Workspace


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

    @r.get("/sign-ins")
    def sign_ins() -> list[SignInView]:
        return [
            SignInView(
                name=s.name,
                label=s.label,
                status=flow.status(keys(s.plugin), s),
                ready=bool(host.plugin_secret(s.plugin, s.client_id, ws.root)),
                callback=flow.redirect_uri(cfg.server),
                allows=list(s.allows),
                account=(flow.kept(keys(s.plugin), s) or {}).get("account"),
                missing=flow.missing(s, flow.granted(keys(s.plugin), s))
                if flow.status(keys(s.plugin), s) == "signed_in"
                else [],
            )
            for s in host.sign_ins().values()
        ]

    @r.post("/sign-ins/{name:path}/start")
    def start(name: str) -> SignInStarted:
        s = find(name)
        try:
            url = flow.start(s, host.plugin_secret(s.plugin, s.client_id, ws.root) or "", flow.redirect_uri(cfg.server))
        except flow.SignInError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        return SignInStarted(url=url)

    @r.get("/sign-ins/callback", include_in_schema=False)
    def callback(state: str = "", code: str = "", error: str = "", error_description: str = "") -> RedirectResponse:
        """The service sends the person back here; the screen then says how it went, with the service's own code
        and words when it refused (shown as text)."""
        s = flow.pending_sign_in(state)
        if error:
            flow.drop_pending(state)
            words = urlencode(
                {"sign_in": "refused", "error": error[:80], "detail": " ".join(error_description.split())[:300]}
            )
            return RedirectResponse(f"{prefix}/?{words}", status_code=303)
        if s is None or not code:
            return RedirectResponse(f"{prefix}/?sign_in=expired", status_code=303)
        from engine.net import WebClient

        web = WebClient(list(host.manifests[s.plugin].requires.network))
        try:
            client_secret = host.plugin_secret(s.plugin, s.client_secret, ws.root) if s.client_secret else None
            done, tokens = flow.finish(
                state, code, web, host.plugin_secret(s.plugin, s.client_id, ws.root) or "", client_secret
            )
            flow.keep(keys(done.plugin), done, tokens)
        except (flow.SignInError, ConnectorError):
            return RedirectResponse(f"{prefix}/?sign_in=failed&name={quote(s.name)}", status_code=303)
        finally:
            web.close()
        host.signed_in(done, ws.root)
        return RedirectResponse(f"{prefix}/?sign_in=done&name={quote(s.name)}", status_code=303)

    @r.delete("/sign-ins/{name:path}")
    def sign_out(name: str) -> Ok:
        s = find(name)
        if s.revoke_url:
            from engine.net import WebClient

            web = WebClient(list(host.manifests[s.plugin].requires.network))
            try:
                flow.revoke(web, s, flow.kept(keys(s.plugin), s), host.plugin_secret(s.plugin, s.client_id, ws.root))
            finally:
                web.close()
        flow.forget(keys(s.plugin), s)
        return Ok(ok="signed_out")

    return r
