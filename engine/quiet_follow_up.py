"""The follow-up to someone who owes the person a promise that has gone quiet (design 6.32, 7.7): written by rules from
the wording sheet, with no AI run, for the person to send as an act (design 6.12) after their yes.

Only a promise someone else owes the person gets one; a promise the person made to someone has no chase, the person's
own update being theirs to write."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from engine import people_memory
from engine.names import People


@dataclass(frozen=True)
class FollowUp:
    """A drafted follow-up: who it is for (a person id), its subject and its body."""

    person: str
    subject: str
    body: str


def draft(store: Any, cfg: Any, action: str, today: date) -> FollowUp | None:
    """The follow-up for a promise that has gone quiet, or None when it hasn't, or when the person is the one who owes
    it."""
    quiet = next((q for q in people_memory.quiet_promises(store, cfg, today) if q.action == action), None)
    if quiet is None or quiet.direction != "from":
        return None
    words = cfg.language.messages
    people = People(store, cfg)
    lines = [
        words.greeting.format(first_name=people.first_name(quiet.person)),
        "",
        words.quiet_intro,
        quiet.text,
        "",
        words.nudge_ask_one,
        "",
        words.closing,
    ]
    return FollowUp(quiet.person, words.quiet_subject.format(text=quiet.text), "\n".join(lines))
