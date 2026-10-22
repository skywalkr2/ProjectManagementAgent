"""Which model of a family is the newest (design 6.16, "A newer model is asked about, never switched to").

A family is a word from the catalog's presets, matched without regard to case against a service's model ids. The newest
model of a family is decided from what the service states, in this order:

1. a creation or release date the model listing gives (`ModelInfo.released`), when every model of the family has one;
2. else the version number in the model's id, compared number by number (so 5.5 is newer than 4.5 and 10 newer than 9),
   when every model of the family has one; a long run of digits (a date stamp) is not part of the version and only
   breaks a tie between equal versions;
3. else the list's own order, the first listed, and the answer says so.

One function decides it for the preset that fills a new account's tiers and for the weekly check of newer models, so
the two never disagree. Nothing here reads a vendor's name: the family word comes from the catalog's data.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal

from engine.ai.task import ModelInfo

Basis = Literal["date", "version", "list"]

#: A run of at least this many digits is a date stamp, not a version.
STAMP_DIGITS = 6

_NUMBERS = re.compile(r"\d+")


def of_family(family: str, ids: Sequence[str]) -> list[str]:
    """The ids that hold the family word, ignoring case, in the order given. Never a model of another family."""
    word = family.casefold()
    return [i for i in ids if word and word in i.casefold()]


def version_of(model_id: str) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """The version in a model's id as numbers, and its date stamps apart, or None when the id has no version number."""
    found = _NUMBERS.findall(model_id)
    version = tuple(int(n) for n in found if len(n) < STAMP_DIGITS)
    stamps = tuple(int(n) for n in found if len(n) >= STAMP_DIGITS)
    return (version, stamps) if version else None


def newest_of_family(
    family: str, ids: Sequence[str], info: Mapping[str, ModelInfo] | None = None
) -> tuple[str | None, Basis]:
    """The newest model of the family among `ids` (in the list's order) and what decided it: `date`, `version` or
    `list`. None when no id holds the family word. A tie keeps the model listed first."""
    found = of_family(family, ids)
    if not found:
        return None, "list"
    if len(found) == 1:
        return found[0], "list"
    known = info or {}
    dates = [(known[i].released if i in known else None) for i in found]
    if all(dates):
        best = max(range(len(found)), key=lambda n: (str(dates[n]), -n))
        return found[best], "date"
    versions = [version_of(i) for i in found]
    if all(v is not None for v in versions):
        best = max(range(len(found)), key=lambda n: (versions[n], -n))  # type: ignore[type-var]
        return found[best], "version"
    return found[0], "list"


def is_newer(
    family: str, current: str, candidate: str, ids: Sequence[str], info: Mapping[str, ModelInfo] | None
) -> bool:
    """Whether `candidate` is a newer model of the family than `current`, by the same rule: it is newer when it is the
    family's newest among the listed ids and the current one is not it, and, where the rule can compare only two
    models, when it beats the current model by that comparison."""
    pair = [i for i in ids if i in (current, candidate)]
    if candidate == current or len(pair) < 2:
        return False
    newest, _ = newest_of_family(family, pair, info)
    return newest == candidate
