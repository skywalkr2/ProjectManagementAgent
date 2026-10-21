"""A phone number in a known sender's mail signature, offered for their record by rule (design 6.7, `person.contact`).

A rule on the text, with no AI: the signature of a message (what the reply splitter takes off its end, or the lines
after a "--" line) is read for a run of digits that looks like a phone number. The proposal is an ordinary
`person.contact` op, so it waits for the person like any contact detail. Nothing here guesses who the sender is: the
From line must resolve to exactly one known person who is not the person this app is for."""

from __future__ import annotations

import re
from typing import Any

from engine import reply_lines
from engine.ops import EvidenceIn, OpModel, PersonContactOp
from engine.reply_split import split_message

# Digits with spaces, dashes, dots, slashes and brackets between them, starting at a digit, a bracket or a plus sign.
_RUN = re.compile(r"(?<![\w@])\+?\(?\d[\d ()./-]*\d")
_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(r"\S*(?:://|www\.)\S*", re.IGNORECASE)
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}")
_RULE = re.compile(r"--\s*")


def signature_lines(text: str) -> list[str]:
    """The signature of a message body: the lines the splitter takes as its signature, else the lines after the last
    "--" line of its new text."""
    parts = split_message(text)
    if parts.signature.strip():
        return parts.signature.splitlines()
    lines = parts.new.splitlines()
    marks = [i for i, line in enumerate(lines) if _RULE.fullmatch(line)]
    return lines[marks[-1] + 1 :] if marks else []


def phones_in(lines: list[str], min_digits: int) -> list[tuple[str, str]]:
    """The phone numbers the lines hold, each as written with the line it is on, in order. Addresses and links are
    set aside first, and a run that is a day is not a number."""
    found: list[tuple[str, str]] = []
    for line in lines:
        clean = _LINK.sub(lambda m: " " * len(m.group()), _ADDRESS.sub(lambda m: " " * len(m.group()), line))
        for run in _RUN.finditer(clean):
            written = line[run.start() : run.end()].strip()
            if len(re.findall(r"\d", written)) >= min_digits and not _DAY.fullmatch(written):
                found.append((written, line.strip()))
    return found


def _digits(value: str) -> str:
    return "".join(re.findall(r"\d", value))


def proposals(
    raw_input: str, view: Any, cfg: Any, people: Any, kind: str | None, ops: list[OpModel]
) -> list[PersonContactOp]:
    """The `person.contact` op to add for a message's signature, as a list of zero or one. None when the input isn't a
    message with a From line, the sender isn't exactly one known person other than the person (or sent it from one of
    their own addresses), the signature holds no phone number, the person's record already holds one of them, or the
    answer already has a contact op for that person's phone. `kind` is the workspace's name for a phone number, None
    when it has none."""
    head = reply_lines.leading_headers(raw_input)
    sender = (head[0].get("from") if head else None) or ""
    if kind is None or not sender or reply_lines.sent_by_me(view, cfg, sender):
        return []
    who = people.match_entries([sender])
    if len(who) != 1:
        return []
    (person,) = who
    record = view.get("person", person)
    if person == people.pm or record is None:
        return []
    numbers = phones_in(signature_lines(head[1]), cfg.workspace.phone_min_digits)
    if not numbers:
        return []
    held = (record.data.get("how_to_reach") or {}).get(kind)
    if held and _digits(held) in {_digits(value) for value, _ in numbers}:
        return []
    if any(
        isinstance(op, PersonContactOp)
        and op.person == person
        and " ".join(op.kind.split()).casefold() == kind.casefold()
        for op in ops
    ):
        return []
    value, line = numbers[0]
    return [PersonContactOp(person=person, kind=kind, value=value, evidence=EvidenceIn(quote=line))]
