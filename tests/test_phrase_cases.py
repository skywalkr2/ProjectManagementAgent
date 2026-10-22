"""The rules held to what people mean by deadline and repeat phrases (the outside helper's cases in
tests/fixtures/phrases/). The rules may decline a phrase, which leaves the date for the person to check; whatever they
read firmly must be what a person means, and nothing unclear or waiting on an event gets a firm date or a repeat."""

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from dateutil.rrule import rrulestr

from engine.due_phrases import DEFAULT_CONDITION_WORDS, is_condition, resolve
from engine.repeat_phrases import Unknown, rule_from_phrase

PHRASES = Path(__file__).parent / "fixtures" / "phrases"
DUE = yaml.safe_load((PHRASES / "due-phrases-01.yaml").read_text(encoding="utf-8"))
REPEAT = yaml.safe_load((PHRASES / "repeat-phrases-01.yaml").read_text(encoding="utf-8"))

# The rules read the end of a week as its last working day, the earlier of the two readings people use, so a promise
# is never due later than meant; the helper's answer is the whole week through Sunday.
WORKWEEK_END = {"end of the week", "end of next week"}


def _received(stamp: str) -> tuple[datetime, ZoneInfo]:
    moment, name = re.fullmatch(r"(.+?)\[(.+)\]", stamp).groups()
    here = ZoneInfo(name)
    return datetime.fromisoformat(moment).astimezone(here), here


@pytest.mark.parametrize("case", DUE, ids=lambda c: f"{c['phrase']}@{c['received'][:10]}")
def test_a_deadline_the_rules_read_firmly_is_the_one_a_person_means(case):
    received, here = _received(case["received"])
    assert received.strftime("%A") == case["received_day"]
    found = resolve(case["phrase"], received, here)
    if case["meaning"] in ("condition", "unclear"):
        assert found.start is None and found.end is None
        if case["meaning"] == "condition":
            assert is_condition(case["phrase"], DEFAULT_CONDITION_WORDS)
        return
    if not found.exact or found.start is None or case["phrase"] in WORKWEEK_END:
        return
    assert (found.end or found.start) == date.fromisoformat(case["end"])


def _reading(case):
    received, here = _received(case["received"])
    return resolve(case["phrase"], received, here)


def test_the_rules_read_more_of_the_deadline_words_people_use_every_day():
    """How much of the helper's set the rules read for certain, never wrongly (the test above fails on a wrong one).
    Exact readings that match are what the person no longer has to check; the phrases that mean nothing firm (unclear or
    waiting on an event) must still read as nothing."""
    exact = [c for c in DUE if c["meaning"] not in ("condition", "unclear") and _reading(c).exact]
    matching = [c for c in exact if c["phrase"] not in WORKWEEK_END]
    assert all((_reading(c).end or _reading(c).start) == date.fromisoformat(c["end"]) for c in matching)
    nothing = [c for c in DUE if c["meaning"] in ("condition", "unclear") and _reading(c).start is None]
    assert len(nothing) == sum(c["meaning"] in ("condition", "unclear") for c in DUE)
    assert len(matching) >= 33
    # Counting the phrases read as nothing too (the roadmap's measure, 42 before this change).
    assert len(nothing) + len(exact) >= 55
    # The phrases the helper marked firm that are everyday words read exactly now.
    firm = {c["phrase"] for c in matching}
    for phrase in (
        "first thing Monday",
        "later today",
        "day after tomorrow",
        "end of the month",
        "end of next month",
        "11/6",
        "12/4",
        "by noon tomorrow",
        "by 5pm ET",
        "by 8 tonight",
        "by Thanksgiving",
    ):
        assert phrase in firm, phrase


def _dates(rule: str, start: date, count: int) -> list[date]:
    first = datetime.combine(start, datetime.min.time())
    return [d.date() for d in rrulestr(rule, dtstart=first).xafter(first, count=count, inc=True)]


@pytest.mark.parametrize("case", REPEAT, ids=lambda c: c["phrase"])
def test_a_repeat_the_rules_read_is_the_one_a_person_means(case):
    start = date.fromisoformat(case["start"]) if case["start"] else date(2026, 11, 2)
    if case["rule"] != "unclear":
        assert [d.isoformat() for d in _dates(case["rule"], start, 3)] == case["next_three"]
    got = rule_from_phrase(case["phrase"], start)
    if isinstance(got, Unknown):
        return
    assert case["rule"] != "unclear", f"{case['phrase']!r} is unclear, but the rules read it as {got}"
    assert _dates(got, start, 24) == _dates(case["rule"], start, 24)


# The helper's phrases that carry the to-do's own words (what to water, which meeting): the repeat is the part of a
# phrase about when, so the rules read the Repeats field, never words about what is to be done.
WITH_TASK_WORDS = {
    "water the plants every day",
    "weekday standup",
    "water plants every 2 days",
    "school pickup every Saturday",
}


def _start_of(case):
    return date.fromisoformat(case["start"]) if case["start"] else date(2026, 11, 2)


def test_the_rules_read_every_repeat_the_helper_wrote_except_those_with_the_task_in_them():
    """Every phrase the helper marked as a repeat is read, and read as the helper's rule (the test above checks the
    dates); the unclear ones and the phrases that carry other words stay declined, so nothing is read wrongly."""
    clear = [case for case in REPEAT if case["rule"] != "unclear"]
    declined = {c["phrase"] for c in clear if isinstance(rule_from_phrase(c["phrase"], _start_of(c)), Unknown)}
    assert declined == WITH_TASK_WORDS
    unclear = [case for case in REPEAT if case["rule"] == "unclear"]
    assert unclear and all(isinstance(rule_from_phrase(c["phrase"], _start_of(c)), Unknown) for c in unclear)
    assert len(clear) - len(declined) >= 40


@pytest.mark.parametrize("phrase", sorted(WITH_TASK_WORDS))
def test_a_phrase_with_the_task_in_it_is_declined_not_guessed(phrase):
    assert isinstance(rule_from_phrase(phrase, date(2026, 11, 2)), Unknown)
