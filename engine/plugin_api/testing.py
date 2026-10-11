"""Testing a connector without a network: part of the plugin API, for plugins' own tests.

    from engine.plugin_api.testing import Reply, connector_context, read

    def service(asked):
        if asked.path == "/v1/changes":
            return Reply(json={"items": [...], "next": "m2"})
        return Reply(status=404)

    context = connector_context(service, network=["api.example.com"], secrets={"client-id": "x"},
                                tokens={"myplugin/account": "token"})
    poll = read(my_poll, MySettings(), {}, context)

`service(asked)` answers every request the connector makes through `context.web`: `asked` has the method, url,
path, query (a dict), headers and body (text, and `form` / `json()` parsed). Only hosts in `network` are reached, over
HTTPS, as in the app. `secrets` answers `context.secret(name)` and records `context.keep_secret`; `tokens` answers
`context.access_token(name)`, and a sign-in missing from it raises `ConnectorError("auth")` as an expired sign-in
does. `read` runs `poll` and checks its answer the way the watcher does.
"""

from __future__ import annotations

import json as jsonlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from engine.connectors import ConnectorContext, ConnectorError, Poll, checked_poll

__all__ = ["Asked", "Reply", "connector_context", "read"]


@dataclass(frozen=True)
class Asked:
    """One request a connector made."""

    method: str
    url: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: str

    @property
    def form(self) -> dict[str, list[str]]:
        """A form body, parsed."""
        return parse_qs(self.body)

    def json(self) -> Any:
        return jsonlib.loads(self.body) if self.body else None


@dataclass(frozen=True)
class Reply:
    """An answer: a status, and a JSON value or text, with headers (a Retry-After, say)."""

    status: int = 200
    json: Any = None
    text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def connector_context(
    service: Callable[[Asked], Reply],
    *,
    network: list[str],
    secrets: dict[str, str] | None = None,
    tokens: dict[str, str] | None = None,
    workspace_root: Path | str = ".",
) -> ConnectorContext:
    """A connector's context whose web client is answered by `service`. `kept` secrets land in `secrets`."""
    from engine.net import WebClient

    kept = secrets if secrets is not None else {}
    granted = dict(tokens or {})

    def answer(request: httpx.Request) -> httpx.Response:
        parts = urlsplit(str(request.url))
        asked = Asked(
            request.method,
            str(request.url),
            parts.path,
            parse_qs(parts.query),
            dict(request.headers),
            request.content.decode("utf-8", errors="replace"),
        )
        reply = service(asked)
        if not isinstance(reply, Reply):
            raise TypeError("the service function answers with a Reply")
        if reply.json is not None:
            return httpx.Response(reply.status, json=reply.json, headers=reply.headers)
        return httpx.Response(reply.status, text=reply.text or "", headers=reply.headers)

    def access_token(name: str) -> str:
        if name not in granted:
            raise ConnectorError("auth", f"Sign in to {name} first.")
        return granted[name]

    return ConnectorContext(
        workspace_root=Path(workspace_root),
        web=WebClient(list(network), transport=httpx.MockTransport(answer)),
        secret=kept.get,
        keep_secret=kept.__setitem__,
        access_token=access_token,
    )


def read(poll: Callable[..., Poll], settings: Any, state: dict[str, Any] | None, context: ConnectorContext) -> Poll:
    """Run a connector's `poll` and check its answer as the watcher does. A ConnectorError passes through."""
    return checked_poll(poll(settings, dict(state or {}), context))
