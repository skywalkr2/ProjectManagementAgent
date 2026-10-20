"""The mailbox connector: new messages in one folder of a mailbox, read over IMAP with TLS, and never changed there
(messages are fetched without being marked as read). Each message is an item keyed by its Message-ID, with its sender,
date, subject and plain text, and its attachments as files for the core to read. Only messages after the last one seen
are read, so the listing is not complete.

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
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.connectors import ConnectorContext, ConnectorError, ItemFile, MessageDetails, Poll, SourceItem
from engine.connectors.feed import plain
from engine.secrets import SecretHint

#: The longest message text kept; the rest is cut with a note.
MAX_TEXT = 20_000


class MailboxSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, description="The mail server's name, which your email provider's help page gives.")
    port: int = Field(
        993, ge=1, le=65535, description="The number the mail server listens on.", json_schema_extra={"advanced": True}
    )
    user: str = Field(min_length=1, description="The account's user name, usually the address.")
    password: str = Field(
        min_length=1,
        description=SecretHint(
            "The password, or an app password from your email provider. It is kept on this computer."
        ),
    )
    folder: str = Field("INBOX", description="The folder to read.", json_schema_extra={"advanced": True})
    first_read: int = Field(
        20,
        ge=0,
        le=500,
        description="How many of the latest messages the first read takes.",
        json_schema_extra={"advanced": True},
    )
    max_per_read: int = Field(
        50, ge=1, le=500, description="The most messages one read takes.", json_schema_extra={"advanced": True}
    )
    timeout_seconds: float = Field(
        30,
        gt=0,
        description="How many seconds to wait for the server.",
        json_schema_extra={"advanced": True},
    )


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
    files = attachments(message)
    received = _received(str(message.get("Date") or ""))
    details = MessageDetails(
        sender=sender, received=received, bulk=is_bulk(message), participants=participants(message)
    )
    return SourceItem(
        key,
        subject[:200],
        "\n".join(lines).strip(),
        sender,
        str(message.get("Date") or "") or None,
        message=details,
        files=files,
    )


def attachments(message: EmailMessage) -> tuple[ItemFile, ...]:
    """The message's attachments that have a file name, as files for the core to read; the core limits their size."""
    found = []
    for part in message.iter_attachments() if message.is_multipart() else []:
        name = part.get_filename()
        data = part.get_payload(decode=True)
        if name and isinstance(data, bytes):
            found.append(ItemFile(" ".join(str(name).split()), part.get_content_type(), data))
    return tuple(found)


def participants(message: EmailMessage) -> tuple[str, ...]:
    """Everyone else on the message: the people in its To and Cc headers, each once, as `Name <address>` (or the
    address or the name alone), in the order the headers list them."""
    found: list[str] = []
    for header in ("To", "Cc"):
        values = [" ".join(str(v).split()) for v in message.get_all(header, [])]
        for name, address in getaddresses(values):
            written = f"{name} <{address}>" if name and address else (address or name)
            if written and written not in found:
                found.append(written)
    return tuple(found)


#: Values of the Precedence header that mark a message as sent to many.
BULK_PRECEDENCE = ("bulk", "list")


def is_bulk(message: EmailMessage) -> bool:
    """Whether the headers say the message was sent to many: a list-unsubscribe address, or a bulk or list
    precedence."""
    if str(message.get("List-Unsubscribe") or "").strip():
        return True
    return str(message.get("Precedence") or "").strip().lower() in BULK_PRECEDENCE


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


#: The kind of failure each classified refusal is, for the kinds a connector can raise.
_REFUSAL_KINDS = {
    "credentials_refused": "auth",
    "wrong_password": "auth",
    "app_password_needed": "auth",
    "account_locked": "auth",
    "sign_in_method_off": "no_access",
    "server_busy": "outage",
    "secure_connection_failed": "no_access",
    "unknown": "auth",
}
#: The most of the server's own words kept in the problem.
_SAID_MAX = 300


def _refusal(err: imaplib.IMAP4.error, host: str) -> ConnectorError:
    """The error for a refused sign-in: the cause by rules, the advice as a wording key, and the server's own words
    only as quoted text (addresses in them already shortened to their domain)."""
    from engine.connectors.imap_refusal import imap_problem

    problem = imap_problem(err.args[0] if err.args else "", host)
    said = " ".join(problem.text.split())
    if len(said) > _SAID_MAX:
        said = said[:_SAID_MAX].rstrip() + "…"
    detail = "the mail server refused the sign-in" + (f"; it said \u201c{said}\u201d." if said else ".")
    return ConnectorError(
        _REFUSAL_KINDS[problem.kind],  # type: ignore[arg-type]
        detail,
        advice_key=f"sources.advice.{problem.advice_key}",
    )


def _open(settings: MailboxSettings) -> imaplib.IMAP4_SSL:
    """A signed-in connection to the server. Refusals and unreachable servers become connector errors."""
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
        server.login(settings.user, password or "")
    except imaplib.IMAP4.error as err:
        _close(server)
        raise _refusal(err, settings.host) from None
    except (imaplib.IMAP4.abort, TimeoutError, OSError) as err:
        _close(server)
        raise ConnectorError("outage", f"the mail server stopped answering: {err}") from None
    return server


def _close(server: imaplib.IMAP4) -> None:
    with contextlib.suppress(imaplib.IMAP4.error, OSError):
        server.logout()


def read_mailbox(settings: MailboxSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    server = _open(settings)
    try:
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
        _close(server)


@dataclass(frozen=True)
class Folders:
    """The folders of a mailbox that can be read, and the one the server marks as the sent mail (None when it marks
    none)."""

    names: tuple[str, ...]
    sent: str | None


_LISTED = re.compile(rb'^\((?P<flags>[^)]*)\) (?:"(?:[^"\\]|\\.)*"|NIL) (?P<name>"(?:[^"\\]|\\.)*"|\S+)\s*$')


def parse_folders(lines: list[Any]) -> Folders:
    """The folders in a server's LIST answer. A folder flagged as not selectable is left out; the one flagged `\\Sent`
    (the server's own word for the sent mail, where it gives one) is the sent folder."""
    names: list[str] = []
    sent: str | None = None
    for line in lines:
        found = _LISTED.match(line) if isinstance(line, bytes) else None
        if found is None:
            continue
        flags = {f.lower() for f in found["flags"].decode("ascii", "replace").split()}
        name = found["name"].decode("utf-8", "replace")
        if name.startswith('"'):
            name = re.sub(r"\\(.)", r"\1", name[1:-1])
        if "\\noselect" in flags or "\\nonexistent" in flags:
            continue
        names.append(name)
        if "\\sent" in flags and sent is None:
            sent = name
    return Folders(tuple(names), sent)


def list_folders(settings: MailboxSettings) -> Folders:
    """The mailbox's folders, read without changing anything there."""
    server = _open(settings)
    try:
        status, data = server.list()
        if status != "OK":
            raise ConnectorError("outage", "the mail server didn't list its folders")
        return parse_folders(list(data or []))
    except (imaplib.IMAP4.abort, imaplib.IMAP4.error, TimeoutError, OSError) as err:
        raise ConnectorError("outage", f"the mail server stopped answering: {err}") from None
    finally:
        _close(server)


def _quoted(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _validity(server: imaplib.IMAP4) -> str:
    """The folder's UIDVALIDITY: when it changes, UIDs start over and the last one seen means nothing."""
    response = server.response("UIDVALIDITY")[1]
    value = response[0] if response else b""
    match = re.search(rb"\d+", value or b"")
    return match.group(0).decode() if match else ""
