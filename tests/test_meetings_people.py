"""Prep before a calendar entry, capture after it, and people memory (design 6.32, 7.14): every part is worked out by
rules from the records, each with the words or the record it rests on, and the only AI work is the prep note, a draft
that is estimated and held for the person's go. Names, ids and addresses come from the fixtures or are made up here;
the AI is the stub."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import meeting_prep, people_memory
from engine import packet as packets
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import apply_as_person
from engine.config.schema import Price
from engine.dispatcher import process
from engine.meeting_guests import with_others
from engine.names import People
from engine.storage import Store, StoreError, WriteContext
from engine.tasks import task_kind
from engine.texts import versions
from engine.today import zone
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.meetings")
_WATCH = WriteContext(actor="engine", trust="untrusted", op="test.watch")
TOKEN = "meetings-people-token"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def me(cfg) -> str:
    return cfg.workspace.user.person


def person(store, name: str, **more) -> str:
    with store.transaction() as tx:
        return tx.create("person", {"full_name": name, **more}, _TEST).id


def email_of(name: str) -> str:
    return f"{name.split()[0].lower()}@example.com"


def at(days: float = 0, hours: float = 0) -> str:
    return (NOW + timedelta(days=days, hours=hours)).isoformat()


def entry(store, title="Design review", start=None, end=None, guests=(), **more) -> str:
    """A calendar entry; `guests` are (person id, response) pairs, or dicts for someone the workspace doesn't know."""
    attendees = [g if isinstance(g, dict) else {"person": g[0], "response": g[1]} for g in guests]
    start = start or at(hours=6)
    data = {"title": title, "start": start, "end": end or start, "attendees": attendees, "trust": "trusted", **more}
    with store.transaction() as tx:
        return tx.create("event", data, _TEST).id


def promise(
    store, cfg, owner: str, to: str | None = None, text="Send the proofs", quote="I will send the proofs", **more
):
    data = {
        "text": text,
        "owners": [{"person": owner}],
        "promised_to": [to] if to else [],
        "basis": "said",
        "evidence": {"source": "note", "quote": quote},
        **more,
    }
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


def question(store, to: str, title="Which trim size do you want?", **more) -> str:
    with store.transaction() as tx:
        return tx.create("question", {"to": to, "title": title, **more}, _TEST).id


def update(store, kind: str, record_id: str, changes: dict) -> None:
    with store.transaction() as tx:
        tx.update(kind, record_id, changes, _TEST, read_version=tx.get(kind, record_id).version)


def mail(store, sender: str, *, to=(), received=None, key="m1") -> None:
    """A mail item a watched mailbox holds, as its snapshot: from `sender`, to the people in `to`."""
    with store.transaction() as tx:
        tx.create(
            "snapshot",
            {
                "source": "mailbox",
                "key": key,
                "title": "Re: the proofs",
                "content_hash": "0" * 64,
                "seen_at": NOW.isoformat(),
                "message": {"sender": sender, "received": received or at(days=-2), "participants": list(to)},
            },
            _WATCH,
        )


def prep(env, entry_id):
    _, cfg, store = env
    return meeting_prep.prep(store, cfg, entry_id, NOW)


# ---- prep: who is coming -------------------------------------------------------------------------------------------


def test_who_is_coming_is_by_id_without_the_person_or_anyone_who_declined(env):
    _, cfg, store = env
    ana, ben, cy = person(store, "Ana Guest"), person(store, "Ben Guest"), person(store, "Cy Guest")
    nobody = {"name": "Unknown Guest", "address": "stranger@example.net"}
    found = entry(store, guests=[(me(cfg), "accepted"), (ana, "accepted"), (ben, "declined"), (cy, None), nobody])
    shown = prep(env, found)
    assert [g.person for g in shown.coming] == [ana, cy, None]
    assert shown.coming[2].name == "Unknown Guest" and [p.person for p in shown.people] == [ana, cy]
    assert shown.untrusted is False and shown.over is False


