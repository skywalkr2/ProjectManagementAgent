"""Collect the installed application's modules, metadata, and bundled resources."""

import importlib.metadata
import importlib.util
import os
import platform
import sys
from pathlib import Path

from build_model import bundled_data, release_versions
from packaging.version import Version
from PyInstaller.utils.hooks import collect_submodules, copy_metadata


def freeze_inputs(root: Path, expected_system: str) -> dict:
    if sys.platform != expected_system:
        raise SystemExit("Run this spec on its target operating system")
    version = os.environ.get("APP_VERSION")
    if not version:
        raise SystemExit("Set APP_VERSION explicitly before freezing")
    display, numeric = release_versions("v" + version)
    entries = list(importlib.metadata.entry_points(group="console_scripts", name="cockpit"))
    if len(entries) != 1 or entries[0].value != "engine.cli:main":
        raise SystemExit("Install exactly one cockpit console script pointing to engine.cli:main")
    distribution = entries[0].dist
    if distribution is None or Version(distribution.version) != Version(display):
        raise SystemExit("The installed package version must match the release tag")
    datas = list(bundled_data(root))
    for source, _ in datas:
        if not Path(source).is_dir() or not any(Path(source).rglob("*")):
            raise SystemExit(f"Required data folder is missing or empty: {source}")
    if not (root / "web" / "dist" / "index.html").is_file():
        raise SystemExit("Build the front end first: web/dist/index.html is missing")
    datas.extend(copy_metadata(distribution.metadata["Name"], recursive=True))
    hiddenimports = collect_submodules("engine")
    for package in ("plugins", "uvicorn"):
        if importlib.util.find_spec(package) is not None:
            hiddenimports.extend(collect_submodules(package))
    architecture = platform.machine().lower()
    if expected_system == "darwin" and architecture not in {"arm64", "x86_64"}:
        raise SystemExit("A native arm64 or x86_64 interpreter is required")
    return {
        "datas": datas,
        "hiddenimports": sorted(set(hiddenimports)),
        "version": display,
        "numeric_version": numeric,
        "architecture": architecture,
    }
