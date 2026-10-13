"""Small state files kept on this computer (the workspace's private folder): written whole, changed one at a time.

`write_whole` puts the new content in a temporary file beside the target and replaces the target with it, so a reader
finds the old file or the new one and never half of either, and two writers never share a temporary file. `changing`
holds one lock per file for a read, a change and a write, so changes made at the same moment (request threads and the
worker's threads) are applied one after the other and none is lost.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def write_whole(path: Path, text: str, *, mode: int | None = None) -> None:
    """Write `text` to `path` in one step. With `mode`, the file is created with those permissions from the start, so
    it is never readable more widely than that, not even for a moment. The folder is made when it is missing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.saving")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666 if mode is None else mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if mode is not None:
            os.chmod(temporary, mode)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def changing(path: Path) -> Iterator[None]:
    """Hold the lock of one state file while it is read, changed and written. Re-entrant, so a function that holds it
    may call another that takes it too."""
    key = str(Path(path).absolute())
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield
