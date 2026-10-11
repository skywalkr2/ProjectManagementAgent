"""Connectors: where the assistant reads from (design 6.2). A connector lists what a source holds now; the watcher
(6.4) compares that with what it saw last time and hands in what is new, changed or gone.

The core ships a folder connector and a stand-in for tests; plugins add others (`registrar.connector`). A connector
returns plain data and raises `ConnectorError` with a kind: `auth` (sign in again), `no_access`, `not_found`,
`outage` (the service is failing) or `offline` (no network here, which is never an outage and files nothing).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ErrorKind = Literal["auth", "no_access", "not_found", "outage", "offline"]


@dataclass(frozen=True)
class SourceItem:
    """One thing a source holds: a stable key within the source, a title, its text now, and who changed it last."""

    key: str
    title: str
    text: str
    author: str | None = None
    changed_at: str | None = None
    link: str | None = None


@dataclass
class Poll:
    """What a source holds now. `complete`: the list is everything (an item missing from it is gone); otherwise it is
    only what changed since `state`. `state` is kept and given back on the next read."""

    items: list[SourceItem]
    state: dict[str, Any] = field(default_factory=dict)
    complete: bool = True


class ConnectorError(Exception):
    def __init__(self, kind: ErrorKind, detail: str = ""):
        self.kind = kind
        self.detail = detail[:500]
        super().__init__(f"{kind}: {self.detail}" if self.detail else kind)


@dataclass(frozen=True)
class ConnectorContext:
    """What a connector's read gets besides its settings: the workspace's folder (for paths relative to it), and for
    a plugin that declares them, a web client limited to its `requires.network` hosts and its declared secrets."""

    workspace_root: Path
    web: Any = None  # engine.net.WebClient, or None when the connector may not reach the network
    secret: Callable[[str], str | None] | None = None  # a declared secret's value, or None when it isn't set
    keep_secret: Callable[[str, str], None] | None = None  # keep a declared secret (a refreshed token) on this computer
    access_token: Callable[[str], str] | None = None  # a current token for one of the plugin's own sign-ins


@dataclass(frozen=True)
class Connector:
    name: str
    label: str
    settings: type[BaseModel]
    poll: Callable[[Any, dict[str, Any], ConnectorContext], Poll]
    network: bool = False


# ---- the folder connector ------------------------------------------------------------------------------------------


class FolderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, description="The folder: a full path, or one inside the workspace's folder.")
    patterns: list[str] = Field(
        default_factory=lambda: ["*.txt", "*.md"], description="Which files to read, as name patterns."
    )
    subfolders: bool = Field(True, description="Read the folders inside it too.")
    max_kb: int = Field(512, ge=1, description="Files larger than this are listed as too large and not read.")


def _read_folder(settings: FolderSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    folder = Path(settings.path).expanduser()
    if not folder.is_absolute():
        folder = context.workspace_root / folder
    if not folder.is_dir():
        raise ConnectorError("not_found", f"the folder {folder} isn't there")
    items = []
    found = set()
    for pattern in settings.patterns:
        for path in sorted(folder.rglob(pattern) if settings.subfolders else folder.glob(pattern)):
            if not path.is_file() or path in found or any(part.startswith(".") for part in path.parts[-3:]):
                continue
            found.add(path)
            key = path.relative_to(folder).as_posix()
            if path.stat().st_size > settings.max_kb * 1024:
                items.append(SourceItem(key, path.name, f"(not read: larger than {settings.max_kb} KB)"))
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                items.append(SourceItem(key, path.name, "(not read: not plain text)"))
                continue
            items.append(SourceItem(key, path.name, text))
    return Poll(items, state, complete=True)


# ---- the stand-in connector -----------------------------------------------------------------------------------------


class FakeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(default_factory=list, description="What the source holds: key, title, text.")
    error: ErrorKind | None = Field(None, description="Fail every read with this kind of error.")


def _read_fake(settings: FakeSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    if settings.error:
        raise ConnectorError(settings.error, "the stand-in source is set to fail")
    reads = int(state.get("reads", 0)) + 1
    return Poll([SourceItem(**item) for item in settings.items], {"reads": reads}, complete=True)


def _core() -> dict[str, Connector]:
    from engine.connectors.calendar import CalendarSettings, read_calendar
    from engine.connectors.feed import FeedSettings, read_feed
    from engine.connectors.mailbox import MailboxSettings, read_mailbox

    return {
        "folder": Connector("folder", "A folder", FolderSettings, _read_folder),
        "feed": Connector("feed", "A news feed (RSS or Atom)", FeedSettings, read_feed, network=True),
        "calendar": Connector("calendar", "A calendar (its private address)", CalendarSettings, read_calendar, True),
        "mailbox": Connector("mailbox", "A mail folder (IMAP)", MailboxSettings, read_mailbox, network=True),
        "fake": Connector("fake", "A stand-in source for tests", FakeSettings, _read_fake),
    }


CORE: dict[str, Connector] = _core()
