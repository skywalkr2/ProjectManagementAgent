"""Gentle suggestions with choices (design 6.32, "Manner"): a to-do moved again and again, a promise re-dated again and
again, a person owed several replies, and a to-do nobody has touched each become one suggestion line with choices; each
choice acts at once, records a signal and can be taken back. Names, ids and counts come from the fixtures and the
settings; the AI is not involved at all."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import patterns, suggestions
from engine.open_items import open_actions, stale_actions
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "patterns-token"
_PM = WriteContext(actor="pm", trust="trusted", op="test")
PEOPLE = fixture_records(DEMO_B, "person")
ME = PEOPLE[0]["id"]
OTHER = PEOPLE[1]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]
WORDS = {"reason": "Not doing this", "waiting": "A better time", "weekly": "every week"}


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def add(store, text, *, owners=(ME,), **more) -> str:
    data = {"text": text, "owners": [{"person": p} for p in owners], "project": PROJECT["id"], **more}
    with store.transaction() as tx:
        return tx.create("action", data, _PM).id


def update(store, record_id, changes) -> None:
    with store.transaction() as tx:
        tx.update("action", record_id, changes, _PM, read_version=tx.get("action", record_id).version)


def move_day(store, record_id, times, start=date(2026, 11, 2)) -> None:
    """Move a to-do's day `times` times, each a day later than the one before."""
    for n in range(times):
        update(store, record_id, {"due": (start + timedelta(days=n + 1)).isoformat()})


def moved_todo(store, times, text="Book the studio") -> str:
    made = add(store, text, due="2026-11-02")
    move_day(store, made, times)
    return made


def promise(store, times, text="Send the cover") -> str:
    made = add(store, text, due="2026-11-02", promised_to=[OTHER], basis="said")
    move_day(store, made, times)
    return made


def owed(store, n, asker=OTHER) -> list[str]:
    return [add(store, f"Reply about item {i}", reply_owed=True, asker=asker) for i in range(n)]


def lines(client, kind="pattern"):
    return [x for x in client.get("/api/today/queue").json() if x["kind"] == kind]


def status_of(store, record_id) -> str:
    return store.read().get("action", record_id).data["status"]


def signals(store, kind):
    return [s for s in store.read().list("signal") if s.data["kind"] == kind]


# ---- the patterns ----


def test_a_to_do_whose_day_moved_enough_times_is_a_moved_pattern_and_fewer_is_not(env):
    _, cfg, store = env
    needed = cfg.steward.patterns.moved_times
    short = moved_todo(store, needed - 1, "Tidy the shelf")
    enough = moved_todo(store, needed)
    found = patterns.moved_todos(store, cfg)
    assert [(f.subject, f.count) for f in found] == [(enough, needed)]
    assert short not in [f.subject for f in found]


def test_setting_a_first_day_or_taking_one_off_is_not_a_move(env):
    _, cfg, store = env
    needed = cfg.steward.patterns.moved_times
    made = add(store, "Plan the trip")
    for _ in range(needed):
        update(store, made, {"due": "2026-11-05"})
        update(store, made, {"due": None})
    assert patterns.date_moves(store.read()) == {}
    assert patterns.moved_todos(store, cfg) == []


def test_a_promise_moved_enough_times_is_a_redated_pattern_not_a_moved_one(env):
    _, cfg, store = env
    made = promise(store, cfg.steward.patterns.redated_times)
    assert patterns.moved_todos(store, cfg) == []
    assert [f.subject for f in patterns.redated_promises(store, cfg)] == [made]


def test_only_the_persons_own_open_to_dos_count_and_a_repeating_or_held_one_does_not(env):
    _, cfg, store = env
    needed = cfg.steward.patterns.moved_times
    theirs = add(store, "Fix the cover file", owners=(OTHER,), due="2026-11-02")
    move_day(store, theirs, needed)
    repeating = moved_todo(store, needed, "Water the plants")
    update(
        store, repeating, {"repeat": {"rule": "FREQ=WEEKLY;BYDAY=TH", "phrase": "every week", "start": "2026-11-05"}}
    )
    held = moved_todo(store, needed, "Wait for the printer")
    update(store, held, {"on_hold": {"waiting_for": "the printer", "since": "2026-11-01"}})
    done = moved_todo(store, needed, "Old thing")
    update(store, done, {"status": "done"})
    assert patterns.moved_todos(store, cfg) == []


