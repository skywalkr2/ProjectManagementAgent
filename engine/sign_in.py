"""Signing in to a service a plugin connects to, as the person, through the service's own sign-in page (OAuth 2.0
authorization code with PKCE, the flow for apps on a person's computer).

A plugin declares a sign-in (`registrar.sign_in`): the service's sign-in and token addresses, the scopes it asks for,
and which of its declared secrets hold the app's client id (and secret, for services that issue one). The person
starts it from the screens; the core opens the service's page, receives the answer at its own callback route, and
keeps the tokens on this computer, beside the plugin's other kept secrets, never in the settings files or the export.
A plugin's code asks for a current access token with `context.access_token(name)`; the core renews it when it is
about to run out, and a sign-in that can't be renewed reads as an `auth` failure, so the person is asked to sign in
again. A sign-in may hold several accounts of the service at once, each with its own tokens, known by its address; a
source reads with the account it names.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from engine.state_file import write_whole

#: How long a started sign-in waits for the service's answer.
PENDING_SECONDS = 600
#: An access token this close to running out is renewed first.
RENEW_SECONDS = 120
CALLBACK_PATH = "/api/sign-ins/callback"


class SignInError(Exception):
    """A sign-in can't start, finish or be renewed; the message says why in plain words. `refused`: the service
    refused to renew it just now, so the person has to sign in again. `ambiguous`: several accounts are signed in and
    none was chosen. `account`: the address of the account it is about, when it is about one."""

    def __init__(self, message: str, refused: bool = False, ambiguous: bool = False, account: str | None = None):
        super().__init__(message)
        self.refused = refused
        self.ambiguous = ambiguous
        self.account = account


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
    default_client_id: str | None = None  # the add-on's own app registration, used when the person sets none
    default_client_secret: str | None = None
    default_app_note: str | None = None  # what using the add-on's own registration means for the person
    own_app_steps: tuple[tuple[str, str | None], ...] = ()  # how to make one's own registration: (step, link)
    default_redirects: tuple[str, ...] = ()  # the callback addresses the add-on's own registration allows
    sources: tuple[dict[str, Any], ...] = ()  # sources started when the person signs in: connector, label, settings
    acting_scopes: tuple[str, ...] = ()  # the extra scopes acting needs, asked only when the person turns acting on


def address_allowed(redirect: str, allowed: tuple[str, ...]) -> bool:
    """Whether the app's callback address is one a registration allows: the same address, where a loopback host
    (localhost, 127.0.0.1, [::1]) matches on any port, as services accept for apps on a person's computer. No list
    means any address."""
    if not allowed:
        return True
    loopback = {"localhost", "127.0.0.1", "::1"}

    def key(address: str) -> tuple[str, str | None, int | None, str]:
        parts = urlsplit(address)
        host = (parts.hostname or "").lower()
        return parts.scheme, host, None if host in loopback else parts.port, parts.path.rstrip("/") or "/"

    return key(redirect) in {key(a) for a in allowed}


#: Where the app registration a sign-in uses comes from: the workspace's references, values pasted on this computer,
#: the add-on's own, or nowhere yet.
APP_SOURCES = ("workspace", "pasted", "add-on", "none")


def pasted_path(keys: Path, secret: str) -> Path:
    """Where a value the person pasted for a sign-in's app registration is kept, beside the plugin's kept secrets."""
    return keys / secret


def paste_app(keys: Path, sign_in: SignIn, client_id: str, client_secret: str | None) -> None:
    """Keep the person's own app registration for a sign-in on this computer (readable by its owner only), and
    forget the tokens of the registration it replaces, which the service ties to that registration."""
    keys.mkdir(parents=True, exist_ok=True)
    os.chmod(keys, 0o700)
    _write_private(pasted_path(keys, sign_in.client_id), client_id.strip())
    if sign_in.client_secret:
        if client_secret and client_secret.strip():
            _write_private(pasted_path(keys, sign_in.client_secret), client_secret.strip())
        else:
            pasted_path(keys, sign_in.client_secret).unlink(missing_ok=True)
    forget(keys, sign_in)


def set_aside_app(keys: Path, sign_in: SignIn) -> bool:
    """Stop using the pasted registration, keeping it aside so it can be brought back; the sign-in made with it is
    forgotten. False when nothing was pasted."""
    moved = False
    for secret in (sign_in.client_id, sign_in.client_secret):
        if secret and pasted_path(keys, secret).is_file():
            pasted_path(keys, secret).replace(keys / f"{secret}.set-aside")
            moved = True
    if moved:
        forget(keys, sign_in)
    return moved


def bring_back_app(keys: Path, sign_in: SignIn) -> bool:
    """Use the registration set aside last again. False when there is none."""
    moved = False
    for secret in (sign_in.client_id, sign_in.client_secret):
        aside = keys / f"{secret}.set-aside" if secret else None
        if aside is not None and aside.is_file():
            aside.replace(pasted_path(keys, secret))
            moved = True
    if moved:
        forget(keys, sign_in)
    return moved


def _write_private(path: Path, value: str) -> None:
    write_whole(path, value + "\n", mode=0o600)


@dataclass
class _Pending:
    sign_in: SignIn
    verifier: str
    redirect: str
    started: float
    acting: bool = False


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
            raise ValueError(f"{url} must be an https address on a host the add-on says it reaches")


def start(sign_in: SignIn, client_id: str, redirect: str, now: float | None = None, acting: bool = False) -> str:
    """The address of the service's sign-in page for this sign-in; the answer comes back to `redirect`. With `acting`
    it asks for the sign-in's acting scopes as well as its reading ones (the person turned acting on); never
    otherwise."""
    if not client_id:
        raise SignInError(f"{sign_in.label} needs an app registration first: paste one on its Sign-ins row")
    now = time.time() if now is None else now
    for state in [s for s, p in _PENDING.items() if now - p.started > PENDING_SECONDS]:
        del _PENDING[state]
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    asked = (*sign_in.scopes, *(sign_in.acting_scopes if acting else ()))
    _PENDING[state] = _Pending(sign_in, verifier, redirect, now, bool(acting and sign_in.acting_scopes))
    query = {
        **sign_in.params,
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": " ".join(asked),
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
    tokens = _tokens(web.post(pending.sign_in.token_url, data=form), now)
    return pending.sign_in, {**tokens, "acting": True} if pending.acting else tokens


def drop_pending(state: str) -> None:
    """Forget a started sign-in the service refused."""
    _PENDING.pop(state, None)


def pending_sign_in(state: str) -> SignIn | None:
    """The sign-in a callback's `state` belongs to, if one is waiting."""
    pending = _PENDING.get(state)
    return pending.sign_in if pending else None


