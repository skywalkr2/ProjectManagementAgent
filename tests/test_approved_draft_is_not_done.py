"""An approved draft isn't done (design 6.35; the functional designer's answer F19, B-7).

Approving or copying the draft the assistant made for an action leaves the action open: a nudge isn't completion. The
approved text is kept as a copy (the message the person means to send), which ends the action when the sent folder
shows the message went out (the person's own sent mail applies at once) and otherwise asks "Did your message go out?"
after `steward.sent_match.ask_after_days`. The person can end it themselves at any time. Names and ids come from the
fixtures."""

from __future__ import annotations

from datetime import timedelta

import pytest

from engine import sent_version
from engine.applier import apply_as_person
from engine.storage import Store
from engine.texts import versions
from tests import test_sent_version as base
from tests.test_sent_version import (
    _TEST,
    EDITOR,
    NOW,
    a_sent_folder_being_read,
    copies,
    edited_signals,
    me,
    sent,
    settings,
    unsent,
)
from tests.test_sent_version import match as _match

DRAFT = "The interior proofs ship on November 3 (the printer's published schedule)."


@pytest.fixture
def env(tmp_path):
    ws, cfg = base._build(tmp_path, with_sent_folder=False)
    store = Store(ws.db_path, cfg=cfg)
    base._addresses(store, cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def env_sent(tmp_path):
    ws, cfg = base._build(tmp_path, with_sent_folder=True)
    store = Store(ws.db_path, cfg=cfg)
    base._addresses(store, cfg)
    yield ws, cfg, store
    store.close()


def match(env):
    return _match(env)


def work_action(store, cfg, *, promised_to=(EDITOR["id"],)) -> str:
    store.clock = lambda: (NOW - timedelta(hours=5)).isoformat()  # what is done in a test happened five hours ago
    with store.transaction() as tx:
        return tx.create(
            "action",
            {
                "text": "Tell the editor when the proofs ship",
                "owners": [{"person": me(cfg)}],
                "promised_to": list(promised_to),
                "basis": "said",
            },
            _TEST,
        ).id


def propose(store, cfg, action: str, text: str = DRAFT) -> str:
    """A draft of the action's work waiting for the person's review; returns its version id."""
    apply_as_person(
        store,
        cfg,
        [{"op": "text.propose", "record": {"kind": "action", "id": action}, "field": "work", "text": text}],
        "A draft",
    )
    return versions(store.read(), "action", action, "work")[-1].id


def approve(store, cfg, version_id: str) -> None:
    current = store.read().get("text_version", version_id)
    apply_as_person(
        store, cfg, [{"op": "text.accept", "version": version_id, "read_version": current.version}], "Approved"
    )


def test_approving_the_draft_leaves_the_action_open_and_keeps_the_text_as_a_copy(env):
    _, cfg, store = env
    action = work_action(store, cfg)
    approve(store, cfg, propose(store, cfg, action))
    kept = store.read().get("action", action).data
    assert kept["status"] == "open" and kept["done_by"] == [] and kept["reported_by"] is None
    (found,) = copies(store)
    assert (found.data["kind"], found.data["person"], found.data["actions"]) == ("work", EDITOR["id"], [action])
    assert found.data["text"].strip() == DRAFT and found.data["sent_source"] is None


def test_copying_the_draft_keeps_the_same_copy_and_copying_again_moves_it_forward(env):
    _, cfg, store = env
    action = work_action(store, cfg)
    version = propose(store, cfg, action)
    first = sent_version.keep_work(store, action, now=NOW - timedelta(hours=5))
    again = sent_version.keep_work(store, action, now=NOW - timedelta(hours=1))
    assert first == again and len(copies(store)) == 1
    assert store.read().get("action", action).data["status"] == "open"
    assert store.read().get("text_version", version).data["status"] == "pending", "copying doesn't approve it"


def test_a_draft_for_nobody_known_is_kept_as_a_copy_that_is_never_matched_and_the_action_stays_open(env):
    _, cfg, store = env
    action = work_action(store, cfg, promised_to=())
    approve(store, cfg, propose(store, cfg, action))
    (found,) = copies(store)
    assert found.data["person"] is None
    assert store.read().get("action", action).data["status"] == "open"


def test_the_sent_version_in_the_sent_folder_ends_the_action_at_once_as_the_persons_own_act(env):
    ws, cfg, store = env
    action = work_action(store, cfg)
    approve(store, cfg, propose(store, cfg, action))
    sent(env, to=EDITOR, body=DRAFT + "\n\nThanks.", at=NOW - timedelta(hours=1))
    assert match(env) == [copies(store)[0].id]
    ended = store.read().get("action", action).data
    assert ended["status"] == "done" and ended["done_by"] == [me(cfg)] and ended["reported_by"] == me(cfg)
    assert len(edited_signals(store)) == 1  # what they changed before sending is learned, as for any copy
    assert match(env) == []


def test_a_message_that_isnt_the_draft_ends_nothing(env):
    _, cfg, store = env
    action = work_action(store, cfg)
    approve(store, cfg, propose(store, cfg, action))
    sent(env, to=EDITOR, body="Lunch on Friday? I am free after noon.", at=NOW - timedelta(hours=1))
    assert match(env) == [] and store.read().get("action", action).data["status"] == "open"


def test_nothing_matching_sent_within_the_days_asks_did_your_message_go_out_and_the_action_stays_open(env_sent):
    ws, cfg, store = env_sent
    a_sent_folder_being_read(env_sent)
    action = work_action(store, cfg)
    propose(store, cfg, action)
    sent_version.keep_work(store, action, now=NOW - timedelta(days=settings(cfg).ask_after_days, hours=-1))
    assert unsent(env_sent) == []
    (line,) = unsent(env_sent, NOW + timedelta(hours=2))
    (found,) = copies(store)
    assert (line.person, line.sent_copy, line.actions) == (EDITOR["id"], found.id, [action])
    assert store.read().get("action", action).data["status"] == "open"


def test_answering_that_it_went_another_way_or_never_went_leaves_the_action_to_the_person(env_sent):
    ws, cfg, store = env_sent
    action = work_action(store, cfg)
    propose(store, cfg, action)
    sent_version.keep_work(store, action, now=NOW - timedelta(days=5))
    (found,) = copies(store)
    sent_version.settle(store, cfg, found.id, "not_sent", NOW)
    kept = store.read().get("action", action).data
    assert kept["status"] == "open" and kept["told"] == {}
    assert store.read().get("copy", found.id).data["settled"] == "not_sent"


def test_a_copy_whose_action_was_ended_by_the_person_is_not_asked_about(env_sent):
    ws, cfg, store = env_sent
    a_sent_folder_being_read(env_sent)
    action = work_action(store, cfg)
    propose(store, cfg, action)
    sent_version.keep_work(store, action, now=NOW - timedelta(days=5))
    assert len(unsent(env_sent)) == 1
    rec = store.read().get("action", action)
    with store.transaction() as tx:
        tx.update(
            "action",
            action,
            {"status": "done", "done_by": [me(cfg)], "reported_by": me(cfg)},
            _TEST,
            read_version=rec.version,
        )
    assert unsent(env_sent) == []


def test_the_persons_own_marking_ends_it_whatever_the_copy_says(env):
    _, cfg, store = env
    action = work_action(store, cfg)
    approve(store, cfg, propose(store, cfg, action))
    rec = store.read().get("action", action)
    with store.transaction() as tx:
        tx.update("action", action, {"status": "done", "done_by": [me(cfg)]}, _TEST, read_version=rec.version)
    sent(env, to=EDITOR, body=DRAFT, at=NOW - timedelta(hours=1))
    assert match(env) != [] and store.read().get("action", action).data["status"] == "done"


def test_the_api_keeps_a_copy_of_the_draft_when_the_person_copies_it(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from tests.test_sent_version import TOKEN, _addresses, _build

    ws, cfg = _build(tmp_path, with_sent_folder=True)
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        store = app.state.store
        _addresses(store, cfg)
        action = work_action(store, cfg)
        assert client.post(f"/api/actions/{action}/work/copied").status_code == 409  # nothing drafted yet
        propose(store, cfg, action)
        made = client.post(f"/api/actions/{action}/work/copied")
        assert made.status_code == 200, made.text
        (found,) = copies(store)
        assert made.json() == {"id": found.id} and found.data["kind"] == "work"
        assert client.post("/api/actions/ACT-NOPE/work/copied").status_code == 404
        assert store.read().get("action", action).data["status"] == "open"
