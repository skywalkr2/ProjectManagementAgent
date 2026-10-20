"""Connectors: where the assistant reads from (design 6.2). A connector lists what a source holds now; the watcher
(6.4) compares that with what it saw last time and hands in what is new, changed or gone.

The core ships a folder connector and a stand-in for tests; plugins add others (`registrar.connector`). A connector
returns plain data and raises `ConnectorError` with a kind: `auth` (sign in again), `no_access`, `not_found`,
`outage` (the service is failing) or `offline` (no network here, which is never an outage and files nothing).
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.extract import media_type_of, reader_for

ErrorKind = Literal["auth", "no_access", "not_found", "outage", "offline", "throttled"]
#: What a connector can say it reads, for the screens that offer mail and calendar services.
ReadKind = Literal["mail", "calendar"]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventPerson:
    """Someone on a calendar event. `address`: their address, without `mailto:`. `name`: as the calendar names them.
    `response`: their answer to the invitation as the service says it, in lower case (accepted, declined, tentative,
    needs-action, delegated); None when it says none."""

    address: str | None = None
    name: str | None = None
    response: str | None = None


@dataclass(frozen=True)
class EventOccurrence:
    """One date of a repeating event the connector expanded. `start` and `end`: as on `EventDetails`. `was`: the
    start it had in the series before it was moved, set only for a moved date (the series' own date is the date's
    identity, so a moved date is still the same one). `cancelled`: this date was called off. `title`, `where`: what
    differs from the series for a changed date; None for the series' own."""

    start: str
    end: str | None = None
    was: str | None = None
    cancelled: bool = False
    title: str | None = None
    where: str | None = None


@dataclass(frozen=True)
class EventDetails:
    """What a calendar item is, for the day's agenda. `start` and `end`: ISO 8601 date-times with their offset
    (`2026-03-02T09:30:00+01:00` or `...Z`), or plain dates (`2026-03-02`) with `all_day`; an all-day `end` is the day
    after the last day, as calendars write it. `where`: the place or the meeting address, as the service says.
    `cancelled`: the organizer called it off. `repeats`: the repeat rule as the service wrote it, for an item that
    stands for a series; with `occurrences` empty the agenda can't place its dates. `occurrences`: the dates of a
    series the connector expanded over its window (the first in `start` and `end`), each with its own start and end,
    so the agenda shows every date and a changed or called-off date touches only that date. `organizer` and
    `attendees`: who invited and who is asked. `method`: how the calendar says the event was sent (`REQUEST` for an
    invitation). `notes`: plain sentences about how the event was read that the person should see (a repeat rule
    that wasn't understood, a time zone that was guessed). `entries`: ask the core to keep each date as a calendar
    entry of its own (with its attendees), so a promise can be due at it and move with it."""

    start: str
    end: str | None = None
    all_day: bool = False
    where: str | None = None
    cancelled: bool = False
    repeats: str | None = None
    occurrences: tuple[EventOccurrence, ...] = ()
    organizer: EventPerson | None = None
    attendees: tuple[EventPerson, ...] = ()
    method: str | None = None
    notes: tuple[str, ...] = ()
    entries: bool = False

    @staticmethod
    def from_dict(data: dict[str, Any]) -> EventDetails:
        """The details as the snapshot keeps them (nested values as plain data) back as they were handed in."""
        organizer = data.get("organizer")
        return EventDetails(
            **{
                **data,
                "occurrences": tuple(EventOccurrence(**o) for o in data.get("occurrences") or ()),
                "organizer": EventPerson(**organizer) if organizer else None,
                "attendees": tuple(EventPerson(**a) for a in data.get("attendees") or ()),
                "notes": tuple(data.get("notes") or ()),
            }
        )


