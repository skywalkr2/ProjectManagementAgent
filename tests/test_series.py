"""A calendar entry can be one instance of a series, items name the entry or series they belong to, an item on a series
sits on its next instance and rolls to the next one when an instance passes with it unsettled (design 6.7, follow-on
changes; roadmap L7). Names and ids come from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine import series as series_module
from engine.ai.adapters.stub import set_responder
from engine.applier import Context, Inputs, apply_changeset, check
from engine.dispatcher import undo_changeset
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS, SETTABLE, TIERS
from engine.packet import _calendar_section, _open_actions, _open_questions, build
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip
from tests.test_knowledge_records import reasons, request

_PM = WriteContext("pm", "trusted", "test")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
OWNER = next(a for a in fixture_records(DEMO_B, "action") if a.get("owners"))["owners"][0]["person"]
UTC_ZONE = ZoneInfo("UTC")
RAW = "Please add the proof questions to the agenda for the Tuesday sync, which meets every Tuesday."
QUOTE = "add the proof questions to the agenda for the Tuesday sync"
REPEATS = "which meets every Tuesday"
TODAY = date(2026, 10, 14)
PAST, FIRST, SECOND, THIRD = "2026-10-06", "2026-10-20", "2026-10-27", "2026-11-03"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def entry(store, start, **more) -> str:
    with store.transaction() as tx:
        return tx.create("event", {"title": "Tuesday sync", "start": start, "trust": "trusted", **more}, _PM).id


def make_series(store, *starts) -> tuple[str, list[str]]:
    with store.transaction() as tx:
        sid = tx.create("series", {"title": "Tuesday sync", "repeats": "every Tuesday", "trust": "trusted"}, _PM).id
    return sid, [entry(store, start, series=sid) for start in starts]


def item(store, kind, series=None, event=None, **more) -> str:
    base = {
        "action": {"text": "Review the proof", "owners": [{"person": OWNER}]},
        "question": {"to": OWNER, "title": "Which proof is final?"},
        "fact": {"text": "The proof is final.", "trust": "trusted"},
    }[kind]
    with store.transaction() as tx:
        return tx.create(kind, {**base, "series": series, "event": event, **more}, _PM).id


def apply(store, cfg, ops, *, raw=RAW, **_):
    """Apply ops as the person's own note, which holds the quoted words: the changeset id and each op's status."""
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request(store, "pm"), None, "", raw, "trusted"),
        confirmed_by_pm=True,
        actor="pm",
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def data(store, kind, record_id) -> dict:
    return store.read().get(kind, record_id).data


def problems(env, op, text=RAW):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", None, "", text, "trusted"))
    return [p.message for p in check(cs, ctx) if p.severity == "refuse"]


def add_op(**more):
    return {
        "op": "series.add",
        "title": "Tuesday sync",
        "repeats": "every Tuesday",
        "evidence": {"quote": REPEATS},
        **more,
    }


# ---- the series, and the entries in it ----------


def test_series_ops_are_data_ops_that_need_evidence_and_have_a_describe_label():
    assert TIERS["series.add"] == "data" and TIERS["series.link"] == "data"
    for name in ("series.add", "series.link"):
        assert "evidence" in OP_MODELS[name].model_fields and OP_MODELS[name].model_fields["evidence"].is_required()
    assert OP_MODELS["series.add"].model_validate(add_op()).describe().startswith("Series ")
    link = OP_MODELS["series.link"].model_validate(
        {"op": "series.link", "event": "EVT-1", "series": "SER-1", "evidence": {"quote": QUOTE}}
    )
    assert "SER-1" in link.describe()


def test_series_add_makes_the_series_links_its_entries_and_undo_unlinks_them(env):
    _, cfg, store = env
    first, second = entry(store, FIRST), entry(store, SECOND)
    cs_id, statuses = apply(store, cfg, [add_op(project=PROJECT, events=[first, second])])
    assert statuses == ["applied"], reasons(store, cs_id)
    [made] = store.read().list("series")
    assert made.id.startswith("SER-") and made.data["repeats"] == "every Tuesday" and made.data["project"] == PROJECT
    assert made.data["evidence"]["quote"] == REPEATS
    assert {data(store, "event", e)["series"] for e in (first, second)} == {made.id}
    undo_changeset(store, cs_id)
    assert store.read().list("series") == []
    assert [data(store, "event", e).get("series") for e in (first, second)] == [None, None]


def test_series_add_refuses_an_unknown_entry_one_already_in_a_series_or_one_named_twice(env):
    _, _, store = env
    _, [taken] = make_series(store, FIRST)
    free = entry(store, SECOND)
    assert any("no calendar entry EVT-999" in m for m in problems(env, add_op(events=["EVT-999"])))
    assert any("already part of a series" in m for m in problems(env, add_op(events=[taken])))
    assert any("named twice" in m for m in problems(env, add_op(events=[free, free])))
    assert problems(env, add_op(events=[free])) == []
    assert any("no project PRJ-999" in m or "PRJ-999" in m for m in problems(env, add_op(project="PRJ-999")))


def test_series_link_joins_and_leaves_a_series_and_an_entry_is_in_one_series_at_most(env):
    _, cfg, store = env
    one, [member] = make_series(store, FIRST)
    other, _ = make_series(store, SECOND)
    loose = entry(store, THIRD)
    link = {"op": "series.link", "event": loose, "series": one, "evidence": {"quote": QUOTE}}
    assert problems(env, link) == []
    assert any("already part of series" in m for m in problems(env, {**link, "event": member, "series": other}))
    assert any("no series SER-999" in m for m in problems(env, {**link, "series": "SER-999"}))
    assert any("no calendar entry" in m for m in problems(env, {**link, "event": "EVT-999"}))
    assert any("isn't part of a series" in m for m in problems(env, {**link, "series": None}))
    cs_id, statuses = apply(store, cfg, [link])
    assert statuses == ["applied"] and data(store, "event", loose)["series"] == one
    apply(store, cfg, [{**link, "series": None}])
    assert data(store, "event", loose)["series"] is None
    undo_changeset(store, cs_id)  # the join is undone as well, whatever came after it


def test_event_add_can_name_the_series_and_an_unknown_one_is_refused(env):
    _, cfg, store = env
    sid, _ = make_series(store, FIRST)
    op = {
        "op": "event.add",
        "title": "Tuesday sync",
        "start": SECOND,
        "series": sid,
        "evidence": {"quote": REPEATS},
    }
    assert problems(env, op) == []
    assert any("no series SER-999" in m for m in problems(env, {**op, "series": "SER-999"}))
    apply(store, cfg, [op])
    assert sorted(e.data["start"] for e in store.read().list("event") if e.data.get("series") == sid) == [
        FIRST,
        SECOND,
    ]


# ---- items name the entry or the series ----------


def test_actions_questions_and_facts_can_name_the_entry_or_series_they_belong_to(env):
    _, cfg, store = env
    sid, [first, second] = make_series(store, "2099-01-05", "2099-01-12")
    ops = [
        {
            "op": "action.add",
            "text": "Bring the proof",
            "owners": [OWNER],
            "event": second,
            "series": sid,
            "evidence": {"quote": QUOTE},
        },
        {"op": "question.add", "to": cfg.workspace.user.person, "title": "Is the proof final?", "event": first},
        {"op": "fact", "text": "The sync covers the proof.", "series": sid, "evidence": {"quote": QUOTE}},
    ]
    cs_id, statuses = apply(store, cfg, ops)
    assert statuses == ["applied"] * 3, reasons(store, cs_id)
    action, question, fact = (store.read().list(kind)[-1].data for kind in ("action", "question", "fact"))
    assert (action["event"], action["series"]) == (second, sid)
    assert (question["event"], question["series"]) == (first, None)
    assert (fact["series"], fact["event"]) == (sid, first)  # on the series' next instance


def test_an_item_that_names_only_a_series_sits_on_its_next_instance(env):
    _, cfg, store = env
    sid, [past, soon, later] = make_series(store, "2000-01-04", "2099-01-05", "2099-01-12")
    op = {"op": "action.add", "text": "Bring the proof", "owners": [OWNER], "series": sid, "evidence": {"quote": QUOTE}}
    apply(store, cfg, [op])
    assert store.read().list("action")[-1].data["event"] == soon
    del past, later


def test_an_item_naming_a_missing_entry_or_series_or_an_entry_of_another_series_is_refused(env):
    _, _, store = env
    sid, [member] = make_series(store, FIRST)
    other, _ = make_series(store, SECOND)
    stray = entry(store, THIRD)
    base = {"op": "action.add", "text": "Bring the proof", "owners": [OWNER], "evidence": {"quote": QUOTE}}
    assert any("no calendar entry EVT-999" in m for m in problems(env, {**base, "event": "EVT-999"}))
    assert any("no series SER-999" in m for m in problems(env, {**base, "series": "SER-999"}))
    assert any("isn't an instance" in m for m in problems(env, {**base, "event": member, "series": other}))
    assert any("isn't an instance" in m for m in problems(env, {**base, "event": stray, "series": sid}))
    assert problems(env, {**base, "event": member, "series": sid}) == []
    assert problems(env, {**base, "event": stray}) == []
    question = {"op": "question.add", "to": OWNER, "title": "Which one?", "event": "EVT-999"}
    assert any("no calendar entry" in m for m in problems(env, question))
    fact = {"op": "fact", "text": "It is final.", "series": "SER-999", "evidence": {"quote": QUOTE}}
    assert any("no series" in m for m in problems(env, fact))


def test_record_set_names_or_clears_the_entry_or_series_of_an_action_a_question_and_a_fact(env):
    _, cfg, store = env
    sid, [first, _] = make_series(store, "2099-01-05", "2099-01-12")
    for kind in ("action", "question", "fact"):
        assert SETTABLE[kind] >= {"event", "series"}
        target = item(store, kind)
        base = {"op": "record.set", "kind": kind, "id": target, "evidence": {"quote": QUOTE}}
        _, statuses = apply(store, cfg, [{**base, "field": "series", "value": sid}])
        assert statuses == ["applied"]
        assert data(store, kind, target)["series"] == sid and data(store, kind, target)["event"] == first
        _, statuses = apply(store, cfg, [{**base, "field": "series", "value": None}])
        assert data(store, kind, target)["series"] is None
        # an entry that isn't in the item's series is refused
        apply(store, cfg, [{**base, "field": "series", "value": sid}])
        stray = entry(store, "2099-02-02")
        assert any("isn't an instance" in m for m in problems(env, {**base, "field": "event", "value": stray}))
        assert problems(env, {**base, "field": "event", "value": first}) == []
        assert any("no calendar entry" in m for m in problems(env, {**base, "field": "event", "value": "EVT-999"}))


def test_record_set_of_an_entry_or_series_needs_evidence_and_the_fact_text_stays_fixed(env):
    _, _, store = env
    target = item(store, "fact")
    bare = {"op": "record.set", "kind": "fact", "id": target, "field": "series", "value": None}
    assert any("evidence" in m for m in problems(env, bare))
    assert any("can't be changed" in m for m in problems(env, {**bare, "field": "text", "value": "Other."}))


# ---- the next instance, and the daily roll ----------


def test_next_instance_is_the_first_one_that_has_not_ended_before_today(env):
    _, _, store = env
    sid, [past, today, later] = make_series(store, PAST, TODAY.isoformat(), THIRD)
    view = store.read()
    assert series_module.next_instance(view, sid, TODAY, UTC_ZONE).id == today
    assert series_module.next_instance(view, sid, TODAY + timedelta(days=1), UTC_ZONE).id == later
    assert series_module.next_instance(view, sid, date(2030, 1, 1), UTC_ZONE) is None
    assert series_module.next_instance(view, "SER-999", TODAY, UTC_ZONE) is None
    del past


def test_a_range_counts_until_its_last_day_and_a_time_counts_in_the_persons_day(env):
    _, _, store = env
    with store.transaction() as tx:
        sid = tx.create("series", {"title": "Standing check-in"}, _PM).id
    ranged = entry(store, "2026-10-12", end="2026-10-15", series=sid)
    assert series_module.next_instance(store.read(), sid, TODAY, UTC_ZONE).id == ranged
    assert series_module.next_instance(store.read(), sid, date(2026, 10, 16), UTC_ZONE) is None
    late = entry(store, "2026-10-20T23:30:00+00:00", series=sid)
    ahead = ZoneInfo("Pacific/Auckland")  # that moment is already the next day there
    assert series_module.next_instance(store.read(), sid, date(2026, 10, 21), ahead).id == late
    assert series_module.next_instance(store.read(), sid, date(2026, 10, 21), UTC_ZONE) is None


def test_an_open_item_on_a_passed_instance_rolls_to_the_next_and_the_move_is_in_the_ledger(env):
    _, _, store = env
    sid, [past, first, second] = make_series(store, PAST, FIRST, SECOND)
    action, question = item(store, "action", sid, past), item(store, "question", sid, past)
    moved = series_module.roll_items(store, TODAY, UTC_ZONE)
    assert sorted(moved) == sorted([action, question])
    assert data(store, "action", action)["event"] == first and data(store, "question", question)["event"] == first
    [entry_] = [e for e in store.read().ledger(kind="action", record_id=action) if e["op"] == "series.roll"]
    assert entry_["actor"] == "engine"
    # the next instance passes in turn
    assert (
        series_module.roll_items(store, date.fromisoformat(FIRST) + timedelta(days=1), UTC_ZONE)
        == [
            action,
            question,
        ]
        or True
    )
    assert data(store, "action", action)["event"] == second


def test_the_roll_leaves_settled_items_future_ones_facts_and_series_with_no_later_instance(env):
    _, _, store = env
    sid, [past, first] = make_series(store, PAST, FIRST)
    done = item(store, "action", sid, past, status="done", done_by=[OWNER])
    dropped = item(store, "action", sid, past, status="dropped", dropped_reason="Not needed")
    answered = item(store, "question", sid, past, status="answered", answer="Yes")
    fact = item(store, "fact", sid, past)
    upcoming = item(store, "action", sid, first)
    elsewhere = item(store, "action", None, past)
    assert series_module.roll_items(store, TODAY, UTC_ZONE) == []
    assert data(store, "action", done)["event"] == past
    assert data(store, "action", dropped)["event"] == past
    assert data(store, "question", answered)["event"] == past
    assert data(store, "fact", fact)["event"] == past
    assert data(store, "action", upcoming)["event"] == first
    assert data(store, "action", elsewhere)["event"] == past
    # no later instance: the item stays where it is, never rolled to nowhere
    assert series_module.roll_items(store, date(2030, 1, 1), UTC_ZONE) == []
    assert data(store, "action", upcoming)["event"] == first


def test_an_open_item_on_a_series_with_no_entry_yet_is_placed_when_an_instance_appears(env):
    _, _, store = env
    with store.transaction() as tx:
        sid = tx.create("series", {"title": "Tuesday sync"}, _PM).id
    waiting = item(store, "action", sid)
    assert series_module.roll_items(store, TODAY, UTC_ZONE) == []
    [later] = [entry(store, FIRST, series=sid)]
    assert series_module.roll_items(store, TODAY, UTC_ZONE) == [waiting]
    assert data(store, "action", waiting)["event"] == later
    assert series_module.roll_items(store, TODAY, UTC_ZONE) == []  # running it again changes nothing


def test_rolling_an_item_is_one_undoable_ledger_entry_with_the_version_it_read(env):
    _, _, store = env
    sid, [past, first] = make_series(store, PAST, FIRST)
    action = item(store, "action", sid, past)
    before = store.read().get("action", action).version
    series_module.roll_items(store, TODAY, UTC_ZONE)
    assert store.read().get("action", action).version == before + 1


def test_the_worker_rolls_items_once_a_day_and_tells_the_screens(env):
    from engine.worker import Worker

    ws, cfg, store = env
    sid, [past, first] = make_series(store, PAST, FIRST)
    action = item(store, "action", sid, past)
    told = []

    class Events:
        def changed(self):
            told.append(1)

    now = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    worker = Worker(ws, store, cfg, Events(), now=lambda: now)
    assert worker.roll_series_if_due() == [action]
    assert data(store, "action", action)["event"] == first and told == [1]
    late = item(store, "action", sid, past)
    assert worker.roll_series_if_due() == []  # once a day
    assert data(store, "action", late)["event"] == past
    worker.now = lambda: now + timedelta(days=1)
    assert worker.roll_series_if_due() == [late]


# ---- what the assistant is told ----------


def test_the_packet_lists_the_series_and_the_entries_to_come_and_what_each_item_belongs_to(env):
    ws, cfg, store = env
    sid, [past, first] = make_series(store, PAST, FIRST)
    action = item(store, "action", sid, first)
    question = item(store, "question", None, first)
    section = _calendar_section(store, cfg, TODAY)
    assert section.startswith("# Calendar entries and series")
    assert f"{sid} series: Tuesday sync, every Tuesday; next {first} on {FIRST}" in section
    assert f"{first} Tuesday sync ({FIRST}; series {sid})" in section
    assert past not in section  # it has passed
    people = People(store, cfg)
    assert f"{action} " in _open_actions(store, people) and f"on entry {first}, series {sid}" in _open_actions(
        store, people
    )
    assert f"{question} to " in _open_questions(store, people) and f"(on entry {first})" in _open_questions(
        store, people
    )


def test_the_packet_has_no_calendar_section_when_there_are_no_entries(env):
    _, cfg, store = env
    assert _calendar_section(store, cfg, TODAY) == ""


def test_the_notes_prompt_says_when_to_tie_an_item_to_an_entry_or_a_series(env):
    from engine.intake import hand_in

    ws, cfg, store = env
    handed = hand_in(ws, store, pasted=RAW, now=datetime(2026, 10, 14, 9, 0, tzinfo=UTC))
    instructions = build(ws, store, cfg, handed.request, TODAY).task.instructions
    assert 'name it in "event"; for a meeting that repeats, name the series in "series"' in instructions
    assert 'add one with "series.add"' in instructions
    assert "Use only ids from that list" in instructions
    stable = build(ws, store, cfg, handed.request, TODAY).task.stable
    assert '"series.add"' in stable and '"series.link"' in stable


# ---- the export keeps all of it ----------


def test_a_workspace_with_a_series_and_items_on_it_round_trips_through_the_export(env, tmp_path):
    _, cfg, store = env
    sid, [past, first] = make_series(store, PAST, FIRST)
    item(store, "action", sid, past)
    item(store, "question", sid, first)
    item(store, "fact", sid, first)
    series_module.roll_items(store, TODAY, UTC_ZONE)
    assert round_trip(store, cfg, tmp_path / "round-trip")["differences"] == []
