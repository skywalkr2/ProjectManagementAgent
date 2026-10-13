"""The wording check: text the screen shows never names a settings file, a secret reference, a settings key, a manifest
field or a command (design 7.0, 7.1). Terminal output may; the screen may not.

`problems(text)` finds what a person would have to know the product's insides to read. `ScreenText` types the response
fields whose text the server writes; while the developer switch `COCKPIT_CHECK_WORDING=1` is set (tests and
development, never a setting), sending such a field that `problems` flags fails, and so does an error message the app
returns that it flags. With the switch off nothing changes.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Annotated, Any

from pydantic import WrapValidator
from pydantic_core import PydanticCustomError

from engine.secrets import SecretHint

#: The environment variable that turns the check on.
SWITCH = "COCKPIT_CHECK_WORDING"

_FILE_NAME = re.compile(r"\S*\.ya?ml\b")
#: Phrases that name where settings are kept, which a person never needs to know ("your settings" says it).
_BANNED_PHRASES = re.compile(r"\bsettings? files?\b", re.IGNORECASE)
_SECRET_REF = re.compile(r"\b(?:env|keychain):|\bfile:/|\bfile:~")
_MANIFEST_FIELD = re.compile(r"\b(?:requires|provides|interfaces)\.[a-z_]+|\b(?:plugin_api|depends_on|config_schema)\b")
_DOTTED = re.compile(r"(?<![\w.-])[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)+(?![\w-])")
_OTHER_COMMANDS = re.compile(
    r"\buv (?:run|sync|lock|pip|tool)\b"
    r"|\bnpm [a-z]+"
    r"|\bgit (?:pull|push|commit|clone|checkout|status|add|merge|rebase|fetch|log|diff|reset|stash|init|config|remote|"
    r"tag|branch)\b"
)


def enabled() -> bool:
    """Whether the developer switch is on."""
    return os.environ.get(SWITCH) == "1"


@lru_cache(maxsize=1)
def _key_index() -> tuple[frozenset[str], frozenset[str]]:
    """The settings keys as the schema declares them, and which of them hold a mapping or a list of records.

    Each key is listed with the file's name in front and without it, with its parent groups. A path may go on under a
    key that holds a mapping, with names the person chose."""
    from engine.config import Config
    from engine.config.schema import FILES
    from engine.settings import describe

    cfg = Config(files={name: model() for name, model in FILES.items()})
    keys: set[str] = set()
    mappings: set[str] = set()
    for setting in describe(cfg):
        for form in (setting.key, setting.key.partition(".")[2]):
            parts = [p for p in form.split(".") if p]
            keys.update(".".join(parts[:size]) for size in range(1, len(parts) + 1))
            if setting.type == "other" and parts:
                mappings.add(form)
    return frozenset(keys), frozenset(mappings)


def settings_keys() -> frozenset[str]:
    """Every key the settings forms list, in every form a message could use (see `_key_index`)."""
    return _key_index()[0]


@lru_cache(maxsize=1)
def command_names() -> frozenset[str]:
    """The command line's subcommand names, read from its parser."""
    import argparse

    from engine.cli import _parser

    names: set[str] = set()
    for action in _parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices)
    return frozenset(names)


def _is_key_path(token: str) -> bool:
    keys, mappings = _key_index()
    if token in keys:
        return True
    parts = token.split(".")
    return any(".".join(parts[:size]) in mappings for size in range(1, len(parts)))


def problems(text: str) -> list[str]:
    """What in text meant for the screen names the product's insides; empty when nothing does."""
    found: list[str] = []
    for match in _FILE_NAME.finditer(text):
        found.append(f"names a settings file: {match.group()!r}")
    for match in _BANNED_PHRASES.finditer(text):
        found.append(f"names a settings file: {match.group()!r}")
    for match in _SECRET_REF.finditer(text):
        found.append(f"names a secret reference: {match.group()!r}")
    for match in _MANIFEST_FIELD.finditer(text):
        found.append(f"names a manifest field: {match.group()!r}")
    for match in _DOTTED.finditer(text):
        if _is_key_path(match.group()):
            found.append(f"names a settings key: {match.group()!r}")
    commands = command_names()
    for match in re.finditer(r"\bcockpit ([a-z][a-z-]*)", text):
        if match.group(1) in commands:
            found.append(f"names a command: {match.group()!r}")
    for match in _OTHER_COMMANDS.finditer(text):
        found.append(f"names a command: {match.group()!r}")
    return found


def _check(value: Any, handler: Any) -> str:
    text = handler(value)
    # A secret-reference field's input hint is the one text allowed to show the reference form.
    if enabled() and not isinstance(value, SecretHint):
        found = problems(text)
        if found:
            raise PydanticCustomError(
                "screen_text", "text for the screen {problems}: {text}", {"problems": "; ".join(found), "text": text}
            )
    return text


#: Text a person reads that the server writes. While the check is on, a value that `problems` flags is refused.
ScreenText = Annotated[str, WrapValidator(_check)]


def refusal(text: str) -> str | None:
    """The reason an error message the app returns can't be shown, or None when it can (or the check is off)."""
    if not enabled():
        return None
    found = problems(text)
    return f"error text for the screen {'; '.join(found)}: {text}" if found else None


__all__ = ["SWITCH", "ScreenText", "command_names", "enabled", "problems", "refusal", "settings_keys"]
