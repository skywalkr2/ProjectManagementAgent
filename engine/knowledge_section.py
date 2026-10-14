"""The knowledge section of a packet (design 6.22): what the workspace has learned, chosen for one run.

Plain functions over a snapshot of the records, with no AI. Two parts, so a provider's cached prefix holds from input
to input: `stable_section` is the same for every run of a task kind (standing rules for the whole workspace, lessons
for the task kind, the glossary while it is small) and carries no dates or counts; `per_input_section` depends on the
input (narrowed rules, lessons and glossary terms, routing, ranked facts). Scope is filtered here, never left to the
model: an entry whose scope excludes the input's projects is not in the text, and its id is returned so the run's
knowledge log can say so. Only active entries go in. An entry that came from outside content is shown as data with its
source, never as guidance.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from typing import Any, NamedTuple

from engine.config.schema import KnowledgeSettings
from engine.records import Scope

HEADINGS = {
    "rules": "# Standing rules",
    "lessons": "# Lessons",
    "glossary": "# Glossary",
    "input_rules": "# Standing rules for this input",
    "input_lessons": "# Lessons for this input",
    "routing": "# Who answers what",
    "input_glossary": "# Terms this input uses",
    "facts": "# Facts recorded for this input's projects",
}

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class Stable(NamedTuple):
    text: str
    ids: list[str]
    moved: list[str]  # rules moved to the per-input part because the section passed its size budget


class PerInput(NamedTuple):
    text: str
    ids: list[str]
    left_out_by_scope: list[str]
    facts_left_out: int


# ---- reading the records ---------------------------------------------------------------------------------------------


def _id_key(record_id: str) -> tuple[str, int, str]:
    """Order by id the way a person reads them: LES-2 before LES-10."""
    prefix, _, number = record_id.rpartition("-")
    return prefix, int(number) if number.isdigit() else 0, record_id


def _key(stored: Any) -> tuple[str, int, str]:
    return _id_key(stored.id)


def _active(view: Any, kind: str) -> list[Any]:
    return sorted((s for s in view.list(kind) if s.data.get("status") == "active"), key=_key)


def _scope(stored: Any) -> Scope:
    return Scope.model_validate(stored.data.get("applies_to") or {})


def _covers_task(scope: Scope, task_kind: str) -> bool:
    return not scope.task_kinds or task_kind in scope.task_kinds


def _whole_workspace(scope: Scope) -> bool:
    """Nothing narrows it by project, exclusion or person (task kinds are decided by each caller)."""
    return scope.scope == "workspace" and not scope.except_ and not scope.projects and not scope.people


def _in_scope_of_projects(scope: Scope, projects: set[str], also: str | None = None) -> bool:
    """False when the scope excludes every one of the input's projects: an `except` that names one of them, or a
    `projects` scope that doesn't include them. `also` is a project the entry itself names; it must be one of them."""
    if also is not None and also not in projects:
        return False
    if scope.scope == "projects":
        return bool(set(scope.projects) & projects)
    return not (set(scope.except_) & projects)


def with_ancestors(view: Any, projects: Iterable[str]) -> list[str]:
    """The projects and then every project above them (`Project.parent`, any depth), each once. A scope that names a
    project covers the projects below it, so scopes are matched against this list."""
    found: list[str] = []
    for project_id in projects:
        while project_id and project_id not in found:
            found.append(project_id)
            project = view.get("project", project_id)
            project_id = project.data.get("parent") if project is not None else None
    return found


def _about_these_people(scope: Scope, people: set[str]) -> bool:
    return not scope.people or bool(set(scope.people) & people)


# ---- how an entry is shown -------------------------------------------------------------------------------------------


def _marked(text: str) -> str:
    """Text that can't close the marking it sits in."""
    return text.replace("</untrusted", "</ untrusted")


def _origin_note(data: dict[str, Any]) -> str:
    if data.get("origin") != "pack":
        return ""
    return f" (pack guidance: {data['pack']})" if data.get("pack") else " (pack guidance)"


def _source_label(view: Any, data: dict[str, Any]) -> str:
    source_id = data.get("source") or (data.get("evidence") or {}).get("source")
    source = view.get("source", source_id) if source_id else None
    label = source.data["title"] if source is not None else source_id or data.get("origin") or "outside"
    return " ".join(str(label).split()).replace('"', "'")


def _shown(view: Any, stored: Any, line: str) -> str:
    """A line as guidance when its source is trusted, else as data with its source."""
    if stored.data.get("trust", "trusted") == "trusted":
        return line
    return f'<untrusted source="{_source_label(view, stored.data)}">\n{_marked(line)}\n</untrusted>'


def _section(view: Any, heading: str, lines: list[tuple[Any, str]]) -> str:
    """One heading, then the lines guidance gives, then each line from untrusted content on its own as data."""
    if not lines:
        return ""
    trusted = [line for stored, line in lines if stored.data.get("trust", "trusted") == "trusted"]
    data = [_shown(view, stored, line) for stored, line in lines if stored.data.get("trust", "trusted") != "trusted"]
    return "\n".join([heading, *trusted, *data])


