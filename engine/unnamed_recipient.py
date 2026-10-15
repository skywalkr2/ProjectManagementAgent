"""The check that a recipient is never guessed: when an input says the person already sent something and gives no
recipient, a question or action that names one for it is a guess from the nearest name (design 6.7)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from engine.check_text import without_links
from engine.cleaning import normalize

_SENTENCE_END = re.compile(r"[.!?\n]")
_WORD = re.compile(r"[a-z0-9]{4,}")
_NAME_WORD = re.compile(r"[a-z0-9]{3,}")


def sentence_saying_sent(text: str, phrases: Iterable[str]) -> str | None:
    """The sentence of `text` that says the person already sent something (one of `phrases`, as whole words, ignoring
    case), or None."""
    shown = normalize(text)
    for phrase in phrases:
        needle = normalize(phrase)
        if not needle:
            continue
        found = re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", shown)
        if found is None:
            continue
        start = max((m.end() for m in _SENTENCE_END.finditer(shown, 0, found.start())), default=0)
        end = _SENTENCE_END.search(shown, found.end())
        return shown[start : end.start() if end else len(shown)].strip()
    return None


def names_in(text: str, names: Iterable[str]) -> bool:
    """Whether `text` holds a person's name: any of `names` (full name, aliases) as a whole phrase, or any word of
    three letters or more from them."""
    shown = normalize(text)
    words = set(re.findall(r"[a-z0-9]+", shown))
    for name in names:
        full = normalize(name)
        if full and re.search(rf"(?<![a-z0-9]){re.escape(full)}(?![a-z0-9])", shown):
            return True
        if any(word in words for word in _NAME_WORD.findall(full)):
            return True
    return False


def guessed_recipient(
    input_text: str, op_text: str, recipients: Iterable[Iterable[str]], phrases: Iterable[str]
) -> bool:
    """Whether an op's recipients are a guess: the input says something was already sent, an op's words are about what
    was sent, and none of the recipients (each a list of the names that person goes by) is in the input's words."""
    sentence = sentence_saying_sent(input_text, phrases)
    people = [list(names) for names in recipients]
    if sentence is None or not people:
        return False
    about = set(_WORD.findall(without_links(sentence))) & set(_WORD.findall(normalize(without_links(op_text))))
    return bool(about) and not any(names_in(input_text, names) for names in people)
