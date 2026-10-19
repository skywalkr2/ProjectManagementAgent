"""The "built claims" check: a claim that something is built names a test that exists (design 10.5).

A claim is a checked roadmap box (`- [x]`), or in a design file a bold "Built" marker (in prose, a list item or a table
row), a table cell that starts with "Built", or a "State: Built" line (its claim is the numbered milestone it closes).
Plain "Built" in running prose is not a claim. Each claim is the list item, table row, milestone or paragraph it sits
in. It is satisfied when it cites at least one test that exists, or says "checked by reading" (docs and process items).
It fails when anything it cites is missing: a test
file that isn't there, or a test name that isn't defined in the file it is attached to (`file::name`) or anywhere in the
tests (a bare `test_name`). A test file is cited by its path (`tests/...`, `web/e2e/...`, `web/src/...`, or `src/...`
for `web/src/...`) or by its bare file name (`journeys.spec.ts`, `Addons.test.tsx`, `test_requeue.py`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from engine.selfcheck.scans import REPO, Finding

ROADMAPS = ("docs/project/roadmap-to-1.0.md", "docs/project/roadmap-done.md")
DESIGN_DIR = "docs/design"
READING = re.compile(r"checked by reading", re.IGNORECASE)

#: Claims that are still under review: each is "<file>: <first 60 characters of its first line>". A claim leaves this
#: set when it cites a test or says "checked by reading"; an entry that no longer fails is itself reported.
UNDER_REVIEW: frozenset[str] = frozenset()

CHECKBOX = re.compile(r"^\s*[-*]\s+\[[xX]\]\s")
BUILT_MARKER = re.compile(r"\*\*Built\b|\*\*built\b")
BUILT_CELL = re.compile(r"^\**built\b(?!-)", re.IGNORECASE)
STATE_BUILT = re.compile(r"\bState: Built\b")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
NUMBERED = re.compile(r"^(\s*)\d+\.\s")
LIST_START = re.compile(r"^(\s*)(?:[-*]|\d+\.)\s")
TABLE_ROW = re.compile(r"^\s*\|")
HEADING = re.compile(r"^\s*#")

PATH = re.compile(
    r"(?<![\w/.-])(?P<path>(?:web/e2e|web/src|tests|src|plugins/[\w-]+/tests)/[\w./-]+?\.(?:py|tsx?))"
    r"(?P<names>(?:::[\w\[\]-]+)*)"
)
BARE_FILE = re.compile(r"(?<![\w/.-])(?P<file>test_\w+\.py|[\w-]+(?:\.[\w-]+)*\.(?:test\.tsx?|spec\.ts))(?![\w])")
BARE_NAME = re.compile(r"(?<![\w/.:-])(?P<name>test_\w+)(?![\w.])")


@dataclass(frozen=True)
class Claim:
    path: str
    line: int
    text: str

    @property
    def key(self) -> str:
        head = " ".join(self.text.split("\n", 1)[0].split())
        return f"{self.path}: {head[:60]}"


def _is_list_start(line: str) -> bool:
    return LIST_START.match(line) is not None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _item_from(lines: list[str], start: int) -> tuple[int, str]:
    """A list item or paragraph starting at `start`: its lines up to a blank line, a heading, a table row or the next
    item at the same or a lower indent. Returns the line after it and its text."""
    base = _indent(lines[start])
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip() or HEADING.match(line) or TABLE_ROW.match(line):
            break
        if _is_list_start(line) and _indent(line) <= base:
            break
        end += 1
    return end, "\n".join(lines[start:end])


def _marker_unit(lines: list[str], at: int) -> tuple[int, str]:
    """The table row, list item or paragraph that holds the marker on line `at`; returns its first line and text."""
    if TABLE_ROW.match(lines[at]):
        return at, lines[at]
    start = at
    while start > 0 and lines[start].strip() and not _is_list_start(lines[start]):
        if not lines[start - 1].strip() or HEADING.match(lines[start - 1]) or TABLE_ROW.match(lines[start - 1]):
            break
        start -= 1
    return start, _item_from(lines, start)[1]


def _has_built_cell(line: str) -> bool:
    """A table row with a cell that starts with "Built" (any case, not "built-in")."""
    return TABLE_ROW.match(line) is not None and any(BUILT_CELL.match(c.strip()) for c in CELL_SPLIT.split(line))


def _state_block(lines: list[str], at: int) -> tuple[int, str]:
    """The numbered item (a milestone) that holds the "State:" line at `at`: its first line and text."""
    start = at
    while start > 0 and not (NUMBERED.match(lines[start]) and _indent(lines[start]) < _indent(lines[at])):
        start -= 1
    base = _indent(lines[start])
    end = start + 1
    while end < len(lines) and not HEADING.match(lines[end]):
        if NUMBERED.match(lines[end]) and _indent(lines[end]) <= base:
            break
        end += 1
    return start, "\n".join(lines[start:end])


def find_claims(text: str, path: str, *, roadmap: bool) -> list[Claim]:
    """Every claim in one markdown file: checked boxes when `roadmap`, bold Built markers otherwise."""
    lines = text.split("\n")
    claims: list[Claim] = []
    seen: set[int] = set()
    for number, line in enumerate(lines):
        if roadmap:
            if not CHECKBOX.match(line):
                continue
            first, unit = number, _item_from(lines, number)[1]
        else:
            if STATE_BUILT.search(line):
                first, unit = _state_block(lines, number)
            elif _has_built_cell(line):
                first, unit = number, line
            elif BUILT_MARKER.search(line):
                first, unit = _marker_unit(lines, number)
            else:
                continue
        if first in seen:
            continue
        seen.add(first)
        claims.append(Claim(path, first + 1, unit))
    return claims


class TestIndex:
    """The test files of a checkout and the test names they define, read once and only when asked."""

    __test__ = False

    def __init__(self, root: Path) -> None:
        self.root = root

    @cached_property
    def files_by_name(self) -> dict[str, list[Path]]:
        found: dict[str, list[Path]] = {}
        patterns = [
            ("tests", "*.py"),
            ("web/src", "*.test.ts*"),
            ("web/e2e", "*.ts"),
            ("plugins", "tests/*.py"),
            ("plugins", "*/tests/*.py"),
        ]
        for folder, pattern in patterns:
            base = self.root / folder
            if base.is_dir():
                for file in base.rglob(pattern):
                    if "node_modules" not in file.parts:
                        found.setdefault(file.name, []).append(file)
        return found

    @cached_property
    def python_names(self) -> set[str]:
        names: set[str] = set()
        for files in self.files_by_name.values():
            for file in files:
                if file.suffix == ".py":
                    names.update(re.findall(r"^\s*(?:async\s+)?def (test_\w+)", _read(file), re.MULTILINE))
        return names

    def resolve(self, cited: str) -> Path | None:
        """The file a cited path names, if it exists (`src/` means `web/src/`)."""
        rel = f"web/{cited}" if cited.startswith("src/") else cited
        file = self.root / rel
        return file if file.is_file() else None

    def defines(self, file: Path, name: str) -> bool:
        text = _read(file)
        if file.suffix == ".py":
            return re.search(rf"^\s*(?:async\s+)?def {re.escape(name)}\b", text, re.MULTILINE) is not None
        title = re.compile(rf"\b(?:test|it)(?:\.\w+)*\(\s*(['\"`])[^\n]*?{re.escape(name)}")
        return title.search(text) is not None


def _read(file: Path) -> str:
    try:
        return file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def judge(claim: Claim, index: TestIndex) -> list[str]:
    """What is wrong with a claim: empty when it cites only tests that exist (and at least one), or is checked by
    reading."""
    problems: list[str] = []
    cited = 0
    text = claim.text
    for match in PATH.finditer(text):
        cited += 1
        file = index.resolve(match["path"])
        if file is None:
            problems.append(f"cites {match['path']}, which doesn't exist")
            continue
        for name in [n for n in match["names"].split("::") if n]:
            if not index.defines(file, name.split("[")[0]):
                problems.append(f"cites {name} in {match['path']}, which doesn't define it")
    bare_text = PATH.sub(" ", text)
    for match in BARE_FILE.finditer(bare_text):
        cited += 1
        if match["file"] not in index.files_by_name:
            problems.append(f"cites {match['file']}, which doesn't exist")
    for match in BARE_NAME.finditer(bare_text):
        cited += 1
        if match["name"] not in index.python_names:
            problems.append(f"cites {match['name']}, which no test defines")
    if problems:
        return problems
    if cited or READING.search(text):
        return []
    return ["cites no test and isn't marked as checked by reading"]


def check_claims(
    text: str, path: str, root: Path, *, roadmap: bool, under_review: Iterable[str] = ()
) -> tuple[list[Finding], set[str]]:
    """The findings for one markdown file's claims, against the tests under `root`, and the keys of the claims that
    fail but are listed as under review."""
    index = TestIndex(root)
    skipped = set(under_review)
    findings: list[Finding] = []
    failing: set[str] = set()
    for claim in find_claims(text, path, roadmap=roadmap):
        problems = judge(claim, index)
        if problems and claim.key in skipped:
            failing.add(claim.key)
        else:
            findings += [Finding("built", path, claim.line, f"a claim of 'built' {p}") for p in problems]
    return findings, failing


def scan_built_claims(root: Path = REPO, under_review: Iterable[str] | None = None) -> list[Finding]:
    """Every claim in the roadmap and the design files, plus any under-review entry that no longer fails."""
    exceptions = set(UNDER_REVIEW if under_review is None else under_review)
    files = [(rel, True) for rel in ROADMAPS] + [
        (f"{DESIGN_DIR}/{p.name}", False) for p in sorted((root / DESIGN_DIR).glob("*.md"))
    ]
    findings: list[Finding] = []
    failing: set[str] = set()
    for rel, roadmap in files:
        file = root / rel
        if file.is_file():
            more, keys = check_claims(_read(file), rel, root, roadmap=roadmap, under_review=exceptions)
            findings += more
            failing |= keys
    for key in sorted(exceptions - failing):
        findings.append(Finding("built", "engine/selfcheck/built_claims.py", 0, f"under review but now passes: {key}"))
    return findings
