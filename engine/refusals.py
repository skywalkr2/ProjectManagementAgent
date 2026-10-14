"""Refusals counted per check, and the seed lessons they bring into a packet (design 6.6, 6.22).

The applier records, on each changeset, the checks that refused each of its ops. A run of a task kind is a request that
the assistant answered with a changeset. The share of a check is how many of the task kind's last `of_last` runs it
refused at least once, over the runs counted. A check whose share reaches `knowledge.refusals_to_packet.share` has its
seed lesson (`engine/defaults/invariants.yaml`) added to that task kind's stable section, marked as the product's own
guidance, in the order the file lists the checks.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from engine import invariants
from engine.config.schema import KnowledgeSettings

HEADING = "# Where this kind of work often goes wrong"
MARK = "(the product's own guidance)"


class Seeded(NamedTuple):
    text: str
    ids: list[str]  # SEED-<check> for each lesson given, in the order given


def seed_id(check: str) -> str:
    return f"SEED-{check}"


def recent_runs(view: Any, task_kind: str, of_last: int) -> list[Any]:
    """The task kind's last `of_last` assistant runs that produced a changeset, oldest first."""
    requests = [r for r in view.find("request", {"task": task_kind}) if r.data.get("changeset")]
    runs = [c for r in requests if (c := view.get("changeset", r.data["changeset"])) is not None and c.data.get("run")]
    return runs[-of_last:] if of_last > 0 else []


def _refused_by(changeset: Any) -> set[str]:
    """The names of the checks that refused something in a changeset."""
    problems = [*changeset.data.get("problems", [])]
    for outcome in changeset.data.get("ops", []):
        problems += outcome.get("problems", [])
    return {p["check"] for p in problems if p.get("severity") == "refuse" and p.get("check")}


def refusal_shares(view: Any, task_kind: str, of_last: int) -> dict[str, float]:
    """For each check that refused any of the task kind's last `of_last` runs, the share of those runs it refused."""
    runs = recent_runs(view, task_kind, of_last)
    counts: dict[str, int] = {}
    for run in runs:
        for name in _refused_by(run):
            counts[name] = counts.get(name, 0) + 1
    return {name: count / len(runs) for name, count in sorted(counts.items())}


def seed_section(
    view: Any,
    task_kind: str,
    settings: KnowledgeSettings,
    known: dict[str, invariants.Invariant] | None = None,
) -> Seeded:
    """The seed lessons of the checks that refuse the task kind's runs at or above the configured share. Nothing for a
    check with no seed lesson, or that refused no run."""
    limits = settings.refusals_to_packet
    shares = refusal_shares(view, task_kind, limits.of_last)
    lessons = [
        i
        for i in (known if known is not None else invariants.load()).values()
        if i.seed and shares.get(i.name, 0) > 0 and shares[i.name] >= limits.share - 1e-9
    ]
    if not lessons:
        return Seeded("", [])
    lines = [f"- {seed_id(i.name)}: {i.seed} {MARK}" for i in lessons]
    return Seeded("\n".join([HEADING, *lines]), [seed_id(i.name) for i in lessons])
