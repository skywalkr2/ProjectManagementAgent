"""Examples of individual calendar recurrence sets."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.recurrence import Override, occurrences

ZONE = ZoneInfo("America/New_York")


def dt(day, hour=9, month=1, year=2026):
    return datetime(year, month, day, hour, tzinfo=ZONE)


def expand(rule, start=None, end=None, **kwargs):
    start = start or dt(1)
    return occurrences(
        start,
        end if end is not None else start + timedelta(hours=1),
        rule,
        kwargs.pop("exdates", ()),
        kwargs.pop("rdates", ()),
        kwargs.pop("overrides", {}),
        kwargs.pop("window_start", dt(1, year=2025)),
        kwargs.pop("window_end", dt(1, year=2032)),
        ZONE,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("FREQ=DAILY;INTERVAL=2;COUNT=3", [dt(1), dt(3), dt(5)]),
        ("FREQ=WEEKLY;INTERVAL=2;COUNT=3", [dt(1), dt(15), dt(29)]),
        ("FREQ=MONTHLY;INTERVAL=2;COUNT=3", [dt(1), dt(1, month=3), dt(1, month=5)]),
        ("FREQ=YEARLY;INTERVAL=2;COUNT=3", [dt(1), dt(1, year=2028), dt(1, year=2030)]),
        ("FREQ=DAILY;UNTIL=20260103T140000Z", [dt(1), dt(2), dt(3)]),
        ("FREQ=WEEKLY;BYDAY=MO,TH;COUNT=4", [dt(1), dt(5), dt(8), dt(12)]),
        ("FREQ=MONTHLY;BYDAY=2MO;COUNT=2", [dt(1), dt(12)]),
        ("FREQ=MONTHLY;BYDAY=-1FR;COUNT=2", [dt(1), dt(30)]),
        ("FREQ=MONTHLY;BYMONTHDAY=31;COUNT=3", [dt(1), dt(31), dt(31, month=3)]),
        ("FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=2", [dt(1), dt(31)]),
        ("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=10;COUNT=2", [dt(1), dt(10, month=2)]),
        (
            "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=2",
            [dt(1), dt(30)],
        ),
    ],
)
def test_rules(rule, expected):
    assert [item.start for item in expand(rule)] == expected


def test_exdates_rdates_union_and_exclusion_precedence():
    found = expand(
        "FREQ=DAILY;COUNT=3",
        exdates=[dt(2), dt(5)],
        rdates=[dt(3), dt(4), dt(5), dt(4)],
    )
    assert [item.start for item in found] == [dt(1), dt(3), dt(4)]


def test_moved_and_cancelled_overrides():
    found = expand(
        "FREQ=DAILY;COUNT=3",
        overrides={dt(2): Override(dt(2, 14), dt(2, 16)), dt(3): Override(cancelled=True)},
    )
    assert found[1].start == dt(2, 14)
    assert found[1].end == dt(2, 16)
    assert found[1].override_id == dt(2)
    assert found[2].cancelled
    assert found[2].override_id == dt(3)


def test_move_into_and_out_of_window_and_shared_destination():
    found = expand(
        "FREQ=DAILY;COUNT=5",
        overrides={dt(1): Override(dt(3)), dt(3): Override(dt(8))},
        window_start=dt(3, 0),
        window_end=dt(4, 0),
    )
    assert len(found) == 1
    assert found[0].override_id == dt(1)
    found = expand("FREQ=DAILY;COUNT=2", overrides={dt(1): Override(dt(2))})
    assert len(found) == 2
    assert found[0].start == found[1].start


def test_all_day_exclusive_end_until_and_override():
    found = occurrences(
        date(2026, 1, 1),
        date(2026, 1, 3),
        "FREQ=DAILY;UNTIL=20260103",
        [date(2026, 1, 2)],
        [date(2026, 1, 4)],
        {date(2026, 1, 3): Override(date(2026, 1, 5))},
        date(2026, 1, 2),
        date(2026, 1, 6),
        ZONE,
    )
    assert [item.start.day for item in found] == [1, 4, 5]
    assert all(item.all_day and type(item.start) is date for item in found)
    assert all(item.end - item.start == timedelta(days=2) for item in found)


def test_floating_times_and_floating_until():
    found = expand(
        "FREQ=DAILY;UNTIL=20260103T090000",
        start=datetime(2026, 1, 1, 9),  # noqa: DTZ001 - Floating DTSTART is the input under test.
        end=datetime(2026, 1, 1, 10),  # noqa: DTZ001 - Floating DTEND is the input under test.
    )
    assert [item.start for item in found] == [dt(1), dt(2), dt(3)]


@pytest.mark.parametrize(("month", "day", "offsets"), [(3, 7, [-5, -4, -4]), (10, 31, [-4, -5, -5])])
def test_nine_stays_nine_across_dst(month, day, offsets):
    found = expand("FREQ=DAILY;COUNT=3", start=dt(day, month=month))
    assert [item.start.hour for item in found] == [9, 9, 9]
    assert [item.start.utcoffset().total_seconds() / 3600 for item in found] == offsets
    assert all(item.end.astimezone(UTC) - item.start.astimezone(UTC) == timedelta(hours=1) for item in found)


def test_nonexistent_time_uses_pre_gap_offset_and_counts():
    start = datetime(2026, 3, 7, 2, 30, tzinfo=ZONE)
    found = expand("FREQ=DAILY;COUNT=3", start=start)
    assert [item.start.day for item in found] == [7, 8, 9]
    assert [item.start.hour for item in found] == [2, 3, 2]
    assert [item.start.minute for item in found] == [30, 30, 30]
    assert found[1].start.astimezone(UTC) == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    assert found[1].end == datetime(2026, 3, 8, 4, 30, tzinfo=ZONE)


def test_ambiguous_time_uses_first_fold():
    start = datetime(2026, 10, 31, 1, 30, tzinfo=ZONE)
    found = expand("FREQ=DAILY;COUNT=3", start=start)
    assert found[1].start.fold == 0
    assert found[1].start.utcoffset() == timedelta(hours=-4)


def test_exact_duration_across_dst():
    found = expand("FREQ=DAILY;COUNT=2", start=dt(7, 1, month=3), end=dt(7, 4, month=3))
    assert found[1].end.hour == 5
    assert found[1].end.astimezone(UTC) - found[1].start.astimezone(UTC) == timedelta(hours=3)


def test_half_open_overlap_and_zero_duration():
    found = expand("FREQ=DAILY;COUNT=2", window_start=dt(1, 10), window_end=dt(2))
    assert found == []
    found = expand(None, window_start=dt(1, 9), window_end=dt(1, 10))
    assert len(found) == 1
    found = occurrences(dt(1), None, None, [], [], {}, dt(1), dt(1, 10), ZONE)
    assert found[0].start == found[0].end


def test_missing_all_day_end_and_equivalent_utc_exception():
    found = occurrences(date(2026, 1, 1), None, None, [], [], {}, date(2026, 1, 1), date(2026, 1, 2), ZONE)
    assert found[0].end == date(2026, 1, 2)
    assert expand(None, exdates=[dt(1).astimezone(UTC)]) == []


def test_exdate_suppresses_override_and_inputs_are_unchanged():
    changes = {dt(1): Override(dt(2))}
    exclusions = [dt(1)]
    assert expand(None, exdates=exclusions, overrides=changes) == []
    assert changes == {dt(1): Override(dt(2))}
    assert exclusions == [dt(1)]


@pytest.mark.parametrize(
    "rule",
    [
        "FREQ=DAILY;COUNT=2;UNTIL=20260103T140000Z",
        "FREQ=HOURLY",
        "FREQ=DAILY;INTERVAL=0",
        "FREQ=DAILY;COUNT=0",
        "FREQ=WEEKLY;BYDAY=2MO",
        "FREQ=WEEKLY;BYMONTHDAY=1",
        "FREQ=DAILY;FREQ=WEEKLY",
        "FREQ=DAILY;UNTIL=20260230T090000",
        "FREQ=DAILY;UNTIL=20260103T250000Z",
        "FREQ=DAILY;UNTIL=2026-01-03",
    ],
)
def test_invalid_rules(rule):
    with pytest.raises(ValueError):
        expand(rule)


def test_mixed_value_types_and_invalid_bounds():
    with pytest.raises(ValueError):
        expand(None, exdates=[date(2026, 1, 1)])
    with pytest.raises(ValueError):
        expand(None, end=dt(1, 8))
    with pytest.raises(ValueError):
        expand(None, window_start=dt(2), window_end=dt(1))


@pytest.mark.parametrize("until", ["20260103T090000", "20260103T140000Z"])
def test_aware_event_accepts_floating_and_utc_until(until):
    assert [item.start for item in expand(f"FREQ=DAILY;UNTIL={until}")] == [dt(1), dt(2), dt(3)]


@pytest.mark.parametrize("until", ["20260103", "20260103T000000", "20260103T235959Z"])
def test_all_day_until_uses_written_date(until):
    found = occurrences(
        date(2026, 1, 1),
        None,
        f"FREQ=DAILY;UNTIL={until}",
        [],
        [],
        {},
        date(2026, 1, 1),
        date(2026, 1, 5),
        ZONE,
    )
    assert [item.start for item in found] == [date(2026, 1, day) for day in (1, 2, 3)]


def test_floating_until_uses_event_zone_instead_of_window_zone():
    found = occurrences(
        dt(1),
        dt(1, 10),
        "FREQ=DAILY;UNTIL=20260103T090000",
        [],
        [],
        {},
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 5, tzinfo=UTC),
        UTC,
    )
    assert [item.start for item in found] == [dt(1), dt(2), dt(3)]


def test_count_one_with_nonmatching_start():
    assert [item.start for item in expand("FREQ=MONTHLY;BYDAY=2MO;COUNT=1")] == [dt(1)]


def test_excluding_start_does_not_restore_count():
    found = expand("FREQ=MONTHLY;BYDAY=2MO;COUNT=2", exdates=[dt(1)])
    assert [item.start for item in found] == [dt(12)]


def test_nonmatching_count_does_not_include_rdates():
    found = expand("FREQ=MONTHLY;BYDAY=2MO;COUNT=2", rdates=[dt(20)])
    assert [item.start for item in found] == [dt(1), dt(12), dt(20)]


def test_start_in_gap_keeps_requested_time_for_later_days():
    start = datetime(2026, 3, 8, 2, 30, tzinfo=ZONE)
    found = occurrences(start, None, "FREQ=DAILY;COUNT=2", [], [], {}, dt(8, 0, month=3), dt(10, 0, month=3), ZONE)
    assert [item.start.hour for item in found] == [3, 2]
    assert [item.start.minute for item in found] == [30, 30]
