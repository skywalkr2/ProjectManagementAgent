"""Quality figures (design 6.20, 6.13): how well the loop of correcting and learning is working.

Plain functions over a read of the records, with no AI.

- What an answer claims. A run's answer may list the knowledge ids it applied (`applied`) and what it needed that no op
  could do (`missing`). The dispatcher keeps on the changeset only the ids the run was given, and counts the rest.
- The knowledge-used rate, per kind of work: the runs that applied at least one entry over the runs that were given at
  least one. Only the run that made a changeset counts, so a fix round that never became one doesn't lower it.
- The repeat-correction rate, per kind of work and week: the corrections whose run had been given an active lesson or
  rule whose target matched the corrected item, over all the corrections of that kind of work that week. A week with
  fewer corrections than the configured minimum has no rate.
- Missed, declined and dropped, each counted on its own for each week; a drop is not a correction of the assistant and
  is not in the repeat-correction rate.
- The missing-op list: what runs said they lacked, grouped by wording, week by week.
- The first run on a fallback account, so its cards can say so.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from engine.knowledge_section import _covers_task, _in_scope_of_projects, with_ancestors
from engine.learn import NETTED_WAITING, kind_of_id, learn_request
from engine.records import Scope

#: The corrections that count: the person changed, undid or sent back what the assistant made. What the person does to
#: what was learned (keep, discard, retire, narrow, just this time) is not one, and neither is a drop: work no longer
#: needed says nothing about the assistant, so drops are counted apart (`apart_per_week`).
CORRECTIONS = frozenset(
    {
        "sent_back",
        "undone",
        "reworded",
        "pulled_back",
        "draft_edited",
        "held_declined",
        "routed",
        "edited",
        "change_requested",
        "set_aside",
        "no_reply_needed",
        "missed",
    }
)
#: The knowledge a repeat is counted against: what the person keeps as a lesson or a rule.
REPEATABLE = ("lesson", "rule")
#: Kinds of record a correction names that are bookkeeping, not the corrected item.
NOT_ITEMS = ("changeset", "signal", "request", "run")


# ---- what an answer claims -------------------------------------------------------------------------------------------


def claims(store: Any, run_id: str | None, applied: Iterable[str], missing: Iterable[str]) -> dict[str, Any]:
    """The fields of a changeset that record an answer's claims: the ids it said it applied that the run was given
    (`applied`), how many it named that it wasn't given (`applied_dropped`), and what it lacked (`missing`). Only the
    fields with something in them are returned."""
    run = store.read().get("run", run_id) if run_id else None
    given = set(((run.data.get("knowledge") or {}) if run is not None else {}).get("given", []))
    named = list(dict.fromkeys(applied))
    kept = [i for i in named if i in given]
    found: dict[str, Any] = {}
    if kept:
        found["applied"] = kept
    if len(named) > len(kept):
        found["applied_dropped"] = len(named) - len(kept)
    if missing:
        found["missing"] = list(missing)
    return found


def first_run_on(store: Any, run_id: str | None) -> str | None:
    """The name of the account a run was made on, when no answered run for another request was made on the same
    account and model (the rounds of one request are one first run); None when the run isn't recorded or one was."""
    run = store.read().get("run", run_id) if run_id else None
    if run is None:
        return None
    for other in store.read().list("run"):
        if (
            other.data.get("request") != run.data.get("request")
            and other.data["provider"] == run.data["provider"]
            and other.data["model"] == run.data["model"]
            and other.data["outcome"] == "ok"
        ):
            return None
    return run.data["provider"]


# ---- times -----------------------------------------------------------------------------------------------------------


def at_of(stamp: Any) -> datetime:
    """A stored time as a moment with a zone."""
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def week_of(moment: datetime, here: tzinfo) -> date:
    """The Monday of the week a moment falls in, in the person's time zone."""
    day = at_of(moment).astimezone(here).date()
    return day - timedelta(days=day.weekday())


