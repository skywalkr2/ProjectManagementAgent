"""The everyday words of a language: the shipped list a project name made of one such word never files by alone
(`language.everyday_words`, design 6.32). Reads the file the core ships beside the other defaults."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from engine.yaml_load import load_yaml

WORDS_FILE = Path(__file__).parent / "defaults" / "everyday_words.yaml"
DEFAULT_LANGUAGE = "en"


@cache
def _shipped() -> dict[str, tuple[str, ...]]:
    data = load_yaml(WORDS_FILE.read_text(encoding="utf-8")) or {}
    return {str(tag): tuple(str(w) for w in words or []) for tag, words in data.items()}


def shipped(language: str = DEFAULT_LANGUAGE) -> list[str]:
    """The shipped everyday words for a language tag (its primary part is used: `en-US` reads the `en` list); the
    default language's list when none ships for it."""
    tag = language.split("-", 1)[0].lower()
    found = _shipped()
    return list(found.get(tag) or found.get(DEFAULT_LANGUAGE) or ())
