"""How much each piece of knowledge was used (design 6.22): from the runs' knowledge logs, how many runs were given it
and in how many it was applied.

An entry is **given** to a run when the run's knowledge log lists it. It is **used** by a run when the log shows it
applied: a rule the log counts as applied, or an entry the run's changeset cites among the ones it was given. All of
this is decided from records, never from a model's own claim. Plain functions over a read of the records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Use:
    """What the runs show about one entry: `given` runs listed it, `used` runs applied it, and `last_used` is when the
    latest of those began."""

    used: int = 0
    given: int = 0
    last_used: datetime | None = None


def _at(stamp: Any) -> datetime | None:
    if not stamp:
        return None
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def use_of(view: Any) -> dict[str, Use]:
    """The use of every entry and rule the runs mention, by id. An id no run mentions is not in the result, and means
    it was never given."""
    cited: dict[str, set[str]] = {}
    for changeset in view.list("changeset"):
        run_id = changeset.data.get("run")
        if run_id:
            cited.setdefault(run_id, set()).update(changeset.data.get("applied") or [])
    given: dict[str, int] = {}
    used: dict[str, int] = {}
    last: dict[str, datetime] = {}
    for run in view.list("run"):
        log = run.data.get("knowledge")
        if not log:
            continue
        began = _at(run.data.get("started_at"))
        for entry_id in set(log.get("given") or []):
            given[entry_id] = given.get(entry_id, 0) + 1
        for entry_id in {*(log.get("rules_applied") or []), *cited.get(run.id, ())}:
            used[entry_id] = used.get(entry_id, 0) + 1
            if began is not None and (entry_id not in last or began > last[entry_id]):
                last[entry_id] = began
    return {
        entry_id: Use(used.get(entry_id, 0), given.get(entry_id, 0), last.get(entry_id)) for entry_id in {*given, *used}
    }
