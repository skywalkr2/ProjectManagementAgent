"""The app's own calendar: `event.add` records a dated item from what came in, undo removes it, and the agenda lists
the entries after the connected calendars' events, on every day they cover."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, check
from engine.dispatcher import process, undo_changeset
from engine.evaluate import evaluate
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET, OP_MODELS
from engine.storage import Store, WriteContext
from engine.today import agenda
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_PM = WriteContext("pm", "trusted", "test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def project_id() -> str:
    return fixture_records(DEMO_B, "project")[0]["id"]


def window_op(**more) -> dict:
    return {
        "op": "event.add",
        "title": "Printed bookmarks delivered",
        "start": "2026-10-20",
        "end": "2026-10-22",
        "evidence": {"quote": "Estimated delivery: Tuesday, October 20 - Thursday, October 22"},
        **more,
    }


MAIL = "Your order has shipped.\n\nEstimated delivery: Tuesday, October 20 - Thursday, October 22\n\nThank you."


def problems(env, op, text=MAIL):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), ("event.add",), Inputs("REQ-1", None, text, text, "untrusted"))
    return [p for p in check(cs, ctx) if p.severity == "refuse"]


def test_event_add_is_a_data_op_that_needs_evidence_and_readable_dates(env):
    assert "event.add" in OP_MODELS
    assert problems(env, window_op()) == []
    for bad in ({"start": "next Tuesday"}, {"end": "22/10"}, {"start": "2026-13-40"}):
        with pytest.raises(ValidationError):
            OP_MODELS["event.add"].model_validate(window_op(**bad))
    with pytest.raises(ValidationError):
        OP_MODELS["event.add"].model_validate({k: v for k, v in window_op().items() if k != "evidence"})
    no_evidence = {k: v for k, v in window_op().items() if k != "evidence"}
    with pytest.raises(ValidationError):
        CHANGESET.validate_python({"ops": [no_evidence]}, context={"op_models": env[2].plugins.ops})


def test_an_entry_that_ends_before_it_starts_or_quotes_words_not_in_the_input_is_refused(env):
    found = problems(env, window_op(start="2026-10-22", end="2026-10-20"))
    assert [p.check for p in found] == ["targets"] and "ends before it starts" in found[0].message
    # A date-time end on the start's own day is the same day, not before it.
    assert problems(env, window_op(start="2026-10-20T10:00:00+00:00", end="2026-10-20")) == []
    assert problems(env, window_op(start="2026-10-20T10:00:00+00:00", end="2026-10-20T09:00:00+00:00"))
    found = problems(env, window_op(evidence={"quote": "arrives sometime in October"}))
    assert [p.check for p in found] == ["evidence"]


def test_the_applier_creates_the_entry_with_its_words_and_undo_removes_it(env):
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"ops": [window_op(project=project_id())]}))
    handed = hand_in(ws, store, note="", pasted=MAIL, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    [entry] = store.read().list("event")
    assert entry.id.startswith("EVT-")
    assert entry.data["start"] == "2026-10-20" and entry.data["end"] == "2026-10-22"
    assert entry.data["project"] == project_id() and entry.data["trust"] == "untrusted"
    assert entry.data["evidence"]["quote"] == window_op()["evidence"]["quote"]
    report = undo_changeset(store, cs_id)
    assert report.restored == [0]
    assert store.read().list("event") == []
    assert len(store.read().list("event", include_deleted=True)) == 1


def seed(store, **entry):
    with store.transaction() as tx:
        return tx.create("event", {"trust": "trusted", **entry}, _PM).id


@pytest.mark.parametrize(
    ("written", "stored"),
    [
        ("2026-11-16T14:00Z", "2026-11-16T14:00:00+00:00"),
        ("2026-11-16T14:00:00Z", "2026-11-16T14:00:00+00:00"),
        ("2026-11-16T14:00+00:00", "2026-11-16T14:00:00+00:00"),
        ("2026-11-16T09:30", "2026-11-16T09:30:00"),
        (" 2026-11-16 ", "2026-11-16"),
    ],
)
def test_an_entrys_times_are_kept_in_one_form_however_they_were_written(env, written, stored):
    """The same moment is always the same text, so entries compare, sort and match as the moments they are."""
    _, _, store = env
    entry = store.read().get("event", seed(store, title="Walkthrough", start=written, end=written))
    assert entry.data["start"] == stored and entry.data["end"] == stored
    op = OP_MODELS["event.add"](op="event.add", title="Walkthrough", start=written, evidence={"quote": "on Monday"})
    assert op.start == stored


def test_the_agenda_lists_an_entry_on_each_day_of_its_range_after_the_calendar_events(env):
    _, cfg, store = env
    cfg.ui.today.agenda_days_ahead = 4
    first = TODAY + timedelta(days=1)
    seed(store, title="Delivery window", start=first.isoformat(), end=(first + timedelta(days=2)).isoformat())
    seed(store, title="Launch party", start=f"{TODAY.isoformat()}T18:30:00+00:00")
    seed(store, title="Far away", start=(TODAY + timedelta(days=30)).isoformat())
    seed(store, title="Long past", start="2026-01-01", end="2026-01-05")
    found = agenda(store, cfg, NOW)
    by_title = {a.title: a for a in found}
    assert set(by_title) == {"Delivery window", "Launch party"}
    window = by_title["Delivery window"]
    assert window.own and window.all_day and window.where is None and window.link is None
    assert window.days == [first, first + timedelta(days=1), first + timedelta(days=2)]
    assert window.snapshot.startswith("EVT-") and window.start == first.isoformat()
    party = by_title["Launch party"]
    assert (
        party.own
        and not party.all_day
        and party.days == [TODAY]
        and party.start.startswith(f"{TODAY.isoformat()}T18:30")
    )


def test_own_entries_follow_the_connected_events_and_a_removed_entry_is_gone(env):
    _, cfg, store = env
    entry = seed(store, title="Own", start=TODAY.isoformat())
    with store.transaction() as tx:
        tx.create(
            "snapshot",
            {
                "source": "s",
                "key": "k",
                "title": "Connected",
                "content_hash": "h",
                "seen_at": NOW.isoformat(),
                "event": {"start": f"{TODAY}T09:00:00+00:00"},
            },
            _PM,
        )
    [first, second] = agenda(store, cfg, NOW)
    assert (first.title, first.own, second.title, second.own) == ("Connected", False, "Own", True)
    with store.transaction() as tx:
        tx.delete("event", entry, _PM, read_version=1)
    assert [a.title for a in agenda(store, cfg, NOW)] == ["Connected"]


def test_the_agenda_route_marks_an_own_entry(env, tmp_path):
    ws, cfg, store = env
    from engine.today import zone

    today = datetime.now(zone(cfg)).date()
    seed(store, title="Delivery window", start=today.isoformat(), end=(today + timedelta(days=1)).isoformat())
    store.close()
    client = TestClient(create_app(ws, cfg, "t", start_worker=False))
    client.headers["Authorization"] = "Bearer t"
    [item] = client.get(cfg.server.base_path.rstrip("/") + "/api/today/agenda").json()
    assert item["own"] is True and item["all_day"] is True and len(item["days"]) == 2


def test_a_workspace_with_an_entry_round_trips_through_the_export(env, tmp_path):
    _, cfg, store = env
    seed(store, title="Delivery window", start="2026-10-20", end="2026-10-22", project=project_id())
    assert round_trip(store, cfg, tmp_path / "round-trip")["differences"] == []


def test_the_delivery_window_case_gives_the_fact_and_an_entry_spanning_it():
    report = evaluate(DEMO_B, stub=True, env={}, only=["delivery-window"])
    assert [(r.case, r.passed, r.missing, r.forbidden) for r in report.results] == [("delivery-window", True, [], [])]
