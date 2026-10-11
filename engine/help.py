"""The material an ask is answered from (design 6.25): sections of the user guide chosen for the question, the
workspace's settings without anything secret, and what this install can do. Every line here may be quoted as the
words an answer rests on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GUIDE = Path(__file__).parent / "guide" / "guide.md"
#: Setting keys never put in a packet: where keys come from is nobody's business but the person's.
PRIVATE_KEYS = re.compile(r"(^|\.)(auth|key_env|pass_env|token|secret)s?($|\.)")
_WORD = re.compile(r"[a-z0-9]+")
#: Words too common to say what a question is about.
_COMMON = frozenset(
    line.strip()
    for line in (Path(__file__).parent / "guide" / "common-words.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)


@dataclass(frozen=True)
class Section:
    title: str
    text: str


def guide_sections(path: Path = GUIDE) -> list[Section]:
    """The user guide, one section per `##` heading."""
    found: list[Section] = []
    title, lines = "", []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if title:
                found.append(Section(title, "\n".join(lines).strip()))
            title, lines = line[3:].strip(), []
        elif title:
            lines.append(line)
    if title:
        found.append(Section(title, "\n".join(lines).strip()))
    return found


def _stem(word: str) -> str:
    """A word without a common ending, so "closing", "closed" and "closes" match "close"."""
    for ending in ("ing", "ed", "es", "s", "e"):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def _words(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _COMMON and len(w) > 2}


def chosen_sections(question: str, limit: int = 4, sections: list[Section] | None = None) -> list[Section]:
    """The sections that share the most words with the question (the title counting double), best first; the
    overview when nothing matches."""
    sections = guide_sections() if sections is None else sections
    asked = _words(question)
    scored = []
    for position, section in enumerate(sections):
        score = 2 * len(asked & _words(section.title)) + len(asked & _words(section.text))
        if score:
            scored.append((-score, position, section))
    picked = [s for _, _, s in sorted(scored)[:limit]]
    return picked or sections[:1]


def settings_lines(cfg: Any) -> list[str]:
    """One line per setting the screens show: its key, current value, default, whether the screens can change it,
    and what it does. Nothing that says where a key comes from."""
    from engine import settings as config_screens

    lines = []
    for item in config_screens.describe(cfg):
        if PRIVATE_KEYS.search(item.key) or item.type == "other":
            continue
        change = "changeable" if item.editable else "locked" if item.locked else f"changed in {item.file}.yaml"
        lines.append(
            f"{item.key} = {json.dumps(item.value, ensure_ascii=False)} (default {json.dumps(item.default)}, "
            f"{change}): {item.description}"
        )
    return lines


def capability_lines(store: Any) -> list[str]:
    """What this install can do: the kinds of work, actions, screens and setup steps each running add-on offers."""
    from engine.records import kind_label

    lines = []
    for name, status in sorted(store.plugins.status.items()):
        if status.state != "enabled":
            lines.append(f"Add-on {name} is turned off: {status.reason or 'no reason given'}")
            continue
        registrar = store.plugins.registrars.get(name)
        if registrar is None:
            continue
        parts = [
            ("kinds of AI work", [store.plugins.task_kind(t).label or t for t in sorted(registrar.tasks)]),
            ("actions", [a.label for a in registrar.actions.values()]),
            ("screens", [p.title for p in registrar.panels.values()]),
            ("setup steps", [s.label for s in registrar.setup_steps.values()]),
            ("item types", [kind_label(model, kind) for kind, model in sorted(registrar.records.items())]),
        ]
        offered = "; ".join(f"{label}: {', '.join(items)}" for label, items in parts if items)
        lines.append(f"Add-on {name} is on" + (f". It offers {offered}." if offered else "."))
    return lines or ["No add-ons are installed."]
