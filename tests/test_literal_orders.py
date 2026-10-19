"""Two `Literal` types with the same values in a different order may be cached as one object on newer Pythons, so the
order the generated plugin guide and API schema show would depend on import order and differ between Python versions.
Every set of literal values is written in one order."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LITERAL = re.compile(r'Literal\[((?:"[^"]*"\s*,\s*)+"[^"]*")\]')


def test_each_set_of_literal_values_is_written_in_one_order():
    orders: dict[frozenset[str], set[tuple[str, ...]]] = defaultdict(set)
    for folder in ("engine", "api"):
        for path in (ROOT / folder).rglob("*.py"):
            for found in _LITERAL.finditer(path.read_text(encoding="utf-8")):
                values = tuple(re.findall(r'"([^"]*)"', found.group(1)))
                orders[frozenset(values)].add(values)
    assert [sorted(o) for o in orders.values() if len(o) > 1] == []
