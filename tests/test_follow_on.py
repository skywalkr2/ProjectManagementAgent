"""The follow-on run (design 6.7, follow-on changes; roadmap L7): one request when a dated record moves or a fact is
replaced, queued in the same transaction as the change; what is tied to the move is found by code; the run's own
changes start no other run (one hop); changes to the person's own items apply with Undo and what already reached
someone gets a drafted correction that waits. Names and ids come from the fixtures; the AI is the stub."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from engine import follow_on
from engine import packet as packets
from engine import series as series_module
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, apply_as_person, apply_changeset
from engine.dispatcher import process, undo_changeset
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.tasks import task_kind
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records, without_first_go
from tests.test_knowledge_records import request as make_request
from tests.test_knowledge_section import lesson

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
TODAY = date(2026, 10, 14)
_PM = WriteContext("pm", "trusted", "test")
PROJECT = fixture_records(DEMO_B, "project")[0]
PERSONS = [p["id"] for p in fixture_records(DEMO_B, "person")]
OWNER, TOLD, ASKED = PERSONS[1], PERSONS[2], PERSONS[3]
OLD, NEW = "2026-10-22", "2026-10-24"
RAW = "The sync moved."


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def make(store, kind, **fields) -> str:
    base = {
        "event": {"title": "Printer sync", "start": OLD, "project": PROJECT["id"], "trust": "trusted"},
        "action": {"text": "Review the proof", "owners": [{"person": OWNER}], "project": PROJECT["id"]},
        "question": {"to": ASKED, "title": "Which proof is final?", "projects": [PROJECT["id"]]},
        "fact": {"text": "The press slot is on the 22nd.", "project": PROJECT["id"], "trust": "trusted"},
        "series": {"title": "Printer sync", "trust": "trusted"},
    }[kind]
    with store.transaction() as tx:
        return tx.create(kind, {**base, **fields}, _PM).id


def follow_ons(store) -> list:
    return [r for r in store.read().list("request") if r.data["task"] == follow_on.TASK]


def edit(env, kind, record_id, **fields) -> str:
    """The person's own change to fields of a record, as the screens make it: the changeset id."""
    _, cfg, store = env
    op = {
        "op": "record.edit",
        "record": {"kind": kind, "id": record_id},
        "fields": fields,
        "read_version": store.read().get(kind, record_id).version,
    }
    return apply_as_person(store, cfg, [op], "Changed on screen")


def assistant_applies(env, ops, *, raw=RAW, request_id=None, task="notes") -> tuple[str, list[str]]:
    """Apply ops as the assistant does from an input, with these words as the input: the changeset and its statuses."""
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    request_id = request_id or make_request(store, "input", task=task)
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request_id, None, "", raw, "untrusted"),
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def moved_due(action_id: str, due: str = NEW) -> list[dict]:
    return [
        {
            "op": "record.set",
            "kind": "action",
            "id": action_id,
            "field": "due",
            "value": due,
            "evidence": {"quote": RAW},
        }
    ]


def scripted(*bodies: dict) -> list:
    """Make the stub answer with these answers in turn (the last repeats), and record what it was asked."""
    asked: list = []
    queue = [json.dumps(b) for b in bodies]

    def responder(task):
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    set_responder(responder)
    return asked


def run(env, request_id: str):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def line(move: str) -> str:
    return f"{move} was {OLD}, now {NEW}"


def moved_entry(env):
    """An entry with an action on it and the person's move of the entry to a new day: the entry, the action, the
    queued request."""
    _, _, store = env
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD)
    edit(env, "event", entry, start=NEW)
    return entry, action, follow_ons(store)[0]


# ---- queuing: one request per save, with the change ---------------------------------------------------------------


def test_the_persons_edit_of_an_entrys_day_queues_one_request_naming_the_change(env):
    _, _, store = env
    entry = make(store, "event", end="2026-10-23")
    cs_id = edit(env, "event", entry, start=NEW, end="2026-10-25")
    (queued,) = follow_ons(store)
    assert queued.data["follows"] == cs_id
    assert queued.data["about"] == {"kind": "event", "id": entry}
    assert (queued.data["state"], queued.data["origin"]) == ("queued", "schedule")