@dataclass(frozen=True)
class MessageDetails:
    """What a mail item is, for the day's inbox. `sender`: who it is from, as the service names them, with the address
    in angle brackets when it has one (`Name <name@example.com>`), which sender rules read. `received`: an ISO 8601
    date-time with its offset. `unread`: whether the person hasn't opened it yet, when the service says. `bulk`:
    whether the message says it was sent to many (it has a list-unsubscribe header, or a bulk or list precedence),
    None when the connector can't tell. `categories`: the service's own categories or labels for it, as read and in
    lower case (promotions, social, say); empty when it has none or doesn't say. `participants`: everyone else on the
    message (the people it was sent to, and those copied), each as the service names them, with the address in angle
    brackets when it has one; empty when there are none or the service doesn't say. A first name in the text means
    the person of that name who is on the message."""

    sender: str | None = None
    received: str | None = None
    unread: bool | None = None
    bulk: bool | None = None
    categories: tuple[str, ...] = ()
    participants: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemFile:
    """A file an item carries (a mail's attachment, a document in a folder). `name`: its file name. `media_type`: its
    type as the service says it; when that is missing or generic, the name's ending decides. `data`: its bytes. The
    core reads it as text with its readers (a plugin's reader for the type first), cuts the text at the configured
    size and adds it to the item's text, so a connector never parses a file and hands over what it has."""

    name: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class SourceItem:
    """One thing a source holds. `key`: stable within the source (a message or event id), so the same thing read
    again is compared with what was seen. `title`: one line naming it. `text`: everything the assistant should read
    about it now, as plain text; a change is a change in this text. `author`: who changed it last, as the service
    names them (triage rules compare it with `workspace.our_accounts`). `changed_at`: when, as the service says it.
    `link`: where the person can open it. `event` or `message` (at most one): what it is, for a calendar item or a
    mail item, so Today can show the day's agenda and what came in; the text still says everything the assistant
    reads. `files`: the files it carries (attachments), which the core reads and adds to the text."""

    key: str
    title: str
    text: str
    author: str | None = None
    changed_at: str | None = None
    link: str | None = None
    event: EventDetails | None = None
    message: MessageDetails | None = None
    files: tuple[ItemFile, ...] = ()


@dataclass
class Poll:
    """What a source holds now. `items`: what it lists. `complete`: True when the list is everything, so an item
    missing from it is gone; False when it is only what changed since `state`. `removed`: keys the service says are
    gone, for a read that lists only changes (handed in like an item missing from a complete read, when the source
    reports removals). `state`: kept and given back on the next read (a change marker, say); a read that fails keeps
    the state of the last read that worked."""

    items: list[SourceItem]
    state: dict[str, Any] = field(default_factory=dict)
    complete: bool = True
    removed: list[str] = field(default_factory=list)


class ConnectorError(Exception):
    """Why a read failed. `kind`: auth (sign in again), no_access, not_found, outage (the service is failing),
    offline (no network here: never counted as a failure), or throttled (the service asked to wait: `retry_after`
    seconds; the source isn't read again before then, and it isn't counted as a failure). When the web client raised
    it from an answer, `status`, `headers` and `body` (its text, at most 20 KB) are the service's own, and `json()`
    parses the body, so a connector can read the service's error code and raise a better kind itself. `advice_key`
    names, in the screen's wording sheet, a sentence that says what the person should do about it (it replaces the
    kind's usual advice); leave it out to use the kind's."""

    def __init__(
        self,
        kind: ErrorKind,
        detail: str = "",
        *,
        retry_after: float | None = None,
        status: int | None = None,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        advice_key: str | None = None,
    ):
        self.kind = kind
        self.advice_key = advice_key
        self.detail = detail[:500]
        self.retry_after = retry_after
        self.status = status
        self.headers = dict(headers or {})
        self.body = body[:20_000] if body is not None else None
        super().__init__(f"{kind}: {self.detail}" if self.detail else kind)

    def json(self) -> Any:
        """The answer's body as JSON, or None when it isn't any."""
        import json

        try:
            return json.loads(self.body) if self.body else None
        except ValueError:
            return None


def checked_poll(poll: Any) -> Poll:
    """A connector's answer, checked the way the watcher reads it. Raises ValueError with what is wrong."""
    if not isinstance(poll, Poll):
        raise ValueError("poll must return a Poll")
    for item in poll.items:
        if not isinstance(item, SourceItem):
            raise ValueError("a Poll's items are SourceItems")
        if not all(isinstance(v, str) for v in (item.key, item.title, item.text)) or not item.key:
            raise ValueError("a SourceItem has a key, a title and its text, all text")
        _check_details(item)
        _check_files(item)
    if not isinstance(poll.state, dict):
        raise ValueError("a Poll's state is a dict")
    if not all(isinstance(k, str) and k for k in poll.removed):
        raise ValueError("a Poll's removed lists keys")
    if poll.complete and poll.removed:
        raise ValueError("only a read that lists changes (complete=False) names removed keys")
    keys = [i.key for i in poll.items]
    if len(keys) != len(set(keys)):
        raise ValueError("a Poll lists each key once")
    return poll


def _check_files(item: SourceItem) -> None:
    if not isinstance(item.files, (tuple, list)):
        raise ValueError(f"item {item.key!r}: files is a list of ItemFile")
    for file in item.files:
        if not isinstance(file, ItemFile):
            raise ValueError(f"item {item.key!r}: files is a list of ItemFile")
        if not isinstance(file.name, str) or not isinstance(file.media_type, str) or not isinstance(file.data, bytes):
            raise ValueError(f"item {item.key!r}: a file has a name and a media type (text) and its data (bytes)")


def moment(value: str, *, all_day: bool = False) -> datetime | date:
    """An ISO 8601 date-time with its offset, or with `all_day` a plain date. Raises ValueError otherwise."""
    if all_day:
        return date.fromisoformat(value[:10]) if len(value) == 10 else _aware(value).date()
    return _aware(value)


