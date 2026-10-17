"""Check CLDR completeness and calendar identifier normalization offline."""

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from engine.windows_zones import iana_zone

MAPPING = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "engine" / "defaults" / "windows_zones.yaml").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Eastern Standard Time", "America/New_York"),
        ("Pacific Standard Time", "America/Los_Angeles"),
        ("GMT Standard Time", "Europe/London"),
        ("India Standard Time", "Asia/Calcutta"),
        ("Nepal Standard Time", "Asia/Katmandu"),
        ("UTC", "Etc/UTC"),
        ("UTC+12", "Etc/GMT-12"),
        ("UTC-11", "Etc/GMT+11"),
        (" eastern standard time ", "America/New_York"),
        ("America/New_York", "America/New_York"),
        ("US/Eastern", "US/Eastern"),
        ("Asia/Kolkata", "Asia/Kolkata"),
        ("Etc/GMT+5", "Etc/GMT+5"),
        ('"Eastern Standard Time"', "America/New_York"),
        ("'Pacific Standard Time'", "America/Los_Angeles"),
        ('TZID="Eastern Standard Time"', "America/New_York"),
        ('TZID:"Europe/London"', "Europe/London"),
        ('"TZID=Eastern Standard Time"', "America/New_York"),
        ('TZID="/Microsoft/Eastern Standard Time"', "America/New_York"),
        ("tzone://Microsoft/Pacific Standard Time", "America/Los_Angeles"),
        ("tzone://Microsoft/Utc", "Etc/UTC"),
        ("/America/New_York", "America/New_York"),
        ("/IANA/America/New_York", "America/New_York"),
        ("/freeassociation.sourceforge.net/Tzfile/Europe/London", "Europe/London"),
    ],
)
def test_known_names(name, expected):
    assert iana_zone(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        "Not a time zone",
        "america/new_york",
        '"Eastern Standard Time',
        "Eastern Standard Time'",
        "tzone://Microsoft/Custom",
        "/Microsoft/Custom",
        "TZID=",
        "../Europe/London",
        "/etc/passwd",
        "America/../Europe/London",
        "Unknown/America/New_York",
        'TZID="America/New_York";VALUE=DATE',
        "America/New_York\x00",
        "TZID=Europe/London\nTZID=UTC",
    ],
)
def test_unknown_or_malformed_names(name):
    assert iana_zone(name) is None


def test_the_mapping_holds_every_default_windows_zone_as_one_zone_name():
    # The file was checked against the CLDR source it names when it was added; this keeps its shape.
    assert len(MAPPING) == 139
    assert all(isinstance(value, str) and len(value.split()) == 1 for value in MAPPING.values())


@pytest.mark.parametrize(("name", "expected"), sorted(MAPPING.items()))
def test_every_windows_name_resolves(name, expected):
    assert iana_zone(name) == expected
    assert ZoneInfo(expected).key == expected


def test_uses_default_territory_not_user_location():
    assert iana_zone("Eastern Standard Time") == "America/New_York"
    assert iana_zone("America/Toronto") == "America/Toronto"
