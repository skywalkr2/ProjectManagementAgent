"""A claim of "built" must name a test that exists (design 10.5). Each test plants small markdown in a scratch tree."""

from pathlib import Path

import pytest

from engine.selfcheck.built_claims import check_claims, find_claims, scan_built_claims


@pytest.fixture
def root(tmp_path: Path) -> Path:
    files = {
        "tests/test_alpha.py": "def test_first_thing():\n    pass\n\n\nasync def test_second_thing():\n    pass\n",
        "web/src/components/Panel.test.tsx": 'test("shows the list", () => {});\nit("hides it again", () => {});\n',
        "web/e2e/flow.spec.ts": 'test("J1 the whole path", async () => {});\n',
        "docs/design/01-a.md": "",
    }
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def roadmap(root: Path, text: str):
    findings, _ = check_claims(text, "roadmap.md", root, roadmap=True)
    return findings


def design(root: Path, text: str):
    findings, _ = check_claims(text, "design.md", root, roadmap=False)
    return findings


def test_a_checked_box_citing_an_existing_test_file_passes(root):
    assert roadmap(root, "- [x] Done. Built: `tests/test_alpha.py`.\n") == []


def test_a_checked_box_citing_a_missing_file_fails(root):
    findings = roadmap(root, "- [x] Done. Built: `tests/test_missing.py`.\n")
    assert len(findings) == 1 and "tests/test_missing.py" in findings[0].message and findings[0].line == 1


def test_a_checked_box_citing_no_test_fails(root):
    assert len(roadmap(root, "- [x] Done, and it works.\n")) == 1


def test_a_wrong_test_name_fails_and_the_right_one_passes(root):
    assert roadmap(root, "- [x] Done (`tests/test_alpha.py::test_first_thing`).\n") == []
    assert roadmap(root, "- [x] Done (`tests/test_alpha.py::test_second_thing`).\n") == []
    wrong = roadmap(root, "- [x] Done (`tests/test_alpha.py::test_other_thing`).\n")
    assert len(wrong) == 1 and "test_other_thing" in wrong[0].message


def test_a_bare_test_name_must_be_defined_in_some_test(root):
    assert roadmap(root, "- [x] Done (`test_first_thing`).\n") == []
    assert len(roadmap(root, "- [x] Done (`test_not_there`).\n")) == 1


def test_a_bare_file_name_and_a_screen_test_title_are_checked(root):
    assert roadmap(root, "- [x] Done (`Panel.test.tsx`, `flow.spec.ts` J1).\n") == []
    assert roadmap(root, "- [x] Done (`web/src/components/Panel.test.tsx::shows`).\n") == []
    assert roadmap(root, "- [x] Done (`src/components/Panel.test.tsx`, `web/e2e/flow.spec.ts`).\n") == []
    assert len(roadmap(root, "- [x] Done (`Gone.test.tsx`).\n")) == 1
    assert len(roadmap(root, "- [x] Done (`web/src/components/Panel.test.tsx::nowhere`).\n")) == 1


def test_checked_by_reading_passes_without_a_test(root):
    assert roadmap(root, "- [x] The README says it. Docs only, checked by reading.\n") == []


def test_checked_by_reading_does_not_excuse_a_missing_file(root):
    assert len(roadmap(root, "- [x] Docs, checked by reading, and `tests/test_missing.py`.\n")) == 1


def test_an_unchecked_box_is_ignored(root):
    assert roadmap(root, "- [ ] Not done yet, no test.\n") == []
    assert find_claims("- [ ] Not done yet.\n", "r.md", roadmap=True) == []


def test_a_box_covers_its_continuation_lines_and_nested_items_only(root):
    text = "- [x] First, built:\n  `tests/test_alpha.py`\n  - nested note\n- [x] Second, no test\n"
    findings = roadmap(root, text)
    assert [f.line for f in findings] == [4]


def test_a_built_marker_in_a_table_row_is_judged_on_that_row(root):
    table = "| Old | New |\n|---|---|\n| One | **Built (A2):** `tests/test_alpha.py` |\n| Two | **Built (A2)** |\n"
    findings = design(root, table)
    assert [f.line for f in findings] == [4]


def test_a_built_marker_in_a_paragraph_or_list_item_is_judged_on_that_unit(root):
    text = (
        "A paragraph that is **Built:** `tests/test_alpha.py`.\n\n"
        "- **Built (phase A2):** an item\n  that cites `tests/test_missing.py`.\n- Other item, **Built**.\n"
    )
    findings = design(root, text)
    assert [f.line for f in findings] == [3, 5]
    assert "test_missing.py" in findings[0].message


def test_design_text_without_a_marker_is_not_a_claim(root):
    assert design(root, "Built-in features are for what happens every day. Not built yet: the rest.\n") == []


def test_an_under_review_claim_is_skipped_and_a_stale_entry_is_reported(root):
    text = "- [x] Done with no test.\n"
    key = find_claims(text, "roadmap.md", roadmap=True)[0].key
    findings, failing = check_claims(text, "roadmap.md", root, roadmap=True, under_review=[key])
    assert findings == [] and failing == {key}

    docs = root / "docs" / "project"
    docs.mkdir(parents=True)
    (docs / "roadmap-to-1.0.md").write_text("- [x] Done. Built: `tests/test_alpha.py`.\n", encoding="utf-8")
    stale = scan_built_claims(root, under_review=["roadmap-to-1.0.md: stale entry"])
    assert len(stale) == 1 and "under review but now passes" in stale[0].message


def test_the_roadmap_and_the_design_make_no_unproven_claim_of_built():
    assert scan_built_claims() == []
