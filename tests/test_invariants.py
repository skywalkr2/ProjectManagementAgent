"""Invariants stated in the op reference (design 6.7): each check the applier always refuses by has one plain line,
shown under the ops it constrains, and the self-check fails when a line is missing or names an op that doesn't exist.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from engine import invariants
from engine.ops import OP_MODELS, PERSON_ONLY_OPS, reference_for
from engine.selfcheck.invariants import check_invariant_lines, refusing_checks

SHIPPED = invariants.load()


def block(reference: str, op: str) -> list[str]:
    """The lines of the reference that belong to one op: its own line and the constraint lines beneath it."""
    lines = reference.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f'- "{op}":'))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith(('- "', "Every op is checked"))), len(lines)
    )
    return lines[start:end]


def test_the_reference_shows_an_invariants_line_under_each_op_it_constrains():
    reference = reference_for(["question.add", "note"])

    asked = block(reference, "question.add")
    assert f"  Always checked: {SHIPPED['question-links'].line}" in asked
    assert f"  Always checked: {SHIPPED['question-links'].line}" not in block(reference, "note")
    assert f"  Always checked: {SHIPPED['evidence'].line}" not in asked


def test_a_line_that_applies_to_every_op_follows_the_list_once():
    reference = reference_for(["note", "fact"])

    every = [
        f"Every op is checked: {SHIPPED[name].line}" for name in ("allowed-ops", "never-shown", "plugin-validator")
    ]
    assert all(reference.splitlines().count(line) == 1 for line in every)
    assert reference.splitlines()[-len(every) :] == every
    assert reference_for([]) == ""


def test_every_op_that_needs_evidence_or_is_the_persons_alone_says_so_in_the_reference():
    from engine.ops import NEEDS_EVIDENCE

    reference = reference_for(sorted(OP_MODELS))
    for op in NEEDS_EVIDENCE:
        assert f"  Always checked: {SHIPPED['evidence'].line}" in block(reference, op)
    for op in PERSON_ONLY_OPS:
        assert f"  Always checked: {SHIPPED['person-only'].line}" in block(reference, op)


def test_the_shipped_lines_cover_every_check_the_applier_refuses_by():
    applier = Path(__file__).parent.parent / "engine" / "applier.py"
    names = set(refusing_checks(applier.read_text(encoding="utf-8")))

    assert {"evidence", "targets", "question-links", "plugin-validator", "required-ops"} <= names
    assert names <= set(SHIPPED) and all(SHIPPED[name].line and SHIPPED[name].seed for name in names)
    assert check_invariant_lines() == []


def test_the_self_check_fails_for_an_invariant_without_a_line():
    without = {name: entry for name, entry in SHIPPED.items() if name != "evidence"}
    blank = {**SHIPPED, "targets": replace(SHIPPED["targets"], line="")}

    (missing,) = check_invariant_lines(without)
    assert "evidence" in missing.message and missing.path == "engine/applier.py" and missing.line > 0
    (empty,) = check_invariant_lines(blank)
    assert "targets" in empty.message


def test_the_self_check_fails_for_a_line_that_names_an_op_that_does_not_exist():
    wrong = {**SHIPPED, "evidence": replace(SHIPPED["evidence"], ops=("fact", "fact.invented"))}

    (found,) = check_invariant_lines(wrong)
    assert "evidence" in found.message and "fact.invented" in found.message


def test_the_self_check_reads_refusals_from_the_source(tmp_path):
    source = tmp_path / "applier.py"
    source.write_text(
        "def check():\n"
        "    def refuse(i, name, message): ...\n"
        "    refuse(0, 'alpha', 'x')\n"
        "    problems = [Problem('beta', 'refuse', 0, 'x'), Problem('gamma', 'hold', 0, 'x')]\n"
        "    problems += [Problem(name, 'refuse', 0, '')]\n"
    )

    assert set(refusing_checks(source.read_text())) == {"alpha", "beta"}
    names = {finding.message.split()[2] for finding in check_invariant_lines({}, applier=source)}
    assert names == {"alpha", "beta"}


def test_a_malformed_entry_is_named():
    with pytest.raises(ValueError, match="evidence"):
        invariants.parse({"evidence": {"ops": "some", "line": "x"}})
