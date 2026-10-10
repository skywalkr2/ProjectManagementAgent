"""Secret references: config holds `env:NAME` or `file:/path`, never the secret itself."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


class SecretError(Exception):
    """A secret reference can't be resolved. The message names the reference, never a value."""


def resolve_secret(ref: str | None, env: Mapping[str, str] | None = None) -> str | None:
    if ref is None:
        return None
    env = os.environ if env is None else env
    scheme, _, name = ref.partition(":")
    if scheme == "env":
        value = env.get(name)
        if not value:
            raise SecretError(f"the environment variable {name} isn't set")
        return value
    if scheme == "file":
        path = Path(name).expanduser()
        if not path.is_file():
            raise SecretError(f"the secret file {path} doesn't exist")
        return path.read_text(encoding="utf-8").strip()
    if scheme == "keychain":
        raise SecretError("keychain references aren't supported yet; use env:NAME or file:/path")
    raise SecretError(f"{ref.split(':', 1)[0]!r} isn't a known secret reference; use env:NAME or file:/path")


def describe_secret(ref: str | None) -> str:
    """Where a secret reference reads from, in plain words, never the secret itself."""
    if ref is None:
        return "no key is set for this account"
    scheme, _, name = ref.partition(":")
    if scheme == "env":
        return f"key from the environment variable {name}"
    if scheme == "file":
        return f"key from the file {Path(name).expanduser()}"
    return f"key from {scheme}"
