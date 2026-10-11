"""Watchers (design 6.4): a source is read through its connector, compared with what was seen, and each real
difference is handed in as outside content; a first read only notes what is there; failures ask once; plugins add
connectors."""

from datetime import UTC, datetime, timedelta

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)


def make(tmp_path, sources, **watch):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": sources, **watch}))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def folder_source(tmp_path):
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "plan.md").write_text("Line one\nLine two\n")
    ws, cfg, store = make(
        tmp_path,
        [{"id": "shared", "connector": "folder", "label": "Shared notes", "settings": {"path": str(folder)}}],
    )
    yield ws, cfg, store, folder
    store.close()


def source_text(ws, store, request_id):
    request = store.read().get("request", request_id)
    source = store.read().get("source", request.data["source"])
    return source, (ws.sources_dir / f"{source.data['content_hash']}.txt").read_text()


def test_the_first_read_only_notes_what_is_there(folder_source):
    from engine.watch import refresh

    ws, cfg, store, _ = folder_source
    result = refresh(ws, store, cfg, "shared", NOW)
    assert result.outcome == "baseline" and result.new == []
    assert [s.data["key"] for s in store.read().find("snapshot", {"source": "shared"})] == ["plan.md"]
    assert not [r for r in store.read().list("request") if r.data.get("origin") == "input"]


def test_new_changed_and_gone_items_are_handed_in_as_outside_content(folder_source):
    from engine.watch import refresh

    ws, cfg, store, folder = folder_source
    refresh(ws, store, cfg, "shared", NOW)
    (folder / "plan.md").write_text("Line one\nLine two, revised\n")
    (folder / "extra.txt").write_text("A new note")
    result = refresh(ws, store, cfg, "shared", NOW + timedelta(hours=1))
    assert len(result.new) == 1 and len(result.changed) == 1
    source, text = source_text(ws, store, result.changed[0])
    assert source.data["trust"] == "untrusted" and source.data["watched"]["change"] == "changed"
    assert "-Line two" in text and "+Line two, revised" in text and "It now reads:" in text
    request = store.read().get("request", result.new[0])
    assert request.data["origin"] == "input" and request.data["state"] == "queued"
    assert source_text(ws, store, result.new[0])[1].startswith("New in Shared notes: extra.txt")
    (folder / "extra.txt").unlink()
    gone = refresh(ws, store, cfg, "shared", NOW + timedelta(hours=2))
    assert len(gone.removed) == 1 and "no longer in Shared notes" in source_text(ws, store, gone.removed[0])[1]
    assert refresh(ws, store, cfg, "shared", NOW + timedelta(hours=3)).new == []


def test_first_run_all_hands_in_everything(tmp_path):
    from engine.watch import refresh

    items = [{"key": "a", "title": "A", "text": "first"}, {"key": "b", "title": "B", "text": "second"}]
    ws, cfg, store = make(
        tmp_path, [{"id": "s", "connector": "fake", "first_run": "all", "settings": {"items": items}}]
    )
    try:
        assert len(refresh(ws, store, cfg, "s", NOW).new) == 2
    finally:
        store.close()


def test_failures_ask_once_and_a_good_read_ends_the_question(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [{"id": "s", "connector": "fake", "label": "Board", "settings": {"error": "auth"}}],
        failures_before_asking=2,
    )
    try:
        pm = cfg.workspace.user.person
        assert pm, "the demo workspace names the PM"
        first = refresh(ws, store, cfg, "s", NOW)
        assert first.outcome == "failed" and "Sign in" in first.problem
        refresh(ws, store, cfg, "s", NOW + timedelta(hours=1))
        refresh(ws, store, cfg, "s", NOW + timedelta(hours=2))
        asked = [q for q in store.read().list("question") if (q.data.get("resolves") or {}).get("kind") == "watch"]
        assert len(asked) == 1 and asked[0].data["title"] == "Board can't be read"
        store.close()
        (ws.config_dir / "watch.yaml").write_text(
            yaml.safe_dump({"version": 1, "sources": [{"id": "s", "connector": "fake", "label": "Board"}]})
        )
        from engine.storage import Store

        cfg = load_config(ws.config_dir, env={})
        store = Store(ws.db_path, cfg=cfg)
        assert refresh(ws, store, cfg, "s", NOW + timedelta(hours=3)).outcome == "baseline"
        assert store.read().get("question", asked[0].id).data["status"] == "dropped"
    finally:
        store.close()


