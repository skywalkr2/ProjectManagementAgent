"""Follow-ups' Later (design 7.5, 5.0): a question held for a meeting (a calendar entry or a series) or for a send date
sits in Later, out of To send, until that meeting's day or the date. Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.followups import FollowUpError, hold_message, hold_question, mark_sent, restore_holds, sections
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


def _two_questions(store):
    """Two more questions ready to send to the same person, so the message is numbered."""
    with store.transaction() as tx:
        return [
            tx.create("question", {"to": ASKED, "title": title, "text": f"About {title}"}, _PM).id
            for title in ("Which cover is final?", "Who signs off the proof?")
        ]


def test_a_message_held_for_a_day_leaves_todays_batch_and_comes_back_numbered_as_before(env):
    _, cfg, store = env
    _two_questions(store)
    before = _section(store, cfg)
    ids = [q["id"] for q in before.questions]
    titles = [q["title"] for q in before.questions]
    assert len(ids) >= 3 and all(f"{n}. {t}" in before.message for n, t in enumerate(titles, 1))
    day = TODAY + timedelta(days=3)
    held_before = hold_message(store, ASKED, {"on": day.isoformat()}, today=TODAY)
    assert held_before == {i: None for i in ids}
    held = _section(store, cfg)
    assert held.questions == [] and sorted(x["id"] for x in held.later) == sorted(ids)
    assert all(t not in held.message for t in titles)  # none of its asks is in today's message
    assert {store.read().get("question", i).data["held_for"]["on"] for i in ids} == {day.isoformat()}
    # On its day the whole message is to send again, numbered as before, and Later is empty.
    back = _section(store, cfg, day)
    assert [q["id"] for q in back.questions] == ids and back.later == []
    assert back.message == before.message


def test_a_message_held_for_a_meeting_waits_for_it_and_undo_puts_every_question_back(env):
    _, cfg, store = env
    _two_questions(store)
    before = _section(store, cfg)
    meeting = _entry(store, (TODAY + timedelta(days=6)).isoformat())
    previous = hold_message(store, ASKED, {"event": meeting}, today=TODAY)
    held = _section(store, cfg)
    assert held.questions == [] and {x["held_for_name"] for x in held.later} == {"Print sync"}
    assert {x["held_until"] for x in held.later} == {(TODAY + timedelta(days=6)).isoformat()}
    restore_holds(store, previous)
    after = _section(store, cfg)
    assert after.message == before.message and after.later == []
    assert all(store.read().get("question", i).data.get("held_for") is None for i in previous)


def test_holding_a_message_is_one_change_and_refuses_what_a_single_question_refuses(env):
    _, cfg, store = env
    _two_questions(store)
    ids = [q["id"] for q in _section(store, cfg).questions]
    before = store.read().get("question", ids[0]).version
    with pytest.raises(FollowUpError):
        hold_message(store, ASKED, {"on": TODAY.isoformat()}, today=TODAY)  # not after today
    with pytest.raises(FollowUpError):
        hold_message(store, ASKED, {"event": "EVT-999"}, today=TODAY)
    assert store.read().get("question", ids[0]).version == before  # nothing changed
    with pytest.raises(FollowUpError):
        hold_message(store, "PER-999", {"on": (TODAY + timedelta(days=2)).isoformat()}, today=TODAY)  # no message
    hold_message(store, ASKED, {"on": (TODAY + timedelta(days=2)).isoformat()}, today=TODAY)
    with pytest.raises(FollowUpError):
        hold_message(store, ASKED, {"on": (TODAY + timedelta(days=4)).isoformat()}, today=TODAY)  # nothing left to hold


def test_the_api_holds_a_whole_message_with_undo(api):
    client, base, store, cfg = api
    ids = [
        q["id"] for q in next(s for s in client.get(f"{base}/followups").json() if s["person"] == ASKED)["questions"]
    ]
    when = (datetime.now(UTC).date() + timedelta(days=4)).isoformat()
    put = client.post(f"{base}/followups/{ASKED}/held-for", json={"held_for": {"on": when}})
    assert put.status_code == 200
    assert sorted(h["id"] for h in put.json()["previous"]) == sorted(ids)
    section = next(s for s in client.get(f"{base}/followups").json() if s["person"] == ASKED)
    assert section["questions"] == [] and sorted(x["id"] for x in section["later"]) == sorted(ids)
    undone = client.post(f"{base}/followups/{ASKED}/held-for/restore", json={"holds": put.json()["previous"]})
    assert undone.status_code == 200
    section = next(s for s in client.get(f"{base}/followups").json() if s["person"] == ASKED)
    assert sorted(x["id"] for x in section["questions"]) == sorted(ids) and section["later"] == []
    bad = client.post(f"{base}/followups/{ASKED}/held-for", json={"held_for": {"on": "2020-01-01"}})
    assert bad.status_code == 409
    assert client.post(f"{base}/followups/PER-999/held-for", json={"held_for": {"on": when}}).status_code == 404
