"""Adding a to-do by hand (design 6.32): the words, a day said in plain words, who does it, a project and how it
repeats.

No assistant reads anything. The day is read by the due-date rules (`engine/due_phrases.py`) from today on the person's
own clock, and the repeat by the repeat grammar (`engine/repeats.py`); both are read before anything is kept, so words
that aren't clear save nothing. The to-do is the person's own `action.add`, applied at once; a repeat is the person's
own `action.repeat` on it, and an effort the person gave is their own edit of it. Each is its own change, returned in
the order made so Undo takes them back last first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from engine import repeats
from engine.applier import apply_as_person
from engine.due_phrases import load_holidays, resolve
from engine.storage import StoreError
from engine.today import zone


class TodoProblem(ValueError):
    """Why the to-do can't be added as typed, in plain words for the person."""


@dataclass(frozen=True)
class DayReading:
    """What words typed for a day are read as. `ok`: `day` is the day. `unclear`: the rules decline them, and nothing is
    guessed. `none`: no words were typed, so the to-do has no day."""

    status: str
    day: date | None = None


def read_day(store: Any, cfg: Any, words: str | None) -> DayReading:
    """The day the words name, read from today on the person's own clock with the language settings' own words."""
    if not (words or "").strip():
        return DayReading("none")
    language = (cfg.workspace.language or "en-US").replace("_", "-")
    if not language.lower().startswith("en"):
        return DayReading("unclear")
    settings = cfg.language
    where = zone(cfg)
    found = resolve(
        words.strip(),
        datetime.fromisoformat(store.clock()).astimezone(where),
        where,
        locale="en_US" if language.lower().startswith("en-us") else "en_GB",
        lead_words=settings.due_lead_words,
        ordinal_suffixes=settings.due_ordinal_suffixes,
        phrase_words=settings.due_phrase_words,
        number_words=settings.due_number_words,
        time_zones=settings.time_zone_abbreviations,
        sender_zone=where,
        holidays=load_holidays(settings.holiday_calendar or language),
    )
    day = found.end or found.start
    return DayReading("ok", day) if day is not None else DayReading("unclear")


def add(
    store: Any,
    cfg: Any,
    *,
    text: str,
    when: str | None = None,
    owners: list[str] | None = None,
    project: str | None = None,
    repeat: str | None = None,
    effort_minutes: int | None = None,
) -> tuple[str, list[str]]:
    """Add the to-do as the person's own. Returns its id and the changes made (the to-do, then its repeat), in order.
    Raises `TodoProblem` saying what to fix, before anything is kept, when the words, the day or the repeat aren't clear
    or the repeat doesn't fall on the day."""
    words = " ".join(text.split())
    if not words:
        raise TodoProblem("Say what to do.")
    who = list(dict.fromkeys(owners or []))
    if not who:
        raise TodoProblem("Pick who does it.")
    view = store.read()
    for person in who:
        if view.get("person", person) is None:
            raise TodoProblem("That person isn't on file.")
    if project and view.get("project", project) is None:
        raise TodoProblem("That project isn't on file.")
    day = read_day(store, cfg, when)
    if day.status == "unclear":
        raise TodoProblem("That day isn't clear. Try something like 'Friday' or 'next Tuesday', or leave it empty.")
    phrase = " ".join((repeat or "").split())
    found = None
    if phrase:
        found = repeats.read_phrase(phrase, day.day, repeats.local_today(store, cfg))
        if found.status == "unclear":
            raise TodoProblem("That repeat isn't clear. Try something like 'every Tuesday'.")
        if found.status == "off_start":
            raise TodoProblem(f"The day isn't one of those days. The first that is: {found.start}.")
    op: dict[str, Any] = {
        "op": "action.add",
        "text": words,
        "owners": who,
        "due": day.day.isoformat() if day.day else None,
        "project": project or None,
        "evidence": {"quote": words},
    }
    made = apply_as_person(store, cfg, [op], f"Added a to-do: {words}", note=words)
    outcome = store.read().get("changeset", made).data["ops"][0]
    if outcome["status"] != "applied":
        raise TodoProblem(outcome.get("reason") or "That couldn't be added.")
    action = next(r["id"] for r in outcome["records"] if r["kind"] == "action")
    changes = [made]
    if effort_minutes:
        # The person's own estimate is their own edit of the new to-do, so Undo can take it back by itself.
        fresh = store.read().get("action", action)
        edit_op = {
            "op": "record.edit",
            "record": {"kind": "action", "id": action},
            "fields": {"effort_minutes": effort_minutes},
            "read_version": fresh.version,
        }
        try:
            changes.append(apply_as_person(store, cfg, [edit_op], "Set how long a to-do takes"))
        except StoreError:
            from engine.dispatcher import undo_changeset

            undo_changeset(store, made)
            raise
    if found is not None:
        repeat_op = {
            "op": "action.repeat",
            "id": action,
            "rule": found.rule,
            "phrase": phrase,
            "start": found.start.isoformat(),
        }
        try:
            changes.append(apply_as_person(store, cfg, [repeat_op], "Set how a to-do repeats"))
        except StoreError:
            from engine.dispatcher import undo_changeset

            undo_changeset(store, made)  # a to-do whose repeat wasn't kept is not left half-made
            raise
    return action, changes