def test_one_save_that_moves_several_records_queues_one_request_listing_them_all(env):
    _, cfg, store = env
    entry, action = make(store, "event"), make(store, "action", due=OLD)
    ops = [
        {"op": "record.edit", "record": {"kind": k, "id": i}, "fields": f, "read_version": 1}
        for k, i, f in (("event", entry, {"start": NEW}), ("action", action, {"due": NEW}))
    ]
    cs_id = apply_as_person(store, cfg, ops, "Changed on screen")
    assert len(follow_ons(store)) == 1
    assert {(m.kind, m.record) for m in follow_on.moves_of(store.read(), cs_id)} == {
        ("event", entry),
        ("action", action),
    }


def test_the_assistants_move_of_an_actions_due_day_from_an_input_queues_one_request(env):
    _, _, store = env
    action = make(store, "action", due=OLD)
    cs_id, statuses = assistant_applies(env, moved_due(action))
    assert statuses == ["applied"]
    (queued,) = follow_ons(store)
    assert queued.data["follows"] == cs_id and queued.data["about"] == {"kind": "action", "id": action}


def test_a_replaced_fact_queues_one_request_whoever_replaces_it(env):
    _, _, store = env
    old = make(store, "fact")
    op = {
        "op": "fact",
        "text": "The press slot is on the 24th.",
        "project": PROJECT["id"],
        "supersedes": old,
        "evidence": {"quote": RAW},
    }
    cs_id, statuses = assistant_applies(env, [op])
    assert statuses == ["applied"]
    (queued,) = follow_ons(store)
    (move,) = follow_on.moves_of(store.read(), cs_id)
    assert (queued.data["follows"], move.kind, move.after) == (cs_id, "fact", old)


@pytest.mark.parametrize("change", ["new_action", "words_only", "same_day", "off", "first_value"])
def test_a_save_that_moves_no_date_queues_nothing(env, change):
    _, _, store = env
    entry, action = make(store, "event"), make(store, "action", due=OLD)
    if change == "new_action":
        make(store, "action", due=NEW)
    elif change == "words_only":
        edit(env, "action", action, text="Review the final proof")
    elif change == "same_day":
        edit(env, "event", entry, start=OLD, title="Printer sync, moved room")
    elif change == "off":
        store.plugins.cfg.dispatch.knowledge.follow_on = False
        edit(env, "event", entry, start=NEW)
    elif change == "first_value":
        assistant_applies(env, moved_due(make(store, "action")))  # a day where there was none is not a move
    assert follow_ons(store) == []


def test_an_undo_of_a_move_and_the_series_roll_are_not_moves(env):
    _, _, store = env
    entry = make(store, "event")
    cs_id = edit(env, "event", entry, start=NEW)
    (queued,) = follow_ons(store)
    undo_changeset(store, cs_id)
    assert follow_ons(store) == [queued]
    action = make(store, "action")
    with store.transaction() as tx:  # the daily roll of an item to the next instance writes `event`, not a day
        tx.update("action", action, {"event": entry}, series_module.ROLL, read_version=1)
    assert follow_ons(store) == [queued]


# ---- one hop ------------------------------------------------------------------------------------------------------


def test_the_follow_on_runs_own_changes_start_no_other_run(env):
    ws, cfg, store = env
    entry, action, queued = moved_entry(env)
    packet = packets.build(ws, store, cfg, queued.id, TODAY)
    quote = line("start")
    assert quote in packet.raw_input
    scripted(
        {
            "summary": "Moved the action with the entry.",
            "ops": [
                {
                    "op": "record.set",
                    "kind": "action",
                    "id": action,
                    "field": "due",
                    "value": NEW,
                    "evidence": {"quote": quote},
                }
            ],
        }
    )
    cs_id = run(env, queued.id)
    assert store.read().get("action", action).data["due"] == NEW
    assert len(follow_ons(store)) == 1  # the run's own move of a due day queued nothing
    assert store.read().get("changeset", cs_id).data["request"] == queued.id


