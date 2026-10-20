"""Follow-ups' Later (design 7.5, 5.0): a question held for a meeting (a calendar entry or a series) or for a send date
sits in Later, out of To send, until that meeting's day or the date. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.followups import FollowUpError, hold_question, mark_sent, sections
from engine.records import REFERENCES, Question
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "later-token"
NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_PM = WriteContext("pm", "trusted", "test")
ASKED = next(q for q in fixture_records(DEMO_B, "question") if q["to"] != "")["to"]


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
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.store, cfg


def _question(store):
    """An open question to someone other than the person, the first the fixtures have."""
    return next(q.id for q in store.read().list("question") if q.data["status"] == "open" and q.data["to"] == ASKED)


def _section(store, cfg, today=TODAY):
    return next(s for s in sections(store, cfg, today) if s.person == ASKED)


def _entry(store, start, **more):
    with store.transaction() as tx:
        return tx.create("event", {"title": "Print sync", "start": start, "trust": "trusted", **more}, _PM).id


def test_a_question_holds_for_a_meeting_a_series_or_a_date_and_nothing_else():
    assert Question.model_validate(
        {"id": "Q-1", "to": ASKED, "title": "T", "held_for": {"on": "2026-10-20"}}
    ).held_for.on
    for bad in ({}, {"on": "2026-10-20", "event": "EVT-1"}, {"event": "EVT-1", "series": "SER-1"}):
        with pytest.raises(ValidationError):
            Question.model_validate({"id": "Q-1", "to": ASKED, "title": "T", "held_for": bad})
    assert ("held_for.event", "event") in REFERENCES["question"]
    assert ("held_for.series", "series") in REFERENCES["question"]


def test_a_question_held_for_a_date_is_out_of_to_send_until_that_day(env):
    _, cfg, store = env
    q = _question(store)
    assert any(x["id"] == q for x in _section(store, cfg).questions)
    to_send_before = _section(store, cfg).to_send
    assert hold_question(store, q, {"on": (TODAY + timedelta(days=3)).isoformat()}, today=TODAY) is None
    held = _section(store, cfg)
    assert all(x["id"] != q for x in held.questions) and held.to_send == to_send_before - 1
    (later,) = [x for x in held.later if x["id"] == q]
    assert later["held_until"] == (TODAY + timedelta(days=3)).isoformat() and later["held_for_name"] is None
    assert q not in held.message and held.message != _section(store, cfg, TODAY + timedelta(days=3)).message
    # On the day it comes back to To send, and leaves Later.
    back = _section(store, cfg, TODAY + timedelta(days=3))
    assert any(x["id"] == q for x in back.questions) and all(x["id"] != q for x in back.later)
    assert back.to_send == to_send_before


def test_a_question_held_for_a_meeting_waits_for_that_meetings_day_and_names_it(env):
    _, cfg, store = env
    q = _question(store)
    meeting = _entry(store, (TODAY + timedelta(days=6)).isoformat())
    hold_question(store, q, {"event": meeting}, today=TODAY)
    (later,) = [x for x in _section(store, cfg).later if x["id"] == q]
    assert later["held_until"] == (TODAY + timedelta(days=6)).isoformat() and later["held_for_name"] == "Print sync"
    assert any(x["id"] == q for x in _section(store, cfg, TODAY + timedelta(days=6)).questions)


def test_a_question_held_for_a_series_waits_for_its_next_instance_and_stays_out_once_that_day_has_passed(env):
    _, cfg, store = env
    q = _question(store)
    with store.transaction() as tx:
        sid = tx.create("series", {"title": "Print sync", "repeats": "weekly", "trust": "trusted"}, _PM).id
    _entry(store, (TODAY + timedelta(days=2)).isoformat(), series=sid)
    _entry(store, (TODAY + timedelta(days=9)).isoformat(), series=sid)
    hold_question(store, q, {"series": sid}, today=TODAY)
    (later,) = [x for x in _section(store, cfg).later if x["id"] == q]
    assert later["held_until"] == (TODAY + timedelta(days=2)).isoformat() and later["held_for_name"] == "Print sync"
    # The first instance's day has come: the question is back in To send, and it stays there when the next instance
    # is the one a week later, because it was held for the one that came first.
    for day in (2, 3, 8):
        back = _section(store, cfg, TODAY + timedelta(days=day))
        assert any(x["id"] == q for x in back.questions) and all(x["id"] != q for x in back.later)


def test_a_hold_for_a_meeting_that_cannot_be_dated_is_refused_and_so_is_a_closed_question(env):
    _, cfg, store = env
    q = _question(store)
    with pytest.raises(FollowUpError):
        hold_question(store, q, {"event": "EVT-999"}, today=TODAY)
    with store.transaction() as tx:
        lone = tx.create("series", {"title": "Print sync", "repeats": "weekly", "trust": "trusted"}, _PM).id
    with pytest.raises(FollowUpError):
        hold_question(store, q, {"series": lone}, today=TODAY)  # no instance to wait for
    with pytest.raises(FollowUpError):
        hold_question(store, q, {"on": (TODAY - timedelta(days=1)).isoformat()}, today=TODAY)  # not in the future
    rec = store.read().get("question", q)
    with store.transaction() as tx:
        tx.update("question", q, {"status": "sent", "sent_at": NOW.isoformat()}, _PM, read_version=rec.version)
    with pytest.raises(FollowUpError):
        hold_question(store, q, {"on": (TODAY + timedelta(days=2)).isoformat()}, today=TODAY)


def test_marking_a_person_sent_leaves_a_held_question_unsent_and_send_now_brings_it_back(env):
    _, cfg, store = env
    q = _question(store)
    previous = hold_question(store, q, {"on": (TODAY + timedelta(days=5)).isoformat()}, today=TODAY)
    mark_sent(store, cfg, ASKED, now=NOW)
    assert store.read().get("question", q).data["status"] == "open"
    assert hold_question(store, q, None, today=TODAY)["on"]  # Send now returns what it was held for
    assert store.read().get("question", q).data.get("held_for") is None
    assert previous is None
    assert any(x["id"] == q for x in _section(store, cfg).questions)


def test_the_api_holds_a_question_for_later_with_undo_and_the_view_lists_it_in_later(api):
    client, base, store, cfg = api
    q = _question(store)
    when = (datetime.now(UTC).date() + timedelta(days=4)).isoformat()
    put = client.post(f"{base}/questions/{q}/held-for", json={"held_for": {"on": when}})
    assert put.status_code == 200 and put.json()["previous"] is None
    section = next(s for s in client.get(f"{base}/followups").json() if s["person"] == ASKED)
    assert all(x["id"] != q for x in section["questions"])
    (later,) = [x for x in section["later"] if x["id"] == q]
    assert later["held_until"] == when
    again = client.post(f"{base}/questions/{q}/held-for", json={"held_for": None})
    assert again.json()["previous"]["on"] == when
    back = client.post(f"{base}/questions/{q}/held-for", json={"held_for": again.json()["previous"]})
    assert back.status_code == 200 and store.read().get("question", q).data["held_for"]["on"] == when
    bad = client.post(f"{base}/questions/{q}/held-for", json={"held_for": {"on": "2020-01-01"}})
    assert bad.status_code == 409
    assert client.post(f"{base}/questions/Q-999/held-for", json={"held_for": None}).status_code == 404
