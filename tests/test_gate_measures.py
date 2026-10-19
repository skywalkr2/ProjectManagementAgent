"""The gate week's instruments (design 6.32, "Measures"): silent closes out of all closes, wrong endings out of endings
made (declined, undone, or a nudge recorded as done that the person reopened), the person's own daily count of missed
out of present, "Missed one" for each week and the replay set, each with its denominator, for each day and for the
window. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import gate_measures
from engine.applier import apply_as_person, decline_held, release, undo
from engine.names import People
from engine.records import REGISTRY
from engine.storage import Store, WriteContext
from engine.today import zone
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip
from tests.test_hold_drop_fold import DROPPING, OPEN, RAW, WAITING, drop_op
from tests.test_knowledge_records import apply, source

_TEST = WriteContext(actor="pm", trust="trusted", op="test.gate-measures")
_UI = WriteContext(actor="pm", trust="trusted", op="ui")
TOKEN = "gate-token"
PEOPLE = fixture_records(DEMO_B, "person")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def today_of(cfg) -> date:
    return datetime.now(UTC).astimezone(zone(cfg)).date()


def window_of(cfg, days: int = 28) -> gate_measures.Window:
    return gate_measures.window(datetime.now(UTC), days, zone(cfg))


def the_person(store, cfg) -> str:
    return People(store, cfg).pm


def open_actions(cfg, n: int) -> list[str]:
    """The ids of n fixture actions that are open; an ending read from an input holds for each of them."""
    found = [a["id"] for a in OPEN]
    assert len(found) >= n, "the fixture needs more open actions"
    return found[:n]


def the_person_id(cfg) -> str:
    return cfg.workspace.user.person


def from_input(store, cfg, ops, kind="pasted"):
    """Apply ops as the assistant does for an input that holds RAW (of a kind of source)."""
    return apply(store, cfg, ops, origin="input", trust="untrusted", source_id=source(store, kind=kind), raw=RAW)


def close_op(action_id: str) -> dict:
    return {"op": "action.close", "id": action_id, "evidence": {"quote": WAITING}}


def keep(store, cfg, changeset: str) -> str:
    """The person keeps the held ending, so it applies."""
    release(store, cfg, changeset, 0)
    return changeset


def back_date(store, changeset: str, moment: datetime) -> None:
    with store.transaction() as tx:
        current = tx.get("changeset", changeset)
        tx.update("changeset", changeset, {"created_at": moment.isoformat()}, _TEST, read_version=current.version)


def question_drop(store) -> dict:
    target = store.read().list("question")[0].id
    return {"op": "question.drop", "id": target, "reason": "No longer needed", "evidence": {"quote": DROPPING}}


# ---- silent closes out of all closes --------------------------------------------------------------------------------


def test_silent_closes_are_counted_out_of_all_closes_for_each_day_and_for_the_window(env):
    ws, cfg, store = env
    mine = next(a["id"] for a in OPEN if a["owners"][0]["person"] == the_person_id(cfg))
    apply_as_person(store, cfg, [{"op": "action.drop", "id": mine, "reason": "Not needed"}], "Dropped")
    silent_one, _ = from_input(store, cfg, [question_drop(store)])
    earlier = datetime.now(UTC) - timedelta(days=3)
    back_date(store, silent_one, earlier)
    held = from_input(store, cfg, [drop_op(open_actions(cfg, 1)[0])])[0]
    keep(store, cfg, held)  # approved by the person: a close, but not silent
    now = datetime.now(UTC)
    found = gate_measures.closes_measure(store.read(), window_of(cfg), zone(cfg))
    assert (found.total, found.silent) == (3, 1)
    by_day = {d.day: (d.total, d.silent) for d in found.days}
    assert by_day[earlier.astimezone(zone(cfg)).date()] == (1, 1)
    assert by_day[today_of(cfg)] == (2, 0)
    assert sum(t for t, _ in by_day.values()) == found.total
    assert now - earlier > timedelta(days=2)


def test_a_window_without_closes_has_no_days_and_zero_over_zero(env):
    _, cfg, store = env
    found = gate_measures.closes_measure(store.read(), window_of(cfg), zone(cfg))
    assert (found.total, found.silent, found.days) == (0, 0, [])


# ---- wrong endings out of endings made ------------------------------------------------------------------------------


def test_an_ending_the_person_declined_or_undid_is_wrong_and_every_applied_declined_or_undone_ending_was_made(env):
    ws, cfg, store = env
    kept, declined, undone, waiting = open_actions(cfg, 4)
    keep(store, cfg, from_input(store, cfg, [drop_op(kept)])[0])
    held_declined, _ = from_input(store, cfg, [drop_op(declined)])
    decline_held(store, held_declined, 0)
    undone_cs = keep(store, cfg, from_input(store, cfg, [drop_op(undone)])[0])
    undo(store, undone_cs)
    from_input(store, cfg, [drop_op(waiting)])  # still waiting for the person: not made yet
    found = gate_measures.endings_measure(store.read(), store.read().ledger(kind="action"), window_of(cfg), zone(cfg))
    assert (found.made, found.wrong) == (3, 2)
    assert (found.declined, found.undone, found.reopened) == (1, 1, 0)
    (day,) = found.days
    assert (day.day, day.made, day.wrong) == (today_of(cfg), 3, 2)


def test_what_the_person_does_themselves_is_never_an_ending_the_assistant_made(env):
    ws, cfg, store = env
    mine = next(a["id"] for a in OPEN if a["owners"][0]["person"] == the_person_id(cfg))
    cs = apply_as_person(store, cfg, [{"op": "action.drop", "id": mine, "reason": "Not needed"}], "Dropped")
    undo(store, cs)
    found = gate_measures.endings_measure(store.read(), store.read().ledger(kind="action"), window_of(cfg), zone(cfg))
    assert (found.made, found.wrong, found.days) == (0, 0, [])


def test_a_nudge_recorded_as_done_that_the_person_reopened_is_a_wrong_ending(env):
    ws, cfg, store = env
    chased, kept_closed = open_actions(cfg, 2)
    for target in (chased, kept_closed):
        # a note typed on Followed up is a source of that kind; an ending read from it waits for the person's Keep
        keep(store, cfg, from_input(store, cfg, [close_op(target)], kind="note:followed_up")[0])
    with store.transaction() as tx:
        current = tx.get("action", chased)
        tx.update(
            "action", chased, {"status": "open", "done_by": [], "reported_by": None}, _UI, read_version=current.version
        )
    found = gate_measures.endings_measure(store.read(), store.read().ledger(kind="action"), window_of(cfg), zone(cfg))
    assert (found.made, found.wrong, found.reopened, found.declined, found.undone) == (2, 1, 1, 0, 0)


def test_a_close_reopened_that_did_not_come_from_a_nudge_is_not_counted_and_an_undone_nudge_counts_once(env):
    ws, cfg, store = env
    plain, nudged = open_actions(cfg, 2)
    keep(store, cfg, from_input(store, cfg, [close_op(plain)])[0])
    nudge_cs = keep(store, cfg, from_input(store, cfg, [close_op(nudged)], kind="note:followed_up")[0])
    undo(store, nudge_cs)  # undone, then the action is open: counted as undone, not reopened as well
    with store.transaction() as tx:
        current = tx.get("action", plain)
        tx.update(
            "action", plain, {"status": "open", "done_by": [], "reported_by": None}, _UI, read_version=current.version
        )
    found = gate_measures.endings_measure(store.read(), store.read().ledger(kind="action"), window_of(cfg), zone(cfg))
    assert (found.made, found.wrong, found.undone, found.reopened) == (2, 1, 1, 0)


def test_endings_are_counted_on_the_day_they_were_made_and_only_inside_the_window(env):
    ws, cfg, store = env
    old, recent = open_actions(cfg, 2)
    old_cs = keep(store, cfg, from_input(store, cfg, [drop_op(old)])[0])
    undo(store, old_cs)
    back_date(store, old_cs, datetime.now(UTC) - timedelta(days=60))
    recent_cs = keep(store, cfg, from_input(store, cfg, [drop_op(recent)])[0])
    undo(store, recent_cs)
    back_date(store, recent_cs, datetime.now(UTC) - timedelta(days=2))
    found = gate_measures.endings_measure(store.read(), store.read().ledger(kind="action"), window_of(cfg), zone(cfg))
    assert (found.made, found.wrong) == (1, 1)
    assert [d.day for d in found.days] == [(datetime.now(UTC) - timedelta(days=2)).astimezone(zone(cfg)).date()]


# ---- missed out of present: the person's own daily count ------------------------------------------------------------


def test_the_daily_count_is_saved_corrected_and_undone(env):
    ws, cfg, store = env
    day = today_of(cfg)
    first = gate_measures.save_count(store, cfg, day, present=12, missed=2)
    assert first is None, "nothing was saved for the day before"
    (stored,) = store.read().list("promise_count")
    assert (stored.data["person"], str(stored.data["day"]), stored.data["present"], stored.data["missed"]) == (
        the_person(store, cfg),
        day.isoformat(),
        12,
        2,
    )
    corrected = gate_measures.save_count(store, cfg, day, present=14, missed=1)
    assert corrected == {"present": 12, "missed": 2}
    (still_one,) = store.read().list("promise_count")
    assert (still_one.id, still_one.data["present"], still_one.data["missed"]) == (stored.id, 14, 1)
    gate_measures.restore_count(store, cfg, day, corrected)
    assert [(c.data["present"], c.data["missed"]) for c in store.read().list("promise_count")] == [(12, 2)]
    gate_measures.restore_count(store, cfg, day, None)
    assert store.read().list("promise_count") == []


def test_a_count_with_more_missed_than_present_or_for_a_day_that_has_not_come_is_refused(env):
    ws, cfg, store = env
    with pytest.raises(gate_measures.CountError, match="more"):
        gate_measures.save_count(store, cfg, today_of(cfg), present=2, missed=3)
    with pytest.raises(gate_measures.CountError, match="hasn't"):
        gate_measures.save_count(store, cfg, today_of(cfg) + timedelta(days=2), present=2, missed=1)
    with pytest.raises(gate_measures.CountError):
        gate_measures.save_count(store, cfg, today_of(cfg), present=-1, missed=0)
    assert store.read().list("promise_count") == []


def test_counts_are_summed_for_the_window_as_missed_out_of_present_for_the_person_who_entered_them(env):
    ws, cfg, store = env
    today = today_of(cfg)
    gate_measures.save_count(store, cfg, today, present=10, missed=1)
    gate_measures.save_count(store, cfg, today - timedelta(days=1), present=20, missed=3)
    gate_measures.save_count(store, cfg, today - timedelta(days=90), present=50, missed=9)  # before the window
    other = next(p["id"] for p in PEOPLE if p["id"] != the_person(store, cfg))
    with store.transaction() as tx:  # someone else's count is theirs
        tx.create(
            "promise_count",
            {"person": other, "day": today.isoformat(), "present": 5, "missed": 5, "at": datetime.now(UTC).isoformat()},
            _TEST,
        )
    found = gate_measures.counts_measure(store.read(), the_person(store, cfg), window_of(cfg))
    assert (found.present, found.missed, found.entered) == (30, 4, 2)
    assert [(d.day, d.present, d.missed) for d in found.days] == [(today - timedelta(days=1), 20, 3), (today, 10, 1)]


def test_a_window_with_no_counts_is_zero_over_zero_and_the_counts_survive_export_and_import(env, tmp_path):
    ws, cfg, store = env
    empty = gate_measures.counts_measure(store.read(), the_person(store, cfg), window_of(cfg))
    assert (empty.present, empty.missed, empty.entered, empty.days) == (0, 0, 0, [])
    gate_measures.save_count(store, cfg, today_of(cfg), present=7, missed=1)
    gate_measures.save_count(store, cfg, today_of(cfg), present=8, missed=1)
    assert "promise_count" in REGISTRY
    assert round_trip(store, cfg, tmp_path / "round-trip")["differences"] == []


# ---- the window and the replay set ----------------------------------------------------------------------------------


def test_the_window_is_the_configured_days_ending_today_on_the_persons_own_clock():
    here = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)  # 10 PM on October 18 there
    found = gate_measures.window(now, 7, here)
    assert (found.since, found.until) == (date(2026, 10, 11), date(2026, 10, 18))
    assert found.start == datetime.combine(date(2026, 10, 11), time(0), tzinfo=here).astimezone(UTC)
    assert found.end == now


def test_the_replay_set_is_the_files_in_the_workspaces_replays_folder(env):
    ws, cfg, store = env
    folder = ws.root / "replays"
    folder.mkdir(exist_ok=True)
    before = gate_measures.replay_count(ws.root)
    for name in ("one", "two"):
        (folder / f"added-{name}.yaml").write_text(f"id: added-{name}\n", encoding="utf-8")
    (folder / "notes.txt").write_text("not a replay", encoding="utf-8")
    assert gate_measures.replay_count(ws.root) == before + 2
    assert gate_measures.replay_count(ws.root / "nowhere") == 0


# ---- the API --------------------------------------------------------------------------------------------------------


def client_for(ws, cfg):
    app = create_app(ws, cfg, TOKEN, ui_dist=ws.root / "no-ui", start_worker=False)
    base = cfg.server.base_path.rstrip("/") + "/api"
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}), base, app


def test_the_quality_route_serves_every_measure_with_its_denominator_and_the_window(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    (ws.root / "replays").mkdir(exist_ok=True)
    (ws.root / "replays" / "a-miss.yaml").write_text("id: a-miss\n", encoding="utf-8")
    client, api, app = client_for(ws, cfg)
    with client:
        store = app.state.store
        a, b = open_actions(cfg, 2)
        keep(store, cfg, from_input(store, cfg, [drop_op(a)])[0])
        held, _ = from_input(store, cfg, [drop_op(b)])
        decline_held(store, held, 0)
        from_input(store, cfg, [question_drop(store)])
        body = client.get(f"{api}/quality").json()
        assert body["since"] == window_of(cfg, body["days"]).since.isoformat()
        assert body["until"] == today_of(cfg).isoformat()
        assert (body["closes"]["total"], body["closes"]["silent"]) == (2, 1)
        assert (body["endings"]["made"], body["endings"]["wrong"], body["endings"]["declined"]) == (2, 1, 1)
        assert body["endings"]["days"][0]["day"] == today_of(cfg).isoformat()
        assert (body["counts"]["present"], body["counts"]["missed"], body["counts"]["entered"]) == (0, 0, 0)
        assert body["replays"] == {"count": 1, "last_run": None}
        assert body["missed"] == []


def test_the_daily_count_is_entered_corrected_and_undone_through_the_api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    client, api, _ = client_for(ws, cfg)
    day = today_of(cfg).isoformat()
    with client:
        saved = client.put(f"{api}/quality/counts/{day}", json={"present": 9, "missed": 2})
        assert saved.status_code == 200, saved.text
        assert saved.json()["previous"] is None and saved.json()["id"].startswith("PCNT-")
        counts = client.get(f"{api}/quality").json()["counts"]
        assert (counts["present"], counts["missed"], counts["entered"]) == (9, 2, 1)
        assert counts["days"] == [{"day": day, "present": 9, "missed": 2}]
        fixed = client.put(f"{api}/quality/counts/{day}", json={"present": 10, "missed": 1}).json()
        assert fixed["previous"] == {"present": 9, "missed": 2}
        assert client.post(f"{api}/quality/counts/{day}/undo", json={"previous": fixed["previous"]}).status_code == 200
        assert client.get(f"{api}/quality").json()["counts"]["days"][0]["present"] == 9
        assert client.post(f"{api}/quality/counts/{day}/undo", json={"previous": None}).status_code == 200
        assert client.get(f"{api}/quality").json()["counts"]["entered"] == 0


def test_a_refused_count_says_why_and_changes_nothing(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    client, api, _ = client_for(ws, cfg)
    day = today_of(cfg).isoformat()
    with client:
        more = client.put(f"{api}/quality/counts/{day}", json={"present": 1, "missed": 4})
        assert more.status_code == 409 and "more" in more.json()["detail"]
        future = (today_of(cfg) + timedelta(days=3)).isoformat()
        assert client.put(f"{api}/quality/counts/{future}", json={"present": 1, "missed": 0}).status_code == 409
        assert client.put(f"{api}/quality/counts/{day}", json={"present": -1, "missed": 0}).status_code == 422
        assert client.get(f"{api}/quality").json()["counts"]["entered"] == 0
