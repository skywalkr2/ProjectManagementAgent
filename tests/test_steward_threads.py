"""The steward's promise threads are consistent, and the reply splitter and due phrases read them as labeled."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from engine.due_phrases import resolve
from engine.reply_split import split_message

THREADS = yaml.safe_load((Path(__file__).parents[1] / "docs/project/steward-promise-threads.yaml").read_text())
KINDS = {"done", "partial", "date_changed", "cancelled", "non_answer", "condition_met"}
CLOSING = {"done", "cancelled"}


def test_threads_have_unique_ids():
    ids = [thread["id"] for thread in THREADS]
    assert len(ids) == len(set(ids)) == 25


@pytest.mark.parametrize("thread", THREADS, ids=lambda thread: thread["id"])
def test_references_and_open_promises_agree(thread):
    messages = {message["id"]: message for message in thread["messages"]}
    order = list(messages)
    promises = {promise["id"]: promise for promise in thread["promises"]}
    assert len(messages) == len(thread["messages"]) and len(promises) == len(thread["promises"])
    for promise in promises.values():
        assert promise["owner"] == messages[promise["message"]]["from"]
    still_open = set(promises)
    for resolution in thread["resolutions"]:
        assert resolution["type"] in KINDS
        promise = promises[resolution["promise"]]
        assert order.index(resolution["message"]) > order.index(promise["message"])
        if resolution["type"] == "condition_met":
            assert promise.get("condition")
        if resolution["type"] in CLOSING:
            still_open.discard(resolution["promise"])
    expected = {item["promise"]: item for item in thread["expected_open_promises"]}
    assert set(expected) == still_open
    for promise_id, item in expected.items():
        assert item["owner"] == promises[promise_id]["owner"]
        if "condition_state" in item:
            met = any(r["promise"] == promise_id and r["type"] == "condition_met" for r in thread["resolutions"])
            assert item["condition_state"] == ("met" if met else "not_met")


@pytest.mark.parametrize("thread", THREADS, ids=lambda thread: thread["id"])
def test_quoted_history_is_never_new_text(thread):
    earlier: list[str] = []
    for message in thread["messages"]:
        new = split_message(message["body"]).new
        assert ">" not in new and "wrote:" not in new
        for line in filter(None, (line.strip() for line in new.splitlines())):
            assert not any(line in text for text in earlier), (message["id"], line)
        earlier.append(new)


@pytest.mark.parametrize("thread", THREADS, ids=lambda thread: thread["id"])
def test_due_phrases_resolve_unless_conditional(thread):
    received = datetime(2026, 11, 4, 10, tzinfo=ZoneInfo("America/New_York"))
    for promise in thread["promises"] + thread["expected_open_promises"]:
        conditional = promise.get("condition") or promise.get("condition_state")
        assert resolve(promise["due"], received, received.tzinfo).start is not None or conditional
