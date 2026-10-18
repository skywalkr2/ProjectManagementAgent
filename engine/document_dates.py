"""Extract explicitly labeled date statements without inventing missing dates."""

import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, tzinfo


@dataclass(frozen=True)
class DateFinding:
    kind: str
    date: date | None
    evidence: str
    certain: bool
    relative: bool
    anchor: str | None
    reason: str


def _parse_date(words: str, locale: str) -> tuple[date | None, str]:
    months = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    try:
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", words):
            year, month, day = map(int, words.split("-"))
        elif re.fullmatch(r"\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?", words):
            parts = re.split(r"[/.-]", words)
            if len(parts) != 3 or len(parts[2]) != 4:
                return None, "The year is missing or abbreviated; no year was inferred."
            if locale not in {"en-us", "en-gb"}:
                return None, "The numeric date order is unknown for the supplied locale."
            first, second, year = map(int, parts)
            month, day = (first, second) if locale == "en-us" else (second, first)
        else:
            cleaned = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", words, flags=re.IGNORECASE)
            parts = cleaned.replace(",", "").replace(".", "").casefold().split()
            if len(parts) != 3 or not re.fullmatch(r"\d{4}", parts[2]):
                return None, "The year is missing or abbreviated; no year was inferred."
            year = int(parts[2])
            if parts[0] in months:
                month, day = months[parts[0]], int(parts[1])
            else:
                day, month = int(parts[0]), months[parts[1]]
        return date(year, month, day), "An explicit calendar date is stated."
    except (ValueError, KeyError):
        return None, "The stated date is invalid; it was not corrected."


