"""Triage (design 6.5): rules in `watch.yaml` close a watched change before it reaches the assistant, with the rule
and a readable reason. Closed changes are kept and listed as Auto-closed, where the person can take a closer look,
which hands them in after all.

A rule names a matcher: the core's are below; plugins add theirs (`registrar.triage_matcher`). A matcher gets the
change (source, key, title, change, author, before, now, and the added and removed lines) and the rule's parameters,
and returns a reason in plain words, or None. Matchers are deterministic and never call AI.

A rule with `set_aside` puts mail in the Set aside folder (personal, or sales and promotions) instead of plainly
closing it; `never` keeps mail with the assistant, over every set-aside rule after it and over the built-in sorting
that follows the list (`watch.set_aside_defaults`). A match returns `{rule, reason}`, with `section` when the mail is
set aside.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable
from email.utils import parseaddr
from typing import Any

from engine.references import names_for

Matcher = Callable[[dict[str, Any], dict[str, Any]], str | None]
_NOT_WORDS = re.compile(r"[\W_]+")


def _letters(text: str) -> str:
    return _NOT_WORDS.sub("", text).lower()


def cosmetic(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """Only spacing, punctuation or capitals changed."""
    if change["change"] != "changed":
        return None
    if _letters(change["before"]) == _letters(change["now"]):
        return "only spacing, punctuation or capitals changed"
    return None


def by_us(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """The change was made by one of the workspace's own accounts (`workspace.our_accounts`)."""
    author = (change.get("author") or "").strip().lower()
    ours = {a.strip().lower() for a in change.get("our_accounts", [])}
    if author and author in ours:
        return f"it was changed by {change['author']}, one of our own accounts"
    return None


def _names(params: dict[str, Any]) -> list[str]:
    """The current names of the projects and people the rule holds by id (`names`, filled in by `classify`)."""
    return [str(n).lower() for n in params.get("names", []) if str(n).strip()]


def terms_absent(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """None of the rule's `terms`, nor the names of the projects and people it holds by id, appears in what changed
    (the added and removed lines, or a new item's text). A rule with nothing to look for closes nothing."""
    terms = [str(t).lower() for t in params.get("terms", []) if str(t).strip()] + _names(params)
    if not terms:
        return None
    changed = "\n".join(change["added"] + change["removed"]) if change["change"] == "changed" else change["now"]
    if not any(term in changed.lower() for term in terms):
        return f"none of {', '.join(terms)} appears in what changed"
    return None


def name_matches(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """The item's key or title matches one of the rule's `patterns` (like *.tmp or Draft*), or holds the name of one of
    the projects or people the rule holds by id."""
    for pattern in params.get("patterns", []):
        if fnmatch.fnmatch(change["key"], pattern) or fnmatch.fnmatch(change["title"], pattern):
            return f"its name matches {pattern}"
    for name in _names(params):
        if name in str(change["key"]).lower() or name in str(change["title"]).lower():
            return f"its name holds {name}"
    return None


def _message(change: dict[str, Any]) -> dict[str, Any]:
    return change.get("message") or {}


def sender_address(change: dict[str, Any]) -> str:
    """The mail item's sender address in lower case: from the message's sender, else its author, else the text's
    first From line; empty when none holds an address."""
    candidates = [_message(change).get("sender"), change.get("author")]
    candidates += [line[5:] for line in str(change.get("now") or "").splitlines()[:6] if line[:5].lower() == "from:"]
    for candidate in candidates:
        address = parseaddr(str(candidate or ""))[1].strip().lower()
        if "@" in address:
            return address
    return ""


def bulk_mail(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """The message says it was sent to many (a list-unsubscribe address, or a bulk or list precedence)."""
    if _message(change).get("bulk") is True:
        return "it was sent to many people, as a mailing list or bulk mail"
    return None


def service_category(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """One of the mail service's own categories for the message is among the rule's `categories`."""
    wanted = {str(c).strip().lower() for c in params.get("categories", []) if str(c).strip()}
    found = sorted(wanted & {str(c).strip().lower() for c in _message(change).get("categories") or []})
    if found:
        return f"your mail service files it under {', '.join(found)}"
    return None


def _domain(text: Any) -> str:
    return str(text).strip().lower().removeprefix("*.").lstrip("@").strip(".")


def sender_rule(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """The sender's address is one of the rule's `senders`, or its domain (or a domain it is inside) is one of the
    rule's `domains`. Case doesn't matter."""
    address = sender_address(change)
    if not address:
        return None
    senders = {str(s).strip().lower() for s in params.get("senders", []) if str(s).strip()}
    if address in senders:
        return f"it is from {address}"
    host = address.rpartition("@")[2]
    for domain in (_domain(d) for d in params.get("domains", [])):
        if domain and (host == domain or host.endswith("." + domain)):
            return f"it is from {domain}"
    return None


CORE: dict[str, Matcher] = {
    "cosmetic": cosmetic,
    "by-us": by_us,
    "terms-absent": terms_absent,
    "name-matches": name_matches,
    "bulk-mail": bulk_mail,
    "service-category": service_category,
    "sender-rule": sender_rule,
}

#: The sorting built in after the workspace's own rules: matcher, its settings, the rule's name and the section.
BUILT_IN_SET_ASIDE: tuple[tuple[str, dict[str, Any], str, str], ...] = (
    ("bulk-mail", {}, "Bulk mail", "sales"),
    ("service-category", {"categories": ["promotions", "social", "forums"]}, "Promotions and social", "sales"),
)


def matchers(store: Any) -> dict[str, Matcher]:
    return {**CORE, **store.plugins.triage_matchers()}


def first_match(store: Any, cfg: Any, change: dict[str, Any]) -> dict[str, str] | None:
    """The first rule that closes this change: {rule, reason}, plus `section` (personal or sales) when the rule sets
    mail aside, or None. A matching `never` rule keeps the mail with the assistant against every later set-aside rule
    and the built-in sorting; other rules still apply."""
    return classify(store, cfg, change)[0]


def classify(store: Any, cfg: Any, change: dict[str, Any]) -> tuple[dict[str, str] | None, bool]:
    """What the rules and the built-in sorting make of this change: the match `first_match` gives, and whether a
    `never` rule keeps the mail with the assistant (so no later sorting, the assistant's included, may set it aside)."""
    found = matchers(store)
    kept = False
    for rule in cfg.watch.triage:
        if rule.sources and change["source"] not in rule.sources:
            continue
        match = found.get(rule.kind)
        if match is None:
            continue
        if kept and rule.set_aside:
            continue
        params = dict(rule.params)
        if rule.projects or rule.people:
            view = store.read()
            params["names"] = [*names_for(view, "project", rule.projects), *names_for(view, "person", rule.people)]
        reason = (
            store.plugins.run_matcher(rule.kind, match, change, params) if "/" in rule.kind else match(change, params)
        )
        if not reason:
            continue
        if rule.set_aside == "never":
            kept = True
            continue
        why = rule.why.format(reason=reason) if rule.why else reason
        closed = {"rule": rule.name, "reason": why}
        if rule.set_aside:
            closed["section"] = rule.set_aside
        return closed, kept
    if kept or not change.get("message") or not cfg.watch.set_aside_defaults:
        return None, kept
    for kind, params, name, section in BUILT_IN_SET_ASIDE:
        reason = CORE[kind](change, params)
        if reason:
            return {"rule": name, "reason": reason, "section": section}, kept
    return None, kept
