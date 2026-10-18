"""Conservatively identify unanswered direct questions in supplied thread text."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class Address:
    email: str
    name: str | None = None


@dataclass(frozen=True)
class Message:
    new_text: str
    from_address: Address
    to: tuple[Address, ...]
    cc: tuple[Address, ...]
    received: datetime
    automatic: bool


@dataclass(frozen=True)
class ReplyOwed:
    owed: bool | None
    evidence: tuple[str, ...]
    reason: str
    #: What a screen reads; `reason` is a diagnostic for logs and tests.
    code: str = ""


def _address(value: Address | str) -> str:
    email = value.email if isinstance(value, Address) else value
    if not isinstance(email, str) or email.count("@") != 1:
        raise ValueError("An address is missing or malformed")
    local, domain = email.strip().rsplit("@", 1)
    if not local or not domain or any(character.isspace() for character in local + domain):
        raise ValueError("An address is missing or malformed")
    return local + "@" + domain.casefold()


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Message times and now must be aware datetimes")
    instant = value.astimezone(UTC)
    if instant.astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("A supplied local time does not exist")
    return instant


def _questions(text: str) -> tuple[str, ...]:
    # Sentence periods require whitespace, so addresses and decimal values stay intact.
    found = []
    for line in text.splitlines():
        for segment in re.split(r"(?<=[?？])|(?<=[.!])\s+", line):
            question = segment.strip()
            if question.endswith(("?", "？")):
                found.append(question)
    return tuple(found)


def _answered(question: str, response: str, only_question: bool) -> bool:
    escaped = re.escape(question)
    explicit = re.search(rf'Answer to ["“]{escaped}["”]\s*:\s*(.+)', response, re.IGNORECASE)
    if explicit:
        answer = explicit.group(1).strip()
        return bool(answer) and not re.search(
            r"\b(?:don't know|do not know|not sure|will check)\b|[?？]", answer, re.IGNORECASE
        )
    # A bare yes/no can settle one genuine binary question, not a request to do work.
    binary = re.match(r"(?:Is|Are|Was|Were|Do|Does|Did|Have|Has)\b", question, re.IGNORECASE)
    return bool(only_question and binary and re.fullmatch(r"\s*(?:yes|no)[.!]?\s*", response, re.IGNORECASE))


def reply_owed(
    message: Message,
    my_addresses: Sequence[Address | str],
    later_messages: Sequence[Message],
    now: datetime,
    wait_hours: float,
) -> ReplyOwed:
    """Return True, False, or None for unknown, with exact question evidence."""
    try:
        instant = _instant(now)
        received = _instant(message.received)
        if received > instant:
            raise ValueError("The message is dated after now")
        if isinstance(wait_hours, bool) or not isinstance(wait_hours, (int, float)):
            raise ValueError("wait_hours must be a finite nonnegative number")
        wait = timedelta(hours=wait_hours)
        if wait < timedelta(0):
            raise ValueError("wait_hours must not be negative")
        mine = {_address(value) for value in my_addresses}
        if not mine:
            raise ValueError("Supply at least one of your addresses")
        if type(message.automatic) is not bool:
            raise ValueError("The automatic flag is unknown")
        if not isinstance(message.new_text, str):
            raise ValueError("The new message text is missing")
        if message.automatic:
            return ReplyOwed(False, (), "Automatic mail does not create a personal reply obligation.", "automatic")
        if _address(message.from_address) in mine:
            return ReplyOwed(False, (), "You sent this message.", "sent_by_you")
        direct_recipients = {_address(value) for value in message.to}
        if not direct_recipients & mine:
            return ReplyOwed(
                False,
                (),
                "None of your addresses is in To; being copied does not create this obligation.",
                "only_copied",
            )
        questions = _questions(message.new_text)
        if re.search(
            r"\b(?:no need to (?:reply|respond|answer)|"
            r"no (?:reply|response|answer) (?:is )?(?:needed|required)|do not reply|don't reply)\b",
            message.new_text,
            re.IGNORECASE,
        ):
            return ReplyOwed(False, questions, "The message explicitly says a reply is not needed.", "no_reply_needed")
        if not questions:
            return ReplyOwed(
                False, (), "No explicit question was found; indirect requests are outside this rule.", "no_question"
            )

        my_names = set()
        other_names = set()
        for person in (*message.to, *message.cc, *my_addresses):
            if isinstance(person, Address) and person.name:
                names = {person.name.casefold(), person.name.split()[0].casefold()}
                (my_names if _address(person) in mine else other_names).update(names)
        candidates = []
        uncertain = []
        rhetorical = {"who knows?", "who cares?", "why bother?", "what's the point?", "what could possibly go wrong?"}
        for question in questions:
            normalized = question.casefold().strip()
            if normalized in rhetorical or "rhetorical question" in normalized:
                continue
            directed = re.match(r"(?:Hi\s+|Hello\s+)?([\w -]+),\s*", question)
            if directed:
                name = directed.group(1).strip().casefold()
                if name in other_names and name not in my_names:
                    continue
                if name not in my_names or name in other_names:
                    uncertain.append(question)
                    continue
                candidates.append(question)
            elif len(direct_recipients) == 1:
                candidates.append(question)
            else:
                uncertain.append(question)
        if not candidates:
            if uncertain:
                return ReplyOwed(
                    None,
                    tuple(uncertain),
                    "Unknown: the question's intended recipient is not explicit.",
                    "recipient_unclear",
                )
            return ReplyOwed(
                False, questions, "The questions are rhetorical or addressed to someone else.", "not_for_you"
            )
        if re.search(r"\bFYI\b|for your information", message.new_text, re.IGNORECASE):
            return ReplyOwed(
                None,
                tuple(candidates),
                "Unknown: an FYI label and a question give conflicting reply cues.",
                "fyi_with_question",
            )
        if instant - received < wait:
            return ReplyOwed(False, tuple(candidates), "The supplied waiting period has not elapsed.", "still_waiting")
        responses = []
        for later in later_messages:
            later_time = _instant(later.received)
            if not received < later_time <= instant:
                continue
            if _address(later.from_address) not in mine:
                continue
            if type(later.automatic) is not bool:
                raise ValueError("A later message's automatic flag is unknown")
            if not later.automatic:
                if not isinstance(later.new_text, str):
                    raise ValueError("A later message's new text is missing")
                responses.append(later.new_text)
        unresolved = tuple(
            question
            for question in candidates
            if not any(_answered(question, response, len(questions) == 1) for response in responses)
        )
        if not unresolved:
            return ReplyOwed(
                False,
                tuple(candidates),
                "Your later messages explicitly answer every direct question found.",
                "answered",
            )
        if responses or uncertain:
            return ReplyOwed(
                None,
                unresolved,
                "Unknown: the remaining questions or later replies need a person's interpretation.",
                "needs_reading",
            )
        return ReplyOwed(
            True,
            unresolved,
            "A direct question remains after the waiting period, with no later personal reply from you.",
            "owed",
        )
    except (ValueError, TypeError, OverflowError) as error:
        return ReplyOwed(None, (), f"Unknown: {error}.", "unreadable")
