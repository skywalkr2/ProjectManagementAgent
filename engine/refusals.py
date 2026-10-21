"""Refusals counted per check, and the seed lessons they bring into a packet (design 6.6, 6.22).

The applier records, on each changeset, the checks that refused each of its ops. A run of a task kind is a request that
the assistant answered with a changeset. The share of a check is how many of the task kind's last `of_last` runs it
refused at least once, over the runs counted. Refusals a fix round repaired count too: each call's knowledge log names
the checks that refused its answer. Below `min_runs` runs counted, no seed lesson is given. A check whose share reaches
the configured share has its seed lesson (`engine/defaults/invariants.yaml`) added to that task kind's stable section,
marked as the product's own guidance, in the order the file lists the checks. The floor is for rare work: a check that
refused `floor` runs of the task kind within `floor_days` days brings its seed lesson in whatever the share and however
few runs are counted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
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


def recent_runs(view: Any, task_kind: str, of_last: int) -> list[tuple[Any, Any]]:
    """The task kind's last `of_last` assistant runs that produced a changeset, oldest first, each as its request and
    changeset."""
    pairs = [
        (r, c)
        for r in view.find("request", {"task": task_kind})
        if r.data.get("changeset")
        and (c := view.get("changeset", r.data["changeset"])) is not None
        and c.data.get("run")
    ]
    return pairs[-of_last:] if of_last > 0 else []


def _refused_by(view: Any, request: Any, changeset: Any) -> set[str]:
    """The names of the checks that refused something in one run: those on the changeset it ended with, and those
    every call made for the request recorded in its knowledge log, which includes refusals a fix round repaired."""
    problems = [*changeset.data.get("problems", [])]
    for outcome in changeset.data.get("ops", []):
        problems += outcome.get("problems", [])
    names = {p["check"] for p in problems if p.get("severity") == "refuse" and p.get("check")}
    for call in view.find("run", {"request": request.id}):
        names.update((call.data.get("knowledge") or {}).get("refused_checks", []))
    return names


def counted(view: Any, task_kind: str, of_last: int) -> tuple[dict[str, int], int]:
    """For each check that refused any of the task kind's last `of_last` runs, how many it refused, and how many runs
    were counted."""
    runs = recent_runs(view, task_kind, of_last)
    counts: dict[str, int] = {}
    for request, changeset in runs:
        for name in _refused_by(view, request, changeset):
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items())), len(runs)


def refusal_shares(view: Any, task_kind: str, of_last: int) -> dict[str, float]:
    """For each check that refused any of the task kind's last `of_last` runs, the share of those runs it refused."""
    counts, runs = counted(view, task_kind, of_last)
    return {name: count / runs for name, count in counts.items()}


def _in_window(stamp: Any, today: date, days: int, here: Any) -> bool:
    """Whether a run made at `stamp` falls in the `days` days that end on `today`, both the person's own days."""
    from engine.today import local_day

    try:
        day = local_day(datetime.fromisoformat(str(stamp)), here)
    except ValueError:
        return False
    return today - timedelta(days=days) < day <= today


def floor_counts(view: Any, task_kind: str, settings: KnowledgeSettings, today: date, here: Any) -> dict[str, int]:
    """For each check that refused the task kind's runs in the last `floor_days` days, how many of those runs it
    refused (the runs of any age are looked at, not only the last `of_last`)."""
    limits = settings.refusals_to_packet
    counts: dict[str, int] = {}
    for request, changeset in recent_runs(view, task_kind, len(view.find("request", {"task": task_kind}))):
        if not _in_window(changeset.data.get("created_at"), today, limits.floor_days, here):
            continue
        for name in _refused_by(view, request, changeset):
            counts[name] = counts.get(name, 0) + 1
    return counts


def seed_section(
    view: Any,
    task_kind: str,
    settings: KnowledgeSettings,
    known: dict[str, invariants.Invariant] | None = None,
    today: date | None = None,
    here: Any = None,
) -> Seeded:
    """The seed lessons of the checks that refuse the task kind's runs at or above the configured share. Nothing for a
    check with no seed lesson, or that refused no run, and nothing until `min_runs` runs are counted. With `today`, a
    check that refused the task kind's runs `floor` times in the last `floor_days` days also has its lesson given,
    whatever the share and the number of runs counted."""
    limits = settings.refusals_to_packet
    counts, runs = counted(view, task_kind, limits.of_last)
    shares = {name: count / runs for name, count in counts.items()} if runs >= limits.min_runs else {}
    floor = floor_counts(view, task_kind, settings, today, here) if today is not None else {}
    lessons = [
        i
        for i in (known if known is not None else invariants.load()).values()
        if i.seed
        and (
            (shares.get(i.name, 0) > 0 and shares[i.name] >= limits.share - 1e-9)
            or floor.get(i.name, 0) >= limits.floor
        )
    ]
    if not lessons:
        return Seeded("", [])
    lines = [f"- {seed_id(i.name)}: {i.seed} {MARK}" for i in lessons]
    return Seeded("\n".join([HEADING, *lines]), [seed_id(i.name) for i in lessons])
