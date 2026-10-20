"""A title's topic is never a bare word or a cut-off sentence (design 7.14): a topic from the assistant with fewer words
than `language.title_min_words` gives way to the first meaningful line of what came in only when that line is whole;
with no whole line the assistant's short topic stays (two words or more), and with none of these the topic is empty, so
the screen says it is missing. Deterministic, so a note that is only "Noted." is never what a person scans a list by,
and no title ends in a piece of a sentence."""

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


def test_a_topic_under_the_minimum_gives_way_to_a_whole_first_line_of_the_input():
    head = f"Hi,\n\nCan {ORG} host the reading?\n\nThanks"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Noted.", head) == f"Can {ORG} host the reading?"


def test_a_short_topic_beats_a_first_line_that_would_be_cut_off():
    head = "Jacket update: the approval of the back-cover copy is waiting on the designer's second pass"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Jacket update", head) == "Jacket update"


def test_with_no_topic_and_a_first_line_too_long_to_show_whole_the_topic_is_empty():
    head = "We can host the reading at six in the evening if the stage is free by then."
    assert topic({"origin": "input"}, {"trust": "untrusted"}, None, head) == ""
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Noted.", head) == ""


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


def test_with_nothing_to_fall_back_to_a_topic_of_two_words_stays_and_a_bare_word_does_not():
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Noted today.", "") == "Noted today."
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Noted.", "") == ""


def test_the_minimum_is_a_setting():
    head = "Reading on Dec 1"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Two words", head, min_words=2) == "Two words"
    assert topic({"origin": "input"}, {"trust": "untrusted"}, "Two words", head, min_words=3) == "Reading on Dec 1"


def test_work_the_app_started_is_titled_by_its_kind_and_what_it_is_about():
    request = {"origin": "schedule", "task": "follow-on"}
    title = title_for(request, None, None, people=_People(), skip=SKIP, subject="Print sync")
    assert (title.kind, title.task, title.subject, title.topic) == ("task", "follow-on", "Print sync", "")
    bare = title_for({"origin": "schedule"}, None, None, people=_People(), skip=SKIP)
    assert (bare.kind, bare.task, bare.subject) == ("task", None, "")


def test_what_work_the_app_started_is_about_comes_from_the_record_it_names_or_its_stage_entry():
    from types import SimpleNamespace

    from engine.titles import subject_of

    records = {
        ("action", "A-1"): SimpleNamespace(data={"text": "  Confirm   the seating plan "}),
        ("project", "P-1"): SimpleNamespace(data={"name": "Launch reading"}),
        ("person", "H-1"): SimpleNamespace(data={}),
    }

    class View:
        def get(self, kind, record_id):
            return records.get((kind, record_id))

    view = View()
    assert subject_of(view, {"about": {"kind": "action", "id": "A-1"}}) == "Confirm the seating plan"
    assert subject_of(view, {"stage_start": {"kind": "project", "record": "P-1", "stage": "x"}}) == "Launch reading"
    assert subject_of(view, {"about": {"kind": "person", "id": "H-1"}}) == ""
    assert subject_of(view, {"about": {"kind": "action", "id": "gone"}}) == ""
    assert subject_of(view, {}) == ""