def test_a_setting_of_zero_turns_each_pattern_off(env):
    ws, cfg, store = env
    moved_todo(store, cfg.steward.patterns.moved_times)
    promise(store, cfg.steward.patterns.redated_times)
    owed(store, cfg.steward.patterns.owed_replies)
    off = ws.config(
        env={},
        flags={
            "steward.patterns.moved_times": 0,
            "steward.patterns.redated_times": 0,
            "steward.patterns.owed_replies": 0,
        },
    )
    assert patterns.all_found(store, off) == []
    assert len(patterns.all_found(store, cfg)) == 3


def test_a_person_owed_enough_replies_is_one_pattern_for_them(env):
    _, cfg, store = env
    needed = cfg.steward.patterns.owed_replies
    few = owed(store, needed - 1, asker=ME)
    many = owed(store, needed)
    (found,) = patterns.owed_replies(store, cfg)
    assert (found.state, found.person, found.count, sorted(found.actions)) == ("replies", OTHER, needed, sorted(many))
    assert not set(few) & set(found.actions)


def test_todays_queue_has_one_pattern_line_each_with_its_choices_in_review(env):
    ws, cfg, store = env
    a = moved_todo(store, cfg.steward.patterns.moved_times)
    b = promise(store, cfg.steward.patterns.redated_times)
    c = owed(store, cfg.steward.patterns.owed_replies)
    found = {x.state: x for x in queue(ws, store, cfg, datetime.now(UTC)) if x.kind == "pattern"}
    assert set(found) == {"moved", "redated", "replies"}
    assert all(x.group == "review" for x in found.values())
    assert found["moved"].actions == [a] and found["moved"].choices == ["drop", "weekly", "leave"]
    assert found["redated"].actions == [b] and found["redated"].choices == ["drop", "hold", "leave"]
    assert sorted(found["replies"].actions) == sorted(c) and found["replies"].choices == ["no_reply", "leave"]
    assert found["replies"].person == OTHER and found["moved"].key == f"pattern:moved:{a}"


# ---- the choices ----


def test_drop_closes_the_to_do_with_the_persons_reason_with_undo_and_one_signal_that_teaches_nothing(api):
    client, store, cfg = api
    made = moved_todo(store, cfg.steward.patterns.moved_times)
    (line,) = lines(client)
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "drop", **WORDS}).json()
    record = store.read().get("action", made).data
    assert record["status"] == "dropped" and record["dropped_reason"] == WORDS["reason"]
    assert lines(client) == []
    (signal,) = signals(store, "suggestion_chosen")
    assert (
        signal.id == done["signal"] and signal.data["refs"] == [made] and signal.data["changeset"] == done["changeset"]
    )
    assert '"choice": "drop"' in signal.data["note"]
    assert signals(store, "dropped") == [], "a choice on a suggestion is not a correction of the assistant"
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert status_of(store, made) == "open" and len(lines(client)) == 1
    assert signals(store, "suggestion_chosen")[0].data["note"] == suggestions.TAKEN_BACK
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 404


def test_make_it_weekly_sets_the_repeat_with_undo(api):
    client, store, cfg = api
    made = moved_todo(store, cfg.steward.patterns.moved_times)
    (line,) = lines(client)
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "weekly", **WORDS}).json()
    repeat = store.read().get("action", made).data["repeat"]
    assert repeat["rule"].startswith("FREQ=WEEKLY") and repeat["phrase"] == WORDS["weekly"]
    assert lines(client) == [], "a repeating to-do is left alone"
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert store.read().get("action", made).data["repeat"] is None


def test_a_repeat_that_cannot_be_read_is_refused_and_records_nothing(api):
    client, store, cfg = api
    moved_todo(store, cfg.steward.patterns.moved_times)
    (line,) = lines(client)
    refused = client.post(
        "/api/suggestions/choose", json={"key": line["key"], "choice": "weekly", "weekly": "when I feel like it"}
    )
    assert refused.status_code == 409
    assert signals(store, "suggestion_chosen") == []


