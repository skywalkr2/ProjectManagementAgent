"""Installing a pack from the Add-ons screen: download its release file from the address the catalog gives, check it
against the catalog's SHA-256 checksum, and install it beside the app. Only a wheel of pure Python whose needs the app
already has is installed this way; anything else is refused with what to do instead. Installing never turns a pack
on, and the app uses it after the restart the person chooses. Removing takes away only what an install from here put
in place."""

from __future__ import annotations

import csv
import hashlib
import io
import shutil
import sysconfig
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

#: Written into an installed pack's metadata folder, so only what this app installed can be removed from here.
INSTALLER = "pm-cockpit"
#: The most a release file may be.
MAX_BYTES = 50 * 1024 * 1024


class InstallError(Exception):
    """A pack can't be installed or removed here; the message says why in plain words."""


@dataclass
class Installed:
    name: str
    version: str
    files: int


def target() -> Path:
    """Where packs are installed: the app's own place for pure Python packages."""
    return Path(sysconfig.get_paths()["purelib"])


def download(url: str, expected_sha256: str, token: str | None = None, client: Any = None) -> bytes:
    """The release file, checked against its checksum. A read token goes only to the release's own host; a
    redirect to another host gets no token."""
    import httpx

    headers = {"Accept": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code in (401, 403, 404):
                raise InstallError(
                    "the release file couldn't be read: it may be private, so the app needs a read token for the "
                    "place it is kept, or the address is wrong"
                )
            if response.status_code >= 400:
                raise InstallError(f"the release host answered {response.status_code}; try again later")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise InstallError("the release file is larger than an add-on may be")
                chunks.append(chunk)
    except httpx.HTTPError:
        raise InstallError("the release file couldn't be downloaded; check the connection and try again") from None
    finally:
        if own:
            client.close()
    data = b"".join(chunks)
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise InstallError("the downloaded file doesn't match the catalog's checksum, so it wasn't installed")
    return data


def install(data: bytes, place: Path | None = None) -> Installed:
    """Install a wheel of pure Python: check what it holds and needs, take away an earlier install of the same pack
    made from here, then put its files in place."""
    place = place or target()
    try:
        wheel = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InstallError("the release file isn't a package the app can install") from None
    names = wheel.namelist()
    info_dirs = {n.split("/", 1)[0] for n in names if n.split("/", 1)[0].endswith(".dist-info")}
    if len(info_dirs) != 1:
        raise InstallError("the release file isn't a package the app can install")
    info = info_dirs.pop()
    wheel_meta = Parser().parsestr(wheel.read(f"{info}/WHEEL").decode("utf-8"))
    if wheel_meta.get("Root-Is-Purelib", "").strip().lower() != "true" or not any(
        tag.strip().endswith("-none-any") for tag in wheel_meta.get_all("Tag", [])
    ):
        raise InstallError("only add-ons of pure Python install from here; this one needs installing by hand")
    meta = Parser().parsestr(wheel.read(f"{info}/METADATA").decode("utf-8"))
    name, version = meta["Name"], meta["Version"]
    missing = _missing(meta.get_all("Requires-Dist", []))
    if missing:
        raise InstallError(f"this add-on needs {', '.join(missing)}, which the app doesn't have; install it by hand")
    for member in names:
        path = PurePosixPath(member)
        if path.is_absolute() or ".." in path.parts or path.parts[0].endswith(".data"):
            raise InstallError("the release file holds paths the app won't install")
    _remove_earlier(name, place)
    written = []
    for member in wheel.infolist():
        if member.is_dir():
            continue
        destination = place / member.filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        with wheel.open(member) as source, destination.open("wb") as out:
            shutil.copyfileobj(source, out)
        written.append(member.filename)
    (place / info / "INSTALLER").write_text(INSTALLER + "\n", encoding="utf-8")
    record = io.StringIO()
    writer = csv.writer(record)
    for path in [*written, f"{info}/INSTALLER"]:
        if path != f"{info}/RECORD":
            writer.writerow([path, "", ""])
    writer.writerow([f"{info}/RECORD", "", ""])
    (place / info / "RECORD").write_text(record.getvalue(), encoding="utf-8")
    return Installed(name, version, len(written))


def _missing(requirements: list[str]) -> list[str]:
    found = []
    for line in requirements:
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            found.append(line)
            continue
        if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
            continue
        try:
            have = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            found.append(requirement.name)
            continue
        if requirement.specifier and not requirement.specifier.contains(have, prereleases=True):
            found.append(str(requirement))
    return found


def _info_dir(name: str, place: Path) -> Path | None:
    wanted = name.replace("-", "_").lower()
    for folder in place.glob("*.dist-info"):
        if folder.name.split("-", 1)[0].lower() == wanted:
            return folder
    return None


def installed_here(name: str, place: Path | None = None) -> bool:
    """Whether a pack of this name was installed from here, so it can be removed from here."""
    folder = _info_dir(name, place or target())
    marker = folder / "INSTALLER" if folder is not None else None
    return marker is not None and marker.is_file() and marker.read_text(encoding="utf-8").strip() == INSTALLER


def _remove_earlier(name: str, place: Path) -> None:
    folder = _info_dir(name, place)
    if folder is None:
        return
    marker = folder / "INSTALLER"
    if not marker.exists() or marker.read_text(encoding="utf-8").strip() != INSTALLER:
        raise InstallError(f"{name} was installed another way; update it the same way, or remove it first")
    remove(name, place)


def remove(name: str, place: Path | None = None) -> None:
    """Take away a pack installed from here: the files its record lists, and its metadata folder."""
    place = place or target()
    folder = _info_dir(name, place)
    if folder is None:
        raise InstallError(f"{name} isn't installed")
    installer = (folder / "INSTALLER").read_text(encoding="utf-8").strip() if (folder / "INSTALLER").exists() else ""
    if installer != INSTALLER:
        raise InstallError(f"{name} was installed another way, so it is removed the same way")
    record = folder / "RECORD"
    paths = [row[0] for row in csv.reader(record.read_text(encoding="utf-8").splitlines()) if row]
    for relative in paths:
        path = (place / relative).resolve()
        if path.is_relative_to(place.resolve()) and path.is_file():
            path.unlink()
    for relative in sorted({str(PurePosixPath(p).parent) for p in paths}, key=len, reverse=True):
        directory = place / relative
        if directory != place and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    if folder.exists():
        shutil.rmtree(folder)