def test_a_move_the_person_makes_after_a_run_is_a_new_save_and_queues_again(env):
    _, _, store = env
    _, action, _ = moved_entry(env)
    edit(env, "action", action, due="2026-10-30")
    assert len(follow_ons(store)) == 2


def test_a_move_applied_for_a_follow_on_request_starts_none_whatever_applies_it(env):
    _, _, store = env
    entry, action, queued = moved_entry(env)
    cs_id, _ = assistant_applies(env, moved_due(action, "2026-10-26"), request_id=queued.id)
    assert len(follow_ons(store)) == 1
    assert store.read().get("changeset", cs_id).data["request"] == queued.id


# ---- what is tied -------------------------------------------------------------------------------------------------


def tied(env, request_id: str) -> dict[str, list[str]]:
    _, _, store = env
    cfg = store.plugins.cfg
    view = store.read()
    moves = follow_on.moves_of(view, view.get("request", request_id).data["follows"])
    return {f"{t.kind}:{t.id}": t.why for t in follow_on.tied_records(view, cfg, moves)}


def test_items_naming_the_entry_or_its_series_are_tied_first_then_those_citing_the_old_day(env):
    _, _, store = env
    series = make(store, "series")
    entry = make(store, "event", series=series)
    on_entry = make(store, "action", event=entry, due=OLD)
    on_series = make(store, "question", series=series)
    cites = make(store, "action", text="Send the proofs before the 22nd")
    iso = make(store, "action", text=f"Book the van for {OLD}")
    spelled = make(store, "question", title="Is 22 October still the delivery day?")
    other_project = make(store, "action", text="Collect the samples on 22 October", project=None)
    other_day = make(store, "action", text="Send the proofs before the 21st")
    settled = make(store, "action", text="Pay the invoice on the 22nd", status="done", done_by=[OWNER])
    edit(env, "event", entry, start=NEW)
    found = tied(env, follow_ons(store)[0].id)
    assert list(found)[:2] == [f"action:{on_entry}", f"question:{on_series}"]
    assert {f"action:{cites}", f"action:{iso}", f"question:{spelled}"} <= set(found)
    assert not {f"action:{other_project}", f"action:{other_day}", f"action:{settled}", f"event:{entry}"} & set(found)
    assert found[f"action:{on_entry}"] == [f"is on calendar entry {entry}"]
    assert "old day" in found[f"action:{cites}"][0]


def test_a_move_inside_the_same_day_ties_only_what_names_the_entry(env):
    _, _, store = env
    entry = make(store, "event", start=f"{OLD}T09:00:00")
    on_entry = make(store, "action", event=entry)
    make(store, "action", text="Send the proofs before the 22nd")
    edit(env, "event", entry, start=f"{OLD}T11:00:00")
    assert list(tied(env, follow_ons(store)[0].id)) == [f"action:{on_entry}"]


def test_a_moved_action_ties_the_open_items_on_its_project_that_cite_its_old_day(env):
    _, _, store = env
    action = make(store, "action", text="Send the cover", due=OLD)
    cites = make(store, "question", title=f"Will the cover arrive on {OLD}?")
    edit(env, "action", action, due=NEW)
    assert list(tied(env, follow_ons(store)[0].id)) == [f"question:{cites}"]