def _aware(value: str) -> datetime:
    when = datetime.fromisoformat(value.replace("Z", "+00:00") if value.endswith("Z") else value)
    if when.tzinfo is None:
        raise ValueError(f"{value!r} has no offset; write it as 2026-03-02T09:30:00+01:00 or ...Z")
    return when


def _check_event_people(key: str, event: EventDetails) -> None:
    people = [*event.attendees, *([event.organizer] if event.organizer is not None else [])]
    if not isinstance(event.attendees, (tuple, list)) or not all(isinstance(p, EventPerson) for p in people):
        raise ValueError(f"event {key!r}: attendees is a list of EventPerson, and organizer an EventPerson")
    if not isinstance(event.occurrences, (tuple, list)) or not all(
        isinstance(o, EventOccurrence) for o in event.occurrences
    ):
        raise ValueError(f"event {key!r}: occurrences is a list of EventOccurrence")
    for occurrence in event.occurrences:
        try:
            moment(occurrence.start, all_day=event.all_day)
            if occurrence.end:
                moment(occurrence.end, all_day=event.all_day)
        except (TypeError, ValueError) as err:
            raise ValueError(f"event {key!r}: an occurrence: {err}") from None
    if not isinstance(event.notes, (tuple, list)) or not all(isinstance(n, str) for n in event.notes):
        raise ValueError(f"event {key!r}: notes is a list of text")


def _check_details(item: SourceItem) -> None:
    if item.event is not None and item.message is not None:
        raise ValueError(f"item {item.key!r} is an event or a message, not both")
    if item.event is not None:
        event = item.event
        if not isinstance(event, EventDetails):
            raise ValueError("a SourceItem's event is an EventDetails")
        try:
            start = moment(event.start, all_day=event.all_day)
            end = moment(event.end, all_day=event.all_day) if event.end else None
        except (TypeError, ValueError) as err:
            raise ValueError(f"event {item.key!r}: {err}") from None
        if end is not None and end < start:
            raise ValueError(f"event {item.key!r} ends before it starts")
        _check_event_people(item.key, event)
    if item.message is not None:
        if not isinstance(item.message, MessageDetails):
            raise ValueError("a SourceItem's message is a MessageDetails")
        if item.message.received:
            try:
                _aware(item.message.received)
            except (TypeError, ValueError) as err:
                raise ValueError(f"message {item.key!r}: {err}") from None
        if item.message.bulk is not None and not isinstance(item.message.bulk, bool):
            raise ValueError(f"message {item.key!r}: bulk is true, false or left out")
        categories = item.message.categories
        if not isinstance(categories, (tuple, list)) or not all(isinstance(c, str) for c in categories):
            raise ValueError(f"message {item.key!r}: categories is a list of text")
        participants = item.message.participants
        if not isinstance(participants, (tuple, list)) or not all(isinstance(p, str) for p in participants):
            raise ValueError(f"message {item.key!r}: participants is a list of text")


@dataclass(frozen=True)
class ConnectorContext:
    """What a connector's read gets besides its settings: the workspace's folder (for paths relative to it), and for
    a plugin that declares them, a web client limited to its `requires.network` hosts and its declared secrets."""

    workspace_root: Path
    web: Any = None  # engine.net.WebClient, or None when the connector may not reach the network
    secret: Callable[[str], str | None] | None = None  # a declared secret's value, or None when it isn't set
    keep_secret: Callable[[str, str], None] | None = None  # keep a declared secret (a refreshed token) on this computer
    access_token: Callable[[str], str] | None = None  # a current token for one of the plugin's own sign-ins
    granted: Callable[[str], set[str]] | None = None  # the scopes the person allowed for one of its sign-ins
    #: The address of the account of the plugin's sign-in this source reads with (read-only): what the source names,
    #: else the one account signed in. None when none is signed in, or several are and none is named.
    account: str | None = None
    #: The moment of this read, and the person's time zone (an IANA name), for the core's own connectors: a window
    #: and times with no zone are read against them. Not given to a plugin's connector.
    now: datetime | None = None
    timezone: str | None = None
    #: The app is hosted, so a core connector doesn't read files from the computer it runs on.
    hosted: bool = False


@dataclass(frozen=True)
class Connector:
    name: str
    label: str
    settings: type[BaseModel]
    poll: Callable[[Any, dict[str, Any], ConnectorContext], Poll]
    network: bool = False
    #: A kind made for tests and fixtures: sources already set up with it still read and show, but it is not offered
    #: to a person adding a source.
    test_only: bool = False
    #: What the connector reads, when it says: "mail" or "calendar". Left out, the kind is guessed from its name.
    reads: ReadKind | None = None


