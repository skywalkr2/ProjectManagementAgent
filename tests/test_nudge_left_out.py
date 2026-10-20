"""What the nudge leaves out, and the one suggested escalation (design 7.5, 6.8, the UI designer's answer 36).

A nudge lists only what is still open. What was in the same first message and has been answered or done since is shown
above the box as "answered <date>, left out", so the person sees why the list is shorter. After a second follow-up with
no answer Today suggests one escalation line, "Ask someone else about <item>?", that never sends anything. Names, ids
and dates come from the fixtures and the settings.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.followups import mark_followed_up, mark_sent, sections
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TOKEN = "left-out-token"
_PM = WriteContext(actor="pm", trust="trusted", op="test")


def editor_id() -> str:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == "Editor")["id"]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def section(store, cfg, on: datetime):
    return next(s for s in sections(store, cfg, on.date()) if s.person == editor_id())


def sent_a_while_ago(env, days: int, *, due_soon: bool = True):
    """Everything waiting on the editor went out `days` days before NOW. With `due_soon`, their action is due the day
    after NOW, so the rule chases it too."""
    _, cfg, store = env
    if due_soon:
        action = section(store, cfg, NOW).actions[0]
        rec = store.read().get("action", action["id"])
        with store.transaction() as tx:
            tx.update(
                "action",
                action["id"],
                {"due": (NOW + timedelta(days=1)).date().isoformat()},
                _PM,
                read_version=rec.version,
            )
    sec = section(store, cfg, NOW - timedelta(days=days))
    mark_sent(store, cfg, editor_id(), sent_text=sec.message, now=NOW - timedelta(days=days))


def close_question(store, qid: str, status: str, when: datetime) -> None:
    rec = store.read().get("question", qid)
    with store.transaction() as tx:
        tx.update("question", qid, {"status": status}, _PM, read_version=rec.version)
    _stamp(store, "question", qid, when)


def _stamp(store, kind: str, record_id: str, when: datetime) -> None:
    """Put the ledger's time for the latest entry of a record at `when`, as a clock that had been then would have."""
    with store.transaction() as tx:
        tx.sql(
            "UPDATE ledger SET at=? WHERE seq=(SELECT MAX(seq) FROM ledger WHERE kind=? AND record_id=?)",
            (when.isoformat(timespec="seconds"), kind, record_id),
        )


def test_a_question_answered_since_is_left_out_and_listed_with_the_day_it_was_answered(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait + 2)
    before = section(store, cfg, NOW)
    answered = before.nudge.question_ids[0]
    title = next(q["title"] for q in before.questions if q["id"] == answered)
    answered_on = NOW - timedelta(days=1)
    close_question(store, answered, "answered", answered_on)
    nudge = section(store, cfg, NOW).nudge
    assert nudge is not None
    assert answered not in nudge.question_ids and title not in nudge.text
    assert [(x.kind, x.id, x.text, x.on) for x in nudge.left_out] == [
        ("question", answered, title, answered_on.date().isoformat())
    ]


def test_an_action_done_since_is_left_out_the_same_way(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait + 2)
    before = section(store, cfg, NOW)
    action = before.nudge.action_ids[0]
    text = next(a["text"] for a in before.actions if a["id"] == action)
    rec = store.read().get("action", action)
    with store.transaction() as tx:
        tx.update("action", action, {"status": "done"}, _PM, read_version=rec.version)
    _stamp(store, "action", action, NOW - timedelta(days=1))
    nudge = section(store, cfg, NOW).nudge
    assert nudge is not None and action not in nudge.action_ids
    assert [(x.kind, x.id, x.text) for x in nudge.left_out] == [("action", action, text)]
    assert nudge.left_out[0].on == (NOW - timedelta(days=1)).date().isoformat()


def test_nothing_is_left_out_when_everything_in_the_message_is_still_waiting(env):
    _, cfg, store = env
    sent_a_while_ago(env, cfg.ui.followups.question_after_days + 2)
    assert section(store, cfg, NOW).nudge.left_out == []


def test_a_question_dropped_or_sent_in_another_message_is_not_listed(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait + 2)
    first = section(store, cfg, NOW).nudge.question_ids[0]
    # A question the person dropped is no one's answer.
    close_question(store, first, "dropped", NOW - timedelta(days=1))
    # An earlier answered question went in a message on another day than the ones still waiting.
    with store.transaction() as tx:
        other = tx.create(
            "question",
            {
                "to": editor_id(),
                "title": "An older question",
                "status": "answered",
                "sent_at": (NOW - timedelta(days=wait + 20)).isoformat(),
            },
            _PM,
        ).id
    _stamp(store, "question", other, NOW - timedelta(days=1))
    assert section(store, cfg, NOW).nudge.left_out == []


