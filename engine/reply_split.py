"""Conservatively separate new text, quoted history, and trailing signatures.

Original line endings and whitespace are preserved. Every input character occurs
in exactly one output field. Fields preserve their own source order, but their
concatenation does not reconstruct inline replies. Ambiguous text stays in new.
Unmarked text after an explicit history header is treated as quoted history;
an unmarked reply inside such history cannot always be distinguished from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CLOSING = (
    r"(?:(?:Kind |Best |Warm )?regards|Best(?: wishes)?|Thanks|Thank you|Many thanks|Cheers|Sincerely|Cordialement|"
    r"Bien à vous|Viele Grüße|Beste Grüße|Mit freundlichen Grüßen|Saludos|Un saludo|Cordiali saluti|Saluti|"
    r"Atenciosamente|Abraços)[,!]?"
)
# A one-word device footer, in the common mail languages; it counts only as the last line of the text.
_MOBILE = (
    r"Envoyé de mon \S+|Von meinem \S+ gesendet|Enviado desde mi \S+|Inviato da(?:l mio)? \S+|Enviado do meu \S+|"
    r"\S+から送信|发自我的\S+"
)


def name_like(line: str) -> bool:
    """Whether a line reads as a signed name: up to four capitalized words and no closing punctuation."""
    words = line.split()
    return (
        1 <= len(words) <= 4 and all(word[:1].isupper() for word in words) and not line.endswith((".", "?", "!", ":"))
    )


@dataclass(frozen=True)
class Split:
    new: str
    quoted: str
    signature: str
    forwarded: bool


def split_message(text: str) -> Split:
    """Split a plain-text body without accessing external data or mutable state.

    Explicit > quoting is line-based, so unprefixed inline responses stay new.
    History headers switch to unmarked-history mode only when the first content
    line is not >-quoted. Forwarded is true for explicit forwarding markers,
    not merely for a reply's Original Message marker or Outlook header block.
    Recognized signatures are removed only from the end of a new-text run.
    """
    lines = text.splitlines(keepends=True)
    groups = ["new"] * len(lines)
    forwarded = False

    def content(index: int) -> str:
        return lines[index].rstrip("\r\n")

    def quoted_line(index: int) -> bool:
        return content(index).lstrip().startswith(">")

    def header(index: int) -> tuple[int, bool]:
        current = content(index).strip()
        following = index + 1
        while following < len(lines) and not content(following).strip():
            following += 1
        upcoming = content(following).strip() if following < len(lines) else ""
        if re.fullmatch(r"-{2,}\s*Original Message\s*-{2,}", current, re.I):
            return 1, False
        # Outlook's separator rule counts only when a header block follows it.
        if re.fullmatch(r"_{10,}", current) and re.match(r"From:\s*\S", upcoming, re.I):
            return 1, False
        if re.fullmatch(r"Begin forwarded message:", current, re.I) or re.fullmatch(
            r"-{2,}\s*Forwarded message\s*-{2,}", current, re.I
        ):
            return 1, True
        if re.match(r"From:\s*\S", current, re.I):
            # A header block starts with From and holds From, Sent (or Date), To and Subject once each, in any order,
            # with Cc optional: Outlook writes Sent, other mail programs write Date and may put Subject before To.
            fields, last = [], index
            for end in range(index, min(index + 12, len(lines))):
                field = re.match(r"(From|Sent|Date|To|Cc|Subject):\s*(.*)$", content(end).strip(), re.I)
                if field:
                    fields.append("sent" if field[1].lower() == "date" else field[1].lower())
                    last = end
                elif content(end).strip():
                    break
            required = [name for name in fields if name != "cc"]
            if required and required[0] == "from" and sorted(required) == ["from", "sent", "subject", "to"]:
                return last - index + 1, False
        if re.match(r"On\s+", current, re.I):
            for length in range(1, min(4, len(lines) - index) + 1):
                joined = " ".join(content(part).strip() for part in range(index, index + length))
                if re.fullmatch(r"On\s+.+\s+wrote\s*:", joined, re.I):
                    date_hint = re.search(
                        r"\d|\b(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|"
                        r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?|Jan(?:uary)?|Feb(?:ruary)?|"
                        r"Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
                        r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|yesterday|today)\b",
                        joined,
                        re.I,
                    )
                    following = index + length
                    while following < len(lines) and not content(following).strip():
                        following += 1
                    if date_hint or (following < len(lines) and quoted_line(following)):
                        return length, False
                    break
                if not content(index + length - 1).strip() or quoted_line(index + length - 1):
                    break
        # A "<name or address> wrote:" line, in any of the common mail languages, counts only when quoted lines
        # follow it.
        attribution = re.fullmatch(
            r"\S.*\s(?:wrote|a\s+écrit|escribió|ha\s+scritto|escreveu|schreef)\s*:|\S.*\sschrieb\s.*:", current, re.I
        )
        if attribution and following < len(lines) and quoted_line(following):
            return 1, False
        return 0, False

    index = 0
    history = False
    whole_forward = False
    while index < len(lines):
        if whole_forward:
            # Everything after a forwarding marker and its From line is the forwarded message, its own quotes and
            # signature included.
            groups[index] = "quoted"
            index += 1
            continue
        if quoted_line(index):
            groups[index] = "quoted"
            history = False
            index += 1
            continue
        length, is_forward = header(index)
        if length:
            forwarded = forwarded or is_forward
            for part in range(index, index + length):
                groups[part] = "quoted"
            index += length
            following = index
            while following < len(lines) and not content(following).strip():
                following += 1
            whole_forward = (
                is_forward and following < len(lines) and re.match(r"From:\s*\S", content(following).strip(), re.I)
            )
            history = following < len(lines) and not quoted_line(following)
            continue
        if history:
            groups[index] = "quoted"
        index += 1

    # Inspect each new-text run separately to avoid swallowing inline replies.
    index = 0
    while index < len(lines):
        if groups[index] != "new":
            index += 1
            continue
        end = index
        while end < len(lines) and groups[end] == "new":
            end += 1
        last = end - 1
        while last >= index and not content(last).strip():
            last -= 1
        for part in range(index, last + 1):
            current = content(part)
            rest = [content(tail).strip() for tail in range(part + 1, last + 1) if content(tail).strip()]
            standard = current == "-- " or (current.strip() == "--" and rest and len(rest) <= 10 and name_like(rest[0]))
            # A conventional closing followed by a short contiguous block that starts with a name.
            closing = (
                re.fullmatch(_CLOSING, current.strip(), re.I) is not None
                and 1 <= len(rest) <= 4
                and name_like(rest[0])
                and all(content(tail).strip() for tail in range(part, last + 1))
            )
            mobile = part == last and (
                re.fullmatch(
                    r"Sent from my (?:iPhone|iPad|Android(?: phone)?|Galaxy|Pixel|MacBook|phone|tablet|mobile device)"
                    r"(?:[ .,!].*)?",
                    current.strip(),
                    re.I,
                )
                is not None
                or re.fullmatch(_MOBILE, current.strip(), re.I) is not None
            )
            legal = re.match(
                r"(?:This (?:e-?mail|message)(?: and (?:any |its )?attachments)? (?:is|are) confidential\b|"
                r"Confidentiality notice:\s*This (?:e-?mail|message)\b)",
                current.strip(),
                re.I,
            )
            trailing_paragraph = all(content(tail).strip() for tail in range(part, last + 1))
            legal_text = " ".join(content(tail) for tail in range(part, last + 1))
            legal_detail = re.search(r"intended recipient|unauthorized|received .{0,20}error", legal_text, re.I)
            if standard or closing or mobile or (legal and trailing_paragraph and legal_detail):
                # A postscript after the signature is still the writer's text.
                for tail in range(part, end):
                    if re.match(r"P\.?\s?S\b", content(tail).strip()):
                        break
                    groups[tail] = "signature"
                break
        index = end

    return Split(
        new="".join(line for line, group in zip(lines, groups, strict=True) if group == "new"),
        quoted="".join(line for line, group in zip(lines, groups, strict=True) if group == "quoted"),
        signature="".join(line for line, group in zip(lines, groups, strict=True) if group == "signature"),
        forwarded=forwarded,
    )
