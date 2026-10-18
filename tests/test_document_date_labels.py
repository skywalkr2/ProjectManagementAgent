"""Against 40 labeled fictional documents, the date finder is never confidently wrong: every date it calls certain is
one a careful reader calls certain. Dates it misses (kinds it doesn't look for) are left to the reading step."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from engine.document_dates import find_dates

ITEMS = yaml.safe_load((Path(__file__).parent / "fixtures" / "steward" / "document_dates.yaml").read_text())


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: str(item["id"]))
def test_certain_dates_are_ones_a_reader_calls_certain(item):
    certain = {fact["date"] for fact in item["facts"] if fact["certain"] and fact["date"]}
    # No locale: the documents don't say whose they are, so an all-numeric date stays ambiguous.
    for finding in find_dates(item["snippet"], datetime(2027, 1, 5, tzinfo=UTC), UTC, "unknown"):
        if finding.certain:
            assert finding.date.isoformat() in certain, (finding.kind, finding.evidence)


def test_two_different_dates_of_one_kind_are_both_uncertain():
    item = next(item for item in ITEMS if item["id"] == 27)
    findings = find_dates(item["snippet"], datetime(2027, 1, 5, tzinfo=UTC), UTC, "en-US")
    assert len(findings) == 2 and not any(finding.certain for finding in findings)
