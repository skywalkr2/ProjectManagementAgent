"""The capacity check, clashes from today onward, the attention budget and the reminder offer (design 6.32, S2).

The rules themselves are tested on their own (`test_capacity.py`, `test_free_slots.py`, `test_clashes.py`,
`test_attention.py`); these tests prove they are wired: an effort on a to-do (set by the person, suggested by the
assistant and held), the day's capacity line on Today and in the brief with the moves it proposes, clashes with travel
time after today, which suggestion lines show and which wait for the brief, "Not now" that sticks until something
changes, and the reminder offered in the brief. Names and ids come from the fixtures; the day moves with the clock the
test passes in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine import brief, day_capacity, day_clashes, suggestions, today_queue
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, decline_held, release
from engine.dispatcher import undo_changeset
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

# A Monday at 9:00 on the person's clock (UTC here).
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.day")
ZONE_UTC = {"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


class Clock:
    def __call__(self) -> str:
        return NOW.isoformat(timespec="seconds")


def build(tmp_path, **env):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={**ZONE_UTC, **env})
    return ws, cfg, Store(ws.db_path, cfg=cfg, clock=Clock())


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = build(tmp_path)
    yield ws, cfg, store
    store.close()


def make(store, kind, **data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def me(cfg) -> str:
    return cfg.workspace.user.person


def todo(store, cfg, text, minutes=None, due=None, **more) -> str:
    fields = {"text": text, "owners": [{"person": me(cfg)}], "due": due or day(0), **more}
    if minutes:
        fields["effort_minutes"] = minutes
    return make(store, "action", **fields)


def promised(store) -> list[str]:
    return [make(store, "person", full_name="Quinn Fictional")]


def meeting(store, title, start, end, **more) -> str:
    return make(store, "event", trust="trusted", title=title, start=start, end=end, **more)


def connected(store, key, title, start, end, where=None) -> str:
    event = {"start": start, "end": end, **({"where": where} if where else {})}
    return make(
        store,
        "snapshot",
        source="s",
        key=key,
        title=title,
        content_hash="h",
        seen_at=NOW.isoformat(),
        event=event,
    )


def line_of(found, kind):
    return next((x for x in found if x.kind == kind), None)


# ---- an effort on a to-do ------------------------------------------------------------------------------------------


def test_the_person_sets_an_effort_and_a_value_that_is_not_a_length_of_time_is_refused(env):
    _, cfg, store = env
    action = todo(store, cfg, "Write the report")
    version = store.read().get("action", action).version
    op = {
        "op": "record.edit",
        "record": {"kind": "action", "id": action},
        "fields": {"effort_minutes": 90},
        "read_version": version,
    }
    apply_as_person(store, cfg, [op], "Set how long it takes")
    assert store.read().get("action", action).data["effort_minutes"] == 90
    bad = {**op, "fields": {"effort_minutes": 0}, "read_version": store.read().get("action", action).version}
    with pytest.raises(Exception, match="effort_minutes"):
        apply_as_person(store, cfg, [bad], "Set how long it takes")


def _assistant_suggests(env, action, minutes, quote):
    _, cfg, store = env
    op = {
        "op": "record.set",
        "kind": "action",
        "id": action,
        "field": "effort_minutes",
        "value": minutes,
        "evidence": {"quote": quote},
    }
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, quote, "", "trusted", cites="mail:1"),
        actor="assistant",
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, store.read().get("changeset", cs_id).data["ops"][0]


def test_the_assistants_effort_is_held_as_a_question_and_leaving_it_is_a_signal(env):
    from engine import held_ask

    _, cfg, store = env
    action = todo(store, cfg, "Write the report")
    cs_id, outcome = _assistant_suggests(env, action, 120, "about two hours of work")
    assert outcome["status"] == "held" and "only you can set effort_minutes" in outcome["reason"]
    assert store.read().get("action", action).data.get("effort_minutes") is None
    asked = held_ask.describe(store.read(), People(store, cfg), outcome["op"])
    assert asked["ask"] == "effort" and asked["value"] == "120" and asked["from_value"] is None
    assert asked["item"] == "Write the report" and asked["quote"] == "about two hours of work"

    # Leaving it as it was is a signal the assistant learns from, and changes nothing on the to-do.
    decline_held(store, cs_id, 0)
    assert store.read().get("action", action).data.get("effort_minutes") is None
    (signal,) = [s for s in store.read().list("signal") if s.data["kind"] == "held_declined"]
    assert signal.data["changeset"] == cs_id

    # Keeping a suggestion makes the effort the person's own.
    cs_id, outcome = _assistant_suggests(env, action, 45, "a short job, about 45 minutes")
    release(store, cfg, cs_id, 0)
    assert store.read().get("action", action).data["effort_minutes"] == 45


# ---- the capacity check --------------------------------------------------------------------------------------------


def test_free_time_is_what_the_calendar_leaves_inside_the_working_hours(env):
    _, cfg, store = env
    assert day_capacity.free_minutes(store, cfg, NOW) == 450  # 09:00 to the end of the working day, 16:30
    meeting(store, "Workshop", f"{day(0)}T10:00:00+00:00", f"{day(0)}T15:00:00+00:00")
    assert day_capacity.free_minutes(store, cfg, NOW) == 150
    assert day_capacity.free_minutes(store, cfg, NOW.replace(hour=17)) is None  # the working day is over
    saturday = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
    assert day_capacity.free_minutes(store, cfg, saturday) is None  # not a working day


def test_more_to_do_than_today_holds_is_a_line_that_proposes_what_to_move_and_nothing_else(env):
    ws, cfg, store = env
    meeting(store, "Workshop", f"{day(0)}T10:00:00+00:00", f"{day(0)}T15:00:00+00:00")
    kept = todo(store, cfg, "Send the proposal", 100, promised_to=[make(store, "person", full_name="Quinn Fictional")])
    moved = todo(store, cfg, "Sort the receipts", 100)
    later = todo(store, cfg, "Plan next month", 500, due=day(3))
    unsized = todo(store, cfg, "Water the plants")

    held = day_capacity.check(store, cfg, NOW)
    assert (held.free_minutes, held.needed_minutes, held.over_minutes) == (150, 200, 50)
    assert [m.action for m in held.moves] == [moved] and held.moves[0].due_state == "today"
    assert held.next_day == TODAY + timedelta(days=1)

    line = line_of(today_queue.queue(ws, store, cfg, NOW), "capacity")
    assert (line.group, line.count, line.actions, line.minutes, line.needed_minutes) == ("risk", 1, [moved], 150, 200)
    assert line.due == day(1)
    # Nothing was moved or scheduled.
    view = store.read()
    assert view.get("action", moved).data["due"] == day(0) and view.get("action", kept).data["due"] == day(0)
    assert later and unsized


def test_it_fits_when_the_to_dos_are_small_have_no_effort_or_are_not_due_today(env):
    ws, cfg, store = env
    todo(store, cfg, "Send the proposal", 100)
    assert day_capacity.check(store, cfg, NOW) is None
    todo(store, cfg, "Plan next month", 1000, due=day(2))
    todo(store, cfg, "Water the plants")
    assert line_of(today_queue.queue(ws, store, cfg, NOW), "capacity") is None


def test_a_to_do_tied_to_a_meeting_is_fixed_and_never_proposed(env):
    _, cfg, store = env
    entry = meeting(store, "Review", f"{day(0)}T16:00:00+00:00", f"{day(0)}T16:30:00+00:00")
    todo(store, cfg, "Send the estimate", 600, due_event=entry)
    held = day_capacity.check(store, cfg, NOW)
    assert held.moves == [] and held.still_over == held.over_minutes > 0


def test_moving_a_proposed_to_do_is_the_persons_own_date_change_with_undo(env):
    ws, cfg, store = env
    todo(store, cfg, "Send the proposal", 400, promised_to=promised(store))
    moved = todo(store, cfg, "Sort the receipts", 100)
    held = day_capacity.check(store, cfg, NOW)
    (move,) = held.moves
    assert move.action == moved
    op = {
        "op": "record.edit",
        "record": {"kind": "action", "id": moved},
        "fields": {"due": held.next_day.isoformat(), "due_words": None, "due_check": False},
        "read_version": move.version,
    }
    changeset = apply_as_person(store, cfg, [op], "Moved a to-do")
    assert store.read().get("action", moved).data["due"] == day(1)
    assert day_capacity.check(store, cfg, NOW) is None
    undo_changeset(store, changeset)
    assert store.read().get("action", moved).data["due"] == day(0)
    assert [m.action for m in day_capacity.check(store, cfg, NOW).moves] == [moved]


def test_the_brief_carries_the_same_line_and_opens_todays(env):
    ws, cfg, store = env
    todo(store, cfg, "Send the proposal", 400, promised_to=promised(store))
    todo(store, cfg, "Sort the receipts", 100)
    found = brief.build(ws, store, cfg, NOW, "morning")
    risk = next(s for s in found.sections if s.key == "risk")
    line = line_of(risk.lines, "capacity")
    assert (line.minutes, line.needed_minutes, line.count, line.queue) == (450, 500, 1, "capacity")


# ---- clashes from today onward ------------------------------------------------------------------------------------


def test_clashes_after_today_include_too_little_travel_time_and_stop_at_the_days_ahead(env):
    ws, cfg, store = env
    ahead = cfg.steward.clashes.days_ahead
    travel = cfg.steward.clashes.travel_minutes
    assert ahead >= 2 and travel > 10
    connected(store, "a", "Site visit", f"{day(2)}T10:00:00+00:00", f"{day(2)}T11:00:00+00:00", "North office")
    connected(store, "b", "Supplier call", f"{day(2)}T11:10:00+00:00", f"{day(2)}T12:00:00+00:00", "South office")
    connected(store, "c", "Online sync", f"{day(2)}T12:05:00+00:00", f"{day(2)}T12:30:00+00:00", "www.example.com/room")
    connected(store, "d", "Standup", f"{day(1)}T09:00:00+00:00", f"{day(1)}T09:30:00+00:00", "North office")
    connected(store, "e", "Review", f"{day(1)}T09:15:00+00:00", f"{day(1)}T10:00:00+00:00", "North office")
    far = ahead + 2
    connected(store, "f", "Far one", f"{day(far)}T09:00:00+00:00", f"{day(far)}T10:00:00+00:00")
    connected(store, "g", "Far two", f"{day(far)}T09:30:00+00:00", f"{day(far)}T10:30:00+00:00")

    found = day_clashes.upcoming(store, cfg, NOW)
    assert [(c.state, c.minutes, c.day.isoformat()) for c in found] == [
        ("overlap", 15, day(1)),
        ("travel", travel - 10, day(2)),
    ]
    lines = [x for x in today_queue.queue(ws, store, cfg, NOW) if x.kind == "clash"]
    assert [(x.group, x.state, x.text, x.other, x.due) for x in lines] == [
        ("risk", "overlap", "Standup", "Review", day(1)),
        ("risk", "travel", "Site visit", "Supplier call", day(2)),
    ]
    in_brief = [x for s in brief.build(ws, store, cfg, NOW, "morning").sections for x in s.lines if x.kind == "clash"]
    assert [(x.state, x.minutes, x.day) for x in in_brief] == [("overlap", 15, day(1)), ("travel", travel - 10, day(2))]


def test_a_clash_that_has_already_ended_today_is_left_out(env):
    _, cfg, store = env
    connected(store, "a", "Early one", f"{day(0)}T07:00:00+00:00", f"{day(0)}T08:00:00+00:00")
    connected(store, "b", "Early two", f"{day(0)}T07:30:00+00:00", f"{day(0)}T08:30:00+00:00")
    assert day_clashes.upcoming(store, cfg, NOW) == []


# ---- the attention budget ------------------------------------------------------------------------------------------


class Fake:
    """A suggestion line as the queue makes it, for the attention rules."""

    def __init__(self, kind, key, count=1, actions=(), questions=()):
        self.kind, self.key, self.count = kind, key, count
        self.actions, self.questions = list(actions), list(questions)


def keys(lines):
    return [x.key for x in lines]


def test_only_suggestions_are_held_back_and_the_most_important_come_first(tmp_path):
    _, cfg, store = build(tmp_path, COCKPIT__STEWARD__ATTENTION__DAILY_CAP="1")
    try:
        lines = [
            Fake("stale", "stale", actions=["ACT-1"]),
            Fake("escalate", "escalate:p:q", questions=["Q-1"]),
            Fake("overdue", "overdue"),
        ]
        found = suggestions.split(cfg, store.read(), lines, NOW)
        assert keys(found.shown) == ["escalate:p:q", "overdue"] or keys(found.shown) == ["overdue", "escalate:p:q"]
        assert "stale" not in keys(found.shown) and keys(found.digest) == ["stale"]
    finally:
        store.close()


def test_a_suggestion_below_the_threshold_is_neither_shown_nor_saved_for_the_brief(tmp_path):
    _, cfg, store = build(tmp_path, COCKPIT__STEWARD__ATTENTION__THRESHOLD="0.5")
    try:
        lines = [Fake("stale", "stale", actions=["ACT-1"]), Fake("escalate", "escalate:p:q", questions=["Q-1"])]
        found = suggestions.split(cfg, store.read(), lines, NOW)
        assert keys(found.shown) == ["escalate:p:q"] and found.digest == []
    finally:
        store.close()


def test_quiet_hours_save_suggestions_for_the_brief_but_never_hold_back_what_is_due(tmp_path):
    _, cfg, store = build(tmp_path, COCKPIT__STEWARD__ATTENTION__QUIET="true")
    try:
        lines = [Fake("stale", "stale", actions=["ACT-1"]), Fake("overdue", "overdue")]
        night = NOW.replace(hour=22)
        assert cfg.steward.reminders.quiet_start <= "22:00"
        found = suggestions.split(cfg, store.read(), lines, night)
        assert keys(found.shown) == ["overdue"] and keys(found.digest) == ["stale"]
        assert keys(suggestions.split(cfg, store.read(), lines, NOW).shown) == ["stale", "overdue"]
    finally:
        store.close()


def test_not_now_sticks_until_something_changes_and_undo_brings_it_back(env):
    _, cfg, store = env
    line = Fake("stale", "stale", count=2, actions=["ACT-1", "ACT-2"])
    assert keys(suggestions.split(cfg, store.read(), [line], NOW).shown) == ["stale"]

    signal = suggestions.put_off(store, cfg, line, NOW)
    recorded = store.read().get("signal", signal)
    assert recorded.data["kind"] == "suggestion_dismissed" and recorded.data["refs"] == ["ACT-1", "ACT-2"]
    assert keys(suggestions.split(cfg, store.read(), [line], NOW).shown) == []
    # Still off later, and when nothing about it changed.
    assert keys(suggestions.split(cfg, store.read(), [line], NOW + timedelta(days=3)).shown) == []
    # Something about it changed: another to-do joined it.
    changed = Fake("stale", "stale", count=3, actions=["ACT-1", "ACT-2", "ACT-3"])
    assert keys(suggestions.split(cfg, store.read(), [changed], NOW).shown) == ["stale"]
    # A different suggestion of the same kind is not put off with it.
    other = Fake("escalate", "escalate:p:q", questions=["Q-1"])
    assert keys(suggestions.split(cfg, store.read(), [other], NOW).shown) == ["escalate:p:q"]

    assert suggestions.take_back(store, signal)
    assert keys(suggestions.split(cfg, store.read(), [line], NOW).shown) == ["stale"]
    assert not suggestions.take_back(store, signal)


def test_what_was_put_off_today_counts_against_the_days_cap(tmp_path):
    _, cfg, store = build(tmp_path, COCKPIT__STEWARD__ATTENTION__DAILY_CAP="1")
    try:
        first = Fake("stale", "stale", actions=["ACT-1"])
        suggestions.put_off(store, cfg, first, NOW)
        other = Fake("unfiled", "unfiled", count=2)
        assert keys(suggestions.split(cfg, store.read(), [other], NOW).digest) == ["unfiled"]
        tomorrow = NOW + timedelta(days=1)
        assert keys(suggestions.split(cfg, store.read(), [other], tomorrow).shown) == ["unfiled"]
    finally:
        store.close()


def test_the_queue_leaves_out_what_the_rules_hold_and_the_brief_carries_it(tmp_path, monkeypatch):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__ATTENTION__DAILY_CAP="0")
    try:
        lines = [
            today_queue.Line(key="stale", group="review", kind="stale", count=2, actions=["ACT-1", "ACT-2"], since="a"),
            today_queue.Line(key="overdue", group="risk", kind="overdue", count=1, since="a"),
        ]
        monkeypatch.setattr(today_queue, "_everything", lambda *a, **k: lines)
        assert keys(today_queue.queue(ws, store, cfg, NOW)) == ["overdue"]
        found = brief.build(ws, store, cfg, NOW, "morning")
        yes = next(s for s in found.sections if s.key == "yes")
        digest = line_of(yes.lines, "digest")
        assert (digest.change, digest.count, digest.queue) == ("stale", 2, "stale")
    finally:
        store.close()


# ---- the reminder offer --------------------------------------------------------------------------------------------


def test_a_reminder_is_offered_for_the_working_morning_before_a_to_do_with_a_day_coming_up(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__BRIEF__MAX_LINES="20")
    soon = todo(store, cfg, "Decide on the renewal", due=day(3))
    todo(store, cfg, "Already reminded", due=day(3), remind_at=(NOW + timedelta(days=1)).isoformat())
    todo(store, cfg, "Too far ahead", due=day(10))
    todo(store, cfg, "Due today", due=day(0))
    found = brief.build(ws, store, cfg, NOW, "morning")
    yes = next(s for s in found.sections if s.key == "yes")
    (offer,) = [x for x in yes.lines if x.change == "reminder_offer"]
    start = cfg.steward.reminders.working_start
    assert (offer.text, offer.day, offer.at, offer.link) == ("Decide on the renewal", day(2), start, ("action", soon))
    assert offer.when == f"{day(2)}T{start}:00+00:00"


def test_no_offer_is_made_when_the_setting_is_off(tmp_path):
    ws, cfg, store = build(tmp_path, COCKPIT__STEWARD__BRIEF__OFFER_REMINDERS="false")
    try:
        todo(store, cfg, "Decide on the renewal", due=day(3))
        found = brief.build(ws, store, cfg, NOW, "morning")
        assert all(x.change != "reminder_offer" for s in found.sections for x in s.lines)
    finally:
        store.close()


def test_the_effort_cases_of_both_workspaces_pass_on_their_stub_answers():
    from engine.evaluate import evaluate
    from tests.conftest import DEMO_A

    for template in (DEMO_A, DEMO_B):
        results = [
            r
            for r in evaluate(template, stub=True, runs=1, env={}).results
            if r.case == "effort-stated-for-an-open-todo"
        ]
        assert results and all(r.passed and not r.missing and not r.forbidden for r in results), results
