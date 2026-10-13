"""Name resolution at the boundary (design 6.11): names become person ids once, where they come in.

An id passes. A full name or alias that matches one person becomes that id. The PM's aliases become the PM. A first
name resolves only for a person in the input's context: the PM, the people on the message (its sender and the others
on it), and the people of the project the input is about. A first name with a different initial or surname fragment
resolves only to a person that fragment fits. Anything else is ambiguous or unknown, and the op waits for the PM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any, Literal

from engine.config import Config
from engine.storage import Store


@dataclass(frozen=True)
class Resolved:
    """`ambiguous`: one or more people might be meant and the name and the context don't settle which; `candidates`
    are the people to choose from. `unknown`: nobody fits."""

    status: Literal["ok", "ambiguous", "unknown"]
    person: str | None = None
    candidates: tuple[str, ...] = ()


_HEADER = re.compile(r"^([A-Za-z][A-Za-z-]*):[ \t]*(.*)$")
_PEOPLE_HEADERS = ("from", "to", "cc")


def header_entries(text: str) -> list[str]:
    """The people named in a message's leading header block (From, To and Cc lines, with their folded continuation
    lines), each as written: a name, an address, or `Name <address>`. The block ends at the first blank line, so
    quoted headers further down are not read."""
    values: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.lstrip("\n").splitlines():
        if not line.strip():
            break
        if line[0] in " \t":
            if current in values:
                values[current][-1] += " " + line.strip()
            continue
        found = _HEADER.match(line)
        current = found.group(1).lower() if found else None
        if found and current in _PEOPLE_HEADERS:
            values.setdefault(current, []).append(found.group(2).strip())
        elif found is None:
            break
    entries: list[str] = []
    for name in _PEOPLE_HEADERS:
        for value in values.get(name, []):
            for piece in re.split(r",(?![^<]*>)", value):
                written = " ".join(piece.split())
                if written and written not in entries:
                    entries.append(written)
    return entries


def _parts(entry: str) -> tuple[str, str]:
    """A header entry as (name, address): `Name <address>`, an address alone, or a name alone."""
    label, address = parseaddr(entry) if "<" in entry or "@" in entry else ("", "")
    if not label and not address:
        return " ".join(entry.split()), ""
    return label, address


class People:
    def __init__(self, store: Store, cfg: Config, *, context: Iterable[str] = ()):
        self._build({p.id: p.data for p in store.read().list("person")}, cfg.workspace.user.person, context)

    @classmethod
    def from_records(
        cls, records: Mapping[str, Mapping[str, Any]], pm: str | None, *, context: Iterable[str] = ()
    ) -> People:
        """The people from their records alone, for work that has no store."""
        self = object.__new__(cls)
        self._build(dict(records), pm, context)
        return self

    @classmethod
    def for_input(cls, store: Store, cfg: Config, request_id: str, text: str = "") -> People:
        """The people, with the context of one request's input: who it is from and to (the saved details of a watched
        message, then the header lines of `text`), and the people of the project it is about."""
        people = cls(store, cfg)
        people.in_context = people.in_context | people._input_people(store, request_id, text)
        return people

    def _build(self, records: dict[str, Any], pm: str | None, context: Iterable[str]) -> None:
        self.records = records
        self.pm = pm
        self.in_context: frozenset[str] = frozenset(context) | ({pm} if pm else frozenset())
        # Full names and aliases, which a person or the PM set as a way to name someone.
        self._named: dict[str, set[str]] = {}
        # First names, taken from the full names; they say who only together with the context.
        self._firsts: dict[str, set[str]] = {}
        for pid, data in self.records.items():
            for name in [data["full_name"], *data.get("aliases", [])]:
                if name:
                    self._named.setdefault(name.lower(), set()).add(pid)
            words = data["full_name"].split()
            if words:
                self._firsts.setdefault(words[0].lower(), set()).add(pid)
        self._index = {name: set(pids) for name, pids in self._named.items()}
        if self.pm:
            for alias in ["me", "myself", "I"]:
                self._index[alias.lower()] = {self.pm}

    def resolve(self, name: str) -> Resolved:
        text = " ".join(name.split())
        if text in self.records:
            return Resolved("ok", text)
        exact = [pid for pid, d in self.records.items() if d["full_name"].lower() == text.lower()]
        if len(exact) == 1:
            return Resolved("ok", exact[0])
        key = text.lower()
        named = self._index.get(key, set())
        shares_first_name = self._firsts.get(key, set())
        if named or shares_first_name:
            if len(named) == 1 and not shares_first_name - named:
                return Resolved("ok", next(iter(named)))
            return self._by_context(named | shares_first_name)
        return self._by_fragment(text)

    def _by_context(self, candidates: set[str]) -> Resolved:
        """Candidates for a name nobody explicitly owns: the one that is in context, else a choice for the PM."""
        here = candidates & self.in_context
        if len(here) == 1:
            return Resolved("ok", next(iter(here)))
        return Resolved("ambiguous", candidates=tuple(sorted(candidates)))

    def _by_fragment(self, text: str) -> Resolved:
        """A first name with a surname fragment or an initial ("Ada L."): the people it fits. Nobody it fits means a
        different person, never the one who only shares the first name, so the PM chooses."""
        words = text.replace(".", " ").split()
        if len(words) < 2:
            return Resolved("unknown")
        same_first = self._firsts.get(words[0].lower(), set())
        if not same_first:
            return Resolved("unknown")
        fragment = " ".join(words[1:]).lower()
        fits = {pid for pid in same_first if _rest_of(self.records[pid]["full_name"]).startswith(fragment)}
        if not fits:
            return Resolved("ambiguous", candidates=tuple(sorted(same_first)))
        return self._by_context(fits) if len(fits) > 1 else Resolved("ok", next(iter(fits)))

    def match_entries(self, entries: Iterable[str]) -> set[str]:
        """The people that header entries (`Name <address>`, a name or an address) are: by an address a person can be
        reached at, else by a full name or an alias that is one person's. A first name that no one has set as an alias
        matches no one."""
        found: set[str] = set()
        addresses = {
            value.strip().lower(): pid
            for pid, data in self.records.items()
            for value in data.get("how_to_reach", {}).values()
            if "@" in value
        }
        for entry in entries:
            label, address = _parts(entry)
            if address.strip().lower() in addresses:
                found.add(addresses[address.strip().lower()])
                continue
            for written in (label, address):
                pids = self._named.get(" ".join(written.split()).lower(), set())
                if len(pids) == 1:
                    found |= pids
                    break
        return found

    def _input_people(self, store: Store, request_id: str, text: str) -> frozenset[str]:
        view = store.read()
        request = view.get("request", request_id)
        if request is None:
            return frozenset()
        source = view.get("source", request.data["source"]) if request.data.get("source") else None
        entries = header_entries(text)
        watched = source.data.get("watched") if source is not None else None
        if watched:
            snapshot = next(iter(view.find("snapshot", {"source": watched["source"], "key": watched["key"]})), None)
            message = (snapshot.data.get("message") if snapshot is not None else None) or {}
            entries += [e for e in [message.get("sender"), *message.get("participants", [])] if e]
        found = self.match_entries(entries)
        projects = {request.data.get("project"), *(source.data.get("projects", []) if source is not None else [])}
        for project_id in projects - {None}:
            project = view.get("project", project_id)
            if project is None:
                continue
            if project.data.get("owner"):
                found.add(project.data["owner"])
            for action in view.find("action", {"project": project_id}):
                found |= {o["person"] for o in action.data.get("owners", []) if o.get("person")}
        return frozenset(found & set(self.records))

    def name(self, pid: str | None) -> str:
        if pid is None:
            return ""
        data = self.records.get(pid)
        return data["full_name"] if data else pid

    def first_name(self, pid: str) -> str:
        full = self.name(pid)
        return full.split()[0] if full else full


def _rest_of(full_name: str) -> str:
    """A full name without its first word, lower case and without periods, for matching a fragment."""
    return " ".join(full_name.replace(".", " ").split()[1:]).lower()
