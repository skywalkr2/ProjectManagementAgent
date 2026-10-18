"""The splitter against fifty hard plain-text emails, each labeled with the text its writer added."""

from pathlib import Path

import pytest
import yaml

from engine.reply_split import split_message

CASES = yaml.safe_load((Path(__file__).parent / "fixtures" / "steward" / "tricky_emails.yaml").read_text())

# Known gaps, each erring toward the safe side or needing judgment the rules can't make:
# a line that only looks like a quote or a reply marker, and a closing in the middle of the text.
LOST_ALLOWED = {35, 36, 48}
LEAKED_ALLOWED = {39}


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


@pytest.mark.parametrize("case", CASES, ids=[str(case["id"]) for case in CASES])
def test_tricky_email(case):
    got, want = lines(split_message(case["email"]).new), lines(case["new"])
    lost = [line for line in want if line not in got]
    leaked = [line for line in got if line not in want]
    assert not lost or case["id"] in LOST_ALLOWED, lost
    assert not leaked or case["id"] in LEAKED_ALLOWED, leaked


def test_allowances_are_still_needed():
    for case in CASES:
        got, want = lines(split_message(case["email"]).new), lines(case["new"])
        if case["id"] in LOST_ALLOWED:
            assert [line for line in want if line not in got], case["id"]
        if case["id"] in LEAKED_ALLOWED:
            assert [line for line in got if line not in want], case["id"]
