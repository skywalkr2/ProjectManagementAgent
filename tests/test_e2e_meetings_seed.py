"""The meeting journey's seed (`tests/e2e_meetings.py`) gives Today the three lines the browser journey looks for: the
prep of an entry about to start, the question of what happened at one that has ended, and a promise gone quiet. Names
come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go
from tests.e2e_meetings import seed_meetings


def test_the_seed_gives_today_a_prep_a_capture_and_a_quiet_promise_for_one_person(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    try:
        seeded = seed_meetings(store, cfg)
        lines = {x.kind: x for x in queue(ws, store, cfg, datetime.now(UTC)) if x.kind in KINDS}
        assert set(lines) == set(KINDS)
        assert lines["meeting_prep"].event == seeded["coming"]["id"]
        assert lines["meeting_capture"].event == seeded["ended"]["id"]
        assert lines["quiet_promise"].actions == [seeded["promise"]["id"]]
        assert lines["quiet_promise"].person == seeded["guest"]["id"]
        assert store.read().get("event", seeded["ended"]["id"]).data.get("captured_at") is None
    finally:
        store.close()


KINDS = ("meeting_prep", "meeting_capture", "quiet_promise")
