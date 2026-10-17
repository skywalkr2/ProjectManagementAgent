"""Fictional confirmation markup; no external resources or live mail."""

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path

import pytest

from engine.bookings import read_bookings


def reservation(kind):
    common = {"reservationId": "R-0042", "provider": {"@type": "Organization", "name": "Larkway Travel"}}
    airport_a = {"@type": "Airport", "name": "Alderfield Airport"}
    airport_b = {"@type": "Airport", "name": "Briarford Airport"}
    start, end = "2026-11-20T09:00:00-05:00", "2026-11-20T11:00:00-05:00"
    if kind == "flight":
        common.update(
            {
                "@type": "FlightReservation",
                "reservationFor": {
                    "@type": "Flight",
                    "departureTime": start,
                    "arrivalTime": end,
                    "departureAirport": airport_a,
                    "arrivalAirport": airport_b,
                },
            }
        )
    elif kind == "train":
        common.update(
            {
                "@type": "TrainReservation",
                "reservationFor": {
                    "@type": "TrainTrip",
                    "departureTime": start,
                    "arrivalTime": end,
                    "departureStation": {"name": "Mossgate Station"},
                    "arrivalStation": {"name": "Fern End Station"},
                },
            }
        )
    elif kind == "lodging":
        common.update(
            {
                "@type": "LodgingReservation",
                "checkinTime": start,
                "checkoutTime": end,
                "reservationFor": {
                    "@type": "LodgingBusiness",
                    "name": "Willow Rest",
                    "address": {
                        "@type": "PostalAddress",
                        "streetAddress": "12 Fern Lane",
                        "addressLocality": "Alderford",
                    },
                },
            }
        )
    elif kind == "event":
        common.update(
            {
                "@type": "EventReservation",
                "reservationFor": {
                    "@type": "Event",
                    "name": "Ink Evening",
                    "startDate": start,
                    "endDate": end,
                    "location": {"@type": "Place", "name": "Alder Hall"},
                },
            }
        )
    elif kind == "restaurant":
        common.update(
            {
                "@type": "FoodEstablishmentReservation",
                "startTime": start,
                "endTime": end,
                "reservationFor": {"@type": "Restaurant", "name": "The Paper Finch"},
            }
        )
    else:
        common.update(
            {
                "@type": "RentalCarReservation",
                "pickupTime": start,
                "dropoffTime": end,
                "pickupLocation": {"name": "Larkway Depot"},
                "dropoffLocation": {"name": "Briar Depot"},
                "reservationFor": {"@type": "Car", "name": "Compact car"},
            }
        )
    return common


def json_mail(value):
    return (
        '<html><body><p>Rowan, your reservation is confirmed.</p><script type="application/ld+json">'
        + json.dumps(value, ensure_ascii=False)
        + "</script><p>Questions: reservations@example.com</p></body></html>"
    )


def micro_mail(value):
    def node(value, prop=None):
        if isinstance(value, dict):
            attrs = ' itemscope itemtype="schema:' + escape(value.get("@type", "Thing")) + '"'
            if prop:
                attrs += ' itemprop="' + prop + '"'
            return (
                "<div"
                + attrs
                + ">"
                + "".join(node(child, key) for key, child in value.items() if key != "@type")
                + "</div>"
            )
        return '<meta itemprop="' + prop + '" content="' + escape(str(value), quote=True) + '">'

    return "<html><body><p>Rowan, here are your booking details.</p>" + node(value) + "</body></html>"


@pytest.mark.parametrize("kind", ["flight", "lodging", "event", "restaurant", "rental_car", "train"])
@pytest.mark.parametrize("markup", [json_mail, micro_mail])
def test_six_reservation_types(kind, markup):
    result = read_bookings(markup(reservation(kind)))
    assert not result.issues
    assert len(result.bookings) == 1
    item = result.bookings[0]
    assert item.kind == kind
    assert item.start == datetime(2026, 11, 20, 14, tzinfo=UTC)
    assert item.end == datetime(2026, 11, 20, 16, tzinfo=UTC)
    assert item.time_zone == item.end_time_zone == "-05:00"
    assert item.confirmation_code == "R-0042"
    assert item.provider == "Larkway Travel"
    assert item.place.name
    if kind in {"flight", "train", "rental_car"}:
        assert item.destination.name
    if kind == "lodging":
        assert item.place.address == "12 Fern Lane, Alderford"
    with pytest.raises(FrozenInstanceError):
        item.provider = "Other"


