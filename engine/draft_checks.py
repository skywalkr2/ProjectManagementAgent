"""Plain checks on text that reaches a person or is kept as the workspace's own (design 6.7, 8.8): quoted words are in
the material cited, names are spelled as the workspace has them, links come from somewhere the person can trust, a
tool's version number stays out of a message to someone else, a project's summary is status, and a change that says it
made a draft or a file holds it.

Each function takes text and what to compare it with and returns what it found; none reads the store or the network.
The applier turns what they find into lints with the severity the workspace sets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from engine.check_text import links_in, quoted_passages
from engine.cleaning import normalize

_EDGE = " \t\r\n.,;:!?-'\"()[]‘’“”–—"
_ELLIPSIS = re.compile(r"\s*(?:\.{3}|…)\s*")


def unverified_quotes(text: str, sources: Iterable[str], min_words: int) -> list[str]:
    """The passages of `text` in double quotation marks that are not in any of `sources`. A passage with fewer than
    `min_words` words is a name or a term in quotation marks, not a quote. Compared ignoring case, the kind of
    quotation mark and the punctuation at its edges; an ellipsis splits a passage into the pieces that must each be
    there."""
    shown = [normalize(s) for s in sources if s]
    found: list[str] = []
    for passage in quoted_passages(text):
        if len(passage.split()) < min_words:
            continue
        for piece in _ELLIPSIS.split(passage):
            core = normalize(piece.strip(_EDGE))
            if core and not any(core in s for s in shown):
                found.append(passage)
                break
    return found


# ---- links -----------------------------------------------------------------------------------------------------------

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def link_key(link: str) -> tuple[str, str, str]:
    """A link as (host, path, query), for comparing two spellings of one address: scheme, `www.`, a trailing slash and
    the fragment don't matter, and the host's case doesn't."""
    text = _SCHEME.sub("", link.strip()).split("#", 1)[0]
    where, _, query = text.partition("?")
    host, _, path = where.partition("/")
    host = re.sub(r"^www\.", "", host.lower())
    return host, path.rstrip("/"), query


class KnownLinks:
    """The web addresses a person can trust a draft to point at: those in the input and the records, and the
    configured sources'. A bare host passes when it is the host of a known address."""

    def __init__(self) -> None:
        self.keys: set[tuple[str, str, str]] = set()
        self.hosts: set[str] = set()

    def add_text(self, text: str) -> None:
        for link in links_in(text):
            self.add(link)

    def add(self, link: str) -> None:
        key = link_key(link)
        if key[0]:
            self.keys.add(key)
            self.hosts.add(key[0])

    def add_values(self, value: Any) -> None:
        """Every address in the strings inside a record's data, however deeply they are nested."""
        if isinstance(value, str):
            self.add_text(value)
        elif isinstance(value, dict):
            for inner in value.values():
                self.add_values(inner)
        elif isinstance(value, (list, tuple)):
            for inner in value:
                self.add_values(inner)

    def holds(self, link: str) -> bool:
        key = link_key(link)
        if key in self.keys:
            return True
        return not key[1] and not key[2] and key[0] in self.hosts


def unknown_links(text: str, extra: Iterable[str], known: KnownLinks) -> list[str]:
    """The web addresses in `text` and in `extra` (links given beside it) that `known` doesn't hold, each once."""
    found: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for link in [*links_in(text), *extra]:
        key = link_key(link)
        if key in seen or known.holds(link):
            continue
        seen.add(key)
        found.append(link)
    return found


# ---- version numbers -------------------------------------------------------------------------------------------------


def without_names(text: str, names: Iterable[str]) -> str:
    """`text` with each of the names taken out (whole phrase, ignoring case)."""
    for name in sorted({n for n in names if n and n.strip()}, key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", " ", text, flags=re.IGNORECASE)
    return text


def version_numbers(text: str, patterns: Sequence[str], known_names: Iterable[str] = ()) -> list[str]:
    """The tool version numbers in `text`, each as written: matches of `patterns`, outside any known name that holds
    one (a product's own name)."""
    left = without_names(text, [n for n in known_names if any(ch.isdigit() for ch in n)])
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, left):
            if match.group() not in found:
                found.append(match.group())
    return found


