"""Classify a mail server's sign-in refusal: the standard IMAP response codes first, then known phrases."""

import ast
import contextlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

#: Phrases mail servers put in their refusals, with the service names kept in data.
RULES_FILE = Path(__file__).parents[1] / "defaults" / "imap_refusals.yaml"
RULES: list[dict] = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))["rules"]
KINDS = frozenset(
    {
        "credentials_refused",
        "wrong_password",
        "app_password_needed",
        "account_locked",
        "sign_in_method_off",
        "server_busy",
        "secure_connection_failed",
    }
)


@dataclass(frozen=True)
class Problem:
    kind: str
    text: str
    advice_key: str
    reason: str


def imap_problem(error: str | bytes, host: str, *, rules: list[dict] | None = None) -> Problem:
    """Classify a refusal using response codes, then phrase rules (the shipped ones unless given).

    A refusal already turned into text as a bytes literal (b'...') is read back as the bytes it shows. A plain
    authentication failure with no more specific phrase is credentials_refused, whose advice covers both a wrong
    password and a service that wants an app password.
    """
    if not isinstance(error, (str, bytes)):
        raise TypeError("error must be text or bytes")
    if isinstance(error, str) and re.fullmatch(r"b(['\"]).*\1", error.strip(), re.S):
        with contextlib.suppress(ValueError, SyntaxError):
            literal = ast.literal_eval(error.strip())
            if isinstance(literal, bytes):
                error = literal
    text = error.decode("utf-8", errors="replace") if isinstance(error, bytes) else error

    def redact(match: re.Match[str]) -> str:
        address = match.group(0)
        trailing = ""
        while address and address[-1] in ".,;!)]}":
            trailing = address[-1] + trailing
            address = address[:-1]
        try:
            domain = urlsplit(address if "://" in address else "//" + address).hostname
        except ValueError:
            domain = None
        return (domain or "[invalid address]") + trailing

    cleaned = re.sub(r"(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>\"']+", redact, text, flags=re.IGNORECASE)
    # Bare domains with paths or queries are addresses too; email addresses are excluded.
    cleaned = re.sub(
        r"(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?::\d+)?[/?#][^\s<>\"']*",
        redact,
        cleaned,
        flags=re.IGNORECASE,
    )

    def result(kind: str, reason: str) -> Problem:
        advice = {
            "credentials_refused": "check_credentials",
            "wrong_password": "check_password",
            "app_password_needed": "create_app_password",
            "account_locked": "unlock_account",
            "sign_in_method_off": "check_sign_in_method",
            "server_busy": "retry_later",
            "secure_connection_failed": "check_secure_connection",
            "unknown": "review_server_message",
        }
        return Problem(kind, cleaned, advice[kind], reason)

    codes = re.findall(r"\[([A-Z][A-Z0-9-]*)(?:\s[^\]]*)?\]", cleaned, re.IGNORECASE)
    strong = {"UNAVAILABLE": "server_busy", "PRIVACYREQUIRED": "secure_connection_failed"}
    decisive = {strong[code.upper()] for code in codes if code.upper() in strong}
    if len(decisive) > 1:
        return result("unknown", "Response codes indicate conflicting causes.")
    if decisive:
        return result(decisive.pop(), "The standard response code specifies the cause.")
    # Generic authentication and authorization codes do not prove a bad password or a lockout.
    if any(code.upper() in {"AUTHORIZATIONFAILED", "EXPIRED", "CONTACTADMIN", "NOPERM"} for code in codes):
        return result("unknown", "The response code does not identify one of the supported causes.")

    rules = RULES if rules is None else rules
    if not isinstance(rules, list):
        raise ValueError("Rules must be a list")
    normalized_host = host.rstrip(".").casefold()
    matches = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("phrase"), str):
            raise ValueError("Each rule needs a phrase")
        kind = rule.get("kind")
        if kind not in KINDS:
            raise ValueError("Unsupported rule kind")
        domains = rule.get("hosts", [])
        if not isinstance(domains, list) or not all(isinstance(domain, str) for domain in domains):
            raise ValueError("Rule hosts must be a list of strings")
        if domains and normalized_host not in {domain.casefold().rstrip(".") for domain in domains}:
            continue
        phrase = rule["phrase"].strip().casefold()
        if not phrase:
            raise ValueError("Rule phrases must not be empty")
        if phrase in cleaned.casefold():
            matches.add(kind)
    # A specific cause outranks the generic "credentials refused".
    if len(matches) > 1:
        matches.discard("credentials_refused")
    if len(matches) == 1:
        return result(matches.pop(), "An explicit refusal phrase identifies the cause.")
    if matches:
        return result("unknown", "Refusal phrases indicate conflicting causes.")
    if any(code.upper() == "AUTHENTICATIONFAILED" for code in codes):
        return result("credentials_refused", "The server refused the user name or password.")
    return result("unknown", "The refusal does not state a supported cause clearly enough.")
