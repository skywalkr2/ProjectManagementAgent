"""The gate week's instruments (design 6.32, "Measures"): each measure as a count with its denominator, for each day and
for the window, read from the records alone. Nothing here calls AI.

- Silent closes out of all closes: `closes.measure` for the window, and the same closes by the day they were made.
- Wrong endings out of endings made. An ending is an op in `ENDING_OPS` (close, drop, move, part, unhold) in a change
  the assistant made (a run's, not one the person made on a screen). It was made once it applied or the person decided
  about it; one still waiting for the person's Keep is not counted yet. It is wrong when the person declined it ("Not
  yet", recorded by `decline_held`), when they undid it, or when it was a nudge recorded as done and the person later
  reopened the action. A nudge is found from the records: an applied `action.close` whose request came from a note
  typed on "Followed up" (the source's kind is `note:followed_up`), and the reopening is the action's status going back
  to open in the ledger after that close. An ending undone and then reopened counts once.
- Missed out of present: the person's own daily count (`promise_count`), summed over the window. The app never works
  it out.
- The replay set: how many replay files the workspace has. When the replays last ran is not recorded anywhere that
  tells them from the golden set's runs, so it isn't shown.

A day is a day on the person's own clock. The window is the configured number of days ending today, whole days.
"""

from __future__ import annotations

import typing
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any

from engine import closes
from engine.applier import DECLINED_REASON, ENDING_OPS
from engine.names import People
from engine.storage import StoreError, WriteContext
from engine.today import zone

#: Where the person's own count is written: the person's own entry on a screen.
_COUNT = WriteContext(actor="pm", trust="trusted", op="gate.count")
#: The kind of source a note typed on "Followed up" is.
NUDGE_SOURCE = "note:followed_up"


class CountError(StoreError):
    """The day's count can't be saved as it was typed."""


# ---- the window ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    since: date  # the first day
    until: date  # the last day: today
    start: datetime  # the start of the first day
    end: datetime  # now


def window(now: datetime, days: int, here: tzinfo) -> Window:
    """The `days` days before today and today, on the person's clock."""
    today = now.astimezone(here).date()
    first = today - timedelta(days=days)
    return Window(first, today, datetime.combine(first, time(0), tzinfo=here).astimezone(UTC), now)


def _moment(stamp: Any) -> datetime | None:
    if isinstance(stamp, datetime):
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    try:
        moment = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _day_of(stamp: Any, here: tzinfo) -> date | None:
    moment = _moment(stamp)
    return moment.astimezone(here).date() if moment is not None else None


# ---- silent closes out of all closes ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class CloseDay:
    day: date
    total: int
    silent: int


@dataclass(frozen=True)
class ClosesMeasure:
    total: int
    silent: int
    days: list[CloseDay] = field(default_factory=list)  # days with a close, oldest first


def closes_measure(view: Any, win: Window, here: tzinfo) -> ClosesMeasure:
    """Silent closes out of all closes in the window, and for each day with a close."""
    whole = closes.measure(view, win.start, win.end)
    total: dict[date, int] = defaultdict(int)
    silent: dict[date, int] = defaultdict(int)
    for close in closes.collect(view, win.start, win.end):
        day = _day_of(close.when, here)
        if day is None:
            continue
        total[day] += 1
        silent[day] += close.silent
    return ClosesMeasure(whole.total, whole.silent, [CloseDay(d, total[d], silent[d]) for d in sorted(total)])


# ---- wrong endings out of endings made -------------------------------------------------------------------------------

_ENDING_NAMES = frozenset(typing.get_args(cls.model_fields["op"].annotation)[0] for cls in ENDING_OPS)


@dataclass(frozen=True)
class EndingDay:
    day: date
    made: int
    wrong: int


@dataclass(frozen=True)
class EndingsMeasure:
    made: int
    wrong: int
    declined: int  # wrong: the person kept things as they were ("Not yet")
    undone: int  # wrong: the person undid it
    reopened: int  # wrong: a nudge recorded as done, reopened by the person
    days: list[EndingDay] = field(default_factory=list)  # days with an ending made, oldest first


def _reopened_after(ledger: list[dict[str, Any]], changeset: str, action: str) -> bool:
    """Whether the action's status went back to open after the change closed it."""
    closed = [
        e["seq"]
        for e in ledger
        if e["changeset"] == changeset and e["record_id"] == action and e["field"] == "status" and e["after"] == "done"
    ]
    if not closed:
        return False
    return any(
        e["record_id"] == action and e["field"] == "status" and e["after"] == "open" and e["seq"] > min(closed)
        for e in ledger
    )