#: Words in a connector's name (the part after the add-on's name) that say what kind of thing it reads. Used only for a
#: connector that doesn't declare what it reads.
READS_WORDS: dict[str, tuple[str, ...]] = {
    "mail": ("mail", "mailbox", "email", "inbox"),
    "calendar": ("calendar",),
}

_guessed: set[str] = set()


def declared_reads(connectors: Mapping[str, Connector]) -> dict[str, str | None]:
    """What each of these connectors says it reads (None for one that doesn't say), by name."""
    return {name: connector.reads for name, connector in connectors.items()}


def reads(connector: str, declared: Mapping[str, str | None] | None = None) -> list[str]:
    """What a connector reads: "mail" or "calendar", or nothing for any other kind. The declaration comes first
    (`declared` maps a connector's name to what it says it reads: a registered connector's `reads`, or a manifest's
    `provides.connector_reads`). A connector that says nothing is read by its name, and a match is logged once, since
    the connector should say so itself."""
    said = (declared or {}).get(connector)
    if said:
        return [said]
    last = connector.rsplit("/", 1)[-1].lower()
    guessed = [kind for kind, words in READS_WORDS.items() if last in words]
    if guessed and connector not in _guessed:
        _guessed.add(connector)
        log.warning("Connector %s doesn't declare what it reads; guessed %s from its name", connector, guessed[0])
    return guessed


# ---- the folder connector ------------------------------------------------------------------------------------------


class FolderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, description="The folder: a full path, or one inside the workspace's folder.")
    patterns: list[str] = Field(
        default_factory=lambda: ["*.txt", "*.md"],
        description="Which files to read, as name patterns. Documents, spreadsheets, presentations and PDFs are read "
        "as text too.",
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
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
            if stat.st_size > settings.max_kb * 1024:
                items.append(
                    SourceItem(key, path.name, f"(not read: larger than {settings.max_kb} KB)", changed_at=modified)
                )
                continue
            media = media_type_of(path.name, None)
            reader = reader_for(media)
            if reader is not None and reader.kind != "text":
                # A document, spreadsheet, presentation or PDF: handed over as bytes, read by the core.
                try:
                    data = path.read_bytes()
                except OSError:
                    items.append(
                        SourceItem(key, path.name, "(not read: the file can't be opened)", changed_at=modified)
                    )
                    continue
                items.append(
                    SourceItem(key, path.name, "", changed_at=modified, files=(ItemFile(path.name, media, data),))
                )
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                items.append(SourceItem(key, path.name, "(not read: not plain text)", changed_at=modified))
                continue
            items.append(SourceItem(key, path.name, text, changed_at=modified))
    return Poll(items, state, complete=True)


# ---- the stand-in connector -----------------------------------------------------------------------------------------


class FakeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="What the source holds: key, title, text, event or message details, and files (name, media type "
        "and data as base64 text).",
    )
    error: ErrorKind | None = Field(None, description="Fail every read with this kind of error.")


def _read_fake(settings: FakeSettings, state: dict[str, Any], context: ConnectorContext) -> Poll:
    if settings.error:
        raise ConnectorError(settings.error, "the stand-in source is set to fail")
    reads = int(state.get("reads", 0)) + 1
    items = []
    for raw in settings.items:
        item = dict(raw)
        event, message = item.pop("event", None), item.pop("message", None)
        files = tuple(
            ItemFile(f["name"], f["media_type"], base64.b64decode(f["data"])) for f in item.pop("files", None) or []
        )
        items.append(
            SourceItem(
                **item,
                files=files,
                event=EventDetails.from_dict(event) if event else None,
                message=MessageDetails(
                    **{
                        **message,
                        "categories": tuple(message.get("categories", ())),
                        "participants": tuple(message.get("participants", ())),
                    }
                )
                if message
                else None,
            )
        )
    return Poll(items, {"reads": reads}, complete=True)


def _core() -> dict[str, Connector]:
    from engine.connectors.calendar import CalendarSettings, read_calendar
    from engine.connectors.feed import FeedSettings, read_feed
    from engine.connectors.mailbox import MailboxSettings, read_mailbox

    return {
        "folder": Connector("folder", "A folder", FolderSettings, _read_folder),
        "feed": Connector("feed", "A news feed (RSS or Atom)", FeedSettings, read_feed, network=True),
        "calendar": Connector(
            "calendar", "A calendar (its private address)", CalendarSettings, read_calendar, True, reads="calendar"
        ),
        "mailbox": Connector(
            "mailbox", "A mail folder (IMAP)", MailboxSettings, read_mailbox, network=True, reads="mail"
        ),
        "fake": Connector("fake", "A stand-in source for tests", FakeSettings, _read_fake, test_only=True),
    }


CORE: dict[str, Connector] = _core()
