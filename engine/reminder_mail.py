"""Build reminder email without sending or accessing external state."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.headerregistry import Address, HeaderRegistry
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from hashlib import sha256


@dataclass(frozen=True)
class Unknown:
    reason: str
    status: str = "unknown"


def _domain(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Supply a domain without surrounding whitespace")
    try:
        domain = value.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("The domain cannot be encoded") from error
    if len(domain) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in domain.split(".")
    ):
        raise ValueError("The domain is not a supported DNS hostname")
    return domain


def _addresses(value: str | Address | Sequence[str | Address]) -> tuple[Address, ...]:
    values = (value,) if isinstance(value, (str, Address)) else tuple(value)
    addresses = []
    for entry in values:
        if isinstance(entry, Address):
            parsed = (entry,)
        elif isinstance(entry, str):
            if "\r" in entry or "\n" in entry:
                raise ValueError("Address headers must not contain line breaks")
            try:
                header = HeaderRegistry()("To", entry)
            except IndexError:
                # Older Python versions' address parser fails this way on an address that ends at the "@".
                raise ValueError("Supply explicit, valid mailboxes") from None
            if header.defects or any(group.display_name is not None for group in header.groups):
                raise ValueError("Supply explicit, valid mailboxes rather than an address group")
            parsed = header.addresses
        else:
            raise ValueError("An address must be text or an Address object")
        for address in parsed:
            if not address.username or not address.domain or not address.username.isascii():
                raise ValueError("Supply a complete mailbox with an ASCII local part")
            addresses.append(Address(address.display_name, address.username, _domain(address.domain)))
    if not addresses:
        raise ValueError("Supply at least one explicit mailbox")
    return tuple(addresses)


def reminder_message(
    to: str | Address | Sequence[str | Address],
    sender: str | Address,
    subject: str,
    body: str,
    date: datetime,
    message_domain: str,
    ics: str | bytes | None = None,
    *,
    message_id_token: str | None = None,
) -> EmailMessage | Unknown:
    """Build a message using a caller-owned unique token; return unknown for invalid input."""
    try:
        if (
            not isinstance(message_id_token, str)
            or len(message_id_token) > 200
            or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", message_id_token)
        ):
            raise ValueError("Supply a unique message_id_token; this pure function cannot generate one")
        domain = _domain(message_domain)
        recipients = _addresses(to)
        senders = _addresses(sender)
        if len(senders) != 1:
            raise ValueError("Supply exactly one sender mailbox")
        if not isinstance(subject, str) or re.search(r"[\x00-\x08\x0a-\x1f\x7f]", subject):
            raise ValueError("The subject must be text without line breaks or unsafe control characters")
        if not isinstance(body, str):
            raise ValueError("The plain-text body must be text")
        if not isinstance(date, datetime) or date.tzinfo is None or date.utcoffset() is None:
            raise ValueError("Supply an aware datetime for the Date header")
        if date.utcoffset().total_seconds() % 60:
            raise ValueError("The Date header needs a whole-minute UTC offset")
        if date.astimezone(UTC).astimezone(date.tzinfo).replace(tzinfo=None) != date.replace(tzinfo=None):
            raise ValueError("The Date value falls in a nonexistent local time")
        if ics is not None and (not isinstance(ics, (str, bytes)) or not ics):
            raise ValueError("The calendar attachment must be nonempty text or bytes")
        message = EmailMessage(policy=SMTP)
        message["To"] = recipients
        message["From"] = senders[0]
        message["Subject"] = subject
        message["Date"] = format_datetime(date)
        message["Message-ID"] = f"<{message_id_token}@{domain}>"
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(body, subtype="plain", charset="utf-8", cte="quoted-printable")
        if ics is not None:
            payload = ics.encode("utf-8") if isinstance(ics, str) else ics
            payload.decode("utf-8")
            message.add_attachment(
                payload,
                maintype="text",
                subtype="calendar",
                filename="reminder.ics",
                params={"charset": "utf-8"},
                cte="base64",
            )
            # Supply the boundary so serialization does not need random boundary generation.
            boundary = sha256(f"{message_id_token}@{domain}".encode("ascii")).hexdigest()[:48]
            message.set_boundary("=_reminder_" + boundary)
        return message
    except (ValueError, TypeError, UnicodeError) as error:
        return Unknown(str(error))
