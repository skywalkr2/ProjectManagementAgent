"""The core's `mailbox` channel: a plain mailbox acts through its own servers (design 6.12).

Messages go out through the account's outgoing server (SMTP over TLS) and a copy is saved to the sent folder unless the
server does that itself. Archive, move, label and mark read go over IMAP, finding each message by its Message-ID in the
account's folder. An answer to an invitation is a message to the organizer with the iTIP reply attached.

The Message-ID of an outgoing message is made from the attempt key, so `status` can ask the sent folder whether an
attempt went out. A server may keep no copy, so a message not found there is `ChannelUnknown`, never `ChannelNotSent`.

Each act makes one connection to each server it needs, waits at most the account's timeout, and never retries: a server
that says to try later is an `outage` and the person decides. A message is never deleted.
"""

from __future__ import annotations

import contextlib
import imaplib
import logging
import re
import smtplib
import socket
import ssl
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any

from engine import act_accounts, itip
from engine.channels import (
    ChannelContext,
    ChannelFailed,
    ChannelRegistration,
    ChannelSent,
    ChannelUndone,
    ChannelUnknown,
    OutgoingAct,
)
from engine.connectors import ConnectorError
from engine.connectors.mailbox import MailboxSettings, _close, _open, _quoted, parse_folders

log = logging.getLogger(__name__)

NAME = "mailbox"
#: What the channel does, by kind of target.
ACTIONS: dict[str, tuple[str, ...]] = {
    "message": ("send", "reply", "reply_all", "forward"),
    "mailbox": ("archive", "move", "label", "mark_read"),
    "calendar": ("answer",),
}
#: The answers to an invitation a mailbox can give (it can't propose another time), and why it refuses that one.
ANSWERS = ("accepted", "tentative", "declined")
NO_PROPOSE = "a mailbox can only accept, decline or say maybe to an invitation, not propose a new time"
#: The port that is a secure connection from the start; any other is made secure after connecting.
IMPLICIT_TLS_PORT = 465
#: How a person's answer to an invitation reads in the iTIP reply.
_STATUS = {"accepted": "ACCEPTED", "tentative": "TENTATIVE", "declined": "DECLINED"}
_FLAG_SEEN = "\\Seen"
_FLAG_DELETED = "\\Deleted"


class _Stop(Exception):
    """The act ends here with this answer (a `ChannelFailed` or a `ChannelUnknown`)."""

    def __init__(self, answer: Any):
        self.answer = answer


def message_id(key: str, address: str) -> str:
    """The Message-ID of the message an attempt sends: the same key always gives the same one."""
    domain = address.rsplit("@", 1)[-1] if "@" in address else "localhost"
    return f"<{key}@{domain}>"


def _refused(reason: str) -> _Stop:
    return _Stop(ChannelFailed("refused", reason))


def _failed_from(err: ConnectorError, settings: MailboxSettings) -> _Stop:
    """A connector's error as the channel's answer: sure that nothing was done."""
    if err.kind == "auth":
        return _Stop(
            ChannelFailed("auth", f"Sign in again to the mailbox {settings.user}: {err.detail or 'it was refused'}")
        )
    if err.kind in ("outage", "throttled"):
        return _Stop(ChannelFailed("outage", err.detail or "the mail server isn't answering"))
    if err.kind == "offline":
        return _Stop(ChannelFailed("offline", err.detail or "the mail server can't be reached from here"))
    return _refused(err.detail or "the mail server refused it")


def _by_code(code: int, what: str) -> _Stop:
    """What an SMTP reply code says about a step that was not accepted: 4xx is a try-later, 5xx a refusal; any other
    code is no clear answer."""
    if 400 <= code < 500:
        return _Stop(ChannelFailed("outage", f"the outgoing mail server can't take {what} right now; try again later"))
    if 500 <= code < 600:
        return _Stop(ChannelFailed("refused", f"the outgoing mail server refused {what}"))
    return _Stop(ChannelUnknown())


