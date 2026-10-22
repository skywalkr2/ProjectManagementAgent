"""API routes for the outward act and the publisher (design 6.12): acts by state, one act with the fingerprint a yes
would cover, the person's yes, taking one back, sending (the yes and the send in one, after the yes) and the answers
for an act the app can't confirm went out.

Every change is the person's own click on that act, applied as theirs through the applier, so each is in the ledger.
The person also drafts an act here (a reply, a change to their mail, an answer to an invitation), and asks what can be
done about a saved message or an invitation and which times are free to propose.
Only the publisher calls a channel, and only for an act whose yes still covers it."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from api.schemas import (
    ActAboutView,
    ActAccountsView,
    ActAccountView,
    ActApproveIn,
    ActDraftIn,
    ActFailureView,
    ActListView,
    ActOptionsView,
    ActRecipientView,
    ActResultView,
    ActSettleIn,
    ActView,
    FreeSlotsView,
    FreeSlotView,
)
from engine import act_accounts, acts, propose_times, reply_recipients
from engine.applier import apply_as_person
from engine.channels import COPY
from engine.channels_mailbox import ANSWERS as MAILBOX_ANSWERS
from engine.channels_mailbox import NO_PROPOSE
from engine.config import Config
from engine.names import People
from engine.ops import ACT_ACTIONS, ACT_REPLY_ACTIONS, ActDraftOp
from engine.publisher import Publisher
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_act_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    def about_of(rid: str) -> ActAboutView:
        """One thing an act is about, labeled for the screen."""
        view = store.read()
        message = view.get("source", rid)
        if message is not None:
            data = message.data
            sent = data.get("sent_at") or data.get("received_at")
            return ActAboutView(
                id=rid,
                kind="message",
                title=data.get("title") or "",
                sender=(data.get("watched") or {}).get("author"),
                when=str(sent)[:10] if sent else None,
            )
        entry = view.get("event", rid)
        if entry is not None:
            return ActAboutView(
                id=rid, kind="event", title=entry.data["title"], when=entry.data["start"], end=entry.data.get("end")
            )
        return ActAboutView(id=rid, kind="missing", title="")

    def view_of(found: Any) -> ActView:
        view = store.read()
        data = found.data
        people = People(store, cfg)
        called = {c.key: c.reasons for c in acts.callouts(view, people.pm, data, act_id=found.id)}
        recipients = []
        for rec in data["target"].get("recipients") or []:
            key = acts.recipient_key(rec.get("person"), rec["address"])
            address = acts.current_address(view, rec)
            recipients.append(
                ActRecipientView(
                    key=key,
                    person=rec.get("person"),
                    name=people.name(rec["person"]) if rec.get("person") else rec["address"],
                    address=address,
                    role=rec["role"],
                    reasons=list(called.get(key, ())),
                )
            )
        channel = acts.channel_of(store.plugins, data["channel"])
        target = data["target"]
        account = data.get("account")
        undo_channel = channel is not None and channel.undo is not None
        approval = data.get("approved")
        failure = data.get("failure")
        return ActView(
            id=found.id,
            version=found.version,
            channel=data["channel"],
            channel_label=channel.label if channel is not None else data["channel"],
            kind=target["kind"],
            action=acts.what(data),
            about=[about_of(rid) for rid in target.get("about") or []],
            account=account,
            account_label=act_accounts.label_of(store, cfg, account),
            acting=act_accounts.acting_on(cfg, account),
            copied_because="acting_off" if data.get("intended_channel") else None,
            intended_channel=data.get("intended_channel"),
            label=target.get("label"),
            start=target.get("start"),
            end=target.get("end"),
            title=target.get("title"),
            alarm_minutes=target.get("alarm_minutes"),
            answer=target.get("answer"),
            proposed_start=target.get("proposed_start"),
            proposed_end=target.get("proposed_end"),
            undoable=data["status"] == "sent"
            and data.get("sent_by") == "publisher"
            and undo_channel
            and acts.undoable(data)
            and not data.get("undo_requested_at"),
            undone_at=data.get("undone_at"),
            undo_failure=ActFailureView(**data["undo_failure"]) if data.get("undo_failure") else None,
            status=data["status"],
            parts=dict(data["parts"]),
            recipients=recipients,
            calendar=data["target"].get("calendar"),
            when=data["target"].get("when"),
            folder=data["target"].get("folder"),
            template=(data.get("template") or {}).get("name"),
            fingerprint=acts.current_fingerprint(view, store.plugins, data)[0],
            approved_by=approval["by"] if approval else None,
            approved_at=approval["at"] if approval else None,
            withheld=acts.name_problem(view, cfg, data),
            failure=ActFailureView(**failure) if failure else None,
            why=list(data.get("why") or []),
            service_id=data.get("service_id"),
            sent_at=data.get("sent_at"),
            sent_by=data.get("sent_by"),
            made_by=data["made_by"],
            sensitivity=data["sensitivity"],
        )

    def need(act_id: str) -> Any:
        found = store.read().get("act", act_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"act {act_id} doesn't exist")
        return found

    def status_of(act_id: str) -> str:
        return store.read().get("act", act_id).data["status"]

    def serving(account: str, kind: str, action: str) -> tuple[str, Any] | None:
        """The channel that serves this kind of account and does this action, else the first that serves the account
        for this kind of target (so the draft is refused with its own reason); None when none serves the account."""
        kind_of = act_accounts.kind_of(account)
        found = [
            (name, channel)
            for name, channel in sorted(store.plugins.channels().items())
            if not channel.manual and channel.accounts and kind_of in channel.accounts and kind in channel.kinds
        ]
        return next(((n, c) for n, c in found if c.takes(kind, action)), found[0] if found else None)

    def message_of(view: Any, record: str) -> str:
        """The saved message or entry a record stands for: a reply owed stands for the message that asked."""
        action = view.get("action", record)
        return (action.data.get("replies_to") or "") if action is not None else record

    @r.get("/acts/options")
    def options(record: str) -> ActOptionsView:
        """What the person can do about a saved message, a calendar entry or a reply owed: the account it came in on,
        whether acting is on for it, the actions its channel does and the ways an invitation can be answered."""
        view = store.read()
        rid = message_of(view, record)
        kind = "message" if view.get("source", rid) else "event" if view.get("event", rid) else None
        if kind is None:
            return ActOptionsView(record=record, kind="missing")
        account = act_accounts.of_record(view, store, cfg, rid)
        acting = act_accounts.acting_on(cfg, account)
        carrier = (
            serving(account, "message" if kind == "message" else "calendar", "reply" if kind == "message" else "answer")
            if account
            else None
        )
        channel = carrier[1] if carrier else None
        mailbox = account is not None and act_accounts.kind_of(account) == act_accounts.MAILBOX
        out = ActOptionsView(
            record=rid,
            kind=kind,
            account=account,
            account_label=act_accounts.label_of(store, cfg, account),
            acting=acting,
            channel_label=channel.label if channel else None,
        )
        if kind == "message":
            out.actions = list(ACT_REPLY_ACTIONS)
            out.can_act = bool(channel and acting and channel.takes("message", "reply"))
            if account and channel is not None:
                serves = serving(account, "mailbox", "archive")
                mail = serves[1] if serves else None
                if mailbox:
                    out.folder_source = act_accounts.name_of(account)
                out.actions += [
                    a
                    for a in ("archive", "move", "label", "mark_read")
                    if mail is not None and mail.takes("mailbox", a) and (a != "move" or out.folder_source)
                ]
        elif channel is not None and channel.takes("calendar", "answer"):
            out.can_act = acting
            out.answers = list(MAILBOX_ANSWERS) if mailbox else ["accepted", "tentative", "declined", "propose"]
            out.propose_refusal = NO_PROPOSE if mailbox else None
        return out

    @r.get("/acts/accounts")
    def accounts() -> ActAccountsView:
        """The accounts an act can go through, each with the person's switch for letting the assistant act on it after
        their yes (the `watch.acting` setting). `sign_in` names the sign-in a signed-in account belongs to, which the
        screen starts with `acting` to ask the service for the wider access; a plain mailbox has none."""
        sign_ins = store.plugins.sign_ins()
        found = []
        for info in act_accounts.known(store, cfg):
            sign_in = sign_ins.get(act_accounts.kind_of(info.id))
            found.append(
                ActAccountView(
                    id=info.id,
                    label=info.label,
                    acting=info.acting,
                    sign_in=sign_in.name if sign_in is not None else None,
                    can_act=sign_in is None or bool(sign_in.acting_scopes),
                )
            )
        return ActAccountsView(accounts=found)

    @r.get("/acts/free-slots")
    def free_slots(about: str) -> FreeSlotsView:
        """The free times to offer when proposing another time for the calendar entry `about`: each as long as the
        entry, starting a gap in the working week, earliest first."""
        found = propose_times.slots(store.read(), cfg, worker.now(), about)
        return FreeSlotsView(slots=[FreeSlotView(start=s.start.isoformat(), end=s.end.isoformat()) for s in found])

    @r.post("/acts")
    def draft(body: ActDraftIn) -> ActView:
        """The person drafts an act, applied as theirs with the account and channel chosen as the engine does: the
        account named, else the one the message or invitation came in on. Acting off for the account makes it a Copy
        act (`copied_because`). Nothing is sent. A draft its channel can't carry (proposing a time through a plain
        mailbox, a move the channel doesn't do) is refused with the reason."""
        view = store.read()
        what = body.action or ACT_ACTIONS[body.kind][0]
        account = body.account
        if account is None:
            ids = [body.in_reply_to] if what in ACT_REPLY_ACTIONS and body.in_reply_to else list(body.about)
            came_in = {a.lower(): a for rid in ids if (a := act_accounts.of_record(view, store, cfg, rid))}
            if len(came_in) > 1:
                raise HTTPException(status_code=409, detail="These came in on different accounts; draft one for each.")
            account = next(iter(came_in.values()), None)
            if account is None and what in ("send", "create"):
                account = act_accounts.last_picked(view)
        if body.answer == "propose" and account is not None and act_accounts.kind_of(account) == act_accounts.MAILBOX:
            raise HTTPException(status_code=409, detail=NO_PROPOSE)
        recipients = [r.model_dump(mode="json", exclude_none=True) for r in body.recipients]
        if body.kind == "message" and not recipients and what in ("reply", "reply_all") and body.in_reply_to:
            recipients = reply_recipients.of_message(ws, view, cfg, body.in_reply_to, what)
        target = {
            "kind": body.kind,
            "action": body.action,
            "recipients": recipients,
            "about": body.about,
            "folder": body.folder,
            "label": body.label,
            "answer": body.answer,
            "proposed_start": body.proposed_start,
            "proposed_end": body.proposed_end,
        }
        carrier = serving(account, body.kind, what) if account else None
        op: dict[str, Any] = {
            "op": "act.draft",
            "channel": carrier[0] if carrier else COPY.name,
            "target": {k: v for k, v in target.items() if v not in (None, [])},
            "parts": body.parts,
        }
        if account:
            op["account"] = account
        if body.in_reply_to:
            op["in_reply_to"] = body.in_reply_to
        try:
            ActDraftOp.model_validate(op)
        except ValidationError as err:
            # The rule's own words ("a move names the folder"), never the raw input the validator echoes.
            said = "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in err.errors())
            raise HTTPException(status_code=409, detail=said) from None
        cs = guard(lambda: apply_as_person(store, cfg, [op], "Drafted an act"))
        events.changed()
        made = store.read().get("changeset", cs).data["ops"][0]["records"][0]["id"]
        return view_of(need(made))

    @r.get("/acts")
    def list_acts(
        status: Annotated[list[str] | None, Query()] = None, limit: Annotated[int | None, Query(ge=1)] = None
    ) -> ActListView:
        """The acts, newest first; with `status` (repeat it for several), only those in one of those states (Waiting to
        go out reads draft, approved, stale, failed and uncertain), and with `limit`, at most that many."""
        found = [a for a in store.read().list("act") if not status or a.data["status"] in status]
        found.sort(key=lambda a: int(a.id.rpartition("-")[2]), reverse=True)
        return ActListView(acts=[view_of(a) for a in found[:limit]])

    @r.get("/acts/{act_id}")
    def read_act(act_id: str) -> ActView:
        """One act: its exact content and target, the fingerprint a yes would cover and the recipients called out."""
        return view_of(need(act_id))

    @r.post("/acts/{act_id}/approve")
    def approve(act_id: str, body: ActApproveIn) -> ActResultView:
        """The person's yes on this exact act: the fingerprint their screen showed and the recipients called out they
        acknowledged. Nothing is sent. A different fingerprint, or a recipient not acknowledged, is refused."""
        need(act_id)
        op = {"op": "act.approve", "id": act_id, "fingerprint": body.fingerprint, "acknowledged": body.acknowledged}
        cs = guard(lambda: apply_as_person(store, cfg, [op], "Said yes to an act"))
        events.changed()
        return ActResultView(id=act_id, status=status_of(act_id), changeset=cs)

    @r.post("/acts/{act_id}/withdraw")
    def withdraw(act_id: str) -> ActResultView:
        """Take an act back: it will not go. Undo brings it back as it was."""
        need(act_id)
        cs = guard(lambda: apply_as_person(store, cfg, [{"op": "act.withdraw", "id": act_id}], "Took an act back"))
        events.changed()
        return ActResultView(id=act_id, status=status_of(act_id), changeset=cs)

    @r.post("/acts/{act_id}/send")
    def send(act_id: str, body: ActApproveIn) -> ActResultView:
        """Approve and send in one, after the yes. An act already approved is sent as it stands, and only when the
        fingerprint named is the one the yes covers. The publisher checks again at send time."""
        found = need(act_id)
        cs: str | None = None
        if found.data["status"] != "approved":
            op = {"op": "act.approve", "id": act_id, "fingerprint": body.fingerprint, "acknowledged": body.acknowledged}
            cs = guard(lambda: apply_as_person(store, cfg, [op], "Said yes to an act"))
        elif found.data["approved"]["fingerprint"] != body.fingerprint:
            raise HTTPException(status_code=409, detail="This act is different from the one you were shown.")
        sent = guard(lambda: Publisher(store, cfg, now=worker.now).send(act_id))
        events.changed()
        return ActResultView(id=act_id, status=sent.status, reason=sent.reason, changeset=cs)

    @r.post("/acts/{act_id}/undo")
    def undo(act_id: str) -> ActResultView:
        """Take back a sent act where its channel can (a mailbox act, an event it created): the person's request is
        recorded as theirs, then the channel is asked once. A refusal or no answer leaves the act sent, with the reason
        on it. A sent message, or a change or answer others were told of, is refused."""
        need(act_id)
        cs = guard(lambda: apply_as_person(store, cfg, [{"op": "act.undo", "id": act_id}], "Asked to take an act back"))
        result = guard(lambda: Publisher(store, cfg, now=worker.now).undo(act_id))
        events.changed()
        return ActResultView(id=act_id, status=status_of(act_id), reason=result.reason, changeset=cs)

    @r.post("/acts/{act_id}/settle")
    def settle(act_id: str, body: ActSettleIn) -> ActResultView:
        """The person's answer for an act the app can't confirm went out (or one they carried out themselves): `sent`
        marks it sent; `again` approves it again as it is and sends it, or, when what the yes covered changed, makes it
        stale and needs a new yes. Undo takes `sent` back."""
        need(act_id)
        name = "act.confirm_sent" if body.answer == "sent" else "act.resend"
        cs = guard(lambda: apply_as_person(store, cfg, [{"op": name, "id": act_id}], "Answered about an act"))
        events.changed()
        if body.answer == "again" and status_of(act_id) == "approved":
            sent = guard(lambda: Publisher(store, cfg, now=worker.now).send(act_id))
            events.changed()
            return ActResultView(id=act_id, status=sent.status, reason=sent.reason, changeset=cs)
        return ActResultView(id=act_id, status=status_of(act_id), changeset=cs)

    return r
