"""API routes for reminders on actions (design 6.32): setting one, snoozing one, and clearing one.

A reminder is an action's `remind_at`. Changing it is the person's own `record.edit` applied as theirs with Undo; it is
not a correction of the assistant's work, so it records no learning signal."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    Applied,
    ReminderAccountView,
    ReminderExampleView,
    ReminderIn,
    ReminderTextView,
    ReminderWhereView,
    StandingYesIn,
    StandingYesView,
)
from engine import act_accounts, reminder_content, reminder_lines, reminder_template, standing_yes
from engine.applier import apply_as_person
from engine.config import Config
from engine.intake import IntakeError
from engine.names import People
from engine.storage import Store, StoreError
from engine.today import zone
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_reminder_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, IntakeError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    def text_of(form: reminder_template.Rendered) -> ReminderTextView:
        return ReminderTextView(subject=form.subject, body=form.body, event_title=form.event_title)

    @r.get("/reminders/where")
    def where() -> ReminderWhereView:
        """Where reminders reach the person when the app isn't open: the choice, the standing yes if one stands and
        whether it is stale, the accounts that can carry a reminder, and the exact reminder as it would go."""
        view = store.read()
        chosen = cfg.steward.reminders
        root = reminder_content.root_of(store)
        people = People(store, cfg)
        yes = standing_yes.active(view)
        standing = None
        stale: list[str] = []
        if yes is not None:
            stale = standing_yes.stale_reasons(store, cfg, view, people, yes)
            standing = StandingYesView(
                id=yes.id,
                form=yes.data["form"],
                account=yes.data["account"],
                account_label=act_accounts.label_of(store, cfg, yes.data["account"]),
                given_at=yes.data["given_at"],
                template_version=yes.data["template"]["version"],
                stale=stale,
            )
        elif chosen.where in reminder_content.FORMS and chosen.where_account:
            if not act_accounts.acting_on(cfg, chosen.where_account):
                stale = ["acting"]
        accounts = [
            ReminderAccountView(
                id=a.id,
                label=a.label,
                mail=reminder_content.channel_for(store.plugins, a.id, "mail") is not None,
                calendar=reminder_content.channel_for(store.plugins, a.id, "calendar") is not None,
            )
            for a in act_accounts.known(store, cfg)
            if a.acting
        ]
        shown = reminder_template.example(root, at=worker.now(), tz=zone(cfg), app=cfg.workspace.name)
        return ReminderWhereView(
            where=chosen.where,
            account=chosen.where_account or None,
            account_label=act_accounts.label_of(store, cfg, chosen.where_account or None),
            standing=standing,
            stale=stale,
            accounts=[a for a in accounts if a.mail or a.calendar],
            template_version=reminder_template.version(root),
            example=ReminderExampleView(item=text_of(shown["item"]), plain=text_of(shown["plain"])),
            look_ahead_hours=chosen.look_ahead_hours,
        )

    @r.post("/reminders/yes")
    def give_yes(body: StandingYesIn) -> Applied:
        """The person's yes for reminders: ends the one that stands, if any, and gives this one, as one change with
        Undo. Refused in plain words when the reminder changed since they looked or the account can't carry it."""
        ops: list[dict[str, Any]] = []
        if (stands := standing_yes.active(store.read())) is not None:
            ops.append({"op": "standing_yes.end", "id": stands.id})
        ops.append(
            {
                "op": "standing_yes.give",
                "account": body.account,
                "form": body.form,
                "template_version": body.template_version,
            }
        )
        cs_id = guard(lambda: apply_as_person(store, cfg, ops, "Said yes to reminders going without asking"))
        events.changed()
        return Applied(changeset=cs_id)

    @r.post("/reminders/yes/end")
    def end_yes() -> Applied:
        """End the standing yes for reminders, with Undo."""
        stands = standing_yes.active(store.read())
        if stands is None:
            raise HTTPException(status_code=409, detail="nothing to end")
        op = {"op": "standing_yes.end", "id": stands.id}
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Ended the yes to reminders going without asking"))
        events.changed()
        return Applied(changeset=cs_id)

    @r.post("/reminders/{action_id}")
    def remind(action_id: str, body: ReminderIn) -> Applied:
        """Set an action's reminder to a snooze choice or to a time the person picked, with Undo; with neither, clear
        it. A time that has passed, or a choice with no time left, is refused in plain words."""
        record = store.read().get("action", action_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"action {action_id} doesn't exist")
        if body.choice is not None and body.at is not None:
            raise HTTPException(status_code=409, detail="Pick a choice or a time, not both.")
        value: str | None = None
        if body.choice is not None or body.at is not None:
            found = reminder_lines.resolve(cfg, worker.now(), choice=body.choice, at=body.at)
            if found.status != "known" or found.at is None:
                raise HTTPException(
                    status_code=409,
                    detail="That time has passed. Pick a time that is still ahead."
                    if body.at is not None
                    else "That choice has no time left. Pick another.",
                )
            value = found.at.isoformat()
        elif record.data.get("remind_at") is None:
            raise HTTPException(status_code=409, detail="nothing to change")
        op = {
            "op": "record.edit",
            "record": {"kind": "action", "id": action_id},
            "fields": {"remind_at": value},
            "read_version": body.read_version or record.version,
        }
        cs_id = guard(lambda: apply_as_person(store, cfg, [op], "Changed on screen"))
        events.changed()
        return Applied(changeset=cs_id)

    return r
