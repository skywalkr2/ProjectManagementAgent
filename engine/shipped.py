"""Files the product ships beside its code: starting templates, the AI endpoint catalog, the built web screens and the
fictional demo workspaces.

An installed package carries them in `engine/_shipped/` (the wheel's build hook copies them there); a checkout of the
repository uses them where they are. Code asks for a shipped folder by name and never builds the path itself.
"""

from __future__ import annotations

from pathlib import Path

PACKAGED = Path(__file__).resolve().parent / "_shipped"
CHECKOUT = Path(__file__).resolve().parents[1]

#: Each shipped folder: its name in the package, and where it is in a checkout.
FOLDERS = {
    "templates": "templates",
    "catalog": "catalog",
    "web": "web/dist",
    "demos": "workspaces",
}

#: The demo workspaces a person can start from; each holds only made-up names.
DEMOS = ("demo-a", "demo-b")


def shipped(name: str, packaged: Path = PACKAGED, checkout: Path = CHECKOUT) -> Path:
    """Where a shipped folder is: the installed package's copy when there is one, else the checkout's."""
    if name not in FOLDERS:
        raise KeyError(name)
    inside = packaged / name
    return inside if inside.is_dir() else checkout / FOLDERS[name]


def demo(name: str = "demo-b", packaged: Path = PACKAGED, checkout: Path = CHECKOUT) -> Path:
    """A demo workspace's folder, to copy a new workspace from."""
    if name not in DEMOS:
        raise KeyError(name)
    return shipped("demos", packaged, checkout) / name
