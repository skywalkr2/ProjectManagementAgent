"""Fake outside services for the journey tests: one small process on 127.0.0.1 that plays every service the app talks
to, so a browser can walk a person's whole path with nothing real on the other end.

    uv run python -m tests.fake_services --port 8790 --https-port 8791 --state /path/to/state

Each service is a list of routes under its own prefix, added to `SERVICES` (plain HTTP) or `SECURE_SERVICES` (HTTPS).

- `/ai/v1/...` speaks the common chat format: a model list with prices, and chat completions whose answer is the
  stand-in's answer to the packet it was sent (`engine.ai.adapters.stand_in`), so the journey checks the app, not a
  model. Every chat request is recorded.
- `/__e2e/...` are the helpers the browser tests read: what the AI service was asked, the people in the fictional
  workspace to write notes about, a folder the app may read as a source (and a route that puts a file in it), what the
  sign-in service was asked, and the token the app was started with. A test may also script one answer: the next
  request that holds the given words gets that answer instead of the stand-in's (for what no stand-in rule produces).

With `--https-port` the process also answers over HTTPS, with a certificate from a throwaway authority made at start
(`tests.fake_tls`; the app is told to trust it with `SSL_CERT_FILE`). `SECURE_SERVICES` are those:

- `/account/...` is a sign-in page that sends the person straight back with a code, a token address that checks the
  code and the PKCE verifier, a revoke address and a "who am I" answer;
- `/mail/v1/...` and `/calendar/v1/...` are a small mail and calendar API that answers only to a token it issued, with
  fictional messages from example.com addresses and meetings today;
- `/catalog/...` is an add-on catalog feed listing the add-ons named by `--catalog` (fixture folders; the example panel
  by default), and the wheels it points to, built from their fixture folders at start.

The folder the app's own process works in is passed as `--state`; `tests.e2e_fresh_server` writes `info.json` there.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import secrets
import threading
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import uvicorn
import yaml
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from engine.ai import learning_check
from engine.ai.adapters import stand_in
from tests import fake_tls
from tests.conftest import DEMO_B, fixture_records

HOST = "127.0.0.1"
PLUGINS = Path(__file__).parent / "fixtures" / "plugins"

#: Fictional model names with a price per token, as a service's own model list gives them.
MODELS = {
    "fake-small": {"prompt": "0.0000005", "completion": "0.0000015", "context_length": 128000},
    "fake-large": {"prompt": "0.000003", "completion": "0.000015", "context_length": 200000},
}

#: The app registration the sign-in service knows (the mail add-on ships it; a test compares the two).
CLIENT_ID = "journey-mail-app"
SCOPES = "mail.read calendar.read offline"
TOKEN_SECONDS = 3600


class State:
    """What the fake services remember: the chat requests received, what the sign-in service has given out and been
    asked, and where the app's own folders are."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.chats: list[dict] = []
        self.scripted: list[dict] = []  # answers waiting for a request that holds their words: {"when", "answer"}
        self.https_base = ""
        self.assets = folder / "services"
        self.catalog_text = ""
        self.wheels: dict[str, Path] = {}  # the wheels the catalog lists, by file name
        self.codes: dict[str, dict] = {}  # given and not yet used: the challenge and address each was asked with
        self.access: set[str] = set()  # access tokens the service issued and has not withdrawn
        self.refresh: set[str] = set()
        #: The moment the made-up mailbox and calendar are dated from, so reading them again gives the same text.
        self.moment = datetime.now(UTC)
        self.later_mail: list[dict] = []  # messages that arrive after the first read (added by a helper route)
        self.seen = {
            "authorizations": 0,
            "exchanges": 0,
            "renewals": 0,
            "refused": 0,
            "revoked": 0,
            "mail_reads": 0,
            "calendar_reads": 0,
            "unauthorized": 0,
        }

    def info(self) -> dict:
        """What the app's start-up script wrote: the token, the source folder and the backup folder."""
        try:
            return json.loads((self.folder / "info.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


# ---- the AI service --------------------------------------------------------------------------------------------------


#: How a sorting run's request opens: a batch of message headers, marked as outside content.
SORTING_MARK = '<untrusted source="mail headers">'


def is_sorting(user: str) -> bool:
    """Whether this packet asks to sort mail headers (the assistant's sorting of mail the rules can't place)."""
    return SORTING_MARK in user


def is_check(user: str) -> bool:
    """Whether this packet is part of an account's connection check: the fixed reply, or the learning round-trip."""
    return "Reply with exactly" in user or learning_check.CHECK_REQUEST in user


def scripted_answer(state: State, user: str) -> str | None:
    """The answer a test scripted for a request holding its words, used once; None when none applies."""
    for entry in state.scripted:
        if entry["when"] in user:
            state.scripted.remove(entry)
            return json.dumps(entry["answer"])
    return None


def answer_to(system: str, user: str) -> str:
    """The text a model would send back for this packet, from the stand-in's rules."""
    if "Reply with exactly this JSON" in user:
        return json.dumps({"ok": True})
    if is_check(user):
        return json.dumps(stand_in.learn(user))
    if is_sorting(user):
        return json.dumps(stand_in.sort_mail(user))
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
        first = " / ".join(stand_in.input_lines(user))
        state.chats.append(
            {
                "model": body.get("model"),
                "at": time.time(),
                "smoke": is_check(user),
                "sorting": is_sorting(user),
                "input": first[:200],
            }
        )
        text = (None if is_check(user) else scripted_answer(state, user)) or answer_to(system, user)
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


# ---- the sign-in service ---------------------------------------------------------------------------------------------


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _loopback(address: str) -> bool:
    parts = urlsplit(address)
    return parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"} and parts.path.endswith("/callback")


def account_routes(state: State) -> list[Route]:
    """The made-up service's sign-in: the page sends the person straight back, as a person already signed in to it
    would be; the token address is where the app proves it started the sign-in (PKCE)."""

    def issue(with_refresh: bool) -> dict:
        access = "access-" + secrets.token_urlsafe(12)
        state.access.add(access)
        body = {"access_token": access, "token_type": "Bearer", "expires_in": TOKEN_SECONDS, "scope": SCOPES}
        if with_refresh:
            refresh = "refresh-" + secrets.token_urlsafe(12)
            state.refresh.add(refresh)
            body["refresh_token"] = refresh
        return body

    def refused(error: str, status: int = 400) -> JSONResponse:
        state.seen["refused"] += 1
        return JSONResponse({"error": error}, status_code=status)

    async def authorize(request: Request) -> Response:
        q = request.query_params
        redirect = q.get("redirect_uri", "")
        if (
            q.get("response_type") != "code"
            or q.get("client_id") != CLIENT_ID
            or q.get("code_challenge_method") != "S256"
            or not q.get("code_challenge")
            or not q.get("state")
            or not _loopback(redirect)
        ):
            return refused("invalid_request")
        code = "code-" + secrets.token_urlsafe(12)
        state.codes[code] = {"challenge": q["code_challenge"], "redirect": redirect}
        state.seen["authorizations"] += 1
        return RedirectResponse(f"{redirect}?{urlencode({'code': code, 'state': q['state']})}", status_code=302)

    async def token(request: Request) -> JSONResponse:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        if form.get("client_id") != CLIENT_ID:
            return refused("invalid_client", 401)
        if form.get("grant_type") == "authorization_code":
            grant = state.codes.pop(form.get("code", ""), None)
            if (
                grant is None
                or form.get("redirect_uri") != grant["redirect"]
                or _challenge(form.get("code_verifier", "")) != grant["challenge"]
            ):
                return refused("invalid_grant")
            state.seen["exchanges"] += 1
            return JSONResponse(issue(with_refresh=True))
        if form.get("grant_type") == "refresh_token" and form.get("refresh_token") in state.refresh:
            state.seen["renewals"] += 1
            return JSONResponse(issue(with_refresh=False))
        return refused("invalid_grant")

    async def revoke(request: Request) -> Response:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        state.refresh.discard(form.get("token", ""))
        state.access.discard(form.get("token", ""))
        state.seen["revoked"] += 1
        return Response(status_code=200)

    async def me(request: Request) -> JSONResponse:
        if not signed_in(state, request):
            return unauthorized()
        return JSONResponse({"email": address_of(people()[0])})

    return [
        Route("/authorize", authorize),
        Route("/token", token, methods=["POST"]),
        Route("/revoke", revoke, methods=["POST"]),
        Route("/v1/me", me),
    ]


def signed_in(state: State, request: Request) -> bool:
    header = request.headers.get("authorization", "")
    return header.startswith("Bearer ") and header[7:] in state.access


def unauthorized() -> JSONResponse:
    return JSONResponse({"error": {"code": "InvalidAuthenticationToken"}}, status_code=401)


# ---- the mail and calendar service -----------------------------------------------------------------------------------


def people() -> list[str]:
    """The names in the fictional workspace the journeys use: the first is the person at the keyboard."""
    return [p["full_name"] for p in fixture_records(DEMO_B, "person")]


def projects() -> list[str]:
    """The project names in the fictional workspace, for a test that needs a name no fresh workspace holds."""
    return [p["name"] for p in fixture_records(DEMO_B, "project")]


def address_of(name: str) -> str:
    return ".".join(re.sub(r"[^a-z0-9]", "", part.lower()) for part in name.split()) + "@example.com"


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


#: The sender of the social update and of the mail that comes later: a made-up network, not a person in the workspace.
NETWORK = ("Neighborhood Network", "updates@network.example.com")
SHOP = ("Spring Shop", "deals@shop.example.com")


def message(
    key: str,
    sender: tuple[str, str],
    subject: str,
    age: timedelta,
    unread: bool,
    *lines: str,
    now: datetime,
    bulk: bool = False,
    categories: tuple[str, ...] = (),
) -> dict:
    """One message as the made-up mail service gives it: who from, when, and what the service says about it."""
    return {
        "id": key,
        "from": {"name": sender[0], "address": sender[1]},
        "subject": subject,
        "received": stamp(now - age),
        "unread": unread,
        "body": "\n".join(lines),
        "bulk": bulk,
        "categories": list(categories),
    }


def messages(now: datetime, later: list[dict] | None = None) -> list[dict]:
    """Six messages: three work messages from the last day, with the shapes the stand-in reads, a social update with
    the service's category and a sales mail with a bulk flag, both from the last day too, and one from last week.
    `later` are messages that arrived after the first read."""
    me, first, second = people()[:3]

    def work(key: str, sender: str, subject: str, age: timedelta, unread: bool, *lines: str) -> dict:
        return message(key, (sender, address_of(sender)), subject, age, unread, *lines, now=now)

    return [
        work(
            "m-1",
            first,
            "Venue list",
            timedelta(hours=2),
            True,
            f"{me} will send the venue list by 2026-11-02.",
            "Decided: the offsite is on a Friday.",
        ),  # fmt: skip
        work(
            "m-2",
            second,
            "Catering quote",
            timedelta(hours=5),
            True,
            "We need a catering quote.",
            "To do: send the headcount by 2026-11-04.",
        ),  # fmt: skip
        work("m-3", first, "Thanks", timedelta(hours=1), False, "Thanks for the update. See you there."),
        work("m-4", second, "Last week's agenda", timedelta(days=6), False, "We need a printed agenda."),
        message(
            "m-5",
            NETWORK,
            "Three neighbors posted today",
            timedelta(hours=3),
            True,
            "See what your neighbors are up to.",
            now=now,
            categories=("social",),
        ),
        message(
            "m-6",
            SHOP,
            "Spring sale: everything half price",
            timedelta(hours=4),
            True,
            "Half price on everything this week only.",
            now=now,
            bulk=True,
        ),
        *(later or []),
    ]


def events(now: datetime) -> list[dict]:
    """Three events: two within the hour, and one next week."""
    first, second = people()[1:3]

    def event(key: str, title: str, start: datetime, where: str, organizer: str, notes: str) -> dict:
        return {
            "id": key,
            "title": title,
            "start": stamp(start),
            "end": stamp(start + timedelta(minutes=30)),
            "where": where,
            "organizer": organizer,
            "cancelled": False,
            "notes": notes,
        }

    return [
        event(
            "e-1", "Venue walk-through", now + timedelta(minutes=15), "Room 4", first, "To do: bring the floor plan."
        ),
        event(
            "e-2",
            "Budget check-in",
            now + timedelta(minutes=45),
            "Room 2",
            second,
            "Agreed: the budget stays as planned.",
        ),  # fmt: skip
        event("e-3", "Offsite day", now + timedelta(days=9), "The lodge", first, "Everyone arrives by nine."),
    ]


def recent_items(now: datetime, hours: int = 24) -> dict[str, list[str]]:
    """The titles of the work messages that came in and the events that fall within `hours` of now, which a first read
    hands the assistant; of the mail the app sets aside by what the service says about it (bulk, or a category); and
    of those further away, which it only notes."""

    def near(stamped: str) -> bool:
        return abs(datetime.fromisoformat(stamped) - now) <= timedelta(hours=hours)

    mail, events_ = messages(now), events(now)
    aside = [m for m in mail if m["bulk"] or {"promotions", "social", "forums"} & set(m["categories"])]
    return {
        "mail": [m["subject"] for m in mail if near(m["received"]) and m not in aside],
        "set_aside": [m["subject"] for m in aside if near(m["received"])],
        "events": [e["title"] for e in events_ if near(e["start"])],
        "noted": [m["subject"] for m in mail if not near(m["received"])]
        + [e["title"] for e in events_ if not near(e["start"])],
    }


def intake_items(now: datetime, days: int = 14) -> dict[str, list[str]]:
    """What a quiet first read takes in (a sign-in's sources): the work messages of the last `days` and every event,
    whatever its day; the mail the app sets aside by what the service says about it within those days; and the mail
    older than that, which it only notes."""
    mail = messages(now)
    aside = [m for m in mail if m["bulk"] or {"promotions", "social", "forums"} & set(m["categories"])]

    def within(stamped: str) -> bool:
        return datetime.fromisoformat(stamped) >= now - timedelta(days=days)

    return {
        "mail": [m["subject"] for m in mail if within(m["received"]) and m not in aside],
        "set_aside": [m["subject"] for m in aside if within(m["received"])],
        "events": [e["title"] for e in events(now)],
        "noted": [m["subject"] for m in mail if not within(m["received"])],
    }


def mail_routes(state: State) -> list[Route]:
    async def listed(request: Request) -> JSONResponse:
        if not signed_in(state, request):
            state.seen["unauthorized"] += 1
            return unauthorized()
        state.seen["mail_reads"] += 1
        return JSONResponse({"messages": messages(state.moment, state.later_mail)})

    return [Route("/messages", listed)]


def calendar_routes(state: State) -> list[Route]:
    async def listed(request: Request) -> JSONResponse:
        if not signed_in(state, request):
            state.seen["unauthorized"] += 1
            return unauthorized()
        state.seen["calendar_reads"] += 1
        return JSONResponse({"events": events(state.moment)})

    return [Route("/events", listed)]


# ---- the add-on catalog ----------------------------------------------------------------------------------------------


def build_wheel(source: Path, out: Path) -> Path:
    """A wheel of pure Python from a plugin folder (the package is the folder, its `plugin.yaml` inside it), with the
    metadata an install needs: the entry point the app finds plugins by, and a record of the files."""
    manifest = yaml.safe_load((source / "plugin.yaml").read_text(encoding="utf-8"))
    name, version, package = manifest["name"], manifest["version"], source.name
    info = f"{package}-{version}.dist-info"
    files = {
        f"{package}/{path.relative_to(source).as_posix()}": path.read_bytes()
        for path in sorted(source.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    files[f"{info}/METADATA"] = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
    files[f"{info}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: journey-tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files[f"{info}/entry_points.txt"] = f"[pm_cockpit.plugins]\n{name} = {manifest['entry']}\n".encode()
    record = [f"{n},sha256={hashlib.sha256(d).hexdigest()},{len(d)}" for n, d in files.items()]
    files[f"{info}/RECORD"] = ("\n".join([*record, f"{info}/RECORD,,"]) + "\n").encode()
    out.mkdir(parents=True, exist_ok=True)
    wheel = out / f"{package}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, data in files.items():
            archive.writestr(zipfile.ZipInfo(member, (2026, 1, 1, 0, 0, 0)), data)
    return wheel


#: The add-ons a catalog can list: the fixture folder, and the name and summary the catalog gives each.
ADD_ONS: dict[str, tuple[str, str]] = {
    "journey_panel": ("Example panel", "One screen with a short page, to see an add-on installed from the list."),
    "journey_mail": (
        "Example mail",
        "Reads a made-up mailbox and calendar, signing in through the service's own page.",
    ),
}


def catalog_feed(wheels: Path | list[Path], base: str) -> str:
    """A catalog feed in the app's format listing the add-ons the wheels hold, each with its release address and
    checksum. What an entry says it provides and needs is copied from its fixture's manifest, as a catalog entry is."""
    entries = []
    for wheel in [wheels] if isinstance(wheels, Path) else wheels:
        folder = wheel.name.split("-")[0]
        manifest = yaml.safe_load((PLUGINS / folder / "plugin.yaml").read_text(encoding="utf-8"))
        name, summary = ADD_ONS[folder]
        entries.append(
            {
                "id": manifest["name"],
                "name": name,
                "summary": summary,
                "publisher": "Example publisher",
                "maintainers": False,
                "updated": "2026-10-12",
                "version": manifest["version"],
                "plugin_api": manifest["plugin_api"],
                "price": {"model": "free"},
                "provides": manifest["provides"],
                "requires": manifest["requires"],
                "release": {
                    "url": f"{base}/catalog/{wheel.name}",
                    "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                },
            }
        )
    return yaml.safe_dump({"version": 1, "packs": entries}, sort_keys=False)


def catalog_routes(state: State) -> list[Route]:
    async def feed(_request: Request) -> Response:
        return Response(state.catalog_text, media_type="application/yaml")

    async def release(request: Request) -> Response:
        wheel = state.wheels.get(request.path_params["name"])
        if wheel is None:
            return Response(status_code=404)
        return Response(wheel.read_bytes(), media_type="application/octet-stream")

    return [Route("/packs.yaml", feed), Route("/{name}", release)]


# ---- the helpers the browser tests read ------------------------------------------------------------------------------

#: A fictional file the source folder is given: a meeting note in the stand-in's own sentence shapes.
SOURCE_FILE = "folder-note.txt"


def helper_routes(state: State, base: str) -> list[Route]:
    async def info(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                **state.info(),
                "ai_base_url": f"{base}/ai/v1",
                "people": people(),
                "projects": projects(),
                "https_base": state.https_base,
            }
        )

    async def requests(_request: Request) -> JSONResponse:
        asked = [c for c in state.chats if not c["smoke"]]
        work = [c for c in asked if not c["sorting"]]
        inputs = [c["input"] for c in work]
        return JSONResponse(
            {
                "total": len(state.chats),
                "smoke": len(state.chats) - len(asked),
                "sorting": len(asked) - len(work),
                "work": len(work),
                "inputs": inputs,
                "models": [c["model"] for c in work],
            }
        )

    async def sign_in(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                **state.seen,
                "tokens": len(state.access),
                "recent_items": recent_items(datetime.now(UTC)),
                "intake_items": intake_items(datetime.now(UTC)),
            }
        )

    async def mail_later(_request: Request) -> JSONResponse:
        """A new message from the social network's sender arrives, saying nothing about itself."""
        now = datetime.now(UTC)
        subject = f"Another update from the network ({len(state.later_mail) + 1})"
        state.later_mail.append(
            message(
                f"m-later-{len(state.later_mail) + 1}",
                NETWORK,
                subject,
                timedelta(minutes=10),
                True,
                "More news.",
                now=now,
            )
        )
        return JSONResponse({"subject": subject, "sender": NETWORK[1]})

    async def put_source_file(request: Request) -> JSONResponse:
        body = await request.json()
        folder = Path(state.info()["source_folder"])
        (folder / SOURCE_FILE).write_text(str(body["text"]), encoding="utf-8")
        return JSONResponse({"file": SOURCE_FILE})

    async def script(request: Request) -> JSONResponse:
        """The next request holding `when` is answered with `answer`, once."""
        body = await request.json()
        state.scripted.append({"when": str(body["when"]), "answer": body["answer"]})
        return JSONResponse({"waiting": len(state.scripted)})

    return [
        Route("/__e2e/info", info),
        Route("/__e2e/script", script, methods=["POST"]),
        Route("/__e2e/ai-requests", requests),
        Route("/__e2e/sign-in", sign_in),
        Route("/__e2e/source-file", put_source_file, methods=["POST"]),
        Route("/__e2e/mail-later", mail_later, methods=["POST"]),
    ]


# ---- assembling ------------------------------------------------------------------------------------------------------

Services = dict[str, Callable[[State], list[Route]]]

#: Every fake service over plain HTTP: its prefix and the function that makes its routes. A new service is one entry.
SERVICES: Services = {"/ai/v1": ai_routes}

#: Every fake service over HTTPS, the same way.
SECURE_SERVICES: Services = {
    "/account": account_routes,
    "/mail/v1": mail_routes,
    "/calendar/v1": calendar_routes,
    "/catalog": catalog_routes,
}


def build_app(state: State, port: int, services: Services | None = None, helpers: bool = True) -> Starlette:
    routes = [
        Route(f"{prefix}{r.path}", r.endpoint, methods=sorted(r.methods or []))
        for prefix, make in (SERVICES if services is None else services).items()
        for r in make(state)
    ]
    if helpers:
        routes += helper_routes(state, f"http://{HOST}:{port}")
    return Starlette(routes=routes)


def start_secure(state: State, port: int, add_ons: tuple[str, ...] = ("journey_panel",)) -> uvicorn.Server:
    """Make the throwaway authority and certificate, build the wheels of the add-ons the catalog lists (fixture folders)
    and the feed that lists them, and answer over HTTPS on `port` from a background thread. Returns once the server is
    listening."""
    certs = fake_tls.make(state.folder / "tls")
    state.https_base = f"https://{HOST}:{port}"
    wheels = [build_wheel(PLUGINS / folder, state.assets) for folder in add_ons]
    state.wheels = {wheel.name: wheel for wheel in wheels}
    state.catalog_text = catalog_feed(wheels, state.https_base)
    config = uvicorn.Config(
        build_app(state, port, SECURE_SERVICES, helpers=False),
        host=HOST,
        port=port,
        log_level="warning",
        ssl_certfile=str(certs.certificate),
        ssl_keyfile=str(certs.key),
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    # An event's timed wait: it can't be cut short by a clock tool, as a plain sleep was.
    pause = threading.Event()
    for _ in range(200):
        if server.started:
            return server
        pause.wait(0.05)
    raise RuntimeError("the HTTPS fake services did not start")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--https-port", type=int, default=0)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--catalog", default="journey_panel", help="the fixture add-ons the catalog lists, comma-separated"
    )
    args = parser.parse_args()
    state = State(args.state)
    if args.https_port:
        start_secure(state, args.https_port, tuple(name for name in args.catalog.split(",") if name))
    uvicorn.run(build_app(state, args.port), host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