def test_an_entry_the_person_declined_or_that_was_called_off_has_nobody_coming_to_prepare_for(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    declined = entry(store, guests=[(ana, "accepted")], response="declined")
    off = entry(store, guests=[(ana, "accepted")], cancelled=True)
    view = store.read()
    assert [with_others(view, cfg, view.get("event", found)) for found in (declined, off)] == [[], []]
    assert meeting_prep.prep_lines(store, cfg, NOW) == [] and meeting_prep.capture_lines(store, cfg, NOW) == []


# ---- prep: what is open with each of them -------------------------------------------------------------------------


def test_the_open_things_with_each_person_are_promises_both_ways_questions_and_replies_owed_with_their_words(env):
    _, cfg, store = env
    ana, ben = person(store, "Ana Guest"), person(store, "Ben Guest")
    mine = promise(store, cfg, me(cfg), ana, "Send Ana the cover", "I'll send the cover")
    theirs = promise(store, cfg, ana, me(cfg), "Return the contract", "I will return the contract", due="2026-10-30")
    owed = promise(
        store, cfg, me(cfg), None, "Reply to Ana about the date", "when can we start?", reply_owed=True, asker=ana
    )
    asked = question(store, ana)
    promise(store, cfg, me(cfg), ben, "Send Ben the plan")  # someone else's
    promise(store, cfg, ben, me(cfg), "Ben's own promise")
    question(store, ben, "A question for Ben")
    shown = prep(env, entry(store, guests=[(ana, "accepted")]))
    (one,) = shown.people
    assert [(i.id, i.quote) for i in one.promised_to] == [(mine, "I'll send the cover")]
    assert [(i.id, i.quote, i.due) for i in one.promised_by] == [
        (theirs, "I will return the contract", date(2026, 10, 30))
    ]
    assert [i.id for i in one.asked_by] == [owed] and one.asked_by[0].quote == "when can we start?"
    assert [i.id for i in one.asked_of] == [asked] and one.asked_of[0].quote is None
    assert one.more == 0 and one.open == 4


def test_a_promise_someone_made_to_a_third_person_is_not_open_between_the_two_of_them(env):
    _, cfg, store = env
    ana, ben = person(store, "Ana Guest"), person(store, "Ben Guest")
    promise(store, cfg, ana, ben, "Ana promised Ben a file")
    (one,) = prep(env, entry(store, guests=[(ana, "accepted")])).people
    assert one.open == 0


def test_a_cap_keeps_the_most_pressing_kinds_and_counts_the_rest(env):
    _, cfg, store = env
    cfg.steward.meetings.max_items = 2
    ana = person(store, "Ana Guest")
    mine = [promise(store, cfg, me(cfg), ana, f"Send part {n}") for n in range(2)]
    question(store, ana)
    promise(store, cfg, ana, me(cfg), "Their promise")
    (one,) = prep(env, entry(store, guests=[(ana, "accepted")])).people
    assert sorted(i.id for i in one.promised_to) == sorted(mine) and one.promised_by == [] and one.asked_of == []
    assert one.more == 2 and one.open == 4


# ---- prep: last in touch and what the last meeting left open ---------------------------------------------------------


def test_the_last_time_in_touch_is_the_latest_of_their_mail_the_persons_mail_a_copied_message_and_a_past_entry(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest", how_to_reach={"email": email_of("Ana Guest")})
    update(store, "person", me(cfg), {"how_to_reach": {"email": "me@example.com"}})
    sender_me = f"{store.read().get('person', me(cfg)).data['full_name']} <me@example.com>"
    mail(store, f"Ana Guest <{email_of('Ana Guest')}>", received=at(days=-5), key="a")
    mail(store, sender_me, to=[f"Ana Guest <{email_of('Ana Guest')}>"], received=at(days=-3), key="b")
    touch, written_from = people_memory.last_in_touch(store.read(), cfg, People(store, cfg), ana, NOW)
    assert (touch.kind, touch.on, touch.untrusted) == ("to", date(2026, 10, 17), True)
    assert touch.subject == "Re: the proofs" and written_from == f"Ana Guest <{email_of('Ana Guest')}>"
    with store.transaction() as tx:
        tx.create("copy", {"kind": "follow_up", "person": ana, "text": "Hello", "at": at(days=-1)}, _TEST)
    touch, _ = people_memory.last_in_touch(store.read(), cfg, People(store, cfg), ana, NOW)
    assert (touch.kind, touch.on, touch.record_kind) == ("to", date(2026, 10, 19), "copy")
    entry(store, "Last sync", start=at(hours=-24), end=at(hours=-23), guests=[(ana, "accepted")])
    touch, _ = people_memory.last_in_touch(store.read(), cfg, People(store, cfg), ana, NOW)
    assert (touch.kind, touch.on, touch.subject) == ("to", date(2026, 10, 19), None)
    entry(store, "Later sync", start=at(hours=-2), end=at(hours=-1), guests=[(ana, "accepted")])
    touch, _ = people_memory.last_in_touch(store.read(), cfg, People(store, cfg), ana, NOW)
    assert (touch.kind, touch.on, touch.subject) == ("met", date(2026, 10, 20), "Later sync")


def test_nobody_in_touch_yet_is_none_and_an_entry_still_ahead_is_not_a_meeting_held(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    entry(store, guests=[(ana, "accepted")])
    assert people_memory.last_in_touch(store.read(), cfg, People(store, cfg), ana, NOW) == (None, None)


def test_the_last_meeting_with_a_person_shows_what_it_left_open_without_repeating_their_own_items(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    last = entry(store, "Kickoff", start=at(days=-3), end=at(days=-3, hours=1), guests=[(ana, "accepted")])
    entry(store, "Older sync", start=at(days=-9), end=at(days=-9, hours=1), guests=[(ana, "accepted")])
    tied = promise(store, cfg, me(cfg), None, "Book the room", "I'll book the room", event=last)
    shared = promise(store, cfg, me(cfg), ana, "Send Ana the cover", event=last)
    settled = promise(store, cfg, me(cfg), None, "Already done", status="done", event=last)
    asked = question(store, ana, "Who signs off?", event=last)
    (one,) = prep(env, entry(store, guests=[(ana, "accepted")])).people
    assert one.left_open.event == last and one.left_open.title == "Kickoff" and one.left_open.on == date(2026, 10, 17)
    assert sorted(i.id for i in one.left_open.items) == sorted([tied])
    assert shared in [i.id for i in one.promised_to] and asked in [i.id for i in one.asked_of] and settled
    assert people_memory.open_with(store.read(), me(cfg), ana, TODAY, zone(cfg))["asked_of"]


# ---- the lines on Today ---------------------------------------------------------------------------------------------


def test_the_prep_line_shows_within_the_configured_hours_before_an_entry_with_others_and_goes_when_it_starts(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    soon = entry(store, "Design review", start=at(hours=5), guests=[(ana, "accepted")])
    entry(store, "Next week", start=at(days=7), guests=[(ana, "accepted")])
    entry(store, "Alone", start=at(hours=2))
    entry(store, "Started", start=at(hours=-1), end=at(hours=1), guests=[(ana, "accepted")])
    promise(store, cfg, me(cfg), ana)
    (line,) = meeting_prep.prep_lines(store, cfg, NOW)
    assert (line.event, line.title, line.people, line.others, line.open) == (soon, "Design review", [ana], 1, 1)
    cfg.steward.meetings.prep_hours_before = 3
    assert meeting_prep.prep_lines(store, cfg, NOW) == []
    cfg.steward.meetings.prep_hours_before = 24
    assert [x.event for x in meeting_prep.prep_lines(store, cfg, NOW + timedelta(hours=5, seconds=1))] == []


def test_a_minimum_of_open_things_keeps_the_line_off_an_entry_with_nothing_to_prepare(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    entry(store, start=at(hours=5), guests=[(ana, "accepted")])
    cfg.steward.meetings.prep_min_open = 1
    assert meeting_prep.prep_lines(store, cfg, NOW) == []
    question(store, ana)
    assert len(meeting_prep.prep_lines(store, cfg, NOW)) == 1


def test_the_capture_line_shows_after_an_entry_with_others_ends_for_the_configured_hours_until_it_is_captured(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    ended = entry(store, "Design review", start=at(hours=-3), end=at(hours=-2), guests=[(ana, "accepted")])
    entry(store, "Still on", start=at(hours=-1), end=at(hours=1), guests=[(ana, "accepted")])
    entry(store, "Long ago", start=at(days=-4), end=at(days=-4, hours=1), guests=[(ana, "accepted")])
    entry(store, "Alone", start=at(hours=-3), end=at(hours=-2))
    (line,) = meeting_prep.capture_lines(store, cfg, NOW)
    assert (line.event, line.title, line.others) == (ended, "Design review", 1) and line.end == NOW - timedelta(hours=2)
    cfg.steward.meetings.capture_hours_after = 1
    assert meeting_prep.capture_lines(store, cfg, NOW) == []


def test_today_carries_the_prep_capture_and_quiet_lines_with_their_data_and_marks_outside_titles(env):
    ws, cfg, store = env
    ana = person(store, "Ana Guest")
    soon = entry(store, "Design review", start=at(hours=5), guests=[(ana, "accepted")], trust="untrusted")
    ended = entry(store, "Kickoff", start=at(hours=-3), end=at(hours=-2), guests=[(ana, "accepted")])
    found = {line.kind: line for line in queue(ws, store, cfg, NOW) if line.kind in ("meeting_prep", "meeting_capture")}
    prep_line, capture_line = found["meeting_prep"], found["meeting_capture"]
    assert (prep_line.event, prep_line.text, prep_line.names, prep_line.count, prep_line.group) == (
        soon,
        "Design review",
        ["Ana Guest"],
        1,
        "review",
    )
    assert prep_line.untrusted is True and prep_line.at.startswith("2026-10-20T17:00") and prep_line.open_items == 0
    assert (capture_line.event, capture_line.text, capture_line.untrusted) == (ended, "Kickoff", False)


# ---- capture ----------------------------------------


def test_capture_hands_the_persons_words_in_as_a_note_tied_to_the_entry_and_the_line_goes(env):
    ws, cfg, store = env
    ana = person(store, "Ana Guest")
    ended = entry(store, "Kickoff", start=at(hours=-3), end=at(hours=-2), guests=[(ana, "accepted")])
    words = "Ana agreed to send the contract by Friday, and I will book the room."
    done = meeting_prep.capture(ws, store, cfg, ended, f"  {words}  ", NOW)
    request = store.read().get("request", done.request).data
    source = store.read().get("source", request["source"]).data
    assert (request["task"], request["origin"], request["state"]) == ("notes", "pm", "queued")
    assert request["about"] == {"kind": "event", "id": ended} and source["kind"] == "note:meeting_capture"
    assert source["trust"] == "trusted" and source["author"] == me(cfg)
    assert (ws.sources_dir / f"{source['content_hash']}.txt").read_text(encoding="utf-8") == words
    assert store.read().get("event", ended).data["captured_at"] and meeting_prep.capture_lines(store, cfg, NOW) == []
    built = packets.build(ws, store, cfg, done.request, TODAY)
    assert words in built.task.request and ended in built.task.request and 'in "event"' in built.task.request
    assert '<untrusted source="record">' in built.task.request and built.knowledge is not None


def test_saying_there_is_nothing_to_note_ends_the_line_and_makes_no_run(env):
    ws, cfg, store = env
    ana = person(store, "Ana Guest")
    ended = entry(store, start=at(hours=-3), end=at(hours=-2), guests=[(ana, "accepted")])
    before = len(store.read().list("request"))
    assert meeting_prep.capture(ws, store, cfg, ended, "   ", NOW).request is None
    assert len(store.read().list("request")) == before and meeting_prep.capture_lines(store, cfg, NOW) == []
    again = entry(store, "Second", start=at(hours=-3), end=at(hours=-2), guests=[(ana, "accepted")])
    assert meeting_prep.capture(ws, store, cfg, again, "ok", NOW).request is None  # a bare confirmation reads nothing
    assert store.read().get("event", again).data["captured_at"]


def test_capturing_an_entry_that_isnt_there_is_refused(env):
    ws, cfg, store = env
    with pytest.raises(StoreError, match="no calendar entry"):
        meeting_prep.capture(ws, store, cfg, "EVT-9999", "Something happened.", NOW)


# ---- people memory ----------------------------------------


def test_how_a_person_likes_to_be_reached_is_what_is_kept_and_the_channel_they_last_wrote_from(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest", how_to_reach={"email": email_of("Ana Guest"), "phone": "555-0100"})
    mail(store, f"Ana Guest <{email_of('Ana Guest')}>", received=at(days=-1))
    found = people_memory.memory(store, cfg, ana, NOW)
    assert (
        found.reach.kept == {"email": email_of("Ana Guest"), "phone": "555-0100"} and found.reach.replies_on == "email"
    )
    assert found.reach.replies_record == found.last_in_touch.record and found.last_in_touch.kind == "from"
    unknown = person(store, "Ben Guest", how_to_reach={"phone": "555-0101"})
    assert people_memory.memory(store, cfg, unknown, NOW).reach == people_memory.Reach(
        {"phone": "555-0101"}, None, None
    )
    assert people_memory.memory(store, cfg, "PER-9999", NOW) is None


def fact(store, text: str, **more) -> str:
    data = {"text": text, "trust": "trusted", "basis": "person", "evidence": {"source": "note", "quote": text}, **more}
    with store.transaction() as tx:
        return tx.create("fact", data, _TEST).id


def test_their_dates_are_facts_with_a_date_word_and_the_next_day_it_falls_on_and_one_off_dates_still_ahead(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    ben = person(store, "Ben Guest")
    birthday = fact(store, "Ana Guest's birthday is March 3")
    thanks = fact(store, "Ana Guest's anniversary at the firm is 2026-10-25")
    review = fact(store, "Ana Guest's contract ends on 2027-01-15")
    past = fact(store, "Ana Guest started on 2020-05-04")
    fact(store, "Ben Guest's birthday is 1 November")
    found = people_memory.memory(store, cfg, ana, NOW)
    assert [(d.fact, d.on, d.yearly) for d in found.dates] == [
        (thanks, date(2026, 10, 25), True),
        (review, date(2027, 1, 15), False),
        (birthday, date(2027, 3, 3), True),
    ]
    assert found.dates[2].quote == "Ana Guest's birthday is March 3" and found.dates[2].source == "note"
    assert [k.fact for k in found.matters] == [past] and [
        d.fact for d in people_memory.memory(store, cfg, ben, NOW).dates
    ]


def test_what_matters_is_the_facts_the_person_kept_newest_first_and_never_what_was_only_inferred_or_replaced(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    old = fact(store, "Ana Guest prefers short notes", as_of="2026-09-01")
    new = fact(store, "Ana Guest prefers the phone for urgent things", as_of="2026-10-01")
    replaced = fact(store, "Ana Guest likes long meetings", as_of="2026-08-01")
    fact(store, "Ana Guest dislikes long meetings", as_of="2026-09-15", supersedes=replaced)
    fact(store, "Ana Guest seems to be on leave", basis="inferred")
    fact(store, "Ana Guest wants a raise", trust="untrusted")
    fact(store, "Ben says Ana Guest is difficult", basis="said")
    fact(store, "The printer is broken")
    texts = [k.text for k in people_memory.memory(store, cfg, ana, NOW).matters]
    assert texts == [
        "Ana Guest prefers the phone for urgent things",
        "Ana Guest dislikes long meetings",
        "Ana Guest prefers short notes",
    ]
    assert new and old
    cfg.steward.people.max_facts = 1
    assert len(people_memory.memory(store, cfg, ana, NOW).matters) == 1


def test_asked_of_and_by_them_and_promises_both_ways_are_on_the_persons_page_with_their_evidence(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    mine = promise(store, cfg, me(cfg), ana, "Send Ana the cover", "I'll send the cover")
    theirs = promise(store, cfg, ana, me(cfg), "Return the contract", "I will return the contract")
    owed = promise(store, cfg, me(cfg), None, "Reply to Ana", "any news?", reply_owed=True, asker=ana)
    asked = question(store, ana)
    found = people_memory.memory(store, cfg, ana, NOW)
    assert [(i.id, i.quote) for i in found.promised_to] == [(mine, "I'll send the cover")]
    assert [(i.id, i.quote) for i in found.promised_by] == [(theirs, "I will return the contract")]
    assert [i.id for i in found.asked_by] == [owed] and [i.id for i in found.asked_of] == [asked]


# ---- a promise that has gone quiet ----------------------------------------


def aged(store, days: int):
    """Make records dated `days` before the test's today."""
    store.clock = lambda: f"{TODAY - timedelta(days=days)}T09:00:00+00:00"


def quiet(env, **kw):
    _, cfg, store = env
    return people_memory.quiet_promises(store, cfg, TODAY, **kw)


def test_a_promise_to_someone_with_no_news_for_the_configured_days_is_a_line_to_follow_up_with_them(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    aged(store, 9)
    mine = promise(store, cfg, me(cfg), ana, "Send Ana the cover", "I'll send the cover")
    (found,) = quiet(env)
    assert (found.action, found.person, found.direction, found.quiet) == (mine, ana, "to", 9)
    assert found.quote == "I'll send the cover" and found.since == TODAY - timedelta(days=9)
    cfg.steward.people.quiet_promise_days = 10
    assert quiet(env) == []
    cfg.steward.people.quiet_promise_days = 0
    assert quiet(env) == []


def test_a_promise_from_someone_with_no_news_is_a_line_and_news_since_restarts_the_count(env):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    aged(store, 12)
    theirs = promise(store, cfg, ana, me(cfg), "Return the contract")
    (found,) = quiet(env)
    assert (found.person, found.direction, found.quiet) == (ana, "from", 12)
    update(store, "action", theirs, {"news": [{"on": (TODAY - timedelta(days=2)).isoformat(), "text": "Said soon"}]})
    assert quiet(env) == []
    update(store, "action", theirs, {"news": [{"on": (TODAY - timedelta(days=8)).isoformat(), "text": "Said soon"}]})
    (again,) = quiet(env)
    assert again.quiet == 8 and again.since == TODAY - timedelta(days=8)


def test_a_quiet_promise_that_has_a_line_already_is_on_hold_or_isnt_chased_is_left_out(env):
    _, cfg, store = env
    ana, boss = person(store, "Ana Guest"), person(store, "Lena Boss", stance="report_to")
    aged(store, 20)
    on_a_line = promise(store, cfg, ana, me(cfg), "Already on a line")
    held = promise(store, cfg, ana, me(cfg), "On hold", on_hold={"waiting_for": "the keys", "since": "2026-10-01"})
    promise(store, cfg, boss, me(cfg), "From the boss")
    promise(store, cfg, ana, boss, "Promised to someone else")
    promise(store, cfg, me(cfg), ana, "Past its day", due="2026-10-10")
    promise(store, cfg, me(cfg), None, "Replied", reply_owed=True, asker=ana)
    plain = {"text": "A plain to-do", "owners": [{"person": ana}]}
    with store.transaction() as tx:
        tx.create("action", plain, _TEST)
    assert held and {q.action for q in quiet(env)} == {on_a_line}
    assert quiet(env, skip={on_a_line}) == []


def test_today_has_a_line_for_a_quiet_promise_that_names_who_to_follow_up_with(env):
    ws, cfg, store = env
    ana = person(store, "Ana Guest")
    aged(store, 9)
    mine = promise(store, cfg, me(cfg), ana, "Send Ana the cover")
    (line,) = [x for x in queue(ws, store, cfg, NOW) if x.kind == "quiet_promise"]
    assert (line.key, line.group, line.person, line.actions, line.state) == (
        f"quiet_promise:{mine}",
        "send",
        ana,
        [mine],
        "to",
    )
    assert (line.text, line.waiting_days) == ("Send Ana the cover", 9)


# ---- the prep note ----------------------------------------


def test_the_prep_note_is_a_draft_on_the_entrys_prep_text_started_by_the_person(env):
    kind = task_kind(meeting_prep.TASK)
    assert (kind.output, kind.on, kind.field, kind.ops) == ("draft", "event", "prep", ("text.draft",))


def noted(env, text="Ana: send the contract.\n"):
    _, cfg, store = env
    ana = person(store, "Ana Guest")
    promise(store, cfg, ana, me(cfg), "Return the contract", "I will return the contract")
    found = entry(store, "Design review", guests=[(ana, "accepted")], trust="untrusted")
    asked: list = []
    set_responder(lambda task: asked.append(task) or text)
    return found, meeting_prep.ask_for_note(store, found, "  Keep it short.  "), asked


def test_the_prep_note_packet_has_the_facts_marked_as_data_after_the_stable_parts_and_a_knowledge_log(env):
    ws, cfg, store = env
    found, request, _ = noted(env)
    queued = store.read().get("request", request).data
    assert queued["about"] == {"kind": "event", "id": found} and queued["note"] == "Keep it short."
    built = packets.build(ws, store, cfg, request, TODAY)
    text = built.task.request
    assert built.task.kind == meeting_prep.TASK and built.about == ("event", found) and built.untrusted_material
    assert "Return the contract" in text and "Ana Guest" in text and "Keep it short." in text
    assert text.count("<untrusted") >= 1 and "<untrusted" not in built.task.stable
    assert built.task.instructions.startswith("You are") and built.knowledge is not None


def test_a_run_files_a_pending_draft_asks_once_and_the_state_says_a_draft_waits(env):
    ws, cfg, store = env
    found, request, asked = noted(env)
    assert meeting_prep.note_state(store.read(), found).state == "working"
    process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    (draft,) = versions(store.read(), "event", found, "prep")
    assert (draft.data["status"], draft.data["source"]) == ("pending", "draft")
    assert store.read().get("event", found).data.get("prep") is None
    assert meeting_prep.note_state(store.read(), found).state == "draft" and asked[0].kind == meeting_prep.TASK
    assert store.read().list("run")[-1].data["knowledge"]
    with pytest.raises(StoreError, match="already"):
        meeting_prep.ask_for_note(store, found)
    version = store.read().get("text_version", draft.id)
    apply_as_person(
        store, cfg, [{"op": "text.discard", "version": draft.id, "read_version": version.version}], "Set aside"
    )
    (signal,) = store.read().list("signal")
    assert signal.data["kind"] == "dropped" and signal.data["refs"] == [found]
    assert meeting_prep.note_state(store.read(), found).state == "none"
    meeting_prep.ask_for_note(store, found)


def test_the_prep_note_is_estimated_and_waits_for_the_go_above_the_amount_to_confirm(env):
    ws, cfg, store = env
    use = cfg.ai.tiers["routine"].use
    cfg.ai.prices[use] = Price(input_per_million=500_000.0, output_per_million=500_000.0)
    cfg.ai.budgets.per_run_usd = 1000.0
    cfg.ai.budgets.confirm_above_usd = 0.0
    found, request, asked = noted(env)
    process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    held = store.read().get("request", request).data
    assert (held["state"], held["approval"]) == ("needs_you", "required") and held["estimate_usd"] > 0 and asked == []
    state = meeting_prep.note_state(store.read(), found)
    assert (state.state, state.estimate_usd) == ("needs_go", held["estimate_usd"])


def test_asking_for_a_prep_note_on_an_entry_that_isnt_there_is_refused(env):
    _, _, store = env
    with pytest.raises(StoreError, match="no calendar entry"):
        meeting_prep.ask_for_note(store, "EVT-9999")


# ---- the routes ----------------------------------------


@pytest.fixture
def client(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"}, flags={"server.base_path": "/"})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as http:
        yield http, app.state.store, cfg
    set_responder(None)


def test_the_prep_route_says_who_is_coming_what_is_open_and_where_the_note_stands(client):
    http, store, cfg = client
    ana = person(store, "Ana Guest")
    mine = promise(store, cfg, me(cfg), ana, "Send Ana the cover", "I'll send the cover")
    found = entry(
        store, "Design review", start=(datetime.now(UTC) + timedelta(hours=3)).isoformat(), guests=[(ana, "accepted")]
    )
    body = http.get(f"/api/meetings/{found}/prep").json()
    assert body["title"] == "Design review" and body["note"] == {"state": "none", "request": None, "estimate_usd": None}
    assert [(g["person"], g["name"]) for g in body["coming"]] == [(ana, "Ana Guest")]
    (one,) = body["people"]
    assert one["name"] == "Ana Guest" and [i["id"] for i in one["promised_to"]] == [mine]
    assert one["promised_to"][0]["quote"] == "I'll send the cover" and one["last_in_touch"] is None
    assert http.get("/api/meetings/EVT-9999/prep").status_code == 404
    asked = http.post(f"/api/meetings/{found}/prep-note", json={"note": "Short."})
    assert asked.status_code == 200 and http.get(f"/api/meetings/{found}/prep").json()["note"]["state"] == "working"
    assert http.post(f"/api/meetings/{found}/prep-note", json={}).status_code == 409
    assert http.post("/api/meetings/EVT-9999/prep-note", json={}).status_code == 404


def test_the_capture_route_files_the_note_marks_the_entry_and_refuses_one_that_isnt_there(client):
    http, store, _ = client
    ana = person(store, "Ana Guest")
    ended = entry(
        store,
        "Kickoff",
        start=(datetime.now(UTC) - timedelta(hours=3)).isoformat(),
        end=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        guests=[(ana, "accepted")],
    )
    lines = [x for x in http.get("/api/today/queue").json() if x["kind"] == "meeting_capture"]
    assert [(x["event"], x["text"], x["names"]) for x in lines] == [(ended, "Kickoff", ["Ana Guest"])]
    done = http.post(f"/api/meetings/{ended}/capture", json={"text": "Ana will send the contract by Friday."})
    assert done.status_code == 200 and done.json()["request"] and done.json()["captured_at"]
    assert http.get(f"/api/meetings/{ended}/prep").json()["captured_at"]
    assert [x for x in http.get("/api/today/queue").json() if x["kind"] == "meeting_capture"] == []
    assert http.post("/api/meetings/EVT-9999/capture", json={"text": "x"}).status_code == 404
    assert http.post(f"/api/meetings/{ended}/capture", json={}).json()["request"] is None


def test_the_memory_route_gives_each_part_of_a_persons_page(client):
    http, store, cfg = client
    ana = person(store, "Ana Guest", how_to_reach={"email": email_of("Ana Guest")})
    promise(store, cfg, ana, me(cfg), "Return the contract", "I will return the contract")
    fact(store, "Ana Guest's birthday is March 3")
    fact(store, "Ana Guest prefers short notes")
    body = http.get(f"/api/people/{ana}/memory").json()
    assert body["name"] == "Ana Guest" and body["reach"]["kept"] == {"email": email_of("Ana Guest")}
    assert [i["quote"] for i in body["promised_by"]] == ["I will return the contract"]
    assert [d["yearly"] for d in body["dates"]] == [True] and [k["text"] for k in body["matters"]] == [
        "Ana Guest prefers short notes"
    ]
    assert body["last_in_touch"] is None and http.get("/api/people/PER-9999/memory").status_code == 404