def test_json_graph_and_local_references():
    data = reservation("event")
    event = data.pop("reservationFor")
    event["@id"] = "#event"
    data["reservationFor"] = {"@id": "#event"}
    result = read_bookings(json_mail({"@graph": [data, event]}))
    assert len(result.bookings) == 1
    assert result.bookings[0].place.name == "Alder Hall"
    assert not result.issues


def test_multiple_json_blocks_and_array():
    first = json_mail([reservation("train"), reservation("lodging")])
    result = read_bookings(first + json_mail(reservation("event")))
    assert [item.kind for item in result.bookings] == ["train", "lodging", "event"]


@pytest.mark.parametrize(
    "body",
    [
        "{broken",
        "null",
        '"a string"',
        "42",
        '{"@type":"EventReservation","x":NaN}',
        '{"@type":"EventReservation","reservationId":"a","reservationId":"b"}',
    ],
)
def test_invalid_json_reports(body):
    result = read_bookings('<script type="application/ld+json">' + body + "</script>")
    assert not result.bookings
    assert result.issues


def test_missing_fields_returns_partial_record_and_issues():
    result = read_bookings(json_mail({"@type": "FlightReservation"}))
    assert len(result.bookings) == 1
    assert result.bookings[0].start is None
    assert result.bookings[0].provider is None
    assert {issue.field for issue in result.issues} >= {"start", "end", "place", "provider", "confirmation_code"}


@pytest.mark.parametrize("value", ["Friday at noon", "2026-02-30T09:00:00Z", "09:00:00", "20261120", 123])
def test_malformed_times_are_not_inferred(value):
    data = reservation("restaurant")
    data["startTime"] = value
    result = read_bookings(json_mail(data))
    assert result.bookings[0].start is None
    assert any(issue.field == "startTime" for issue in result.issues)


def test_missing_offset_is_retained_and_reported():
    data = reservation("event")
    data["reservationFor"]["startDate"] = "2026-11-20T09:00:00"
    result = read_bookings(json_mail(data))
    item = result.bookings[0]
    assert item.start.tzinfo is None
    assert item.time_zone is None
    assert any("No offset" in issue.note for issue in result.issues)


def test_explicit_named_zone_is_data_not_a_lookup():
    data = reservation("event")
    event = data["reservationFor"]
    event["startDate"] = "2026-11-20T09:00:00"
    event["eventSchedule"] = {"@type": "Schedule", "scheduleTimezone": "America/New_York"}
    item = read_bookings(json_mail(data)).bookings[0]
    assert item.time_zone == "America/New_York"
    assert item.start.tzinfo is None


def test_different_arrival_offset_preserved():
    data = reservation("flight")
    data["reservationFor"]["arrivalTime"] = "2026-11-20T16:00:00+01:00"
    item = read_bookings(json_mail(data)).bookings[0]
    assert item.end_time_zone == "+01:00"
    assert item.end - item.start == timedelta(hours=1)


def test_date_only_values_stay_dates():
    data = reservation("lodging")
    data.update(checkinTime="2026-11-20", checkoutTime="2026-11-23")
    item = read_bookings(json_mail(data)).bookings[0]
    assert item.start == date(2026, 11, 20)
    assert type(item.start) is date
    assert item.time_zone is None


def test_plain_prose_is_not_extracted():
    result = read_bookings("<p>Rowan, your flight leaves Friday; code MAYBE.</p>")
    assert not result.bookings
    assert not result.issues


def test_script_type_and_html_entities():
    data = reservation("lodging")
    data["reservationFor"]["name"] = "Fern & Finch"
    assert read_bookings(micro_mail(data)).bookings[0].place.name == "Fern & Finch"
    text = json_mail(data).replace("application/ld+json", "APPLICATION/LD+JSON; charset=utf-8")
    assert read_bookings(text).bookings[0].place.name == "Fern & Finch"
    assert not read_bookings(json_mail(data).replace("application/ld+json", "text/plain")).bookings


def test_repeated_microdata_is_ambiguous():
    text = micro_mail(reservation("restaurant")).replace(
        'itemprop="reservationId" content="R-0042">',
        'itemprop="reservationId" content="R-0042"><meta itemprop="reservationId" content="R-0099">',
    )
    result = read_bookings(text)
    assert result.bookings[0].confirmation_code is None
    assert any("Multiple values" in issue.note for issue in result.issues)


def test_external_microdata_reference_reported():
    text = micro_mail(reservation("event")).replace(
        'itemscope itemtype="schema:EventReservation"',
        'itemscope itemref="elsewhere" itemtype="schema:EventReservation"',
    )
    assert any(issue.field == "itemref" for issue in read_bookings(text).issues)