def _rule_line(rule: Any, *, one_line: bool = False) -> str:
    data = rule.data
    lines = [line.strip() for line in data["text"].splitlines() if line.strip()]
    text = (lines[0] if one_line else " ".join(lines)) if lines else data["name"]
    return f"- {rule.id}: {text}{_origin_note(data)}"


def _entry_line(stored: Any) -> str:
    return f"- {stored.id}: {stored.data['text']}{_origin_note(stored.data)}"


def _term_line(stored: Any) -> str:
    return f"- {stored.data['term']}: {stored.data['meaning']}{_origin_note(stored.data)}"


# ---- the stable part -------------------------------------------------------------------------------------------------


def _stable_rule(scope: Scope, task_kind: str) -> bool:
    return _whole_workspace(scope) and scope.task_kinds in ([], [task_kind])


def _leaves_first(rule: Any, scope: Scope, task_kind: str) -> int:
    """How soon a rule leaves the always-sent part when it grows too large: rules for one task kind first, then
    workspace-wide rules from other sources, and the person's own workspace-wide rules last."""
    if scope.task_kinds == [task_kind]:
        return 0
    return 2 if rule.data.get("origin") == "person" else 1


def stable_section(view: Any, task_kind: str, settings: KnowledgeSettings) -> Stable:
    """The knowledge every run of this task kind is sent: active rules for the whole workspace, active lessons for
    the task kind, then the whole glossary while it has fewer terms than `glossary_all_below`. By id, with no dates or
    counts. A rule a stage check enforces is there as its one line only. Past `stable_budget`, rules leave one by one,
    narrowest first, and are returned in `moved` for the per-input part to carry."""
    rules = [(r, _scope(r)) for r in _active(view, "rule")]
    rules = [(r, s) for r, s in rules if _stable_rule(s, task_kind)]
    lessons = [s for s in _active(view, "lesson") if _whole_workspace(_scope(s)) and _covers_task(_scope(s), task_kind)]
    terms = [
        s
        for s in _active(view, "glossary_entry")
        if _whole_workspace(_scope(s)) and _covers_task(_scope(s), task_kind) and not s.data.get("project")
    ]
    if len(terms) >= settings.glossary_all_below:
        terms = []

    def build(kept: list[tuple[Any, Scope]]) -> str:
        rule_lines = [(r, _rule_line(r, one_line=bool(r.data.get("check")))) for r, _ in kept]
        return "\n\n".join(
            part
            for part in (
                _section(view, HEADINGS["rules"], rule_lines),
                _section(view, HEADINGS["lessons"], [(s, _entry_line(s)) for s in lessons]),
                _section(view, HEADINGS["glossary"], [(s, _term_line(s)) for s in terms]),
            )
            if part
        )

    kept = list(rules)
    text = build(kept)
    moved: list[str] = []
    # Newest first within a kind of rule, then the narrowest kind first; the sort is stable.
    order = sorted(
        sorted(rules, key=lambda pair: _key(pair[0]), reverse=True), key=lambda pair: _leaves_first(*pair, task_kind)
    )
    for pair in order:
        if len(text) <= settings.stable_budget:
            break
        kept.remove(pair)
        moved.append(pair[0].id)
        text = build(kept)
    ids = [r.id for r, _ in kept] + [s.id for s in lessons] + [s.id for s in terms]
    return Stable(text, ids, sorted(moved, key=_id_key))


# ---- the per-input part ----------------------------------------------------------------------------------------------


def _uses(term: str, text: str) -> bool:
    return bool(term.strip()) and re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", text, re.IGNORECASE) is not None


def _overlap_words(text: str) -> set[str]:
    """The words and ids of a text worth matching on: ids and long words, lower case."""
    return {w.lower() for w in _WORD.findall(text) if len(w) >= 4 or any(c.isdigit() for c in w)}


