"""Notices that something needs the person (design 7.19): sent outward, to the person only, and only for what Today's
Decide group holds, so the notice and the screen never disagree.

A notice carries a count, never what an item is about: a chat app or a push service is a third party. The wording comes
from `ui.notifications`. The targets are the browser (shown by the open screen, which asks for the count here) and a
webhook, the person's own address kept as a secret reference like a key. Mail to the person themselves comes with the
mail channel and is not here.

What is sent and when: when an item enters the Decide group that has not been told about yet, one notice with how many
wait now. Nothing is sent in quiet hours; what came up then goes out once, when they end. A notice that could not be
delivered is tried again after `retry_minutes`, and the screen says so. What was told is kept in the workspace's private
folder, so a restart never repeats a notice.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

from engine.connectors import ConnectorError
from engine.net import LOCAL, WebClient
from engine.reminders import QuietHours, in_quiet_hours
from engine.secrets import SecretError, resolve_secret
from engine.state_file import write_whole

log = logging.getLogger(__name__)

STATE_FILE = "notified.json"
#: Where each kind of failure sends the person, in plain words for the screen.
_PROBLEMS = {
    "auth": "The address didn't accept the note. Check that it is still the right one.",
    "no_access": "The address wasn't reached. It has to be an https address, one that is still working.",
    "not_found": "The address doesn't exist any more. Give it again from the chat app or the push service.",
    "throttled": "The address asked to slow down. It is tried again by itself.",
    "outage": "The address didn't answer. It is tried again by itself.",
    "offline": "No connection to the address. It is tried again by itself.",
}
_OTHER_PROBLEM = "The note could not be sent. It is tried again by itself."


@dataclass(frozen=True)
class Waiting:
    """What Today's Decide group holds now: a stable key for each item, and the notice that counts them."""

    keys: list[str]
    message: str

    @property
    def count(self) -> int:
        return len(self.keys)


@dataclass(frozen=True)
class Sent:
    ok: bool
    problem: str | None = None


def decide_keys(ws: Any, store: Any, cfg: Any, now: datetime, handover: tuple[str, str] | None = None) -> list[str]:
    """A key for each item in Today's Decide group: the core's own lines and the lines add-ons put there."""
    from engine.today_queue import queue

    keys = [line.key for line in queue(ws, store, cfg, now, handover=handover) if line.group == "decide"]
    for plugin, line in store.plugins.today():
        if line.group == "decide":
            keys.append(f"plugin:{plugin}:{line.id}")
    return keys


def message_for(cfg: Any, count: int) -> str:
    """The notice for this many items: a count and the action, never what they are about."""
    n = cfg.ui.notifications
    return n.message_one if count == 1 else n.message_many.format(count=count)


def test_message(cfg: Any) -> str:
    return cfg.ui.notifications.test_message.format(count=0)


def quiet_now(cfg: Any, now: datetime) -> bool:
    """Whether the person's own clock is inside the notices' quiet hours."""
    from engine.today import zone

    q = cfg.ui.notifications.quiet_hours
    return in_quiet_hours(now.astimezone(zone(cfg)), QuietHours(time.fromisoformat(q.start), time.fromisoformat(q.end)))


# ---- what was told -------------------------------------------------------------------------------


def _state(ws: Any) -> dict[str, Any]:
    try:
        data = json.loads((ws.private_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(ws: Any, data: dict[str, Any]) -> None:
    write_whole(ws.private_dir / STATE_FILE, json.dumps(data, indent=2) + "\n")


def last_problem(ws: Any) -> str | None:
    """Why the last notice didn't arrive, when it didn't; cleared by the next one that did."""
    problem = _state(ws).get("problem")
    return problem if isinstance(problem, str) and problem else None


# ---- sending -------------------------------------------------------------------------------------


def _address(cfg: Any, env: Any = None) -> str | None:
    """The person's own address for notices, read from where it is kept; None when none is set."""
    ref = cfg.ui.notifications.webhook
    if not ref:
        return None
    try:
        return resolve_secret(ref, env)
    except SecretError:
        return None


def _post(cfg: Any, address: str, text: str, *, env: Any = None) -> Sent:
    """One note to the address, which is the only host reached. A hosted app never reaches this computer's own
    addresses."""
    parts = urlsplit(address)
    host = (parts.hostname or "").lower()
    if not host or parts.scheme not in ("https", "http"):
        return Sent(False, _PROBLEMS["no_access"])
    if cfg.server.mode != "local" and host in LOCAL:
        return Sent(False, _PROBLEMS["no_access"])
    plain = cfg.ui.notifications.webhook_format == "plain"
    if plain:
        content, kind = text.encode("utf-8"), "text/plain; charset=utf-8"
    else:
        # The text under the names chat apps read it from.
        content, kind = json.dumps({"text": text, "content": text}).encode("utf-8"), "application/json"
    try:
        response = WebClient([host]).request("POST", address, content=content, headers={"Content-Type": kind})
    except ConnectorError as err:
        return Sent(False, _PROBLEMS.get(err.kind, _OTHER_PROBLEM))
    if response.status >= 400:
        return Sent(False, _PROBLEMS["auth"] if response.status in (401, 403) else _OTHER_PROBLEM)
    return Sent(True)


def send_test(ws: Any, cfg: Any, *, env: Any = None) -> Sent:
    """ "Send me a test" for the webhook: the test note to the person's own address."""
    address = _address(cfg, env)
    if address is None:
        return Sent(False, "There is no address to send to yet. Give one first.")
    result = _post(cfg, address, test_message(cfg), env=env)
    state = _state(ws)
    _record(state, result)
    _save(ws, state)
    return result


def _record(state: dict[str, Any], result: Sent) -> None:
    if result.ok:
        state.pop("problem", None)
    else:
        state["problem"] = result.problem


def deliver_if_due(
    ws: Any,
    store: Any,
    cfg: Any,
    now: datetime,
    handover: tuple[str, str] | None = None,
    *,
    env: Any = None,
) -> Sent | None:
    """Send the notice when an item has come into Today's Decide group that the person has not been told about. Returns
    what was sent, or None when nothing was due (off, no address, nothing new, quiet hours, or waiting to try again)."""
    n = cfg.ui.notifications
    if not n.enabled or not n.webhook:
        return None
    state = _state(ws)
    keys = decide_keys(ws, store, cfg, now, handover)
    told = [k for k in state.get("told", []) if k in keys]
    if not keys:
        if state.get("told"):
            _save(ws, {**state, "told": []})
        return None
    if all(k in told for k in keys):
        if told != state.get("told"):
            _save(ws, {**state, "told": told})
        return None
    if quiet_now(cfg, now):
        return None
    failed_at = state.get("failed_at")
    if failed_at and now - datetime.fromisoformat(failed_at) < timedelta(minutes=n.retry_minutes):
        return None
    address = _address(cfg, env)
    if address is None:
        return None
    result = _post(cfg, address, message_for(cfg, len(keys)), env=env)
    if result.ok:
        state.update(told=keys, sent_at=now.isoformat())
        state.pop("failed_at", None)
    else:
        state.update(failed_at=now.isoformat())
        log.warning("A notice could not be delivered.")
    _record(state, result)
    _save(ws, state)
    return result


def waiting(ws: Any, store: Any, cfg: Any, now: datetime, handover: tuple[str, str] | None = None) -> Waiting:
    """What the open screen shows a notice for."""
    keys = decide_keys(ws, store, cfg, now, handover)
    return Waiting(keys=keys, message=message_for(cfg, len(keys)) if keys else "")
