"""Invitations waiting for the person's answer (design 6.32, 7.7): one line on Today for a calendar entry that came as
an invitation, has not been called off, starts within `steward.meetings.invitation_days_ahead` days, and that the person
has not answered. It opens the entry's page, where Accept, Maybe, Decline and Propose a time draft the answer for the
person's yes (design 6.12). Rules only: no AI run, and nothing is sent from here.

An invitation counts as unanswered when the calendar's answer for the person is "needs action"; an answer already
drafted for it (waiting, sent or failed, not withdrawn or undone) also ends the line, since the person has acted."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from engine.meeting_guests import window

#: The acts that end the line: an answer in any state but one taken back.
_TAKEN_BACK = ("withdrawn", "undone")


@dataclass(frozen=True)
class Waiting:
    """One invitation to answer: the calendar entry's id and title, when it starts, who invited (as the entry names
    them) and whether its text came from outside."""

    event: str
    title: str
    start: datetime
    organizer: str
    untrusted: bool


def _needs_answer(data: dict[str, Any]) -> bool:
    return str(data.get("response") or "").strip().casefold().replace("_", "-") in ("needs-action", "needsaction")


def _answered_by_an_act(view: Any, entry: str) -> bool:
    for act in view.list("act"):
        target = act.data.get("target") or {}
        if (
            target.get("kind") == "calendar"
            and target.get("action") == "answer"
            and entry in (target.get("about") or [])
            and act.data.get("status") not in _TAKEN_BACK
        ):
            return True
    return False


def waiting(store: Any, cfg: Any, now: datetime) -> list[Waiting]:
    """The invitations to answer, soonest first. A zero `invitation_days_ahead` turns the line off."""
    days = cfg.steward.meetings.invitation_days_ahead
    if days <= 0:
        return []
    view = store.read()
    from engine.today import zone

    here = zone(cfg)
    found: list[Waiting] = []
    for entry in view.list("event"):
        data = entry.data
        if not data.get("invitation") or data.get("cancelled") or not _needs_answer(data):
            continue
        spans = window(data, here)
        if spans is None or not now <= spans[0] <= now + timedelta(days=days):
            continue
        if _answered_by_an_act(view, entry.id):
            continue
        organizer = data.get("organizer") or {}
        found.append(
            Waiting(
                entry.id,
                data["title"],
                spans[0],
                str(organizer.get("name") or organizer.get("address") or ""),
                data.get("trust") == "untrusted",
            )
        )
    return sorted(found, key=lambda x: (x.start, x.event))
