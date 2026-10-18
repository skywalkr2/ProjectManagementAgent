from datetime import UTC, date, datetime

import pytest

from engine.document_dates import find_dates


def received():
    return datetime(2027, 1, 5, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "text,locale,kind,expected",
    [
        ("Dear Rowan, your Alder Club renewal date is January 20, 2028.", "en-US", "renewal", date(2028, 1, 20)),
        ("Your reading plan renews on 2028-02-01.", "en-US", "renewal", date(2028, 2, 1)),
        ("The studio membership auto-renews on 03/04/2028.", "en-US", "renewal", date(2028, 3, 4)),
        ("Your workshop pass expires on 2028-03-31.", "en-US", "expiry", date(2028, 3, 31)),
        ("Lease ends on 30 April 2028.", "en-GB", "expiry", date(2028, 4, 30)),
        ("Permit expiry date: May 2, 2028.", "en-US", "expiry", date(2028, 5, 2)),
        ("Cancel by June 15, 2028 to avoid another term.", "en-US", "cancel_by", date(2028, 6, 15)),
        ("Cancellation deadline: 16 June 2028.", "en-GB", "cancel_by", date(2028, 6, 16)),
        ("Cancel before 2028-07-01.", "en-US", "cancel_by", date(2028, 7, 1)),
        ("Notice must be received by July 10, 2028.", "en-US", "cancel_by", date(2028, 7, 10)),
        ("Your ticket is valid until 2028-08-31.", "en-US", "valid_until", date(2028, 8, 31)),
        ("The admission letter is valid through September 2, 2028.", "en-US", "valid_until", date(2028, 9, 2)),
        ("Warranty ends on October 3, 2028.", "en-US", "warranty_end", date(2028, 10, 3)),
        ("Warranty coverage expires on 4 October 2028.", "en-GB", "warranty_end", date(2028, 10, 4)),
        ("Warranty-end date: 2028-11-05.", "en-US", "warranty_end", date(2028, 11, 5)),
        ("Payment due: December 6, 2028.", "en-US", "payment_due", date(2028, 12, 6)),
        ("Invoice is due on 07/12/2028.", "en-GB", "payment_due", date(2028, 12, 7)),
        ("Rent due 2028-01-01.", "en-US", "payment_due", date(2028, 1, 1)),
        ("Balance due on 2028-01-02.", "en-US", "payment_due", date(2028, 1, 2)),
        ("Check-in date: February 3, 2028 at Willow Lodge.", "en-US", "check_in", date(2028, 2, 3)),
        ("Check in on 4 February 2028 at Fern House.", "en-GB", "check_in", date(2028, 2, 4)),
        ("Appointment: March 5, 2028 with Oren.", "en-US", "appointment", date(2028, 3, 5)),
        ("Appointment date: 2028-03-06.", "en-US", "appointment", date(2028, 3, 6)),
        ("Your renewal is on Nov. 20, 2028.", "en-US", "renewal", date(2028, 11, 20)),
        ("Expiry: 21 Sept 2028.", "en-GB", "expiry", date(2028, 9, 21)),
        ("Warranty ends Jan 22nd, 2028.", "en-US", "warranty_end", date(2028, 1, 22)),
        ("Payment due 23rd Feb. 2028.", "en-GB", "payment_due", date(2028, 2, 23)),
        ("Appointment 2028-02-29.", "en-US", "appointment", date(2028, 2, 29)),
        ("Renewal 04/05/2028.", "en-GB", "renewal", date(2028, 5, 4)),
        ("Renewal 04/05/2028.", "en-US", "renewal", date(2028, 4, 5)),
        ("The entry ticket expires on December 31, 2028.", "en-US", "expiry", date(2028, 12, 31)),
        ("Your lease renewal date is 1 January 2029.", "en-GB", "renewal", date(2029, 1, 1)),
        ("Cancel no later than April 9, 2028.", "en-US", "cancel_by", date(2028, 4, 9)),
        ("The voucher is valid-until 2028-04-10.", "en-US", "valid_until", date(2028, 4, 10)),
        ("Amount due: 2028-05-11.", "en-US", "payment_due", date(2028, 5, 11)),
        ("Expiration date: 2028-06-12.", "en-US", "expiry", date(2028, 6, 12)),
        ("Check-in: 07.08.2028.", "en-GB", "check_in", date(2028, 8, 7)),
        ("Warranty valid until 2028-09-13.", "en-US", "warranty_end", date(2028, 9, 13)),
        ("Appointment 14 October 2028.", "en-GB", "appointment", date(2028, 10, 14)),
        ("Renewal: 2028-11-15. Regards, Tess at Fern Circle.", "en-US", "renewal", date(2028, 11, 15)),
    ],
)
def test_forty_fictional_snippets(text, locale, kind, expected):
    findings = find_dates(text, received(), UTC, locale)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == kind
    assert finding.date == expected
    assert finding.certain
    assert finding.evidence in text
    assert not finding.relative


