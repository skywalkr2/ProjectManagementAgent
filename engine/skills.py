"""The skills a run can get right or wrong (design 6.16, "What a model can do, measured").

The core ships the list as data (`engine/defaults/skills.yaml`): an id, a label in plain words and a description. Every
evaluation case, learning pair and scenario names the skills it proves with `skills:`, and a name that isn't on the list
is refused. A pack adds its own skills with `merge`; the list the screens and the checks read is `skills()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.yaml_load import load_yaml

DEFAULTS = Path(__file__).parent / "defaults" / "skills.yaml"


@dataclass(frozen=True)
class Skill:
    id: str
    label: str
    description: str


def core_skills() -> list[Skill]:
    """The skills the core ships, in the order of the file."""
    data = load_yaml(DEFAULTS.read_text(encoding="utf-8")) or {}
    return [
        Skill(str(entry["id"]), str(entry["label"]), str(entry.get("description", "")))
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
