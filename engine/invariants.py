"""The core's invariants as data (design 6.6, 6.7): for each check that always refuses an op, the one plain line the op
reference shows, the ops it constrains and the seed lesson that joins a packet when the check refuses often.

The data is `engine/defaults/invariants.yaml`. This module only reads it; the applier decides what is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

INVARIANTS_FILE = Path(__file__).parent / "defaults" / "invariants.yaml"

#: The value of `ops` for a check that constrains every op.
EVERY_OP = "any"


@dataclass(frozen=True)
class Invariant:
    name: str
    line: str  # the one line of what it refuses
    ops: tuple[str, ...] | None  # the ops it constrains; None for every op
    seed: str  # the fuller guidance given to runs that keep tripping it


def parse(raw: dict[str, Any]) -> dict[str, Invariant]:
    """The invariants a mapping describes, in its order. A malformed entry raises ValueError saying which."""
    found: dict[str, Invariant] = {}
    for name, entry in (raw or {}).items():
        if not isinstance(entry, dict):
            raise ValueError(f"{name}: expected a line, the ops it constrains and a seed lesson")
        ops = entry.get("ops", [])
        if ops != EVERY_OP and not (isinstance(ops, list) and all(isinstance(op, str) for op in ops)):
            raise ValueError(f"{name}: ops must be a list of op names, or {EVERY_OP}")
        found[name] = Invariant(
            name,
            " ".join(str(entry.get("line", "")).split()),
            None if ops == EVERY_OP else tuple(ops),
            " ".join(str(entry.get("seed", "")).split()),
        )
    return found


@lru_cache(maxsize=1)
def load() -> dict[str, Invariant]:
    """The shipped invariants, by check name, in the order the file lists them."""
    raw = yaml.safe_load(INVARIANTS_FILE.read_text(encoding="utf-8")) or {}
    return parse(raw.get("invariants", {}))


def lines_for(op: str, invariants: dict[str, Invariant] | None = None) -> list[str]:
    """The one-line constraints of the invariants that name this op, in the file's order."""
    return [i.line for i in (invariants or load()).values() if i.ops is not None and op in i.ops and i.line]


def lines_for_every_op(invariants: dict[str, Invariant] | None = None) -> list[str]:
    """The one-line constraints of the invariants that apply to every op."""
    return [i.line for i in (invariants or load()).values() if i.ops is None and i.line]
