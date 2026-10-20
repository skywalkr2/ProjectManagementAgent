"""Cloud-drive folders on this computer, offered as the place for backups (design 7.8).

Which drives to look for, and where each keeps its folder on each system, is a setting (`storage.backups.cloud_folders`,
with the app's own list in `engine/defaults/cloud_folders.yaml`); nothing here names a drive. A drive is found when one
of its places on this system exists inside the home folder. The first found is the one the guide recommends.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from engine.yaml_load import load_yaml

if TYPE_CHECKING:
    from collections.abc import Iterable

    from engine.config.schema import CloudFolder

DEFAULTS = Path(__file__).parent / "defaults" / "cloud_folders.yaml"
#: What joins the folders of a path shown to the person.
ARROW = " › "


@dataclass(frozen=True)
class Found:
    name: str  # the drive's name, as the entry gives it
    root: Path  # the drive's folder on this computer


def system_name() -> str:
    """Which of the three places an entry lists applies on this computer: "macos", "windows" or "linux"."""
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def shipped() -> list[CloudFolder]:
    """The app's own list of drives to look for."""
    from engine.config.schema import CloudFolder

    data = load_yaml(DEFAULTS.read_text(encoding="utf-8")) or {}
    return [CloudFolder.model_validate(entry) for entry in data.get("folders", [])]


def found(drives: Iterable[CloudFolder], home: Path, system: str | None = None) -> list[Found]:
    """The drives whose folder exists on this computer, in the order of the list, each with the first of its places that
    is a folder. A place may use `*` to match any characters in a name."""
    here = system or system_name()
    out: list[Found] = []
    for drive in drives:
        for place in getattr(drive, here, []):
            root = next((p for p in sorted(home.glob(place)) if p.is_dir()), None)
            if root is not None:
                out.append(Found(drive.name, root))
                break
    return out


def shown(parts: Iterable[str]) -> str:
    """A path of folders as the person reads it: plain names joined with arrows."""
    return ARROW.join(parts)


def make_backup_folder(root: Path, parts: Iterable[str]) -> Path:
    """The folder for backups inside a drive's folder, made when it isn't there yet."""
    folder = root.joinpath(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    return folder