def test_the_api_carries_what_was_left_out(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    store = app.state.store
    wait = cfg.ui.followups.question_after_days
    long_ago = datetime.now(UTC) - timedelta(days=wait + 5)
    sec = next(s for s in sections(store, cfg, long_ago.date()) if s.person == editor_id())
    mark_sent(store, cfg, editor_id(), sent_text=sec.message, now=long_ago)
    qid = next(q["id"] for q in sec.questions)
    rec = store.read().get("question", qid)
    with store.transaction() as tx:
        tx.update("question", qid, {"status": "answered"}, _PM, read_version=rec.version)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        found = next(s for s in client.get("/api/followups").json() if s["person"] == editor_id())
        left = found["nudge"]["left_out"]
        assert [(x["kind"], x["id"]) for x in left] == [("question", qid)]
        assert left[0]["text"] and left[0]["on"]


# ---- the suggested escalation --------------------------------------------------------------------------------------


def chased_twice(env):
    """Two follow-ups went out and the wait ran its length again with no answer; returns the day it is now."""
    _, cfg, store = env
    rule = cfg.ui.followups
    sent_a_while_ago(env, rule.question_after_days + 2)
    day = NOW
    for _ in range(2):
        nudge = section(store, cfg, day).nudge
        mark_followed_up(store, cfg, editor_id(), nudge.question_ids, nudge.action_ids, sent_text=nudge.text, now=day)
        day = day + timedelta(days=rule.question_after_days)
    return day


def escalations(ws, store, cfg, now):
    return [line for line in queue(ws, store, cfg, now) if line.kind == "escalate"]


def test_after_a_second_follow_up_with_no_answer_today_suggests_one_escalation_for_the_person(env):
    ws, cfg, store = env
    day = chased_twice(env)
    found = escalations(ws, store, cfg, day)
    assert len(found) == 1
    line = found[0]
    assert (line.group, line.person) == ("send", editor_id())
    assert (line.questions or line.actions) and line.text
    assert line.count == 2, "the number of follow-ups it has had"
    # The same item is not also a follow-up line: asking again would be the third.
    assert not [
        n
        for n in queue(ws, store, cfg, day)
        if n.kind == "nudge" and set(n.questions + n.actions) & set(line.questions + line.actions)
    ]


def test_one_follow_up_is_not_yet_an_escalation(env):
    ws, cfg, store = env
    rule = cfg.ui.followups
    sent_a_while_ago(env, rule.question_after_days + 2)
    nudge = section(store, cfg, NOW).nudge
    mark_followed_up(store, cfg, editor_id(), nudge.question_ids, nudge.action_ids, sent_text=nudge.text, now=NOW)
    later = NOW + timedelta(days=rule.question_after_days)
    assert escalations(ws, store, cfg, later) == []
    assert [n for n in queue(ws, store, cfg, later) if n.kind == "nudge"], "it is the second follow-up still"


def test_it_waits_for_the_wait_to_run_again_after_the_second_follow_up(env):
    ws, cfg, store = env
    day = chased_twice(env)
    assert escalations(ws, store, cfg, day - timedelta(days=1)) == []


def test_it_is_a_setting_and_zero_turns_it_off(env):
    ws, cfg, store = env
    day = chased_twice(env)
    off = ws.config(env={}, flags={"ui.followups.escalate_after_chases": 0})
    assert escalations(ws, store, off, day) == []
    assert [n for n in queue(ws, store, off, day) if n.kind == "nudge"]


def test_an_answered_item_is_no_longer_suggested(env):
    ws, cfg, store = env
    day = chased_twice(env)
    line = escalations(ws, store, cfg, day)[0]
    for qid in line.questions:
        close_question(store, qid, "answered", day)
    for aid in line.actions:
        rec = store.read().get("action", aid)
        with store.transaction() as tx:
            tx.update("action", aid, {"status": "done"}, _PM, read_version=rec.version)
    assert all(
        set(l2.questions + l2.actions) != set(line.questions + line.actions) for l2 in escalations(ws, store, cfg, day)
    )
