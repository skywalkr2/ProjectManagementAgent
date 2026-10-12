"""Secret references: config holds `env:NAME` or `file:/path`, never the secret itself."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


class SecretHint(str):
    """The input hint of a field that takes a secret reference. It is the one text that names the `env:NAME` and
    `file:/path` forms on screen, because the field can't be filled in without them; the wording check exempts it."""


class SecretError(Exception):
    """A secret reference can't be resolved. The message is plain words for the screen: it names the secret the person
    gave (its name or its file), never a value and never the reference's syntax."""


def resolve_secret(ref: str | None, env: Mapping[str, str] | None = None) -> str | None:
    if ref is None:
        return None
    env = os.environ if env is None else env
    scheme, _, name = ref.partition(":")
    if scheme == "env":
        value = env.get(name)
        if not value:
            raise SecretError(f"a secret isn't set (its name: {name})")
        return value
    if scheme == "file":
        path = Path(name).expanduser()
        if not path.is_file():
            raise SecretError(f"the file that holds a secret isn't there ({path})")
        return path.read_text(encoding="utf-8").strip()
    if scheme == "keychain":
        raise SecretError("keeping a secret in the computer's keychain isn't supported yet")
    raise SecretError("that isn't a way of keeping a secret the app knows; use the form the field's hint shows")


def describe_secret(ref: str | None) -> str:
    """Where a secret reference reads from, in plain words, never the secret itself."""
    if ref is None:
        return "no key is set for this account"
    scheme, _, name = ref.partition(":")
    if scheme == "env":
        return f"key from the secret named {name}"
    if scheme == "file":
        return f"key from the file {Path(name).expanduser()}"
    return "key from another place"
