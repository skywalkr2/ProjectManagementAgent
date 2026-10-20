"""The demo shows what the designer's answers 27 to 31 describe (the UI/UX re-review, batch B-7, C53): a moved meeting
with the questions asked after it, held lines with their verbs, an inferred fact with where it came from, a meeting
series with its page, a rules line with "Not now", and a meeting with an agenda item. Each loads a fictional workspace
and finds its record in the state the screen reads. Names and ids come from the fixtures, which carry the history
the app made (`ledger.jsonl`), so the round trip holds."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from engine import follow_on
from engine.record_page import fact_source
from engine.record_page import page as record_page
from engine.rule_review import due as rule_review_due
from engine.rule_review import review as rule_review
from engine.series_page import page as series_page
from engine.storage import Store
from engine.today import agenda as todays_agenda
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import fixture_records as base_records
from tests.roundtrip import round_trip

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
WORDING = json.loads((Path(__file__).parents[1] / "web" / "src" / "wording" / "en.json").read_text(encoding="utf-8"))


@pytest.fixture
def env(tmp_path, demo):
    ws = init_workspace(tmp_path / "ws", template=demo, git=False, history=True)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store, demo
    store.close()


def fixture_records(demo: Path, kind: str) -> list[dict]:
    """The records of a kind in the demo's history, as the export holds them."""
    path = demo / "history" / "data" / f"{kind}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def by_id(demo: Path, kind: str) -> dict[str, dict]:
    return {r["id"]: r for r in fixture_records(demo, kind)}


def lines(env, kind: str):
    ws, cfg, store, _ = env
    return [line for line in queue(ws, store, cfg, NOW) if line.kind == kind]


def test_only_the_demo_opens_on_the_history_and_the_starting_records_stay_as_they_were(tmp_path, demo):
    plain = init_workspace(tmp_path / "plain", template=demo, git=False)
    store = Store(plain.db_path, cfg=plain.config(env={}))
    try:
        for kind in ("event", "series", "fact", "rule", "request", "changeset", "run", "source"):
            assert store.read().list(kind) == []
    finally:
        store.close()
    assert not (plain.root / "sources").exists() or not any((plain.root / "sources").iterdir())
    assert {r["id"] for r in base_records(demo, "action")} < {r["id"] for r in fixture_records(demo, "action")}


def test_the_demo_history_round_trips_through_the_export(env, tmp_path):
    _, cfg, store, _ = env
    assert round_trip(store, cfg, tmp_path / "round")["differences"] == []


def test_a_moved_meeting_is_one_group_under_the_move_with_a_row_for_each_question_to_the_person(env):
    _, cfg, store, demo = env
    events, actions, people = by_id(demo, "event"), by_id(demo, "action"), by_id(demo, "person")
    request = next(r for r in fixture_records(demo, "request") if r["task"] == follow_on.TASK)
    (move,) = follow_on.moves_of(store.read(), request["follows"])
    moved = events[move.record]
    (group,) = lines(env, "moved")
    assert group.group == "decide" and group.count == 2 and len(group.questions) == 2
    assert group.text == moved["title"] and group.due == moved["start"][:10]
    assert group.after_move["record"] == move.record and group.after_move["by"] == "pm"
    assert {row["check"]["kind"] for row in group.after_move["rows"]} == {"date", "plan"}
    told = next(a for a in actions.values() if a.get("event") == move.record and a.get("told"))
    assert group.after_move["others"] == [people[next(iter(told["told"]))]["full_name"]]
    assert cfg.workspace.user.person != next(iter(told["told"]))  # that question is someone else's, left to Follow-ups
    assert WORDING["queue.moved"] and WORDING["queue.moved.checks.other"]


def test_held_lines_ask_to_close_and_to_drop_each_with_the_words_it_rests_on(env):
    ws, cfg, store, demo = env
    actions, people = by_id(demo, "action"), by_id(demo, "person")
    held = [
        op["op"] | {"status": op["status"]}
        for changeset in fixture_records(demo, "changeset")
        for op in changeset["ops"]
        if op["status"] == "held"
    ]
    assert {op["op"] for op in held} == {"action.close", "action.drop"}
    shown = {line.held["ask"]: line.held for line in lines(env, "held")}
    assert set(shown) == {"close", "drop"}
    close = next(op for op in held if op["op"] == "action.close")
    drop = next(op for op in held if op["op"] == "action.drop")
    assert shown["close"]["item"] == actions[close["id"]]["text"]
    assert shown["close"]["quote"] == close["evidence"]["quote"]
    assert shown["drop"]["item"] == actions[drop["id"]]["text"]
    assert sorted(shown["drop"]["told"]) == sorted(people[p]["full_name"] for p in actions[drop["id"]]["told"])
    for key in ("queue.held.a.close", "queue.held.k.close", "queue.held.a.drop"):
        assert WORDING[key]  # the three verbs: Close it, Keep it open, Drop it


