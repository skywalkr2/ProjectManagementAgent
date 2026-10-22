"""The publisher: the only code that calls a channel (design 6.12).

An act goes out only when the person approved it and what the approval covered is the same now. `send` refuses an act
that isn't approved, recomputes the fingerprint (a difference makes the act stale and stops), runs the name check on
every part, and then, in one transaction, moves the act to `sending` with a fresh attempt key. Only after that is the
channel called, with that key. A clear answer makes the act `sent` (with the service's id) or `failed` (with the
reason the channel gave, classified by the channel). A timeout, a lost connection or a closed lid leaves it `sending`.

`resume` asks the channel what happened to every act left `sending`: sent becomes `sent`; the service has nothing
for the key, so the act is `approved` again and is never sent by itself; a channel that can't say, or isn't there,
makes it `uncertain`. It runs at start and before any send, so nothing is sent twice. An `auth` failure never
retries: the act is `failed` and waits for the person. Every change of state is an op through the applier, so each is
in the ledger; nothing here writes a record any other way.

`undo` takes a sent act back where its channel can (a mailbox act, an event it created), only after the person asked
(`act.undo`), by calling the channel once and recording `undone`, or the reason it could not, with the act left sent.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from engine import acts, outward
from engine.applier import apply_for_publisher
from engine.channels import ChannelFailed, ChannelNotSent, ChannelSent, ChannelUndone
from engine.config import Config
from engine.storage import Store, StoreError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendResult:
    """What `Publisher.send` did: the act's state afterwards (`sent`, `failed`, `stale`, `sending` when the answer
    hasn't come, or whatever `resume` found) and, for a failure, the channel's reason."""

    id: str
    status: str
    reason: str | None = None


class Publisher:
    """Sends approved acts through their channels, and settles what an earlier attempt left open. `now` and `new_key`
    are passed in (the clock and the attempt-key source) so tests never wait and never depend on randomness."""

    def __init__(
        self,
        store: Store,
        cfg: Config,
        *,
        now: Callable[[], datetime] | None = None,
        new_key: Callable[[], str] | None = None,
    ):
        self.store, self.cfg = store, cfg
        self.now = now or (lambda: datetime.now(UTC))
        self.new_key = new_key or (lambda: secrets.token_hex(16))

    # ---- the ops, each its own changeset in the ledger ---------------------------------------------------------------

    def _op(self, op: dict[str, Any], summary: str) -> None:
        apply_for_publisher(self.store, self.cfg, op, summary)

    def _status(self, act_id: str) -> str:
        found = self.store.read().get("act", act_id)
        return found.data["status"] if found is not None else "gone"

    def _stale(self, act_id: str, why: list[str]) -> None:
        self._op({"op": "act.stale", "id": act_id, "why": why}, "A yes no longer covers an act")

    # ---- sending -----------------------------------------------------------------------------------------------------

    def send(self, act_id: str) -> SendResult:
        """Carry out one approved act. Raises StoreError for an act that isn't approved, or whose content still names
        the assistant or is limited away from a recipient; the act is left as it was."""
        self._settle_attempts()
        view = self.store.read()
        found = view.get("act", act_id)
        if found is None:
            raise StoreError(f"act {act_id} doesn't exist")
        data = found.data
        if data["status"] != "approved" or data["approved"] is None:
            raise StoreError(f"this act can't be sent: it is {data['status']}, not approved")
        channel = acts.channel_of(self.store.plugins, data["channel"])
        if channel is None:
            raise StoreError(f"there is no channel {data['channel']} to send it with")
        if channel.manual or channel.send is None:
            raise StoreError("this one is carried out by you: copy it, then say it was sent")
        covered = data["approved"]
        now_print, now_parts = acts.current_fingerprint(view, self.store.plugins, data)
        if now_print != covered["fingerprint"]:
            self._stale(act_id, acts.what_changed(covered["covers"], now_parts))
            return SendResult(act_id, "stale")
        if (why := acts.acting_problem(self.cfg, self.store.plugins, data)) is not None:
            raise StoreError(why)
        outward.check_outgoing(view, self.cfg, acts.part_labels(view, self.cfg, data))
        from engine.names import People

        if (
            why := acts.audience_problem(
                view, People(self.store, self.cfg), data["sources"], acts.act_recipients(view, data)
            )
        ) is not None:
            raise StoreError(why)
        key = self.new_key()
        self._op(
            {
                "op": "act.sending",
                "id": act_id,
                "attempt_key": key,
                "fingerprint": now_print,
                "at": self.now().isoformat(),
            },
            "An act is being sent",
        )
        outgoing = acts.outgoing(self.store.read(), act_id, data)
        try:
            answer = channel.send(outgoing, key)
        except Exception as err:  # a timeout or a lost connection: the act stays `sending` until the service is asked
            log.warning("the channel %s gave no answer for act %s: %s", channel.name, act_id, type(err).__name__)
            return SendResult(act_id, "sending")
        return self._answered(act_id, key, answer)

    def _answered(self, act_id: str, key: str, answer: Any) -> SendResult:
        at = self.now().isoformat()
        if isinstance(answer, ChannelSent):
            self._op(
                {"op": "act.sent", "id": act_id, "attempt_key": key, "service_id": answer.service_id, "at": at},
                "An act went out",
            )
            return SendResult(act_id, "sent")
        if isinstance(answer, ChannelFailed):
            self._op(
                {
                    "op": "act.failed",
                    "id": act_id,
                    "attempt_key": key,
                    "kind": answer.kind,
                    "reason": answer.reason,
                    "at": at,
                },
                "An act did not go out",
            )
            return SendResult(act_id, "failed", answer.reason)
        return SendResult(act_id, "sending")  # no clear answer: it stays `sending`, and the service is asked next

    # ---- taking back -------------------------------------------------------------------------------------------------

    def undo(self, act_id: str) -> SendResult:
        """Take back a sent act the person asked to take back: the channel is called once. `undone` when it did; when it
        could not (a refusal, or no clear answer), the act stays sent and says why. Raises StoreError for an act the
        person hasn't asked to take back, or whose channel can't."""
        view = self.store.read()
        found = view.get("act", act_id)
        if found is None:
            raise StoreError(f"act {act_id} doesn't exist")
        data = found.data
        if data["status"] != "sent" or not data.get("undo_requested_at"):
            raise StoreError(
                f"this act can't be taken back: it is {data['status']}, and taking it back wasn't asked for"
            )
        channel = acts.channel_of(self.store.plugins, data["channel"])
        if channel is None or channel.undo is None:
            raise StoreError("the channel that carried it out can't take it back")
        outgoing = acts.outgoing(view, act_id, data)
        at = self.now().isoformat()
        try:
            answer = channel.undo(outgoing, data["service_id"])
        except Exception as err:  # no clear answer: the act stays sent and the person looks in the service
            log.warning("the channel %s gave no answer to undoing act %s: %s", channel.name, act_id, type(err).__name__)
            answer = None
        if isinstance(answer, ChannelUndone):
            self._op({"op": "act.undone", "id": act_id, "at": at}, "A sent act was taken back")
            return SendResult(act_id, "undone")
        failure = (
            answer
            if isinstance(answer, ChannelFailed)
            else ChannelFailed("outage", self.cfg.language.messages.undo_no_answer)
        )
        self._op(
            {"op": "act.undo_failed", "id": act_id, "kind": failure.kind, "reason": failure.reason, "at": at},
            "A sent act could not be taken back",
        )
        return SendResult(act_id, "failed", failure.reason)

    # ---- settling what an earlier attempt left open ------------------------------------------------------------------

    def _settle_attempts(self) -> list[SendResult]:
        """Ask the channel about every act left `sending`, so what an earlier attempt did is known before a send."""
        return [self._settle(f.id, f.data) for f in self.store.read().list("act") if f.data["status"] == "sending"]

    def resume(self) -> list[SendResult]:
        """Ask each channel what happened to every act left `sending`, and mark an approved act stale when what its
        yes covered changed (a restart that re-resolved an address, a template updated since). Called at start. An act
        is never sent again here."""
        settled = self._settle_attempts()
        for found in self.store.read().list("act"):
            if found.data["status"] != "approved" or found.data["approved"] is None:
                continue
            view = self.store.read()
            now_print, now_parts = acts.current_fingerprint(view, self.store.plugins, found.data)
            if now_print != found.data["approved"]["fingerprint"]:
                self._stale(found.id, acts.what_changed(found.data["approved"]["covers"], now_parts))
                settled.append(SendResult(found.id, "stale"))
        return settled

    def _settle(self, act_id: str, data: dict[str, Any]) -> SendResult:
        key = data["attempt_key"]
        at = self.now().isoformat()
        channel = acts.channel_of(self.store.plugins, data["channel"])
        if channel is None or channel.status is None:
            why = "no_channel" if channel is None else "no_status"
            self._op({"op": "act.uncertain", "id": act_id, "why": why, "at": at}, "An act may or may not have gone out")
            return SendResult(act_id, "uncertain")
        try:
            answer = channel.status(key)
        except Exception as err:
            log.warning(
                "the channel %s couldn't say what happened to act %s: %s", channel.name, act_id, type(err).__name__
            )
            answer = None
        if isinstance(answer, ChannelSent):
            self._op(
                {"op": "act.sent", "id": act_id, "attempt_key": key, "service_id": answer.service_id, "at": at},
                "An act went out",
            )
            return SendResult(act_id, "sent")
        if isinstance(answer, ChannelNotSent):
            self._op({"op": "act.reopen", "id": act_id, "attempt_key": key, "at": at}, "An act never went out")
            return SendResult(act_id, "approved")
        self._op(
            {"op": "act.uncertain", "id": act_id, "why": "lost_answer", "at": at}, "An act may or may not have gone out"
        )
        return SendResult(act_id, "uncertain")
