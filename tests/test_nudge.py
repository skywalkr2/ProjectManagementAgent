"""A drafted nudge: one message per person, built from a template with no AI run (design 7.5, designer answer 36).

It lists only what has gone unanswered as long as the follow-up rule says, numbered, with the date of the first message
and an overdue date said as a fact. Marking it sent records a chase on each item and restarts the wait without losing
when it was first asked. A second nudge is shorter. Names and thresholds come from the fixtures and the settings.
"""

from datetime import UTC, datetime, timedelta

import pytest

from engine.followups import FollowUpError, mark_followed_up, mark_sent, sections, unmark_followed_up
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
_WRITE = WriteContext(actor="pm", trust="trusted", op="test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()


def editor():
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == "Editor")


def editor_id():
    return editor()["id"]


def section(store, cfg, on: datetime):
    return next(s for s in sections(store, cfg, on.date()) if s.person == editor_id())


def sent_a_while_ago(env, days: int):
    """The editor was sent everything waiting for them, `days` days before NOW; returns the message that went."""
    _, cfg, store = env
    sec = section(store, cfg, NOW - timedelta(days=days))
    mark_sent(store, cfg, editor_id(), sent_text=sec.message, now=NOW - timedelta(days=days))
    return sec


def test_a_nudge_is_empty_until_something_has_waited_as_long_as_the_rule_says(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait - 1)
    assert section(store, cfg, NOW).nudge is None


