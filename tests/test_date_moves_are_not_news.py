"""A date move isn't news (roadmap B-6a; the designer's answer F17): the history readers see leaves out a change that
only moves a date on an existing item (the same text, a new due or start date), and keeps everything else: new, closed
and blocked items, status, scope, risks, decisions and a date move that came with any other change. The ledger keeps
every row. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.history import changes_for_readers, date_fields, for_readers, is_date_move
from engine.plugin_api import ReadView
from engine.records import Action, CalendarEntry, Project
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "date-move-token"
_PM = WriteContext("pm", "trusted", "test")
FIRST = next(a for a in fixture_records(DEMO_B, "action") if a.get("due") and a.get("owners"))
ACTION, ACTION_TEXT = FIRST["id"], FIRST["text"]


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


def _update(store, kind, record_id, **changes):
    rec = store.read().get(kind, record_id)
    with store.transaction() as tx:
        tx.update(kind, record_id, changes, _PM, read_version=rec.version)


def _later(store, days):
    due = store.read().get("action", ACTION).data["due"]
    return (date.fromisoformat(str(due)) + timedelta(days=days)).isoformat()


def _fields(rows):
    return [(r["version"], r["field"]) for r in rows]


def test_dates_are_found_by_type_and_a_calendar_entrys_start_and_end_count_too():
    assert "due" in date_fields(Action) and "target" in date_fields(Project) and "text" not in date_fields(Action)
    assert {"start", "end"} <= date_fields(CalendarEntry) and "title" not in date_fields(CalendarEntry)


def test_a_change_of_only_the_due_date_of_an_existing_item_is_a_date_move_and_is_left_out(env):
    _, cfg, store = env
    _update(store, "action", ACTION, due=_later(store, 3))
    rows = store.read().ledger(kind="action", record_id=ACTION)
    assert any(r["field"] == "due" for r in rows)
    readers = changes_for_readers(store.read(), "action", ACTION)
    assert [r for r in readers if r["field"] == "due" and r["version"] > 1] == []
    assert any(r["version"] == 1 for r in readers), "the item's creation is still there"
    assert len(store.read().ledger(kind="action", record_id=ACTION)) == len(rows), "the ledger keeps every row"


def test_the_words_that_come_with_a_date_are_part_of_the_move(env):
    _, cfg, store = env
    _update(store, "action", ACTION, due=_later(store, 2), due_words="by the 9th", due_check=True)
    assert [r for r in changes_for_readers(store.read(), "action", ACTION) if r["version"] > 1] == []


@pytest.mark.parametrize(
    "extra",
    [{"text": f"{ACTION_TEXT} by courier"}, {"on_hold": {"waiting_for": "x", "since": "2026-10-01"}}],
)
def test_a_date_move_together_with_any_other_change_shows_in_full(env, extra):
    _, cfg, store = env
    _update(store, "action", ACTION, due=_later(store, 4), **extra)
    shown = {r["field"] for r in changes_for_readers(store.read(), "action", ACTION)}
    assert {"due", *extra} <= shown


def test_the_text_changing_in_its_own_change_shows_and_the_date_move_beside_it_does_not(env):
    _, cfg, store = env
    _update(store, "action", ACTION, due=_later(store, 1))
    _update(store, "action", ACTION, text=f"{ACTION_TEXT} and the cover")
    shown = [r["field"] for r in changes_for_readers(store.read(), "action", ACTION) if r["version"] > 1]
    assert shown == ["text"]


def test_a_first_date_an_removed_date_new_items_closed_items_and_status_are_news(env):
    _, cfg, store = env
    undated = next(a.id for a in store.read().list("action") if not a.data.get("due") and a.data["status"] == "open")
    _update(store, "action", undated, due="2026-12-01")  # a date where there was none
    _update(store, "action", ACTION, due=None)  # a date taken away
    _update(store, "action", ACTION, status="dropped", dropped_reason="No longer needed")
    project = fixture_records(DEMO_B, "project")[0]["id"]
    _update(store, "project", project, status="At risk")
    view = store.read()
    assert [r["field"] for r in changes_for_readers(view, "action", undated) if r["version"] > 1] == ["due"]
    assert {"due", "status"} <= {r["field"] for r in changes_for_readers(view, "action", ACTION) if r["version"] > 1}
    assert "status" in {r["field"] for r in changes_for_readers(view, "project", project)}


def test_a_calendar_entry_moved_to_a_new_start_is_a_date_move(env):
    _, cfg, store = env
    with store.transaction() as tx:
        entry = tx.create("event", {"title": "Print sync", "start": "2026-10-20", "trust": "trusted"}, _PM).id
    _update(store, "event", entry, start="2026-10-22")
    assert [r["field"] for r in changes_for_readers(store.read(), "event", entry) if r["version"] > 1] == []
    _update(store, "event", entry, title="Print and cover sync", start="2026-10-23")
    after = {r["field"] for r in changes_for_readers(store.read(), "event", entry) if r["version"] > 1}
    assert {"title", "start"} <= after


def test_the_rule_is_one_function_over_rows_and_leaves_rows_without_a_field_alone():
    rows = [
        {"version": 1, "field": None, "before": None, "after": None, "op": "create"},
        {"version": 2, "field": "due", "before": "2026-10-01", "after": "2026-10-05", "op": "x"},
        {"version": 3, "field": "text", "before": "a", "after": "b", "op": "x"},
        {"version": 3, "field": "due", "before": "2026-10-05", "after": "2026-10-06", "op": "x"},
    ]
    assert is_date_move([r for r in rows if r["version"] == 2], Action)
    assert not is_date_move([r for r in rows if r["version"] == 3], Action)
    assert not is_date_move([rows[0]], Action)
    assert [r["version"] for r in for_readers(rows, Action)] == [1, 3, 3]


def test_a_records_activity_leaves_out_a_pure_date_move_and_keeps_the_rest(api):
    client, base, store, cfg = api
    _update(store, "action", ACTION, due=_later(store, 5))
    quiet = client.get(f"{base}/record-pages/{ACTION}", params={"kind": "action"}).json()["activity"]
    assert all(e["field"] != "due" for e in quiet)
    _update(store, "action", ACTION, text=f"{ACTION_TEXT} today")
    loud = client.get(f"{base}/record-pages/{ACTION}", params={"kind": "action"}).json()["activity"]
    assert any(e["field"] == "text" for e in loud) and all(e["field"] != "due" for e in loud)
    assert any(r["field"] == "due" for r in store.read().ledger(kind="action", record_id=ACTION))


def test_a_plugin_reads_the_same_filtered_history_through_its_read_view(env):
    _, cfg, store = env
    _update(store, "action", ACTION, due=_later(store, 6))
    _update(store, "action", ACTION, text=f"{ACTION_TEXT} again")
    view = ReadView(store.read(), "demo")
    found = view.changes("action", ACTION)
    assert [c.field for c in found if c.version > 1] == ["text"]
    assert found[0].at and found[-1].before == ACTION_TEXT
    assert view.changes("action", "ACT-999") == []


def test_the_plugin_api_names_this_version_and_the_guide_lists_the_history_reader():
    from pathlib import Path

    from engine.plugin_api import PLUGIN_API_VERSION

    assert tuple(int(n) for n in PLUGIN_API_VERSION.split(".")) >= (0, 3, 83)
    guide = (Path(__file__).parent.parent / "docs" / "plugin-guide.md").read_text(encoding="utf-8")
    assert "view.changes(" in guide and "### Change" in guide