def test_put_it_on_hold_holds_a_redated_promise_with_undo(api):
    client, store, cfg = api
    made = promise(store, cfg.steward.patterns.redated_times)
    (line,) = lines(client)
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "hold", **WORDS}).json()
    assert store.read().get("action", made).data["on_hold"]["waiting_for"] == WORDS["waiting"]
    assert lines(client) == []
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert not store.read().get("action", made).data.get("on_hold")


def test_no_reply_needed_drops_every_owed_reply_and_is_the_correction_it_is(api):
    client, store, cfg = api
    owed_ids = owed(store, cfg.steward.patterns.owed_replies)
    (line,) = lines(client)
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "no_reply", **WORDS}).json()
    assert {status_of(store, i) for i in owed_ids} == {"dropped"}
    assert len(signals(store, "no_reply_needed")) == len(owed_ids), "the assistant thought a reply was owed"
    assert lines(client) == []
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert {status_of(store, i) for i in owed_ids} == {"open"}


def test_leave_it_keeps_a_line_away_until_it_changes_and_undo_brings_it_back(api):
    client, store, cfg = api
    needed = cfg.steward.patterns.moved_times
    made = moved_todo(store, needed)
    (line,) = lines(client)
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "leave"}).json()
    assert done["changeset"] is None and status_of(store, made) == "open"
    assert lines(client) == []
    move_day(store, made, 1, start=date(2026, 11, 20))
    (again,) = lines(client)
    assert again["count"] == needed + 1, "it moved once more, so the suggestion is new"
    client.post(f"/api/suggestions/choose/{done['signal']}/undo")
    assert len(lines(client)) == 1


def test_a_choice_the_line_doesnt_offer_or_a_line_that_isnt_there_is_refused(api):
    client, store, cfg = api
    owed(store, cfg.steward.patterns.owed_replies)
    (line,) = lines(client)
    assert (
        client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "weekly", **WORDS}).status_code
        == 409
    )
    assert (
        client.post("/api/suggestions/choose", json={"key": "pattern:moved:ACT-0", "choice": "leave"}).status_code
        == 404
    )
    assert client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "no_reply"}).status_code == 409
    assert signals(store, "suggestion_chosen") == []


def test_a_choice_counts_toward_the_days_cap_like_a_put_off(env):
    ws, cfg, store = env
    made = moved_todo(store, cfg.steward.patterns.moved_times)
    now = datetime.now(UTC)
    (line,) = [x for x in queue(ws, store, cfg, now) if x.kind == "pattern"]
    patterns.choose(store, cfg, line, "leave", patterns.Words(), now, suggestions.change_key(line))
    assert len(suggestions._put_off_today(store.read(), cfg, now + timedelta(seconds=1))) == 1
    assert status_of(store, made) == "open"


# ---- the stale sweep ----


def stamp(store, record_id, when) -> None:
    with store.transaction() as tx:
        tx.sql(
            "UPDATE ledger SET at=? WHERE kind=? AND record_id=?",
            (when.isoformat(timespec="seconds"), "action", record_id),
        )


def stale_one(store, cfg, text="Tidy the style sheet") -> str:
    made = add(store, text)
    stamp(store, made, datetime.now(UTC) - timedelta(days=cfg.ui.today.stale_after_days + 5))
    return made


def test_one_stale_to_do_has_a_still_doing_this_line_with_keep_drop_and_snooze_and_several_have_keep_and_snooze(env):
    ws, cfg, store = env
    now = datetime.now(UTC)
    first = stale_one(store, cfg)
    (line,) = [x for x in queue(ws, store, cfg, now) if x.kind == "stale"]
    assert line.actions == [first] and line.choices == ["keep", "drop", "snooze"]
    stale_one(store, cfg, "Sort the old proofs")
    (line,) = [x for x in queue(ws, store, cfg, now) if x.kind == "stale"]
    assert line.count == 2 and line.choices == ["keep", "snooze"]


