"""Repeating to-dos (design 6.32): a repeat is set from the person's words and read back as data; each occurrence is its
own to-do and the next is made, in the same change, when one ends (done, dropped, or done by someone else); a missed one
stays open and the next waits for it; Undo of the ending takes the next back; stopping leaves the open one as it is.
Names and ids come from the fixtures; the date is moved by the store's own clock."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import repeats
from engine.applier import Context, Inputs, apply_as_person, apply_changeset, check, release
from engine.dispatcher import undo_changeset
from engine.followups import they_finished
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, StoreError, WriteContext
from engine.today import zone
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_corrections import other_of, pm_of
from tests.test_knowledge_records import NOW, apply, source

TOKEN = "repeating-todos-token"
_TEST = WriteContext(actor="pm", trust="trusted", op="test.repeat")
FRIDAY = date(2026, 11, 6)
WEEKLY = "every Friday"
TEXT = "Send the weekly update"


class Clock:
    """The store's clock, set to noon on a day of the person's own calendar."""

    def __init__(self, cfg, day: date):
        self.cfg = cfg
        self.on(day)

    def on(self, day: date) -> None:
        self.stamp = datetime(day.year, day.month, day.day, 12, tzinfo=zone(self.cfg)).astimezone(UTC).isoformat()

    def __call__(self) -> str:
        return self.stamp


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    clock = Clock(cfg, FRIDAY)
    store = Store(ws.db_path, cfg=cfg, clock=clock)
    yield cfg, store, clock
    store.close()


def data(store, action_id) -> dict:
    return store.read().get("action", action_id).data


def todo(store, cfg, *, due: date | None = FRIDAY, owner: str | None = None, **more) -> str:
    fields = {
        "text": TEXT,
        "owners": [{"person": owner or pm_of(cfg)}],
        "due": due.isoformat() if due else None,
        "notes": "Use last week's list.",
        **more,
    }
    with store.transaction() as tx:
        return tx.create("action", fields, _TEST).id


def make_repeat(store, cfg, action_id, phrase=WEEKLY, start: date | None = FRIDAY) -> str:
    found = repeats.read_phrase(phrase, start, date(2026, 11, 2))
    assert found.status == "ok", found
    op = {
        "op": "action.repeat",
        "id": action_id,
        "rule": found.rule,
        "phrase": phrase,
        "start": found.start.isoformat(),
    }
    return apply_as_person(store, cfg, [op], "Set a repeat")


def repeating(store, cfg, phrase=WEEKLY, start: date | None = FRIDAY, **more) -> str:
    action_id = todo(store, cfg, due=start, **more)
    make_repeat(store, cfg, action_id, phrase, start)
    return action_id


def chain(store, first_id) -> list[dict]:
    """Every occurrence of the repeat, oldest first, with its id."""
    found = [store.read().get("action", first_id)] + store.read().find("action", {"occurrence_of": first_id})
    return [{"id": a.id, **a.data} for a in sorted(found, key=lambda a: a.id)]


def open_ones(store, first_id) -> list[dict]:
    return [a for a in chain(store, first_id) if a["status"] == "open"]


def finish(store, cfg, action_id) -> str:
    return apply_as_person(store, cfg, [{"op": "action.close", "id": action_id}], "Marked done")


# ---- setting a repeat ----------------------------


def test_a_repeat_set_by_the_person_applies_at_once_with_its_words_its_rule_and_its_start_and_undo_takes_it_off(env):
    cfg, store, _ = env
    action_id = todo(store, cfg)
    done = make_repeat(store, cfg, action_id, "  Every   FRIDAY ")
    kept = data(store, action_id)["repeat"]
    assert kept == {"rule": "FREQ=WEEKLY;BYDAY=FR", "phrase": "Every FRIDAY", "start": FRIDAY.isoformat()}
    assert data(store, action_id).get("occurrence_of") is None
    undo_changeset(store, done)
    assert data(store, action_id)["repeat"] is None


def test_a_to_do_with_no_day_is_due_on_the_first_day_of_its_repeat(env):
    cfg, store, _ = env
    action_id = todo(store, cfg, due=None)
    make_repeat(store, cfg, action_id, "the 1st and 15th", date(2026, 11, 15))
    assert data(store, action_id)["due"] == "2026-11-15"


def test_a_repeat_the_grammar_cannot_say_back_is_refused_and_nothing_is_kept(env):
    cfg, store, _ = env
    action_id = todo(store, cfg)
    for rule in ("FREQ=HOURLY", "FREQ=DAILY;COUNT=5", "FREQ=WEEKLY;BYDAY=FR;BYHOUR=9", "FREQ=WEEKLY;BYDAY=TU"):
        op = {"op": "action.repeat", "id": action_id, "rule": rule, "phrase": "often", "start": FRIDAY.isoformat()}
        with pytest.raises(StoreError, match="can't be read"):
            apply_as_person(store, cfg, [op], "Set a repeat")
    assert data(store, action_id)["repeat"] is None


def test_the_repeat_starts_on_the_to_dos_own_day_and_needs_all_of_its_parts(env):
    cfg, store, _ = env
    action_id = todo(store, cfg)
    op = {"op": "action.repeat", "id": action_id, "rule": "FREQ=WEEKLY;BYDAY=MO", "phrase": "Mondays"}
    with pytest.raises(ValueError, match="rule, its words and its first day"):
        apply_as_person(store, cfg, [op], "Set a repeat")
    off = {**op, "start": "2026-11-09"}
    with pytest.raises(StoreError, match="is due 2026-11-06"):
        apply_as_person(store, cfg, [off], "Set a repeat")


def test_stopping_needs_a_repeat_and_an_open_to_do(env):
    cfg, store, _ = env
    plain = todo(store, cfg)
    with pytest.raises(StoreError, match="doesn't repeat"):
        apply_as_person(store, cfg, [{"op": "action.repeat", "id": plain}], "Stopped")
    ended = repeating(store, cfg)
    finish(store, cfg, ended)
    with pytest.raises(StoreError, match="can't be made to repeat"):
        make_repeat(store, cfg, ended)


def test_a_repeat_the_assistant_reads_from_an_input_waits_for_the_persons_yes(env):
    cfg, store, _ = env
    action_id = todo(store, cfg)
    raw = f"I {TEXT.lower()} {WEEKLY}."
    op = {
        "op": "action.repeat",
        "id": action_id,
        "rule": "FREQ=WEEKLY;BYDAY=FR",
        "phrase": WEEKLY,
        "start": FRIDAY.isoformat(),
        "evidence": {"quote": WEEKLY},
    }
    cs_id, statuses = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=source(store), raw=raw)
    assert statuses == ["held"]
    assert data(store, action_id)["repeat"] is None
    release(store, cfg, cs_id, 0)
    assert data(store, action_id)["repeat"]["phrase"] == WEEKLY
    # An unreadable rule from the assistant is refused outright, not held.
    other = todo(store, cfg)
    bad = {**op, "id": other, "rule": "FREQ=HOURLY"}
    _, statuses = apply(store, cfg, [bad], origin="input", trust="untrusted", source_id=source(store), raw=raw)
    assert statuses == ["refused"]


# ---- a repeat the assistant names in the input's own words ----------------------------

SAID = f"I will {TEXT.lower()} {WEEKLY}."
MONDAY = date(2026, 11, 9)


def added(due: date | None = None, **more) -> dict:
    """An `action.add` for the person with the quote from `SAID`, optionally with a day."""
    op = {"op": "action.add", "text": TEXT, "owners": ["PERSON"], "evidence": {"quote": f"{TEXT.lower()} {WEEKLY}"}}
    return {**op, **({"due": due.isoformat()} if due else {}), **more}


def repeat_of(words: str = WEEKLY, to: str = "@0", **more) -> dict:
    """An `action.repeat` naming a to-do by `@`, with its words quoted as its evidence."""
    quote = words if len(words.strip()) >= 3 else WEEKLY
    return {"op": "action.repeat", "id": to, "words": words, "evidence": {"quote": quote}, **more}


def run(store, cfg, ops, *, mine: bool, raw: str = SAID):
    """The ops as the answer to one input: the person's own note, or an input from outside."""
    ops = [{**op, "owners": [pm_of(cfg)]} if op.get("owners") == ["PERSON"] else op for op in ops]
    if not mine:
        return apply(store, cfg, ops, origin="input", trust="untrusted", source_id=source(store), raw=raw)
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create("request", {"task": "notes", "origin": "pm", "state": "done", "created_at": NOW}, _TEST).id
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs(request, None, "", raw, "trusted"))
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def made_action(store, cs_id, index: int = 0) -> str:
    records = store.read().get("changeset", cs_id).data["ops"][index]["records"]
    return next(r["id"] for r in records if r["kind"] == "action")


