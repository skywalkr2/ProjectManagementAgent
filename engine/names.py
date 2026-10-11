"""Name resolution at the boundary (design 6.11): names become person ids once, where they come in.

An id passes. A full name or alias that matches one person becomes that id. The PM's aliases become the PM. A first
name only one person has becomes that person. Anything else is ambiguous or unknown, and the op waits for the PM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from engine.config import Config
from engine.storage import Store


@dataclass(frozen=True)
class Resolved:
    status: Literal["ok", "ambiguous", "unknown"]
    person: str | None = None
    candidates: tuple[str, ...] = ()


class People:
    def __init__(self, store: Store, cfg: Config):
        self.records = {p.id: p.data for p in store.read().list("person")}
        self.pm = cfg.workspace.user.person
        self._index: dict[str, set[str]] = {}
        for pid, data in self.records.items():
            names = [data["full_name"], *data.get("aliases", [])]
            first = data["full_name"].split()[0] if data["full_name"].split() else ""
            for name in [*names, first]:
                if name:
                    self._index.setdefault(name.lower(), set()).add(pid)
        if self.pm:
            for alias in ["me", "myself", "I"]:
                if alias:
                    self._index[alias.lower()] = {self.pm}

    def resolve(self, name: str) -> Resolved:
        text = name.strip()
        if text in self.records:
            return Resolved("ok", text)
        exact = [pid for pid, d in self.records.items() if d["full_name"].lower() == text.lower()]
        if len(exact) == 1:
            return Resolved("ok", exact[0])
        matches = self._index.get(text.lower(), set())
        if len(matches) == 1:
            return Resolved("ok", next(iter(matches)))
        if len(matches) > 1:
            return Resolved("ambiguous", candidates=tuple(sorted(matches)))
        return Resolved("unknown")

    def name(self, pid: str | None) -> str:
        if pid is None:
            return ""
        data = self.records.get(pid)
        return data["full_name"] if data else pid

    def first_name(self, pid: str) -> str:
        full = self.name(pid)
        return full.split()[0] if full else full