def test_a_nudge_lists_what_is_due_numbered_with_the_first_date_and_asks_for_the_smallest_reply(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    first = sent_a_while_ago(env, wait + 2)
    sec = section(store, cfg, NOW)
    nudge = sec.nudge
    assert nudge is not None and nudge.round == 1
    words = cfg.language.messages
    sent_on = (NOW - timedelta(days=wait + 2)).date().strftime(words.date_format)
    lines = nudge.text.splitlines()
    assert lines[0] == words.greeting.format(first_name=editor()["full_name"].split()[0])
    assert sent_on in nudge.text
    assert lines[-1] == words.closing
    assert words.nudge_ask in nudge.text or words.nudge_ask_one in nudge.text
    due_questions = [q for q in sec.questions if q["chase_due"]]
    for n, q in enumerate(due_questions, 1):
        assert (f"{n}. " if len(nudge.question_ids) + len(nudge.action_ids) > 1 else "") + q["title"] in nudge.text
    assert set(nudge.question_ids) == {q["id"] for q in due_questions}
    # Nothing in it is a new item: every title was in the first message.
    assert all(q["title"] in first.message for q in due_questions)
    assert nudge.text != first.message


def test_an_overdue_due_date_is_said_as_a_fact(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    action = section(store, cfg, NOW).actions[0]
    rec = store.read().get("action", action["id"])
    past = (NOW - timedelta(days=3)).date()
    with store.transaction() as tx:
        tx.update("action", action["id"], {"due": past.isoformat()}, _WRITE, read_version=rec.version)
    sent_a_while_ago(env, wait + 2)
    nudge = section(store, cfg, NOW).nudge
    assert nudge is not None and action["id"] in nudge.action_ids
    words = cfg.language.messages
    assert words.nudge_overdue.format(date=past.strftime(words.date_format)) in nudge.text


def test_marking_a_nudge_sent_restarts_the_wait_and_keeps_when_it_was_first_asked(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait + 2)
    first_sent = (NOW - timedelta(days=wait + 2)).date().isoformat()
    nudge = section(store, cfg, NOW).nudge
    done = mark_followed_up(
        store, cfg, editor_id(), nudge.question_ids, nudge.action_ids, sent_text=nudge.text, now=NOW
    )
    assert done["questions"] == len(nudge.question_ids) and done["actions"] == len(nudge.action_ids)
    after = section(store, cfg, NOW)
    for q in after.questions:
        if q["id"] in nudge.question_ids:
            assert q["sent"] == first_sent, "first asked is kept"
            assert q["followed_up"] == NOW.date().isoformat() and q["chases"] == 1
            assert q["waiting_days"] == 0 and not q["chase_due"], "the wait starts again"
    assert after.nudge is None
    assert store.read().list("signal") == [], "an unedited nudge teaches nothing"


def test_a_second_nudge_is_shorter_and_asks_who_else_to_ask(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    sent_a_while_ago(env, rule.question_after_days + 2)
    first = section(store, cfg, NOW).nudge
    mark_followed_up(store, cfg, editor_id(), first.question_ids, first.action_ids, sent_text=first.text, now=NOW)
    later = NOW + timedelta(days=rule.question_after_days)
    second = section(store, cfg, later).nudge
    assert second is not None and second.round == 2
    words = cfg.language.messages
    assert words.nudge_second_ask in second.text and words.nudge_second_intro.split("{")[0] in second.text
    assert len(second.question_ids) + len(second.action_ids) <= rule.second_nudge_items
    assert (
        len(second.text) < len(first.text) or len(first.question_ids) + len(first.action_ids) <= rule.second_nudge_items
    )


def test_an_edited_nudge_records_the_same_signal_as_an_edited_message_and_undo_takes_it_back(env):
    _, cfg, store = env
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait + 2)
    nudge = section(store, cfg, NOW).nudge
    done = mark_followed_up(
        store,
        cfg,
        editor_id(),
        nudge.question_ids,
        nudge.action_ids,
        sent_text=nudge.text + "\nP.S. no rush",
        now=NOW,
    )
    assert [s.data["kind"] for s in store.read().list("signal")] == ["draft_edited"]
    unmark_followed_up(
        store,
        editor_id(),
        nudge.question_ids,
        nudge.action_ids,
        on=done["on"],
        previous_told=done["previous_told"],
        signal_at=done["signal_at"],
    )
    back = section(store, cfg, NOW)
    assert back.nudge is not None and set(back.nudge.question_ids) == set(nudge.question_ids)
    assert all(q["chases"] == 0 for q in back.questions)
    assert all(a["told"] is not None for a in back.actions if a["id"] in nudge.action_ids)


def test_what_is_not_waiting_cannot_be_marked_followed_up(env):
    _, cfg, store = env
    open_question = next(q for q in store.read().list("question") if q.data["status"] == "open" and q.data["to"])
    with pytest.raises(FollowUpError):
        mark_followed_up(store, cfg, open_question.data["to"], [open_question.id], [], sent_text="x", now=NOW)


def test_the_nudge_words_are_settings(env):
    ws, _, store = env
    cfg = ws.config(
        env={},
        flags={
            "language.messages.nudge_ask": "Any word is fine.",
            "language.messages.nudge_ask_one": "Any word is fine.",
        },
    )
    wait = cfg.ui.followups.question_after_days
    sent_a_while_ago(env, wait + 2)
    assert "Any word is fine." in section(store, cfg, NOW).nudge.text


def test_the_api_offers_the_nudge_records_it_and_takes_it_back(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, "test-token-value", ui_dist=tmp_path / "no-ui")
    store = app.state.store
    long_ago = datetime.now(UTC) - timedelta(days=cfg.ui.followups.question_after_days + 5)
    mark_sent(store, cfg, editor_id(), sent_text=section(store, cfg, long_ago).message, now=long_ago)
    with TestClient(app, headers={"Authorization": "Bearer test-token-value"}) as client:
        found = next(s for s in client.get("/api/followups").json() if s["person"] == editor_id())
        nudge = found["nudge"]
        assert nudge["round"] == 1 and nudge["question_ids"] and nudge["text"]
        assert all(q["chases"] == 0 and q["followed_up"] is None for q in found["questions"])
        done = client.post(
            f"/api/followups/{editor_id()}/followed-up",
            json={"text": nudge["text"], "question_ids": nudge["question_ids"], "action_ids": nudge["action_ids"]},
        )
        assert done.status_code == 200 and done.json()["questions"] == len(nudge["question_ids"])
        after = next(s for s in client.get("/api/followups").json() if s["person"] == editor_id())
        assert after["nudge"] is None
        assert all(q["chases"] == 1 for q in after["questions"] if q["id"] in nudge["question_ids"])
        back = client.post(f"/api/followups/{editor_id()}/unfollow", json={**done.json()})
        assert back.status_code == 200
        again = next(s for s in client.get("/api/followups").json() if s["person"] == editor_id())
        assert again["nudge"]["question_ids"] == nudge["question_ids"]
        refused = client.post(
            f"/api/followups/{editor_id()}/followed-up", json={"question_ids": ["Q-NOPE"], "action_ids": []}
        )
        assert refused.status_code in (400, 409, 422)
