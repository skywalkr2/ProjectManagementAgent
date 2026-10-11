"""Signing in to a service a plugin connects to, as the person, through the service's own sign-in page (OAuth 2.0
authorization code with PKCE, the flow for apps on a person's computer).

A plugin declares a sign-in (`registrar.sign_in`): the service's sign-in and token addresses, the scopes it asks for,
and which of its declared secrets hold the app's client id (and secret, for services that issue one). The person
starts it from the screens; the core opens the service's page, receives the answer at its own callback route, and
keeps the tokens on this computer, beside the plugin's other kept secrets, never in the settings files or the export.
A plugin's code asks for a current access token with `context.access_token(name)`; the core renews it when it is
about to run out, and a sign-in that can't be renewed reads as an `auth` failure, so the person is asked to sign in
again.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

#: How long a started sign-in waits for the service's answer.
PENDING_SECONDS = 600
#: An access token this close to running out is renewed first.
RENEW_SECONDS = 120
CALLBACK_PATH = "/api/sign-ins/callback"


class SignInError(Exception):
    """A sign-in can't start, finish or be renewed; the message says why in plain words. `refused`: the service
    refused to renew it just now, so the person has to sign in again."""

    def __init__(self, message: str, refused: bool = False):
        super().__init__(message)
        self.refused = refused


@dataclass(frozen=True)
class SignIn:
    """One sign-in a plugin declares."""

    plugin: str
    name: str  # "<plugin>/<name>"
    label: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    client_id: str  # the declared secret holding the app's client id
    client_secret: str | None = None  # the declared secret holding its client secret, when the service issues one
    params: dict[str, str] = field(default_factory=dict)  # extra parameters for the sign-in page (e.g. offline access)
    allows: tuple[str, ...] = ()  # what the person is asked to allow, in plain words, shown before they leave the app
    account: Any = None  # (context) -> str: the signed-in account's name, read once after signing in
    revoke_url: str | None = None  # where signing out withdraws the access at the service (RFC 7009), if it offers it


@dataclass
class _Pending:
    sign_in: SignIn
    verifier: str
    redirect: str
    started: float


_PENDING: dict[str, _Pending] = {}


def redirect_uri(server: Any) -> str:
    """Where the service sends the person back: the app's public address (its scheme and host) or this computer's
    loopback address, then the base path and the callback route."""
    prefix = "" if server.base_path == "/" else server.base_path
    origin = server.public_url.rstrip("/") if server.public_url else f"http://{server.host}:{server.port}"
    if prefix and origin.endswith(prefix):
        origin = origin[: -len(prefix)]
    return origin + prefix + CALLBACK_PATH


def check_addresses(sign_in: SignIn, network: list[str]) -> None:
    """A sign-in's addresses are HTTPS and on hosts the plugin declares in `requires.network`."""
    from engine.net import host_allowed

    for url in (sign_in.authorize_url, sign_in.token_url, *([sign_in.revoke_url] if sign_in.revoke_url else [])):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or not host_allowed(parts.hostname, network):
            raise ValueError(f"{url} must be an https address on a host listed in requires.network")


def start(sign_in: SignIn, client_id: str, redirect: str, now: float | None = None) -> str:
    """The address of the service's sign-in page for this sign-in; the answer comes back to `redirect`."""
    if not client_id:
        raise SignInError(f"{sign_in.label} needs the app's client id first: set it in the add-on's secrets")
    now = time.time() if now is None else now
    for state in [s for s, p in _PENDING.items() if now - p.started > PENDING_SECONDS]:
        del _PENDING[state]
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _PENDING[state] = _Pending(sign_in, verifier, redirect, now)
    query = {
        **sign_in.params,
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": " ".join(sign_in.scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return sign_in.authorize_url + ("&" if "?" in sign_in.authorize_url else "?") + urlencode(query)


def finish(
    state: str, code: str, web: Any, client_id: str, client_secret: str | None, now: float | None = None
) -> tuple[SignIn, dict[str, Any]]:
    """Exchange the service's answer for tokens. Returns the sign-in and the tokens to keep."""
    now = time.time() if now is None else now
    pending = _PENDING.pop(state, None)
    if pending is None or now - pending.started > PENDING_SECONDS:
        raise SignInError("That sign-in had expired or was already used. Start it again.")
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending.redirect,
        "client_id": client_id,
        "code_verifier": pending.verifier,
    }
    if client_secret:
        form["client_secret"] = client_secret
    return pending.sign_in, _tokens(web.post(pending.sign_in.token_url, data=form), now)


def drop_pending(state: str) -> None:
    """Forget a started sign-in the service refused."""
    _PENDING.pop(state, None)


def pending_sign_in(state: str) -> SignIn | None:
    """The sign-in a callback's `state` belongs to, if one is waiting."""
    pending = _PENDING.get(state)
    return pending.sign_in if pending else None


