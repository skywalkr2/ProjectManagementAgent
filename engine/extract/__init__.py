"""Reading files as text (design 6.2): documents, spreadsheets, presentations, PDFs and plain text, each by a plain
function from bytes to text with a limit, so a run never asks the person to paste what a file already holds.

`read_file` picks the reader by media type (the file's name decides when the type is only generic), asks plugins'
readers first when the caller passes them, never returns an empty text (a file with nothing to read is a failure with
a reason), and cuts the text at the configured size with a mark. A type nothing reads is `Unsupported`.
"""

from __future__ import annotations

import posixpath
from collections.abc import Callable
from dataclasses import dataclass

from engine.extract.core import CUT_MARK, Extracted, ExtractError, Unsupported

DOCUMENT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SPREADSHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PRESENTATION = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PDF = "application/pdf"

#: What a file's ending says its type is, for files that arrive with no type or a generic one.
EXTENSIONS = {
    ".docx": DOCUMENT,
    ".xlsx": SPREADSHEET,
    ".pptx": PRESENTATION,
    ".pdf": PDF,
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".ics": "text/calendar",
    ".html": "text/html",
    ".htm": "text/html",
}
GENERIC = ("", "application/octet-stream", "binary/octet-stream", "application/x-download")

#: What a reader says when a file has no text in it, by kind.
NO_TEXT = {
    "pdf": "the PDF has no text in it; it may be pictures of pages",
    "document": "the document has no text in it",
    "spreadsheet": "the spreadsheet has no filled cells",
    "presentation": "the presentation has no text in it",
}


@dataclass(frozen=True)
class Reader:
    """A core reader: `kind` is what the screens call this kind of file, `media_types` the types it reads."""

    kind: str
    media_types: tuple[str, ...]
    read: Callable[[bytes, int], Extracted]


def _document(data: bytes, limit: int) -> Extracted:
    from engine.extract.office import read_document

    return read_document(data, limit)


def _spreadsheet(data: bytes, limit: int) -> Extracted:
    from engine.extract.office import read_spreadsheet

    return read_spreadsheet(data, limit)


def _presentation(data: bytes, limit: int) -> Extracted:
    from engine.extract.office import read_presentation

    return read_presentation(data, limit)


def _pdf(data: bytes, limit: int) -> Extracted:
    from engine.extract.pdf import read_pdf

    return read_pdf(data, limit)


def _text(data: bytes, limit: int) -> Extracted:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractError("the file isn't text in an encoding that can be read") from None
    return Extracted(text)


def _html(data: bytes, limit: int) -> Extracted:
    from engine.connectors.feed import plain

    return Extracted(plain(_text(data, limit).text))


READERS: tuple[Reader, ...] = (
    Reader("document", (DOCUMENT,), _document),
    Reader("spreadsheet", (SPREADSHEET,), _spreadsheet),
    Reader("presentation", (PRESENTATION,), _presentation),
    Reader("pdf", (PDF,), _pdf),
    Reader("text", ("text/html",), _html),
)
#: Any other `text/*` type is read as it is.
TEXT = Reader("text", (), _text)


def media_type_of(name: str, declared: str | None) -> str:
    """The media type to read a file as: the declared one without its parameters, in lower case; when it is missing
    or generic, the one its name's ending says (the declared one stays when the ending says nothing)."""
    declared = (declared or "").split(";", 1)[0].strip().lower()
    if declared in GENERIC:
        return EXTENSIONS.get(posixpath.splitext(name)[1].lower(), declared)
    return declared


def reader_for(media_type: str) -> Reader | None:
    for reader in READERS:
        if media_type in reader.media_types:
            return reader
    return TEXT if media_type.startswith("text/") else None


def kinds() -> list[str]:
    """The kinds of file the core reads, in a fixed order."""
    return list(dict.fromkeys([*(r.kind for r in READERS), TEXT.kind]))


@dataclass(frozen=True)
class Read:
    """What reading one file gave: its text (cut when `cut`) and the kind of file it was."""

    text: str
    cut: bool
    kind: str


def read_file(
    data: bytes,
    name: str,
    media_type: str | None,
    *,
    max_chars: int,
    max_bytes: int,
    plugin: Callable[[str, bytes, str], tuple[str, str] | None] | None = None,
) -> Read:
    """The text of one file. `plugin(media_type, data, name)` is asked first, and returns (kind, text) when a
    plugin's reader took the file, or None; the core's own reader follows. Raises `ExtractError` (with its `kind` once
    known) when the file is too large, can't be read, or has no text, and `Unsupported` when nothing reads its type."""
    media = media_type_of(name, media_type)
    if len(data) > max_bytes:
        raise ExtractError(f"it is larger than {max_bytes / (1024 * 1024):g} MB, the most that is read")
    taken = plugin(media, data, name) if plugin is not None else None
    if taken is not None:
        kind, text = taken
        cut = len(text) > max_chars
        result = Extracted(text[:max_chars] + "\n" + CUT_MARK if cut else text, cut)
    else:
        reader = reader_for(media)
        if reader is None:
            raise Unsupported(media)
        kind = reader.kind
        try:
            result = reader.read(data, max_chars)
        except ExtractError as err:
            raise ExtractError(err.reason, kind) from None
        except ImportError:
            raise ExtractError("the part of the app that reads this kind of file isn't installed", kind) from None
        except Exception:  # a reader never stops the caller; a file it can't take is a failure with a reason
            raise ExtractError("the file couldn't be read; it may be damaged", kind) from None
        if not result.cut and len(result.text) > max_chars:
            result = Extracted(result.text[:max_chars] + "\n" + CUT_MARK, True)
    if not result.text.strip():
        raise ExtractError(NO_TEXT.get(kind, "the file has no text in it"), kind)
    return Read(result.text, result.cut, kind)
