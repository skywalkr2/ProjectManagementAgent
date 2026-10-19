"""An action on hold isn't due, and one rule says when something sent is due a follow-up (design 6.9, 5.1).

Dates and thresholds come from the config, never written out here.
"""

from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.config.loader import load_config
from engine.followups import (
    FollowUpError,
    follow_up_due,
    put_on_hold,
    restore_hold,
    sections,
    take_off_hold,
)
from engine.storage import Store, WriteContext
from engine.today import todo
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "test-token-value"
NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_WRITE = WriteContext(actor="pm", trust="trusted", op="test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()


def _set(store, action_id, **changes):
    rec = store.read().get("action", action_id)
    with store.transaction() as tx:
        tx.update("action", action_id, changes, _WRITE, read_version=rec.version)


def _told(env, *, told_days_ago, due_in_days=None, on_hold=None, owner_is_pm=False):
    """An open action told to its owner `told_days_ago` days before TODAY, due `due_in_days` days after it."""
    _, cfg, store = env
    pm = cfg.workspace.user.person
    action = next(
        a
        for a in store.read().list("action")
        if a.data["status"] == "open" and a.data.get("owners") and (a.data["owners"][0]["person"] == pm) == owner_is_pm
    )
    owner = action.data["owners"][0]["person"]
    change = {
        "told": {owner: (TODAY - timedelta(days=told_days_ago)).isoformat()},
        "due": None if due_in_days is None else (TODAY + timedelta(days=due_in_days)).isoformat(),
    }
    if on_hold:
        change["on_hold"] = {"waiting_for": on_hold, "since": TODAY.isoformat()}
    _set(store, action.id, **change)
    return action.id, owner


def _row(env, action_id, owner):
    _, cfg, store = env
    section = next(s for s in sections(store, cfg, TODAY) if s.person == owner)
    return next(a for a in section.actions if a["id"] == action_id)


# ---- the rule, branch by branch -------------------------------------------------------------------------------------


def test_a_told_action_due_far_ahead_is_not_chased(env):
    _, cfg, _ = env
    rule = cfg.ui.followups
    far = rule.action_due_within_days + 25
    action_id, owner = _told(env, told_days_ago=rule.question_after_days + 20, due_in_days=far)
    assert not _row(env, action_id, owner)["chase_due"]


def test_a_told_action_due_soon_is_chased_once_it_has_waited(env):
    _, cfg, _ = env
    rule = cfg.ui.followups
    action_id, owner = _told(env, told_days_ago=rule.question_after_days, due_in_days=rule.action_due_within_days)
    assert _row(env, action_id, owner)["chase_due"]
    just_outside = _told(env, told_days_ago=rule.question_after_days, due_in_days=rule.action_due_within_days + 1)
    assert not _row(env, *just_outside)["chase_due"]


def test_a_told_action_just_sent_is_not_chased_even_when_due_soon(env):
    _, cfg, _ = env
    rule = cfg.ui.followups
    action_id, owner = _told(env, told_days_ago=rule.question_after_days - 1, due_in_days=1)
    assert not _row(env, action_id, owner)["chase_due"]


def test_an_overdue_told_action_is_chased(env):
    _, cfg, _ = env
    action_id, owner = _told(env, told_days_ago=cfg.ui.followups.question_after_days, due_in_days=-3)
    assert _row(env, action_id, owner)["chase_due"]


def test_an_action_on_hold_is_never_chased(env):
    _, cfg, _ = env
    rule = cfg.ui.followups
    action_id, owner = _told(
        env, told_days_ago=rule.undated_after_days + 30, due_in_days=-10, on_hold="the supplier's answer"
    )
    row = _row(env, action_id, owner)
    assert row["on_hold"] == "the supplier's answer" and not row["chase_due"]
    assert row["due"] is not None, "the old due date is kept"


def test_an_undated_told_action_is_chased_after_the_undated_wait_and_not_before(env):
    _, cfg, _ = env
    wait = cfg.ui.followups.undated_after_days
    action_id, owner = _told(env, told_days_ago=wait - 1)
    assert not _row(env, action_id, owner)["chase_due"]
    _set(env[2], action_id, told={owner: (TODAY - timedelta(days=wait)).isoformat()})
    assert _row(env, action_id, owner)["chase_due"]


def test_a_sent_question_is_chased_after_the_question_wait_and_not_before(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    question = next(q for q in store.read().list("question") if q.data["status"] == "open" and q.data["to"])
    person = question.data["to"]

    def check(days_ago):
        _set_question(store, question.id, status="sent", sent_at=(NOW - timedelta(days=days_ago)).isoformat())
        section = next(s for s in sections(store, cfg, TODAY) if s.person == person)
        return next(q for q in section.questions if q["id"] == question.id)["chase_due"]

    assert not check(wait - 1)
    assert check(wait)


def _set_question(store, question_id, **changes):
    rec = store.read().get("question", question_id)
    with store.transaction() as tx:
        tx.update("question", question_id, changes, _WRITE, read_version=rec.version)


def test_the_rule_reads_every_threshold_from_the_settings(env):
    ws, _, _ = env
    cfg = ws.config(
        env={},
        flags={
            "ui.followups.action_due_within_days": 2,
            "ui.followups.undated_after_days": 30,
            "ui.followups.question_after_days": 1,
        },
    )
    due = TODAY + timedelta(days=2)
    assert follow_up_due(cfg, TODAY, waiting_days=1, action=True, due=due)
    assert not follow_up_due(cfg, TODAY, waiting_days=1, action=True, due=due + timedelta(days=1))
    assert not follow_up_due(cfg, TODAY, waiting_days=29, action=True)
    assert follow_up_due(cfg, TODAY, waiting_days=30, action=True)
    assert follow_up_due(cfg, TODAY, waiting_days=1) and not follow_up_due(cfg, TODAY, waiting_days=0)
    assert not follow_up_due(cfg, TODAY, waiting_days=None, action=True, due=due)


def test_the_old_nudge_setting_is_read_as_the_question_wait(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ui.yaml"
    data = yaml.safe_load(path.read_text())
    data["followups"].pop("question_after_days")
    data["today"]["nudge_after_days"] = 9
    path.write_text(yaml.safe_dump(data))
    assert load_config(ws.config_dir, env={}).ui.followups.question_after_days == 9
    data["followups"]["question_after_days"] = 2  # the new name wins when both are set
    path.write_text(yaml.safe_dump(data))
    assert load_config(ws.config_dir, env={}).ui.followups.question_after_days == 2


# ---- on hold --------------------------------------------------------------------------------------------------------


def test_putting_an_action_on_hold_records_what_it_waits_for_and_a_signal_and_taking_it_off_keeps_the_due_date(env):
    _, cfg, store = env
    action_id, _ = _told(env, told_days_ago=1, due_in_days=3)
    before = store.read().get("action", action_id).data
    assert put_on_hold(store, action_id, "  the  quote   from the printer ", now=NOW) is None
    held = store.read().get("action", action_id).data
    assert held["on_hold"] == {"waiting_for": "the quote from the printer", "since": TODAY.isoformat()}
    assert held["due"] == before["due"]
    previous = take_off_hold(store, action_id, now=NOW)
    assert previous["waiting_for"] == "the quote from the printer"
    freed = store.read().get("action", action_id).data
    assert freed["on_hold"] is None and freed["due"] == before["due"]
    signals = [(s.data["kind"], s.data["refs"], s.data["note"]) for s in store.read().list("signal")]
    assert signals == [
        ("put_on_hold", [action_id], "the quote from the printer"),
        ("taken_off_hold", [action_id], "the quote from the printer"),
    ]


def test_a_hold_needs_words_and_an_open_action_and_undoing_it_records_no_signal(env):
    _, cfg, store = env
    action_id, _ = _told(env, told_days_ago=1, due_in_days=3)
    with pytest.raises(FollowUpError):
        put_on_hold(store, action_id, "   ", now=NOW)
    with pytest.raises(FollowUpError):
        take_off_hold(store, action_id, now=NOW)  # not on hold
    previous = put_on_hold(store, action_id, "an answer", now=NOW)
    restore_hold(store, action_id, previous)
    assert store.read().get("action", action_id).data["on_hold"] is None
    assert [s.data["kind"] for s in store.read().list("signal")] == ["put_on_hold"]
    _set(store, action_id, status="done", done_by=[], reported_by=None)
    with pytest.raises(FollowUpError):
        put_on_hold(store, action_id, "an answer", now=NOW)


def test_an_action_on_hold_is_never_overdue_on_the_to_do_list_or_in_todays_queue(env):
    ws, cfg, store = env
    me = cfg.workspace.user.person
    mine = next(
        a
        for a in store.read().list("action")
        if a.data["status"] == "open" and any(o["person"] == me for o in a.data["owners"])
    )
    _set(store, mine.id, due=(TODAY - timedelta(days=4)).isoformat())
    assert next(t for t in todo(store, cfg, NOW) if t.action == mine.id).overdue

    def overdue_lines():
        return [line for line in queue(ws, store, cfg, NOW) if line.kind == "overdue"]

    assert mine.id in overdue_lines()[0].actions
    put_on_hold(store, mine.id, "the legal review", now=NOW)
    item = next(t for t in todo(store, cfg, NOW) if t.action == mine.id)
    assert not item.overdue and item.on_hold == "the legal review" and item.due == TODAY - timedelta(days=4)
    assert all(mine.id not in line.actions for line in overdue_lines())


# ---- Today and Follow-ups agree --------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.store, cfg


def test_today_and_the_follow_ups_view_agree_on_what_is_due_a_follow_up_and_on_hold_leaves_both(api):
    client, base, store, cfg = api
    rule = cfg.ui.followups
    today = datetime.now(UTC).date()
    pm = cfg.workspace.user.person
    candidates = [
        a
        for a in store.read().list("action")
        if a.data["status"] == "open" and a.data.get("owners") and a.data["owners"][0]["person"] != pm
    ]
    owner = candidates[0].data["owners"][0]["person"]
    with store.transaction() as tx:
        extra = tx.create(
            "action", {"text": "Check the proof", "owners": [{"person": owner}], "status": "open"}, _WRITE
        )
    mine = [candidates[0], store.read().get("action", extra.id)]
    told = (today - timedelta(days=rule.undated_after_days + 3)).isoformat()
    due = [
        (today - timedelta(days=2)).isoformat(),
        (today + timedelta(days=rule.action_due_within_days + 60)).isoformat(),
    ]
    for action, when in zip(mine, due, strict=True):
        _set(store, action.id, told={owner: told}, due=when)
    chased, calm = mine[0].id, mine[1].id

    def view():
        rows = {a["id"]: a for s in client.get(f"{base}/followups").json() for a in s["actions"]}
        # Today asks for the chase on one line: the follow-up line, or, once the day has passed, the promise's own.
        lines = client.get(f"{base}/today/queue").json()
        chase = [a for line in lines if line["key"] == f"nudge:{owner}" for a in line["actions"]]
        chase += [a for line in lines if line["kind"] == "promise" and line["person"] == owner for a in line["actions"]]
        return rows, chase

    rows, nudged = view()
    assert rows[chased]["chase_due"] and not rows[calm]["chase_due"]
    assert nudged == [chased]
    # Putting it on hold through the API takes it out of both, and the Follow-ups row says what it waits for.
    put = client.post(f"{base}/actions/{chased}/hold", json={"waiting_for": "the supplier"})
    assert put.status_code == 200 and put.json()["previous"] is None
    rows, nudged = view()
    assert not rows[chased]["chase_due"] and rows[chased]["on_hold"] == "the supplier" and nudged == []
    # Undo puts it back exactly, with no further signal; taking it off is a signal of its own.
    undone = client.post(f"{base}/actions/{chased}/hold/restore", json={"hold": put.json()["previous"]})
    assert undone.status_code == 200
    assert view()[1] == [chased]
    assert [s.data["kind"] for s in store.read().list("signal")] == ["put_on_hold"]
    client.post(f"{base}/actions/{chased}/hold", json={"waiting_for": "the supplier"})
    off = client.post(f"{base}/actions/{chased}/unhold")
    assert off.status_code == 200 and off.json()["previous"]["waiting_for"] == "the supplier"
    assert view()[1] == [chased]
    assert client.post(f"{base}/actions/{chased}/unhold").status_code == 409


def test_the_to_do_list_view_says_what_a_held_action_waits_for(api):
    client, base, store, cfg = api
    pm = cfg.workspace.user.person
    mine = next(
        a
        for a in store.read().list("action")
        if a.data["status"] == "open" and any(o["person"] == pm for o in a.data["owners"])
    )
    _set(store, mine.id, due=(datetime.now(UTC).date() - timedelta(days=5)).isoformat())
    row = next(t for t in client.get(f"{base}/today/todo").json() if t["action"] == mine.id)
    assert row["overdue"] and row["on_hold"] is None
    client.post(f"{base}/actions/{mine.id}/hold", json={"waiting_for": "a reply"})
    row = next(t for t in client.get(f"{base}/today/todo").json() if t["action"] == mine.id)
    assert not row["overdue"] and row["on_hold"] == "a reply" and row["due"]