# ---- names -----------------------------------------------------------------------------------------------------------

_WORD = r"[A-Z][a-z]+(?:[-'’][A-Za-z]+)*"
_RUN = re.compile(rf"(?<![A-Za-z0-9]){_WORD}(?:[ \t]+{_WORD})+")
_POSSESSIVE = re.compile(r"['’]s$")


def name_phrases(text: str, skip_words: Iterable[str], greeting: str = "") -> list[str]:
    """The phrases in `text` that read as a person's name: two or more capitalized words in a row, with everyday words
    from `skip_words` taken off either end, and the one capitalized word after the greeting (the part of the greeting
    line before the first name, such as "Hi "). Each once, as written."""
    skipped = {w.lower() for w in skip_words}
    found: list[str] = []

    def keep(words: list[str]) -> None:
        while words and words[0].lower() in skipped:
            words = words[1:]
        while words and words[-1].lower() in skipped:
            words = words[:-1]
        if not words:
            return
        phrase = _POSSESSIVE.sub("", " ".join(words))
        if phrase not in found:
            found.append(phrase)

    for match in _RUN.finditer(text):
        words = match.group().split()
        if len(words) >= 2 and len([w for w in words if w.lower() not in skipped]) >= 2:
            keep(words)
    prefix = greeting.split("{first_name}", 1)[0].strip() if "{first_name}" in greeting else ""
    if prefix:
        for match in re.finditer(rf"(?:^|\n)\s*{re.escape(prefix)}\s+({_WORD})", text):
            keep([match.group(1)])
    return found


def person_names(person: dict[str, Any]) -> list[str]:
    """Every way a person's record spells their name: the full name, the name a greeting uses (the first word of the
    full name when none is set) and the aliases."""
    full = str(person.get("full_name") or "")
    first = str(person.get("first_name") or "") or (full.split()[0] if full.split() else "")
    return [n for n in (full, first, *(person.get("aliases") or [])) if n and n.strip()]


def unverified_names(
    text: str,
    people: Iterable[Iterable[str]],
    known_terms: Iterable[str],
    sources: Iterable[str],
    skip_words: Iterable[str],
    greeting: str = "",
) -> list[str]:
    """The names `text` spells that no person's full name, first name or alias matches, that aren't a name the
    workspace knows (a glossary term, a project, an organization, a team, whole or in part) and that the input doesn't
    spell: the spelling came from nowhere."""
    own = {normalize(n) for names in people for n in names}
    terms = [normalize(t) for t in known_terms]
    shown = [normalize(s) for s in sources if s]
    found: list[str] = []
    for phrase in name_phrases(text, skip_words, greeting):
        key = normalize(phrase)
        if key in own or any(key in t for t in terms) or any(key in s for s in shown):
            continue
        found.append(phrase)
    return found


# ---- a project's summary ---------------------------------------------------------------------------------------------


def summary_problems(text: str, max_lines: int, findings_words: Iterable[str]) -> list[str]:
    """Why a project's summary isn't status, as plain reasons: more lines than `max_lines`, or one of the findings
    words (whole words, ignoring case)."""
    reasons = []
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > max_lines:
        reasons.append(f"it has {len(lines)} lines and a summary has at most {max_lines}")
    shown = normalize(text)
    for word in findings_words:
        needle = normalize(word)
        if needle and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", shown):
            reasons.append(f"it says {word!r}, which reports a finding, not the project's status")
            break
    return reasons


# ---- what a change made ----------------------------------------------------------------------------------------------


def says_it_made(summary: str, phrases: Iterable[str]) -> str | None:
    """The phrase (one of `phrases`, as whole words, ignoring case) that says the change made a draft, a write-up or a
    file, or None."""
    shown = normalize(summary)
    for phrase in phrases:
        needle = normalize(phrase)
        if needle and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", shown):
            return phrase
    return None