def test_the_persons_own_words_make_the_to_do_and_its_repeat_at_once_read_from_the_to_dos_day(env):
    cfg, store, _ = env
    cs_id, statuses = run(
        store, cfg, [added(due=MONDAY), repeat_of("every Monday")], mine=True, raw=f"{SAID} Every Monday."
    )
    assert statuses == ["applied", "applied"]
    # Read from the to-do's own day (a Monday), not from the day the input arrived.
    assert data(store, made_action(store, cs_id))["repeat"] == {
        "rule": "FREQ=WEEKLY;BYDAY=MO",
        "phrase": "every Monday",
        "start": MONDAY.isoformat(),
    }
    assert store.read().get("changeset", cs_id).data["ops"][1]["op"]["id"] == "@0"


def test_a_to_do_with_no_day_reads_the_words_from_the_day_the_input_was_received_and_is_due_on_the_first_day(env):
    cfg, store, _ = env
    cs_id, statuses = run(store, cfg, [added(), repeat_of()], mine=True)
    assert statuses == ["applied", "applied"]
    kept = data(store, made_action(store, cs_id))
    # Received on a Wednesday: the first Friday on or after it is two days later.
    assert kept["repeat"]["start"] == "2026-10-16" and kept["due"] == "2026-10-16"


def test_the_at_sign_counts_ops_from_zero_and_names_only_the_one_it_says(env):
    cfg, store, _ = env
    other = {**added(due=FRIDAY), "text": "Send the monthly report"}
    ops = [{"op": "note", "text": "Noted."}, added(due=MONDAY), other, repeat_of(to="@2")]
    cs_id, statuses = run(store, cfg, ops, mine=True)
    assert statuses == ["applied"] * 4
    assert data(store, made_action(store, cs_id, 1))["repeat"] is None
    assert data(store, made_action(store, cs_id, 2))["repeat"]["start"] == FRIDAY.isoformat()
    assert data(store, made_action(store, cs_id, 2))["repeat"]["phrase"] == WEEKLY


def test_a_repeat_read_from_an_input_is_held_with_its_words_and_the_to_do_still_applies(env):
    cfg, store, _ = env
    cs_id, statuses = run(store, cfg, [added(due=FRIDAY), repeat_of()], mine=False)
    assert statuses == ["applied", "held"]
    action_id = made_action(store, cs_id)
    assert data(store, action_id)["repeat"] is None
    held = store.read().get("changeset", cs_id).data["ops"][1]
    assert WEEKLY in held["reason"] and held["problems"][0]["check"] == "repeat-confirm"
    assert held["label"] == f"Make the new to-do repeat: {WEEKLY}"


def test_a_held_repeat_released_later_resolves_from_what_the_changeset_made(env):
    cfg, store, _ = env
    cs_id, _ = run(store, cfg, [added(due=FRIDAY), repeat_of()], mine=False)
    action_id = made_action(store, cs_id)
    release(store, cfg, cs_id, 1)
    assert data(store, action_id)["repeat"] == {
        "rule": "FREQ=WEEKLY;BYDAY=FR",
        "phrase": WEEKLY,
        "start": FRIDAY.isoformat(),
    }
    assert store.read().get("changeset", cs_id).data["ops"][1]["status"] == "applied"


def test_a_held_repeat_released_after_its_to_do_is_gone_or_ended_is_refused_plainly(env):
    cfg, store, _ = env
    cs_id, _ = run(store, cfg, [added(due=FRIDAY), repeat_of()], mine=False)
    action_id = made_action(store, cs_id)
    with store.transaction() as tx:
        tx.delete("action", action_id, _TEST, read_version=tx.get("action", action_id).version)
    with pytest.raises(StoreError, match=f"there is no action {action_id}"):
        release(store, cfg, cs_id, 1)
    assert store.read().get("changeset", cs_id).data["ops"][1]["status"] == "held"
    ended, _ = run(store, cfg, [added(due=FRIDAY), repeat_of()], mine=False)
    finish(store, cfg, made_action(store, ended))
    with pytest.raises(StoreError, match="can't be made to repeat"):
        release(store, cfg, ended, 1)


