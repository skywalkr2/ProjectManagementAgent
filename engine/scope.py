"""The scope slice (design 6.18): the person's part in each project, and the two checks that follow from it.

A project carries each person's part in it: they run it, design for it, or only watch it. A person with no entry runs
it. On a project the person only watches, the assistant records facts: an action or a question for anyone else is
returned once to be recorded as a fact, and held if it comes back. An action whose owners are all outside the person's
team is the same kind of item on any project, unless the words it quotes show the person owes it something.
"""

from __future__ import annotations

import re
from typing import Any

from engine.ops import ActionAddOp, OpModel, QuestionAddOp
from engine.records import PROJECT_ROLES

#: The checks that return an item once and hold it if it comes back, whoever the item reaches.
HELD_LINTS = frozenset({"watched-project", "other-team-item", "stance"})
#: The part a person has on a project that gives them none.
DEFAULT_ROLE = "run"


def role_of(view: Any, project_id: str | None, person_id: str | None) -> str:
    """The person's part in the project (run, design or watch); a project or person with no entry is run."""
    project = view.get("project", project_id) if project_id else None
    if project is None or person_id is None:
        return DEFAULT_ROLE
    for entry in project.data.get("roles") or []:
        if entry.get("person") == person_id and entry.get("role") in PROJECT_ROLES:
            return entry["role"]
    return DEFAULT_ROLE


def findings(op: OpModel, view: Any, people: Any, language: Any, project_id: str | None) -> list[tuple[str, str]]:
    """The scope checks an op fails, each as (check name, message in plain words). Only an action or a question for
    someone else is looked at; facts, notes and calendar entries never are. `language` is the workspace's wording
    settings, which say what shows the person owes an item something."""
    pm = people.pm
    if pm is None or not isinstance(op, (ActionAddOp, QuestionAddOp)):
        return []
    if isinstance(op, QuestionAddOp):
        others = people.resolve(op.to).person != pm
        noun = "a question"
    else:
        resolved = [people.resolve(name) for name in op.owners]
        others = any(r.status != "ok" or r.person != pm for r in resolved)
        noun = "an action"
    if others and role_of(view, project_id, pm) == "watch":
        name = view.get("project", project_id).data["name"]
        return [
            (
                "watched-project",
                f"you only watch {name}, so {noun} for someone else isn't made there: record it as a fact",
            )
        ]
    if isinstance(op, ActionAddOp) and _another_teams(op, view, people) and not _owed(op, view, people, language):
        return [
            (
                "other-team-item",
                "everyone this action is for is on another team: record it as a fact, unless the input says you owe "
                "it something",
            )
        ]
    return []


def _team_of(people: Any, person_id: str) -> str | None:
    team = people.records.get(person_id, {}).get("team")
    return team if isinstance(team, str) and team else None


def _inside(view: Any, people: Any, team: str, person_id: str) -> bool:
    """Whether a person is in a team, by their own record or by the team's list of members."""
    if _team_of(people, person_id) == team:
        return True
    record = view.get("team", team)
    return record is not None and person_id in (record.data.get("members") or [])


def _another_teams(op: ActionAddOp, view: Any, people: Any) -> bool:
    """Whether the person has a team and every owner is a known person outside it."""
    team = _team_of(people, people.pm)
    if team is None or not op.owners:
        return False
    owners = [people.resolve(name) for name in op.owners]
    return all(r.status == "ok" and r.person is not None and not _inside(view, people, team, r.person) for r in owners)


def _owed(op: ActionAddOp, view: Any, people: Any, language: Any) -> bool:
    """Whether the words an action quotes are a request addressed to the person: a word of `owed_words`, or the
    person's name or their team's followed by a request word, or a promise made to the person."""
    if any(people.resolve(name).person == people.pm for name in op.promised_to):
        return True
    quote = op.evidence.quote
    if any(_has_word(quote, word) for word in language.owed_words if word):
        return True
    pm = people.records.get(people.pm, {})
    names = [pm.get("full_name"), pm.get("first_name"), *(pm.get("aliases") or [])]
    full = (pm.get("full_name") or "").split()
    names += full[:1]
    team_id = _team_of(people, people.pm)
    team = view.get("team", team_id) if team_id else None
    if team is not None:
        names += [team.data.get("name"), *(team.data.get("aliases") or [])]
    return any(_addressed(quote, name, language.request_words) for name in names if name)


def _addressed(quote: str, name: str, request_words: list[str]) -> bool:
    """Whether a request word comes right after the name, with at most a comma, colon or dash between."""
    words = "|".join(re.escape(w.strip()) for w in request_words if w.strip())
    if not words:
        return False
    pattern = r"(?<!\w)" + re.escape(name.strip()) + rf"\s*[,:;-]?\s*(?:{words})(?!\w)"
    return re.search(pattern, quote, re.IGNORECASE) is not None


def _has_word(text: str, word: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(word.strip()) + r"(?!\w)", text, re.IGNORECASE) is not None


def stance_of(view: Any, steward: Any, person_id: str | None) -> str:
    """Who a person is to the person (design 6.34): their own stance, watch for someone marked track_only, else the
    workspace's default."""
    record = view.get("person", person_id) if person_id else None
    if record is None:
        return steward.default_stance
    if record.data.get("stance"):
        return record.data["stance"]
    return "watch" if record.data.get("track_only") else steward.default_stance


def stance_findings(op: OpModel, view: Any, people: Any, steward: Any) -> list[tuple[str, str]]:
    """What a question to someone else may ask, by who they are to the person and what the person tracks (design
    6.34): nothing to someone they only watch or report to (unless the person asks for it), nothing about something
    the person doesn't track, no design questions to someone they work alongside, and a mistake only with links to
    both sides of what it contradicts."""
    if not isinstance(op, QuestionAddOp):
        return []
    resolved = people.resolve(op.to)
    if resolved.status != "ok" or resolved.person is None or resolved.person == people.pm:
        return []
    name = people.name(resolved.person)
    stance = stance_of(view, steward, resolved.person)
    tracked = {"date": "dates", "decision": "decisions", "design": "design"}.get(op.asks_about)
    if stance == "watch":
        return [("stance", f"you only watch {name}, so nothing is drafted to them: record what you learned as a fact")]
    if stance == "report_to":
        return [("stance", f"you report to {name}, so a question to them is drafted only when you ask for one")]
    if tracked is not None and tracked not in steward.tracks:
        return [("stance", f"you don't track {tracked}, so this isn't asked: record it as a fact if it matters")]
    if stance == "alongside" and op.asks_about == "design":
        return [("stance", f"you work alongside {name}, so how they do their own work isn't yours to ask about")]
    if op.asks_about == "mistake" and len(op.links) < 2:
        return [("stance", "a possible mistake links both sides: what it contradicts and where it was said")]
    return []
