"""A title's topic is never a bare word or two (design 7.14): when the assistant's topic has fewer words than
`language.title_min_words`, the topic comes from the first meaningful line of what came in. Deterministic, so a note
that is only "Noted." is never what a person scans a list by."""

from __future__ import annotations

from engine.config.schema import DEFAULT_TITLE_SKIP
from engine.names import Resolved
from engine.titles import title_for
from tests.conftest import DEMO_B, fixture_records

SKIP = list(DEFAULT_TITLE_SKIP)
MIN = 3
ORG = fixture_records(DEMO_B, "organization")[2]["name"]


class _People:
    def resolve(self, name: str) -> Resolved:
        return Resolved("unknown")


def topic(request, source, answer, head="", *, min_words=MIN):
    return title_for(
        request,
        source,
        {"topic": answer} if answer is not None else None,
        people=_People(),
        skip=SKIP,
        head=head,
        min_words=min_words,
    ).topic


def test_a_topic_under_the_minimum_falls_back_to_the_first_meaningful_line_of_the_input():
    head = f"Hi,\n\nCan {ORG} host the reading on Dec 1?\n\nThanks"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Noted.", head) == f"Can {ORG} host the reading on…"


def test_a_topic_of_enough_words_is_kept():
    assert (
        topic({"origin": "input"}, {"trust": "untrusted"}, "The reading time", "Hello\nSomething else")
        == "The reading time"
    )


def test_a_typed_note_falls_back_to_its_own_words():
    assert (
        topic({"origin": "pm", "note": "Move the launch reading to Dec 1"}, None, "Noted.")
        == "Move the launch reading to Dec 1"
    )


def test_a_watched_items_subject_is_the_sources_own_title_and_stays():
    source = {
        "trust": "untrusted",
        "watched": {"author": "A Sender", "source": "s", "key": "k"},
        "title": "Re: Paperback",
    }
    assert topic({"origin": "input"}, source, "Noted.", "x y z") == "Paperback"


def test_with_nothing_to_fall_back_to_the_short_topic_stays():
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Noted.", "") == "Noted."


def test_the_minimum_is_a_setting():
    head = "Reading on Dec 1"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Two words", head, min_words=2) == "Two words"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Two words", head, min_words=3) == "Reading on Dec 1"