def test_words_the_grammar_declines_refuse_the_repeat_alone_and_the_to_do_still_applies(env):
    cfg, store, _ = env
    for mine in (True, False):
        odd = "whenever the mood takes me"
        cs_id, statuses = run(store, cfg, [added(due=FRIDAY), repeat_of(odd)], mine=mine, raw=f"{SAID} {odd}.")
        assert statuses == ["applied", "refused"]
        refused = store.read().get("changeset", cs_id).data["ops"][1]
        assert refused["reason"] == "the repeat in the input isn't clear"
        assert data(store, made_action(store, cs_id))["repeat"] is None


def test_words_that_are_clear_but_miss_the_to_dos_day_are_refused_in_plain_words(env):
    cfg, store, _ = env
    cs_id, statuses = run(store, cfg, [added(due=FRIDAY), repeat_of("every Monday")], mine=True)
    assert statuses == ["applied", "refused"]
    assert "isn't one of the days" in store.read().get("changeset", cs_id).data["ops"][1]["reason"]


def test_the_check_reads_the_words_against_the_earlier_ops_before_anything_is_applied(env):
    cfg, store, _ = env
    before = len(store.read().list("action"))

    def problems(words: str):
        cs = CHANGESET.validate_python({"ops": [added(due=FRIDAY, owners=[pm_of(cfg)]), repeat_of(words)]})
        ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs(None, None, SAID, "", "trusted"))
        return [(p.op, p.severity) for p in check(cs, ctx) if p.check == "targets"]

    assert problems("whenever the mood takes me") == [(1, "refuse")]
    assert problems(WEEKLY) == []
    assert len(store.read().list("action")) == before


def test_an_at_sign_that_does_not_name_an_earlier_add_is_refused_and_nothing_repeats(env):
    cfg, store, _ = env
    note = {"op": "note", "text": "Noted."}
    for ops in (
        [repeat_of(to="@0")],
        [added(due=FRIDAY), repeat_of(to="@1")],
        [added(due=FRIDAY), repeat_of(to="@5")],
        [note, repeat_of(to="@0")],
    ):
        cs_id, statuses = run(store, cfg, ops, mine=True)
        assert statuses[-1] == "refused", ops
        assert "must name an" in store.read().get("changeset", cs_id).data["ops"][-1]["reason"]
    assert all(a.data.get("repeat") is None for a in store.read().list("action"))
    with pytest.raises(ValueError, match="the number of the op"):
        run(store, cfg, [added(), repeat_of(to="@first")], mine=True)


def test_the_words_of_a_repeat_cannot_be_given_with_its_rule_or_empty(env):
    cfg, store, _ = env
    both = {**repeat_of(), "rule": "FREQ=WEEKLY;BYDAY=FR", "phrase": WEEKLY, "start": FRIDAY.isoformat()}
    with pytest.raises(ValueError, match="not both"):
        run(store, cfg, [added(), both], mine=True)
    with pytest.raises(ValueError):
        run(store, cfg, [added(), repeat_of(" ")], mine=True)


def test_the_words_of_a_repeat_must_be_inside_its_quoted_evidence(env):
    cfg, store, _ = env
    # A model that writes words the input never said is refused: the words are read only from the quote.
    made_up = {**repeat_of(), "words": "every Monday"}
    with pytest.raises(ValueError, match="aren't in it"):
        run(store, cfg, [added(), made_up], mine=False)


# ---- the next occurrence ----------------------------


def test_done_makes_the_next_with_the_same_words_owners_project_notes_and_repeat_due_on_the_next_date(env):
    cfg, store, _ = env
    project = store.read().list("project")[0].id
    first = repeating(store, cfg, project=project)
    finish(store, cfg, first)
    assert data(store, first)["status"] == "done"
    (later,) = open_ones(store, first)
    assert later["id"] != first
    assert {k: later[k] for k in ("text", "owners", "project", "notes", "repeat")} == {
        k: data(store, first)[k] for k in ("text", "owners", "project", "notes", "repeat")
    }
    assert later["occurrence_of"] == first
    assert later["due"] == "2026-11-13"


def test_each_occurrence_is_its_own_row_and_only_the_next_exists(env):
    cfg, store, clock = env
    first = repeating(store, cfg)
    finish(store, cfg, first)
    (second,) = open_ones(store, first)
    clock.on(date(2026, 11, 13))
    finish(store, cfg, second["id"])
    (third,) = open_ones(store, first)
    assert third["due"] == "2026-11-20" and third["occurrence_of"] == first
    assert len(chain(store, first)) == 3


