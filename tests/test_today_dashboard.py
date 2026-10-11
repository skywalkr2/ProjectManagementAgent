"""Today's agenda and what came in: calendar and mail connectors say what an item is, the watcher keeps it on the
snapshot, and Today lists the day's events and the latest messages, leaving out what a triage rule closed."""

from datetime import UTC, datetime, timedelta

import pytest
import yaml

from engine.config import load_config
from engine.connectors import EventDetails, MessageDetails, Poll, SourceItem, checked_poll
from tests.conftest import DEMO_B
from tests.test_watch import NOW, reread

ZONE = "Europe/Lisbon"


def make(tmp_path, items, **watch):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    source = {"id": "s", "connector": "fake", "label": "Board", "first_run": "all", "settings": {"items": items}}
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [source], **watch}))
    workspace = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    workspace.setdefault("user", {})["timezone"] = ZONE
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(workspace))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def event(key, start, end=None, **more):
    return {
        "key": key,
        "title": f"Event {key}",
        "text": f"{key} at {start}",
        "event": {"start": start, "end": end, **more},
    }


def message(key, received, **more):
    return {"key": key, "title": f"Mail {key}", "text": f"{key} body", "message": {"received": received, **more}}


def test_details_must_be_readable_times():
    def poll(**details):
        return Poll([SourceItem("k", "t", "x", **details)])

    checked_poll(poll(event=EventDetails("2030-03-04T09:00:00+00:00", "2030-03-04T10:00:00Z")))
    checked_poll(poll(event=EventDetails("2030-03-04", "2030-03-05", all_day=True)))
    checked_poll(poll(message=MessageDetails("someone", "2030-03-04T08:00:00+01:00")))
    for bad in (
        {"event": EventDetails("2030-03-04T09:00:00")},  # no offset
        {"event": EventDetails("2030-03-04T10:00:00Z", "2030-03-04T09:00:00Z")},  # ends before it starts
        {"event": EventDetails("tomorrow")},
        {"message": MessageDetails("someone", "yesterday")},
        {"event": EventDetails("2030-03-04", all_day=True), "message": MessageDetails()},
    ):
        with pytest.raises(ValueError):
            checked_poll(poll(**bad))


def test_the_agenda_lists_today_and_the_days_after_in_the_persons_zone(tmp_path):
    from engine.today import agenda
    from engine.watch import refresh

    items = [
        event("late", "2030-03-04T23:30:00+00:00", "2030-03-05T00:30:00+00:00"),  # Lisbon is UTC here
        event("early", "2030-03-04T08:00:00+00:00", "2030-03-04T09:00:00+00:00", where="Room 2"),
        event("all", "2030-03-04", "2030-03-06", all_day=True),
        event("called-off", "2030-03-04T12:00:00+00:00", cancelled=True),
        event("yesterday", "2030-03-03T10:00:00+00:00", "2030-03-03T11:00:00+00:00"),
        event("far", "2030-03-09T10:00:00+00:00"),
        {"key": "plain", "title": "Plain", "text": "no details"},
    ]
    ws, cfg, store = make(tmp_path, items)
    try:
        refresh(ws, store, cfg, "s", NOW)
        found = agenda(store, cfg, NOW)
        days = cfg.ui.today.agenda_days_ahead
        assert days >= 1
        assert [a.title for a in found if a.days[0] == NOW.date()] == [
            "Event all",
            "Event early",
            "Event called-off",
            "Event late",
        ]
        by_title = {a.title: a for a in found}
        assert by_title["Event early"].where == "Room 2" and by_title["Event called-off"].cancelled
        assert by_title["Event late"].days == [NOW.date(), NOW.date() + timedelta(days=1)]
        assert by_title["Event all"].days == [NOW.date(), NOW.date() + timedelta(days=1)]
        assert "Event yesterday" not in by_title and "Event far" not in by_title and "Plain" not in by_title
    finally:
        store.close()


def test_what_came_in_is_newest_first_without_what_a_rule_closed(tmp_path):
    from engine.today import arrived
    from engine.watch import refresh

    hour = timedelta(hours=1)
    items = [
        message("old", (NOW - 30 * hour).isoformat(), sender="A"),
        message("recent", (NOW - 2 * hour).isoformat(), sender="B", unread=True),
        message("newest", (NOW - hour).isoformat(), sender="C"),
        {**message("list", (NOW - hour).isoformat(), sender="D"), "text": "the newsletter"},
    ]
    rules = [{"name": "Letters", "kind": "name-matches", "params": {"patterns": ["list"]}}]
    ws, cfg, store = make(tmp_path, items, triage=rules)
    try:
        refresh(ws, store, cfg, "s", NOW)
        inbox = arrived(store, cfg, NOW)
        assert [a.title for a in inbox.items] == ["Mail newest", "Mail recent"]
        assert inbox.items[1].unread is True and inbox.items[0].sender == "C" and inbox.left_out == 1
        # Opening a message changes what it is, not its text: kept, and nothing handed in again.
        opened = [{**items[1], "message": {**items[1]["message"], "unread": False}}, *items[2:3]]
        cfg, store, again = reread(tmp_path, ws, store, opened)
        assert again.new == [] and again.changed == []
        assert next(a for a in arrived(store, cfg, NOW).items if a.title == "Mail recent").unread is False
    finally:
        store.close()


def test_the_routes_answer_for_the_screens(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine.watch import refresh

    now = datetime.now(UTC).replace(microsecond=0)
    items = [
        event("soon", (now + timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=2)).isoformat()),
        message("hi", (now - timedelta(minutes=5)).isoformat(), sender="E"),
    ]
    ws, cfg, store = make(tmp_path, items)
    refresh(ws, store, cfg, "s", now)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    assert [a["title"] for a in c.get(f"{api}/today/agenda").json()] == ["Event soon"]
    inbox = c.get(f"{api}/today/arrived").json()
    assert [a["sender"] for a in inbox["items"]] == ["E"] and inbox["left_out"] == 0


def test_the_persons_own_open_actions_come_overdue_first(tmp_path):
    from engine.today import todo

    ws, cfg, store = make(tmp_path, [])
    try:
        me = cfg.workspace.user.person
        assert me
        mine = [
            a
            for a in store.read().list("action")
            if a.data["status"] == "open" and any(o["person"] == me for o in a.data["owners"])
        ]
        found = todo(store, cfg, NOW)
        assert {t.action for t in found} == {a.id for a in mine}
        dated = [t.due for t in found if t.due is not None]
        assert dated == sorted(dated) and all(t.due is None for t in found[len(dated) :])
        assert all(t.overdue == (t.due is not None and t.due < NOW.date()) for t in found)
    finally:
        store.close()
