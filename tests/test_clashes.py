from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.clashes import Event, clashes


def stamp(hour, minute=0):
    return datetime(2027, 1, 5, hour, minute, tzinfo=UTC)


def event(identifier, start=9, end=10, show_as="busy", location=None, calendar="work"):
    return Event(identifier, calendar, stamp(start), stamp(end), show_as, location)


def test_overlap():
    result = clashes((event("a", 9, 11), event("b", 10, 12, calendar="personal")))
    assert result.status == "known"
    assert len(result.blocking) == 1
    assert result.blocking[0].overlap_minutes == 60
    assert result.blocking[0].travel_shortfall_minutes is None


@pytest.mark.parametrize(
    "first,second", [("busy", "busy"), ("busy", "out of office"), ("out of office", "out of office")]
)
def test_blocking_states(first, second):
    assert len(clashes((event("a", show_as=first), event("b", show_as=second))).blocking) == 1


@pytest.mark.parametrize(
    "first,second",
    [("tentative", "busy"), ("busy", "tentative"), ("tentative", "tentative"), ("out of office", "tentative")],
)
def test_tentative_separate(first, second):
    result = clashes((event("a", show_as=first), event("b", show_as=second)))
    assert len(result.tentative) == 1
    assert not result.blocking


@pytest.mark.parametrize("other", ["busy", "out of office", "tentative", "free"])
def test_free_does_not_block(other):
    result = clashes((event("a", show_as="free"), event("b", show_as=other)), 20)
    assert not result.blocking and not result.tentative and not result.unknown_pairs


def test_back_to_back_no_travel():
    assert not clashes((event("a", 9, 10), event("b", 10, 11))).blocking


def test_travel_only():
    a = event("a", 9, 10, location="Willow Hall")
    b = Event("b", "personal", stamp(10, 10), stamp(11), "busy", "Alder Studio")
    result = clashes((a, b), 20)
    assert result.blocking[0].overlap_minutes == 0
    assert result.blocking[0].travel_shortfall_minutes == 10


def test_exact_travel_gap_not_clash():
    a = event("a", 9, 10, location="Willow Hall")
    b = Event("b", "personal", stamp(10, 20), stamp(11), "busy", "Alder Studio")
    assert not clashes((a, b), 20).blocking


def test_same_normalized_location():
    result = clashes((event("a", 9, 10, location=" Willow  Hall "), event("b", 10, 11, location="willow hall")), 20)
    assert not result.blocking
    assert result.status == "known"


@pytest.mark.parametrize("location", [None, "", "   "])
def test_missing_location_unknown_for_short_gap(location):
    result = clashes((event("a", 9, 10, location=location), event("b", 10, 11, location="Willow Hall")), 20)
    assert result.status == "known"
    assert len(result.unknown_pairs) == 1
    assert not result.blocking


def test_missing_location_not_needed_for_sufficient_gap():
    assert clashes((event("a", 9, 10), event("b", 11, 12)), 20).status == "known"


def test_overlap_known_without_locations():
    result = clashes((event("a"), event("b")), 20)
    assert result.status == "known" and result.blocking


def test_tentative_travel():
    result = clashes((event("a", location="Willow Hall"), event("b", 10, 11, "tentative", "Alder Studio")), 20)
    assert len(result.tentative) == 1 and not result.blocking


def test_all_pairs_including_nested():
    items = (event("a", 9, 14), event("b", 10, 12), event("c", 11, 13))
    result = clashes(items)
    assert [item.overlap_minutes for item in result.blocking] == [120, 120, 60]


def test_same_id_different_calendars():
    assert len(clashes((event("a"), event("a", calendar="personal"))).blocking) == 1


def test_duplicate_identity_reported():
    result = clashes((event("a"), event("a")))
    assert result.status == "unknown" and result.issues[0].index == 1


def test_input_order_not_time_order():
    result = clashes((event("later", 10, 12), event("earlier", 9, 11)))
    assert result.blocking[0].first.id == "earlier"


