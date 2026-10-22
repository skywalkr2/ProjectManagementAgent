"""The outcome, measured (design 6.20, 6.32 "Measured"): promises found and kept, false alerts, time spent reviewing and
follow-ups completed, each per week and from the records alone, on the Quality screen. Names and ids come from the
fixtures; every record is made at a moment the test sets, so each week's numbers are known."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import outcome
from engine.learn import record
from engine.storage import Store, WriteContext
from engine.today import zone
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "outcome-token"
# Wednesday of the third week; weeks start on Monday on the person's clock (UTC here).
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
WEEK_3 = date(2026, 10, 19)
WEEK_2 = date(2026, 10, 12)
WEEK_1 = date(2026, 10, 5)
DAYS = 16
_PM = WriteContext(actor="pm", trust="trusted", op="test")
_ASSISTANT = WriteContext(actor="assistant", trust="trusted", op="test.assistant")
PEOPLE = fixture_records(DEMO_B, "person")
ME = PEOPLE[0]["id"]
OTHER = PEOPLE[1]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]


class Clock:
    def __init__(self) -> None:
        self.at = NOW

    def __call__(self) -> str:
        return self.at.isoformat(timespec="seconds")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    clock = Clock()
    store = Store(ws.db_path, cfg=cfg, clock=clock)
    yield cfg, store, clock
    store.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def day(week: date, offset: int = 0, hour: int = 10) -> datetime:
    return datetime.combine(week + timedelta(days=offset), datetime.min.time(), tzinfo=UTC) + timedelta(hours=hour)


def make(store, clock, when, kind, data, by=_PM) -> str:
    clock.at = when
    with store.transaction() as tx:
        return tx.create(kind, data, by).id


def change(store, clock, when, kind, record_id, changes, by=_PM) -> None:
    clock.at = when
    with store.transaction() as tx:
        tx.update(kind, record_id, changes, by, read_version=tx.get(kind, record_id).version)


def promise(store, clock, when, *, owner=ME, by=_ASSISTANT, **more) -> str:
    data = {
        "text": "Send the proofs",
        "owners": [{"person": owner}],
        "promised_to": [OTHER if owner == ME else ME],
        "basis": "said",
        "project": PROJECT,
        **more,
    }
    return make(store, clock, when, "action", data, by)


def week_row(found, week):
    return next(w for w in found if w.week == week)


def signal(env, when, kind, note=None) -> None:
    cfg, store, clock = env
    clock.at = when
    with store.transaction() as tx:
        record(tx, cfg, {"kind": kind, "note": note, "at": when.isoformat()}, _PM, when)


def figures(cfg, store):
    return outcome.per_week(store.read(), ME, NOW, DAYS, zone(cfg))


# ---- promises found and kept ---------------------------------------------------------------------------------------


def test_promises_the_assistant_found_are_counted_by_the_week_it_found_them_and_the_persons_own_are_not(env):
    cfg, store, clock = env
    promise(store, clock, day(WEEK_2, 1))
    promise(store, clock, day(WEEK_2, 3))
    promise(store, clock, day(WEEK_3))
    promise(store, clock, day(WEEK_3), by=_PM)  # the person's own note: not found by the assistant
    promise(store, clock, day(WEEK_3), owner=OTHER)  # someone else's promise to the person: not the person's to keep
    found = figures(cfg, store)
    assert [(w.week, w.found) for w in found] == [(WEEK_1, 0), (WEEK_2, 2), (WEEK_3, 1)]


def test_a_found_promise_is_kept_in_the_week_the_person_closed_it_as_done_whichever_week_it_was_found(env):
    cfg, store, clock = env
    early = promise(store, clock, day(WEEK_1, 1))
    other = promise(store, clock, day(WEEK_2))
    dropped = promise(store, clock, day(WEEK_2))
    still_open = promise(store, clock, day(WEEK_2))
    change(store, clock, day(WEEK_3, 1), "action", early, {"status": "done"})
    change(store, clock, day(WEEK_2, 4), "action", other, {"status": "done"})
    change(store, clock, day(WEEK_3, 2), "action", dropped, {"status": "dropped"})
    found = figures(cfg, store)
    assert [(w.week, w.found, w.kept) for w in found] == [(WEEK_1, 1, 0), (WEEK_2, 3, 1), (WEEK_3, 0, 1)]
    assert store.read().get("action", still_open).data["status"] == "open"


def test_a_promise_closed_reopened_and_closed_again_counts_once_at_its_last_close(env):
    cfg, store, clock = env
    made = promise(store, clock, day(WEEK_1))
    change(store, clock, day(WEEK_1, 2), "action", made, {"status": "done"})
    change(store, clock, day(WEEK_2), "action", made, {"status": "open"})
    change(store, clock, day(WEEK_3), "action", made, {"status": "done"})
    assert [w.kept for w in figures(cfg, store)] == [0, 0, 1]


# ---- false alerts --------------------------------------------------------------------------------------------------


def chosen(choice: str) -> str:
    return json.dumps({"kind": "pattern", "subject": "pattern:moved:ACT-1", "change": "3", "choice": choice})


def test_leaving_or_keeping_a_suggestion_and_correcting_the_assistants_work_are_false_alerts_and_not_now_is_not(env):
    cfg, store, clock = env
    signal(env, day(WEEK_2), "suggestion_chosen", chosen("leave"))
    signal(env, day(WEEK_2), "suggestion_chosen", chosen("keep"))
    signal(env, day(WEEK_2), "suggestion_chosen", chosen("drop"))  # acting on it says it was right
    signal(env, day(WEEK_2), "suggestion_chosen", chosen("snooze"))
    signal(env, day(WEEK_3), "suggestion_dismissed", '{"kind": "stale", "subject": "stale", "change": "x"}')
    signal(env, day(WEEK_3), "held_declined")
    signal(env, day(WEEK_3), "no_reply_needed")
    signal(env, day(WEEK_3), "undone")
    signal(env, day(WEEK_3), "missed", "It missed the invoice")  # a miss is no false alert
    signal(env, day(WEEK_3), "dropped", "No longer needed")  # a drop says nothing about the assistant
    found = figures(cfg, store)
    assert [(w.week, w.dismissed, w.corrected) for w in found] == [(WEEK_1, 0, 0), (WEEK_2, 2, 0), (WEEK_3, 0, 3)]


def test_a_suggestion_choice_taken_back_is_no_false_alert(env):
    cfg, store, clock = env
    signal(env, day(WEEK_3), "suggestion_chosen", "taken back")
    assert [w.dismissed for w in figures(cfg, store)] == [0, 0, 0]


# ---- time spent reviewing ------------------------------------------------------------------------------------------


def test_review_time_is_summed_per_week_with_the_visits_and_held_to_the_most_for_a_visit(env):
    cfg, store, clock = env
    cap = cfg.dispatch.knowledge.review_visit_max_seconds
    clock.at = day(WEEK_2)
    assert outcome.record_review_time(store, cfg, "review", 90, day(WEEK_2)) == 90
    assert outcome.record_review_time(store, cfg, "changes", 30, day(WEEK_2, 1)) == 30
    assert outcome.record_review_time(store, cfg, "since", cap * 10, day(WEEK_3)) == cap, "a screen left open"
    assert outcome.record_review_time(store, cfg, "review", 0, day(WEEK_3)) == 0
    found = figures(cfg, store)
    assert [(w.week, w.review_seconds, w.review_visits) for w in found] == [
        (WEEK_1, 0, 0),
        (WEEK_2, 120, 2),
        (WEEK_3, cap, 1),
    ]


def test_a_screen_that_doesnt_look_over_the_assistants_work_is_refused(env):
    cfg, store, _ = env
    with pytest.raises(Exception, match="screen"):
        outcome.record_review_time(store, cfg, "settings", 30, NOW)


# ---- follow-ups completed ------------------------------------------------------------------------------------------


def test_a_chased_promise_or_question_that_was_then_settled_is_a_follow_up_completed_in_that_week(env):
    cfg, store, clock = env
    chased = promise(store, clock, day(WEEK_1), owner=OTHER, followed_up={OTHER: [day(WEEK_1, 2).date().isoformat()]})
    unchased = promise(store, clock, day(WEEK_1), owner=OTHER)
    own = promise(store, clock, day(WEEK_1), followed_up={OTHER: [day(WEEK_1, 2).date().isoformat()]})
    asked = make(
        store,
        clock,
        day(WEEK_1),
        "question",
        {
            "to": OTHER,
            "title": "Which trim size?",
            "status": "sent",
            "followed_up": [day(WEEK_1, 3).date().isoformat()],
        },
    )
    never_chased = make(store, clock, day(WEEK_1), "question", {"to": OTHER, "title": "Which font?", "status": "sent"})
    for record_id in (chased, unchased, own):
        change(store, clock, day(WEEK_2, 1), "action", record_id, {"status": "done"})
    change(store, clock, day(WEEK_3), "question", asked, {"status": "answered"})
    change(store, clock, day(WEEK_3), "question", never_chased, {"status": "answered"})
    assert [(w.week, w.follow_ups) for w in figures(cfg, store)] == [(WEEK_1, 0), (WEEK_2, 1), (WEEK_3, 1)]


# ---- on the Quality screen -----------------------------------------------------------------------------------------


def test_the_quality_view_carries_every_measure_for_the_window_and_each_week_and_nothing_is_added_together(api):
    client, store, cfg = api
    me = cfg.workspace.user.person
    clock_now = datetime.now(UTC)
    with store.transaction() as tx:
        made = tx.create(
            "action",
            {
                "text": "Send the proofs",
                "owners": [{"person": me}],
                "promised_to": [OTHER],
                "basis": "said",
                "project": PROJECT,
            },
            _ASSISTANT,
        ).id
    with store.transaction() as tx:
        tx.update("action", made, {"status": "done"}, _PM, read_version=tx.get("action", made).version)
    assert client.post("/api/quality/review-time", json={"screen": "review", "seconds": 45}).json() == {"seconds": 45}
    view = client.get("/api/quality").json()["outcome"]
    assert (view["promises_found"], view["promises_kept"]) == (1, 1)
    assert (view["review_seconds"], view["review_visits"]) == (45, 1)
    assert (view["dismissed"], view["corrected"], view["follow_ups_completed"]) == (0, 0, 0)
    assert sum(w["review_seconds"] for w in view["weeks"]) == 45 and len(view["weeks"]) >= 4
    this_week = view["weeks"][-1]
    assert this_week["week_end"] == (date.fromisoformat(this_week["week"]) + timedelta(days=6)).isoformat()
    assert this_week["week"] <= clock_now.date().isoformat()


def test_a_review_time_for_a_screen_that_isnt_one_is_refused(api):
    client, _, _ = api
    assert client.post("/api/quality/review-time", json={"screen": "settings", "seconds": 5}).status_code == 422
    assert client.post("/api/quality/review-time", json={"screen": "review", "seconds": 0}).json() == {"seconds": 0}
