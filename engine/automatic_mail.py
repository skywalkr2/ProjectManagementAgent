"""Classify mail from transport evidence and anchored subject markers only."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Literal

import yaml

#: The mail programs' compatibility headers and the subject phrases of automatic replies.
MARKERS_FILE = Path(__file__).parent / "defaults" / "automatic_mail.yaml"
_MARKERS = yaml.safe_load(MARKERS_FILE.read_text(encoding="utf-8"))
_REPLY_HEADERS = frozenset(name.lower() for name in _MARKERS["reply_headers"])
_AFFIRMATIVE = frozenset(value.lower() for value in _MARKERS["affirmative"])
_REPLY_FROM_HEADERS = frozenset(name.lower() for name in _MARKERS["reply_from_headers"])
_GENERATED_REPLY = {
    name.lower(): {v.lower() for v in values} for name, values in _MARKERS["generated_reply_headers"].items()
}
_SUBJECT = re.compile(rf"^(?:{'|'.join(_MARKERS['subject_phrases'])})(?=$|\s*[:：])", re.I)


@dataclass(frozen=True)
class Classification:
    kind: Literal["auto_reply", "generated", "bounce", "bulk", "list", "none"]
    evidence: str | None


def classify_automatic(
    headers: Mapping[str, str | Iterable[str]] | Iterable[tuple[str, str]] | Message,
    subject: str,
    content_type: str,
) -> Classification:
    """Return a kind and its deciding header or phrase, without reading a body.

    Delivery reports take priority, then reply indicators, list/bulk markers,
    generated-message indicators, and subject phrases. Auto-Submitted: no blocks
    subject-only inference, not independent transport evidence. Suppression and
    loop-prevention headers alone are never evidence of an automatic message.
    Generated mail (a receipt, a notification) is its own kind: it is not a reply,
    and neither kind is a person answering.
    """
    if isinstance(headers, Message):
        pairs = list(headers.raw_items())
    elif isinstance(headers, Mapping):
        pairs = []
        for name, values in headers.items():
            pairs.extend([(name, values)] if isinstance(values, str) else [(name, value) for value in values])
    else:
        pairs = list(headers)
    fields = []
    for name, value in pairs:
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("Header names and values must be strings")
        fields.append((name.lower(), " ".join(value.split()), f"{name}: {value}"))

    media = Message()
    media["Content-Type"] = content_type
    mime = media.get_content_type().lower()
    report_type = str(media.get_param("report-type", "")).lower()
    if mime in {"message/delivery-status", "message/global-delivery-status"} or (
        mime == "multipart/report" and report_type in {"delivery-status", "global-delivery-status"}
    ):
        return Classification("bounce", "Content-Type: " + content_type)
    for name, value, evidence in fields:
        if name == "x-failed-recipients" and value:
            return Classification("bounce", evidence)

    explicit_personal = False
    generated = None
    for name, value, evidence in fields:
        if name == "auto-submitted":
            token = value.split(";", 1)[0].strip().lower()
            if token == "auto-replied":
                return Classification("auto_reply", evidence)
            if token == "auto-generated":
                generated = evidence
            explicit_personal = explicit_personal or token == "no"
    for name, value, evidence in fields:
        if name in _REPLY_HEADERS and value.lower().split(";", 1)[0].strip() in _AFFIRMATIVE:
            return Classification("auto_reply", evidence)
        if name in _REPLY_FROM_HEADERS and re.fullmatch(r"[^\s<>@]+@[^\s<>@]+", value):
            return Classification("auto_reply", evidence)
        if value.lower() in _GENERATED_REPLY.get(name, ()):
            return Classification("auto_reply", evidence)
    for name, value, evidence in fields:
        if name == "list-id" and re.search(r"<[^<>\s]+>", value):
            return Classification("list", evidence)
    for name, value, evidence in fields:
        if name == "precedence":
            token = value.lower()
            if token == "list":
                return Classification("list", evidence)
            if token in {"bulk", "junk"}:
                return Classification("bulk", evidence)
            if token in {"auto_reply", "auto-reply", "auto-replied"}:
                return Classification("auto_reply", evidence)
    if generated:
        return Classification("generated", generated)
    if not explicit_personal and (match := _SUBJECT.match(" ".join(subject.split()))):
        return Classification("auto_reply", "Subject phrase: " + match[0])
    return Classification("none", None)
