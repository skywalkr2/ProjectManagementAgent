"""The morning brief, the evening wrap-up and the Monday briefing (design 6.32), built from the records by rules:
which form is due, each section's lines and their order, an empty section left out, a quiet day, the wrap-up's credit
to whoever did the work, the Monday form with nothing Today already holds repeated, what changed in an invitation, and
the ten sample mornings of the fictional workspaces (`workspaces/*/briefs`). Names, ids and days come from the fixtures
and the settings; times move with the store's own clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine import brief
from engine.brief_cases import LEFT, load_cases, score
from engine.brief_cases import run as run_case
from engine.followups import put_on_hold
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B

# A Monday at 9:00 on the person's clock (UTC here), and the clock of the store.
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.brief")
_RULE = WriteContext(actor="engine", trust="untrusted", op="calendar.keep")
ZONE_UTC = {"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> str:
        return self.now.isoformat(timespec="seconds")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env=ZONE_UTC)
    clock = Clock()
    store = Store(ws.db_path, cfg=cfg, clock=clock)
    yield ws, cfg, store, clock
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def make(store, kind, ctx=_TEST, **data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, ctx).id


def someone(store, name="Quinn Fictional", **more) -> str:
    return make(store, "person", full_name=name, **more)


def own(store, cfg, text, due=None, **more) -> str:
    return make(store, "action", text=text, owners=[{"person": me(cfg)}], due=due, **more)


def update(store, kind, record_id, ctx=_TEST, **changes) -> None:
    with store.transaction() as tx:
        found = tx.get(kind, record_id)
        tx.update(kind, record_id, changes, ctx, read_version=found.version)


def built(env, form=None, now=NOW):
    ws, cfg, store, _ = env
    return brief.build(ws, store, cfg, now, form)


def section(found, key):
    return next((s for s in found.sections if s.key == key), None)


def lines_of(found, key) -> list[brief.Line]:
    s = section(found, key)
    return s.lines if s is not None else []


def with_key(found, prefix) -> list[brief.Line]:
    return [line for s in found.sections for line in s.lines if line.key.startswith(prefix)]


# ---- which form is due ---------------------------------------------------------------------------------------------


def at_clock(offset: int, text: str, minutes: int = 0) -> datetime:
    """The moment `text` (a time of day) falls on the day `offset` days from the Monday, `minutes` later."""
    hour, minute = text.split(":")
    return datetime(TODAY.year, TODAY.month, TODAY.day, int(hour), int(minute), tzinfo=UTC) + timedelta(
        days=offset, minutes=minutes
    )


def test_the_form_due_follows_the_time_of_day_and_the_day_of_the_week(env):
    _, cfg, _, _ = env
    rule = cfg.steward.brief
    assert brief.available(cfg, at_clock(0, "09:00")) == [
        "monday",
        "morning",
    ]  # the weekly day: the week, then the morning
    assert brief.available(cfg, at_clock(1, "09:00"), goals_confirmed=True) == ["morning"]
    assert brief.available(cfg, at_clock(1, rule.morning_from, -1)) == []  # before the morning time there is no brief
    assert brief.available(cfg, at_clock(1, rule.morning_from), goals_confirmed=True) == ["morning"]  # from the minute
    assert brief.available(cfg, at_clock(1, rule.evening_from, -1), goals_confirmed=True) == ["morning"]
    assert brief.available(cfg, at_clock(1, rule.evening_from)) == ["evening"]  # the wrap-up takes the morning's place
    assert brief.available(cfg, at_clock(0, "23:30")) == ["evening"]


def test_the_monday_briefing_is_offered_on_a_later_working_day_until_the_weeks_goals_are_confirmed(env):
    from engine import week_plan

    ws, cfg, store, _ = env
    wednesday = at_clock(2, "09:00")
    assert brief.available(cfg, wednesday) == ["morning", "monday"]  # the first open of the week isn't the first day
    assert built(env, now=wednesday).forms == ["morning", "monday"]
    assert built(env, now=wednesday).form == "morning"
    week_plan.set_goals(store, cfg, ["One", "Two", "Three"], NOW)
    assert built(env, now=wednesday).forms == ["morning"]  # used: nothing more to offer
    assert brief.available(cfg, at_clock(5, "09:00")) == ["morning"]  # a day off isn't a day of the week


def test_the_weekly_day_and_the_times_are_settings(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(
        env={
            **ZONE_UTC,
            "COCKPIT__STEWARD__BRIEF__WEEKLY_DAY": "tuesday",
            "COCKPIT__STEWARD__BRIEF__MORNING_FROM": "08:00",
            "COCKPIT__STEWARD__BRIEF__EVENING_FROM": "16:00",
        }
    )
    assert brief.available(cfg, at_clock(0, "09:00")) == ["morning"]
    assert brief.available(cfg, at_clock(1, "09:00")) == ["monday", "morning"]
    assert brief.available(cfg, at_clock(1, "07:59")) == [] and brief.available(cfg, at_clock(1, "16:00")) == [
        "evening"
    ]


def test_settings_that_make_no_sense_are_refused_with_the_reason(tmp_path):
    from engine.config.loader import ConfigError

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    with pytest.raises(ConfigError, match="evening wrap-up must start after"):
        ws.config(env={"COCKPIT__STEWARD__BRIEF__EVENING_FROM": "05:00"})
    with pytest.raises(ConfigError, match="fewest goals"):
        ws.config(env={"COCKPIT__STEWARD__BRIEF__GOALS_MIN": "6", "COCKPIT__STEWARD__BRIEF__GOALS_MAX": "4"})
    with pytest.raises(ConfigError, match="time of day"):
        ws.config(env={"COCKPIT__STEWARD__BRIEF__MORNING_FROM": "morning"})


def test_nothing_is_due_when_the_brief_is_turned_off(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={**ZONE_UTC, "COCKPIT__STEWARD__BRIEF__ENABLED": "false"})
    store = Store(ws.db_path, cfg=cfg)
    try:
        found = brief.build(ws, store, cfg, NOW)
        assert (found.form, found.forms, found.sections) == (None, [], [])
    finally:
        store.close()


def test_a_form_can_be_asked_for_at_any_time_and_an_unknown_one_is_refused(env):
    found = built(env, "evening", at_clock(1, "04:00"))
    assert found.form == "evening" and found.forms == [
        "evening"
    ]  # asked for, though none is due at four in the morning
    ws, cfg, store, _ = env
    with pytest.raises(ValueError, match="no"):
        brief.build(ws, store, cfg, NOW, "noon")


# ---- the morning brief ---------------------------------------------------------------------------------------------


def test_a_day_with_nothing_to_say_is_quiet_and_has_no_sections(tmp_path):
    ws = init_workspace(tmp_path / "ws", git=False)
    cfg = ws.config(env=ZONE_UTC)
    store = Store(ws.db_path, cfg=cfg)
    try:
        found = brief.build(ws, store, cfg, NOW + timedelta(days=1), "morning")
        assert found.form == "morning" and found.quiet and found.sections == []
    finally:
        store.close()


def test_the_sections_come_changed_then_risk_then_yes_and_an_empty_one_is_left_out(env):
    ws, cfg, store, _ = env
    # What the fixtures hold waits for the person's yes (the decision), so a day with only an at-risk line has two.
    own(store, cfg, "Send the estimate", due=day(0))
    found = built(env, "morning")
    assert [s.key for s in found.sections] == ["risk", "yes"] and not found.quiet
    assert all(s.lines for s in found.sections)
    assert "decision" in {line.change for line in lines_of(found, "yes")}


def test_the_persons_own_to_do_due_today_or_late_is_at_risk_and_says_which_and_when(env):
    ws, cfg, store, _ = env
    to = someone(store)
    today_id = own(store, cfg, "Send the estimate", due=day(0), promised_to=[to])
    late_id = own(store, cfg, "Return the signed form", due=day(-3))
    later_id = own(store, cfg, "Plan the review", due=day(2))
    done_id = own(store, cfg, "Send the invoice", due=day(0), status="done", done_by=[me(cfg)])
    held_id = own(store, cfg, "Wait for the quote", due=day(0))
    put_on_hold(store, held_id, "the quote", now=NOW)
    found = built(env, "morning")
    made = {today_id, late_id, later_id, done_id, held_id}
    mine = {line.link[1]: line for line in lines_of(found, "risk") if line.kind == "own_due" and line.link[1] in made}
    assert set(mine) == {today_id, late_id}
    assert later_id not in mine and done_id not in mine and held_id not in mine
    assert (mine[today_id].state, mine[today_id].day, mine[today_id].person) == ("today", day(0), to)
    assert (mine[late_id].state, mine[late_id].days) == ("overdue", 3)
    # The late one is listed first.
    ordered = [line.link[1] for line in lines_of(found, "risk") if line.kind == "own_due" and line.link[1] in made]
    assert ordered == [late_id, today_id]


def test_the_time_of_the_meeting_a_promise_is_due_at_says_when_it_bites(env):
    ws, cfg, store, _ = env
    meeting = make(store, "event", trust="trusted", title="Print review", start=f"{day(0)}T12:00:00+00:00")
    action = own(store, cfg, "Send the estimate", due=day(0), due_event=meeting)
    line = next(x for x in lines_of(built(env, "morning"), "risk") if x.link == ("action", action))
    assert line.at == "12:00"


def test_what_someone_owes_the_person_and_is_late_is_at_risk_with_who_and_how_late(env):
    ws, cfg, store, _ = env
    owner = someone(store, "Dev Fictional")
    action = make(
        store, "action", text="Send the measurements", owners=[{"person": owner}], due=day(-1), promised_to=[me(cfg)]
    )
    found = built(env, "morning")
    line = next(x for x in lines_of(found, "risk") if x.kind == "owed_late" and x.link == ("action", action))
    assert (line.person, line.person_name, line.days, line.day) == (owner, "Dev Fictional", 1, day(-1))
    assert line.queue is not None and line.queue.split(":")[0] in ("promise", "nudge", "escalate")


def test_meetings_that_overlap_today_are_an_at_risk_line_with_by_how_much(env):
    ws, cfg, store, _ = env
    first = make(
        store,
        "event",
        trust="trusted",
        title="Call with the printer",
        start=f"{day(0)}T10:00:00+00:00",
        end=f"{day(0)}T11:00:00+00:00",
    )
    second = make(
        store,
        "event",
        trust="trusted",
        title="Dentist",
        start=f"{day(0)}T10:30:00+00:00",
        end=f"{day(0)}T11:30:00+00:00",
    )
    other_day = make(
        store,
        "event",
        trust="trusted",
        title="Tomorrow",
        start=f"{day(1)}T10:30:00+00:00",
        end=f"{day(1)}T11:30:00+00:00",
    )
    clashes = [x for x in lines_of(built(env, "morning"), "risk") if x.kind == "clash"]
    assert len(clashes) == 1
    (clash,) = clashes
    assert {clash.text, clash.other} == {"Call with the printer", "Dentist"}
    assert (clash.minutes, clash.day, clash.at) == (30, day(0), "10:30")
    assert first and second and other_day


def test_what_waits_for_the_persons_yes_is_one_line_each_that_opens_the_line_on_today(env):
    ws, cfg, store, _ = env
    from engine.today_queue import queue

    wanted = {q.key: q for q in queue(ws, store, cfg, NOW) if q.kind in brief.YES_KINDS}
    assert wanted, "the fixtures hold a decision for the person"
    found = built(env, "morning")
    yes = lines_of(found, "yes")
    assert {x.queue for x in yes} <= set(wanted)
    assert len(yes) + section(found, "yes").more == len(wanted)  # what doesn't fit is counted, never dropped silently
    assert all(x.kind == "yes" and x.change == wanted[x.queue].kind for x in yes)
    # A message the assistant wrote is "ready"; a decision is not.
    for x in yes:
        assert x.ready is (x.change in brief.READY_KINDS or (x.change == "reply" and bool(wanted[x.queue].reply)))


def test_a_section_shows_at_most_the_configured_lines_and_says_how_many_more(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={**ZONE_UTC, "COCKPIT__STEWARD__BRIEF__MAX_LINES": "2"})
    store = Store(ws.db_path, cfg=cfg)
    try:
        for n in range(5):
            own(store, cfg, f"Finish part {n}", due=day(0))
        found = brief.build(ws, store, cfg, NOW, "morning")
        risk = section(found, "risk")
        every = ws.config(env={**ZONE_UTC, "COCKPIT__STEWARD__BRIEF__MAX_LINES": "20"})
        total = len(section(brief.build(ws, store, every, NOW, "morning"), "risk").lines)
        assert total >= 5 and len(risk.lines) == 2 and risk.more == total - 2
    finally:
        store.close()


def test_no_line_of_any_form_reports_status_or_progress(env):
    ws, cfg, store, _ = env
    own(store, cfg, "Already finished", due=day(0), status="done", done_by=[me(cfg)])
    own(store, cfg, "Send the estimate", due=day(0))
    kinds = {line.kind for form in brief.FORMS for s in built(env, form).sections for line in s.lines}
    assert kinds <= {
        "closed",
        "moved",
        "news",
        "invitation",
        "own_due",
        "owed_late",
        "clash",
        "yes",
        "done",
        "carried",
        "waiting",
        "waiting_answer",
        "week_promise",
        "send_question",
        "chase_answer",
        "decision",
    }
    # Nothing that counts how much is done: no line of the morning is about the finished to-do.
    assert not [x for x in built(env, "morning").sections for line in x.lines if line.text == "Already finished"]


# ---- what changed overnight ----------------------------------------------------------------------------------------


@pytest.fixture
def la_env(tmp_path):
    """The workspace on a clock in Los Angeles, with the store's own clock to set: the three of them the way the
    since-yesterday tests make them. Yields the workspace, settings, store and clock."""
    from tests.test_since_yesterday import ENV

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env=ENV)
    clock = Clock()
    store = Store(ws.db_path, cfg=cfg, clock=clock)
    yield ws, cfg, store, clock
    store.close()


def news_of(env, action: dict, at: datetime, *, heard: str, author: str | None = None, by_you: bool = False, key="n"):
    """Apply what a message said about an action (news, which applies on its own) at a moment."""
    from tests.test_since_yesterday import apply_at

    ws, cfg, store, clock = env
    clock.now = at
    op = {"op": "action.news", "id": action["id"], "text": heard, "evidence": {"quote": heard}}
    return apply_at((ws, cfg, store), [op], at, quote_in=f"{heard}.", author=author, by_you=by_you, key=key)


def test_what_someone_else_did_to_the_persons_things_overnight_is_listed_newest_first_with_who(la_env):
    from tests.test_since_yesterday import (
        ADDED_AT,
        CLOSED_AT,
        FLOOR_QUOTE,
        MINE,
        MOVED_AT,
        SENDER,
        THEIRS,
        add_op,
        apply_at,
    )
    from tests.test_since_yesterday import NOW as LA_NOW

    ws, cfg, store, clock = la_env
    clock.now = ADDED_AT
    apply_at((ws, cfg, store), [add_op()], ADDED_AT, quote_in=f"Hello. {FLOOR_QUOTE}. Thanks.", key="added")
    news_of(la_env, THEIRS, CLOSED_AT, heard="The first copy would not open", author=SENDER["full_name"])
    clock.now = MOVED_AT
    update(store, "action", MINE["id"], _RULE, due="2026-10-30")  # the meeting it was due at moved, and it followed
    found = brief.build(ws, store, cfg, LA_NOW, "morning")
    changed = lines_of(found, "changed")
    # Something new is not a change to what the person already had; news and a date that followed its meeting are.
    assert [(x.kind, x.text) for x in changed] == [("moved", MINE["text"]), ("news", THEIRS["text"])]
    moved, news = changed
    assert (moved.change, moved.day, moved.person_name) == ("meeting", "2026-10-30", None)
    assert (news.person_name, news.person, news.detail) == (
        SENDER["full_name"],
        SENDER["id"],
        "The first copy would not open",
    )
    assert moved.link == ("action", MINE["id"]) and news.link == ("action", THEIRS["id"])
    assert found.sections[0].key == "changed"


def test_what_the_person_did_themselves_is_not_a_change(la_env):
    from tests.test_since_yesterday import CLOSED_AT, ME, THEIRS
    from tests.test_since_yesterday import NOW as LA_NOW

    ws, cfg, store, _ = la_env
    news_of(la_env, THEIRS, CLOSED_AT, heard="It is on its way", author=ME["full_name"], by_you=True)
    assert lines_of(brief.build(ws, store, cfg, LA_NOW, "morning"), "changed") == []


def test_a_close_a_rule_made_is_a_change_overnight(tmp_path):
    from tests.test_silent_closes import closed_by_a_rule

    ws, cfg, store, request = closed_by_a_rule(tmp_path)
    try:
        created = datetime.fromisoformat(str(store.read().get("request", request).data["created_at"]))
        cfg = ws.config(env=ZONE_UTC)
        found = brief.build(ws, store, cfg, created + timedelta(hours=1), "morning")
        closed = [x for x in lines_of(found, "changed") if x.kind == "closed"]
        assert len(closed) == 1 and closed[0].text
    finally:
        store.close()


def test_only_what_changed_since_the_evening_before_is_overnight(la_env):
    from tests.test_since_yesterday import MINE, SENDER, THEIRS
    from tests.test_since_yesterday import NOW as LA_NOW

    ws, cfg, store, _ = la_env
    tuesday = LA_NOW + timedelta(days=1)
    start = brief.overnight_start(cfg, tuesday).astimezone(UTC)
    assert start == datetime(2026, 10, 20, 1, 0, tzinfo=UTC)  # Monday 18:00 on the person's clock
    news_of(la_env, THEIRS, start - timedelta(minutes=1), heard="Not overnight", author=SENDER["full_name"], key="a")
    assert lines_of(brief.build(ws, store, cfg, tuesday, "morning"), "changed") == []
    news_of(la_env, MINE, start + timedelta(minutes=1), heard="Overnight", author=SENDER["full_name"], key="b")
    assert [x.text for x in lines_of(brief.build(ws, store, cfg, tuesday, "morning"), "changed")] == [MINE["text"]]


def test_overnight_on_the_first_working_day_starts_on_the_last_working_evening_before(env):
    _, cfg, _, _ = env
    start = brief.overnight_start(cfg, NOW)  # a Monday: back over the weekend to Friday evening
    assert start == datetime(2026, 10, 16, 18, 0, tzinfo=UTC)
    assert brief.overnight_start(cfg, NOW + timedelta(days=2)) == datetime(2026, 10, 20, 18, 0, tzinfo=UTC)


def an_invitation(store, clock, when, title, start, **more) -> str:
    clock.now = when
    organizer = {"address": "organizer@example.com", "name": "Quinn Fictional"}
    return make(
        store,
        "event",
        _RULE,
        title=title,
        start=start,
        end=more.pop("end", None),
        invitation=True,
        organizer=organizer,
        source="SRC-0",
        key=f"key-{title}",
        **more,
    )


def test_what_changed_in_an_invitation_overnight_is_a_line_for_each_change_that_matters(env):
    ws, cfg, store, clock = env
    before = NOW - timedelta(days=4)  # the Thursday before
    overnight = NOW - timedelta(hours=12)  # Sunday evening, after Friday evening
    new = an_invitation(
        store, clock, overnight, "Client review", f"{day(0)}T15:00:00+00:00", end=f"{day(0)}T16:00:00+00:00"
    )
    moved = an_invitation(
        store, clock, before, "Print call", f"{day(0)}T14:00:00+00:00", end=f"{day(0)}T15:00:00+00:00"
    )
    called_off = an_invitation(
        store, clock, before, "Workshop", f"{day(2)}T10:00:00+00:00", end=f"{day(2)}T11:00:00+00:00"
    )
    replies = an_invitation(
        store, clock, before, "Planning", f"{day(1)}T10:00:00+00:00", end=f"{day(1)}T11:00:00+00:00"
    )
    past = an_invitation(store, clock, before, "Last week's call", f"{day(-3)}T10:00:00+00:00")
    clock.now = overnight
    update(store, "event", moved, _RULE, start=f"{day(3)}T10:00:00+00:00", end=f"{day(3)}T11:00:00+00:00")
    update(store, "event", called_off, _RULE, cancelled=True)
    update(
        store, "event", replies, _RULE, attendees=[{"address": "a@example.com", "name": "A", "response": "accepted"}]
    )
    update(store, "event", past, _RULE, start=f"{day(-2)}T10:00:00+00:00")
    found = built(env, "morning")
    changed = lines_of(found, "changed")
    by_event = {line.link[1]: line for line in changed if line.kind == "invitation"}
    assert set(by_event) == {new, moved, called_off}  # a reply, and a meeting already past, are not news
    assert (by_event[new].change, by_event[new].text, by_event[new].person_name) == (
        "new",
        "Client review",
        "Quinn Fictional",
    )
    assert (by_event[new].day, by_event[new].at) == (day(0), "15:00")
    line = by_event[moved]
    assert (line.change, line.from_day, line.from_at, line.day, line.at) == ("moved", day(0), "14:00", day(3), "10:00")
    assert by_event[called_off].change == "cancelled" and by_event[called_off].day == day(2)
    assert replies not in by_event and past not in by_event


def test_an_invitation_changed_before_the_evening_or_not_an_invitation_is_not_overnight_news(env):
    ws, cfg, store, clock = env
    old = an_invitation(store, clock, NOW - timedelta(days=5), "Old call", f"{day(1)}T10:00:00+00:00")
    clock.now = NOW - timedelta(days=4)
    update(store, "event", old, _RULE, cancelled=True)
    clock.now = NOW - timedelta(hours=6)
    plain = make(
        store,
        "event",
        _RULE,
        title="Own entry",
        start=f"{day(1)}T10:00:00+00:00",
        invitation=False,
        key="own-k",
        source="SRC-0",
    )
    update(store, "event", plain, _RULE, cancelled=True)
    assert [x for x in lines_of(built(env, "morning"), "changed") if x.kind == "invitation"] == []


# ---- the evening wrap-up -------------------------------------------------------------------------------------------

EVENING = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)


def at(clock, when) -> None:
    clock.now = when


def test_done_today_is_credited_to_whoever_did_the_work(env):
    ws, cfg, store, clock = env
    other = someone(store, "Dev Fictional")
    mine = own(store, cfg, "Send the proposal", due=day(0))
    theirs = make(
        store, "action", text="Send the illustrations", owners=[{"person": other}], promised_to=[me(cfg)], due=day(0)
    )
    yesterdays = own(store, cfg, "Send the invoice", due=day(-1))
    unrelated = make(store, "action", text="Tidy their files", owners=[{"person": other}])
    at(clock, NOW - timedelta(days=1))
    update(store, "action", yesterdays, status="done", done_by=[me(cfg)])
    at(clock, NOW + timedelta(hours=3))
    update(store, "action", mine, status="done", done_by=[me(cfg)])
    at(clock, NOW + timedelta(hours=5))
    update(store, "action", theirs, status="done", done_by=[other], reported_by=other)
    update(store, "action", unrelated, status="done", done_by=[other])
    found = built(env, "evening", EVENING)
    done = lines_of(found, "done")
    assert [x.link[1] for x in done] == [mine, theirs]  # in the order the work was done, today's alone
    assert (done[0].you, done[0].person_name) == (True, None)
    assert (done[1].you, done[1].person, done[1].person_name) == (False, other, "Dev Fictional")
    assert yesterdays not in {x.link[1] for x in done} and unrelated not in {x.link[1] for x in done}


def test_what_moved_ahead_today_and_what_is_still_open_today_carry_to_tomorrow(env):
    ws, cfg, store, clock = env
    shifted = own(store, cfg, "Edit the website", due=day(0))
    still = own(store, cfg, "Print the estimate", due=day(0))
    later = own(store, cfg, "Plan the review", due=day(3))
    at(clock, NOW + timedelta(hours=2))
    update(store, "action", shifted, due=day(1))
    found = built(env, "evening", EVENING)
    moved = {x.link[1]: x for x in lines_of(found, "moved")}
    assert moved[shifted].kind == "moved_ahead" and moved[shifted].day == day(1)
    assert moved[still].kind == "carried" and moved[still].day == day(0)
    assert later not in moved
    assert not found.quiet


def test_who_still_owes_the_person_and_which_answers_are_awaited_are_waited_on(env):
    ws, cfg, store, clock = env
    other = someone(store, "Dev Fictional")
    owed = make(
        store,
        "action",
        text="Send the third illustration",
        owners=[{"person": other}],
        promised_to=[me(cfg)],
        due=day(2),
    )
    asked = make(
        store,
        "question",
        to=other,
        title="Does the quote include travel?",
        status="sent",
        sent_at=(NOW - timedelta(days=3)).isoformat(),
    )
    found = built(env, "evening", EVENING)
    waiting = {x.link[1]: x for x in lines_of(found, "waiting")}
    assert (waiting[owed].kind, waiting[owed].person_name, waiting[owed].day) == ("waiting", "Dev Fictional", day(2))
    assert (waiting[asked].kind, waiting[asked].days) == ("waiting_answer", 3)


def test_a_wrap_up_with_nothing_moved_and_nobody_waited_on_is_quiet_though_work_was_done(tmp_path):
    ws = init_workspace(tmp_path / "ws", git=False, you="Sam Fictional")
    cfg = ws.config(env=ZONE_UTC)
    clock = Clock()
    store = Store(ws.db_path, cfg=cfg, clock=clock)
    try:
        assert brief.build(ws, store, cfg, EVENING, "evening").quiet  # nothing at all
        action = own(store, cfg, "Send the report", due=day(0))
        clock.now = NOW + timedelta(hours=4)
        update(store, "action", action, status="done", done_by=[me(cfg)])
        found = brief.build(ws, store, cfg, EVENING, "evening")
        assert found.quiet and [s.key for s in found.sections] == ["done"]
    finally:
        store.close()


# ---- the Monday briefing -------------------------------------------------------------------------------------------


def watched(store, name="Oren Fictional") -> str:
    """Someone the person only watches: what they promise is not a line on Today, so the briefing holds it."""
    return someone(store, name, stance="watch")


def test_the_week_lists_what_is_due_through_the_last_working_day_by_who_owns_it(env):
    ws, cfg, store, clock = env
    tracked = watched(store)
    yours = own(store, cfg, "Draft the proposal", due=day(2))
    friday = own(store, cfg, "Check the proofs", due=day(4))
    next_week = own(store, cfg, "Plan next month", due=day(8))
    owed = make(
        store, "action", text="Send the measurements", owners=[{"person": tracked}], promised_to=[me(cfg)], due=day(1)
    )
    found = built(env, "monday")
    assert [x.link[1] for x in lines_of(found, "yours")] == [yours, friday]
    assert [(x.kind, x.state, x.day) for x in lines_of(found, "yours")] == [
        ("week_promise", "due", day(2)),
        ("week_promise", "due", day(4)),
    ]
    assert [(x.link[1], x.person_name) for x in lines_of(found, "owed")] == [(owed, "Oren Fictional")]
    assert next_week not in {x.link[1] for s in found.sections for x in s.lines}
    keys = [s.key for s in found.sections]
    assert keys == sorted(keys, key=["yours", "owed", "send", "chase", "decide"].index)


def test_what_today_already_holds_a_line_for_is_not_repeated_but_counted(env):
    ws, cfg, store, clock = env
    from engine.today_queue import queue

    other = someone(store, "Mira Fictional")
    promise = make(
        store, "action", text="Send the draft", owners=[{"person": other}], promised_to=[me(cfg)], due=day(2)
    )
    on_today = {i for q in queue(ws, store, cfg, NOW) for i in (*q.actions, *q.questions, q.question) if i}
    assert promise in on_today  # what someone owes the person is a line to send or follow up on
    found = built(env, "monday")
    assert promise not in {x.link[1] for s in found.sections for x in s.lines}
    assert found.on_today >= 1  # it links to Today instead


def test_questions_to_send_answers_to_chase_and_decisions_waiting_are_their_own_sections(env):
    ws, cfg, store, clock = env
    other = someone(store, "Mira Fictional")
    held = make(store, "question", to=other, title="Which cover is final?", held_for={"on": day(3)})
    sent = make(store, "question", to=other, title="Who signs off the proof?", status="sent", sent_at=NOW.isoformat())
    found = built(env, "monday")
    assert [x.link[1] for x in lines_of(found, "send")] == [held]
    chase = lines_of(found, "chase")
    assert [(x.link[1], x.kind, x.person_name, x.days) for x in chase] == [(sent, "chase_answer", "Mira Fictional", 0)]
    # The fixtures' decision for the person is a line on Today, so it is counted, not listed again.
    assert section(found, "decide") is None and found.on_today >= 1


def test_a_question_held_for_the_weekly_note_is_in_that_mondays_briefing_and_not_the_one_before(env):
    from engine.followups import hold_question

    ws, cfg, store, clock = env
    other = someone(store, "Mira Fictional")
    asked = make(store, "question", to=other, title="Which cover is final?")
    next_monday = TODAY + timedelta(days=7)
    assert next_monday.weekday() == 0
    assert hold_question(store, asked, {"on": next_monday.isoformat()}, today=TODAY) is None
    assert asked not in [x.link[1] for x in lines_of(built(env, "monday"), "send")]
    # On that Monday it is a line on Today to send, which the briefing counts and links to instead of repeating.
    from engine.today_queue import queue

    later = NOW + timedelta(days=7)
    assert asked in {i for q in queue(ws, store, cfg, later) if q.kind == "send" for i in q.questions}
    assert asked not in [x.link[1] for x in lines_of(built(env, "monday", later), "send")]
    assert built(env, "monday", later).on_today >= 1


def test_goals_are_proposed_from_what_is_due_until_the_person_confirms_them(env):
    ws, cfg, store, clock = env
    for n in range(7):
        own(store, cfg, f"Finish part {n}", due=day(1 + n % 4))
    found = built(env, "monday")
    goals = found.goals
    assert (goals.first, goals.last) == (TODAY, TODAY + timedelta(days=4))
    assert not goals.confirmed and goals.goals == [] and len(goals.proposed) == cfg.steward.brief.goals_max
    assert (goals.fewest, goals.most) == (cfg.steward.brief.goals_min, cfg.steward.brief.goals_max)


def test_confirmed_goals_are_kept_for_the_week_and_read_by_the_morning_brief(env):
    from engine import week_plan

    ws, cfg, store, clock = env
    kept = ["Ship the proof", "Close the print order", "Plan the launch"]
    assert week_plan.set_goals(store, cfg, kept, NOW) == []
    monday = built(env, "monday")
    assert monday.goals.confirmed and monday.goals.goals == kept and monday.goals.proposed == []
    tuesday = built(env, "morning", NOW + timedelta(days=1))
    assert tuesday.goals is not None and tuesday.goals.goals == kept
    assert built(env, "morning", NOW + timedelta(days=7)).goals is None  # next week's brief has no goals yet


def test_a_morning_without_confirmed_goals_carries_none(env):
    assert built(env, "morning").goals is None


def test_the_message_section_exists_only_when_the_person_reports_to_someone(env):
    ws, cfg, store, clock = env
    assert built(env, "monday").message is None
    boss = someone(store, "Lena Fictional", stance="report_to")
    found = built(env, "monday")
    assert found.message.state == "none" and found.message.to == (boss,)


# ---- the ten sample mornings, as cases of both fictional workspaces --------------------------------------------------

WORKSPACES = (DEMO_A, DEMO_B)
CASES = [pytest.param(ws, case, id=f"{ws.name}-{case['id']}") for ws in WORKSPACES for case in load_cases(ws)]


def test_each_workspace_has_all_ten_sample_mornings_as_cases_with_their_day_and_records():
    for ws in WORKSPACES:
        cases = load_cases(ws)
        assert sorted(c["sample"] for c in cases) == list(range(1, 11)), ws.name
        assert all(c["received"] and c["now"] and c["form"] == "morning" for c in cases)
        assert all(c.get("given") for c in cases), "a case carries the records its day starts from"
        quiet = {c["sample"] for c in cases if c.get("quiet")}
        assert quiet == {5, 10}, "the samples that need nothing are the quiet ones"


@pytest.mark.parametrize(("ws", "case"), CASES)
def test_a_sample_morning_makes_the_brief_its_case_expects(ws, case, tmp_path):
    outcome = run_case(ws, case, tmp_path)
    assert outcome.problems == [], outcome.problems


def test_a_case_names_what_no_rule_makes_yet_and_only_that():
    for ws in WORKSPACES:
        for case in load_cases(ws):
            assert set(case.get("left") or []) <= set(LEFT)
    leftover = {c["sample"]: c.get("left") for c in load_cases(DEMO_B) if c.get("left")}
    assert 6 not in leftover and leftover[7] == ["document_dates", "deadline"]


def test_the_scoring_is_exact_a_missing_extra_or_changed_line_and_a_wrong_order_are_each_a_problem(tmp_path):
    case = next(c for c in load_cases(DEMO_B) if c["sample"] == 2)
    good = run_case(DEMO_B, case, tmp_path).made
    assert score(good, case) == []
    short = {**case, "expect": {**case["expect"], "risk": []}}
    assert any("risk: 1 lines where 0" in p for p in score(good, short))
    more = {**case, "expect": {**case["expect"], "risk": [*case["expect"]["risk"], *case["expect"]["risk"]]}}
    assert any("risk: 1 lines where 2" in p for p in score(good, more))
    changed = {**case, "expect": {**case["expect"], "yes": [{**case["expect"]["yes"][0], "ready": False}]}}
    assert any("ready is True, expected False" in p for p in score(good, changed))
    order = {**case, "expect": dict(reversed(list(case["expect"].items())))}
    assert any(p.startswith("sections") for p in score(good, order))
    quiet = {"id": "q", "quiet": True}
    assert score(good, quiet)  # a brief with lines is not a quiet day
