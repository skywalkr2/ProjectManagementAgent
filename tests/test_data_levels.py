"""Sources and files carry their data level: from the hand-in's choice, from the watched source's setting (else its
kind's, else the default), or from the upload; the level on a source decides which accounts may see its text."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from engine.dispatcher import _data_level
from engine.files import add_file
from engine.intake import hand_in
from engine.watch import data_level_of, refresh
from tests.test_watch import make

ITEM = {"key": "n1", "title": "A note", "text": "A line."}


def watched_level(tmp_path, source, **watch):
    ws, cfg, store = make(tmp_path, [{"id": "s", "connector": "fake", "first_run": "all", **source}], **watch)
    try:
        result = refresh(ws, store, cfg, "s", datetime(2026, 10, 9, 9, 0, tzinfo=UTC))
        request = store.read().get("request", result.new[0])
        record = store.read().get("source", request.data["source"])
        return record.data["sensitivity"], _data_level(store, request.data)
    finally:
        store.close()


def test_a_hand_ins_choice_is_kept_on_its_source_and_decides_the_runs_level(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace
    from tests.conftest import DEMO_B

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    store = Store(ws.db_path)
    try:
        chosen = hand_in(ws, store, pasted="Some private text.", data_level="restricted")
        usual = hand_in(ws, store, pasted="Some other text.")
        assert store.read().get("source", chosen.source).data["sensitivity"] == "restricted"
        assert store.read().get("source", usual.source).data["sensitivity"] == "internal"
        # The level is read from the source, so it holds when the request carries no choice of its own.
        request = store.read().get("request", chosen.request).data | {"sensitivity": None}
        assert _data_level(store, request) == "restricted"
        assert _data_level(store, store.read().get("request", usual.request).data) == "internal"
    finally:
        store.close()


def test_a_watched_sources_level_is_its_own_setting_else_its_kinds_else_the_default(tmp_path):
    items = {"settings": {"items": [ITEM]}}
    assert watched_level(tmp_path / "a", items) == ("internal", "internal")
    assert watched_level(tmp_path / "b", items, default_data_level="restricted") == ("restricted", "restricted")
    kinds = {"connector_data_levels": {"fake": "open"}, "default_data_level": "restricted"}
    assert watched_level(tmp_path / "c", items, **kinds)[0] == "open"
    own = {**items, "data_level": "restricted"}
    assert watched_level(tmp_path / "d", own, connector_data_levels={"fake": "open"}) == ("restricted", "restricted")


def test_the_level_is_chosen_from_the_source_then_its_kind_then_the_default():
    class Source:
        def __init__(self, level):
            self.data_level, self.connector = level, "kind"

    class Watch:
        connector_data_levels = {"kind": "open"}
        default_data_level = "internal"

    class Cfg:
        watch = Watch()

    assert data_level_of(Cfg, Source("restricted")) == "restricted"
    assert data_level_of(Cfg, Source(None)) == "open"
    Cfg.watch.connector_data_levels = {}
    assert data_level_of(Cfg, Source(None)) == "internal"


@pytest.fixture
def env(workspace):
    from engine.storage import Store

    cfg = workspace.config(env={})
    store = Store(workspace.db_path, cfg=cfg)
    yield workspace, cfg, store
    store.close()


def test_a_file_carries_the_level_it_was_added_with(env):
    _, cfg, store = env
    plain = add_file(store, cfg, b"one", name="a.txt", media_type="text/plain")
    private = add_file(store, cfg, b"two", name="b.txt", media_type="text/plain", data_level="restricted")
    assert plain.data["sensitivity"] == "internal" and private.data["sensitivity"] == "restricted"


def test_an_upload_names_its_level_and_the_list_shows_it(env):
    from api.app import create_app

    ws, cfg, store = env
    store.close()
    client = TestClient(create_app(ws, cfg, "t", start_worker=False))
    client.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    text = {"Content-Type": "text/plain"}
    private = client.post(f"{api}/files?name=b.txt&data_level=restricted", content=b"two", headers=text)
    plain = client.post(f"{api}/files?name=a.txt", content=b"one", headers=text)
    assert private.json()["data_level"] == "restricted" and plain.json()["data_level"] == "internal"
    assert client.post(f"{api}/files?name=c.txt&data_level=secret", content=b"x", headers=text).status_code == 422


def test_a_watched_restricted_source_stops_for_the_person_when_no_account_may_see_it(tmp_path):
    from engine.ai.router import Router
    from engine.dispatcher import process

    ws, cfg, store = make(
        tmp_path,
        [
            {
                "id": "s",
                "connector": "fake",
                "first_run": "all",
                "data_level": "restricted",
                "settings": {"items": [ITEM]},
            }
        ],
    )
    try:
        for account in cfg.ai.providers.values():
            account.allowed_data = ["open", "internal"]
        result = refresh(ws, store, cfg, "s", datetime(2026, 10, 9, 9, 0, tzinfo=UTC))
        process(ws, store, cfg, Router(cfg, store, env={}), result.new[0], now=datetime(2026, 10, 9, 9, 1, tzinfo=UTC))
        request = store.read().get("request", result.new[0])
        assert request.data["state"] == "needs_you" and request.data["cause"]["kind"] == "data_level"
        assert request.data["cause"]["level"] == "restricted"
    finally:
        store.close()