def _tokens(response: Any, now: float, keep_refresh: str | None = None) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise SignInError("The service's answer couldn't be read.") from None
    token = body.get("access_token") if isinstance(body, dict) else None
    if not token:
        raise SignInError("The service didn't grant access.")
    return {
        "access_token": token,
        "expires_at": now + float(body.get("expires_in") or 3600),
        "refresh_token": body.get("refresh_token") or keep_refresh,
        "scope": body.get("scope"),
        "signed_in_at": now,
    }


# ---- tokens kept on this computer -----------------------------------------------------------------------------------


def _path(keys: Path, sign_in: SignIn) -> Path:
    return keys / ("sign-in-" + sign_in.name.split("/", 1)[1] + ".json")


def keep(keys: Path, sign_in: SignIn, tokens: dict[str, Any]) -> None:
    keys.mkdir(parents=True, exist_ok=True)
    os.chmod(keys, 0o700)
    path = _path(keys, sign_in)
    path.write_text(json.dumps(tokens), encoding="utf-8")
    os.chmod(path, 0o600)


def kept(keys: Path, sign_in: SignIn) -> dict[str, Any] | None:
    try:
        data = json.loads(_path(keys, sign_in).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("access_token") else None


def forget(keys: Path, sign_in: SignIn) -> bool:
    path = _path(keys, sign_in)
    if path.exists():
        path.unlink()
        return True
    return False


def access_token(
    keys: Path, sign_in: SignIn, web: Any, client_id: str | None, client_secret: str | None, now: float | None = None
) -> str:
    """A current access token, renewed first when it is about to run out. Raises SignInError when the person needs to
    sign in (again)."""
    now = time.time() if now is None else now
    tokens = kept(keys, sign_in)
    if tokens is None:
        raise SignInError(f"Sign in to {sign_in.label} first.")
    if tokens.get("refused"):
        raise SignInError(f"The sign-in to {sign_in.label} was withdrawn. Sign in again.")
    if float(tokens.get("expires_at") or 0) - now > RENEW_SECONDS:
        return tokens["access_token"]
    if not tokens.get("refresh_token") or not client_id:
        raise SignInError(f"The sign-in to {sign_in.label} ran out. Sign in again.")
    form = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "scope": " ".join(sign_in.scopes),
    }
    if client_secret:
        form["client_secret"] = client_secret
    from engine.connectors import ConnectorError

    try:
        response = web.post(sign_in.token_url, data=form)
        renewed = _tokens(response, now, keep_refresh=tokens["refresh_token"])
    except (ConnectorError, SignInError) as err:
        if isinstance(err, ConnectorError) and err.kind not in ("auth", "no_access"):
            raise  # the service is failing or out of reach: try again later, the sign-in still stands
        keep(keys, sign_in, {**tokens, "refused": True})
        raise SignInError(f"The sign-in to {sign_in.label} was withdrawn. Sign in again.", refused=True) from None
    renewed["signed_in_at"] = tokens.get("signed_in_at")
    renewed["account"] = tokens.get("account")
    renewed["scope"] = renewed.get("scope") or tokens.get("scope")
    keep(keys, sign_in, renewed)
    return renewed["access_token"]


def status(keys: Path, sign_in: SignIn, now: float | None = None) -> str:
    """ "signed_in", "expired" (and can't be renewed) or "signed_out"."""
    now = time.time() if now is None else now
    tokens = kept(keys, sign_in)
    if tokens is None:
        return "signed_out"
    if tokens.get("refused") or (float(tokens.get("expires_at") or 0) <= now and not tokens.get("refresh_token")):
        return "expired"
    return "signed_in"


def granted(keys: Path, sign_in: SignIn) -> set[str]:
    """The scopes the person allowed: what the service said it granted, or everything asked when it didn't say."""
    tokens = kept(keys, sign_in)
    if tokens is None:
        return set()
    scope = tokens.get("scope")
    return set(str(scope).split()) if scope else set(sign_in.scopes)


def missing(sign_in: SignIn, allowed: set[str]) -> list[str]:
    """Scopes asked for and not granted. A granted scope written with the service's resource in front of it
    (".../Mail.Read") counts for the plain name."""
    return [s for s in sign_in.scopes if not any(g == s or g.endswith("/" + s) for g in allowed)]


def revoke(web: Any, sign_in: SignIn, tokens: dict[str, Any] | None, client_id: str | None) -> bool:
    """Withdraw the access at the service, when it offers it; best effort. True when the service accepted."""
    from engine.connectors import ConnectorError

    token = (tokens or {}).get("refresh_token") or (tokens or {}).get("access_token")
    if not sign_in.revoke_url or not token:
        return False
    form = {"token": token, "token_type_hint": "refresh_token" if tokens.get("refresh_token") else "access_token"}
    if client_id:
        form["client_id"] = client_id
    try:
        return web.post(sign_in.revoke_url, data=form).status < 400
    except ConnectorError:
        return False
