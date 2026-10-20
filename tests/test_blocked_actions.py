"""A blocked action is an action on hold that names its blocker: a person, an action or a question (design 6.9).

It stays one state (a hold), is never due or chased, and is counted by `blocked_actions`, which the Top priorities list
reads. A question tie shows "Waits on: ..." and, once that question is answered, the to-do is unblocked and first on
the rail. Names and ids come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.applier import undo
from engine.blocked import blocked_actions
from engine.followups import FollowUpError, put_on_hold, restore_hold, sections, take_off_hold
from engine.names import People
from engine.storage import Store, WriteContext
from engine.today import todo, zone
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_hold_drop_fold import an_action, data, from_input, hold_op

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
TOKEN = "blocked-token"
_WRITE = WriteContext(actor="pm", trust="trusted", op="test.blocked")


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


def _set(store, kind, record_id, **changes):
    rec = store.read().get(kind, record_id)
    with store.transaction() as tx:
        tx.update(kind, record_id, changes, _WRITE, read_version=rec.version)


def _two_actions(cfg, store):
    """A to-do of the person's own and a different open action that can block it."""
    mine = an_action(cfg, mine=True)
    other = an_action(cfg, mine=False)
    return mine, other


def _other_person(cfg, store):
    pm = cfg.workspace.user.person
    return next(p.id for p in store.read().list("person") if p.id != pm)


def _question_to(store, person, **more):
    with store.transaction() as tx:
        q = tx.create(
            "question",
            {"to": person, "title": "Can proof copies ship by the target date?", "status": "sent", **more},
            _WRITE,
        )
    return q.id


# ---- a hold names its blocker ---------------------------------------------------------------------------------------


def test_a_hold_can_name_a_person_and_the_words_default_to_their_name(env):
    _, cfg, store = env
    mine, _ = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    assert put_on_hold(store, mine, on=who, now=NOW) is None
    hold = data(store, "action", mine)["on_hold"]
    assert hold["on"] == who
    assert hold["waiting_for"] == People(store, cfg).name(who)
    assert blocked_actions(store).total == 1


