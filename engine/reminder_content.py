"""What a reminder act says and where it goes (design 6.12): the one place that works out the exact act for a to-do's
reminder, so the engine that drafts it and the invariant that lets a standing yes approve it read the same answer.

A reminder act goes only to the person themselves, in one of two forms on a signed-in account or a mailbox: a message
to their own address (`mail`), or an event with an alarm on the account's own calendar (`calendar`). Its words are the
core's reminder template rendered for the to-do, in the item's own form or, when the to-do is more sensitive than the
account may hold, the plain form. (A reminder in the app's own calendar is local data, kept by
`engine/reminder_entries.py`, and is no act.) Everything here reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine import act_accounts, reminder_template
from engine.today import zone

#: What the act's calendar says for the account's own calendar, which the account's channel resolves.
OWN_CALENDAR = "own"
#: The forms a reminder act takes: an event with an alarm on the account's own calendar, or a message to the person.
FORMS = ("calendar", "mail")
#: The levels a to-do's words may have, least sensitive first.
LEVELS = ("open", "internal", "restricted")
#: The kind of way of reaching a person the mail goes to.
ADDRESS_KIND = "email"


def root_of(store: Any) -> Path:
    """The workspace folder: the one that holds the store's database."""
    return Path(store.path).parent


def action_level(view: Any, action: Any) -> str:
    """How sensitive a to-do's words are: the most sensitive level of the saved input it came from, never below
    internal (a to-do the person made themselves is internal)."""
    levels = ["internal"]
    source = view.get("source", action.data["source"]) if action.data.get("source") else None
    if source is not None:
        levels.append(source.data.get("sensitivity") or "internal")
    return max((lv for lv in levels if lv in LEVELS), key=LEVELS.index)


def plain_needed(cfg: Any, level: str) -> bool:
    """Whether a to-do at this level goes out in the plain form: it is above what the account may hold."""
    return LEVELS.index(level) > LEVELS.index(cfg.steward.reminders.allowed_data)


def own_address(view: Any, person: str | None) -> str:
    """The person's own address as it stands now, lowercased; empty when the record holds none."""
    found = view.get("person", person) if person else None
    reach = (found.data.get("how_to_reach") or {}) if found is not None else {}
    return str(reach.get(ADDRESS_KIND, "")).strip().lower()


def channel_for(plugins: Any, account: str, form: str) -> str | None:
    """The channel that carries a reminder in this form on this account: one that serves the kind of account and
    declares the action (a message's `send`, an event's `create`). None when the account has none."""
    kind, action = ("message", "send") if form == "mail" else ("calendar", "create")
    for name, channel in sorted(plugins.channels().items()):
        if channel.manual or not channel.accounts:
            continue
        if act_accounts.kind_of(account) in channel.accounts and channel.takes(kind, action):
            return name
    return None


def instant(value: Any) -> datetime:
    """A moment as an aware UTC datetime, from text or a datetime."""
    at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return at.astimezone(UTC)


@dataclass(frozen=True)
class Expected:
    """The exact reminder act for one to-do's reminder time on one account: what it is drafted as, and what the
    standing yes checks the act against."""

    channel: str
    account: str
    form: str
    template: dict[str, str]
    target: dict[str, Any]
    parts: dict[str, str]
    plain: bool

    def draft_target(self) -> dict[str, Any]:
        """The target as the draft op takes it."""
        return {key: value for key, value in self.target.items() if value not in (None, [])}


def expected(
    store: Any,
    cfg: Any,
    view: Any,
    action: Any,
    at: Any,
    *,
    form: str,
    account: str,
    channel: str,
    person: str,
    address: str | None,
) -> Expected:
    """The reminder act for `action` at the reminder time `at`, in `form` on `account` through `channel`, to `person`
    (at `address`, for a mail). Raises `reminder_template.TemplateError` when the template can't be read."""
    root = root_of(store)
    moment = instant(at)
    plain = plain_needed(cfg, action_level(view, action))
    rendered = reminder_template.render(
        root,
        text=str(action.data["text"]),
        at=moment,
        tz=zone(cfg),
        app=cfg.workspace.name,
        plain=plain,
    )
    template = {"name": reminder_template.NAME, "version": reminder_template.version(root)}
    if form == "mail":
        target: dict[str, Any] = {
            "kind": "message",
            "action": "send",
            "recipients": [{"person": person, "address": address, "kind": ADDRESS_KIND, "role": "to"}],
        }
        parts = {"subject": rendered.subject, "body": rendered.body}
    else:
        minutes = int(reminder_template.load(root)["event_minutes"])
        target = {
            "kind": "calendar",
            "action": "create",
            "calendar": OWN_CALENDAR,
            "start": moment.isoformat(),
            "end": (moment + timedelta(minutes=minutes)).isoformat(),
            "title": rendered.event_title,
            "alarm_minutes": 0,
        }
        parts = {"note": rendered.body}
    return Expected(channel, account, form, template, target, parts, plain)
