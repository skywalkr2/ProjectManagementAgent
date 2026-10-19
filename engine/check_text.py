"""The text a check on words reads: the words, with links and the person's own quoted text taken out first.

A link (a web address with a query string, a bare domain, a mail address) and a passage the person or the input wrote
are not the product's wording, so a check on wording (the screen-text check, the applier's wording lints, word
similarity) never reads them. Every such check calls `words_of` (or `without_links` where no quotes are known); a check
that scans text with a pattern and skips this is a bug.

What is known at each place decides which quotes can be passed. The applier knows the input, so it passes the exact
quotes an op carries as evidence and any passage in quotation marks that is in the input. A screen field holds a
string only, so it knows links and nothing more.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Characters that may end a sentence or close a bracket right after a link, which are not part of it.
_TRAILING = r"[^\s<>\"'.,;:!?)\]}]"
_BODY = r"[^\s<>\"]*"

#: A web address with a scheme, a mail link, a mail address, and an address that starts with "www.".
_SCHEME_LINK = re.compile(rf"(?i)\b(?:[a-z][a-z0-9+.-]*://|mailto:){_BODY}{_TRAILING}")
_WWW_LINK = re.compile(rf"(?i)(?<![\w.@-])www\.{_BODY}{_TRAILING}")
_MAIL_ADDRESS = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

#: Endings that make a bare dotted name a domain, whatever follows it. A dotted name that ends otherwise is a domain
#: only when a path, query or fragment follows it.
DOMAIN_ENDINGS = frozenset(
    {
        "com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "io", "dev", "app", "ai", "co", "me", "us",
        "uk", "ca", "au", "de", "fr", "es", "it", "nl", "se", "no", "dk", "fi", "ch", "at", "be", "ie", "nz", "jp",
        "cn", "in", "br", "mx", "ru", "pl", "eu", "tv", "cloud", "online", "site", "tech", "xyz", "page", "wiki",
    }
)  # fmt: skip
_BARE_HOST = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
_BARE_DOMAIN = re.compile(rf"(?<![\w./@:-])({_BARE_HOST})(?![\w])(?::\d+)?((?:[/?#]{_BODY}{_TRAILING})?)")


def _bare_domain(match: re.Match[str]) -> str:
    host, rest = match.group(1), match.group(2)
    if rest or host.rsplit(".", 1)[1].lower() in DOMAIN_ENDINGS:
        return " "
    return match.group()


def without_links(text: str) -> str:
    """The text with every link replaced by a space: addresses with a scheme, `mailto:`, `www.` addresses, mail
    addresses, and bare domains (a name ending as a domain does, or followed by a path, query or fragment)."""
    for pattern in (_SCHEME_LINK, _WWW_LINK, _MAIL_ADDRESS):
        text = pattern.sub(" ", text)
    return _BARE_DOMAIN.sub(_bare_domain, text)


def links_in(text: str) -> list[str]:
    """The web addresses in the text, each as written, in order: addresses with a scheme, `www.` addresses and bare
    domains. Mail addresses and `mailto:` links are not web addresses and are left out."""
    text = _MAIL_ADDRESS.sub(" ", text)
    found: list[tuple[int, str]] = []

    def take(pattern: re.Pattern[str], text: str) -> str:
        for match in pattern.finditer(text):
            if not match.group().lower().startswith("mailto:"):
                found.append((match.start(), match.group()))
        return pattern.sub(lambda m: " " * len(m.group()), text)

    text = take(_SCHEME_LINK, text)
    text = take(_WWW_LINK, text)
    for match in _BARE_DOMAIN.finditer(text):
        if _bare_domain(match) == " ":
            found.append((match.start(), match.group()))
    return [link for _, link in sorted(found)]


def without_quotes(text: str, quotes: Iterable[str] = ()) -> str:
    """The text with each exact quote taken out (compared ignoring case and the kind of quotation mark)."""
    for quote in sorted({q for q in quotes if q and q.strip()}, key=len, reverse=True):
        text = re.sub(_loose(quote), " ", text, flags=re.IGNORECASE)
    return text


_QUOTE_MARKS = {"‘": "'", "’": "'", "“": '"', "”": '"'}


def _loose(quote: str) -> str:
    """A pattern for the quote that accepts either kind of quotation mark and any run of whitespace."""
    out = []
    for part in re.split(r"(\s+)", quote.strip()):
        if part.isspace():
            out.append(r"\s+")
            continue
        for ch in part:
            plain = _QUOTE_MARKS.get(ch, ch)
            if plain in ("'", '"'):
                curly = [k for k, v in _QUOTE_MARKS.items() if v == plain]
                out.append("[" + plain + "".join(curly) + "]")
            else:
                out.append(re.escape(ch))
    return "".join(out)


_QUOTED = re.compile(r"\"([^\"]+)\"|“([^”]+)”")


def quoted_passages(text: str) -> list[str]:
    """Passages of the text written between double quotation marks."""
    return [a or b for a, b in _QUOTED.findall(text)]


def words_of(text: str, quotes: Iterable[str] = ()) -> str:
    """What a check on wording reads: the text without its links and without the exact quotes given."""
    return without_links(without_quotes(text, quotes))


_NUMBER_MARK = re.compile(r"(?:^|\s)\(?(\d{1,2})[.)]\s+(?=\S)")


def numbered_questions(text: str) -> int:
    """How many items of a numbered list in the text are questions. The list is the markers ("1.", "2)", "(3)") that
    count up from 1 in order, so a date or a figure inside a sentence isn't one; an item is a question when it holds a
    question mark."""
    chain: list[re.Match[str]] = []
    for mark in _NUMBER_MARK.finditer(text):
        if int(mark.group(1)) == len(chain) + 1:
            chain.append(mark)
    asked = 0
    for index, mark in enumerate(chain):
        end = chain[index + 1].start() if index + 1 < len(chain) else len(text)
        if "?" in text[mark.end() : end]:
            asked += 1
    return asked