def test_the_31st_falls_on_the_last_day_of_a_short_month(env):
    cfg, store, clock = env
    start = date(2027, 1, 31)
    clock.on(start)
    first = repeating(store, cfg, "every month on the 31st", start)
    finish(store, cfg, first)
    (second,) = open_ones(store, first)
    assert second["due"] == "2027-02-28"
    clock.on(date(2027, 2, 28))
    finish(store, cfg, second["id"])
    assert open_ones(store, first)[0]["due"] == "2027-03-31"


def test_a_missed_one_stays_open_and_finished_late_makes_the_next_from_today(env):
    cfg, store, clock = env
    first = repeating(store, cfg)
    clock.on(date(2026, 11, 18))  # the Friday of the 6th went by
    assert data(store, first)["status"] == "open", "nothing closes a missed one"
    assert len(chain(store, first)) == 1, "and nothing makes the next while it is open"
    finish(store, cfg, first)
    assert open_ones(store, first)[0]["due"] == "2026-11-20"
    # Finished after the next Friday too: the next is the first Friday from that day, never one in the past.
    other = repeating(store, cfg)
    clock.on(date(2026, 11, 21))
    finish(store, cfg, other)
    assert open_ones(store, other)[0]["due"] == "2026-11-27"


def test_done_early_makes_the_next_after_the_day_it_was_due(env):
    cfg, store, clock = env
    clock.on(date(2026, 11, 3))
    first = repeating(store, cfg)
    finish(store, cfg, first)
    assert open_ones(store, first)[0]["due"] == "2026-11-13"


def test_dropped_makes_the_next_too(env):
    cfg, store, _ = env
    first = repeating(store, cfg)
    drop = {"op": "action.drop", "id": first, "reason": "Nobody reads it any more"}
    apply_as_person(store, cfg, [drop], "Dropped a to-do")
    assert data(store, first)["status"] == "dropped"
    (later,) = open_ones(store, first)
    assert later["due"] == "2026-11-13" and later["text"] == TEXT


def test_done_by_someone_else_makes_the_next_owned_by_the_same_people(env):
    cfg, store, _ = env
    other = other_of(cfg)
    first = repeating(store, cfg, owner=other)
    they_finished(store, cfg, first, other)
    assert data(store, first)["done_by"] == [other]
    (later,) = open_ones(store, first)
    assert [o["person"] for o in later["owners"]] == [other] and later["due"] == "2026-11-13"


def test_undo_of_the_ending_takes_the_next_back_too(env):
    cfg, store, _ = env
    first = repeating(store, cfg)
    done = finish(store, cfg, first)
    assert len(chain(store, first)) == 2
    undo_changeset(store, done)
    assert data(store, first)["status"] == "open"
    assert len(chain(store, first)) == 1


def test_nothing_is_made_for_a_to_do_that_does_not_repeat_or_whose_repeat_was_stopped(env):
    cfg, store, _ = env
    plain = todo(store, cfg)
    finish(store, cfg, plain)
    assert not store.read().find("action", {"occurrence_of": plain})
    first = repeating(store, cfg)
    stopped = apply_as_person(store, cfg, [{"op": "action.repeat", "id": first}], "Stopped a to-do repeating")
    assert data(store, first)["repeat"] is None
    assert data(store, first)["status"] == "open", "stopping leaves the open one as it is"
    finish(store, cfg, first)
    assert len(chain(store, first)) == 1
    undo_changeset(store, stopped)
    assert data(store, first)["repeat"]["phrase"] == WEEKLY


def test_a_second_next_is_never_made_while_another_occurrence_is_open(env):
    cfg, store, clock = env
    first = repeating(store, cfg)
    finish(store, cfg, first)
    (second,) = open_ones(store, first)
    # The person reopens the first (a screen's own change) while the second is open: ending it again adds nothing.
    with store.transaction() as tx:
        cur = tx.get("action", first)
        tx.update("action", first, {"status": "open"}, _TEST, read_version=cur.version)
    clock.on(date(2026, 11, 7))
    finish(store, cfg, first)
    assert [a["id"] for a in open_ones(store, first)] == [second["id"]]


def test_the_earlier_occurrences_are_listed_with_their_day_and_how_each_ended(env):
    cfg, store, clock = env
    first = repeating(store, cfg)
    finish(store, cfg, first)
    (second,) = open_ones(store, first)
    clock.on(date(2026, 11, 13))
    apply_as_person(store, cfg, [{"op": "action.drop", "id": second["id"], "reason": "Not needed"}], "Dropped")
    (third,) = open_ones(store, first)
    found = repeats.earlier_occurrences(store.read(), store.read().get("action", third["id"]))
    assert found == [
        {"id": first, "due": "2026-11-06", "how": "done"},
        {"id": second["id"], "due": "2026-11-13", "how": "dropped"},
    ]