class MailboxChannel:
    """The channel. `settings_of` gives an account's mailbox settings (None when there is no such mailbox now),
    `acting_accounts` the mailbox accounts acting is on for (the ones a status can look in), `saved_text` the text of a
    saved message by its record id (for a forward's quote), and `now` the clock."""

    def __init__(
        self,
        settings_of: Callable[[str], MailboxSettings | None],
        acting_accounts: Callable[[], list[str]],
        saved_text: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.settings_of = settings_of
        self.acting_accounts = acting_accounts
        self.saved_text = saved_text
        self.now = now or (lambda: datetime.now(UTC))

    def registration(self) -> ChannelRegistration:
        return ChannelRegistration(
            NAME,
            "Mailbox",
            tuple(ACTIONS),
            send=self.send,
            status=self.status,
            undo=self.undo,
            actions=dict(ACTIONS),
            accounts=(act_accounts.MAILBOX,),
        )

    # ---- sending -----------------------------------------------------------------------------------------------------

    def send(self, act: OutgoingAct, attempt_key: str, context: ChannelContext | None = None) -> Any:
        try:
            settings = self._settings(act)
            if act.kind == "mailbox":
                return self._mailbox_act(act, settings)
            if act.kind == "message" and act.action in ACTIONS["message"]:
                return self._send_mail(act, settings, attempt_key, self._compose(act, settings, attempt_key))
            if act.kind == "calendar" and act.action == "answer":
                return self._send_mail(act, settings, attempt_key, self._answer(act, settings, attempt_key))
            raise _refused(f"a mailbox can't {act.action or 'do that'} for a {act.kind} act")
        except _Stop as stop:
            return stop.answer

    def _settings(self, act: OutgoingAct) -> MailboxSettings:
        found = self.settings_of(act.account) if act.account else None
        if found is None:
            raise _refused("the mailbox this goes through isn't set up any more")
        return found

    def _compose(self, act: OutgoingAct, settings: MailboxSettings, key: str) -> EmailMessage:
        sender = self._sender(settings)
        message = self._envelope(act, settings, key, sender, act.parts.get("subject") or "(no subject)")
        body = act.parts.get("body") or ""
        if act.action in ("reply", "reply_all", "forward") and act.about and act.about[0].service_id:
            original = act.about[0]
            if act.action != "forward":
                message["In-Reply-To"] = original.service_id
                message["References"] = original.service_id
            elif self.saved_text is not None:
                quoted = "\n".join("> " + line for line in self.saved_text(original.id).splitlines())
                body = f"{body}\n\n{quoted}" if quoted else body
        message.set_content(body)
        return message

    def _answer(self, act: OutgoingAct, settings: MailboxSettings, key: str) -> EmailMessage:
        status = _STATUS.get(act.answer or "")
        if status is None:
            raise _refused(NO_PROPOSE)
        if not act.about or not act.about[0].uid:
            raise _refused("the invitation has no id to answer")
        if not act.recipients:
            raise _refused("the invitation names no organizer to answer")
        sender = self._sender(settings)
        about = act.about[0]
        start: datetime | None = None
        with contextlib.suppress(TypeError, ValueError):
            start = datetime.fromisoformat(act.start) if act.start else None
        invitation = itip.Invitation(
            method="REQUEST",
            uid=about.uid,
            sequence=about.sequence or 0,
            summary=act.title or "",
            start=start,
            end=None,
            organizer=act.recipients[0].address,
            attendees=(itip.Attendee(email=sender),),
            cancelled=False,
            dtstamp=self.now(),
        )
        try:
            ics = itip.reply_ics(invitation, sender, status, act.parts.get("comment"), dtstamp=self.now())
        except ValueError as err:
            raise _refused(f"the answer can't be prepared: {err}") from None
        message = self._envelope(act, settings, key, sender, act.parts.get("subject") or act.title or about.uid)
        message.set_content(act.parts.get("body") or "")
        message.add_attachment(
            ics, subtype="calendar", charset="utf-8", params={"method": "REPLY"}, filename="reply.ics"
        )
        return message

    def _sender(self, settings: MailboxSettings) -> str:
        if not settings.sender:
            raise _refused("the mailbox has no address to send from; set one in its settings")
        return settings.sender

    def _envelope(
        self, act: OutgoingAct, settings: MailboxSettings, key: str, sender: str, subject: str
    ) -> EmailMessage:
        to = [r.address for r in act.recipients if r.role == "to"]
        cc = [r.address for r in act.recipients if r.role == "cc"]
        if not to and not cc:
            raise _refused("there is no one to send it to")
        message = EmailMessage()
        message["From"] = sender
        if to:
            message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        message["Subject"] = " ".join(subject.split())
        message["Date"] = format_datetime(self.now())
        message["Message-ID"] = message_id(key, sender)
        return message

    def _send_mail(self, act: OutgoingAct, settings: MailboxSettings, key: str, message: EmailMessage) -> Any:
        from engine.secrets import SecretError, resolve_secret

        try:
            password = resolve_secret(settings.password)
        except SecretError as err:
            raise _Stop(
                ChannelFailed("auth", f"the password of the mailbox {settings.user} isn't set: {err}")
            ) from None
        recipients = [r.address for r in act.recipients]
        self._submit(settings, password or "", self._sender(settings), recipients, message.as_bytes())
        sent_id = str(message["Message-ID"])
        if not settings.server_keeps_sent:
            self._save_copy(settings, message)
        return ChannelSent(sent_id)

    def _submit(self, settings: MailboxSettings, password: str, sender: str, recipients: list[str], raw: bytes) -> None:
        """Hand the message to the outgoing server. Raises `_Stop` with the answer unless the server took it."""
        host, port, wait = settings.outgoing_host, settings.smtp_port, settings.timeout_seconds
        context = ssl.create_default_context()
        server: Any = None
        try:
            try:
                if port == IMPLICIT_TLS_PORT:
                    server = smtplib.SMTP_SSL(host, port, timeout=wait, context=context)
                else:
                    server = smtplib.SMTP(host, port, timeout=wait)
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(settings.user, password)
            except smtplib.SMTPNotSupportedError:
                raise _refused("the outgoing mail server doesn't offer a secure, signed-in connection") from None
            except smtplib.SMTPAuthenticationError:
                raise _Stop(
                    ChannelFailed(
                        "auth", f"Sign in again to the mailbox {settings.user}: the outgoing server refused it"
                    )
                ) from None
            except smtplib.SMTPResponseException as err:
                if err.smtp_code in (530, 534, 535, 538):
                    raise _Stop(
                        ChannelFailed(
                            "auth", f"Sign in again to the mailbox {settings.user}: the outgoing server refused it"
                        )
                    ) from None
                raise _by_code(err.smtp_code, "the sign-in") from None
            except smtplib.SMTPException:  # (these are OSErrors too, so they are named first)
                raise _Stop(ChannelFailed("outage", "the outgoing mail server stopped answering")) from None
            except (socket.gaierror, ConnectionError, TimeoutError, OSError):
                raise _Stop(ChannelFailed("offline", "couldn't reach the outgoing mail server")) from None
            self._transfer(server, sender, recipients, raw)
        finally:
            if server is not None:
                with contextlib.suppress(smtplib.SMTPException, OSError):
                    server.quit()

    def _transfer(self, server: Any, sender: str, recipients: list[str], raw: bytes) -> None:
        """MAIL, every RCPT, then DATA. Nothing is handed over unless every recipient is accepted; a connection lost
        while the message itself is going over is no clear answer."""
        try:
            code, _ = server.mail(sender)
            if code != 250:
                raise _by_code(code, "the message")
            for address in recipients:
                code, _ = server.rcpt(address)
                if code not in (250, 251):
                    raise _by_code(code, f"the address {address}")
        except smtplib.SMTPResponseException as err:
            raise _by_code(err.smtp_code, "the message") from None
        except (smtplib.SMTPException, OSError):
            raise _Stop(ChannelFailed("outage", "the outgoing mail server stopped answering")) from None
        try:
            code, _ = server.data(raw)
        except smtplib.SMTPDataError as err:
            raise _by_code(err.smtp_code, "the message") from None
        except (smtplib.SMTPException, OSError):
            raise _Stop(ChannelUnknown()) from None
        if not 200 <= code < 300:
            raise _by_code(code, "the message")

    def _save_copy(self, settings: MailboxSettings, message: EmailMessage) -> None:
        """Save a copy in the sent folder. The message has gone out, so a copy that can't be saved changes nothing
        about the answer."""
        try:
            server = _open(settings)
        except ConnectorError:
            log.warning("a sent message's copy wasn't saved: the mailbox didn't sign in")
            return
        try:
            folder = _sent_folder(server, settings)
            server.append(_quoted(folder), _FLAG_SEEN, imaplib.Time2Internaldate(self.now()), message.as_bytes())
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, OSError):
            log.warning("a sent message's copy wasn't saved: the sent folder didn't take it")
        finally:
            _close(server)

    # ---- what happened to an attempt ---------------------------------------------------------------------------------

    def status(self, attempt_key: str, context: ChannelContext | None = None) -> Any:
        """Found in the sent folder of a mailbox acting is on for: sent. Anything else: unknown."""
        for account in self.acting_accounts():
            settings = self.settings_of(account)
            if settings is None or not settings.sender:
                continue
            wanted = f"<{attempt_key}@"
            try:
                server = _open(settings)
            except ConnectorError:
                continue
            try:
                status, _ = server.select(_quoted(_sent_folder(server, settings)), readonly=True)
                if status != "OK":
                    continue
                status, found = server.uid("SEARCH", None, "HEADER", "Message-ID", _quoted(wanted))
                if status == "OK" and (found[0] or b"").split():
                    return ChannelSent(message_id(attempt_key, settings.sender))
            except (imaplib.IMAP4.error, imaplib.IMAP4.abort, OSError):
                continue
            finally:
                _close(server)
        return ChannelUnknown()

    # ---- mailbox acts ------------------------------------------------------------------------------------------------

    def _mailbox_act(self, act: OutgoingAct, settings: MailboxSettings) -> Any:
        ids = self._ids(act)
        try:
            server = _open(settings)
        except ConnectorError as err:
            raise _failed_from(err, settings) from None
        try:
            uids = self._locate(server, settings.folder, ids)
            if act.action in ("archive", "move"):
                destination = self._destination(act, settings, server)
                for uid in uids:
                    self._move(server, uid, destination)
            elif act.action == "label":
                keyword = _keyword(act.label)
                for uid in uids:
                    self._store(server, uid, "+FLAGS", keyword)
            elif act.action == "mark_read":
                for uid in uids:
                    self._store(server, uid, "+FLAGS", _FLAG_SEEN)
            else:
                raise _refused(f"a mailbox can't {act.action} messages")
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, OSError):
            raise _Stop(ChannelUnknown()) from None
        finally:
            _close(server)
        return ChannelSent(", ".join(ids))

    def undo(self, act: OutgoingAct, service_id: str, context: ChannelContext | None = None) -> Any:
        """Put a mailbox act back: moved messages go back to their folder, a label or the read mark is removed."""
        try:
            if act.kind != "mailbox" or act.action not in ACTIONS["mailbox"]:
                raise _refused("that can't be taken back")
            settings = self._settings(act)
            ids = self._ids(act)
            try:
                server = _open(settings)
            except ConnectorError as err:
                raise _failed_from(err, settings) from None
            try:
                if act.action in ("archive", "move"):
                    destination = self._destination(act, settings, server)
                    for uid in self._locate(server, destination, ids):
                        self._move(server, uid, settings.folder)
                else:
                    flag = _keyword(act.label) if act.action == "label" else _FLAG_SEEN
                    for uid in self._locate(server, settings.folder, ids):
                        self._store(server, uid, "-FLAGS", flag)
            except (imaplib.IMAP4.error, imaplib.IMAP4.abort, OSError):
                raise _Stop(ChannelUnknown()) from None
            finally:
                _close(server)
        except _Stop as stop:
            return stop.answer
        return ChannelUndone()

    def _ids(self, act: OutgoingAct) -> list[str]:
        ids = [a.service_id for a in act.about]
        if not ids or not all(ids):
            raise _refused("a message this is about has no id on the mail server")
        return [str(i) for i in ids]

    def _destination(self, act: OutgoingAct, settings: MailboxSettings, server: Any) -> str:
        if act.action == "move":
            if not act.folder:
                raise _refused("no folder was named to move the messages to")
            return act.folder
        if settings.archive_folder:
            return settings.archive_folder
        status, data = server.list()
        found = parse_folders(list(data or [])).archive if status == "OK" else None
        if found is None:
            raise _refused("this mailbox has no archive folder; pick one in its settings")
        return found

    def _locate(self, server: Any, folder: str, ids: list[str]) -> list[str]:
        """The UID of each message in the folder, found by Message-ID; every one must be there before
        anything changes."""
        status, _ = server.select(_quoted(folder))
        if status != "OK":
            raise _refused(f"there is no folder {folder}")
        uids: list[str] = []
        for wanted in ids:
            status, found = server.uid("SEARCH", None, "HEADER", "Message-ID", _quoted(wanted))
            hits = (found[0] or b"").split() if status == "OK" and found else []
            if not hits:
                raise _refused(f"a message isn't in {folder} any more: it was moved or deleted")
            uids.append(hits[0].decode() if isinstance(hits[0], bytes) else str(hits[0]))
        return uids

    def _move(self, server: Any, uid: str, destination: str) -> None:
        """Move one message. Where the server has no MOVE, copy it and mark only that one message deleted and expunge
        only it; a server with neither way is refused rather than risking another message."""
        capabilities = {str(c).upper() for c in getattr(server, "capabilities", ())}
        target = _quoted(destination)
        if "MOVE" in capabilities:
            status, _ = server.uid("MOVE", uid, target)
            if status != "OK":
                raise _refused(f"the mail server wouldn't move the message to {destination}")
            return
        if "UIDPLUS" not in capabilities:
            raise _refused("this mail server can't move a message without risking others")
        status, _ = server.uid("COPY", uid, target)
        if status != "OK":
            raise _refused(f"the mail server wouldn't copy the message to {destination}")
        self._store(server, uid, "+FLAGS", _FLAG_DELETED)
        status, _ = server.uid("EXPUNGE", uid)
        if status != "OK":
            raise _refused("the mail server wouldn't finish the move")

    def _store(self, server: Any, uid: str, how: str, flag: str) -> None:
        status, _ = server.uid("STORE", uid, how, f"({flag})")
        if status != "OK":
            raise _refused("the mail server wouldn't change the message")


