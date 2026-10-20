"""Passwords and keys typed on a screen and kept on this computer, and when they go (design 4.0, 12.3).

`engine.setup.keep_secret` writes each one into the workspace's private keys folder and lists it here in a small index
beside the folder (`kept-secrets.json`). Only what is in the index is ever removed: sign-in tokens, the add-ons' own
files and anything the person put there are never touched.

A kept secret is removed when no setting refers to it any more and one of these holds:
- it has been unreferenced for `storage.kept_secrets.keep_days` (an old one that was replaced);
- the source or account it was kept for was removed (`release`), which skips the wait for the days.
Never while an Undo may still point at it: a save recorded in the last `storage.kept_secrets.undo_grace_minutes` whose
earlier or later value names it keeps it, and a secret a setting refers to again (an Undo, or a reference typed in) is
kept for good. A secret marked to keep for ever (the backup key, which older backups need) is never removed.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine.state_file import changing, write_whole
from engine.yaml_load import load_yaml

log = logging.getLogger(__name__)

INDEX = "kept-secrets.json"


def _path(ws: Any) -> Path:
    return ws.private_dir / INDEX


def _load(ws: Any) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_path(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(ws: Any, data: dict[str, dict[str, Any]]) -> None:
    write_whole(_path(ws), json.dumps(data, indent=2, sort_keys=True) + "\n", mode=0o600)


def record(ws: Any, name: str, *, owner: str | None = None, forever: bool = False, now: datetime | None = None) -> None:
    """Note that a secret of this name was kept for something (`owner`, such as `source:<id>`), so it can be removed
    later. Keeping a name again starts it afresh; `forever` marks one that is never removed."""
    with changing(_path(ws)):
        index = _load(ws)
        entry: dict[str, Any] = {"kept_at": (now or datetime.now(UTC)).isoformat()}
        if owner:
            entry["owner"] = owner
        if forever:
            entry["forever"] = True
        index[name] = entry
        _save(ws, index)


def _kept_name(ws: Any, text: str) -> str | None:
    """The name of the kept secret a reference points at, when it is a file in this workspace's keys folder."""
    scheme, _, where = text.partition(":")
    if scheme != "file" or not where:
        return None
    try:
        path = Path(where).expanduser().resolve()
        return path.name if path.parent == (ws.private_dir / "keys").resolve() else None
    except OSError:
        return None


def _names_in(ws: Any, value: Any) -> set[str]:
    """Every kept secret named anywhere inside a value (a setting's value, a record's before and after)."""
    if isinstance(value, str):
        found = _kept_name(ws, value)
        return {found} if found else set()
    if isinstance(value, dict):
        return set().union(*(_names_in(ws, v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_names_in(ws, v) for v in value)) if value else set()
    return set()


def referenced(ws: Any, cfg: Any) -> set[str]:
    """The kept secrets a setting refers to now: the config files as they are, and the settings in use."""
    found: set[str] = set()
    folder = ws.config_dir
    files = [*sorted(folder.glob("*.yaml")), *sorted((folder / "plugins").glob("*.yaml"))]
    for path in files:
        try:
            found |= _names_in(ws, load_yaml(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    with contextlib.suppress(AttributeError, ValueError):
        found |= _names_in(ws, cfg.model_dump(mode="json"))
    return found


def pointed_at_recently(ws: Any, store: Any, now: datetime, minutes: int) -> set[str]:
    """The kept secrets that a save made in the last `minutes` minutes names, before or after: an Undo of that save
    would put one back."""
    since = now - timedelta(minutes=minutes)
    found: set[str] = set()
    for stored in store.read().list("setting_change"):
        data = stored.data
        try:
            at = datetime.fromisoformat(str(data.get("at")))
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        if at > since:
            found |= _names_in(ws, data.get("before")) | _names_in(ws, data.get("after"))
    return found


@dataclass
class Released:
    going: int = 0  # kept secrets that go with what was removed, now or once Undo has run out
    undo_minutes: int = 0


def release(
    ws: Any,
    store: Any,
    cfg: Any,
    *,
    owner: str | None = None,
    before: Any = None,
    now: datetime | None = None,
) -> Released:
    """A source or an account was removed: its kept secrets (the ones kept for `owner`, and the ones named in the value
    it had before) go as soon as no setting and no Undo refers to them, without the wait for days. Returns how many."""
    now = now or datetime.now(UTC)
    still = referenced(ws, cfg)
    with changing(_path(ws)):
        index = _load(ws)
        mine = {n for n, e in index.items() if owner and e.get("owner") == owner}
        mine |= _names_in(ws, before) & set(index)
        going = sorted(n for n in mine if n in index and n not in still and not index[n].get("forever"))
        for name in going:
            index[name]["released"] = True
        _save(ws, index)
    minutes = cfg.storage.kept_secrets.undo_grace_minutes
    sweep(ws, store, cfg, now)
    return Released(going=len(going), undo_minutes=minutes)


def sweep(ws: Any, store: Any, cfg: Any, now: datetime | None = None) -> list[str]:
    """Remove the kept secrets that are due (see the module's words); returns their names, sorted."""
    now = now or datetime.now(UTC)
    settings = cfg.storage.kept_secrets
    still = referenced(ws, cfg)
    removed: list[str] = []
    with changing(_path(ws)):
        index = _load(ws)
        if not index:
            return []
        recent: set[str] | None = None  # read only when something is unreferenced: it walks the settings history
        for name, entry in list(index.items()):
            path = ws.private_dir / "keys" / name
            if not path.exists():
                del index[name]
                continue
            if name in still:
                entry.pop("unreferenced_since", None)
                entry.pop("released", None)
                continue
            if entry.get("forever"):
                continue
            if recent is None:
                recent = pointed_at_recently(ws, store, now, settings.undo_grace_minutes)
            if name in recent:
                continue
            since = entry.setdefault("unreferenced_since", now.isoformat())
            waited = now - datetime.fromisoformat(since)
            if entry.get("released") or waited >= timedelta(days=settings.keep_days):
                try:
                    path.unlink()
                except OSError as err:
                    log.warning("A kept secret could not be removed: %s", err)
                    continue
                del index[name]
                removed.append(name)
        _save(ws, index)
    return sorted(removed)
