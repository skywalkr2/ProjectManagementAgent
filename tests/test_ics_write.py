"""Round-trip generated calendars and inspect UTF-8 physical lines."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from engine.ics_write import event_ics

ZONE = ZoneInfo("America/New_York")
STAMP = datetime(2026, 10, 17, 14, 25, 30, tzinfo=UTC)


def write(**changes):
    values = dict(
        uid="review-1@example.com",
        summary="Review with Mira",
        start=datetime(2026, 11, 6, 9, tzinfo=ZONE),
        end=datetime(2026, 11, 6, 10, tzinfo=ZONE),
        all_day=False,
        tz=ZONE,
        description="Review the draft.",
        location="Alder Room",
        alarms=[],
        dtstamp=STAMP,
    )
    values.update(changes)
    return event_ics(**values)


def parsed(**changes):
    calendar = Calendar.from_ical(write(**changes))
    return calendar, calendar.walk("VEVENT")[0]


def test_round_trip_timed_event():
    calendar, event = parsed()
    assert calendar["VERSION"] == "2.0"
    assert str(event["UID"]) == "review-1@example.com"
    assert str(event["SUMMARY"]) == "Review with Mira"
    assert event.decoded("DTSTART") == datetime(2026, 11, 6, 9, tzinfo=ZONE)
    assert event.decoded("DTEND") == datetime(2026, 11, 6, 10, tzinfo=ZONE)
    assert event.decoded("DTSTAMP") == STAMP
    assert event["DTSTART"].params["TZID"] == ZONE.key
    assert calendar.walk("VTIMEZONE")[0]["TZID"] == ZONE.key
    assert not event.errors


@pytest.mark.parametrize(
    "text",
    [
        "Comma, semicolon; slash\\",
        "First\nSecond",
        "First\r\nSecond",
        "First\rSecond",
        "A: B",
        "Mira’s café — résumé",
        "漢字 🧵",
        "",
        "\\n literal",
    ],
)
def test_text_escaping(text):
    _, event = parsed(summary=text, description=text, location=text)
    expected = text.replace("\r\n", "\n").replace("\r", "\n")
    assert str(event["SUMMARY"]) == expected
    assert str(event["DESCRIPTION"]) == expected
    assert str(event["LOCATION"]) == expected


@pytest.mark.parametrize("character", ["a", "é", "漢", "🧵"])
@pytest.mark.parametrize("length", [1, 65, 66, 67, 68, 74, 75, 76, 150])
def test_folding_does_not_split_multibyte_characters(character, length):
    summary = "a" * 65 + character * length
    output = write(summary=summary)
    raw = output.encode("utf-8")
    assert raw.endswith(b"\r\n")
    for line in raw.split(b"\r\n"):
        assert len(line) <= 75
        line.decode("utf-8", errors="strict")
    assert "\n" not in output.replace("\r\n", "")
    unfolded = raw.replace(b"\r\n ", b"")
    assert b"SUMMARY:" + summary.encode("utf-8") + b"\r\n" in unfolded
    assert str(Calendar.from_ical(raw).walk("VEVENT")[0]["SUMMARY"]) == summary


@pytest.mark.parametrize(
    "alarm",
    [
        timedelta(),
        -timedelta(minutes=15),
        -timedelta(days=1),
        -timedelta(days=1, hours=2),
        timedelta(hours=1, minutes=2, seconds=3),
        timedelta(days=2, hours=3, minutes=4, seconds=5),
    ],
)
def test_display_alarms(alarm):
    calendar, _ = parsed(alarms=[alarm])
    block = calendar.walk("VALARM")[0]
    assert block["ACTION"] == "DISPLAY"
    assert block.decoded("TRIGGER") == alarm
    assert block["TRIGGER"].params["RELATED"] == "START"
    assert str(block["DESCRIPTION"]) == "Review with Mira"


def test_multiple_alarms_and_empty_summary():
    calendar, _ = parsed(summary="", alarms=[-timedelta(minutes=10), -timedelta(days=1)])
    assert len(calendar.walk("VALARM")) == 2
    assert all(block["DESCRIPTION"] == "Reminder" for block in calendar.walk("VALARM"))


def test_all_day_dates_and_exclusive_end():
    calendar, event = parsed(start=date(2026, 11, 6), end=date(2026, 11, 8), all_day=True)
    assert event.decoded("DTSTART") == date(2026, 11, 6)
    assert event.decoded("DTEND") == date(2026, 11, 8)
    assert event["DTSTART"].params["VALUE"] == "DATE"
    assert "TZID" not in event["DTSTART"].params
    assert not calendar.walk("VTIMEZONE")


@pytest.mark.parametrize("all_day", [True, False])
def test_missing_end(all_day):
    _, event = parsed(
        start=date(2026, 11, 6) if all_day else datetime(2026, 11, 6, 9, tzinfo=ZONE), end=None, all_day=all_day
    )
    assert "DTEND" not in event


def test_participants_method_sequence_and_stamp_conversion():
    calendar, event = parsed(
        organizer="rowan@example.com",
        attendees=["mira@example.com", "mailto:oren@example.com"],
        method="request",
        sequence=3,
        dtstamp=STAMP.astimezone(ZONE),
    )
    assert calendar["METHOD"] == "REQUEST"
    assert event["SEQUENCE"] == 3
    assert str(event["ORGANIZER"]) == "mailto:rowan@example.com"
    assert [str(value) for value in event["ATTENDEE"]] == ["mailto:mira@example.com", "mailto:oren@example.com"]
    assert event.decoded("DTSTAMP") == STAMP
    assert "DTSTAMP:20261017T142530Z\r\n" in write()


@pytest.mark.parametrize(
    "zone_name", ["America/New_York", "Europe/London", "Australia/Lord_Howe", "Asia/Kolkata", "UTC"]
)
def test_embedded_timezone_independently_matches_zoneinfo(zone_name):
    zone = ZoneInfo(zone_name)
    calendar, _ = parsed(
        tz=zone_name, start=datetime(2026, 1, 1, 12, tzinfo=zone), end=datetime(2027, 12, 31, 12, tzinfo=zone)
    )
    definition = calendar.walk("VTIMEZONE")[0]
    embedded = definition.to_tz(lookup_tzid=False)
    for month in range(1, 13):
        instant = datetime(2026, month, 15, 12, tzinfo=UTC)
        assert instant.astimezone(embedded).utcoffset() == instant.astimezone(zone).utcoffset()
    assert definition.walk("STANDARD") or definition.walk("DAYLIGHT")


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 3, 8, 6, 59, 59, tzinfo=UTC),
        datetime(2026, 3, 8, 7, tzinfo=UTC),
        datetime(2026, 11, 1, 5, 59, 59, tzinfo=UTC),
        datetime(2026, 11, 1, 6, tzinfo=UTC),
    ],
)
def test_embedded_dst_transition_boundaries(instant):
    calendar, _ = parsed()
    embedded = calendar.walk("VTIMEZONE")[0].to_tz(lookup_tzid=False)
    assert instant.astimezone(embedded).utcoffset() == instant.astimezone(ZONE).utcoffset()


def test_utc_start_converted_to_requested_zone():
    _, event = parsed(start=datetime(2026, 11, 6, 14, tzinfo=UTC))
    assert event.decoded("DTSTART").hour == 9


def test_floating_wall_time():
    value = datetime(2026, 11, 6, 9)  # noqa: DTZ001 - Floating wall time is the input under test.
    _, event = parsed(start=value)
    assert event.decoded("DTSTART") == value.replace(tzinfo=ZONE)


@pytest.mark.parametrize(
    "changes",
    [
        {"uid": ""},
        {"sequence": -1},
        {"sequence": True},
        {"method": "REQUEST\r\nX-BAD:yes"},
        {"organizer": "rowan@example.com\r\nX-BAD:yes"},
        {"attendees": ["Not an address"]},
        {"summary": "bad\x00text"},
        {"alarms": [timedelta(microseconds=1)]},
        {"start": date(2026, 11, 6)},
        {"all_day": True},
        {"end": datetime(2026, 11, 6, 9, tzinfo=ZONE)},
        {"start": datetime(2026, 11, 6, 9, microsecond=1, tzinfo=ZONE)},
        {"start": datetime(2026, 3, 8, 2, 30, tzinfo=ZONE)},
        {"start": datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=ZONE)},
        {"dtstamp": STAMP.replace(tzinfo=None)},
    ],
)
def test_invalid_or_unrepresentable_inputs(changes):
    with pytest.raises(ValueError):
        write(**changes)


def test_pure_and_inputs_unchanged():
    alarms = [-timedelta(minutes=15)]
    attendees = ["mira@example.com"]
    assert write(alarms=alarms, attendees=attendees) == write(alarms=alarms, attendees=attendees)
    assert alarms == [-timedelta(minutes=15)]
    assert attendees == ["mira@example.com"]