def _sent_folder(server: Any, settings: MailboxSettings) -> str:
    """The folder sent copies are saved in and read from: the one set, else the server's own, else Sent."""
    if settings.sent_folder:
        return settings.sent_folder
    status, data = server.list()
    found = parse_folders(list(data or [])).sent if status == "OK" else None
    return found or "Sent"


def _keyword(label: str | None) -> str:
    """A label as an IMAP keyword: letters, digits and a few marks; anything else becomes a dash."""
    word = re.sub(r"[^A-Za-z0-9_.-]", "-", (label or "").strip())
    if not word:
        raise _refused("no label was named")
    return word


def for_workspace(store: Any, cfg_of: Callable[[], Any]) -> MailboxChannel:
    """The channel for a workspace: an account `mailbox:<source id>` is that watched mailbox source, with its settings
    as the configuration holds them now."""

    def settings_of(account: str) -> MailboxSettings | None:
        if act_accounts.kind_of(account) != act_accounts.MAILBOX:
            return None
        name = act_accounts.name_of(account)
        source = next((s for s in cfg_of().watch.sources if s.connector == act_accounts.MAILBOX and s.id == name), None)
        return MailboxSettings.model_validate(source.settings) if source is not None else None

    def acting_accounts() -> list[str]:
        return [a for a in cfg_of().watch.acting if act_accounts.kind_of(a) == act_accounts.MAILBOX]

    def saved_text(record_id: str) -> str:
        from engine.intake import source_text
        from engine.workspace import Workspace

        return source_text(Workspace(store.path.parent), store, record_id)

    return MailboxChannel(settings_of, acting_accounts, saved_text)
