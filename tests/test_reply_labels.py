"""Against 60 labeled fictional messages, the replies-owed rules are never confidently wrong: an "owed" or "not owed"
always matches the label, and anything they can't settle is left unknown for the reading step."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from engine.replies_owed import Address, Message, reply_owed

ITEMS = yaml.safe_load((Path(__file__).parent / "fixtures" / "steward" / "reply_labels.yaml").read_text())
NOW = datetime(2027, 1, 6, 12, tzinfo=UTC)
SENT = NOW - timedelta(hours=48)


def addresses(value):
    return tuple(Address(email) for email in ([value] if isinstance(value, str) else value or []))


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: str(item["id"]))
def test_rules_are_never_confidently_wrong(item):
    message = Message(
        item["body"], Address(item["from"]), addresses(item["to"]), addresses(item.get("cc")), SENT, item["automatic"]
    )
    later = tuple(
        Message(reply["body"], Address(reply["from"]), addresses(reply["to"]), (), SENT + timedelta(hours=1), False)
        for reply in item.get("later_messages", [])
    )
    result = reply_owed(message, ("rowan@example.com",), later, NOW, 24)
    if result.owed is not None:
        assert result.owed == (item["label"] == "needs a reply"), (result.code, item["reason"])


def test_the_set_is_balanced():
    labels = [item["label"] for item in ITEMS]
    assert labels.count("needs a reply") == labels.count("no reply needed") == 30