# ---- the screens' routes ----------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def test_checking_a_phrase_says_what_was_understood_or_that_it_is_not_clear(api):
    client, _, _ = api
    said = client.post("/api/repeats/check", json={"phrase": "Mondays and Thursdays", "start": "2026-11-02"}).json()
    assert said["status"] == "ok" and said["start"] == "2026-11-02"
    assert said["shape"]["kind"] == "weekly_days" and said["shape"]["weekdays"] == ["monday", "thursday"]
    assert said["rule"] == "FREQ=WEEKLY;BYDAY=MO,TH"
    none = client.post("/api/repeats/check", json={"phrase": "Tuesdays"}).json()
    assert none["status"] == "ok" and date.fromisoformat(none["start"]).weekday() == 1, "the first Tuesday"
    off = client.post("/api/repeats/check", json={"phrase": "every Tuesday", "start": "2026-11-04"}).json()
    assert off["status"] == "off_start" and off["start"] == "2026-11-10" and off["shape"]["weekday"] == "tuesday"
    for words in ("biweekly", "quarterly", "now and then", "water the plants every day"):
        unclear = client.post("/api/repeats/check", json={"phrase": words, "start": "2026-11-02"}).json()
        assert unclear == {"status": "unclear", "rule": None, "shape": None, "start": None}


def test_the_routes_set_and_stop_a_repeat_with_undo_and_the_views_carry_it(api):
    client, store, cfg = api
    action_id = todo(store, cfg, due=date(2026, 11, 9))
    unclear = client.post(f"/api/actions/{action_id}/repeat", json={"phrase": "quarterly"})
    assert unclear.status_code == 409 and "isn't clear" in unclear.json()["detail"]
    off = client.post(f"/api/actions/{action_id}/repeat", json={"phrase": "every Tuesday"})
    assert off.status_code == 409 and "2026-11-10" in off.json()["detail"]
    done = client.post(f"/api/actions/{action_id}/repeat", json={"phrase": "every other Monday"})
    assert done.status_code == 200
    assert data(store, action_id)["repeat"]["rule"] == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"
    row = next(a for a in client.get("/api/open-items").json()["actions"] if a["id"] == action_id)
    assert row["repeat"]["phrase"] == "every other Monday"
    assert row["repeat"]["shape"] == {
        "kind": "weekly",
        "interval": 2,
        "weekday": "monday",
        "weekdays": [],
        "day": None,
        "days": [],
        "ordinal": None,
        "ordinals": [],
        "position": None,
        "month": None,
    }
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert data(store, action_id)["repeat"] is None
    client.post(f"/api/actions/{action_id}/repeat", json={"phrase": "every other Monday"})
    stopped = client.post(f"/api/actions/{action_id}/repeat/stop")
    assert stopped.status_code == 200 and data(store, action_id)["repeat"] is None
    assert client.post(f"/api/actions/{action_id}/repeat/stop").status_code == 409


def test_mark_done_makes_the_next_and_reopening_takes_it_back_and_the_page_lists_the_earlier_ones(api):
    client, store, cfg = api
    from engine.today import zone

    today = datetime.now(zone(cfg)).date()
    action_id = todo(store, cfg, due=today)
    assert client.post(f"/api/actions/{action_id}/repeat", json={"phrase": "daily"}).status_code == 200
    assert client.post(f"/api/actions/{action_id}/status", json={"status": "done"}).status_code == 200
    (later,) = open_ones(store, action_id)
    assert later["due"] == (today.fromordinal(today.toordinal() + 1)).isoformat()
    page = client.get(f"/api/record-pages/{later['id']}", params={"kind": "action"}).json()
    assert page["repeat"]["phrase"] == "daily"
    assert page["earlier_occurrences"] == [{"id": action_id, "due": today.isoformat(), "how": "done"}]
    assert all(d["field"] not in ("repeat", "occurrence_of") for d in page["details"])
    assert client.post(f"/api/actions/{action_id}/status", json={"status": "open"}).status_code == 200
    assert data(store, action_id)["status"] == "open"
    assert open_ones(store, action_id) == [{"id": action_id, **data(store, action_id)}]
