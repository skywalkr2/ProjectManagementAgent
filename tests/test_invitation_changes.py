"""Changes between two fictional invitation versions, as kinds and values for the wording sheet."""

from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine.invitation_changes import Attendee, Change, Invitation, Person, describe_change

NEW_YORK = ZoneInfo("America/New_York")


def meeting():
    return Invitation(
        "Draft review",
        datetime(2027, 1, 5, 10, tzinfo=UTC),
        datetime(2027, 1, 5, 11, tzinfo=UTC),
        "Willow Room",
        Person("mira@example.com", "Mira"),
        (),
        False,
    )


def kinds(changes):
    return [change.kind for change in changes]


def oren(status="ACCEPTED", name="Oren", email="oren@example.com"):
    return Attendee(email, name, status)


def test_unchanged():
    assert describe_change(meeting(), meeting(), UTC) == []


def test_start_and_end_change():
    old = meeting()
    new = replace(old, start=datetime(2027, 1, 6, 11, tzinfo=UTC), end=datetime(2027, 1, 6, 12, tzinfo=UTC))
    moved, ended = describe_change(old, new, UTC)
    assert moved == Change(
        "moved",
        {
            "before": {"at": datetime(2027, 1, 5, 10, tzinfo=UTC), "repeated_hour": False},
            "after": {"at": datetime(2027, 1, 6, 11, tzinfo=UTC), "repeated_hour": False},
        },
    )
    assert ended.kind == "end_changed" and ended.values["after"]["at"] == datetime(2027, 1, 6, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"location": "Alder Hall"}, Change("location_changed", {"location": "Alder Hall"})),
        ({"summary": "Final review"}, Change("title_changed", {"title": "Final review"})),
        ({"cancelled": True}, Change("cancelled")),
    ],
)
def test_single_changes(change, expected):
    assert describe_change(meeting(), replace(meeting(), **change), UTC) == [expected]


def test_restore():
    assert describe_change(replace(meeting(), cancelled=True), meeting(), UTC) == [Change("restored")]


def test_cancelled_still_reports_other_changes():
    changes = describe_change(meeting(), replace(meeting(), cancelled=True, location="Alder Hall"), UTC)
    assert kinds(changes) == ["cancelled", "location_changed"]


def test_added_and_removed_attendees():
    with_oren = replace(meeting(), attendees=(oren("NEEDS-ACTION"),))
    assert describe_change(meeting(), with_oren, UTC) == [
        Change("attendee_added", {"email": "oren@example.com", "name": "Oren"})
    ]
    assert kinds(describe_change(with_oren, meeting(), UTC)) == ["attendee_removed"]


@pytest.mark.parametrize(
    "status,code",
    [
        ("ACCEPTED", "accepted"),
        ("DECLINED", "declined"),
        ("TENTATIVE", "tentative"),
        ("NEEDS-ACTION", "no_reply"),
        ("delegated", "delegated"),
    ],
)
def test_reply_status(status, code):
    old = replace(meeting(), attendees=(oren("OTHER"),))
    new = replace(old, attendees=(oren(status),))
    assert describe_change(old, new, UTC) == [
        Change("attendee_replied", {"email": "oren@example.com", "name": "Oren", "status": code})
    ]


def test_unknown_status():
    old = replace(meeting(), attendees=(oren(),))
    assert kinds(describe_change(old, replace(old, attendees=(oren(None),)), UTC)) == ["attendee_reply_unknown"]


def test_organizer_changes():
    tess = describe_change(meeting(), replace(meeting(), organizer=Person("tess@example.com", "Tess")), UTC)
    assert tess == [Change("organizer_changed", {"email": "tess@example.com", "name": "Tess"})]
    nameless = describe_change(meeting(), replace(meeting(), organizer=Person("tess@example.com")), UTC)
    assert nameless[0].values == {"email": "tess@example.com", "name": None}


def test_domain_case_does_not_change_identity():
    old = replace(meeting(), attendees=(oren(),))
    assert describe_change(old, replace(old, attendees=(oren("accepted", email="oren@EXAMPLE.COM"),)), UTC) == []


def test_same_instant_different_zone():
    old = meeting()
    new = replace(old, start=old.start.astimezone(NEW_YORK), end=old.end.astimezone(NEW_YORK))
    assert describe_change(old, new, UTC) == []


def test_times_come_back_in_the_persons_zone():
    old = replace(meeting(), start=datetime(2027, 1, 6, 1, tzinfo=UTC), end=datetime(2027, 1, 6, 2, tzinfo=UTC))
    new = replace(old, start=datetime(2027, 1, 6, 2, tzinfo=UTC), end=datetime(2027, 1, 6, 3, tzinfo=UTC))
    before = describe_change(old, new, NEW_YORK)[0].values["before"]["at"]
    assert (before.date(), before.hour) == (date(2027, 1, 5), 20)