def test_a_hold_can_name_an_action_and_the_words_default_to_its_text(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    put_on_hold(store, mine, "  the  second part ", on=other, now=NOW)
    hold = data(store, "action", mine)["on_hold"]
    assert hold["on"] == other and hold["waiting_for"] == "the second part"
    put_on_hold(store, mine, on=other, now=NOW)
    assert data(store, "action", mine)["on_hold"]["waiting_for"] == data(store, "action", other)["text"]


def test_a_blocker_must_exist_be_a_person_an_action_or_a_question_and_not_the_action_itself(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    for bad in ("PER-999", "ACT-999", "Q-999", "PRJ-1", mine):
        with pytest.raises(FollowUpError):
            put_on_hold(store, mine, "words", on=bad, now=NOW)
    with pytest.raises(FollowUpError):
        put_on_hold(store, mine, "", now=NOW)  # no words and no blocker
    assert data(store, "action", mine).get("on_hold") is None


def test_the_blocked_count_is_by_project_and_in_all_and_leaves_out_holds_with_only_words(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    assert blocked_actions(store).total == 0
    put_on_hold(store, mine, "the legal review", now=NOW)  # words only: on hold, not blocked
    assert blocked_actions(store).total == 0
    put_on_hold(store, mine, on=who, now=NOW)
    project = data(store, "action", mine).get("project")
    count = blocked_actions(store)
    assert count.total == 1 and count.by_project == {project: 1}
    put_on_hold(store, other, on=mine, now=NOW)
    assert blocked_actions(store).total == 2
    take_off_hold(store, mine, now=NOW)
    assert blocked_actions(store).total == 1


def test_an_action_blocked_by_a_finished_action_or_an_answered_question_no_longer_counts(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    put_on_hold(store, mine, on=other, now=NOW)
    asked = _question_to(store, who)
    third = next(a.id for a in store.read().list("action") if a.id not in (mine, other) and a.data["status"] == "open")
    put_on_hold(store, third, on=asked, now=NOW)
    assert blocked_actions(store).total == 2
    _set(store, "action", other, status="done", done_by=[], reported_by=None)
    _set(store, "question", asked, status="answered", answer="Yes")
    assert blocked_actions(store).total == 0


def test_undoing_a_blocked_hold_puts_the_old_hold_back_and_records_no_signal(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    previous = put_on_hold(store, mine, "first words", now=NOW)
    assert previous is None
    previous = put_on_hold(store, mine, on=other, now=NOW)
    assert previous["waiting_for"] == "first words" and previous.get("on") is None
    restore_hold(store, mine, previous)
    assert data(store, "action", mine)["on_hold"].get("on") is None
    restore_hold(store, mine, None)
    assert data(store, "action", mine)["on_hold"] is None
    assert [s.data["kind"] for s in store.read().list("signal")] == ["put_on_hold", "put_on_hold"]


def test_a_blocker_is_kept_from_deletion_by_the_reference_guard(env):
    from engine.records import referrers

    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    put_on_hold(store, mine, on=other, now=NOW)
    assert ("action", mine) in referrers(store.read(), "action", other)
    who = _other_person(cfg, store)
    put_on_hold(store, mine, on=who, now=NOW)
    assert ("action", mine) in referrers(store.read(), "person", who)


# ---- the assistant's put-on-hold op ----------------------------------------------------------------------------------


def test_the_assistants_hold_op_can_name_its_blocker_and_undo_removes_it(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    cs_id, result = from_input(store, cfg, [{**hold_op(other), "on": mine}])
    assert result == ["applied"]
    assert data(store, "action", other)["on_hold"]["on"] == mine
    assert blocked_actions(store).total == 1
    assert undo(store, cs_id).restored == [0]
    assert data(store, "action", other)["on_hold"] is None


def test_the_assistants_hold_op_is_refused_for_a_blocker_that_does_not_exist_or_is_the_action_itself(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    _, result = from_input(store, cfg, [{**hold_op(other), "on": "ACT-999"}, {**hold_op(other), "on": other}])
    assert result == ["refused", "refused"]
    assert data(store, "action", other).get("on_hold") is None


# ---- the rows ------------------------------------------------------------------------------------------------------


def test_the_to_do_list_says_who_or_what_a_blocked_action_waits_on(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    put_on_hold(store, mine, on=who, now=NOW)
    item = next(t for t in todo(store, cfg, NOW) if t.action == mine)
    assert item.on_hold and item.blocker.kind == "person" and item.blocker.name == People(store, cfg).name(who)
    assert not item.overdue
    put_on_hold(store, mine, on=other, now=NOW)
    item = next(t for t in todo(store, cfg, NOW) if t.action == mine)
    assert item.blocker.kind == "action" and item.blocker.name == data(store, "action", other)["text"]


def test_a_question_tie_names_the_question_who_was_asked_and_when_it_was_sent(env):
    _, cfg, store = env
    mine, _ = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    asked = _question_to(store, who, sent_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC).isoformat())
    put_on_hold(store, mine, on=asked, now=NOW)
    blocker = next(t for t in todo(store, cfg, NOW) if t.action == mine).blocker
    assert (blocker.kind, blocker.id, blocker.state) == ("question", asked, "waiting")
    assert blocker.name == data(store, "question", asked)["title"]
    assert blocker.who == People(store, cfg).name(who) and str(blocker.sent) == "2026-10-05"


def test_an_answered_question_unblocks_the_to_do_and_puts_it_first_with_who_answered_and_when(env):
    _, cfg, store = env
    mine, _ = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    # The to-do is overdue by its own date, and another to-do of the person is due earlier than this one's rank.
    _set(store, "action", mine, due=(TODAY - timedelta(days=3)).isoformat())
    asked = _question_to(store, who, sent_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC).isoformat())
    put_on_hold(store, mine, on=asked, now=NOW)
    first = todo(store, cfg, NOW)
    assert next(t for t in first if t.action == mine).on_hold and not next(t for t in first if t.action == mine).overdue
    _set(store, "question", asked, status="answered", answer="Yes, by the 3rd")
    after = todo(store, cfg, datetime.now(UTC))
    item = next(t for t in after if t.action == mine)
    assert after[0].action == mine, "an unblocked to-do goes to the top"
    assert item.blocker.state == "answered" and item.blocker.who == People(store, cfg).name(who)
    assert item.blocker.answered == datetime.now(zone(cfg)).date()
    assert item.on_hold is None and item.overdue, "once unblocked it is due again by its own date"
    # Taking it off hold clears the note; nothing else changes.
    take_off_hold(store, mine, now=NOW)
    cleared = next(t for t in todo(store, cfg, datetime.now(UTC)) if t.action == mine)
    assert cleared.blocker is None


def test_the_follow_ups_row_carries_the_blocker_and_a_blocked_action_is_never_chased(env):
    _, cfg, store = env
    mine, other = _two_actions(cfg, store)
    owner = data(store, "action", other)["owners"][0]["person"]
    _set(store, "action", other, told={owner: (TODAY - timedelta(days=30)).isoformat()}, due=None)
    put_on_hold(store, other, on=mine, now=NOW)
    section = next(s for s in sections(store, cfg, TODAY) if s.person == owner)
    row = next(a for a in section.actions if a["id"] == other)
    assert row["blocker"]["kind"] == "action" and row["blocker"]["name"] == data(store, "action", mine)["text"]
    assert not row["chase_due"]


# ---- through the API ------------------------------------------------------------------------------------------------


def test_the_api_puts_an_action_on_hold_for_a_blocker_with_undo_and_the_views_show_it(api):
    client, base, store, cfg = api
    mine, other = _two_actions(cfg, store)
    who = _other_person(cfg, store)
    put = client.post(f"{base}/actions/{mine}/hold", json={"on": who})
    assert put.status_code == 200 and put.json()["previous"] is None
    row = next(t for t in client.get(f"{base}/today/todo").json() if t["action"] == mine)
    assert row["blocker"]["kind"] == "person" and row["blocker"]["id"] == who and row["on_hold"]
    again = client.post(f"{base}/actions/{mine}/hold", json={"on": other})
    assert again.json()["previous"]["on"] == who
    undone = client.post(f"{base}/actions/{mine}/hold/restore", json={"hold": again.json()["previous"]})
    assert undone.status_code == 200 and data(store, "action", mine)["on_hold"]["on"] == who
    assert client.post(f"{base}/actions/{mine}/hold", json={}).status_code == 409
    assert client.post(f"{base}/actions/{mine}/hold", json={"on": "ACT-999"}).status_code in (404, 409)
    assert client.post(f"{base}/actions/{mine}/hold", json={"waiting_for": "x", "on": who}).status_code == 200
