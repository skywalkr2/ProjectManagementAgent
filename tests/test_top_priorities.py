"""Top priorities (design 7.7): a short ranked list across every project, by rules, never an AI call.

The order is overdue, waiting on the person, due within the follow-up window, at risk (the functional designer's F16,
B-7); ties go by the project's priority, then by date; one line per other person; something on hold is never listed as
itself and the blocked are counted (what holds them up is in `test_chase_moves_to_the_blocker.py`).
The follow-up rule is the one the Follow-ups screen reads. Names, ids and numbers come from the fixtures and the
settings.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.followups import put_on_hold, sections
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.top_priorities import top_priorities
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.top-priorities")


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    # A long list, so the order of every line made below can be read; the limit has its own test.
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


def keys(env, *, only: set[str] | None = None, now=NOW) -> list[str]:
    """The keys of the lines, in order; with `only`, just those about the records made by the test."""
    _, cfg, store = env
    found = [line.key for line in top_priorities(store, cfg, now).lines]
    return [k for k in found if only is None or k.split(":", 1)[1] in only]


def lines_of(env, now=NOW) -> dict:
    _, cfg, store = env
    return {line.key: line for line in top_priorities(store, cfg, now).lines}


# ---- each rule ------------------------------------------------------------------------------------------------------


def test_an_overdue_to_do_is_listed_with_the_days_it_has_passed(env):
    _, cfg, store = env
    late = own(store, cfg, "Send the proofs", due=day(-3))
    line = lines_of(env)[f"action:{late}"]
    assert (line.rank, line.kind, line.days, line.due.isoformat()) == ("overdue", "action", 3, day(-3))
    assert line.action == late and line.person == me(cfg)


def test_a_to_do_due_within_the_follow_up_window_is_listed_and_one_due_later_is_not(env):
    _, cfg, store = env
    window = cfg.ui.followups.action_due_within_days
    soon = own(store, cfg, "Check the cover", due=day(window))
    later = own(store, cfg, "Plan the reprint", due=day(window + 1))
    found = lines_of(env)
    assert found[f"action:{soon}"].rank == "due_soon" and found[f"action:{soon}"].days is None
    assert f"action:{later}" not in found


def test_a_question_for_the_person_is_waiting_on_them_and_ranks_after_what_is_overdue_and_before_what_is_due(env):
    _, cfg, store = env
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    soon = own(store, cfg, "Check the cover", due=day(1))
    found = lines_of(env)
    assert found[f"question:{asked}"].rank == "waiting" and found[f"question:{asked}"].question == asked
    late = own(store, cfg, "Send the proofs", due=day(-1))
    order = keys(env, only={asked, soon, late})
    assert order == [f"action:{late}", f"question:{asked}", f"action:{soon}"]


def test_a_to_do_of_a_project_at_risk_is_listed_last_of_the_ranks_and_a_later_to_do_of_another_is_not(env):
    _, cfg, store = env
    risky = make(store, "project", name="A risky book", status="At risk")
    fine = make(store, "project", name="A calm book", status="On track")
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    in_risk = own(store, cfg, "Tidy the schedule", due=day(40), project=risky)
    calm = own(store, cfg, "Tidy the notes", due=day(40), project=fine)
    found = lines_of(env)
    assert found[f"action:{in_risk}"].rank == "at_risk" and f"action:{calm}" not in found
    assert keys(env, only={asked, in_risk}) == [f"question:{asked}", f"action:{in_risk}"]


def test_the_ranks_run_overdue_then_waiting_then_due_soon_then_at_risk(env):
    _, cfg, store = env
    risky = make(store, "project", name="A risky book", status="At risk")
    at_risk = own(store, cfg, "Tidy the schedule", due=day(40), project=risky)
    asked = make(store, "question", to=me(cfg), title="Which printer?", status="open")
    soon = own(store, cfg, "Check the cover", due=day(2))
    late = own(store, cfg, "Send the proofs", due=day(-1))
    assert keys(env, only={at_risk, asked, soon, late}) == [
        f"action:{late}",
        f"question:{asked}",
        f"action:{soon}",
        f"action:{at_risk}",
    ]


def test_ties_go_by_the_projects_priority_then_by_date(env):
    _, cfg, store = env
    high = make(store, "project", name="A first book", priority="High")
    low = make(store, "project", name="A last book", priority="Low")
    a = own(store, cfg, "Late in low", due=day(-9), project=low)
    b = own(store, cfg, "Later in high", due=day(-2), project=high)
    c = own(store, cfg, "Earlier in high", due=day(-5), project=high)
    d = own(store, cfg, "No project", due=day(-20))
    assert keys(env, only={a, b, c, d}) == [f"action:{c}", f"action:{b}", f"action:{a}", f"action:{d}"]


def test_something_on_hold_is_never_listed_and_a_blocked_action_is_counted(env):
    _, cfg, store = env
    held = own(store, cfg, "Wait for the quote", due=day(-4))
    blocker = someone(store)
    put_on_hold(store, held, on=blocker, now=NOW)
    words_only = own(store, cfg, "Wait for the printer", due=day(-4))
    put_on_hold(store, words_only, "the printer", now=NOW)
    before = top_priorities(store, cfg, NOW)
    assert f"action:{held}" not in lines_of(env) and f"action:{words_only}" not in lines_of(env)
    assert before.blocked == 1


# ---- one line per person, by the follow-up rule ----------------------------------------------------------


def told(store, who, text, *, ago, due=None) -> str:
    return make(
        store,
        "action",
        text=text,
        owners=[{"person": who}],
        due=due,
        told={who: (TODAY - timedelta(days=ago)).isoformat()},
    )


def test_everything_one_other_person_holds_is_one_line_with_counts(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    who = someone(store)
    sent = (NOW - timedelta(days=rule.question_after_days + 1)).isoformat()
    make(store, "question", to=who, title="Which date?", status="sent", sent_at=sent)
    make(store, "question", to=who, title="Which size?", status="sent", sent_at=sent)
    make(store, "question", to=who, title="Which paper?", status="open")
    told(store, who, "Send the file", ago=rule.question_after_days, due=day(-2))
    mine = [line for line in top_priorities(store, cfg, NOW).lines if line.person == who]
    assert len(mine) == 1
    line = mine[0]
    assert line.kind == "person" and line.rank == "overdue"
    assert (line.send, line.chase, line.overdue) == (1, 2, 1)
    assert line.waiting_days == rule.question_after_days + 1
    assert len(line.things) == 4


def test_a_person_with_only_something_to_send_ranks_as_waiting_on_the_person(env):
    _, cfg, store = env
    who = someone(store)
    make(store, "question", to=who, title="Which paper?", status="open")
    line = lines_of(env)[f"person:{who}"]
    assert (line.rank, line.send, line.chase) == ("waiting", 1, 0)


def test_a_person_with_something_to_send_ranks_before_one_due_a_follow_up_and_after_one_overdue(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    to_send, chased, late = (
        someone(store, "Quinn Fictional"),
        someone(store, "Robin Fictional"),
        someone(store, "Sam F."),
    )
    make(store, "question", to=to_send, title="Which paper?", status="open")
    make(
        store,
        "question",
        to=chased,
        title="Which date?",
        status="sent",
        sent_at=(NOW - timedelta(days=rule.question_after_days + 1)).isoformat(),
    )
    told(store, late, "Send the file", ago=rule.question_after_days, due=day(-2))
    assert keys(env, only={late, to_send, chased}) == [f"person:{late}", f"person:{to_send}", f"person:{chased}"]


def test_nothing_with_no_act_for_the_person_today_is_listed(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    quiet = someone(store)
    # Told lately, due far ahead, nothing to send, nothing unanswered: no act for the person today.
    told(store, quiet, "Plan the reprint", ago=0, due=day(rule.action_due_within_days + 30))
    make(store, "question", to=quiet, title="Which date?", status="answered", sent_at=NOW.isoformat())
    far = own(store, cfg, "Plan the launch", due=day(rule.action_due_within_days + 30))
    undated = own(store, cfg, "Tidy the shelves")
    found = lines_of(env)
    assert f"person:{quiet}" not in found and f"action:{far}" not in found and f"action:{undated}" not in found


def test_the_follow_up_rule_is_the_one_the_follow_ups_screen_reads(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    who = someone(store)
    # A question one day short of the wait is not chased; a day later it is; a told action due far ahead never is.
    make(
        store,
        "question",
        to=who,
        title="Which date?",
        status="sent",
        sent_at=(NOW - timedelta(days=rule.question_after_days - 1)).isoformat(),
    )
    assert f"person:{who}" not in lines_of(env)
    later = NOW + timedelta(days=1)
    assert lines_of(env, later)[f"person:{who}"].chase == 1
    far = told(store, who, "Plan the reprint", ago=rule.undated_after_days, due=day(rule.action_due_within_days + 20))
    assert far not in {t.id for t in lines_of(env, later)[f"person:{who}"].things}
    section = next(s for s in sections(store, cfg, later.date()) if s.person == who)
    chased = {q["id"] for q in section.questions if q["chase_due"]} | {
        a["id"] for a in section.actions if a["chase_due"]
    }
    listed = {t.id for t in lines_of(env, later)[f"person:{who}"].things if t.why == "chase"}
    assert listed == chased


def test_an_undated_told_action_is_chased_after_the_undated_wait_and_not_before(env):
    _, cfg, store = env
    rule = cfg.ui.followups
    who = someone(store)
    first = told(store, who, "Send the budget", ago=rule.undated_after_days - 1)
    assert f"person:{who}" not in lines_of(env)
    second = told(store, who, "Send the notes", ago=rule.undated_after_days)
    line = lines_of(env)[f"person:{who}"]
    assert line.chase == 1 and [t.id for t in line.things] == [second]
    assert first not in [t.id for t in line.things]


def test_today_and_top_priorities_agree_on_who_is_due_a_follow_up(env):
    ws, cfg, store = env
    rule = cfg.ui.followups
    chased, quiet = someone(store, "Quinn Fictional"), someone(store, "Robin Fictional")
    old = (NOW - timedelta(days=rule.question_after_days + 2)).isoformat()
    make(store, "question", to=chased, title="Which date?", status="sent", sent_at=old)
    make(store, "question", to=quiet, title="Which size?", status="sent", sent_at=NOW.isoformat())
    nudged = {x.person for x in queue(ws, store, cfg, NOW) if x.kind == "nudge"}
    mine = {line.person: line for line in top_priorities(store, cfg, NOW).lines if line.kind == "person"}
    assert chased in nudged and quiet not in nudged
    assert mine[chased].chase == 1 and quiet not in mine


def test_every_number_the_list_reads_is_a_setting(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(
        env={
            "COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC",
            "COCKPIT__UI__TODAY__TOP_PRIORITIES_LINES": "50",
            "COCKPIT__UI__FOLLOWUPS__ACTION_DUE_WITHIN_DAYS": "2",
            "COCKPIT__UI__FOLLOWUPS__QUESTION_AFTER_DAYS": "1",
            "COCKPIT__UI__TODAY__TOP_PRIORITIES_AHEAD_DAYS": "4",
        }
    )
    store = Store(ws.db_path, cfg=cfg)
    near = own(store, cfg, "Due in two days", due=day(2))
    far = own(store, cfg, "Due in three days", due=day(3))
    who = someone(store)
    make(store, "question", to=who, title="Which date?", status="sent", sent_at=(NOW - timedelta(days=1)).isoformat())
    found = top_priorities(store, cfg, NOW)
    keys_ = [line.key for line in found.lines]
    assert f"action:{near}" in keys_ and f"action:{far}" not in keys_
    assert f"person:{who}" in keys_  # chased after one day, by the setting
    assert [c.action for c in found.coming if c.action in (near, far)] == [far]  # the days ahead are a setting too
    store.close()


# ---- the list's size and what follows it -----------------------------------------------------------------


def test_only_the_configured_number_of_lines_is_listed_and_the_rest_are_counted(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC", "COCKPIT__UI__TODAY__TOP_PRIORITIES_LINES": "2"})
    store = Store(ws.db_path, cfg=cfg)
    for n in range(5):
        own(store, cfg, f"Overdue {n}", due=day(-1 - n))
    found = top_priorities(store, cfg, NOW)
    assert len(found.lines) == 2 and found.more >= 3
    # The oldest passed day comes first.
    assert found.lines[0].due <= found.lines[1].due
    store.close()


def test_the_next_days_dated_to_dos_follow_the_lines_and_leave_out_what_a_line_holds(env):
    _, cfg, store = env
    ahead = cfg.ui.today.top_priorities_ahead_days
    window = cfg.ui.followups.action_due_within_days
    on_a_line = own(store, cfg, "Check the cover", due=day(2))
    inside = own(store, cfg, "Order the samples", due=day(window + 1))
    beyond = own(store, cfg, "Plan the launch", due=day(ahead + 1))
    past = own(store, cfg, "Send the proofs", due=day(-1))
    result = top_priorities(store, cfg, NOW)
    ids = [c.action for c in result.coming]
    assert inside in ids and on_a_line not in ids and beyond not in ids and past not in ids
    assert ids == sorted(ids, key=lambda i: next(c.due for c in result.coming if c.action == i))


def test_a_workspace_that_does_not_say_who_the_person_is_has_no_list(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    cfg.workspace.user.person = None
    store = Store(ws.db_path, cfg=cfg)
    assert top_priorities(store, cfg, NOW).lines == []
    store.close()