def test_an_inferred_fact_says_who_it_rests_on_and_links_to_the_input_it_came_from(env):
    _, _, store, demo = env
    people, sources = by_id(demo, "person"), by_id(demo, "source")
    fact = next(f for f in fixture_records(demo, "fact") if f["basis"] == "inferred")
    shown = fact_source(store.read(), store.read().get("fact", fact["id"]))
    assert shown["basis"] == "inferred" and shown["kind"] == "email"
    assert shown["sender"] == people[sources[fact["source"]]["author"]]["full_name"]
    assert shown["origin"] == {"kind": "source", "source": fact["source"]}
    assert "title" not in shown and sources[fact["source"]]["title"] not in json.dumps(shown)  # never the raw title
    assert WORDING["fact.src.inferred"] and WORDING["fact.confirm"]


def test_a_series_has_a_page_with_its_next_meeting_what_rolled_to_it_and_the_meetings_that_passed(env):
    _, cfg, store, demo = env
    series, events, people, actions = (
        fixture_records(demo, "series")[0],
        by_id(demo, "event"),
        by_id(demo, "person"),
        by_id(demo, "action"),
    )
    here = ZoneInfo(cfg.workspace.user.timezone)
    shown = series_page(store.read(), series["id"], NOW.astimezone(here).date(), here, pm=cfg.workspace.user.person)
    assert shown["title"] == series["title"] and shown["repeats"] == series["repeats"]
    assert shown["next"]["open"] >= 3 and shown["next"]["groups"][-1]["is_pm"]  # the person last, as "You"
    rolled = [i for g in shown["next"]["groups"] for i in g["items"] if i["rolled_from"]]
    assert [i["text"] for i in rolled] and rolled[0]["rolled_from"]["title"] == series["title"]
    (past,) = shown["past"]
    assert len(past["settled"]) == 1 and len(past["moved"]) == 1 and past["moved"][0]["to"]["id"] == shown["next"]["id"]
    guests = {g["person"] for e in events.values() if e.get("series") == series["id"] for g in e.get("attendees", [])}
    assert {p["person"] for p in shown["usually_with"]} == guests
    assert {p["name"] for p in shown["usually_with"]} == {people[g]["full_name"] for g in guests}
    assert rolled[0]["id"] in actions


def test_the_rules_review_line_offers_three_rules_the_assistant_never_used_and_not_now_is_in_its_menu(env):
    _, cfg, store, demo = env
    rules = fixture_records(demo, "rule")
    (line,) = lines(env, "rule_review")
    assert line.count == len(rules) == 3 and sorted(line.rules) == sorted(r["id"] for r in rules)
    found = rule_review(store.read(), cfg.dispatch.knowledge, NOW)
    assert [f.present for f in found.flagged] and all(f.applied == 0 for f in found.flagged)
    assert rule_review_due(store.read(), cfg.dispatch.knowledge, NOW, found)
    assert WORDING["queue.rule_review.not_now"] == "Not now" and WORDING["queue.rule_review.not_now_back"]


def test_a_meeting_has_an_agenda_item_linked_to_the_action_that_was_called_off_into_it(env):
    _, cfg, store, demo = env
    here = ZoneInfo(cfg.workspace.user.timezone)
    people, actions = by_id(demo, "person"), by_id(demo, "action")
    on_agenda = next(e for e in fixture_records(demo, "event") if e.get("agenda"))
    (item,) = on_agenda["agenda"]
    called_off = actions[item["action"]]
    assert called_off["status"] == "dropped" and item["text"] == called_off["text"]
    page = record_page(store, "event", on_agenda["id"], pm=cfg.workspace.user.person, today=NOW.date(), here=here)
    shown = next(a for a in page["agenda"] if a["id"] == item["action"])
    assert (
        shown["text"] == called_off["text"] and shown["added_by_name"] == people[cfg.workspace.user.person]["full_name"]
    )
    assert not any(row["field"] == "agenda" for row in page["details"])
    today = [
        r for r in todays_agenda(store, cfg, NOW, through=NOW.date().replace(day=30)) if r.snapshot == on_agenda["id"]
    ]
    assert item["action"] in [a["id"] for a in today[0].agenda]