def per_input_section(
    view: Any,
    task_kind: str,
    projects: Iterable[str],
    people: Iterable[str],
    text: str,
    today: date,
    settings: KnowledgeSettings,
    moved: Iterable[str] = (),
    facts: bool = True,
    scope_projects: Iterable[str] | None = None,
) -> PerInput:
    """The knowledge that depends on the input: rules narrowed to some projects or task kinds that cover it, rules a
    stage check enforces (in full) and rules that moved out of the stable part; lessons for its projects or people;
    routing for its people and projects; the glossary terms it uses once the glossary is too large to send whole;
    then the facts of its projects, ranked and cut at `facts_budget`. `text` is the input's words, which decide the
    terms and rank the facts. Returns the text, the ids given, the ids left out by scope, and how many facts didn't
    fit. With `facts` False (work the core's learning doesn't run on) the facts are left out. Scopes are matched against
    `scope_projects` (the projects and their ancestors; the projects alone when None); facts stay per exact project."""
    project_set, people_set, moved_set = set(projects), set(people), set(moved)
    scoped = set(scope_projects) if scope_projects is not None else project_set
    ids: list[str] = []
    left_out: set[str] = set()
    sections: list[str] = []

    def passes(stored: Any, scope: Scope, also: str | None = None) -> bool:
        if not _covers_task(scope, task_kind):
            return False
        if (also is not None and also not in project_set) or not _in_scope_of_projects(scope, scoped):
            left_out.add(stored.id)
            return False
        return _about_these_people(scope, people_set)

    def add(heading: str, lines: list[tuple[Any, str]]) -> None:
        rendered = _section(view, heading, lines)
        if rendered:
            sections.append(rendered)
            ids.extend(stored.id for stored, _ in lines)

    rules = []
    for rule in _active(view, "rule"):
        scope = _scope(rule)
        if not passes(rule, scope):
            continue
        if not _stable_rule(scope, task_kind) or rule.data.get("check") or rule.id in moved_set:
            rules.append((rule, _rule_line(rule)))
    add(HEADINGS["input_rules"], rules)

    lessons = []
    for lesson in _active(view, "lesson"):
        scope = _scope(lesson)
        if passes(lesson, scope) and not _whole_workspace(scope):
            lessons.append((lesson, _entry_line(lesson)))
    add(HEADINGS["input_lessons"], lessons)

    teams = {
        t for pid in people_set if (person := view.get("person", pid)) is not None and (t := person.data.get("team"))
    }
    routing = []
    for entry in _active(view, "routing_entry"):
        scope = _scope(entry)
        if not passes(entry, scope):
            continue
        about_input = (
            entry.data.get("person") in people_set
            or (entry.data.get("team") is not None and entry.data["team"] in teams)
            or (scope.scope == "projects" and bool(set(scope.projects) & scoped))
        )
        if about_input:
            routing.append((entry, _entry_line(entry)))
    add(HEADINGS["routing"], routing)

    whole = {
        s.id
        for s in _active(view, "glossary_entry")
        if _whole_workspace(_scope(s)) and _covers_task(_scope(s), task_kind) and not s.data.get("project")
    }
    send_whole = len(whole) < settings.glossary_all_below
    terms = []
    for entry in _active(view, "glossary_entry"):
        scope = _scope(entry)
        if entry.id in whole:
            wanted = not send_whole and _uses(entry.data["term"], text)
        elif passes(entry, scope, entry.data.get("project")):
            # An entry for some projects goes with them; one only narrowed by an exclusion goes when its term is used.
            wanted = scope.scope == "projects" or bool(entry.data.get("project")) or _uses(entry.data["term"], text)
        else:
            wanted = False
        if wanted:
            terms.append((entry, _term_line(entry)))
    add(HEADINGS["input_glossary"], terms)

    fact_text, fact_ids, cut = (
        _facts_section(view, project_set, text, today, settings.facts_budget) if facts else ("", [], 0)
    )
    if fact_text:
        sections.append(fact_text)
        ids.extend(fact_ids)
    return PerInput("\n\n".join(sections), ids, sorted(left_out, key=_id_key), cut)


def _facts_section(view: Any, projects: set[str], text: str, today: date, budget: int) -> tuple[str, list[str], int]:
    """The input's projects' facts that no newer fact replaces, key facts first, then by how many of the input's words
    and ids they share, then newest; cut at `budget` characters with the count of those left out said."""
    facts = view.list("fact")
    replaced = {f.data["supersedes"] for f in facts if f.data.get("supersedes")}
    mine = [f for f in facts if f.data.get("project") in projects and f.id not in replaced]
    if not mine:
        return "", [], 0
    words = _overlap_words(text)

    def when(fact: Any) -> date | None:
        if fact.data.get("as_of"):
            return min(date.fromisoformat(str(fact.data["as_of"])), today)
        source = view.get("source", fact.data["source"]) if fact.data.get("source") else None
        return min(date.fromisoformat(str(source.data["received_at"])[:10]), today) if source is not None else None

    def rank(fact: Any) -> tuple:
        day = when(fact)
        _, number, _ = _key(fact)
        return (
            not fact.data.get("key"),
            -len(_overlap_words(fact.data["text"]) & words),
            day is None,
            -(day.toordinal() if day else 0),
            -number,
        )

    def line(fact: Any) -> str:
        day = when(fact)
        source = view.get("source", fact.data["source"]) if fact.data.get("source") else None
        bits = ([f"as of {day.isoformat()}"] if day else []) + ([f"from {source.data['title']}"] if source else [])
        return f"- {fact.id}: {fact.data['text']}" + (f" ({', '.join(bits)})" if bits else "")

    shown: list[tuple[Any, str]] = []
    used = len(HEADINGS["facts"])
    for fact in sorted(mine, key=rank):
        rendered = _shown(view, fact, line(fact))
        if used + len(rendered) + 1 > budget:
            break
        shown.append((fact, rendered))
        used += len(rendered) + 1
    cut = len(mine) - len(shown)
    lines = [HEADINGS["facts"], *(rendered for _, rendered in shown)]
    if cut:
        on = "this project" if len(projects) == 1 else "these projects"
        lines.append(f"- {cut} more {'fact' if cut == 1 else 'facts'} on {on}; ask to search for them")
    return "\n".join(lines), [f.id for f, _ in shown], cut
