"""The outcome, measured (design 6.20, 6.32 "Measured"): what the assistant's work came to for the person, each week,
read from the records alone. Nothing here calls AI, and nothing is tracked beyond the app's own records.

- **Promises found and kept:** the promises the person made that the assistant found (it made the action from an input),
  counted by the week it found them, and how many promises it found, from any week, the person closed as done in the
  week. A promise dropped is not kept.
- **False alerts:** things the assistant raised that the person said weren't needed, counted by the week they said so.
  *Dismissed* is a suggestion the person chose to leave or keep as it was and didn't take back. *Corrected* is work the
  person declined, undid, pulled back, edited or said needed no reply (`FALSE_ALERT_CORRECTIONS`). Putting a suggestion
  off for now ("Not now") is a matter of timing, never a false alert.
- **Time spent reviewing:** the seconds the screens that look over the assistant's work were open and in view, each
  visit as that screen measured it and counted for at most `dispatch.knowledge.review_visit_max_seconds`, with the
  number of visits. The app records a `review_time` signal when the person leaves such a screen; it measures nothing
  else.
- **Follow-ups completed:** things the person waited on and chased that were then settled in the week: a promise
  someone else owed that was followed up and then done, and a question that was followed up and then answered.

A week is a Monday to Sunday on the person's own clock; the window is `dispatch.knowledge.quality_window_days`. Each
measure is its own count: they are never added together.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from engine.promises import is_promise
from engine.quality import at_of, week_of, weeks_in
from engine.storage import StoreError, WriteContext

#: The corrections that are false alerts: the assistant raised or did something the person said wasn't right.
FALSE_ALERT_CORRECTIONS = frozenset(
    {"held_declined", "no_reply_needed", "set_aside", "undone", "pulled_back", "edited"}
)
#: The suggestion choices that say nothing needed doing.
DISMISSING = ("leave", "keep")
#: The screens that look over the assistant's work, as the screens name themselves when they record their time.
SCREENS = ("review", "changes", "since")
TAKEN_BACK = "taken back"

_TIME = WriteContext(actor="pm", trust="trusted", op="review.time")


@dataclass(frozen=True)
class OutcomeWeek:
    week: date  # the Monday
    found: int  # promises of the person's the assistant found this week
    kept: int  # promises it had found that the person closed as done this week
    dismissed: int
    corrected: int
    review_seconds: int
    review_visits: int
    follow_ups: int  # chased, then settled this week


def _weeks(now: datetime, days: int, here: tzinfo) -> list[date]:
    return weeks_in(now, days, here)


def _note(signal: Any) -> dict[str, Any] | None:
    if signal.data.get("note") in (None, TAKEN_BACK):
        return None
    try:
        said = json.loads(signal.data["note"])
    except (ValueError, TypeError):
        return None
    return said if isinstance(said, dict) else None


def _within(stamp: Any, start: datetime, now: datetime) -> datetime | None:
    try:
        when = at_of(stamp)
    except (TypeError, ValueError):
        return None
    return when if start <= when <= now else None


def promises_found(view: Any, me: str | None, now: datetime, days: int, here: tzinfo) -> dict[date, int]:
    """The promises the person made that the assistant found, by the week it found them."""
    start = now - timedelta(days=days)
    made = view.creators("action")
    counts: dict[date, int] = {}
    for record in view.list("action"):
        who, at = made.get(record.id, ("pm", ""))
        if who == "pm" or not me or not is_promise(record.data):
            continue
        if not any(o.get("person") == me for o in record.data.get("owners") or []):
            continue
        when = _within(at, start, now)
        if when is not None:
            counts[week_of(when, here)] = counts.get(week_of(when, here), 0) + 1
    return counts


def promises_kept(view: Any, me: str | None, now: datetime, days: int, here: tzinfo) -> dict[date, int]:
    """Promises the assistant had found that the person closed as done, by the week they were closed. A promise closed
    and then reopened and closed again counts once, at its last close."""
    start = now - timedelta(days=days)
    made = view.creators("action")
    changes = view.field_changes("action", ("status",))
    counts: dict[date, int] = {}
    for record in view.list("action"):
        d = record.data
        who, _ = made.get(record.id, ("pm", ""))
        if d.get("status") != "done" or who == "pm" or not me or not is_promise(d):
            continue
        if not any(o.get("person") == me for o in d.get("owners") or []):
            continue
        closed = [r for r in changes.get(record.id, []) if r["field"] == "status" and r["after"] == "done"]
        when = _within(closed[-1]["at"], start, now) if closed else None
        if when is not None:
            counts[week_of(when, here)] = counts.get(week_of(when, here), 0) + 1
    return counts


def false_alerts(view: Any, now: datetime, days: int, here: tzinfo) -> tuple[dict[date, int], dict[date, int]]:
    """Suggestions the person left as they were, and work they corrected, each by the week they said so."""
    start = now - timedelta(days=days)
    dismissed: dict[date, int] = {}
    corrected: dict[date, int] = {}
    for signal in view.list("signal"):
        kind = signal.data["kind"]
        if kind not in FALSE_ALERT_CORRECTIONS and kind != "suggestion_chosen":
            continue
        when = _within(signal.data["at"], start, now)
        if when is None:
            continue
        week = week_of(when, here)
        if kind == "suggestion_chosen":
            said = _note(signal)
            if said is not None and said.get("choice") in DISMISSING:
                dismissed[week] = dismissed.get(week, 0) + 1
        else:
            corrected[week] = corrected.get(week, 0) + 1
    return dismissed, corrected


def review_time(view: Any, now: datetime, days: int, here: tzinfo) -> dict[date, tuple[int, int]]:
    """The seconds and the visits to the screens that look over the assistant's work, by week."""
    start = now - timedelta(days=days)
    found: dict[date, tuple[int, int]] = {}
    for signal in view.list("signal"):
        if signal.data["kind"] != "review_time":
            continue
        said = _note(signal)
        when = _within(signal.data["at"], start, now)
        if said is None or when is None:
            continue
        week = week_of(when, here)
        seconds, visits = found.get(week, (0, 0))
        found[week] = (seconds + int(said.get("seconds") or 0), visits + 1)
    return found