def find_dates(text: str, received: datetime, tz: tzinfo, locale: str) -> list[DateFinding]:
    """Find labeled English date statements, retaining uncertainty and relative anchors."""

    def unknown(reason: str) -> list[DateFinding]:
        return [DateFinding("unknown", None, "", False, False, None, reason)]

    if not isinstance(text, str):
        return unknown("The text is missing or is not a string.")
    if not isinstance(tz, tzinfo):
        return unknown("Supply a time-zone object; no zone was inferred.")
    if not isinstance(received, datetime) or received.tzinfo is None or received.utcoffset() is None:
        return unknown("The received time must be an aware datetime.")
    if received.astimezone(UTC).astimezone(received.tzinfo).replace(tzinfo=None) != received.replace(tzinfo=None):
        return unknown("The received time does not exist in its zone.")
    if not isinstance(locale, str):
        return unknown("The date-order locale is unknown.")
    locale = locale.replace("_", "-").casefold()
    # A document that states its own numeric date order is read that way, ahead of any locale.
    if re.search(r"\bday/month/year\b|\bdd/mm/yyyy\b", text, re.IGNORECASE):
        locale = "en-gb"
    elif re.search(r"\bmonth/day/year\b|\bmm/dd/yyyy\b", text, re.IGNORECASE):
        locale = "en-us"
    month = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
        r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    )
    day = r"\d{1,2}(?:st|nd|rd|th)?"
    year = r"(?:,?\s+\d{4})?"
    date_pattern = (
        rf"(?<![\w/.-])(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}([/.-])\d{{1,2}}(?:\1\d{{2,4}})?|"
        rf"{month}\s+{day}{year}|{day}\s+{month}{year})(?![\w/-]|\.\d)"
    )
    relative_pattern = (
        r"\b(?:(?:in|within)\s+\d+\s+(?:calendar\s+|working\s+|business\s+)?(?:days?|weeks?|months?|years?)|"
        r"(?:within\s+)?\d+\s+(?:calendar\s+|working\s+|business\s+)?(?:days?|weeks?|months?|years?)"
        r"\s+(?:after|from|before)\s+(?:the\s+)?(?:date\s+of\s+)?[\w-]+(?:\s+date)?|"
        r"today|tomorrow|next\s+(?:week|month|year))\b"
    )
    labels = (
        ("warranty_end", r"warranty(?:\s+coverage)?\s+(?:ends?|expires?|valid\s+until)|warranty[- ]end(?:\s+date)?"),
        (
            "cancel_by",
            r"cancel(?:lation)?[- ]by|cancel\s+(?:before|no\s+later\s+than)|"
            r"cancellation\s+deadline|notice\s+must\s+be\s+received\s+by",
        ),
        ("valid_until", r"valid[- ]until|valid\s+through"),
        ("payment_due", r"(?:payment|invoice|rent|balance|amount)(?:\s+is)?[- ]due(?:\s+date)?"),
        ("check_in", r"check[- ]in(?:\s+date)?"),
        ("appointment", r"appointment(?:\s+date)?"),
        ("renewal", r"(?:auto[- ])?renews?|renewal(?:\s+date)?"),
        ("expiry", r"lease\s+(?:ends?|expires?)|expires?|expiry(?:\s+date)?|expiration(?:\s+date)?"),
    )
    label_pattern = re.compile("|".join(rf"(?P<{kind}>\b(?:{pattern})\b)" for kind, pattern in labels), re.IGNORECASE)
    findings = []
    # Clauses provide a conservative boundary between unrelated deadlines.
    for clause_match in re.finditer(r"[^;\n]+", text):
        clause = clause_match.group(0)
        for sentence_match in re.finditer(r".+?(?:[!?](?=\s|$)|\.(?=\s+[A-Z])|$)", clause):
            sentence = sentence_match.group(0)
            marks = list(label_pattern.finditer(sentence))
            if not marks:
                continue
            for index, mark in enumerate(marks):
                right = marks[index + 1].start() if index + 1 < len(marks) else len(sentence)
                left = marks[index - 1].end() if index else 0
                after = sentence[mark.end() : right]
                matches = list(re.finditer(date_pattern, after, re.IGNORECASE))
                relatives = list(re.finditer(relative_pattern, after, re.IGNORECASE))
                negated = bool(
                    re.search(
                        r"\b(?:not|ignore|superseded|incorrect|previous|formerly|may|might|could|if|"
                        r"proposed|estimated|tentative|subject to)\b",
                        re.sub(date_pattern, "", sentence, flags=re.IGNORECASE),
                        re.IGNORECASE,
                    )
                )
                if relatives:
                    for relative in relatives:
                        words = relative.group(0)
                        anchor_match = re.search(r"\b(after|from|before)\s+(.+)$", words, re.IGNORECASE)
                        if anchor_match:
                            anchor = re.sub(r"^the\s+", "", anchor_match.group(2), flags=re.IGNORECASE)
                        elif words.casefold().startswith(("in ", "within ", "today", "tomorrow", "next ")):
                            anchor = "message_received"
                        else:
                            anchor = "unknown"
                        evidence = sentence[mark.start() : mark.end() + relative.end()]
                        findings.append(
                            DateFinding(
                                mark.lastgroup,
                                None,
                                evidence,
                                False,
                                True,
                                anchor,
                                "Relative wording; no calendar date was calculated.",
                            )
                        )
                    continue
                backwards = False
                if not matches:
                    before = sentence[left : mark.start()]
                    matches = list(re.finditer(date_pattern, before, re.IGNORECASE))
                    backwards = bool(matches)
                if not matches:
                    findings.append(
                        DateFinding(
                            mark.lastgroup,
                            None,
                            mark.group(0),
                            False,
                            False,
                            None,
                            "No supported explicit date follows or precedes this label.",
                        )
                    )
                    continue
                ambiguous = len(matches) > 1 or negated
                for match in matches:
                    value, reason = _parse_date(match.group(0), locale)
                    if backwards:
                        evidence = sentence[left + match.start() : mark.end()]
                    else:
                        evidence = sentence[mark.start() : mark.end() + match.end()]
                    if ambiguous:
                        reason = (
                            "The clause contains multiple dates or correction wording; the intended date is unknown. "
                            + reason
                        )
                    findings.append(
                        DateFinding(
                            mark.lastgroup, value, evidence, value is not None and not ambiguous, False, None, reason
                        )
                    )
    # One document giving the same kind of date twice, with different values, settles neither.
    dates_by_kind: dict[str, set[date]] = {}
    for finding in findings:
        if finding.date is not None:
            dates_by_kind.setdefault(finding.kind, set()).add(finding.date)
    return [
        replace(finding, certain=False, reason="The document gives different dates of this kind. " + finding.reason)
        if finding.certain and len(dates_by_kind.get(finding.kind, ())) > 1
        else finding
        for finding in findings
    ]
