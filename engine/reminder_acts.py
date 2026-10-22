"""Reminders that reach a person who is away from the app (design 6.12): the engine drafts one act for each reminder
that comes due within the look-ahead, and keeps them true.

When the person has chosen an account (`steward.reminders.where` calendar or mail, and `where_account`) that can act,
each open to-do whose reminder time is within `look_ahead_hours` gets one act: an event with an alarm on the account's
own calendar, or a mail to the person's own address, worded by the core's reminder template
(`engine/reminder_content.py` works out the exact act). A reminder time never gets a second act. A snooze, a cleared
reminder, or a to-do that is done, dropped or put on hold withdraws an act that hasn't gone out. While the person's
standing yes stands and matches, the engine approves the act and the publisher sends it; otherwise the draft waits in
Waiting to go out for the person's own yes. All of that is decided by the applier's invariants (`act-reminder`,
`act-approval`), never here.

"In the app's calendar" is not an act: the same pass keeps a to-do's reminder entry on the app's own calendar
(`engine/reminder_entries.py`), local data that needs no yes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from engine import act_accounts, acts, reminder_content, reminder_entries, reminder_template, standing_yes
from engine.applier import apply_for_publisher, apply_for_reminders
from engine.blocked import standing_hold
from engine.config import Config
from engine.names import People
from engine.publisher import Publisher
from engine.storage import Store, StoreError

log = logging.getLogger(__name__)

#: The states an act can still be withdrawn from (it hasn't gone out and isn't going now).
_WITHDRAWABLE = acts.EDITABLE


class ReminderActs:
    """One pass over the to-dos and the reminder acts. `now` is passed in, so tests never wait."""

    def __init__(self, store: Store, cfg: Config, *, now: Callable[[], datetime] | None = None, publisher: Any = None):
        self.store, self.cfg = store, cfg
        self.now = now or (lambda: datetime.now(UTC))
        self.publisher = publisher or Publisher(store, cfg, now=self.now)
        #: What was refused and isn't tried again until it changes: no changeset is written twice for the same thing.
        self._tried: set[tuple[Any, ...]] = set()

    # ---- what is set up ----------------------------------------------------------------------------------------------

    def enabled(self) -> bool:
        """Whether reminders are set up to go to an account that can carry them now."""
        where = self.cfg.steward.reminders
        return (
            where.where in reminder_content.FORMS
            and bool(where.where_account)
            and act_accounts.acting_on(self.cfg, where.where_account)
            and reminder_content.channel_for(self.store.plugins, where.where_account, where.where) is not None
        )

    # ---- the pass ----------------------------------------------------------------------------------------------------

    def sweep(self) -> bool:
        """Withdraw what no longer holds, draft what is due, approve under the standing yes and send what it approved.
        Returns whether anything changed."""
        changed = self.withdraw()
        changed = self.keep_calendar() or changed
        if self.enabled():
            changed = self.draft() or changed
            changed = self.approve() or changed
        return self.send() or changed

    def _reminder_acts(self) -> list[Any]:
        return [a for a in self.store.read().list("act") if a.data.get("reminder")]

    def withdraw(self) -> bool:
        """Withdraw each reminder act that hasn't gone out whose to-do was snoozed, cleared, finished, dropped or put on
        hold."""
        changed = False
        view = self.store.read()
        for found in self._reminder_acts():
            data = found.data
            if data["status"] not in _WITHDRAWABLE:
                continue
            action = view.get("action", data["reminder"])
            why: str | None = None
            if action is None or action.data.get("status") != "open" or standing_hold(view, action.data):
                why = "ended"
            elif not action.data.get("remind_at") or reminder_content.instant(
                action.data["remind_at"]
            ) != reminder_content.instant(data["reminder_at"]):
                why = "moved"
            if why is None:
                continue
            try:
                apply_for_publisher(
                    self.store,
                    self.cfg,
                    {"op": "act.reminder_withdrawn", "id": found.id, "why": why, "at": self.now().isoformat()},
                    "A reminder act was withdrawn",
                )
                changed = True
            except StoreError as err:
                log.warning("Couldn't withdraw the reminder act %s: %s", found.id, err)
        return changed

    def keep_calendar(self) -> bool:
        """Keep each to-do's reminder entry on the app's own calendar true. With the app's calendar chosen, an open
        to-do whose reminder time is still ahead gets its entry, or has the one it has moved to that time; whatever
        the choice, an entry whose reminder was cleared, or whose to-do is done, dropped or on hold, is removed."""
        changed = False
        view = self.store.read()
        now = self.now()
        wanted = self.cfg.steward.reminders.where == "app"
        for action in view.list("action"):
            have = reminder_entries.entries_of(view, action.id)
            at = reminder_entries.due_entry(view, action, now)
            if at is None:
                cleared = bool(have) and (
                    action.data.get("status") != "open"
                    or standing_hold(view, action.data)
                    or not action.data.get("remind_at")
                )
                at_op = None if cleared else False
            else:
                at_op = at if wanted and (not have or reminder_content.instant(have[0].data["start"]) != at) else False
            if at_op is False or ("entry", action.id, at_op) in self._tried:
                continue
            try:
                apply_for_reminders(
                    self.store,
                    self.cfg,
                    {
                        "op": "reminder.entry",
                        "action": action.id,
                        **({"at": at_op.isoformat()} if at_op is not None else {}),
                    },
                    "A reminder moved on the calendar" if at_op is not None else "A reminder left the calendar",
                )
                changed = True
            except StoreError as err:
                self._tried.add(("entry", action.id, at_op))
                log.warning("Couldn't keep the calendar entry for %s: %s", action.id, err)
        return changed

    def draft(self) -> bool:
        """Draft one act for each open to-do whose reminder time is within the look-ahead and has none yet."""
        changed = False
        where = self.cfg.steward.reminders
        now = self.now()
        until = now + timedelta(hours=where.look_ahead_hours)
        view = self.store.read()
        have = {(a.data["reminder"], reminder_content.instant(a.data["reminder_at"])) for a in self._reminder_acts()}
        person = People(self.store, self.cfg).pm
        if person is None:
            return False
        address = reminder_content.own_address(view, person) if where.where == "mail" else None
        channel = reminder_content.channel_for(self.store.plugins, where.where_account, where.where)
        if channel is None or (where.where == "mail" and not address):
            return False
        for action in view.list("action"):
            d = action.data
            if d.get("status") != "open" or standing_hold(view, d) or not d.get("remind_at"):
                continue
            at = reminder_content.instant(d["remind_at"])
            key = (action.id, at)
            if not now <= at <= until or key in have or ("draft", *key) in self._tried:
                continue
            try:
                exp = reminder_content.expected(
                    self.store,
                    self.cfg,
                    view,
                    action,
                    at,
                    form=where.where,
                    account=where.where_account,
                    channel=channel,
                    person=person,
                    address=address,
                )
                apply_for_reminders(
                    self.store,
                    self.cfg,
                    {
                        "op": "act.draft",
                        "channel": exp.channel,
                        "target": exp.draft_target(),
                        "parts": exp.parts,
                        "template": exp.template,
                        "account": exp.account,
                        "reminder": {"action": action.id, "at": at.isoformat()},
                    },
                    "A reminder drafted",
                )
                changed = True
            except (StoreError, reminder_template.TemplateError) as err:
                self._tried.add(("draft", *key))
                log.warning("Couldn't draft the reminder for %s: %s", action.id, err)
        return changed

    def approve(self) -> bool:
        """Approve, under the standing yes, each reminder draft that matches it. A draft that doesn't stays for the
        person's own yes."""
        yes = standing_yes.active(self.store.read())
        if yes is None:
            return False
        changed = False
        for found in self._reminder_acts():
            if found.data["status"] != "draft" or ("approve", found.id, found.version, yes.id) in self._tried:
                continue
            view = self.store.read()
            try:
                apply_for_reminders(
                    self.store,
                    self.cfg,
                    {
                        "op": "act.approve",
                        "id": found.id,
                        "fingerprint": acts.current_fingerprint(view, self.store.plugins, found.data)[0],
                        "by_standing": yes.id,
                    },
                    "A reminder approved under your standing yes",
                    standing=True,
                )
                changed = True
            except StoreError as err:
                self._tried.add(("approve", found.id, found.version, yes.id))
                log.info("The reminder act %s waits for the person's own yes: %s", found.id, err)
        return changed

    def send(self) -> bool:
        """Send each reminder act the standing yes approved. The publisher recomputes what the yes covered first."""
        changed = False
        for found in self._reminder_acts():
            approval = found.data.get("approved") or {}
            if found.data["status"] != "approved" or not approval.get("standing_yes"):
                continue
            try:
                self.publisher.send(found.id)
                changed = True
            except StoreError as err:
                log.warning("Couldn't send the reminder act %s: %s", found.id, err)
        return changed