def test_a_replaced_fact_ties_items_that_repeat_it_and_ignores_the_fact_itself_and_the_replaced_ones(env):
    _, _, store = env
    old = make(store, "fact", text="The press slot is booked for the third week of November")
    repeats = make(store, "action", text="Confirm the press slot booked for the third week of November")
    unrelated = make(store, "action", text="Review the proof")
    other = make(store, "action", text="Confirm the press slot booked for the third week of November", project=None)
    op = {
        "op": "fact",
        "text": "The press slot is booked for the first week of December",
        "project": PROJECT["id"],
        "supersedes": old,
        "evidence": {"quote": RAW},
    }
    assistant_applies(env, [op])
    found = tied(env, follow_ons(store)[0].id)
    assert list(found) == [f"action:{repeats}"] and old in found[f"action:{repeats}"][0]
    assert not {f"action:{unrelated}", f"action:{other}", f"fact:{old}"} & set(found)


def test_no_more_than_the_configured_number_are_tied_and_those_naming_the_entry_come_first(env):
    _, cfg, store = env
    entry = make(store, "event")
    cites = [make(store, "action", text=f"Prepare part {n} before the 22nd") for n in range(3)]
    linked = make(store, "action", event=entry)
    store.plugins.cfg.dispatch.knowledge.follow_on_max_tied = 2
    edit(env, "event", entry, start=NEW)
    found = tied(env, follow_ons(store)[0].id)
    assert list(found) == [f"action:{linked}", f"action:{cites[0]}"]


def test_the_day_patterns_are_configured_and_each_form_of_a_day_is_found(env):
    _, cfg, _ = env
    day = date.fromisoformat(OLD)
    rxs = follow_on.date_regexes(cfg.language.date_patterns, day)

    def hits(text):
        return any(rx.search(text) for rx in rxs)

    assert all(hits(t) for t in (f"on {OLD}", "22 October", "the 22nd of Oct", "Oct. 22nd", "October 22", "the 22nd"))
    assert not any(hits(t) for t in ("2026-10-23", "the 122nd", "October 2", "22 November", "the 2nd"))


# ---- the packet ---------------------------------------------------------------------------------------------------


def test_the_packet_shows_the_move_the_tied_records_as_they_are_now_who_they_reached_and_the_knowledge(env):
    ws, cfg, store = env
    entry = make(store, "event")
    action = make(store, "action", event=entry, due=OLD, told={TOLD: "2026-10-10"})
    question = make(store, "question", event=entry, status="sent", sent_at="2026-10-10T09:00:00+00:00")
    learned = lesson(store, "A moved date moves its meeting's actions.", guard="Check the entry.")
    edit(env, "event", entry, start=NEW)
    (queued,) = follow_ons(store)
    built = packets.build(ws, store, cfg, queued.id, TODAY)
    people = People(store, cfg)
    assert line("start") in built.raw_input and f"calendar entry {entry}" in built.raw_input
    assert built.raw_input.count("<untrusted") == 2 and built.untrusted_material
    assert f"{people.name(TOLD)} ({TOLD})" in built.raw_input and f"{people.name(ASKED)} ({ASKED})" in built.raw_input
    assert action in built.raw_input and question in built.raw_input
    assert learned in built.task.stable or learned in built.task.request  # what was learned reaches the run
    assert built.knowledge is not None and learned in built.knowledge.given
    assert built.task.instructions.startswith("You are") and built.task.kind == follow_on.TASK


def test_a_run_writes_its_knowledge_log_and_the_kind_declares_the_ops_it_may_use(env):
    ws, cfg, store = env
    _, _, queued = moved_entry(env)
    scripted({"summary": "Nothing tied needed a change.", "ops": []})
    run(env, queued.id)
    log = store.read().list("run")[-1].data["knowledge"]
    assert set(log) >= {"given", "stable_chars", "rules_present"}
    assert task_kind(follow_on.TASK).ops == ("record.set", "question.add", "note")


# ---- results ------------------------------------------------------------------------------------------------------


def test_a_change_to_the_persons_own_action_applies_with_undo(env):
    ws, cfg, store = env
    entry, action, queued = moved_entry(env)
    scripted(
        {
            "summary": "Moved the action with the entry.",
            "ops": [
                {
                    "op": "record.set",
                    "kind": "action",
                    "id": action,
                    "field": "due",
                    "value": NEW,
                    "evidence": {"quote": line("start")},
                }
            ],
        }
    )
    cs_id = run(env, queued.id)
    assert [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]] == ["applied"]
    assert store.read().get("request", queued.id).data["state"] == "review"
    undo_changeset(store, cs_id)
    assert store.read().get("action", action).data["due"] == OLD


