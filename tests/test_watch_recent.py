"""A recent first read (first_run: recent): the first read hands the assistant the last day's mail and the meetings
around now, and only notes the rest; the person can hand in the recent items later after a plain first read."""

from datetime import UTC, datetime, timedelta

import yaml

from engine.config import load_config
from tests.test_watch import make

PLUGIN = """
from datetime import UTC, datetime, timedelta
from engine.plugin_api import EventDetails, MessageDetails, Poll, Settings, SourceItem
from pydantic import BaseModel

class Config(Settings):
    pass

class BoxSettings(BaseModel):
    pass

def poll(settings, state, context):
    now = datetime.now(UTC)
    at = lambda hours: (now - timedelta(hours=hours)).isoformat()
    soon = (now + timedelta(hours=3)).isoformat()
    return Poll([
        SourceItem("m-new", "Proofs are ready", "Ready.", message=MessageDetails(sender="A", received=at(2))),
        SourceItem("m-old", "Old thread", "From last week.", message=MessageDetails(sender="B", received=at(120))),
        SourceItem("e-soon", "Printer call", "A call.", event=EventDetails(start=soon)),
        SourceItem("plain", "No time", "Nothing says when."),
    ])

def register(registrar):
    registrar.connector("p21/box", label="A box", settings=BoxSettings, poll=poll)
"""


def workspace(tmp_path, first_run):
    from engine.storage import Store

    ws, cfg, store = make(tmp_path, [{"id": "box", "connector": "p21/box", "first_run": first_run, "settings": {}}])
    store.close()
    folder = ws.root / "plugins" / "p21"
    folder.mkdir(parents=True)
    (folder / "fixture.py").write_text(PLUGIN)
    manifest = {
        "name": "p21",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Recent first read fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"connectors": ["p21/box"]},
    }
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p21"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p21"), store.plugins.status["p21"].reason
    return ws, cfg, store


def handed_titles(store):
    return sorted(s.data["title"] for s in store.read().list("source") if s.data.get("watched"))


def test_a_recent_first_read_hands_in_the_last_day_and_notes_the_rest(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = workspace(tmp_path, "recent")
    try:
        result = refresh(ws, store, cfg, "box")
        assert result.outcome == "baseline" and len(result.new) == 2
        assert handed_titles(store) == ["Printer call", "Proofs are ready"]
        assert len(store.read().find("snapshot", {"source": "box"})) == 4
    finally:
        store.close()


def test_after_a_plain_first_read_the_person_can_hand_in_the_recent_items_once(tmp_path):
    from engine.watch import hand_in_recent, refresh

    ws, cfg, store = workspace(tmp_path, "baseline")
    try:
        refresh(ws, store, cfg, "box")
        assert handed_titles(store) == []
        assert len(hand_in_recent(ws, store, cfg, "box")) == 2
        assert handed_titles(store) == ["Printer call", "Proofs are ready"]
        assert hand_in_recent(ws, store, cfg, "box") == []
    finally:
        store.close()


def test_recent_means_received_or_starting_near_now():
    from engine.watch import is_recent

    now = datetime(2026, 10, 12, 12, tzinfo=UTC)
    day = timedelta(hours=24)
    assert is_recent({"message": {"received": "2026-10-12T02:00:00Z"}}, None, now, day)
    assert not is_recent({"message": {"received": "2026-10-09T02:00:00Z"}}, None, now, day)
    assert is_recent({"event": {"start": "2026-10-13", "all_day": True}}, None, now, day)
    assert not is_recent({"event": {"start": "2026-10-20T09:00:00Z"}}, None, now, day)
    assert not is_recent({}, None, now, day)
