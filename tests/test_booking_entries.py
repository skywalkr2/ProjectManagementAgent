"""Calendar entries from booking confirmations (design 6.32, "What arrives", S4).

A booking an input carries as structured data (`engine/bookings.py`, fictional samples in `tests/fixtures/bookings/`)
becomes an entry in the app's own calendar by rules, with the confirmation's words as its evidence, and nothing is sent
to any calendar service. The assistant's own reading of the same input adds no second entry. Names come from the
fixtures; the AI is the stub."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import booking_entries
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import process
from engine.intake import hand_in
from engine.ops import CHANGESET
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, without_first_go

FIXTURES = Path(__file__).parent / "fixtures" / "bookings"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def answer(*ops: dict) -> None:
    set_responder(lambda task: json.dumps({"summary": "Read the confirmation.", "ops": list(ops)}))


def run(env, html: str):
    ws, cfg, store = env
    handed = hand_in(ws, store, pasted=html, cfg=cfg)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    return handed, cs_id


def test_a_flight_confirmation_makes_a_calendar_entry_with_its_evidence_and_sends_nothing(env):
    _, _, store = env
    answer()
    _, cs_id = run(env, read("flight_jsonld.html"))
    (entry,) = store.read().list("event")
    assert entry.data["title"] == "Flight: Alderfield Airport to Briarford Airport"
    assert entry.data["start"] == "2026-11-20T09:00:00-05:00" and entry.data["end"] == "2026-11-20T11:00:00-05:00"
    assert entry.data["evidence"]["quote"] == "R-0042"
    assert entry.data["trust"] == "untrusted"  # it came from outside content
    ops = store.read().get("changeset", cs_id).data["ops"]
    assert [o["op"]["op"] for o in ops] == ["event.add"] and ops[0]["status"] == "applied"
    assert not store.read().list("act")  # a local entry is no act: nothing goes to a calendar service


@pytest.mark.parametrize(
    "name, title",
    [
        ("lodging_jsonld.html", "Stay: Willow Rest"),
        ("train_jsonld.html", "Train: Mossgate Station to Fern End Station"),
        ("restaurant_jsonld.html", "Table: The Paper Finch"),
        ("rental_car_jsonld.html", "Rental car: Larkway Depot to Briar Depot"),
        ("event_jsonld.html", "Event: Alder Hall"),
        ("flight_microdata.html", "Flight: Alderfield Airport to Briarford Airport"),
    ],
)
def test_each_kind_of_booking_makes_one_entry_titled_by_its_kind_and_place(env, name, title):
    _, cfg, _ = env
    made = booking_entries.entries(cfg, read(name))
    assert [op["title"] for op in made.ops] == [title], made.skipped
    assert made.ops[0]["evidence"]["quote"] in read(name)


def test_the_assistants_own_entry_for_the_same_booking_is_not_added_twice(env):
    _, _, store = env
    answer(
        {
            "op": "event.add",
            "title": "Flight to Briarford",
            "start": "2026-11-20T09:00:00-05:00",
            "evidence": {"quote": "Alderfield Airport"},
        }
    )
    _, cs_id = run(env, read("flight_jsonld.html"))
    assert len(store.read().list("event")) == 1
    assert [o["op"]["title"] for o in store.read().get("changeset", cs_id).data["ops"]] == [
        "Flight: Alderfield Airport to Briarford Airport"
    ]


def test_the_same_confirmation_handed_in_again_makes_no_second_entry(env):
    _, _, store = env
    answer()
    run(env, read("flight_jsonld.html"))
    run(env, read("flight_jsonld.html") + "<!-- again -->")
    assert len(store.read().list("event")) == 1


def test_a_booking_with_no_words_to_quote_or_no_start_makes_no_entry_and_says_so(env):
    _, cfg, _ = env
    html = (
        read("flight_jsonld.html").replace("R-0042", "").replace("Larkway Travel", "").replace("Alderfield Airport", "")
    )
    html = html.replace('"reservationId": ""', '"reservationId": null')
    made = booking_entries.entries(cfg, html)
    assert made.ops == () and any("nothing in the confirmation to quote" in s for s in made.skipped)
    no_start = read("flight_jsonld.html").replace("2026-11-20T09:00:00-05:00", "")
    made = booking_entries.entries(cfg, no_start)
    assert made.ops == () and made.skipped


def test_what_could_not_be_made_is_listed_with_what_the_run_lacked(env):
    _, cfg, store = env
    answer()
    html = read("flight_jsonld.html").replace("2026-11-20T09:00:00-05:00", "")
    _, cs_id = run(env, html)
    assert not store.read().list("event")
    assert any("no start" in m for m in store.read().get("changeset", cs_id).data.get("missing", []))


def test_plain_mail_is_never_parsed_and_the_setting_turns_the_entries_off(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__STEWARD__DATES__BOOKINGS_TO_CALENDAR": "false"})
    assert booking_entries.entries(cfg, read("flight_jsonld.html")).ops == ()
    on = ws.config(env={})
    assert booking_entries.entries(on, "Your flight is confirmed for November 20.").ops == ()


def test_the_changeset_is_returned_unchanged_when_there_is_no_booking(env):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": []}, context={"op_models": store.plugins.ops})
    assert booking_entries.add_to(cs, cfg, store.read(), "no markup here") is cs