@pytest.mark.parametrize(
    "text,anchor",
    [
        ("Renewal in 30 days.", "message_received"),
        ("Warranty ends 30 days after purchase.", "purchase"),
        ("Cancel by 10 days before arrival.", "arrival"),
        ("Payment due tomorrow.", "message_received"),
    ],
)
def test_relative_not_calculated(text, anchor):
    finding = find_dates(text, received(), UTC, "en-US")[0]
    assert finding.relative and not finding.certain and finding.date is None
    assert finding.anchor == anchor
    assert finding.evidence in text


@pytest.mark.parametrize(
    "text",
    [
        "Renewal November 20.",
        "Payment due 11/20.",
        "Expiry 11/20/28.",
        "Appointment 2027-02-29.",
        "Cancel by 2028-13-01.",
    ],
)
def test_unresolved_dates(text):
    finding = find_dates(text, received(), UTC, "en-US")[0]
    assert not finding.certain and finding.date is None and finding.reason


def test_distinct_deadlines_same_clause():
    text = "Cancel by January 10, 2028, renewal January 20, 2028."
    findings = find_dates(text, received(), UTC, "en-US")
    assert [(item.kind, item.date) for item in findings] == [
        ("cancel_by", date(2028, 1, 10)),
        ("renewal", date(2028, 1, 20)),
    ]


def test_date_before_label():
    text = "January 10, 2028 is the cancellation deadline."
    finding = find_dates(text, received(), UTC, "en-US")[0]
    assert finding.date == date(2028, 1, 10) and finding.evidence in text


def test_correction_not_silently_selected():
    findings = find_dates("Renewal changed from January 10, 2028 to January 20, 2028.", received(), UTC, "en-US")
    assert len(findings) == 2 and all(not finding.certain for finding in findings)


def test_unlabeled_date_not_classified():
    assert find_dates("Rowan wrote on January 5, 2028.", received(), UTC, "en-US") == []


def test_unknown_numeric_locale():
    finding = find_dates("Renewal 03/04/2028.", received(), UTC, "unknown")[0]
    assert finding.date is None and not finding.certain


def test_iso_independent_of_locale():
    assert find_dates("Renewal 2028-03-04.", received(), UTC, "unknown")[0].date == date(2028, 3, 4)


def test_no_cross_clause_guess():
    findings = find_dates("Appointment not booked; Rowan wrote on January 5, 2028.", received(), UTC, "en-US")
    assert findings[0].date is None


def test_missing_anchor_date_not_used_as_expiry():
    finding = find_dates("Warranty ends 30 days after purchase on January 5, 2028.", received(), UTC, "en-US")[0]
    assert finding.relative and finding.date is None and finding.anchor == "purchase"


def test_naive_received():
    value = datetime(2027, 1, 5, 12)  # noqa: DTZ001 -- Verify rejection of a floating received time.
    assert find_dates("Renewal 2028-01-01.", value, UTC, "en-US")[0].kind == "unknown"


def test_exact_evidence():
    text = "Dear Rowan, payment due: 20 Nov. 2028, please."
    finding = find_dates(text, received(), UTC, "en-GB")[0]
    assert finding.evidence == "payment due: 20 Nov. 2028"


def test_conditional_date_uncertain():
    finding = find_dates("If approved, renewal is January 20, 2028.", received(), UTC, "en-US")[0]
    assert finding.date == date(2028, 1, 20) and not finding.certain


def test_within_relative():
    finding = find_dates("Payment due within 30 days.", received(), UTC, "en-US")[0]
    assert finding.relative and finding.anchor == "message_received" and finding.date is None


def test_named_anchor_with_date_of():
    finding = find_dates("Warranty ends 30 days from the date of purchase.", received(), UTC, "en-US")[0]
    assert finding.relative and finding.anchor == "date of purchase"


def test_no_mutable_state():
    text = "Renewal January 20, 2028."
    first = find_dates(text, received(), UTC, "en-US")
    assert find_dates(text, received(), UTC, "en-US") == first


def test_empty():
    assert find_dates("", received(), UTC, "en-US") == []
