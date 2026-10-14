"""The invariant-lines check: every check the applier always refuses by has its one-line constraint (design 6.7).

The check names are read from the applier's own source: the second argument of each `refuse(...)` call, and the first
argument of each `Problem(..., "refuse", ...)`. Each needs an entry in `engine/defaults/invariants.yaml` with a line,
because the op reference prints that line under the ops it constrains, and an entry may name only ops that exist. The
check fails for a refusing check with no line, an entry that names an op that doesn't exist, and a file that can't be
read.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from engine import invariants
from engine.ops import OP_MODELS
from engine.selfcheck.scans import REPO, Finding

APPLIER = REPO / "engine" / "applier.py"
WHERE = "engine/defaults/invariants.yaml"


def refusing_checks(source: str) -> dict[str, int]:
    """The check names the applier refuses by, each with the line of its first use."""
    found: dict[str, int] = {}

    def note(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.setdefault(node.value, node.lineno)

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name == "refuse" and len(node.args) >= 2:
            note(node.args[1])
        elif name == "Problem" and len(node.args) >= 2:
            severity = node.args[1]
            if isinstance(severity, ast.Constant) and severity.value == "refuse":
                note(node.args[0])
    return found


def check_invariant_lines(
    lines: dict[str, invariants.Invariant] | None = None, applier: Path = APPLIER
) -> list[Finding]:
    """Findings for a refusing check with no line and for an entry naming an op that doesn't exist."""
    try:
        known = lines if lines is not None else invariants.load()
    except (OSError, ValueError, yaml.YAMLError) as err:
        return [Finding("invariants", WHERE, 0, f"can't be read: {err}")]
    findings: list[Finding] = []
    for name, line in refusing_checks(applier.read_text(encoding="utf-8")).items():
        entry = known.get(name)
        if entry is None or not entry.line:
            findings.append(
                Finding(
                    "invariants",
                    str(applier.relative_to(REPO)) if applier.is_relative_to(REPO) else str(applier),
                    line,
                    f"the check {name} refuses ops but has no one-line constraint in {WHERE}",
                )
            )
    for entry in known.values():
        findings += [
            Finding("invariants", WHERE, 0, f"{entry.name} names {op}, which isn't an op")
            for op in entry.ops or ()
            if op not in OP_MODELS
        ]
    return findings
