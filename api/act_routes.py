"""API routes for the outward act and the publisher (design 6.12): acts by state, one act with the fingerprint a yes
would cover, the person's yes, taking one back, sending (the yes and the send in one, after the yes) and the answers
for an act the app can't confirm went out.

Every change is the person's own click on that act, applied as theirs through the applier, so each is in the ledger.
Only the publisher calls a channel, and only for an act whose yes still covers it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    ActApproveIn,
    ActFailureView,
    ActListView,
    ActRecipientView,
    ActResultView,
    ActSettleIn,
    ActView,
)
from engine import acts
from engine.applier import apply_as_person
from engine.config import Config
from engine.names import People
from engine.publisher import Publisher
from engine.storage import Store, StoreError
from engine.worker import Events, Worker


def build_act_router(cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except (StoreError, ValueError, KeyError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

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
        approval = data.get("approved")
        failure = data.get("failure")
        return ActView(
            id=found.id,
            version=found.version,
            channel=data["channel"],
            channel_label=channel.label if channel is not None else data["channel"],
            kind=data["target"]["kind"],
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

    @r.get("/acts")
    def list_acts(status: str | None = None) -> ActListView:
        """The acts, newest first; with `status`, only those in that state (Waiting to go out reads draft, approved,
        stale, failed and uncertain)."""
        found = [a for a in store.read().list("act") if status is None or a.data["status"] == status]
        found.sort(key=lambda a: int(a.id.rpartition("-")[2]), reverse=True)
        return ActListView(acts=[view_of(a) for a in found])

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
