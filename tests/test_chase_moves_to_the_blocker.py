"""The chase moves to the blocker (design 6.9; the functional designer's answer F15, B-7): an action on hold that names
a question or another action as its blocker is never due or chased itself, and its follow-up clock goes to the blocker,
which comes due as the blocked action's would have. Top priorities lists the blocker with what it holds up, never the
blocked action. A hold that waits on the person themselves isn't blocked: it is their own to-do. Names and ids come from
the fixtures and the settings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.blocked import blocked_actions
from engine.followups import put_on_hold, sections
from engine.names import People
from engine.storage import Store, WriteContext
from engine.top_priorities import top_priorities
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.blocker-chase")


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC", "COCKPIT__UI__TODAY__TOP_PRIORITIES_LINES": "50"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def make(store, kind, **data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def someone(store, name="Quinn Fictional") -> str:
    return make(store, "person", full_name=name)


def own(store, cfg, text, due=None, **more) -> str:
    return make(store, "action", text=text, owners=[{"person": me(cfg)}], due=due, **more)


def sent_question(store, who, *, ago=1, title="Which floor plan?") -> str:
    return make(store, "question", to=who, title=title, status="sent", sent_at=(NOW - timedelta(days=ago)).isoformat())


def row(store, cfg, person, kind, record_id, today=TODAY) -> dict:
    section = next(s for s in sections(store, cfg, today) if s.person == person)
    return next(r for r in getattr(section, kind) if r["id"] == record_id)


def lines_of(store, cfg) -> dict:
    return {line.key: line for line in top_priorities(store, cfg, NOW).lines}


# ---- a question as the blocker ------------------------------------------------------------------


def test_a_question_that_blocks_an_overdue_action_is_chased_as_the_action_would_have_been(env):
    _, cfg, store = env
    sam = someone(store)
    asked = sent_question(store, sam, ago=1)  # sent yesterday: not due a follow-up by its own clock
    assert not row(store, cfg, sam, "questions", asked)["chase_due"]
    held = own(store, cfg, "Lay out the hall", due=day(-2))
    put_on_hold(store, held, on=asked, now=NOW)
    found = row(store, cfg, sam, "questions", asked)
    assert found["chase_due"] and found["holds_up"] == 1
    # The blocked action itself is never chased or due while it is held.
    mine = next(s for s in sections(store, cfg, TODAY) if s.person == me(cfg))
    assert not next(a for a in mine.actions if a["id"] == held)["chase_due"]


def test_the_blocker_is_not_chased_early_when_the_blocked_action_is_not_due_yet(env):
    _, cfg, store = env
    sam = someone(store)
    asked = sent_question(store, sam, ago=1)
    far = cfg.ui.followups.action_due_within_days + 10
    held = own(store, cfg, "Lay out the hall", due=day(far))
    put_on_hold(store, held, on=asked, now=NOW)
    found = row(store, cfg, sam, "questions", asked)
    assert not found["chase_due"] and found["holds_up"] == 1


def test_a_question_not_sent_yet_is_not_chased_however_late_the_blocked_action_is(env):
    _, cfg, store = env
    sam = someone(store)
    asked = make(store, "question", to=sam, title="Which floor plan?", status="open")
    held = own(store, cfg, "Lay out the hall", due=day(-2))
    put_on_hold(store, held, on=asked, now=NOW)
    assert not row(store, cfg, sam, "questions", asked)["chase_due"]


def test_an_answered_question_blocks_nothing_and_moves_no_chase(env):
    _, cfg, store = env
    sam = someone(store)
    asked = sent_question(store, sam, ago=1)
    held = own(store, cfg, "Lay out the hall", due=day(-2))
    put_on_hold(store, held, on=asked, now=NOW)
    rec = store.read().get("question", asked)
    with store.transaction() as tx:
        tx.update("question", asked, {"status": "answered", "answer": "Here"}, _TEST, read_version=rec.version)
    assert blocked_actions(store, People(store, cfg)).total == 0
    assert f"person:{sam}" not in lines_of(store, cfg)


# ---- an action as the blocker ------------------------------------------------------------------


def test_an_action_someone_owes_that_blocks_a_due_action_comes_due_a_follow_up(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    sam = someone(store)
    plan = make(
        store,
        "action",
        text="Send the floor plan",
        owners=[{"person": sam}],
        due=day(rule.action_due_within_days + 20),
        told={sam: day(-rule.question_after_days)},
    )
    assert not row(store, cfg, sam, "actions", plan)["chase_due"]
    held = own(store, cfg, "Lay out the hall", due=day(1))
    put_on_hold(store, held, on=plan, now=NOW)
    found = row(store, cfg, sam, "actions", plan)
    assert found["chase_due"] and found["holds_up"] == 1


def test_a_blocker_held_up_actions_of_someone_else_pull_the_chase_by_their_told_clock(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    sam, robin = someone(store), someone(store, "Robin Fictional")
    asked = sent_question(store, sam, ago=1)
    held = make(
        store,
        "action",
        text="Print the signs",
        owners=[{"person": robin}],
        due=day(1),
        told={robin: day(-rule.question_after_days)},
    )
    put_on_hold(store, held, on=asked, now=NOW)
    assert row(store, cfg, sam, "questions", asked)["chase_due"]


# ---- Top priorities lists the blocker ------------------------------------------------------------------


def test_top_priorities_shows_the_blocker_with_what_it_holds_up_and_never_the_blocked_action(env):
    _, cfg, store = env
    sam = someone(store)
    asked = sent_question(store, sam, ago=1)
    first = own(store, cfg, "Lay out the hall", due=day(-2))
    second = own(store, cfg, "Book the caterer", due=day(-1))
    put_on_hold(store, first, on=asked, now=NOW)
    put_on_hold(store, second, on=asked, now=NOW)
    found = lines_of(store, cfg)
    assert f"action:{first}" not in found and f"action:{second}" not in found
    line = found[f"person:{sam}"]
    assert line.holds_up == 2 and line.rank == "overdue"
    thing = next(t for t in line.things if t.id == asked)
    assert (thing.why, thing.holds_up) == ("chase", 2)


def test_a_blocker_that_is_not_due_a_chase_is_not_listed_and_nothing_blocked_is(env):
    _, cfg, store = env
    sam = someone(store)
    asked = sent_question(store, sam, ago=1)
    held = own(store, cfg, "Lay out the hall", due=day(cfg.ui.followups.action_due_within_days + 10))
    put_on_hold(store, held, on=asked, now=NOW)
    found = lines_of(store, cfg)
    assert f"person:{sam}" not in found and f"action:{held}" not in found


def test_a_question_for_the_person_that_blocks_actions_says_how_many_it_holds_up(env):
    _, cfg, store = env
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    held = own(store, cfg, "Order the proofs", due=day(-3))
    put_on_hold(store, held, on=asked, now=NOW)
    found = lines_of(store, cfg)
    assert found[f"question:{asked}"].holds_up == 1 and found[f"question:{asked}"].rank == "waiting"
    assert f"action:{held}" not in found


def test_an_action_of_the_persons_own_that_blocks_another_is_listed_as_waiting_on_them(env):
    _, cfg, store = env
    unblock = own(store, cfg, "Sign the lease")
    held = make(store, "action", text="Move the stock", owners=[{"person": someone(store)}], due=day(-1))
    put_on_hold(store, held, on=unblock, now=NOW)
    line = lines_of(store, cfg)[f"action:{unblock}"]
    assert (line.rank, line.holds_up) == ("waiting", 1)
    assert f"action:{held}" not in lines_of(store, cfg)


# ---- a hold that waits on the person themselves is their own to-do ----


def test_a_hold_waiting_on_the_person_themselves_is_not_blocked_and_shows_as_their_own_to_do(env):
    _, cfg, store = env
    people = People(store, cfg)
    held = own(store, cfg, "Reply about the venue", due=day(-3))
    # A person can be named as the blocker; naming oneself means waiting on oneself.
    put_on_hold(store, held, on=me(cfg), now=NOW)
    assert blocked_actions(store, people).total == 0
    line = lines_of(store, cfg)[f"action:{held}"]
    assert (line.rank, line.kind) == ("waiting", "action")


def test_a_question_or_action_waiting_on_the_person_is_not_counted_blocked(env):
    _, cfg, store = env
    people = People(store, cfg)
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    mine = own(store, cfg, "Sign the lease")
    for text, blocker in (("Order the proofs", asked), ("Move the stock", mine)):
        held = make(store, "action", text=text, owners=[{"person": someone(store, text)}])
        put_on_hold(store, held, on=blocker, now=NOW)
    assert blocked_actions(store, people).total == 0


def test_a_blocked_action_waiting_on_someone_else_is_still_counted(env):
    _, cfg, store = env
    sam = someone(store)
    held = own(store, cfg, "Lay out the hall", due=day(-2))
    put_on_hold(store, held, on=sent_question(store, sam), now=NOW)
    assert blocked_actions(store, People(store, cfg)).total == 1
    assert top_priorities(store, cfg, NOW).blocked == 1
