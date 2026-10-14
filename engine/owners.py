"""A suggestion for an action that has no owner (design 6.9, 6.22): who the workspace's own routing entries say does
that kind of work, and the open action it most nearly repeats.

Plain functions over the records, with no AI. The held "Pick an owner" item shows the result; the person still picks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.applier import _similar
from engine.knowledge_section import (
    _active,
    _covers_task,
    _id_key,
    _in_scope_of_projects,
    _overlap_words,
    _scope,
    with_ancestors,
)


@dataclass(frozen=True)
class OwnerSuggestion:
    """`person` is the suggested owner, `entry` the routing entry that says so and `why` its own words. `fold_into` is
    the id of the open action this one most nearly repeats, and `fold_into_text` its text."""

    person: str | None = None
    entry: str | None = None
    why: str | None = None
    fold_into: str | None = None
    fold_into_text: str | None = None

    def shown(self, people: Any) -> dict[str, Any]:
        """The suggestion as plain data for a screen, with the suggested person's name as `people` writes it."""
        return {
            "person": self.person,
            "person_name": people.name(self.person) if self.person else None,
            "entry": self.entry,
            "why": self.why,
            "fold_into": self.fold_into,
            "fold_into_text": self.fold_into_text,
        }


def _routed(view: Any, cfg: Any, action: Any) -> tuple[Any, float] | None:
    """The active routing entry whose topic the action's words hold most of, when that is at least the configured
    share: one that names a person, isn't a "doesn't answer this", and whose scope covers the action's project."""
    words = _overlap_words(action.data["text"])
    scoped = set(with_ancestors(view, [action.data["project"]] if action.data.get("project") else []))
    needed = cfg.checks.tuning.owner_suggestion.match
    best: tuple[Any, float] | None = None
    for entry in _active(view, "routing_entry"):
        data = entry.data
        if data.get("negative") or not data.get("person") or view.get("person", data["person"]) is None:
            continue
        scope = _scope(entry)
        if not _covers_task(scope, "notes") or not _in_scope_of_projects(scope, scoped):
            continue
        topic = _overlap_words(data["topic"])
        share = len(topic & words) / len(topic) if topic else 0.0
        if share == 0 or share < needed:
            continue
        if best is None or (-share, _id_key(entry.id)) < (-best[1], _id_key(best[0].id)):
            best = (entry, share)
    return best


def _nearest(view: Any, cfg: Any, action: Any) -> Any | None:
    """The open action, other than this one, whose words are as alike as a near-duplicate action's (the same
    setting), the most alike first."""
    needed = cfg.checks.tuning.near_duplicate_action.similarity
    best: tuple[float, Any] | None = None
    for other in view.list("action"):
        if other.id == action.id or other.data["status"] != "open":
            continue
        score = _similar(action.data["text"], other.data["text"])
        if score >= needed and (best is None or score > best[0]):
            best = (score, other)
    return best[1] if best else None


def suggest_owner(view: Any, cfg: Any, action_id: str) -> OwnerSuggestion | None:
    """What to suggest for the action with this id, or None when the action isn't there or nothing applies."""
    action = view.get("action", action_id)
    if action is None:
        return None
    routed = _routed(view, cfg, action)
    near = _nearest(view, cfg, action)
    if routed is None and near is None:
        return None
    return OwnerSuggestion(
        person=routed[0].data["person"] if routed else None,
        entry=routed[0].id if routed else None,
        why=routed[0].data["text"] if routed else None,
        fold_into=near.id if near else None,
        fold_into_text=near.data["text"] if near else None,
    )
