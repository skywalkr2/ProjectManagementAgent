"""Validate explicit build inputs without accessing external state."""

import re
from pathlib import PurePath

from packaging.version import Version


def release_versions(tag: str) -> tuple[str, str]:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?", tag):
        raise ValueError("Use a vMAJOR.MINOR.PATCH tag, optionally with a prerelease or post-release suffix")
    version = Version(tag[1:])
    if any(part > 65535 for part in version.release):
        raise ValueError("Version components exceed the installer version limit")
    numeric = ".".join(str(part) for part in version.release)
    return str(version), numeric


def bundled_data(root: PurePath) -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(root / folder), folder)
        for folder in (
            "web/dist",
            "engine/defaults",
            "engine/guide",
            "prompts",
            "plugins",
        )
    )