def _tokens(
    response: Any, now: float, keep_refresh: str | None = None, keep_expires: float | None = None
) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise SignInError("The service's answer couldn't be read.") from None
    token = body.get("access_token") if isinstance(body, dict) else None
    if not token:
        raise SignInError("The service didn't grant access.")
    # When the service says how long the renewal credential lasts, the day it ends is kept so Today can say so ahead
    # of it; a renewal that gives no new credential keeps the end of the one it renews.
    lasts = body.get("refresh_token_expires_in")
    ends = (
        now + float(lasts)
        if isinstance(lasts, (int, float)) and lasts > 0
        else (None if body.get("refresh_token") else keep_expires)
    )
    return {
        "access_token": token,
        "expires_at": now + float(body.get("expires_in") or 3600),
        "refresh_token": body.get("refresh_token") or keep_refresh,
        "refresh_expires_at": ends,
        "scope": body.get("scope"),
        "signed_in_at": now,
    }


# ---- tokens kept on this computer -----------------------------------------------------------------------------------
#
# One file of tokens per account of a sign-in: `sign-in-<name>--<key>.json`, the key a short hash of the account's
# address (a file name that is safe on every system, and the same address is always the same account). A sign-in made
# before accounts existed is one file with no key: when the tokens say whose they are it is moved to its account's file
# on first read; when they don't, it stays as the one account that has no address.

UNNAMED = "unnamed"  # the key of an account whose address isn't known: the file with no key in its name
_KEYED = re.compile(r"--([0-9a-f]{16})\.json$")


@dataclass(frozen=True)
class Account:
    """One account signed in to a sign-in: its key (see `account_key`), its address (None when it was never read) and
    its tokens."""

    key: str
    address: str | None
    tokens: dict[str, Any]


