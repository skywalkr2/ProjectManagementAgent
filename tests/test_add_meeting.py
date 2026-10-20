"""A meeting added in one line (design 6.7, 7.7; roadmap B-6b): what and when, from the agenda. It is the person's own
calendar entry (`event.add`, with Undo), and one that is already there (the same meeting, at the same time, in the
person's own entries or in a connected calendar) is merged into, never added twice. Rules decide this, with no AI run.
Names come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import add_meeting
from engine.applier import undo
from engine.storage import Store, StoreError, WriteContext
from engine.today import agenda
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
_PM = WriteContext("pm", "trusted", "test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def entries(store) -> list:
    return [e for e in store.read().list("event") if not e.data.get("key")]


def connected(store, title="Print sync", start="2026-10-16T15:00:00+00:00"):
    with store.transaction() as tx:
        tx.create(
            "snapshot",
            {
                "source": "SRC-1",
                "key": "k1",
                "title": title,
                "content_hash": "h",
                "seen_at": NOW.isoformat(),
                "event": {"start": start},
            },
            _PM,
        )


def test_a_meeting_is_one_own_calendar_entry_with_the_persons_words_and_it_can_be_undone(env):
    _, cfg, store = env
    made = add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:00")
    assert not made.merged and made.entry and made.changeset
    (entry,) = entries(store)
    assert (entry.id, entry.data["title"], entry.data["start"]) == (made.entry, "Print sync", "2026-10-16T15:00:00")
    assert entry.data["trust"] == "trusted" and "Print sync" in entry.data["evidence"]["quote"]
    undo(store, made.changeset)
    assert entries(store) == []


def test_with_no_time_it_is_an_all_day_entry(env):
    _, cfg, store = env
    add_meeting.add_meeting(store, cfg, "Offsite", "2026-10-20", None)
    assert entries(store)[0].data["start"] == "2026-10-20"


def test_it_shows_on_the_agenda_as_the_persons_own(env):
    _, cfg, store = env
    cfg.ui.today.agenda_days_ahead = 5
    add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:00")
    (item,) = [a for a in agenda(store, cfg, NOW) if a.title == "Print sync"]
    assert item.own and not item.all_day


def test_the_same_meeting_at_the_same_time_is_merged_into_the_one_already_there(env):
    _, cfg, store = env
    first = add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:00")
    again = add_meeting.add_meeting(store, cfg, "  print SYNC ", "2026-10-16", "15:00")
    assert again.merged and again.where == "own" and again.entry == first.entry and again.changeset is None
    assert again.merged_with == "Print sync"
    assert len(entries(store)) == 1


def test_a_meeting_a_connected_calendar_already_has_is_not_added_again(env):
    _, cfg, store = env
    connected(store)
    made = add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:00")
    assert made.merged and made.where == "calendar" and made.entry is None and made.merged_with == "Print sync"
    assert entries(store) == []


def test_a_different_title_day_or_time_is_a_different_meeting(env):
    _, cfg, store = env
    add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:00")
    for what, day, at in (
        ("Cover review", "2026-10-16", "15:00"),
        ("Print sync", "2026-10-17", "15:00"),
        ("Print sync", "2026-10-16", "17:00"),
    ):
        assert not add_meeting.add_meeting(store, cfg, what, day, at).merged
    assert len(entries(store)) == 4


def test_the_minutes_that_make_two_times_one_are_a_setting(env):
    _, cfg, store = env
    add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:00")
    assert add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:20").merged
    cfg.checks.tuning.near_duplicate_meeting.minutes = 5
    assert not add_meeting.add_meeting(store, cfg, "Print sync", "2026-10-16", "15:20").merged


def test_a_title_a_day_or_a_time_that_cannot_be_read_is_refused_in_plain_words(env):
    _, cfg, store = env
    for what, day, at, why in (
        ("  ", "2026-10-16", None, "what"),
        ("Print sync", "next Thursday", None, "day"),
        ("Print sync", "2026-10-16", "3pm", "time"),
    ):
        with pytest.raises(StoreError, match=why):
            add_meeting.add_meeting(store, cfg, what, day, at)
    assert entries(store) == []


def test_the_route_adds_merges_and_refuses(env, tmp_path):
    ws, cfg, store = env
    store.close()
    client = TestClient(create_app(ws, cfg, "t", start_worker=False))
    client.headers["Authorization"] = "Bearer t"
    base = cfg.server.base_path.rstrip("/") + "/api"
    made = client.post(f"{base}/calendar/meetings", json={"what": "Print sync", "day": "2026-10-16", "time": "15:00"})
    assert made.status_code == 200 and made.json()["merged"] is False and made.json()["changeset"]
    again = client.post(f"{base}/calendar/meetings", json={"what": "Print sync", "day": "2026-10-16", "time": "15:00"})
    assert again.json() == {
        "entry": made.json()["entry"],
        "changeset": None,
        "merged": True,
        "merged_with": "Print sync",
        "where": "own",
    }
    bad = client.post(f"{base}/calendar/meetings", json={"what": "Print sync", "day": "soon"})
    assert bad.status_code == 409 and "day" in bad.json()["detail"]