def follow_ups_completed(view: Any, me: str | None, now: datetime, days: int, here: tzinfo) -> dict[date, int]:
    """Things the person chased that were then settled, by the week they were: another person's promise followed up
    and then done, and a question followed up and then answered."""
    start = now - timedelta(days=days)
    counts: dict[date, int] = {}

    statuses = {kind: view.field_changes(kind, ("status",)) for kind in ("action", "question")}

    def week_settled(kind: str, record_id: str, after: str) -> date | None:
        rows = [r for r in statuses[kind].get(record_id, []) if r["after"] == after]
        when = _within(rows[-1]["at"], start, now) if rows else None
        return week_of(when, here) if when is not None else None

    for record in view.list("action"):
        d = record.data
        owners = [o.get("person") for o in d.get("owners") or []]
        if d.get("status") != "done" or not d.get("followed_up") or not owners or me in owners:
            continue
        week = week_settled("action", record.id, "done")
        if week is not None:
            counts[week] = counts.get(week, 0) + 1
    for record in view.list("question"):
        d = record.data
        if d.get("status") != "answered" or not d.get("followed_up"):
            continue
        week = week_settled("question", record.id, "answered")
        if week is not None:
            counts[week] = counts.get(week, 0) + 1
    return counts


def per_week(view: Any, me: str | None, now: datetime, days: int, here: tzinfo) -> list[OutcomeWeek]:
    """Every measure for each week of the window, oldest week first."""
    found = promises_found(view, me, now, days, here)
    kept = promises_kept(view, me, now, days, here)
    dismissed, corrected = false_alerts(view, now, days, here)
    reviewing = review_time(view, now, days, here)
    chased = follow_ups_completed(view, me, now, days, here)
    return [
        OutcomeWeek(
            week,
            found.get(week, 0),
            kept.get(week, 0),
            dismissed.get(week, 0),
            corrected.get(week, 0),
            reviewing.get(week, (0, 0))[0],
            reviewing.get(week, (0, 0))[1],
            chased.get(week, 0),
        )
        for week in _weeks(now, days, here)
    ]


def record_review_time(store: Any, cfg: Any, screen: str, seconds: int, now: datetime) -> int:
    """Record one visit to a screen that looks over the assistant's work: how long it was open and in view, held to the
    configured most for a visit. Returns the seconds recorded; a visit of no time records nothing."""
    from engine.learn import record

    if screen not in SCREENS:
        raise StoreError("that isn't a screen that looks over the assistant's work")
    counted = min(int(seconds), cfg.dispatch.knowledge.review_visit_max_seconds)
    if counted <= 0:
        return 0
    data = {
        "kind": "review_time",
        "note": json.dumps({"screen": screen, "seconds": counted}),
        "at": now.astimezone(UTC).isoformat(),
    }
    with store.transaction() as tx:
        record(tx, cfg, data, _TIME, now)
    return counted