def test_no_network_is_not_a_failure(tmp_path):
    from engine.watch import failures_in_a_row, refresh

    ws, cfg, store = make(tmp_path, [{"id": "s", "connector": "fake", "settings": {"error": "offline"}}])
    try:
        assert refresh(ws, store, cfg, "s", NOW).outcome == "offline"
        assert failures_in_a_row(store, "s") == 0
    finally:
        store.close()


def test_bad_settings_and_unknown_connectors_fail_with_the_reason(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [
            {"id": "bad", "connector": "folder", "settings": {"nothing": 1}},
            {"id": "none", "connector": "nobody/here"},
        ],
    )
    try:
        assert "settings don't fit" in refresh(ws, store, cfg, "bad", NOW).problem
        assert "no running connector" in refresh(ws, store, cfg, "none", NOW).problem
    finally:
        store.close()


PLUGIN = """
from typing import ClassVar
from pydantic import BaseModel
from engine.plugin_api import Poll, Settings, SourceItem

class Config(Settings):
    pass

class BoardSettings(BaseModel):
    board: str
    crash: bool = False

def poll(settings, state, context):
    if settings.crash:
        raise RuntimeError("broken")
    return Poll([SourceItem("card-1", "Card one", "Board " + settings.board)], {"seen": 1})

def register(registrar):
    registrar.connector("p19/board", label="A board", settings=BoardSettings, poll=poll)
"""


def plugin_workspace(tmp_path, crash=False):
    from engine.storage import Store

    ws, cfg, store = make(
        tmp_path,
        [{"id": "b", "connector": "p19/board", "first_run": "all", "settings": {"board": "x", "crash": crash}}],
    )
    store.close()
    folder = ws.root / "plugins" / "p19"
    folder.mkdir(parents=True)
    (folder / "fixture.py").write_text(PLUGIN)
    manifest = {
        "name": "p19",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Connector fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"connectors": ["p19/board"]},
    }
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p19"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p19"), store.plugins.status["p19"].reason
    return ws, cfg, store


def test_a_plugin_adds_a_connector(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = plugin_workspace(tmp_path)
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert len(result.new) == 1 and "Board x" in source_text(ws, store, result.new[0])[1]
        assert store.read().find("watch_run", {"source": "b"})[-1].data["state"] == {"seen": 1}
    finally:
        store.close()


def test_a_crashing_connector_is_contained(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = plugin_workspace(tmp_path, crash=True)
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert result.outcome == "failed" and store.plugins.active("p19")
        assert "connector p19/board failed" in store.plugins.status["p19"].notes[-1]
    finally:
        store.close()


def test_the_worker_reads_due_sources_and_the_route_shows_them(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app

    items = [{"key": "a", "title": "A", "text": "first"}]
    ws, cfg, store = make(tmp_path, [{"id": "s", "connector": "fake", "label": "Board", "settings": {"items": items}}])
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    assert app.state.worker.run_due_watches() == 1 and app.state.worker.run_due_watches() == 0
    listed = c.get(f"{api}/watch").json()
    assert listed[0]["label"] == "Board" and listed[0]["last"]["outcome"] == "baseline" and listed[0]["items"] == 1
    assert c.post(f"{api}/watch/s/read").json()["last"]["outcome"] == "ok"
    assert c.post(f"{api}/watch/nothing/read").status_code == 404