def test_fractional_overlap():
    first = event("a")
    second = Event("b", "personal", stamp(10) - timedelta(seconds=30), stamp(11), "busy")
    assert clashes((first, second)).blocking[0].overlap_minutes == 0.5


def test_elapsed_time_across_spring_change():
    zone = ZoneInfo("America/New_York")
    first = Event(
        "a", "work", datetime(2027, 3, 14, 1, 30, tzinfo=zone), datetime(2027, 3, 14, 3, 30, tzinfo=zone), "busy"
    )
    second = Event("b", "personal", first.start, first.end, "busy")
    assert clashes((first, second)).blocking[0].overlap_minutes == 60


def test_different_folds_are_distinct_instants():
    zone = ZoneInfo("America/New_York")
    first = Event(
        "a",
        "work",
        datetime(2027, 11, 7, 1, tzinfo=zone, fold=0),
        datetime(2027, 11, 7, 1, 30, tzinfo=zone, fold=0),
        "busy",
    )
    second = Event("b", "personal", first.start.replace(fold=1), first.end.replace(fold=1), "busy")
    assert not clashes((first, second)).blocking


@pytest.mark.parametrize("travel", [-1, True, float("inf"), float("nan"), "20"])
def test_invalid_travel(travel):
    result = clashes((event("a"),), travel)
    assert result.status == "unknown" and result.reason


@pytest.mark.parametrize("show_as", ["unknown", "", None])
def test_unknown_show_as(show_as):
    assert clashes((event("a", show_as=show_as),)).issues[0].status == "unknown"


def test_naive_time():
    start = datetime(2027, 1, 5, 9)  # noqa: DTZ001 -- A floating event time must be rejected.
    result = clashes((Event("a", "work", start, stamp(10), "busy"),))
    assert result.issues


@pytest.mark.parametrize("end", [8, 9])
def test_nonpositive_duration(end):
    assert clashes((event("a", 9, end),)).issues


def test_missing_time_unknown():
    assert clashes((Event("a", "work", None, stamp(10), "busy"),)).issues


def test_empty():
    result = clashes(())
    assert result.status == "known" and not result.blocking


def test_unchanged_and_frozen():
    items = [event("a"), event("b")]
    before = items.copy()
    result = clashes(items)
    assert items == before and clashes(items) == result
    with pytest.raises(FrozenInstanceError):
        result.blocking[0].overlap_minutes = 0


def test_an_online_meeting_needs_no_travel():
    online = event("a", 9, 10, location="https" + "://meet.example.com/standup")
    assert not clashes((online, event("b", 10, 11, location="Willow Hall")), 20).blocking
    assert not clashes((online, event("b", 10, 11)), 20).unknown_pairs


@pytest.mark.parametrize("spelling", ["OUT_OF_OFFICE", "Out-of-office", " Busy "])
def test_show_as_spellings(spelling):
    assert len(clashes((event("a", show_as=spelling), event("b"))).blocking) == 1


def test_a_month_of_events_matches_the_pairwise_answer():
    # Stopping early must find exactly the clashes that comparing every pair finds.
    items = []
    for day in range(30):
        base = datetime(2027, 1, 1, 8, tzinfo=UTC) + timedelta(days=day)
        for slot in range(8):
            start = base + timedelta(minutes=50 * slot + (day * 7 + slot * 13) % 25)
            place = ["Willow Hall", "Alder Studio", None][(day + slot) % 3]
            items.append(Event(f"e{day}-{slot}", "work", start, start + timedelta(minutes=45), "busy", place))
    result = clashes(items, 15)
    expected = 0
    for i, first in enumerate(sorted(items, key=lambda item: item.start)):
        for second in sorted(items, key=lambda item: item.start)[i + 1 :]:
            gap = (second.start - first.end).total_seconds() / 60
            overlap = (min(first.end, second.end) - max(first.start, second.start)).total_seconds() / 60
            places = first.location and second.location and first.location != second.location
            expected += overlap > 0 or (gap < 15 and bool(places))
    assert len(result.blocking) == expected
