"""Select a release from supplied feed data without fetching any resources."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit

from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    notes: str
    download_url: str
    sha256: str


def newer_release(
    current: str,
    feed: str | bytes | list[dict],
    include_prereleases: bool = False,
) -> Release | None:
    """Return the highest eligible version; reject ambiguous or malformed feed envelopes."""
    if not isinstance(current, str):
        raise ValueError("The current version must be text")
    try:
        installed = Version(current)
    except InvalidVersion as error:
        raise ValueError("The current version is unknown because it is invalid") from error
    if type(include_prereleases) is not bool:
        raise ValueError("include_prereleases must be a boolean")

    def object_pairs(pairs: list[tuple]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("The JSON contains a duplicate field name")
            result[key] = value
        return result

    if isinstance(feed, (str, bytes)):
        try:
            entries = json.loads(feed, object_pairs_hook=object_pairs)
        except (ValueError, UnicodeError) as error:
            raise ValueError("The release feed is not unambiguous JSON") from error
    else:
        entries = feed
    if not isinstance(entries, list):
        raise ValueError("The release feed must be a JSON list")
    eligible: dict[Version, list[Release]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fields = ("version", "date", "notes", "download_url", "sha256")
        if any(not isinstance(entry.get(field), str) for field in fields):
            continue
        version_text, published, notes, address, checksum = (entry[field] for field in fields)
        if not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
            continue
        try:
            version = Version(version_text)
            if version <= installed or (version.is_prerelease and not include_prereleases):
                continue
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
                date.fromisoformat(published)
            else:
                timestamp = datetime.fromisoformat(published)
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    continue
            if any(character.isspace() or ord(character) < 32 for character in address):
                continue
            parsed = urlsplit(address)
            # Only an encrypted download: over plain HTTP the file and its checksum could both be swapped.
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                continue
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                continue
        except (InvalidVersion, ValueError):
            continue
        release = Release(version_text, published, notes, address, checksum.lower())
        eligible.setdefault(version, []).append(release)
    if not eligible:
        return None
    newest = max(eligible)
    choices = eligible[newest]
    details = {(release.date, release.notes, release.download_url, release.sha256) for release in choices}
    if len(details) != 1:
        raise ValueError("The newest version has conflicting feed entries; the release is unknown")
    # Equivalent version spellings with identical metadata get a stable representative.
    return min(choices, key=lambda release: release.version)
