"""The skills check: every evaluation case, learning pair and scenario the product ships names the skills it proves
(design 6.16, "What a model can do, measured"), and every name is on the skills list.

It reads the fictional workspaces' `evals/`, `pairs/` and `scenarios/` folders and the evaluation cases of the bundled
plugins. A case with no `skills:` or an unknown skill id is a finding; a file that doesn't load is one too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.selfcheck.scans import REPO, Finding
from engine.skills import check_named
from engine.yaml_load import load_yaml

FOLDERS = ("evals", "pairs", "scenarios")


def _cases(folder: Path) -> list[tuple[Path, Any]]:
    found = []
    for path in sorted(folder.glob("*.yaml")):
        loaded = load_yaml(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):  # a list is a starting state several cases share, not a case
            found.append((path, loaded))
    return found


def check_skills_named(workspaces: list[Path] | None = None, plugins: Path | None = None) -> list[Finding]:
    """The findings for every case file under the given workspaces (default: the fictional ones) and the bundled
    plugins' evaluation folders."""
    from engine.selfcheck import FIXTURES

    folders = [ws / name for ws in (workspaces or list(FIXTURES)) for name in FOLDERS]
    folders += sorted((plugins or REPO / "plugins").glob("*/evals"))
    findings = []
    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            cases = _cases(folder)
        except (OSError, ValueError) as err:
            findings.append(
                Finding(
                    "skills", str(folder.relative_to(REPO)) if folder.is_relative_to(REPO) else str(folder), 0, str(err)
                )
            )
            continue
        for path, case in cases:
            where = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
            try:
                check_named(f"case {case.get('id', path.stem)}", case.get("skills"), required=True)
            except ValueError as err:
                findings.append(Finding("skills", where, 0, str(err)))
    return findings
