"""Resolve calendar time zone identifiers using CLDR 48.2 default territories."""

from __future__ import annotations

import re
from pathlib import Path
from zoneinfo import available_timezones

import yaml

#: Windows time zone names to IANA names for CLDR's default territory; the file names its source and version.
ZONES_FILE = Path(__file__).parent / "defaults" / "windows_zones.yaml"
_WINDOWS_ZONES: dict[str, str] = yaml.safe_load(ZONES_FILE.read_text(encoding="utf-8"))
_WINDOWS_FOLDED = {name.casefold(): zone for name, zone in _WINDOWS_ZONES.items()}
_IANA_ZONES = available_timezones() | set(_WINDOWS_ZONES.values())
_PREFIX = re.compile(r"^(?:tzone://Microsoft/|/Microsoft/|/IANA/|/freeassociation\.sourceforge\.net/Tzfile/)", re.I)


def iana_zone(name: str) -> str | None:
    """Return an IANA key, or None for an unknown or custom TZID.

    Accept a value or a TZID: / TZID= fragment, balanced single/double quotes,
    a leading slash, and recognized calendar namespace prefixes. Windows names
    are case-insensitive; IANA keys retain their case and aliases. No guessing
    from display labels, offsets, or custom VTIMEZONE definitions is performed.
    Pass only the TZID fragment, not a complete DTSTART property.
    """
    if not isinstance(name, str):
        return None
    value = name.strip()
    # Quotes may surround either the complete fragment or just its value.
    for _ in range(4):
        previous = value
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1].strip()
        value = re.sub(r"^TZID\s*[:=]\s*", "", value, count=1, flags=re.I)
        if value == previous:
            break
    value = _PREFIX.sub("", value, count=1)
    value = value.removeprefix("/")
    if not value or any(character in value for character in ('"', "'", "\n", "\r", "\x00")):
        return None
    if mapped := _WINDOWS_FOLDED.get(value.casefold()):
        return mapped
    return value if value in _IANA_ZONES else None
