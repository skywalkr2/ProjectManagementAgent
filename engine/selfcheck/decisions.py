"""The "decisions" check: a decision isn't done until the design text says it (the working rules), so every decision
entry from `SINCE` on cites the change-log section that records it in the design ("Change log: section 140"), or says
"Change log: none" with its reason when it changes no design text. A cited section must exist in
`docs/design/CHANGES.md`. The rule is checked here instead of remembered, because remembering it slipped.
"""

from __future__ import annotations

import re

from engine.selfcheck.scans import REPO, Finding

DECISIONS = "docs/decisions.md"
CHANGES = "docs/design/CHANGES.md"
#: Entries before this date were written before the check, and keep their citations as they are.
SINCE = "2026-10-21"

_ENTRY = re.compile(r"^## (\d{4}-\d{2}-\d{2}): (.+)$", re.MULTILINE)
_SECTION = re.compile(r"^## (\d+)\. ", re.MULTILINE)
_CITED = re.compile(r"[Cc]hange log:\s+sections?\s+(\d+(?:(?:\s*,\s*|\s+and\s+)\d+)*)")
_NONE = re.compile(r"[Cc]hange log:\s+none\b")


def check_decisions(decisions: str | None = None, changes: str | None = None) -> list[Finding]:
    text = decisions if decisions is not None else (REPO / DECISIONS).read_text(encoding="utf-8")
    log = changes if changes is not None else (REPO / CHANGES).read_text(encoding="utf-8")
    sections = {int(n) for n in _SECTION.findall(log)}
    entries = list(_ENTRY.finditer(text))
    findings: list[Finding] = []
    for i, entry in enumerate(entries):
        day, title = entry.group(1), entry.group(2)
        if day < SINCE:
            continue
        body = text[entry.end() : entries[i + 1].start() if i + 1 < len(entries) else len(text)]
        line = text.count("\n", 0, entry.start()) + 1
        cited = [int(n) for group in _CITED.findall(body) for n in re.findall(r"\d+", group)]
        if not cited and not _NONE.search(body):
            message = f"'{title[:60]}' cites no change-log section; add 'Change log: section N', or 'Change log: none'"
            findings.append(Finding("decisions", DECISIONS, line, message))
        for n in cited:
            if n not in sections:
                findings.append(
                    Finding("decisions", DECISIONS, line, f"'{title[:60]}' cites section {n}, which isn't there")
                )
    return findings