def endings_measure(view: Any, ledger: list[dict[str, Any]], win: Window, here: tzinfo) -> EndingsMeasure:
    """Wrong endings out of endings made in the window, by the day each was made. `ledger` is the action ledger."""
    made: dict[date, int] = defaultdict(int)
    wrong: dict[date, int] = defaultdict(int)
    kinds = {"declined": 0, "undone": 0, "reopened": 0}
    for cs in view.list("changeset"):
        data = cs.data
        when = _moment(data["created_at"])
        request = view.get("request", data["request"]) if data.get("request") else None
        # A change made on a screen has no run: the person made it. One from the person's note that a run read is the
        # assistant's.
        own = data.get("action") or (request is not None and request.data.get("origin") == "pm" and not data.get("run"))
        if own or when is None or not win.start <= when <= win.end:
            continue
        nudged = False
        source = (
            view.get("source", request.data["source"]) if request is not None and request.data.get("source") else None
        )
        if source is not None and source.data.get("kind") == NUDGE_SOURCE:
            nudged = True
        day = when.astimezone(here).date()
        for outcome in data["ops"]:
            op = outcome.get("op") or {}
            if op.get("op") not in _ENDING_NAMES:
                continue
            status = outcome.get("status")
            if status == "applied":
                how = (
                    "reopened"
                    if nudged and op["op"] == "action.close" and _reopened_after(ledger, cs.id, op["id"])
                    else None
                )
            elif status == "undone":
                how = "declined" if outcome.get("reason") == DECLINED_REASON else "undone"
            else:
                continue  # waiting, refused or rejected: not an ending made
            made[day] += 1
            if how:
                wrong[day] += 1
                kinds[how] += 1
    return EndingsMeasure(
        made=sum(made.values()),
        wrong=sum(wrong.values()),
        declined=kinds["declined"],
        undone=kinds["undone"],
        reopened=kinds["reopened"],
        days=[EndingDay(d, made[d], wrong[d]) for d in sorted(made)],
    )


# ---- missed out of present: the person's own daily count -------------------------------------------------------------


@dataclass(frozen=True)
class CountDay:
    day: date
    present: int
    missed: int


@dataclass(frozen=True)
class CountsMeasure:
    present: int
    missed: int
    entered: int  # days with a count
    days: list[CountDay] = field(default_factory=list)  # oldest first


def _day(value: Any) -> date | None:
    try:
        return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value))
    except ValueError:
        return None


def counts_measure(view: Any, person: str | None, win: Window) -> CountsMeasure:
    """The counts `person` entered for the days of the window, summed: missed out of present."""
    found = []
    for record in view.list("promise_count"):
        day = _day(record.data["day"])
        if record.data.get("person") == person and day is not None and win.since <= day <= win.until:
            found.append(CountDay(day, record.data["present"], record.data["missed"]))
    found.sort(key=lambda c: c.day)
    return CountsMeasure(sum(c.present for c in found), sum(c.missed for c in found), len(found), found)


def _count_of(tx: Any, person: str | None, day: date) -> Any:
    for record in tx.list("promise_count"):
        if record.data.get("person") == person and _day(record.data["day"]) == day:
            return record
    return None


def save_count(
    store: Any, cfg: Any, day: date, present: int, missed: int, *, now: datetime | None = None
) -> dict[str, int] | None:
    """Save the person's count for a day, or correct the day's count. Returns what the day held before (`present` and
    `missed`), or None when it had nothing, which `restore_count` takes."""
    now = now or datetime.now(UTC)
    if present < 0 or missed < 0:
        raise CountError("A count can't be less than zero.")
    if missed > present:
        raise CountError("You can't have missed more than you counted.")
    if day > now.astimezone(zone(cfg)).date():
        raise CountError("That day hasn't happened yet.")
    person = People(store, cfg).pm
    values = {"present": present, "missed": missed, "at": now.isoformat()}
    with store.transaction() as tx:
        current = _count_of(tx, person, day)
        if current is None:
            tx.create("promise_count", {"person": person, "day": day.isoformat(), **values}, _COUNT)
            return None
        previous = {"present": current.data["present"], "missed": current.data["missed"]}
        tx.update("promise_count", current.id, values, _COUNT, read_version=current.version)
        return previous


def restore_count(store: Any, cfg: Any, day: date, previous: dict[str, int] | None) -> None:
    """Undo `save_count`: the day holds what it held before, or nothing."""
    person = People(store, cfg).pm
    with store.transaction() as tx:
        current = _count_of(tx, person, day)
        if current is None:
            raise CountError("There is no count for that day.")
        if previous is None:
            tx.delete("promise_count", current.id, _COUNT, read_version=current.version)
        else:
            tx.update(
                "promise_count",
                current.id,
                {"present": previous["present"], "missed": previous["missed"]},
                _COUNT,
                read_version=current.version,
            )


# ---- the replay set --------------------------------------------------------------------------------------------------


def replay_count(workspace: Path) -> int:
    """How many replay files the workspace has (a file that can't be read still counts: it is a miss someone kept)."""
    folder = workspace / "replays"
    return len(list(folder.glob("*.yaml"))) if folder.is_dir() else 0
