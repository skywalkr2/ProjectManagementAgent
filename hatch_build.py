"""Wheel build hook: copies the files the product ships beside its code into `engine/_shipped/`, where
`engine.shipped` finds them in an installed package. An editable install reads them from the checkout instead.

A wheel without the built web screens would install an app with no screens, so the build stops and says how to build
them.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

#: Each shipped folder: where it is in the checkout, and its name under engine/_shipped/.
FOLDERS = {"templates": "templates", "catalog": "catalog", "web/dist": "web"}
DEMOS = ("demo-a", "demo-b")
#: Runtime files a demo workspace may hold after someone ran it from the checkout; never shipped.
SKIP = ("cockpit.db", "cockpit.db-*", ".cockpit", "__pycache__", "*.pyc", ".git")


def _files(folder: Path):
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if path.is_file() and not any(fnmatch.fnmatch(part, pattern) for part in rel.parts for pattern in SKIP):
            yield path, rel


class ShippedFiles(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel" or version == "editable":
            return
        root = Path(self.root)
        if not (root / "web" / "dist" / "index.html").is_file():
            raise RuntimeError("The web screens aren't built. Run: npm --prefix web ci && npm --prefix web run build")
        sources = {root / src: f"engine/_shipped/{dest}" for src, dest in FOLDERS.items()}
        sources |= {root / "workspaces" / name: f"engine/_shipped/demos/{name}" for name in DEMOS}
        for folder, dest in sources.items():
            for path, rel in _files(folder):
                build_data["force_include"][str(path)] = f"{dest}/{rel.as_posix()}"
