"""Extract stated contact facts from an already separated email signature."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Fact:
    value: str
    evidence: str


@dataclass(frozen=True)
class UnknownField:
    field: str
    reason: str


@dataclass(frozen=True)
class SignatureFacts:
    phones: tuple[Fact, ...]
    job_titles: tuple[Fact, ...]
    organizations: tuple[Fact, ...]
    websites: tuple[Fact, ...]
    unknown: tuple[UnknownField, ...]


def signature_facts(signature: str) -> SignatureFacts:
    """Return explicit facts with exact source lines, without enriching identities."""
    if not isinstance(signature, str):
        return SignatureFacts((), (), (), (), (UnknownField("signature", "unknown: the signature is not text"),))
    phones = []
    titles = []
    organizations = []
    websites = []
    unknown = []
    legal = False
    content_lines = 0
    phone_pattern = re.compile(
        r"(?<![\w])(?:\+\d|\(?\d)[\d() .-]*\d"
        r"(?:\s*(?:ext\.?|extension|x)\s*\d+)?",
        re.IGNORECASE,
    )
    website_pattern = re.compile(
        r"(?:https?://|www\.)[^\s<>]+|"
        r"(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}"
        r"(?::\d+)?(?:[/\?#][^\s<>]*)?",
        re.IGNORECASE,
    )
    role_pattern = re.compile(
        r"(?:independent |senior |junior |lead |managing |executive |assistant )?"
        r"(?:consultant|editor|designer|director|accountant|architect|photographer|translator|"
        r"copywriter|project manager|illustrator|researcher|producer|developer|engineer)|"
        r"founder(?:\s*(?:&|and)\s*(?:designer|director|consultant))?",
        re.IGNORECASE,
    )
    for line in signature.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed == "--":
            continue
        content_lines += 1
        if re.match(
            r"^(?:legal(?: notice)?|disclaimer|confidential(?:ity)?|this (?:email|message)|"
            r"the (?:information|contents) (?:in|of) this|registered (?:office|number)|"
            r"if you (?:are not|have received)|please consider the environment)\b",
            trimmed,
            re.IGNORECASE,
        ):
            legal = True
        if legal or re.match(r"^sent from my\b", trimmed, re.IGNORECASE):
            continue
        title = re.match(r"^(?:job title|title|role|position)\s*:\s*(.*?)\s*$", trimmed, re.IGNORECASE)
        organization = re.match(
            r"^(?:organization|organisation|company|employer)\s*:\s*(.*?)\s*$", trimmed, re.IGNORECASE
        )
        if title:
            if title.group(1):
                titles.append(Fact(title.group(1), line))
            else:
                unknown.append(UnknownField("job_title", "unknown: an explicit title label has no value"))
        elif content_lines > 1 and role_pattern.fullmatch(trimmed):
            titles.append(Fact(trimmed, line))
        if organization:
            if organization.group(1):
                organizations.append(Fact(organization.group(1), line))
            else:
                unknown.append(UnknownField("organization", "unknown: an organization label has no value"))
        labeled_phone = bool(
            re.search(
                r"\b(?:tel(?:ephone)?|phone|mobile|cell|fax|office|direct)\s*[:.]?\s*(?=[+\d(])", line, re.IGNORECASE
            )
        )
        for match in phone_pattern.finditer(line):
            value = match.group(0).strip()
            # An international prefix or a phone label distinguishes numbers from dates and addresses.
            if not labeled_phone and not value.startswith("+"):
                continue
            main = re.split(r"\s*(?:extension|ext\.?|x)\s*\d+$", value, flags=re.IGNORECASE)[0]
            digits = re.sub(r"\D", "", main)
            if not 7 <= len(digits) <= 15:
                unknown.append(UnknownField("phone", "unknown: a phone-like value has an unsupported digit count"))
                continue
            phones.append(Fact(value, line))
        for match in website_pattern.finditer(line):
            value = match.group(0).rstrip(".,;:!?)]}'\"")
            explicit_address = bool(re.match(r"https?://|www\.", value, re.IGNORECASE))
            labeled_website = bool(re.match(r"^(?:web(?:site)?|site|portfolio|visit)\s*:?\s+", trimmed, re.IGNORECASE))
            if not explicit_address and not labeled_website and trimmed.rstrip(".,;:!?)]}'\"") != value:
                continue
            try:
                parsed = urlsplit(value if re.match(r"https?://", value, re.IGNORECASE) else "//" + value)
                domain = parsed.hostname
                if not domain or "." not in domain:
                    raise ValueError("No domain was supplied")
                websites.append(Fact(domain.casefold(), line))
            except ValueError:
                unknown.append(UnknownField("website", "unknown: a website address could not be parsed"))

    for name, values in (
        ("phone", phones),
        ("job_title", titles),
        ("organization", organizations),
        ("website", websites),
    ):
        if not values and not any(item.field == name for item in unknown):
            unknown.append(UnknownField(name, "unknown: no supported explicit value was found"))
    return SignatureFacts(tuple(phones), tuple(titles), tuple(organizations), tuple(websites), tuple(unknown))