def test_unclosed_structured_element_reported():
    result = read_bookings(
        '<div itemscope itemtype="schema:FlightReservation"><meta itemprop="reservationId" content="R-1">'
    )
    assert result.bookings[0].confirmation_code == "R-1"
    assert any("Unclosed" in issue.note for issue in result.issues)


def test_unresolved_and_cyclic_ids_are_reported():
    data = reservation("event")
    data["reservationFor"] = {"@id": "#missing"}
    assert any(issue.field == "@id" for issue in read_bookings(json_mail(data)).issues)
    data["@id"] = "#reservation"
    data["reservationFor"] = {"@id": "#reservation"}
    assert any(issue.field == "@id" for issue in read_bookings(json_mail(data)).issues)


def test_end_before_start_reported_without_rewriting():
    data = reservation("restaurant")
    data["endTime"] = "2026-11-20T08:00:00-05:00"
    result = read_bookings(json_mail(data))
    assert result.bookings[0].end.hour == 8
    assert any("precedes" in issue.note for issue in result.issues)


def test_conflicting_types_and_non_schema_types():
    data = reservation("event")
    data["@type"] = ["EventReservation", "FlightReservation"]
    assert not read_bookings(json_mail(data)).bookings
    data["@type"] = "schema:EventReservation"
    assert len(read_bookings(json_mail(data)).bookings) == 1
    assert read_bookings(json_mail({"@type": "BoatReservation"})).issues


def test_malformed_type_and_id_do_not_crash():
    data = reservation("event")
    data["@type"] = [123]
    assert read_bookings(json_mail(data)).issues
    data["@type"] = "EventReservation"
    data["reservationFor"] = {"@id": ["invalid"]}
    assert read_bookings(json_mail(data)).issues


def test_repeated_call_and_inputs_unchanged():
    text = json_mail(reservation("event"))
    assert read_bookings(text) == read_bookings(text)


@pytest.mark.parametrize("context", [{"name": "custom:name"}, ["unknown"], 17, "unknown-context"])
def test_unsupported_context_is_reported(context):
    data = reservation("event")
    data["@context"] = context
    result = read_bookings(json_mail(data))
    assert not result.bookings
    assert any(issue.field == "@context" for issue in result.issues)


def test_compact_schema_vocabulary_context():
    data = reservation("event")
    data["@context"] = {"@vocab": "schema:"}
    assert len(read_bookings(json_mail(data)).bookings) == 1


def test_empty_and_irrelevant_html():
    assert not read_bookings("").bookings
    assert not read_bookings(
        '<div itemscope itemtype="schema:Person"><span itemprop="name">Rowan</span></div>'
    ).bookings


def test_missing_end_not_filled_from_start():
    data = reservation("event")
    del data["reservationFor"]["endDate"]
    result = read_bookings(json_mail(data))
    assert result.bookings[0].end is None
    assert any(issue.field == "end" for issue in result.issues)


def test_conflicting_identifier_definitions():
    data = reservation("event")
    data["reservationFor"] = {"@id": "#event"}
    result = read_bookings(
        json_mail({"@graph": [data, {"@id": "#event", "name": "First"}, {"@id": "#event", "name": "Second"}]})
    )
    assert any("Conflicting" in issue.note for issue in result.issues)
    assert result.bookings[0].place is None


def test_microdata_time_element():
    text = micro_mail(reservation("restaurant")).replace(
        '<meta itemprop="startTime" content="2026-11-20T09:00:00-05:00">',
        '<time itemprop="startTime" datetime="2026-11-20T09:00:00-05:00">Friday</time>',
    )
    assert read_bookings(text).bookings[0].start.hour == 9


def test_offset_free_and_aware_dates_report_comparison_limit():
    data = reservation("restaurant")
    data["startTime"] = "2026-11-20T09:00:00"
    assert any("incompatible" in issue.note for issue in read_bookings(json_mail(data)).issues)


@pytest.mark.parametrize(
    "html",
    [
        "<div>" * 3000 + "x",
        '<div itemscope itemprop="a" itemtype="schema:Thing">' * 1500,
        '<script type="application/ld+json">' + "[" * 5000 + "]" * 5000 + "</script>",
    ],
    ids=["deep-tags", "deep-microdata", "deep-json"],
)
def test_deep_nesting_is_reported_not_raised(html):
    result = read_bookings(html)
    assert not result.bookings
    assert result.issues


SAMPLES = sorted((Path(__file__).parent / "fixtures" / "bookings").glob("*.html"))


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda path: path.stem)
def test_fictional_samples_read_cleanly(sample):
    result = read_bookings(sample.read_text(encoding="utf-8"))
    assert not result.issues
    assert [booking.kind for booking in result.bookings] == [sample.stem.rsplit("_", 1)[0]]
