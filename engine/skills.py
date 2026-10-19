"""The skills a run can get right or wrong (design 6.16, "What a model can do, measured").

The core ships the list as data (`engine/defaults/skills.yaml`): an id, a label in plain words and a description. Every
evaluation case, learning pair and scenario names the skills it proves with `skills:`, and a name that isn't on the list
is refused. A pack adds its own skills with `merge`; the list the screens and the checks read is `skills()`.

A case, pair or scenario may also say the data level its material carries (`data_level:`, one of the levels an account's
`allowed_data` names); it defaults to the level a handed-in note carries. Measuring an account runs only the ones it is
allowed to see (`within_level`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.ai.router import LEVELS
from engine.yaml_load import load_yaml

DEFAULTS = Path(__file__).parent / "defaults" / "skills.yaml"


@dataclass(frozen=True)
class Skill:
    id: str
    label: str
    description: str
    #: Measurable facts about a request that make this skill matter (the parts of a routing rule's `when`), when the
    #: skill is only at risk on some requests; a skill with none is needed by every request of its kind of work.
    route_when: dict[str, int] = field(default_factory=dict, hash=False, compare=False)


def core_skills() -> list[Skill]:
    """The skills the core ships, in the order of the file."""
    data = load_yaml(DEFAULTS.read_text(encoding="utf-8")) or {}
    return [
        Skill(
            str(entry["id"]),
            str(entry["label"]),
            str(entry.get("description", "")),
            {str(k): int(v) for k, v in (entry.get("route_when") or {}).items()},
        )
        for entry in data.get("skills") or []
    ]


def merge(base: list[Skill], more: list[Skill]) -> list[Skill]:
    """`base` with the skills of `more` added; a skill already there (by id) keeps its first label and description."""
    seen = {s.id for s in base}
    return [*base, *(s for s in more if s.id not in seen and not seen.add(s.id))]


def skills(extra: list[Skill] | None = None) -> list[Skill]:
    """Every skill known: the core's, then any a pack adds."""
    return merge(core_skills(), extra or [])


def known(extra: list[Skill] | None = None) -> set[str]:
    return {s.id for s in skills(extra)}


def check_named(where: str, value: Any, *, required: bool = False) -> list[str]:
    """The skills a case names (`skills:`), as a list of ids. Raises ValueError saying what is wrong: not a list of
    names, an unknown skill, or (when `required`) none at all."""
    if value is None:
        if required:
            raise ValueError(f"{where}: name the skills it proves with skills: [ids from engine/defaults/skills.yaml]")
        return []
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{where}: skills is a list of skill ids, at least one")
    unknown = sorted(set(value) - known())
    if unknown:
        raise ValueError(f"{where}: unknown skill {', '.join(unknown)} (the list is engine/defaults/skills.yaml)")
    return list(dict.fromkeys(value))


#: The level of an item that says none (a handed-in note's).
DEFAULT_LEVEL = "internal"


def check_level(where: str, value: Any) -> str:
    """The data level a case names (`data_level:`), or the default when it names none. Raises ValueError saying what
    is wrong."""
    if value is None:
        return DEFAULT_LEVEL
    if value not in LEVELS:
        raise ValueError(f"{where}: data_level is one of {', '.join(LEVELS)}")
    return str(value)


def within_level(item: dict[str, Any], most_private: str | None) -> bool:
    """Whether a case, pair or scenario may run on an account whose most private allowed level is `most_private`
    (None: no limit)."""
    if most_private is None:
        return True
    return LEVELS.index(check_level("data_level", item.get("data_level"))) <= LEVELS.index(most_private)
