"""When this app was running, so the screens say only what is known about the time it was not.

While the app runs, its worker notes the moment it was last seen in a small file in the workspace's private folder. When
it next notes the moment and finds the last one longer ago than a gap's length, the stretch between them was a time the
app was not running (the computer asleep, or the app closed): it is kept as a gap. A reminder that came due is said to
have come due while the computer was away only when a gap covers its time; otherwise it is only said to be overdue.
Nothing here is read by anything that decides what to do, only by the words on a line."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine.state_file import changing, write_whole

log = logging.getLogger(__name__)

STATE_FILE = "running.json"
#: The most gaps kept, newest last; older ones are dropped.
MOST_GAPS = 200

Gap = tuple[datetime, datetime]


def _path(ws: Any) -> Path:
    return Path(ws.private_dir) / STATE_FILE


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _moment(value: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def note(ws: Any, now: datetime, gap: timedelta) -> bool:
    """Note that the app is running at `now`. When the last moment noted is more than `gap` before it, the time between
    is kept as a gap. Returns whether a gap was added. A file that can't be written is logged and leaves the screens
    saying less, never more."""
    path = _path(ws)
    try:
        with changing(path):
            data = _read(path)
            kept = [list(g) for g in data.get("gaps") or [] if isinstance(g, list) and len(g) == 2]
            last = _moment(data.get("last_seen"))
            added = last is not None and now - last > gap
            if added:
                kept.append([last.isoformat(), now.isoformat()])
            write_whole(path, json.dumps({"last_seen": now.isoformat(), "gaps": kept[-MOST_GAPS:]}, indent=2) + "\n")
            return added
    except OSError as err:
        log.warning("The moment this app was last running couldn't be noted: %s", err)
        return False


def gaps(ws: Any) -> list[Gap]:
    """The times the app is known not to have been running, oldest first."""
    found: list[Gap] = []
    for pair in _read(_path(ws)).get("gaps") or []:
        if isinstance(pair, list) and len(pair) == 2 and (start := _moment(pair[0])) and (end := _moment(pair[1])):
            found.append((start, end))
    return found


def covers(known: list[Gap], moment: datetime) -> bool:
    """Whether a gap includes `moment`."""
    return any(start <= moment <= end for start, end in known)
