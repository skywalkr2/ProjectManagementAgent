"""A second move of the same date is shown to the person (design 6.33; the functional designer's answer F17, B-7).

One date move stays out of what a record's history shows (it isn't news). A second move of the same date within
`steward.second_move_days` shows in the person's own history, worded neutrally ("moved again (second time since Oct
6)"), never in what readers see (a plugin's view, a published page) or in anything drafted for others (a packet, a
copied message), and never worded as slipping. Names and ids come from the fixtures and the settings."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.history import changes_for_person, changes_for_readers
from engine.plugin_api import ReadView
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "second-move-token"
_PM = WriteContext("pm", "trusted", "test")
FIRST = next(a for a in fixture_records(DEMO_B, "action") if a.get("due") and a.get("owners"))
ACTION, ACTION_TEXT = FIRST["id"], FIRST["text"]
START = date(2026, 10, 6)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.store, cfg


def move(store, days_after_start: int, step: int) -> None:
    """Move the action's due date by `step` days, on the day `days_after_start` after the first move's day."""
    store.clock = lambda: f"{START + timedelta(days=days_after_start)}T09:00:00+00:00"
    rec = store.read().get("action", ACTION)
    new = (date.fromisoformat(str(rec.data["due"])) + timedelta(days=step)).isoformat()
    with store.transaction() as tx:
        tx.update("action", ACTION, {"due": new}, _PM, read_version=rec.version)


def shown(store, window=14):
    return [r for r in changes_for_person(store.read(), "action", ACTION, window) if r["version"] > 1]


def test_one_move_is_not_shown_and_a_second_within_the_window_is_shown_as_moved_again(env):
    _, cfg, store = env
    move(store, 0, 3)
    assert shown(store) == []
    move(store, 6, 2)
    (again,) = shown(store)
    assert again["field"] == "due" and again["moved_again"] == 2 and again["moved_since"] == START.isoformat()


def test_a_third_move_counts_from_the_first_of_the_run(env):
    _, cfg, store = env
    move(store, 0, 3)
    move(store, 5, 1)
    move(store, 11, 1)
    found = shown(store)
    assert [(r["moved_again"], r["moved_since"]) for r in found] == [(2, START.isoformat()), (3, START.isoformat())]


def test_a_second_move_after_the_window_starts_over_and_is_not_shown(env):
    _, cfg, store = env
    move(store, 0, 3)
    move(store, 15, 2)
    assert shown(store) == []
    assert shown(store, 30) != []  # the window is a setting


def test_a_move_beside_any_other_change_is_shown_in_full_and_is_not_a_second_move(env):
    _, cfg, store = env
    move(store, 0, 3)
    store.clock = lambda: f"{START + timedelta(days=2)}T09:00:00+00:00"
    rec = store.read().get("action", ACTION)
    due = (date.fromisoformat(str(rec.data["due"])) + timedelta(days=1)).isoformat()
    with store.transaction() as tx:
        tx.update("action", ACTION, {"due": due, "text": f"{ACTION_TEXT} and more"}, _PM, read_version=rec.version)
    found = shown(store)
    assert {r["field"] for r in found} == {"due", "text"} and all("moved_again" not in r for r in found)


def test_what_readers_see_never_carries_a_second_move(env):
    _, cfg, store = env
    move(store, 0, 3)
    move(store, 6, 2)
    assert [r for r in changes_for_readers(store.read(), "action", ACTION) if r["version"] > 1] == []
    assert [c for c in ReadView(store.read(), "demo").changes("action", ACTION) if c.version > 1] == []


def test_nothing_drafted_for_others_says_a_date_moved_again(env):
    from engine.followups import sections
    from engine.names import People
    from engine.packet import _open_actions

    _, cfg, store = env
    move(store, 0, 3)
    move(store, 6, 2)
    listing = _open_actions(store, People(store, cfg))
    drafted = " ".join(s.message + (s.nudge.text if s.nudge else "") for s in sections(store, cfg, START))
    for text in (listing, drafted):
        assert "moved again" not in text.lower() and "slipped" not in text.lower()


def test_the_persons_own_record_page_says_moved_again_with_its_count_and_first_day(api):
    client, base, store, cfg = api
    move(store, 0, 3)
    quiet = client.get(f"{base}/record-pages/{ACTION}", params={"kind": "action"}).json()["activity"]
    assert all(e["field"] != "due" for e in quiet)
    move(store, 6, 2)
    loud = client.get(f"{base}/record-pages/{ACTION}", params={"kind": "action"}).json()["activity"]
    (again,) = [e for e in loud if e["field"] == "due"]
    assert (again["moved_again"], again["moved_since"]) == (2, START.isoformat())


def test_the_window_is_a_setting_with_a_description_and_demo_values(tmp_path):
    import yaml

    from engine.config.schema import StewardFile

    assert StewardFile.model_fields["second_move_days"].description
    for template in (DEMO_B,):
        assert "second_move_days" in yaml.safe_load((template / "config" / "steward.yaml").read_text())
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    assert ws.config(env={"COCKPIT__STEWARD__SECOND_MOVE_DAYS": "3"}).steward.second_move_days == 3


def test_no_wording_calls_a_move_slipping():
    import json
    from pathlib import Path

    words = json.loads((Path(__file__).parent.parent / "web" / "src" / "wording" / "en.json").read_text())
    assert "slip" not in " ".join(words.values()).lower()
    assert words["record.activity.moved_again"].startswith("moved again")
    assert words["record.activity.time.second"] == "second time"
