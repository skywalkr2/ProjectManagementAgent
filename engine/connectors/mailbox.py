"""The mailbox connector: new messages in one folder of a mailbox, read over IMAP with TLS, and never changed there
(messages are fetched without being marked as read). Each message is an item keyed by its Message-ID, with its sender,
date, subject and plain text. Only messages after the last one seen are read, so the listing is not complete.

The password is a secret reference: many mail services issue an app password for this. Accounts that only allow
sign-in through their own pages need a plugin that provides that sign-in.
"""

from __future__ import annotations

import contextlib
import email
import email.policy
import imaplib
import re
import socket
import ssl
from email.message import EmailMessage
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.connectors import ConnectorContext, ConnectorError, MessageDetails, Poll, SourceItem
from engine.connectors.feed import plain
from engine.secrets import SecretHint

#: The longest message text kept; the rest is cut with a note.
MAX_TEXT = 20_000


class MailboxSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, description="The mail server's address (its IMAP host).")
    port: int = Field(993, ge=1, le=65535, description="Its IMAP port with TLS.")
    user: str = Field(min_length=1, description="The account's user name, usually the address.")
    password: str = Field(
        min_length=1,
        description=SecretHint("A secret reference (env:NAME or file:/path) to the password or app password."),
    )
    folder: str = Field("INBOX", description="The folder to read.")
    first_read: int = Field(20, ge=0, le=500, description="How many of the latest messages the first read takes.")
    max_per_read: int = Field(50, ge=1, le=500, description="The most messages one read takes.")
    timeout_seconds: float = Field(30, gt=0, description="How long to wait for the server.")


def message_item(raw: bytes) -> SourceItem | None:
    """A message as an item: keyed by Message-ID, with the headers people need and its plain text."""
    message = email.message_from_bytes(raw, policy=email.policy.default)
    key = str(message.get("Message-ID") or "").strip()
    if not key:
        return None
    subject = " ".join(str(message.get("Subject") or "(no subject)").split())
    sender = " ".join(str(message.get("From") or "").split()) or None
    lines = [f"From: {sender or 'unknown'}"]
    for header in ("To", "Cc", "Date"):
        if message.get(header):
            lines.append(f"{header}: {' '.join(str(message.get(header)).split())}")
    lines += [f"Subject: {subject}", "", body_text(message)]
    attached = (
        [p.get_filename() for p in message.iter_attachments() if p.get_filename()] if message.is_multipart() else []
    )
    if attached:
        lines += ["", "Attached: " + ", ".join(attached)]
    received = _received(str(message.get("Date") or ""))
    details = MessageDetails(sender=sender, received=received)
    return SourceItem(
        key, subject[:200], "\n".join(lines).strip(), sender, str(message.get("Date") or "") or None, message=details
    )


def _received(header: str) -> str | None:
    """A Date header as an ISO 8601 date-time with its offset; None when it can't be read or has no zone."""
    from email.utils import parsedate_to_datetime

    try:
        when = parsedate_to_datetime(header)
    except (TypeError, ValueError, IndexError):
        return None
    return when.isoformat() if when is not None and when.tzinfo is not None else None


def body_text(message: EmailMessage) -> str:
    """The message's plain text: its text part, or its HTML part as text."""
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):
        content = part.get_payload(decode=True).decode("utf-8", errors="replace") if part.get_payload() else ""
    text = plain(content) if part.get_content_type() == "text/html" else content.strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n(cut: the message is longer)"


def read_mailbox(settings: MailboxSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    from engine.secrets import SecretError, resolve_secret

    try:
        password = resolve_secret(settings.password)
    except SecretError as err:
        raise ConnectorError("auth", f"the mailbox password isn't set: {err}") from None
    try:
        server = imaplib.IMAP4_SSL(
            settings.host, settings.port, ssl_context=ssl.create_default_context(), timeout=settings.timeout_seconds
        )
    except (socket.gaierror, ConnectionError, OSError) as err:
        raise ConnectorError("offline", f"couldn't reach the mail server: {err}") from None
    try:
        try:
            server.login(settings.user, password or "")
        except imaplib.IMAP4.error as err:
            raise ConnectorError("auth", f"the mail server refused the sign-in: {err}") from None
        status, data = server.select(_quoted(settings.folder), readonly=True)
        if status != "OK":
            raise ConnectorError("not_found", f"there is no folder {settings.folder}")
        validity = _validity(server)
        last = int(state.get("last_uid", 0)) if state.get("validity") == validity else 0
        query = f"UID {last + 1}:*" if last else "ALL"
        status, found = server.uid("SEARCH", None, query)
        if status != "OK":
            raise ConnectorError("outage", "the mail server didn't answer the search")
        uids = sorted(int(u) for u in (found[0] or b"").split() if int(u) > last)
        if not last:
            uids = uids[-settings.first_read :] if settings.first_read else []
        uids = uids[: settings.max_per_read]
        items = []
        for uid in uids:
            status, parts = server.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in parts or [] if isinstance(p, tuple) and len(p) > 1), None)
            if status == "OK" and raw:
                item = message_item(raw)
                if item is not None:
                    items.append(item)
        newest = max(uids, default=last)
        return Poll(items, {"validity": validity, "last_uid": newest}, complete=False)
    except (imaplib.IMAP4.abort, TimeoutError, OSError) as err:
        raise ConnectorError("outage", f"the mail server stopped answering: {err}") from None
    finally:
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            server.logout()


def _quoted(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _validity(server: imaplib.IMAP4) -> str:
    """The folder's UIDVALIDITY: when it changes, UIDs start over and the last one seen means nothing."""
    response = server.response("UIDVALIDITY")[1]
    value = response[0] if response else b""
    match = re.search(rb"\d+", value or b"")
    return match.group(0).decode() if match else ""