def test_keep_starts_the_quiet_clock_again_and_undo_makes_it_stale_again(api):
    client, store, cfg = api
    made = stale_one(store, cfg)
    (line,) = lines(client, "stale")
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "keep"}).json()
    assert done["changeset"] is None and status_of(store, made) == "open"
    assert lines(client, "stale") == []
    assert stale_actions(store, cfg, datetime.now(UTC)) == []
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert [x["actions"] for x in lines(client, "stale")] == [[made]]


def test_a_kept_to_do_is_stale_again_after_the_same_number_of_days(env):
    _, cfg, store = env
    made = stale_one(store, cfg)
    now = datetime.now(UTC)
    from engine.learn import record

    with store.transaction() as tx:
        record(
            tx,
            cfg,
            {
                "kind": "suggestion_chosen",
                "refs": [made],
                "note": '{"kind": "stale", "subject": "stale", "change": "x", "choice": "keep"}',
                "at": now.isoformat(),
            },
            _PM,
            now,
        )
    assert stale_actions(store, cfg, now) == []
    later = now + timedelta(days=cfg.ui.today.stale_after_days + 1)
    assert made in [r.id for r in stale_actions(store, cfg, later)]


def test_snooze_keeps_a_to_do_away_for_the_configured_days_and_it_changes_nothing_else(api):
    client, store, cfg = api
    made = stale_one(store, cfg)
    (line,) = lines(client, "stale")
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "snooze"}).json()
    assert lines(client, "stale") == []
    rows = {r.id: r for r in open_actions(store, cfg, date.today(), now=datetime.now(UTC) + timedelta(days=1))}
    assert rows[made].state == "open", "snoozed, so not stale tomorrow"
    after = datetime.now(UTC) + timedelta(days=cfg.steward.patterns.snooze_days + cfg.ui.today.stale_after_days + 1)
    assert made in [r.id for r in stale_actions(store, cfg, after)], "it comes back once the snooze and the wait pass"
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert len(lines(client, "stale")) == 1


def test_drop_on_a_stale_line_drops_the_one_to_do_with_undo(api):
    client, store, cfg = api
    made = stale_one(store, cfg)
    (line,) = lines(client, "stale")
    done = client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "drop", **WORDS}).json()
    assert status_of(store, made) == "dropped" and lines(client, "stale") == []
    assert client.post(f"/api/suggestions/choose/{done['signal']}/undo").status_code == 200
    assert status_of(store, made) == "open"


def test_nothing_is_closed_on_its_own_a_suggestion_only_offers(env):
    ws, cfg, store = env
    a = moved_todo(store, cfg.steward.patterns.moved_times)
    b = stale_one(store, cfg)
    queue(ws, store, cfg, datetime.now(UTC))
    assert (status_of(store, a), status_of(store, b)) == ("open", "open")
    assert signals(store, "suggestion_chosen") == []


def test_a_pattern_the_days_cap_holds_back_waits_in_the_morning_brief_with_its_state(env):
    from engine import brief

    ws, cfg, store = env
    held_back = ws.config(env={}, flags={"steward.attention.daily_cap": 0, "steward.brief.max_lines": 20})
    moved_todo(store, cfg.steward.patterns.moved_times)
    now = datetime.now(UTC)
    assert [x for x in queue(ws, store, held_back, now) if x.kind == "pattern"] == []
    found = brief.build(ws, store, held_back, now, "morning")
    yes = next(s for s in found.sections if s.key == "yes")
    (digest,) = [x for x in yes.lines if x.kind == "digest"]
    assert (digest.change, digest.count) == ("pattern_moved", cfg.steward.patterns.moved_times)


def test_make_it_weekly_on_a_to_do_whose_day_has_passed_repeats_from_that_day(api):
    client, store, cfg = api
    made = add(store, "Book the studio", due="2026-01-01")
    move_day(store, made, cfg.steward.patterns.moved_times, start=date(2026, 1, 1))
    due = store.read().get("action", made).data["due"]
    (line,) = lines(client)
    client.post("/api/suggestions/choose", json={"key": line["key"], "choice": "weekly", **WORDS}).raise_for_status()
    assert store.read().get("action", made).data["repeat"]["start"] == str(due)
