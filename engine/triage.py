"""Triage (design 6.5): rules in `watch.yaml` close a watched change before it reaches the assistant, with the rule
and a readable reason. Closed changes are kept and listed as Auto-closed, where the person can take a closer look,
which hands them in after all.

A rule names a matcher: the core's are below; plugins add theirs (`registrar.triage_matcher`). A matcher gets the
change (source, key, title, change, author, before, now, and the added and removed lines) and the rule's parameters,
and returns a reason in plain words, or None. Matchers are deterministic and never call AI.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable
from typing import Any

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


def terms_absent(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """None of the rule's `terms` appears in what changed (the added and removed lines, or a new item's text)."""
    terms = [str(t).lower() for t in params.get("terms", []) if str(t).strip()]
    if not terms:
        return None
    changed = "\n".join(change["added"] + change["removed"]) if change["change"] == "changed" else change["now"]
    if not any(term in changed.lower() for term in terms):
        return f"none of {', '.join(terms)} appears in what changed"
    return None


def name_matches(change: dict[str, Any], params: dict[str, Any]) -> str | None:
    """The item's key or title matches one of the rule's `patterns` (like *.tmp or Draft*)."""
    for pattern in params.get("patterns", []):
        if fnmatch.fnmatch(change["key"], pattern) or fnmatch.fnmatch(change["title"], pattern):
            return f"its name matches {pattern}"
    return None


CORE: dict[str, Matcher] = {
    "cosmetic": cosmetic,
    "by-us": by_us,
    "terms-absent": terms_absent,
    "name-matches": name_matches,
}


def matchers(store: Any) -> dict[str, Matcher]:
    return {**CORE, **store.plugins.triage_matchers()}


def first_match(store: Any, cfg: Any, change: dict[str, Any]) -> dict[str, str] | None:
    """The first rule that closes this change: {rule, reason}, or None."""
    found = matchers(store)
    for rule in cfg.watch.triage:
        if rule.sources and change["source"] not in rule.sources:
            continue
        match = found.get(rule.kind)
        if match is None:
            continue
        reason = (
            store.plugins.run_matcher(rule.kind, match, change, dict(rule.params))
            if "/" in rule.kind
            else match(change, dict(rule.params))
        )
        if reason:
            why = rule.why.format(reason=reason) if rule.why else reason
            return {"rule": rule.name, "reason": why}
    return None
