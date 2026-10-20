"""Questions after a move are one group line under the move (design 7.7): one row inside for each thing to check,
the questions to other people counted and left to Follow-ups, a group of one a normal row that says what it came
after, and a second move of the same record leaving one group for the latest. Names and ids come from the fixtures."""

from __future__ import annotations

import pytest

from engine.ai.adapters.stub import set_responder
from engine.storage import Store
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go
from tests.test_follow_on import (
    ASKED,
    NEW,
    NOW,
    OLD,
    PROJECT,
    ask_date,
    edit,
    follow_ons,
    make,
    pm_of,
    run,
    scripted,
)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def plan(pm, entry, **more):
    return {
        "op": "question.add",
        "kind": "decision",
        "to": pm,
        "title": "Does the plan for the moved entry still hold?",
        "text": "Tied to it.",
        "project": PROJECT["id"],
        "matters_for": entry,
        **more,
    }


def moved_entry_with(env, extra=1):
    """A moved entry with one dated action on it, and the run's questions: to the person about the action's date, to the
    person about the plan, and one to someone else. Returns the entry and the run's request."""
    _, _, store = env
    pm = pm_of(env)
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD)
    for n in range(extra):
        make(store, "action", text=f"Check item {n}", event=entry)
    edit(env, "event", entry, start=NEW)
    (request,) = follow_ons(store)
    ops = [ask_date(pm, action), plan(pm, entry)]
    scripted({"summary": "Asked.", "ops": ops})
    run(env, request.id)
    return entry, request, action


def lines(env, kind=None):
    ws, cfg, store = env
    found = queue(ws, store, cfg, NOW)
    return [x for x in found if kind is None or x.kind == kind]


def test_two_questions_after_one_move_are_one_group_with_a_row_for_each(env):
    entry, request, _ = moved_entry_with(env)
    assert not [x for x in lines(env) if x.kind in ("decision", "question") and x.after_move]
    (group,) = lines(env, "moved")
    assert group.group == "decide" and group.count == 2 and len(group.questions) == 2
    assert group.text == "Printer sync" and group.due == NEW
    assert group.after_move["record"] == entry and group.after_move["earlier"] is False
    assert group.after_move["by"] == "pm" and group.after_move["request"] == request.id


def test_a_move_to_an_earlier_day_says_so(env):
    _, _, store = env
    pm = pm_of(env)
    entry = make(store, "event", start=NEW)
    action = make(store, "action", event=entry, due=NEW)
    make(store, "action", text="Check the other item", event=entry)
    edit(env, "event", entry, start=OLD)
    (request,) = follow_ons(store)
    scripted({"summary": "Asked.", "ops": [ask_date(pm, action), plan(pm, entry)]})
    run(env, request.id)
    (group,) = lines(env, "moved")
    assert group.after_move["earlier"] is True and group.due == OLD


def test_a_group_of_one_is_a_normal_row_that_says_what_it_came_after(env):
    _, _, store = env
    pm = pm_of(env)
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD)
    edit(env, "event", entry, start=NEW)
    (request,) = follow_ons(store)
    scripted({"summary": "Asked.", "ops": [ask_date(pm, action)]})
    run(env, request.id)
    assert not lines(env, "moved")
    (row,) = [x for x in lines(env) if x.kind == "decision" and x.after_move]
    assert row.after_move["title"] == "Printer sync" and row.after_move["to"] == NEW


def test_questions_the_run_asked_other_people_are_counted_in_the_group_not_listed_in_it(env):
    _, _, store = env
    pm = pm_of(env)
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD)
    make(store, "action", text="Cover the freight plan", event=entry)
    edit(env, "event", entry, start=NEW)
    (request,) = follow_ons(store)
    sent_to = make(store, "action", text="Review the proof", event=entry, told={ASKED: OLD})
    correction = {
        "op": "question.add",
        "kind": "question",
        "to": ASKED,
        "title": "The sync moved: is the proof still on time?",
        "text": f"The sync moved from {OLD} to {NEW}.",
        "links": [{"label": PROJECT["links"][0]["label"], "url": PROJECT["links"][0]["url"]}],
        "project": PROJECT["id"],
        "matters_for": sent_to,
    }
    scripted({"summary": "Asked.", "ops": [ask_date(pm, action), plan(pm, entry), correction]})
    run(env, request.id)
    (group,) = lines(env, "moved")
    assert group.count == 2 and len(group.after_move["others"]) == 1


def test_a_second_move_of_the_same_entry_leaves_one_group_for_the_latest(env):
    entry, request, action = moved_entry_with(env)
    _, _, store = env
    edit(env, "event", entry, start="2026-10-26")
    latest = [r for r in follow_ons(store) if r.id != request.id][0]
    pm = pm_of(env)
    scripted(
        {
            "summary": "Asked.",
            "ops": [ask_date(pm, action, title="Move it again?"), plan(pm, entry, title="Plan again?")],
        }
    )
    run(env, latest.id)
    (group,) = lines(env, "moved")
    assert group.after_move["request"] == latest.id and group.due == "2026-10-26"
    assert {q for q in group.questions} and len(group.questions) == 2


# ---- each row's own answers (design 7.7) ----------------------------------------------------------------------


def test_each_row_of_a_group_carries_its_structured_answer_a_date_to_move_and_a_plan_that_holds(env):
    entry, _, action = moved_entry_with(env)
    (group,) = lines(env, "moved")
    rows = {r["question"]: r["check"] for r in group.after_move["rows"]}
    assert len(rows) == 2
    date_check = next(c for c in rows.values() if c["kind"] == "date")
    plan_check = next(c for c in rows.values() if c["kind"] == "plan")
    assert (date_check["action"], date_check["from_day"], date_check["to_day"]) == (action, OLD, NEW)
    assert date_check["version"] and date_check["text"]
    assert plan_check["record"] == entry


def test_a_question_that_names_nothing_to_move_or_confirm_has_no_structured_answer(env):
    _, _, store = env
    pm = pm_of(env)
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD)
    make(store, "action", text="Check the other item", event=entry)
    edit(env, "event", entry, start=NEW)
    (request,) = follow_ons(store)
    # An action with no day of its own is not asked to move: its question is an ordinary one.
    undated = make(store, "action", text="Plan the freight", event=entry)
    scripted(
        {"summary": "Asked.", "ops": [ask_date(pm, action), ask_date(pm, undated, title="Is the freight plan fine?")]}
    )
    run(env, request.id)
    rows = [x.after_move for x in lines(env) if x.after_move and x.kind != "moved"]
    group = lines(env, "moved")
    found = [r["check"] for g in group for r in g.after_move["rows"]] + [r["check"] for r in rows]
    assert any(c and c["kind"] == "date" and c["action"] == action for c in found)
    assert not any(c and c.get("action") == undated for c in found)


def test_a_group_of_one_row_carries_its_structured_answer_too(env):
    _, _, store = env
    pm = pm_of(env)
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD)
    edit(env, "event", entry, start=NEW)
    (request,) = follow_ons(store)
    scripted({"summary": "Asked.", "ops": [ask_date(pm, action)]})
    run(env, request.id)
    (row,) = [x for x in lines(env) if x.kind == "decision" and x.after_move]
    assert row.after_move["check"]["kind"] == "date" and row.after_move["check"]["to_day"] == NEW
