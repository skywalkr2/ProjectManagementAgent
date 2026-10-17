"""The steward's learning pairs are well formed, and the reply splitter keeps quoted and forwarded promises out of new
text."""

from pathlib import Path

import pytest
import yaml

from engine.reply_split import split_message

PAIRS = yaml.safe_load((Path(__file__).parents[1] / "docs/project/steward-learning-pairs.yaml").read_text())
KEYS = {"id", "message", "wrong", "correction", "lesson", "later_message", "right_answer"}


def test_pairs_are_complete_and_distinct():
    assert len({pair["id"] for pair in PAIRS}) == len(PAIRS) == 20
    for pair in PAIRS:
        assert set(pair) == KEYS
        assert all(isinstance(pair[key], str) and pair[key].strip() for key in KEYS - {"id"})
        assert pair["message"] != pair["later_message"]
        assert pair["message"].startswith("From: ") and pair["later_message"].startswith("From: ")


def body(message: str) -> str:
    return message.split("\n", 1)[1]


@pytest.mark.parametrize(
    "pair_id,field,promise",
    [
        (2, "message", "send the estimate"),
        (2, "later_message", "share the draft"),
        (7, "message", "signed agreement"),
        (7, "later_message", "deliver your prints"),
        (8, "message", "We promise delivery"),
        (8, "later_message", "delivered every day"),
        (20, "later_message", "printed seating plans"),
    ],
)
def test_quoted_forwarded_and_signature_text_is_not_new(pair_id, field, promise):
    pair = next(pair for pair in PAIRS if pair["id"] == pair_id)
    assert promise not in split_message(body(pair[field])).new