def weeks_in(now: datetime, days: int, here: tzinfo) -> list[date]:
    """The weeks (their Mondays) that overlap the window, oldest first."""
    first = week_of(now - timedelta(days=days), here)
    last = week_of(now, here)
    return [first + timedelta(weeks=n) for n in range(((last - first).days // 7) + 1)]


# ---- the knowledge-used rate -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeUsed:
    task: str
    given: int  # runs in the window that were given at least one entry
    applied: int  # of those, the runs whose answer listed at least one entry it was given
    dropped: int  # ids answers named as applied that the run was not given, left out

    @property
    def rate(self) -> float | None:
        return self.applied / self.given if self.given else None


def knowledge_used(view: Any, now: datetime, days: int) -> list[KnowledgeUsed]:
    """The knowledge-used rate for each kind of work over the last `days` days, in the order the kinds are named."""
    start = now - timedelta(days=days)
    made = {c.data["run"]: c for c in view.list("changeset") if c.data.get("run")}
    given: dict[str, int] = defaultdict(int)
    applied: dict[str, int] = defaultdict(int)
    dropped: dict[str, int] = defaultdict(int)
    kinds: list[str] = []
    for run in sorted(view.list("run"), key=lambda r: r.data["started_at"]):
        changeset = made.get(run.id)
        if changeset is None or at_of(run.data["started_at"]) < start:
            continue
        task = run.data["task"]
        if task not in kinds:
            kinds.append(task)
        dropped[task] += changeset.data.get("applied_dropped", 0)
        if (run.data.get("knowledge") or {}).get("given"):
            given[task] += 1
            applied[task] += bool(changeset.data.get("applied"))
    return [KnowledgeUsed(k, given[k], applied[k], dropped[k]) for k in kinds if given[k] or dropped[k]]


# ---- the repeat-correction rate --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RepeatWeek:
    task: str
    week: date  # the Monday
    corrections: int
    repeats: int
    enough: bool  # the week had at least the configured number of corrections

    @property
    def rate(self) -> float | None:
        return self.repeats / self.corrections if self.enough else None


def _project_of(found: Any) -> str | None:
    return found.id if found.kind == "project" else found.data.get("project")


def corrected_items(view: Any, records: Mapping[str, Any], signal: Any) -> list[Any]:
    """The records a correction is about: the ones it names, and the ones the corrected changeset touched."""
    named: list[tuple[str, str]] = []
    for ref in signal.data.get("refs") or []:
        kind = kind_of_id(records, ref)
        if kind is not None and kind not in NOT_ITEMS:
            named.append((kind, ref))
    changeset = view.get("changeset", signal.data["changeset"]) if signal.data.get("changeset") else None
    if changeset is not None:
        for outcome in changeset.data["ops"]:
            named += [(r["kind"], r["id"]) for r in outcome.get("records") or []]
    found = []
    for kind, record_id in dict.fromkeys(named):
        stored = view.get(kind, record_id)
        if stored is not None:
            found.append(stored)
    return found


def _targets(scope: Scope) -> bool:
    """Whether an entry names what it is for. One that names nothing applies to everything, so no correction can be
    said to repeat it."""
    return bool(scope.task_kinds or scope.records or scope.filter or scope.projects)


def matches(scope: Scope, task: str, items: list[Any], view: Any) -> bool:
    """Whether an entry's target matches a correction: it covers the run's kind of work, one of the corrected records is
    of a kind it names (a `type` or a `type.field`) and has the field values it asks for, and the projects of the
    corrected records are in its scope."""
    if not _targets(scope) or not _covers_task(scope, task):
        return False
    wanted = {name.partition(".")[0] for name in scope.records}
    chosen = [i for i in items if not wanted or i.kind in wanted]
    if wanted and not chosen:
        return False
    if scope.filter:
        chosen = [i for i in chosen if all(i.data.get(k) == v for k, v in scope.filter.items())]
        if not chosen:
            return False
    projects = {p for p in (_project_of(i) for i in chosen) if p}
    return _in_scope_of_projects(scope, set(with_ancestors(view, projects)))


def is_repeat(view: Any, records: Mapping[str, Any], signal: Any) -> bool:
    """Whether a correction repeats a mistake the assistant had been taught about: the run it corrects was given an
    active lesson or rule whose target matches the corrected item."""
    run = view.get("run", signal.data["run"]) if signal.data.get("run") else None
    if run is None:
        return False
    items = corrected_items(view, records, signal)
    for entry_id in (run.data.get("knowledge") or {}).get("given", []):
        kind = kind_of_id(records, entry_id)
        entry = view.get(kind, entry_id) if kind in REPEATABLE else None
        if entry is not None and matches(
            Scope.model_validate(entry.data.get("applies_to") or {}), run.data["task"], items, view
        ):
            return True
    return False


def repeat_corrections(
    view: Any, records: Mapping[str, Any], now: datetime, days: int, minimum: int, here: tzinfo
) -> list[RepeatWeek]:
    """The repeat-correction rate for each kind of work and week over the last `days` days, oldest week first. A
    correction the person took back within its undo time (its learning was netted out) is not counted, and neither is
    one of something no run made. A week has a rate only with at least `minimum` corrections of that kind of work."""
    start = now - timedelta(days=days)
    weeks = weeks_in(now, days, here)
    total: dict[tuple[str, date], int] = defaultdict(int)
    repeated: dict[tuple[str, date], int] = defaultdict(int)
    for signal in view.list("signal"):
        if signal.data["kind"] not in CORRECTIONS or not signal.data.get("run"):
            continue
        when = at_of(signal.data["at"])
        run = view.get("run", signal.data["run"])
        if run is None or when < start or when > now:
            continue
        learning = learn_request(view, signal.id)
        if learning is not None and learning.data.get("waiting") == NETTED_WAITING:
            continue
        key = (run.data["task"], week_of(when, here))
        total[key] += 1
        repeated[key] += is_repeat(view, records, signal)
    return [
        RepeatWeek(task, week, total[(task, week)], repeated[(task, week)], total[(task, week)] >= minimum)
        for task in sorted({t for t, _ in total})
        for week in weeks
        if total[(task, week)]
    ]


# ---- missed one, per person and week ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class MissedWeek:
    person: str
    week: date  # the Monday
    count: int  # "Missed one" sentences the person sent in the week


def missed_per_week(view: Any, now: datetime, days: int, here: tzinfo) -> list[MissedWeek]:
    """How many times each person said the assistant missed something, for each week of the last `days` days, oldest
    week first. A person with any in the window has a row for every week of it, so a week with none reads as zero. A
    signal that names no person is counted for nobody."""
    start = now - timedelta(days=days)
    weeks = weeks_in(now, days, here)
    counts: dict[tuple[str, date], int] = defaultdict(int)
    for signal in view.list("signal"):
        person = signal.data.get("person")
        when = at_of(signal.data["at"])
        if signal.data["kind"] != "missed" or not person or when < start or when > now:
            continue
        counts[(person, week_of(when, here))] += 1
    return [MissedWeek(p, week, counts[(p, week)]) for p in sorted({p for p, _ in counts}) for week in weeks]


# ---- missed, declined and dropped, counted apart -------------------------------------------------------------------

#: The three signals counted on their own, by the kind of signal each is recorded as.
APART = {"missed": "missed", "declined": "held_declined", "dropped": "dropped"}


@dataclass(frozen=True)
class ApartWeek:
    week: date  # the Monday
    missed: int  # the assistant failed to find something
    declined: int  # a held change was not the person's, or not a promise
    dropped: int  # work no longer needed: not a correction of the assistant


def apart_per_week(view: Any, now: datetime, days: int, here: tzinfo) -> list[ApartWeek]:
    """How many times the person said each of the three over the last `days` days, for each week of the window, oldest
    week first. The three are never added together: a week of drops is not a week of misses."""
    start = now - timedelta(days=days)
    by_kind = {kind: name for name, kind in APART.items()}
    counts: dict[date, dict[str, int]] = {w: dict.fromkeys(APART, 0) for w in weeks_in(now, days, here)}
    for signal in view.list("signal"):
        name = by_kind.get(signal.data["kind"])
        when = at_of(signal.data["at"])
        if name is None or when < start or when > now:
            continue
        counts[week_of(when, here)][name] += 1
    return [ApartWeek(week, **found) for week, found in counts.items()]


# ---- the missing-op list ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MissingGroup:
    wording: str  # the most recent wording in the group
    count: int
    tasks: list[str] = field(default_factory=list)
    changesets: list[str] = field(default_factory=list)  # the answers that said it, newest first
    last_seen: datetime | None = None


@dataclass(frozen=True)
class MissingWeek:
    week: date  # the Monday
    groups: list[MissingGroup]  # most said first


_ARTICLES = ("a", "an", "the", "no")


def wording_key(text: str) -> str:
    """What makes two wordings the same item: lower case, words only, without the small words at the start."""
    words = re.findall(r"[a-z0-9]+", text.casefold())
    while len(words) > 1 and words[0] in _ARTICLES:
        words.pop(0)
    return " ".join(words)


def missing_list(view: Any, now: datetime, days: int, here: tzinfo) -> list[MissingWeek]:
    """What runs said no op could do over the last `days` days, grouped by wording for each week, newest week first.
    Each group counts how many answers said it."""
    start = now - timedelta(days=days)
    buckets: dict[date, dict[str, list[tuple[datetime, str, str, str]]]] = defaultdict(lambda: defaultdict(list))
    for changeset in view.list("changeset"):
        when = at_of(changeset.data["created_at"])
        if not changeset.data.get("missing") or when < start or when > now:
            continue
        request = view.get("request", changeset.data["request"])
        task = request.data["task"] if request is not None else ""
        for wording in changeset.data["missing"]:
            key = wording_key(wording)
            if key:
                buckets[week_of(when, here)][key].append((when, wording, task, changeset.id))
    weeks = []
    for week in sorted(buckets, reverse=True):
        groups = []
        for found in buckets[week].values():
            newest = sorted(found, key=lambda item: item[0], reverse=True)
            groups.append(
                MissingGroup(
                    wording=newest[0][1],
                    count=len({item[3] for item in found}),
                    tasks=sorted({item[2] for item in found if item[2]}),
                    changesets=list(dict.fromkeys(item[3] for item in newest)),
                    last_seen=newest[0][0],
                )
            )
        groups.sort(key=lambda g: (-g.count, g.wording.casefold()))
        weeks.append(MissingWeek(week, groups))
    return weeks
