"""Normalize mail subjects and conservatively select a thread identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ThreadCandidate:
    key: str
    subject: str
    participants: tuple[str, ...]
    received: datetime
    message_id: str | None = None


def normalize_subject(subject: str) -> str:
    """Remove only recognized leading transport tags and reply/forward prefixes.

    Keep ticket tags and all other content. Fold whitespace to a single space.
    Preserve subject capitalization; callers may casefold for comparisons.
    """
    value = " ".join(subject.split())
    words = r"(?:re|fwd|fw|aw|wg|sv|vs|antw|tr|rv|回复|回覆|答复|答覆|转发|轉發|轉寄|返信|転送)"
    prefix = re.compile(
        rf"^(?:\[(?:ext|external)\]\s*:?[\s]*|"
        rf"{words}(?:\s*\[\d+\])?\s*[:：]\s*|"
        rf"\[{words}(?:\s*\[\d+\])?\s*[:：]?\]\s*[:：]?\s*)",
        re.I,
    )
    while match := prefix.match(value):
        value = value[match.end() :].lstrip()
    return value


def thread_key(
    message_id: str | None,
    in_reply_to: str | None,
    references: str | Iterable[str] | None,
    subject: str,
    participants: Iterable[str],
    *,
    received: datetime | None = None,
    candidates: Iterable[ThreadCandidate] = (),
    max_days: int = 14,
) -> str:
    """Prefer a known reference or parent thread, then a reference root, then In-Reply-To.

    A candidate key can associate any known ancestor's id-based key with its
    subject/participants/date. Header links do not require participant or date
    matches. Without links, match subjects only with an overlapping address and
    absolute elapsed separation <= max_days. Reuse only one distinct matching
    key; otherwise create a new identity. No clock or external lookup is used.
    """
    if type(max_days) is not int or max_days < 0:
        raise ValueError("max_days must be a nonnegative integer")

    def instant(value: datetime) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Message dates must be aware datetimes")
        return value.astimezone(UTC)

    def addresses(values: Iterable[str]) -> set[str]:
        if isinstance(values, str):
            raise ValueError("participants must be an iterable of bare addresses, not one string")
        result = set()
        for address in values:
            if not isinstance(address, str) or not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+", address.strip()):
                raise ValueError("Participants must be bare email addresses")
            result.add(address.strip().casefold())
        return result

    def identifiers(value: str | Iterable[str] | None) -> list[str]:
        if value is None:
            return []
        values = (value,) if isinstance(value, str) else value
        found = []
        for header in values:
            # Remove comments so an address mentioned in a comment is not a link.
            cleaned = header
            while re.search(r"\([^()]*\)", cleaned):
                cleaned = re.sub(r"\([^()]*\)", " ", cleaned)
            bracketed = re.findall(r"<([^<>\s]+@[^<>\s]+)>", cleaned)
            if bracketed:
                found.extend(bracketed)
            elif re.fullmatch(r"[^<>\s@]+@[^<>\s@]+", cleaned.strip()):
                found.append(cleaned.strip())
        return list(dict.fromkeys(found))

    def identity(value: str) -> str:
        return "id:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

    current_time = instant(received) if received is not None else None
    people = addresses(participants)
    history = tuple(candidates)
    own_ids = identifiers(message_id)
    own_id = own_ids[0] if own_ids else None
    reference_ids = [item for item in identifiers(references) if item != own_id]
    reply_ids = [item for item in identifiers(in_reply_to) if item != own_id]
    known = {entry.key: entry.key for entry in history}
    for entry in history:
        for candidate_id in identifiers(entry.message_id):
            alias = identity(candidate_id)
            if alias in known and known[alias] != entry.key:
                raise ValueError("A known message ID belongs to conflicting thread keys")
            known[alias] = entry.key
    if reference_ids:
        for ancestor in reference_ids + reply_ids:
            if identity(ancestor) in known:
                return known[identity(ancestor)]
        return identity(reference_ids[0])
    if reply_ids:
        return known.get(identity(reply_ids[0]), identity(reply_ids[0]))
    if own_id and identity(own_id) in known:
        return known[identity(own_id)]
    normalized = normalize_subject(subject).casefold()
    if normalized and people and current_time is not None:
        matching = set()
        for entry in history:
            if not entry.key:
                raise ValueError("Candidate key must not be empty")
            candidate_time = instant(entry.received)
            if (
                abs(current_time - candidate_time) <= timedelta(days=max_days)
                and normalize_subject(entry.subject).casefold() == normalized
                and people.intersection(addresses(entry.participants))
            ):
                matching.add(entry.key)
        if len(matching) == 1:
            return matching.pop()
    if own_id:
        return identity(own_id)
    # Identical anonymous input has identical output; unique storage IDs belong to callers.
    anonymous = json.dumps(
        [normalized, sorted(people), current_time.isoformat() if current_time else None],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "anonymous:" + hashlib.sha256(anonymous.encode("utf-8")).hexdigest()
