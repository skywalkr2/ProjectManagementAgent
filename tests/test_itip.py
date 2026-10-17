"""Fictional calendar invitations using common client serialization styles."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from engine.itip import newer, read_invitation, reply_ics

STAMP = datetime(2026, 10, 17, 12, tzinfo=UTC)


def fixture(style="google", method="REQUEST", sequence=0, start="20261106T140000Z", stamp="20261017T120000Z"):
    common = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{style}//Fictional test//EN",
        f"METHOD:{method}",
    ]
    if style == "outlook":
        common += [
            "BEGIN:VTIMEZONE",
            "TZID:Eastern Standard Time",
            "BEGIN:STANDARD",
            "DTSTART:20261101T020000",
            "TZOFFSETFROM:-0400",
            "TZOFFSETTO:-0500",
            "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
            "END:STANDARD",
            "BEGIN:DAYLIGHT",
            "DTSTART:20260308T020000",
            "TZOFFSETFROM:-0500",
            "TZOFFSETTO:-0400",
            "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
            "END:DAYLIGHT",
            "END:VTIMEZONE",
        ]
    common += ["BEGIN:VEVENT", "UID:meeting-1@example.com", f"DTSTAMP:{stamp}", f"SEQUENCE:{sequence}"]
    if style == "outlook":
        common += [
            'DTSTART;TZID="Eastern Standard Time":20261106T090000',
            'DTEND;TZID="Eastern Standard Time":20261106T100000',
            "X-MICROSOFT-CDO-BUSYSTATUS:BUSY",
        ]
    elif style == "apple":
        common += [
            "DTSTART;VALUE=DATE:20261106",
            "DTEND;VALUE=DATE:20261107",
            "X-APPLE-TRAVEL-ADVISORY-BEHAVIOR:AUTOMATIC",
        ]
    else:
        common += [f"DTSTART:{start}", "DTEND:20261106T160000Z"]
    common += [
        "SUMMARY:Review with Mira",
        'ORGANIZER;CN="Mira Vale":mailto:mira@example.com',
        'ATTENDEE;CN="Rowan Reed";ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:rowan@example.com',
        'ATTENDEE;CN="Oren Pike";PARTSTAT=ACCEPTED:mailto:oren@example.com',
    ]
    if method == "CANCEL":
        common.append("STATUS:CANCELLED")
    common += ["END:VEVENT", "END:VCALENDAR", ""]
    return "\r\n".join(common)


@pytest.mark.parametrize("style", ["google", "outlook", "apple"])
def test_read_client_styles(style):
    invitation = read_invitation(fixture(style))
    assert invitation.method == "REQUEST"
    assert invitation.uid == "meeting-1@example.com"
    assert invitation.summary == "Review with Mira"
    assert invitation.organizer == "mira@example.com"
    assert [(person.email, person.status) for person in invitation.attendees] == [
        ("rowan@example.com", "NEEDS-ACTION"),
        ("oren@example.com", "ACCEPTED"),
    ]
    assert invitation.attendees[0].name == "Rowan Reed"
    assert invitation.dtstamp == STAMP
    assert not invitation.cancelled
    if style == "apple":
        assert invitation.start == date(2026, 11, 6)
        assert invitation.end == date(2026, 11, 7)
    else:
        assert invitation.start.astimezone(UTC) == datetime(2026, 11, 6, 14, tzinfo=UTC)


def test_cancellation_and_minimal_cancellation():
    invitation = read_invitation(fixture(method="CANCEL", sequence=1))
    assert invitation.cancelled
    text = fixture(method="CANCEL", sequence=1)
    text = "\r\n".join(
        line for line in text.split("\r\n") if not line.startswith(("DTSTART", "DTEND", "SUMMARY", "ATTENDEE"))
    )
    minimal = read_invitation(text)
    assert minimal.cancelled
    assert minimal.start is minimal.end is None


def test_method_cancel_without_status_is_cancelled():
    assert read_invitation(fixture(method="CANCEL").replace("STATUS:CANCELLED\r\n", "")).cancelled


def test_higher_sequence_updated_time_beats_later_old_stamp():
    original = read_invitation(fixture(sequence=1, stamp="20261019T120000Z"))
    updated = read_invitation(fixture(sequence=2, start="20261106T150000Z"))
    assert newer(original, updated) is updated
    assert newer(updated, original) is updated
    assert updated.start.hour == 15


def test_timestamp_tiebreak_and_exact_tie():
    first = read_invitation(fixture())
    second = read_invitation(fixture(stamp="20261018T120000Z"))
    assert newer(first, second) is second
    assert newer(second, first) is second
    assert newer(first, replace(first)) is first


def test_cancellation_competes_by_version_not_method():
    first = read_invitation(fixture(sequence=2))
    stale_cancel = read_invitation(fixture(method="CANCEL", sequence=1))
    fresh_cancel = read_invitation(fixture(method="CANCEL", sequence=3))
    assert newer(first, stale_cancel) is first
    assert newer(first, fresh_cancel) is fresh_cancel


@pytest.mark.parametrize("style", ["google", "outlook", "apple"])
@pytest.mark.parametrize("status", ["ACCEPTED", "DECLINED", "TENTATIVE"])
def test_reply_round_trip(style, status):
    invitation = read_invitation(fixture(style, sequence=4))
    output = reply_ics(invitation, "ROWAN@example.com", status, dtstamp=STAMP + timedelta(hours=1))
    response = read_invitation(output)
    assert response.method == "REPLY"
    assert response.uid == invitation.uid
    assert response.sequence == invitation.sequence
    assert response.organizer == invitation.organizer
    assert len(response.attendees) == 1
    assert response.attendees[0].email == "rowan@example.com"
    assert response.attendees[0].status == status
    assert response.start == invitation.start
    assert response.dtstamp == STAMP + timedelta(hours=1)
    assert "RSVP=TRUE" not in output
    assert "VTIMEZONE" not in output
    assert all(len(line) <= 75 for line in output.encode().split(b"\r\n"))


def test_comment_escaping_and_unicode_folding():
    invitation = read_invitation(fixture())
    comment = "Thanks, Mira; yes.\n" + "Café 🧵 " * 30
    output = reply_ics(invitation, "mailto:rowan@example.com", "ACCEPTED", comment, dtstamp=STAMP)
    event = Calendar.from_ical(output).walk("VEVENT")[0]
    assert str(event["COMMENT"]) == comment
    for line in output.encode().split(b"\r\n"):
        line.decode("utf-8")
        assert len(line) <= 75


def test_recurrence_id_is_preserved_in_reply():
    text = fixture().replace("SUMMARY:", "RECURRENCE-ID:20261106T140000Z\r\nSUMMARY:")
    invitation = read_invitation(text)
    response = read_invitation(reply_ics(invitation, "rowan@example.com", "TENTATIVE", dtstamp=STAMP))
    assert response.recurrence_id == datetime(2026, 11, 6, 14, tzinfo=UTC)


def test_missing_sequence_and_default_partstat():
    text = fixture().replace("SEQUENCE:0\r\n", "").replace(";PARTSTAT=NEEDS-ACTION", "")
    invitation = read_invitation(text)
    assert invitation.sequence == 0
    assert invitation.attendees[0].status == "NEEDS-ACTION"


def test_event_duration():
    text = fixture().replace("DTEND:20261106T160000Z", "DURATION:PT90M")
    invitation = read_invitation(text)
    assert invitation.end - invitation.start == timedelta(minutes=90)


def test_floating_event_remains_floating():
    text = (
        fixture()
        .replace("DTSTART:20261106T140000Z", "DTSTART:20261106T140000")
        .replace("DTEND:20261106T160000Z", "DTEND:20261106T160000")
    )
    invitation = read_invitation(text)
    assert invitation.start.tzinfo is None
    output = reply_ics(invitation, "rowan@example.com", "ACCEPTED", dtstamp=STAMP)
    assert "DTSTART:20261106T140000\r\n" in output


@pytest.mark.parametrize(
    "old,new",
    [
        ("METHOD:REQUEST", "METHOD:PUBLISH"),
        ("METHOD:REQUEST\r\n", ""),
        ("UID:meeting-1@example.com\r\n", ""),
        ("DTSTAMP:20261017T120000Z\r\n", ""),
        ("DTSTAMP:20261017T120000Z", "DTSTAMP:20261017T120000"),
        ("SEQUENCE:0", "SEQUENCE:-1"),
        ("SEQUENCE:0", "SEQUENCE:2147483648"),
        ("DTSTART:20261106T140000Z\r\n", ""),
        ("DTEND:20261106T160000Z", "DTEND:20261106T130000Z"),
        ("DTSTART:20261106T140000Z", "DTSTART;TZID=Unknown/Custom:20261106T140000"),
        ("UID:meeting-1@example.com", "UID:meeting-1@example.com\r\nUID:duplicate@example.com"),
    ],
)
def test_invalid_invitations(old, new):
    with pytest.raises(ValueError):
        read_invitation(fixture().replace(old, new))


def test_invalid_calendar_and_multiple_events():
    with pytest.raises(ValueError):
        read_invitation("Not a calendar")
    text = fixture().replace("END:VCALENDAR", "BEGIN:VEVENT\r\nUID:other@example.com\r\nEND:VEVENT\r\nEND:VCALENDAR")
    with pytest.raises(ValueError):
        read_invitation(text)


@pytest.mark.parametrize(
    "address,status",
    [("other@example.com", "ACCEPTED"), ("rowan@example.com", "MAYBE"), ("rowan@example.com\r\nX-BAD:yes", "ACCEPTED")],
)
def test_invalid_reply(address, status):
    with pytest.raises(ValueError):
        reply_ics(read_invitation(fixture()), address, status, dtstamp=STAMP)


def test_cannot_reply_to_cancel_or_reply():
    for method in ["CANCEL", "REPLY"]:
        with pytest.raises(ValueError):
            reply_ics(read_invitation(fixture(method=method)), "rowan@example.com", "ACCEPTED", dtstamp=STAMP)
    with pytest.raises(ValueError):
        reply_ics(read_invitation(fixture()), "rowan@example.com", "ACCEPTED", dtstamp=STAMP.replace(tzinfo=None))


def test_comparison_rejects_unrelated_versions_and_attendee_replies():
    invitation = read_invitation(fixture())
    for other in [
        replace(invitation, uid="other@example.com"),
        replace(invitation, organizer="other@example.com"),
        replace(invitation, recurrence_id=date(2026, 11, 6)),
    ]:
        with pytest.raises(ValueError):
            newer(invitation, other)
    response = read_invitation(reply_ics(invitation, "rowan@example.com", "ACCEPTED", dtstamp=STAMP))
    with pytest.raises(ValueError):
        newer(invitation, response)
    later = replace(response, dtstamp=STAMP + timedelta(hours=1))
    assert newer(response, later) is later


def test_reply_is_deterministic_and_does_not_change_invitation():
    invitation = read_invitation(fixture())
    original = replace(invitation)
    assert reply_ics(invitation, "rowan@example.com", "ACCEPTED", dtstamp=STAMP) == reply_ics(
        invitation, "rowan@example.com", "ACCEPTED", dtstamp=STAMP
    )
    assert invitation == original


def test_aware_stamp_conversion():
    response = reply_ics(
        read_invitation(fixture()),
        "rowan@example.com",
        "ACCEPTED",
        dtstamp=STAMP.astimezone(ZoneInfo("America/New_York")),
    )
    assert read_invitation(response).dtstamp == STAMP


@pytest.mark.parametrize(("duration", "hour", "day"), [("PT2H", 4, 8), ("P1D", 1, 9)])
def test_duration_across_dst(duration, hour, day):
    text = fixture("outlook").replace("20261106T090000", "20260308T013000")
    text = text.replace('DTEND;TZID="Eastern Standard Time":20261106T100000', "DURATION:" + duration)
    invitation = read_invitation(text)
    assert invitation.end.day == day
    assert invitation.end.hour == hour
    assert invitation.end.minute == 30


def test_minimal_reply_without_start():
    original = read_invitation(fixture())
    text = reply_ics(original, "rowan@example.com", "DECLINED", dtstamp=STAMP)
    text = "\r\n".join(line for line in text.split("\r\n") if not line.startswith("DTSTART"))
    invitation = read_invitation(text)
    assert invitation.start is None
    assert invitation.attendees[0].status == "DECLINED"


def test_recurrence_range_is_preserved():
    text = fixture().replace("SUMMARY:", "RECURRENCE-ID;RANGE=THISANDFUTURE:20261106T140000Z\r\nSUMMARY:")
    invitation = read_invitation(text)
    response = read_invitation(reply_ics(invitation, "rowan@example.com", "ACCEPTED", dtstamp=STAMP))
    assert response.recurrence_range == "THISANDFUTURE"


def test_windows_zone_name_without_vtimezone_resolves():
    lines = fixture("outlook").split("\r\n")
    bare = "\r\n".join(lines[: lines.index("BEGIN:VTIMEZONE")] + lines[lines.index("END:VTIMEZONE") + 1 :])
    invitation = read_invitation(bare)
    assert invitation.start == datetime(2026, 11, 6, 14, tzinfo=UTC)
    assert invitation.start.utcoffset() == timedelta(hours=-5)
    with pytest.raises(ValueError, match="Unresolved TZID"):
        read_invitation(bare.replace("Eastern Standard Time", "Unknown Custom Zone"))
