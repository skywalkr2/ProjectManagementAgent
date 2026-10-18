"""The learning pairs for dates, replies owed and facts about people are well formed, and the rules already avoid the
mistakes they describe where a rule is the right tool."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from engine.document_dates import find_dates
from engine.replies_owed import Address, Message, reply_owed

ROOT = Path(__file__).parents[1] / "docs" / "project"
KEYS = {"message", "wrong", "correction", "lesson", "later_message", "right_answer"}


@pytest.mark.parametrize("name", ["dates", "replies", "people"])
def test_pairs_are_complete(name):
    pairs = yaml.safe_load((ROOT / f"steward-learning-pairs-{name}.yaml").read_text())
    assert len(pairs) == 20
    for pair in pairs:
        assert set(pair) == KEYS and all(isinstance(pair[key], str) and pair[key].strip() for key in KEYS)
        assert pair["message"] != pair["later_message"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Your renewal date is 04/05/2028. Dates in this letter use day/month/year.", "2028-05-04"),
        ("Payment due 07/08/2028. All dates use day/month/year.", "2028-08-07"),
    ],
)
def test_a_stated_date_order_wins_over_the_locale(text, expected):
    found = find_dates(text, datetime(2027, 1, 5, tzinfo=UTC), UTC, "en-US")
    assert [(f.date.isoformat(), f.certain) for f in found] == [(expected, True)]


@pytest.mark.parametrize(
    "text",
    [
        "No need to reply about the sketches. Could you still confirm your arrival time?",
        "No answer needed on the deposit. Please tell me who will collect the keys.",
    ],
)
def test_a_waiver_on_one_topic_never_drops_another(text):
    now = datetime(2027, 1, 6, 12, tzinfo=UTC)
    message = Message(
        text, Address("dev@example.com"), (Address("rowan@example.com"),), (), now - timedelta(days=2), False
    )
    assert reply_owed(message, ("rowan@example.com",), (), now, 24).owed is not False
