"""Sources a sign-in starts: once the person signs in, the core starts reading what the plugin declared for that
sign-in (the inbox, the main calendar), so signing in is the whole setup. Each sign-in's sources are added once, and
only where the workspace reads nothing with that connector yet; the person's later changes stand. Which sign-ins have
had theirs added is kept on this computer, beside the sign-ins themselves."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from engine import settings as config_screens
from engine.config import ConfigError, load_config
from engine.state_file import changing, write_whole

STATE = "sign-in-sources.json"


def _state_path(ws: Any) -> Path:
    return ws.private_dir / STATE


def _started(ws: Any) -> set[str]:
    try:
        return set(json.loads(_state_path(ws).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _remember(ws: Any, names: set[str]) -> None:
    """Add `names` to the sign-ins that have had their sources added. The file is read again under its lock, so
    sign-ins finishing at the same moment each stay recorded."""
    with changing(_state_path(ws)):
        write_whole(_state_path(ws), json.dumps(sorted(_started(ws) | names)))


def not_read(ws: Any, sign_in: Any) -> list[str]:
    """The labels of the sign-in's declared sources the workspace reads nothing with yet (none were added, or the
    person removed them), so the screens can offer to start them with one click."""
    try:
        current = load_config(ws.config_dir, env=dict(os.environ))
    except ConfigError:
        return []
    reading = {s.connector for s in current.watch.sources}
    return [s["label"] for s in sign_in.sources if s["connector"] not in reading]


def start_sources(ws: Any, cfg: Any, store: Any, sign_in: Any, *, again: bool = False) -> list[str]:
    """Add the sign-in's declared sources the workspace doesn't read yet: once per sign-in, or `again` when the
    person asks for them. Returns the labels added. Sign-ins finishing at the same moment are handled one after the
    other, so the check that a sign-in's sources were added and the adding itself never interleave."""
    with changing(_state_path(ws)):
        return _start_sources(ws, cfg, store, sign_in, again=again)


def _start_sources(ws: Any, cfg: Any, store: Any, sign_in: Any, *, again: bool) -> list[str]:
    started = _started(ws)
    if (sign_in.name in started and not again) or not sign_in.sources:
        return []
    try:
        current = load_config(ws.config_dir, env=dict(os.environ))
    except ConfigError:
        return []
    sources = [s.model_dump(mode="json") for s in current.watch.sources]
    connectors = {
        name: connector
        for registrar in store.plugins.registrars.values()
        for name, connector in registrar.connectors.items()
    }
    taken = {s["id"] for s in sources}
    added = []
    for wanted in sign_in.sources:
        connector = connectors.get(wanted["connector"])
        if connector is None or any(s["connector"] == wanted["connector"] for s in sources):
            continue
        base = re.sub(r"[^a-z0-9]+", "-", wanted["label"].lower()).strip("-")[:40] or "source"
        source_id = (
            base if base not in taken else next(f"{base}-{n}" for n in range(2, 999) if f"{base}-{n}" not in taken)
        )
        taken.add(source_id)
        settings = connector.settings.model_validate(wanted["settings"]).model_dump(mode="json", exclude_defaults=True)
        sources.append(
            {
                "id": source_id,
                "connector": wanted["connector"],
                "label": wanted["label"],
                "every_minutes": wanted["every_minutes"],
                # The first read is taken in quietly: recent mail and meetings, one total, one summary (design 6.32).
                "first_run": "intake",
                "settings": settings,
            }
        )
        added.append(wanted["label"])
    if added:
        config_screens.save(
            ws,
            cfg,
            store,
            changes={"watch.sources": sources},
            reset=[],
            read_fingerprint=config_screens.fingerprint(ws.config_dir),
            env=dict(os.environ),
            allow=("watch.sources",),
        )
    _remember(ws, {sign_in.name})
    return added


def start_signed_in(ws: Any, cfg: Any, store: Any) -> list[str]:
    """At start-up: sources for sign-ins already signed in before their plugin declared any (or before this app
    started them). Returns the labels added."""
    from engine.sign_in import kept

    added = []
    for registrar in store.plugins.registrars.values():
        if not store.plugins.active(registrar.name):
            continue
        for sign_in in registrar.sign_ins.values():
            if not sign_in.sources or sign_in.name in _started(ws):
                continue
            if kept(ws.root / ".cockpit" / "keys" / registrar.name, sign_in) is None:
                continue
            added += start_sources(ws, cfg, store, sign_in)
    return added
