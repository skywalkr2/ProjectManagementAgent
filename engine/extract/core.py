"""What every reader shares: the result, the failure, and the collector that stops at the limit."""

from __future__ import annotations

from dataclasses import dataclass, field

#: Said at the end of a text that was cut at the limit.
CUT_MARK = "(cut: the file has more text than is read)"


class ExtractError(Exception):
    """A file can't be read as text. `reason` is plain words for the person. `kind` says which kind of file (the
    reader's kind) once known."""

    def __init__(self, reason: str, kind: str | None = None):
        self.reason = reason
        self.kind = kind
        super().__init__(reason)


class Unsupported(ExtractError):
    """No reader handles this media type."""

    def __init__(self, media_type: str):
        self.media_type = media_type
        super().__init__("files of this kind can't be read yet")


@dataclass(frozen=True)
class Extracted:
    """The text of one file. `cut`: it stopped at the limit and `text` ends with the mark."""

    text: str
    cut: bool = False


@dataclass
class Text:
    """Collects lines up to a limit of characters, so a reader can stop as soon as it is `full`."""

    limit: int
    parts: list[str] = field(default_factory=list)
    size: int = 0
    cut: bool = False

    @property
    def full(self) -> bool:
        return self.cut

    def line(self, text: str) -> None:
        text = text.strip()
        if not text or self.cut:
            return
        room = self.limit - self.size
        if len(text) + 1 > room:
            self.parts.append(text[: max(room, 0)])
            self.cut = True
            return
        self.parts.append(text)
        self.size += len(text) + 1

    def result(self) -> Extracted:
        text = "\n".join(p for p in self.parts if p)
        return Extracted(text + "\n" + CUT_MARK if self.cut else text, self.cut)
