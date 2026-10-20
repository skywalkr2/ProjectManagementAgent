"""A hold that waits on the person themselves isn't blocked anywhere (design 6.9; the functional designer's answer F15,
B-7): `standing_hold` doesn't stand for it, and the to-do list and the Follow-ups rows carry no "Blocked, waiting on"
for it, so it is the person's own to-do by its own dates. A hold that waits on someone else is unchanged. Names and ids
come from the fixtures and the settings."""

from __future__ import annotations

import pytest

from engine.blocked import standing_hold
from engine.followups import put_on_hold
from engine.names import People
from engine.open_items import open_actions
from engine.storage import Store
from engine.today import todo
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_chase_moves_to_the_blocker import (
    NOW,
    day,
    make,
    me,
    own,
    row,
    sent_question,
    someone,
)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def held_on(store, cfg, blocker, *, due=-3):
    action = own(store, cfg, "Reply about the venue", due=day(due))
    put_on_hold(store, action, on=blocker, now=NOW)
    return action


def test_a_hold_waiting_on_the_person_does_not_stand_but_one_waiting_on_someone_else_does(env):
    _, cfg, store = env
    people = People(store, cfg)
    self_held = held_on(store, cfg, me(cfg))
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    question_held = held_on(store, cfg, asked)
    other_held = held_on(store, cfg, sent_question(store, someone(store)))
    view = store.read()
    for action in (self_held, question_held):
        assert standing_hold(view, view.get("action", action).data, people) is None
        assert standing_hold(view, view.get("action", action).data, pm=me(cfg)) is None
    assert standing_hold(view, view.get("action", other_held).data, people) is not None
    assert standing_hold(view, view.get("action", self_held).data) is not None  # without a person to compare, as before


def test_the_open_items_row_of_the_persons_own_hold_on_themselves_has_no_blocker(env):
    _, cfg, store = env
    own_wait = held_on(store, cfg, me(cfg))
    blocked = held_on(store, cfg, sent_question(store, someone(store)))
    rows = {r.id: r for r in open_actions(store, cfg, NOW.date())}
    assert (rows[own_wait].blocker, rows[own_wait].on_hold) == (None, None)
    assert rows[blocked].blocker is not None and rows[blocked].on_hold


def test_the_to_do_list_shows_a_hold_on_the_person_as_their_own_dated_to_do(env):
    _, cfg, store = env
    sam = someone(store)
    own_wait = held_on(store, cfg, me(cfg))
    blocked = held_on(store, cfg, sent_question(store, sam))
    rows = {t.action: t for t in todo(store, cfg, NOW)}
    mine, theirs = rows[own_wait], rows[blocked]
    assert (mine.blocker, mine.on_hold, mine.overdue) == (None, None, True)
    assert theirs.blocker is not None and theirs.on_hold is not None and not theirs.overdue


def test_an_action_someone_else_owns_that_waits_on_the_person_stays_on_hold(env):
    _, cfg, store = env
    sam = someone(store)
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    waiting_on_me = make(store, "action", text="Order the proofs", owners=[{"person": sam}], due=day(-2))
    put_on_hold(store, waiting_on_me, on=asked, now=NOW)
    view = store.read()
    # Theirs to wait for: it is not due, chased or listed overdue because the person hasn't answered.
    assert standing_hold(view, view.get("action", waiting_on_me).data, People(store, cfg)) is not None
    assert row(store, cfg, sam, "actions", waiting_on_me)["blocker"] is not None
    rows = {r.id: r for r in open_actions(store, cfg, NOW.date())}
    assert rows[waiting_on_me].blocker is not None and rows[waiting_on_me].on_hold
