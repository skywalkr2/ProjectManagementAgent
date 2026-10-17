"""Fictional message headers covering conservative subject fallback."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from engine.mail_threads import ThreadCandidate, normalize_subject, thread_key

STAMP = datetime(2026, 11, 6, 12, tzinfo=UTC)
PEOPLE = ("rowan@example.com", "mira@example.com")


@pytest.mark.parametrize(
    "prefix",
    [
        "Re:",
        "RE:",
        "Fwd:",
        "FW:",
        "AW:",
        "WG:",
        "SV:",
        "VS:",
        "Antw:",
        "TR:",
        "RV:",
        "回复:",
        "回覆：",
        "答复:",
        "答覆：",
        "转发:",
        "轉發：",
        "轉寄:",
        "返信:",
        "転送：",
        "Re[2]:",
        "RE [12]:",
        "[Re]:",
        "[FW]",
        "[Re:]",
        "[Re[2]]:",
        "[EXT]",
        "[External]",
        "[external]:",
    ],
)
def test_common_prefixes(prefix):
    assert normalize_subject(prefix + " [CASE-123] Draft review") == "[CASE-123] Draft review"


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Re: Fwd: [EXT] AW: [External] Re[2]: Plan", "Plan"),
        ("  RE:   Draft\r\n review  ", "Draft review"),
        ("[12345] Invoice", "[12345] Invoice"),
        ("Re: [Ticket #42] Draft", "[Ticket #42] Draft"),
        ("[RE-42] Draft", "[RE-42] Draft"),
        ("Regarding Friday", "Regarding Friday"),
        ("Re invention", "Re invention"),
        ("The [External] label", "The [External] label"),
        ("", ""),
        ("Re: FW:", ""),
        ("Re: Antw: [CASE-007] Re: Draft", "[CASE-007] Re: Draft"),
    ],
)
def test_normalization_preserves_content(subject, expected):
    assert normalize_subject(subject) == expected


def key(message_id="<new@example.com>", subject="Re: Draft", participants=PEOPLE, **options):
    return thread_key(
        message_id,
        options.pop("in_reply_to", None),
        options.pop("references", None),
        subject,
        participants,
        received=options.pop("received", STAMP),
        **options,
    )


def candidate(key_value="stored-thread", subject="Draft", participants=PEOPLE, age=1):
    return ThreadCandidate(key_value, subject, participants, STAMP - timedelta(days=age))


def test_references_beat_reply_and_subject():
    expected = key("<root@example.com>", subject="Unrelated")
    actual = key(
        references="<root@example.com> <parent@example.com>",
        in_reply_to="<wrong@example.com>",
        candidates=[candidate()],
    )
    assert actual == expected


def test_in_reply_to_beats_subject():
    assert key(in_reply_to="<parent@example.com>", candidates=[candidate()]) == key("<parent@example.com>")


def test_reference_list_folding_duplicates_and_comments():
    expected = key("<root@example.com>")
    assert (
        key(references="(ignore <fake@example.com>) <root@example.com>\r\n <root@example.com> <parent@example.com>")
        == expected
    )
    assert key(references=["<root@example.com>", "<parent@example.com>"]) == expected


def test_known_reference_can_reuse_an_existing_thread_root():
    parent = key("<parent@example.com>")
    assert key(references="<missing@example.com> <parent@example.com>", candidates=[candidate(parent)]) == parent


def test_direct_links_do_not_require_date_or_participant_overlap():
    assert key(references="<root@example.com>", participants=(), received=None) == key("<root@example.com>")


def test_fallback_requires_subject_participants_and_date():
    assert key(candidates=[candidate()]) == "stored-thread"
    assert key(candidates=[candidate(participants=("oren@example.com",))]) != "stored-thread"
    assert key(candidates=[candidate(subject="Different")]) != "stored-thread"
    assert key(candidates=[candidate(age=15)]) != "stored-thread"
    assert key(candidates=[candidate()], received=None) != "stored-thread"
    assert key(candidates=[candidate()], participants=()) != "stored-thread"


def test_overlap_is_not_exact_participant_set():
    assert key(candidates=[candidate(participants=("MIRA@example.com", "oren@example.com"))]) == "stored-thread"


@pytest.mark.parametrize("days,expected", [(0, False), (1, True), (14, True)])
def test_configurable_inclusive_window(days, expected):
    assert (key(candidates=[candidate()], max_days=days) == "stored-thread") is expected


def test_window_is_elapsed_time_not_calendar_date():
    item = ThreadCandidate("stored-thread", "Draft", PEOPLE, STAMP - timedelta(days=14, seconds=1))
    assert key(candidates=[item]) != "stored-thread"


def test_out_of_order_messages_and_equivalent_time_zones():
    assert key(candidates=[candidate(age=-1)]) == "stored-thread"
    equivalent = STAMP.astimezone(timezone(timedelta(hours=-5)))
    assert key(received=equivalent, candidates=[candidate()]) == "stored-thread"


def test_ambiguous_subject_matches_do_not_merge():
    assert key(candidates=[candidate("a"), candidate("b")]) not in {"a", "b"}
    assert key(candidates=[candidate("a"), candidate("a")]) == "a"


def test_empty_subject_does_not_merge():
    assert key(subject="Re:", candidates=[candidate(subject="")]) != "stored-thread"


def test_ticket_numbers_keep_threads_separate():
    assert key(subject="[CASE-2] Draft", candidates=[candidate(subject="[CASE-1] Draft")]) != "stored-thread"


def test_malformed_headers_and_self_reference_do_not_create_links():
    assert key(references="not a message id", in_reply_to="<new@example.com>") == key()
    assert key(in_reply_to="parent@example.com") == key("<parent@example.com>")


def test_message_ids_are_case_sensitive():
    assert key("<Root@example.com>") != key("<root@example.com>")


def test_anonymous_result_is_repeatable_and_order_independent():
    first = key(None, participants=PEOPLE)
    assert first.startswith("anonymous:")
    assert first == key(None, participants=reversed(PEOPLE))
    assert first == key(None, received=STAMP)
    assert first != key(None, received=STAMP + timedelta(seconds=1))


@pytest.mark.parametrize(
    "options",
    [
        {"max_days": -1},
        {"max_days": True},
        {"received": STAMP.replace(tzinfo=None)},
        {"participants": "rowan@example.com"},
        {"participants": ["not an address"]},
    ],
)
def test_invalid_configuration(options):
    with pytest.raises(ValueError):
        key(**options)


def test_input_collections_are_unchanged():
    people = list(PEOPLE)
    history = [candidate()]
    key(participants=people, candidates=history)
    assert people == list(PEOPLE)
    assert history == [candidate()]


def test_known_parent_message_reuses_its_existing_root():
    parent = ThreadCandidate("existing-root", "Draft", PEOPLE, STAMP, "<parent@example.com>")
    assert key(in_reply_to="<parent@example.com>", candidates=[parent]) == "existing-root"
    assert key(references="<parent@example.com>", candidates=[parent]) == "existing-root"
    assert key("<parent@example.com>", candidates=[parent]) == "existing-root"


def test_conflicting_known_message_ids_are_rejected():
    first = ThreadCandidate("a", "Draft", PEOPLE, STAMP, "<parent@example.com>")
    second = ThreadCandidate("b", "Draft", PEOPLE, STAMP, "<parent@example.com>")
    with pytest.raises(ValueError):
        key(candidates=[first, second])


def test_known_parent_wins_when_no_reference_is_known():
    parent = ThreadCandidate("existing-root", "Draft", PEOPLE, STAMP, "<parent@example.com>")
    actual = key(references="<trimmed@example.com>", in_reply_to="<parent@example.com>", candidates=[parent])
    assert actual == "existing-root"