def account_key(address: str) -> str:
    """The short, file-safe key of an account: a hash of its address, in any case (one address is one account)."""
    return hashlib.sha256(" ".join(address.split()).lower().encode()).hexdigest()[:16]


def _base(sign_in: SignIn) -> str:
    return "sign-in-" + sign_in.name.split("/", 1)[1]


def _path(keys: Path, sign_in: SignIn, key: str = UNNAMED) -> Path:
    return keys / (_base(sign_in) + ".json" if key == UNNAMED else f"{_base(sign_in)}--{key}.json")


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("access_token") else None


def _migrate(keys: Path, sign_in: SignIn) -> None:
    """Move a sign-in made before accounts existed to its account's file, when its tokens name the account. An account
    already kept under its own file wins over the old copy."""
    old = _path(keys, sign_in)
    tokens = _read(old)
    address = tokens.get("account") if tokens else None
    if not isinstance(address, str) or not address.strip():
        return
    target = _path(keys, sign_in, account_key(address))
    if not target.exists():
        write_whole(target, json.dumps(tokens), mode=0o600)
    old.unlink(missing_ok=True)


def list_accounts(keys: Path, sign_in: SignIn) -> list[Account]:
    """The accounts signed in (or that need signing in again), the one signed in first first."""
    _migrate(keys, sign_in)
    found = []
    candidates = [(UNNAMED, _path(keys, sign_in))] + sorted(
        (m.group(1), p) for p in keys.glob(_base(sign_in) + "--*.json") if (m := _KEYED.search(p.name))
    )
    for key, path in candidates:
        tokens = _read(path)
        if tokens is not None:
            address = tokens.get("account")
            found.append(Account(key, address if isinstance(address, str) and address else None, tokens))
    return sorted(found, key=lambda a: (float(a.tokens.get("signed_in_at") or 0), a.key))


def _find(keys: Path, sign_in: SignIn, account: str | None) -> Account | None:
    """The account with this address, or (no address given) the first one."""
    accounts = list_accounts(keys, sign_in)
    if account is None:
        return accounts[0] if accounts else None
    wanted = account_key(account)
    return next((a for a in accounts if a.address and account_key(a.address) == wanted), None)


def keep(keys: Path, sign_in: SignIn, tokens: dict[str, Any], account: str | None = None) -> None:
    """Keep the tokens of one account: the address in `account` or in the tokens' own `account`; with neither, the
    account that has no address. Keeping an address again replaces its tokens (one address is one account)."""
    keys.mkdir(parents=True, exist_ok=True)
    os.chmod(keys, 0o700)
    address = account or tokens.get("account")
    if isinstance(address, str) and address.strip():
        tokens = {**tokens, "account": address}
        path = _path(keys, sign_in, account_key(address))
        # An account kept before its address could be read is this sign-in's earlier account, not a second one.
        _path(keys, sign_in).unlink(missing_ok=True)
    else:
        path = _path(keys, sign_in)
    write_whole(path, json.dumps(tokens), mode=0o600)


def kept(keys: Path, sign_in: SignIn, account: str | None = None) -> dict[str, Any] | None:
    """The tokens of the account with this address, or of the first account when none is named."""
    found = _find(keys, sign_in, account)
    return found.tokens if found else None


def forget(keys: Path, sign_in: SignIn, key: str | None = None) -> bool:
    """Forget one account's tokens by its key, or all of the sign-in's when no key is given. True when any was kept."""
    _migrate(keys, sign_in)
    gone = False
    for found in list_accounts(keys, sign_in):
        if key is None or found.key == key:
            _path(keys, sign_in, found.key).unlink(missing_ok=True)
            gone = True
    return gone


def _named(sign_in: SignIn, address: str | None) -> str:
    return f"{sign_in.label} ({address})" if address else sign_in.label


def choose(keys: Path, sign_in: SignIn, account: str | None) -> Account:
    """The account a read uses: the one with this address, or, when none is named, the only one signed in. Raises
    SignInError when the person needs to sign in (that account, or at all) or must choose between several."""
    if account is not None:
        found = _find(keys, sign_in, account)
        if found is None:
            raise SignInError(f"{account} isn't signed in to {sign_in.label}. Sign in again.", account=account)
        return found
    accounts = list_accounts(keys, sign_in)
    if not accounts:
        raise SignInError(f"Sign in to {sign_in.label} first.")
    if len(accounts) > 1:
        raise SignInError(
            f"More than one account is signed in to {sign_in.label}: choose which one this reads.", ambiguous=True
        )
    return accounts[0]