def test_all_day_end_carries_the_last_day():
    old = replace(meeting(), start=date(2027, 1, 5), end=date(2027, 1, 6))
    new = replace(old, start=date(2027, 1, 6), end=date(2027, 1, 8))
    moved, ended = describe_change(old, new, UTC)
    assert moved == Change("moved", {"before": {"date": date(2027, 1, 5)}, "after": {"date": date(2027, 1, 6)}})
    assert ended.values["before"]["last_day"] == date(2027, 1, 5)
    assert ended.values["after"]["last_day"] == date(2027, 1, 7)


def test_all_day_and_timed_switches():
    all_day = replace(meeting(), start=date(2027, 1, 5), end=date(2027, 1, 6))
    assert kinds(describe_change(all_day, meeting(), UTC))[0] == "now_timed"
    to_all_day = describe_change(meeting(), all_day, UTC)
    assert to_all_day[0] == Change("now_all_day", {"start": {"date": date(2027, 1, 5)}})
    assert to_all_day[1].values["after"]["last_day"] == date(2027, 1, 5)


def test_missing_end_unknown():
    assert describe_change(meeting(), replace(meeting(), end=None), UTC) == [
        Change("end_unknown", {"reason": "missing"})
    ]


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"start": datetime(2027, 3, 14, 2, 30, tzinfo=NEW_YORK)}, "time_does_not_exist"),
        ({"start": datetime(2027, 1, 5, 10)}, "no_zone"),  # noqa: DTZ001 -- a floating time is refused
        ({"end": datetime(2027, 1, 5, 10, tzinfo=UTC)}, "end_not_after_start"),
        ({"end": date(2027, 1, 6)}, "mixed_date_and_time"),
    ],
)
def test_unreadable_times(change, reason):
    assert describe_change(meeting(), replace(meeting(), **change), UTC) == [
        Change("times_unknown", {"reason": reason})
    ]


def test_repeated_hour_is_flagged():
    old = replace(
        meeting(),
        start=datetime(2027, 11, 7, 1, tzinfo=NEW_YORK, fold=0),
        end=datetime(2027, 11, 7, 2, tzinfo=NEW_YORK),
    )
    moved = describe_change(old, replace(old, start=old.start.replace(fold=1)), NEW_YORK)[0]
    assert moved.values["before"]["repeated_hour"] and moved.values["after"]["repeated_hour"]
    assert moved.values["before"]["at"].utcoffset() != moved.values["after"]["at"].utcoffset()


def test_duplicate_attendees_unknown():
    changes = describe_change(meeting(), replace(meeting(), attendees=(oren(), oren())), UTC)
    assert changes == [Change("attendees_unknown", {"reason": "duplicate_attendee"})]


def test_seconds_are_kept():
    changes = describe_change(meeting(), replace(meeting(), start=meeting().start.replace(second=15)), UTC)
    assert changes[0].values["after"]["at"].second == 15


def test_no_zone_object():
    assert describe_change(meeting(), meeting(), "UTC") == [Change("unknown", {"reason": "no_zone_given"})]


def test_no_mutation_and_repeatable():
    old = meeting()
    new = replace(old, location="Alder Hall")
    assert describe_change(old, new, UTC) == describe_change(old, new, UTC)
    assert old.location == "Willow Room"


def test_rename_attendee_is_not_add_and_remove():
    old = replace(meeting(), attendees=(oren(),))
    assert describe_change(old, replace(old, attendees=(oren(name="Oren Vale"),)), UTC) == [
        Change("attendee_renamed", {"email": "oren@example.com", "name": "Oren Vale", "before": "Oren"})
    ]


def test_removed_location_and_organizer():
    changes = describe_change(meeting(), replace(meeting(), location=None, organizer=None), UTC)
    assert changes == [Change("location_removed"), Change("organizer_removed")]


def test_missing_cancellation_flag():
    assert describe_change(meeting(), replace(meeting(), cancelled=None), UTC)[0].kind == "cancelled_unknown"


def test_no_change_carries_on_screen_text():
    # Every value is data: kinds and reason codes are identifiers, never sentences.
    old = replace(meeting(), attendees=(oren("OTHER"),))
    new = replace(old, summary="Final", location=None, cancelled=True, attendees=(oren("DECLINED"),))
    for change in describe_change(old, new, UTC):
        assert " " not in change.kind
        assert " " not in str(change.values.get("reason", "")) and " " not in str(change.values.get("status", ""))