def test_what_already_reached_someone_gets_a_drafted_correction_that_waits_and_is_not_edited(env):
    ws, cfg, store = env
    entry = make(store, "event")
    told = make(store, "action", event=entry, due=OLD, told={TOLD: "2026-10-10"})
    edit(env, "event", entry, start=NEW)
    (queued,) = follow_ons(store)
    scripted(
        {
            "summary": "Drafted a correction.",
            "ops": [
                {
                    "op": "record.set",
                    "kind": "action",
                    "id": told,
                    "field": "due",
                    "value": NEW,
                    "evidence": {"quote": line("start")},
                },
                {
                    "op": "question.add",
                    "to": TOLD,
                    "title": "The sync moved to the 24th: is your part still on track?",
                    "text": "The printer sync moved from the 22nd to the 24th.",
                    "links": [{"label": PROJECT["links"][0]["label"], "url": PROJECT["links"][0]["url"]}],
                    "project": PROJECT["id"],
                    "matters_for": entry,
                },
            ],
        }
    )
    cs_id = run(env, queued.id)
    first, second = store.read().get("changeset", cs_id).data["ops"]
    assert first["status"] == "refused" and "already reached someone" in first["reason"]
    assert second["status"] == "applied"
    assert store.read().get("action", told).data["due"] == OLD
    drafted = store.read().get("question", second["records"][0]["id"]).data
    assert (drafted["to"], drafted["status"], drafted["sent_at"]) == (TOLD, "open", None)


def test_a_correction_goes_only_to_someone_a_tied_item_reached_and_only_tied_actions_change(env):
    ws, cfg, store = env
    entry, action, queued = moved_entry(env)
    stranger = make(store, "action", text="Collect the samples")
    scripted(
        {
            "summary": "Too much.",
            "ops": [
                {
                    "op": "question.add",
                    "to": TOLD,
                    "title": "Is the sync still on?",
                    "project": PROJECT["id"],
                    "links": [{"label": "Page", "url": PROJECT["links"][0]["url"]}],
                    "matters_for": entry,
                },
                {
                    "op": "record.set",
                    "kind": "action",
                    "id": stranger,
                    "field": "due",
                    "value": NEW,
                    "evidence": {"quote": line("start")},
                },
                {"op": "record.set", "kind": "action", "id": action, "field": "notes", "value": "x"},
            ],
        }
    )
    cs_id = run(env, queued.id)
    outcomes = store.read().get("changeset", cs_id).data["ops"]
    reasons = [o.get("reason") or "" for o in outcomes]
    assert [o["status"] for o in outcomes] == ["refused"] * 3
    assert "someone a tied item already reached" in reasons[0]
    assert "isn't tied to what moved" in reasons[1]
    assert "only the day or words of an action" in reasons[2]


def test_an_answer_with_no_change_finishes_the_request_and_a_move_undone_before_the_run_closes_it(env):
    ws, cfg, store = env
    _, _, queued = moved_entry(env)
    scripted({"summary": "Nothing tied needed a change.", "ops": []})
    run(env, queued.id)
    done = store.read().get("request", queued.id).data
    assert (done["state"], done["waiting"]) == ("done", follow_on.NOTHING_TIED)

    entry = make(store, "event", title="Another sync")
    cs_id = edit(env, "event", entry, start=NEW)
    second = follow_ons(store)[-1]
    undo_changeset(store, cs_id)
    scripted({"summary": "never asked", "ops": []})
    assert run(env, second.id) is None
    closed = store.read().get("request", second.id).data
    assert (closed["state"], closed["waiting"]) == ("done", follow_on.STALE)
    assert not store.read().list("run")[1:]  # no call was made for it
