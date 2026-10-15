"""Whether the readers work, kept in the workspace's private folder so Today can say so.

Each core reader reads a tiny made-up file of its kind when the app starts (`self_test`); one that fails is a problem
until a later check or a later real file of that kind reads well. A real file that couldn't be read is the same kind
of problem: the person is told once, on Today, and not asked for the file's text. Media types nothing reads are
remembered, so each is flagged to the person once, however many files of it arrive.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from engine.extract import read_file
from engine.extract.core import ExtractError
from engine.extract.fixtures import CHECKS
from engine.state_file import write_whole

STATE_FILE = "extractors.json"
_LOCK = threading.Lock()

#: A check file is tiny; these only keep a broken reader from running away.
CHECK_CHARS = 20_000
CHECK_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Problem:
    """A kind of file that isn't being read. `reason` is plain words; `since` an ISO time."""

    kind: str
    reason: str
    since: str


def check_readers() -> dict[str, str | None]:
    """Each core reader on its own check file, by kind: None when it read the file and found its words, else why not."""
    found: dict[str, str | None] = {}
    for kind, (media_type, build, phrases) in CHECKS.items():
        try:
            read = read_file(build(), "check", media_type, max_chars=CHECK_CHARS, max_bytes=CHECK_BYTES)
        except ExtractError as err:
            found[kind] = f"its own check file didn't read: {err.reason}"
            continue
        except Exception:
            found[kind] = "it stopped on its own check file"
            continue
        missing = [p for p in phrases if p not in read.text]
        found[kind] = "it read its own check file but missed some of the words in it" if missing else None
    return found


def self_test(ws: Any, now: datetime | None = None) -> list[Problem]:
    """Run every reader's check and keep the result: a failing reader becomes a problem, a passing one ends a problem
    its own check raised. Returns the problems now."""
    results = check_readers()
    stamp = (now or datetime.now(UTC)).isoformat()
    with _LOCK:
        state = _load(ws)
        shown = state["problems"]
        before = json.dumps(shown, sort_keys=True)
        for kind, reason in results.items():
            held = shown.get(kind)
            if reason:
                since = held["since"] if held and held["reason"] == reason else stamp
                shown[kind] = {"reason": reason, "since": since, "from": "check"}
            elif held and held["from"] == "check":
                del shown[kind]
        if json.dumps(shown, sort_keys=True) != before:
            _save(ws, state)
    return problems(ws)


def note_read(ws: Any, kind: str, reason: str | None, now: datetime | None = None) -> None:
    """A real file of this kind was read (`reason` None: it worked, which ends a problem) or couldn't be."""
    with _LOCK:
        state = _load(ws)
        shown = state["problems"]
        if reason is None:
            if shown.pop(kind, None) is not None:
                _save(ws, state)
            return
        held = shown.get(kind)
        if held and held["reason"] == reason:
            return
        shown[kind] = {"reason": reason, "since": (now or datetime.now(UTC)).isoformat(), "from": "file"}
        _save(ws, state)


def problems(ws: Any) -> list[Problem]:
    """The kinds of file that aren't being read, oldest first."""
    with _LOCK:
        shown = _load(ws)["problems"]
    return sorted(
        (Problem(kind, v["reason"], v["since"]) for kind, v in shown.items()), key=lambda p: (p.since, p.kind)
    )


def flag_unsupported(ws: Any, media_type: str) -> bool:
    """Note that files of this media type can't be read. True the first time only, so the person is told once."""
    with _LOCK:
        state = _load(ws)
        if media_type in state["unsupported"]:
            return False
        state["unsupported"].append(media_type)
        _save(ws, state)
        return True


def _load(ws: Any) -> dict[str, Any]:
    try:
        data = json.loads((ws.private_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    problems_ = data.get("problems")
    unsupported = data.get("unsupported")
    return {
        "problems": problems_ if isinstance(problems_, dict) else {},
        "unsupported": unsupported if isinstance(unsupported, list) else [],
    }


def _save(ws: Any, state: dict[str, Any]) -> None:
    write_whole(ws.private_dir / STATE_FILE, json.dumps(state, indent=2, sort_keys=True) + "\n")