def access_token(
    keys: Path,
    sign_in: SignIn,
    web: Any,
    client_id: str | None,
    client_secret: str | None,
    now: float | None = None,
    account: str | None = None,
) -> str:
    """A current access token for one account (the only one signed in, when none is named), renewed first when it is
    about to run out. Raises SignInError when the person needs to sign in (again)."""
    now = time.time() if now is None else now
    chosen = choose(keys, sign_in, account)
    tokens, address = chosen.tokens, chosen.address
    if tokens.get("refused"):
        raise SignInError(f"The sign-in to {_named(sign_in, address)} was withdrawn. Sign in again.", account=address)
    if float(tokens.get("expires_at") or 0) - now > RENEW_SECONDS:
        return tokens["access_token"]
    if not tokens.get("refresh_token") or not client_id:
        raise SignInError(f"The sign-in to {_named(sign_in, address)} ran out. Sign in again.", account=address)
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
        renewed = _tokens(
            response, now, keep_refresh=tokens["refresh_token"], keep_expires=tokens.get("refresh_expires_at")
        )
    except (ConnectorError, SignInError) as err:
        if isinstance(err, ConnectorError) and err.kind not in ("auth", "no_access"):
            raise  # the service is failing or out of reach: try again later, the sign-in still stands
        keep(keys, sign_in, {**tokens, "refused": True}, address)
        raise SignInError(
            f"The sign-in to {_named(sign_in, address)} was withdrawn. Sign in again.", refused=True, account=address
        ) from None
    renewed["signed_in_at"] = tokens.get("signed_in_at")
    renewed["account"] = tokens.get("account")
    if tokens.get("acting"):
        renewed["acting"] = True
    renewed["scope"] = renewed.get("scope") or tokens.get("scope")
    keep(keys, sign_in, renewed, address)
    return renewed["access_token"]


def account_status(account: Account, now: float | None = None) -> str:
    """ "signed_in", or "expired" when the account can't be renewed and the person has to sign in again."""
    now = time.time() if now is None else now
    tokens = account.tokens
    if tokens.get("refused") or (float(tokens.get("expires_at") or 0) <= now and not tokens.get("refresh_token")):
        return "expired"
    return "signed_in"


def status(keys: Path, sign_in: SignIn, now: float | None = None, account: str | None = None) -> str:
    """ "signed_in", "expired" (and can't be renewed) or "signed_out". For one account (by address); with none named,
    for the sign-in: signed in when any account is, else expired when any account needs signing in again."""
    now = time.time() if now is None else now
    if account is not None:
        found = _find(keys, sign_in, account)
        return "signed_out" if found is None else account_status(found, now)
    states = {account_status(a, now) for a in list_accounts(keys, sign_in)}
    return "signed_in" if "signed_in" in states else ("expired" if states else "signed_out")


def granted(keys: Path, sign_in: SignIn, account: str | None = None) -> set[str]:
    """The scopes the person allowed: what the service said it granted, or everything asked when it didn't say. For
    one account; with none named, the first."""
    tokens = kept(keys, sign_in, account)
    return set() if tokens is None else allowed_scopes(sign_in, tokens)


def allowed_scopes(sign_in: SignIn, tokens: dict[str, Any]) -> set[str]:
    """The scopes one account's tokens carry: what the service said, or everything asked when it didn't say."""
    scope = tokens.get("scope")
    if scope:
        return set(str(scope).split())
    return {*sign_in.scopes, *(sign_in.acting_scopes if tokens.get("acting") else ())}


def missing(sign_in: SignIn, allowed: set[str]) -> list[str]:
    """Scopes asked for and not granted. A granted scope written with the service's resource in front of it
    (".../Mail.Read") counts for the plain name."""
    return [s for s in sign_in.scopes if not any(g == s or g.endswith("/" + s) for g in allowed)]


def missing_acting(sign_in: SignIn, allowed: set[str]) -> list[str]:
    """Acting scopes asked for and not granted, by the same reading as `missing`."""
    return [s for s in sign_in.acting_scopes if not any(g == s or g.endswith("/" + s) for g in allowed)]


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
