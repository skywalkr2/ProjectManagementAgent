"""Which addresses and origins may reach the app, and which listen addresses local mode allows.

Local mode listens only on this computer, so a request must name the app's own address in `Host`, and a request that
changes anything must not come from another web page. Hosted mode accepts only the public address. The sets are built
from the server settings, so nothing about a particular address or host is written in code.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from engine.config.schema import ServerFile

#: Names that always mean this computer, whatever address the app was told to listen on.
LOOPBACK_NAMES = ("localhost", "127.0.0.1", "[::1]")

_DEFAULT_PORTS = {"http": 80, "https": 443}


def is_loopback(host: str) -> bool:
    """Whether a listen address only reaches this computer: `localhost` or an address in a loopback range."""
    name = host.strip().strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def local_address_problem(server: ServerFile) -> str | None:
    """Plain words saying why local mode can't listen on the configured address, or None when it can."""
    if server.mode != "local" or is_loopback(server.host):
        return None
    return (
        f"Local mode only listens on this computer, so it can't use the address {server.host}. "
        "Reaching the app from another device needs hosted mode, which isn't available yet. "
        "Leave the address at its default."
    )


def _bracketed(host: str) -> str:
    """A host as it appears in a `Host` header: IPv6 literals in brackets, names in lower case."""
    name = host.strip().lower()
    if ":" in name and not name.startswith("["):
        return f"[{name}]"
    return name


def _with_port(host: str, port: int, default_port: int | None) -> set[str]:
    named = {f"{host}:{port}"}
    if port == default_port:
        named.add(host)
    return named


def allowed_hosts(server: ServerFile) -> set[str]:
    """The `Host` values (lower case) the app answers to."""
    if server.mode == "hosted":
        if not server.public_url:
            return set()
        parts = urlsplit(server.public_url)
        if not parts.hostname:
            return set()
        default = _DEFAULT_PORTS.get(parts.scheme)
        return _with_port(_bracketed(parts.hostname), parts.port or default or 0, default)
    names = {_bracketed(name) for name in (server.host, *LOOPBACK_NAMES)}
    allowed: set[str] = set()
    for name in names:
        allowed |= _with_port(name, server.port, _DEFAULT_PORTS["http"])
    return allowed


def allowed_origins(server: ServerFile) -> set[str]:
    """The `Origin` values (lower case) that count as the app's own page."""
    if server.mode == "hosted":
        if not server.public_url:
            return set()
        parts = urlsplit(server.public_url)
        if not parts.hostname:
            return set()
        host = _bracketed(parts.hostname)
        default = _DEFAULT_PORTS.get(parts.scheme)
        shown = host if parts.port in (None, default) else f"{host}:{parts.port}"
        return {f"{parts.scheme.lower()}://{shown}"}
    return {f"http://{host}" for host in allowed_hosts(server)}
