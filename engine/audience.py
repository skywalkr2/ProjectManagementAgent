"""A sender's distribution limit travels with the content (design 6.35).

A message that says who may see it (a configured marking such as "internal only" in its new text, never in the quoted
history) limits its source to the people it went to and came from: its `audience`. The rules read it when the message
is taken in; the assistant may only narrow it (`source.limit`) and the person widens it (`source.widen`). A question or
reply drawn from a limited source goes only to someone in its audience (the person running the app is never outside
it), checked by the applier as the `audience` invariant.

A record made from a limited source (a fact, an action or a question whose evidence or source is one) carries its
source's limit too. The limit is derived from the source when read, never copied, so widening the source widens
everything made from it, and a record drawing on several sources has the narrowest of them. A packet for a draft to a
named reader leaves out the records that reader is outside of (`left_out_for`), and the invariant refuses a draft that
names such a record."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from email.utils import parseaddr
from typing import Any

from engine import reply_lines

#: The longest sentence kept as the reason a message is limited.
WHY_MAX = 300


def marking_in(text: str, markings: Iterable[str]) -> tuple[str, str] | None:
    """The first configured marking the text holds (whole words, ignoring case) and the sentence it is in; None when it
    holds none. When two start together the longer wins."""
    plain = text.replace("’", "'")  # a typographic apostrophe reads as a plain one; the length is unchanged
    best: tuple[int, int, str] | None = None
    for phrase in markings:
        words = " ".join(phrase.replace("’", "'").split())
        if not words:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words.split()) + r"(?!\w)"
        found = re.search(pattern, plain, re.IGNORECASE)
        if found is not None and (best is None or (found.start(), -len(words)) < (best[0], -best[1])):
            best = (found.start(), len(words), phrase)
    if best is None:
        return None
    start = best[0]
    ends = "." + "!?\n"
    before = max(plain.rfind(c, 0, start) for c in ends) + 1
    after = [i for i in (plain.find(c, start + best[1]) for c in ends) if i != -1]
    stop = min(after) + 1 if after else len(plain)
    return best[2], " ".join(plain[before:stop].split())[:WHY_MAX]


def _kept(people: Any, entry: str) -> str | None:
    """A header entry as it is kept in an audience: the id of the one known person it is, else its address lowercased
    (its name lowercased when it has none)."""
    found = people.match_entries([entry])
    if len(found) == 1:
        return next(iter(found))
    name, address = parseaddr(entry)
    kept = (address or name or entry).strip().lower()
    return kept or None


def people_of(text: str, people: Any) -> list[str]:
    """Who a message went to and came from (its From, To and Cc lines), each once: known people by id, anyone else by
    lowercased address. Empty for a text that isn't a message with those lines."""
    read = reply_lines.read_message(text)
    if read is None:
        return []
    kept: list[str] = []
    for entry in (read.sender, *read.to, *read.cc):
        who = _kept(people, entry)
        if who is not None and who not in kept:
            kept.append(who)
    return kept


def limit_of(text: str, markings: Iterable[str], people: Any) -> dict[str, Any] | None:
    """The audience a message's own words give it, or None when its new text holds no marking, or the text doesn't say
    who it went to (a note to oneself has nobody to limit it to)."""
    read = reply_lines.read_message(text)
    if read is None:
        return None
    found = marking_in(read.new_text, markings)
    audience = people_of(text, people)
    if found is None or not audience:
        return None
    return {"people": audience, "marking": found[0], "why": found[1], "group": None, "widened_by": None}


def narrowest(audiences: Iterable[Mapping[str, Any] | None]) -> dict[str, Any] | None:
    """The most restrictive of several audiences: the people all of them hold. None when none of them is limited."""
    limited = [dict(a) for a in audiences if a]
    if not limited:
        return None
    first, *rest = limited
    common = [p for p in first["people"] if all(p in other["people"] for other in rest)]
    return {**first, "people": common}


def addresses_of(people: Any, person: str) -> set[str]:
    """The addresses a person's record holds, lowercased."""
    data = people.records.get(person) or {}
    return {v.strip().lower() for v in (data.get("how_to_reach") or {}).values() if "@" in str(v)}


def within(audience: Mapping[str, Any], people: Any, person: str | None, written: str) -> bool:
    """Whether a recipient is inside an audience: the person running the app always is; a known person is when their id
    or an address their record holds is in it; anyone else is when their address (or name) as written is."""
    allowed = set(audience["people"])
    if person is not None:
        return person == people.pm or person in allowed or bool(addresses_of(people, person) & allowed)
    return written.strip().lower() in allowed or parseaddr(written)[1].strip().lower() in allowed


def names_of(people: Any, audience: Mapping[str, Any]) -> str:
    return ", ".join(people.name(p) for p in audience["people"])


def sources_of(data: Mapping[str, Any]) -> list[str]:
    """The saved sources a record rests on: the one it came from and the one its evidence quotes (the person's own
    note is no saved source)."""
    evidence = data.get("evidence")
    found = [data.get("source"), evidence.get("source") if isinstance(evidence, Mapping) else None]
    return list(dict.fromkeys(s for s in found if isinstance(s, str) and s and s != "note"))


def limit_of_record(view: Any, data: Mapping[str, Any]) -> dict[str, Any] | None:
    """The limit a record carries: the narrowest audience of the sources it rests on, read from them now, or None when
    none of them is limited."""
    found = (view.get("source", s) for s in sources_of(data))
    return narrowest(r.data.get("audience") for r in found if r is not None)


def left_out_for(
    view: Any, people: Any, readers: Iterable[tuple[str | None, str]]
) -> Callable[[Mapping[str, Any]], bool]:
    """A test for the records a packet leaves out because it drafts to these readers (each a person id or None, and the
    name or address as written): true for a record whose limit has any of them outside. With no readers nothing is
    left out."""
    named = list(readers)

    def out(data: Mapping[str, Any]) -> bool:
        limit = limit_of_record(view, data) if named else None
        return limit is not None and any(not within(limit, people, person, written) for person, written in named)

    return out


def sender_reader(people: Any, text: str) -> tuple[str | None, str] | None:
    """Who a message is from, as `left_out_for` takes a reader: the one known person's id, else the From entry as
    written; None for a text that isn't a message."""
    read = reply_lines.read_message(text)
    if read is None:
        return None
    found = people.match_entries([read.sender])
    return (next(iter(found)) if len(found) == 1 else None), read.sender


def recipient_problem(
    view: Any,
    people: Any,
    sources: Iterable[str | None],
    written: str,
    records: Iterable[Mapping[str, Any]] = (),
) -> str | None:
    """Why something drawn from these sources, and from these records (which rest on sources of their own), can't go
    to `written` (a name, an id or an address), or None. Each source that has an audience must hold the recipient."""
    resolved = people.resolve(written)
    person = resolved.person if resolved.status == "ok" else None
    sources = [*sources, *(s for record in records for s in sources_of(record))]
    for source_id in dict.fromkeys(s for s in sources if s):
        source = view.get("source", source_id)
        audience = source.data.get("audience") if source is not None else None
        if audience and not within(audience, people, person, written):
            who = people.name(person) if person else written
            return f"this draws on a message limited to {names_of(people, audience)}, so it can't go to {who}"
    return None
