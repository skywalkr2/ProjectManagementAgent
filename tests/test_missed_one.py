"""Missed one (design 6.32, 6.20): the person says in a plain sentence what the assistant missed. It records a `missed`
signal for the person, hands the words in as the person's own note marked as a miss so the run adds what was missed, is
counted per person per week on the quality view, and is read by the learning loop like a send-back.

Names, ids and texts come from the fixtures; the few free words are about no one.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import learn, quality
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.corrections import missed_one
from engine.dispatcher import process
from engine.intake import IntakeError
from engine.packet import build
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

PM = fixture_records(DEMO_B, "person")[0]["id"]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)  # a Wednesday
THIS_WEEK = date(2026, 10, 12)
UTC_ZONE = ZoneInfo("UTC")
WORDS = "Dana promised me the layout notes by Friday and nothing picked it up"
_TEST = WriteContext(actor="pm", trust="trusted", op="test.missed")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "missed-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer missed-token"}) as client:
        yield client, application.state.store, ws, cfg


def missed_signals(store) -> list:
    return [s for s in store.read().list("signal") if s.data["kind"] == "missed"]


def add_missed(store, person: str, at: datetime) -> None:
    with store.transaction() as tx:
        tx.create(
            "signal",
            {"kind": "missed", "refs": [], "note": "Something", "person": person, "at": at.isoformat()},
            _TEST,
        )


# ---- the route -------------------------------------------------------------------------------------------------------


def test_the_route_records_the_signal_for_the_person_and_queues_a_notes_request_with_the_marker(api):
    client, store, ws, cfg = api
    done = client.post("/api/missed", json={"text": f"  {WORDS}  "})
    assert done.status_code == 200, done.text
    body = done.json()
    (signal,) = missed_signals(store)
    assert body["signal"] == signal.id
    assert signal.data["person"] == cfg.workspace.user.person
    assert signal.data["note"] == WORDS and signal.data["refs"] == []
    queued = store.read().get("request", body["request"]).data
    assert queued["task"] == "notes" and queued["origin"] == "pm"
    saved = store.read().get("source", queued["source"]).data
    assert saved["kind"] == "note:missed_one" and saved["trust"] == "trusted"
    packet = build(ws, store, cfg, body["request"], date(2026, 10, 14)).task.request
    assert "the person says the assistant missed this" in packet.lower()
    assert f'<note source="{queued["source"]}"' in packet and WORDS in packet


def test_a_missed_one_is_read_however_short_and_empty_words_are_refused_in_plain_words(api):
    client, store, _, _ = api
    short = client.post("/api/missed", json={"text": "Reply to Sam"})
    assert short.status_code == 200 and store.read().get("request", short.json()["request"]) is not None
    for text in ("", "   \n "):
        refused = client.post("/api/missed", json={"text": text})
        assert refused.status_code == 400 and refused.json()["detail"] == "Say what the assistant missed."
    assert len(missed_signals(store)) == 1


def test_nothing_is_recorded_when_the_words_are_empty(env):
    ws, cfg, store = env
    with pytest.raises(IntakeError):
        missed_one(ws, store, cfg, "  ")
    assert not missed_signals(store) and not store.read().list("request")


def test_the_notes_prompt_says_a_missed_one_adds_the_item_it_names(env):
    ws, cfg, store = env
    request, _ = missed_one(ws, store, cfg, WORDS, now=NOW)
    instructions = build(ws, store, cfg, request, NOW.date()).task.instructions
    assert "missed" in instructions and "never answer with only a note" in instructions.lower()


def test_the_run_can_add_what_was_missed_from_the_words(env):
    ws, cfg, store = env
    request, _ = missed_one(ws, store, cfg, WORDS, now=NOW)
    op = {
        "op": "action.add",
        "text": "Send the layout notes",
        "owners": [PM],
        "due": "2026-10-16",
        "evidence": {"quote": "promised me the layout notes by Friday"},
    }
    set_responder(lambda task: json.dumps({"summary": "Added.", "topic": "layout notes", "ops": [op]}))
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "applied", outcome


# ---- the measure -----------------------------------------------------------------------------------------------------


def test_the_measure_counts_missed_signals_for_each_person_in_each_week_with_empty_weeks_as_zero(env):
    _, cfg, store = env
    other = next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != PM)
    add_missed(store, PM, NOW - timedelta(days=15))  # two weeks back
    add_missed(store, PM, NOW - timedelta(days=8))  # last week
    add_missed(store, PM, NOW - timedelta(days=7))
    add_missed(store, PM, NOW)  # this week
    add_missed(store, other, NOW)
    add_missed(store, PM, NOW - timedelta(days=60))  # outside the window
    with store.transaction() as tx:  # another kind of correction is not counted
        tx.create("signal", {"kind": "dropped", "refs": [], "person": PM, "at": NOW.isoformat()}, _TEST)
    rows = quality.missed_per_week(store.read(), NOW, 28, UTC_ZONE)
    mine = {r.week: r.count for r in rows if r.person == PM}
    assert mine == {
        THIS_WEEK - timedelta(weeks=4): 0,  # the window starts in this week
        THIS_WEEK - timedelta(weeks=3): 0,
        THIS_WEEK - timedelta(weeks=2): 1,
        THIS_WEEK - timedelta(weeks=1): 2,
        THIS_WEEK: 1,
    }
    theirs = {r.week: r.count for r in rows if r.person == other}
    assert theirs[THIS_WEEK] == 1 and sum(theirs.values()) == 1
    assert [r.week for r in rows if r.person == PM] == sorted(mine)


def test_a_signal_with_no_person_is_counted_for_nobody(env):
    _, _, store = env
    with store.transaction() as tx:
        tx.create("signal", {"kind": "missed", "refs": [], "note": "x", "at": NOW.isoformat()}, _TEST)
    assert quality.missed_per_week(store.read(), NOW, 28, UTC_ZONE) == []


def test_the_quality_route_shows_missed_one_per_person_and_week_with_the_dates(api):
    client, store, _, cfg = api
    now = datetime.now(UTC)
    add_missed(store, cfg.workspace.user.person, now)
    add_missed(store, cfg.workspace.user.person, now - timedelta(days=8))
    body = client.get("/api/quality").json()
    rows = [r for r in body["missed"] if r["person"] == cfg.workspace.user.person]
    assert sum(r["count"] for r in rows) == 2
    last = rows[-1]
    assert last["count"] == 1 and last["person_name"]
    assert date.fromisoformat(last["week_end"]) - date.fromisoformat(last["week"]) == timedelta(days=6)
    assert [r["week"] for r in rows] == sorted(r["week"] for r in rows)


# ---- learning --------------------------------------------------------------------------------------------------------


def test_a_missed_one_queues_learning_at_once_like_a_send_back_and_the_packet_has_the_words_as_theirs(env):
    ws, cfg, store = env
    _, signal_id = missed_one(ws, store, cfg, WORDS, now=NOW)
    (queued,) = [r for r in store.read().list("request") if r.data["task"] == learn.TASK]
    assert queued.data["about"] == {"kind": "signal", "id": signal_id}
    assert not queued.data.get("cause"), "a correction the person wrote is not batched"
    packet = build(ws, store, cfg, queued.id, NOW.date()).task.request
    assert f"<note>\n{WORDS}\n</note>" in packet and "missed" in packet.lower()


def test_a_missed_one_is_a_correction_for_the_quality_measures_and_its_signal_kind_is_known():
    assert "missed" in learn.AT_ONCE and "missed" in learn.TEACHES and "missed" in learn.KIND_WORDS
    assert "missed" in quality.CORRECTIONS
