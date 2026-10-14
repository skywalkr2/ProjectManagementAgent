"""The review of standing rules (design 6.22): which active rules were given to runs and never applied, and how large
the always-sent section is.

Plain functions over a read of the records, with no AI. Each run's knowledge log says, for every rule it was given,
whether it applied or was only present (engine/rule_use.py). A rule is flagged when, over the review window, it was
present at least once and applied never, and no code check enforces it: a check holds a rule whether or not anything
triggers it. A rule is old enough to be flagged only once the review window has passed since it was learned or last
kept, so keeping a rule starts its count again. The Today line built from this is offered at most once a period,
counted from the last time the person kept, narrowed or retired a rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from engine.config.schema import KnowledgeSettings
from engine.records import Rule

#: What the person does to a rule in the review, as the signals that record it.
ACTS = ("kept", "narrowed", "retired")


@dataclass(frozen=True)
class FlaggedRule:
    id: str
    name: str
    text: str
    version: int
    present: int  # runs in the window that were given the rule and did not show it applied
    applied: int  # runs in the window that showed it applied
    applies_to: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleReview:
    flagged: list[FlaggedRule]  # most present first
    stable_chars: int  # the always-sent section's size on the latest run
    stable_budget: int
    moved: int  # rules moved out of the always-sent part on the latest run
    days: int  # the review window

    @property
    def needed(self) -> bool:
        return bool(self.flagged) or self.moved > 0


def _at(stamp: Any) -> datetime | None:
    if not stamp:
        return None
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def review(view: Any, settings: KnowledgeSettings, now: datetime) -> RuleReview:
    """The rules to review at `now`, and the size of what is always sent."""
    start = now - timedelta(days=settings.rule_review_days)
    runs = []
    for run in view.list("run"):
        log = run.data.get("knowledge")
        began = _at(run.data.get("started_at"))
        if log and began is not None:
            runs.append((began, log))
    counts: dict[str, list[int]] = {}
    for began, log in runs:
        if began < start or began > now:
            continue
        for rule_id in log.get("rules_present", []):
            counts.setdefault(rule_id, [0, 0])[0] += 1
        for rule_id in log.get("rules_applied", []):
            counts.setdefault(rule_id, [0, 0])[1] += 1

    flagged = []
    for rule in view.list("rule"):
        data = rule.data
        if data.get("status") != "active" or data.get("check"):
            continue
        clock = max(filter(None, (_at(data.get("learned_at")), _at(data.get("reviewed_at")))), default=None)
        if clock is not None and clock > start:
            continue  # not yet a whole window since it was learned or last kept
        present, applied = counts.get(rule.id, [0, 0])
        if present and not applied:
            flagged.append(
                FlaggedRule(
                    rule.id,
                    data["name"],
                    data["text"],
                    rule.version,
                    present,
                    applied,
                    dict(data.get("applies_to") or {}),
                )
            )
    flagged.sort(key=lambda f: (-f.present, _number(f.id)))
    latest = max(runs, key=lambda pair: pair[0], default=None)
    log = latest[1] if latest else {}
    return RuleReview(
        flagged,
        int(log.get("stable_chars", 0)),
        settings.stable_budget,
        len(log.get("rules_moved", [])),
        settings.rule_review_days,
    )


def _number(record_id: str) -> int:
    tail = record_id.rpartition("-")[2]
    return int(tail) if tail.isdigit() else 0


def last_acted(view: Any) -> datetime | None:
    """When the person last kept, narrowed or retired a rule, from the signals those acts record."""
    prefix = f"{Rule.prefix}-"
    moments = [
        _at(s.data["at"])
        for s in view.list("signal")
        if s.data["kind"] in ACTS and any(ref.startswith(prefix) for ref in s.data.get("refs", []))
    ]
    return max((m for m in moments if m is not None), default=None)


def due(view: Any, settings: KnowledgeSettings, now: datetime, found: RuleReview | None = None) -> bool:
    """Whether the review is offered now: something is flagged or rules were moved, and the person hasn't acted on
    it within `rule_review_every_days`."""
    found = found if found is not None else review(view, settings, now)
    if not found.needed:
        return False
    acted = last_acted(view)
    return acted is None or now - acted >= timedelta(days=settings.rule_review_every_days)
