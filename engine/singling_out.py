"""Never single a person out in a draft to several people (design 6.35).

A draft that goes to a group never names one of its members as the cause of a miss: a discrepancy in one person's work
is asked of that person on their own, in a draft to them alone. Naming is a judgment, so this is a lint (a return
round, then held for the person), found by rules: a sentence that holds a group member's name and one of the
configured miss phrases (`language.singling_out_phrases`)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from engine import audience, scope


def group_of(people: Any, written: Iterable[str]) -> list[str]:
    """The known people other than the person running the app that these names or ids resolve to, each once."""
    found: list[str] = []
    for entry in written:
        resolved = people.resolve(entry) if entry.strip() else None
        if resolved is not None and resolved.status == "ok" and resolved.person not in (people.pm, *found):
            found.append(resolved.person)
    return found


def group_of_message(people: Any, raw: str) -> list[str]:
    """The known people other than the person on a saved message's From, To and Cc lines: the group a reply to all of
    them would reach."""
    return [p for p in audience.people_of(raw, people) if p != people.pm and people.records.get(p) is not None]


def singled_out(people: Any, text: str, group: Iterable[str], phrases: Iterable[str]) -> tuple[str, str] | None:
    """The first member of the group the text blames: the person's id and the sentence, or None. A sentence blames when
    it names the member (by full name or first name, whole words, ignoring case) and holds one of the phrases."""
    phrases = [p for p in phrases if p.strip()]
    members = list(group)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if not any(scope.has_word(sentence, p) for p in phrases):
            continue
        for member in members:
            names = {people.name(member), people.first_name(member)}
            if any(n.strip() and scope.has_word(sentence, n) for n in names):
                return member, sentence.strip()
    return None
