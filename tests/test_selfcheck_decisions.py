"""The decisions check: a decision entry from the check's start date on cites the change-log section that records it."""

from engine.selfcheck.decisions import SINCE, check_decisions

LOG = "# What changed\n\n## 12. Something (date)\n\ntext\n\n## 11. Before (date)\n"


def entry(day, body):
    return f"## {day}: A decision\n\n- **Decided:** something.\n{body}\n\n"


def test_an_entry_citing_a_section_that_exists_passes():
    assert check_decisions(entry(SINCE, "- **Impact:** the code. Change log:\n  section 12."), LOG) == []


def test_an_entry_citing_no_section_fails_and_says_how_to_fix_it():
    (finding,) = check_decisions(entry(SINCE, "- **Impact:** the code."), LOG)
    assert "cites no change-log section" in finding.message and "Change log: none" in finding.message


def test_a_section_that_isnt_there_fails():
    (finding,) = check_decisions(entry(SINCE, "Change log: section 13."), LOG)
    assert "section 13" in finding.message


def test_an_entry_with_no_design_change_says_so_and_passes():
    assert check_decisions(entry(SINCE, "Change log: none (a process rule, no design text)."), LOG) == []


def test_entries_before_the_start_date_are_not_checked():
    assert check_decisions(entry("2026-10-20", "- **Impact:** the code."), LOG) == []


def test_the_repositorys_own_decisions_pass():
    assert check_decisions() == []
