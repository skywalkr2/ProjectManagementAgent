"""Which suggestion lines show on Today and which wait for the brief (design 6.32, the attention budget).

A suggestion is a line the assistant offers rather than something that is due: a follow-up that has gone unanswered,
to-dos nobody has touched, items filed under no project, what the assistant learned. `engine.attention` decides,
from explicit inputs, which of them interrupt: held back when put off ("Not now") and unchanged, or below the
importance threshold; saved for the brief in quiet hours or past the day's cap; the most important first. This module
gathers those inputs from the settings (`steward.attention`, the quiet hours under `steward.reminders`) and the
records, and records a "Not now". Everything else on Today is never held back here.

"Not now" is a `suggestion_dismissed` signal whose note names the line and what it was when put off. It stays off until
something about the suggestion changes (its change key), and taking it back makes it show again. The day's cap counts
what shows and what the person put off or chose something about today. A pattern line and a stale line carry choices
(`engine.patterns`); "Leave it" keeps a line off the way "Not now" does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from engine import attention, patterns
from engine.storage import WriteContext
from engine.today import zone

#: The kinds of Today line that are suggestions, in the settings' own names (`steward.attention.importance`).
KINDS = ("escalate", "stale", "unfiled", "learned", "catch_up", "area", "pattern")
TAKEN_BACK = "taken back"


@dataclass(frozen=True)
class Split:
    """The queue's lines split by the attention rules: what shows now, and the suggestions saved for the brief."""

    shown: list[Any]
    digest: list[Any]


def change_key(line: Any) -> str:
    """What about a suggestion line counts as a change: when it differs from what was put off, the line comes back."""
    if line.kind == "escalate":
        return f"{','.join(sorted([*line.questions, *line.actions]))}:{line.count}"
    if line.kind == "stale":
        return ",".join(sorted(line.actions))
    return str(line.count)  # a pattern: how many times it has happened


def importance(cfg: Any, kind: str) -> float:
    return float(getattr(cfg.steward.attention.importance, kind))


def _note(line: Any) -> str:
    return json.dumps({"kind": line.kind, "subject": line.key, "change": change_key(line)})


def dismissed(view: Any) -> dict[tuple[str, str], str]:
    """What the person put off and hasn't taken back: (kind, line key) to the change key it had."""
    found: dict[tuple[str, str], str] = {}
    for signal in sorted(view.list("signal"), key=lambda s: int(s.id.rpartition("-")[2])):
        if signal.data["kind"] != "suggestion_dismissed" or signal.data.get("note") in (None, TAKEN_BACK):
            continue
        try:
            said = json.loads(signal.data["note"])
            found[(said["kind"], said["subject"])] = said["change"]
        except (ValueError, KeyError, TypeError):
            continue
    # A choice to leave a suggestion keeps it away the same way.
    return {**found, **patterns.stays_off(view)}


def _put_off_today(view: Any, cfg: Any, now: datetime) -> tuple[datetime, ...]:
    here = zone(cfg)
    today = now.astimezone(here).date()
    moments = []
    for signal in view.list("signal"):
        if (
            signal.data["kind"] not in ("suggestion_dismissed", "suggestion_chosen")
            or signal.data.get("note") == TAKEN_BACK
        ):
            continue
        at = datetime.fromisoformat(str(signal.data["at"]))
        at = at if at.tzinfo else at.replace(tzinfo=UTC)
        if at.astimezone(here).date() == today and at <= now:
            moments.append(at)
    return tuple(moments)


def split(cfg: Any, view: Any, lines: list[Any], now: datetime) -> Split:
    """The lines with the suggestions among them sorted by the attention rules. A line that isn't a suggestion is shown;
    a suggestion put off, or below the threshold, is dropped; one saved for the brief goes to the digest."""
    settings = cfg.steward.attention
    suggested = [line for line in lines if line.kind in KINDS]
    if not suggested:
        return Split(list(lines), [])
    reminders = cfg.steward.reminders
    quiet = (
        attention.QuietHours(time.fromisoformat(reminders.quiet_start), time.fromisoformat(reminders.quiet_end))
        if settings.quiet
        else None
    )
    here = zone(cfg)
    decisions = attention.admit(
        [attention.Suggestion(line.kind, importance(cfg, line.kind), change_key(line), line.key) for line in suggested],
        now,
        here,
        attention.DailyCap(settings.daily_cap, now.astimezone(here).date(), _put_off_today(view, cfg, now)),
        quiet,
        settings.threshold,
        dismissed(view),
    )
    verdict = {id(line): d.disposition for line, d in zip(suggested, decisions, strict=True)}
    shown = [line for line in lines if line.kind not in KINDS or verdict[id(line)] == "shown_now"]
    waiting = [line for line in suggested if verdict[id(line)] == "saved_for_digest"]
    # What waits for the brief is in the order of what matters.
    waiting.sort(key=lambda line: -importance(cfg, line.kind))
    return Split(shown, waiting)


def put_off(store: Any, cfg: Any, line: Any, now: datetime) -> str:
    """Record "Not now" for a suggestion line as of its change key; returns the signal's id."""
    from engine.learn import record

    data = {
        "kind": "suggestion_dismissed",
        "refs": [*line.questions, *line.actions][:20],
        "note": _note(line),
        "at": now.astimezone(UTC).isoformat(),
    }
    with store.transaction() as tx:
        return record(tx, cfg, data, WriteContext(actor="pm", trust="trusted", op="suggestion.not_now"), now)


def take_back(store: Any, signal_id: str) -> bool:
    """Undo a "Not now": the signal stays, marked as taken back, and the suggestion shows again. Returns whether
    there was one to take back."""
    found = store.read().get("signal", signal_id)
    if found is None or found.data["kind"] != "suggestion_dismissed" or found.data.get("note") == TAKEN_BACK:
        return False  # a choice is taken back with `patterns.undo`
    with store.transaction() as tx:
        tx.update(
            "signal",
            signal_id,
            {"note": TAKEN_BACK},
            WriteContext(actor="pm", trust="trusted", op="suggestion.take_back"),
            read_version=found.version,
        )
    return True
