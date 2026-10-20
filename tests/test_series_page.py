"""A series' page (design 7.14): the next meeting with what is open for it by person (the person last), the meetings
that passed as one line each of what was settled and what moved, and where a rolled item came from. Names and ids come
from the fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine import series as series_module
from engine.series_page import page
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

_PM = WriteContext("pm", "trusted", "test")
HERE = ZoneInfo("UTC")
TODAY = date(2026, 10, 14)
PAST, FIRST, SECOND = "2026-10-06", "2026-10-20", "2026-10-27"
PEOPLE = fixture_records(DEMO_B, "person")
ME, OTHER = PEOPLE[0]["id"], PEOPLE[1]["id"]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    store = Store(ws.db_path, cfg=ws.config(env={}))
    yield store
    store.close()


def meeting(store, start, series):
    with store.transaction() as tx:
        return tx.create("event", {"title": "Print sync", "start": start, "series": series, "trust": "trusted"}, _PM).id


def action(store, series, event=None, owner=OTHER, **more):
    with store.transaction() as tx:
        return tx.create(
            "action",
            {"text": "Send the interior file", "owners": [{"person": owner}], "series": series, "event": event, **more},
            _PM,
        ).id


@pytest.fixture
def made(env):
    store = env
    with store.transaction() as tx:
        sid = tx.create("series", {"title": "Print sync", "repeats": "every Thursday", "trust": "trusted"}, _PM).id
    return store, sid, [meeting(store, s, sid) for s in (PAST, FIRST, SECOND)]


def shown(store, sid):
    return page(store.read(), sid, TODAY, HERE, pm=ME)


def test_the_next_meeting_lists_what_is_open_by_person_with_the_person_last(made):
    store, sid, (_, first, _) = made
    theirs = action(store, sid, first, owner=OTHER)
    mine = action(store, sid, first, owner=ME, text="Check the cover proof")
    view = shown(store, sid)
    assert view["next"]["id"] == first and view["next"]["open"] == 2
    assert [g["person"] for g in view["next"]["groups"]] == [OTHER, ME]
    assert [g["is_pm"] for g in view["next"]["groups"]] == [False, True]
    assert [i["id"] for g in view["next"]["groups"] for i in g["items"]] == [theirs, mine]
    assert view["title"] == "Print sync" and view["repeats"] == "every Thursday"


def test_an_item_that_rolled_says_which_meeting_it_came_from_and_the_old_meeting_counts_it_as_moved(made):
    store, sid, (past, first, _) = made
    rolled = action(store, sid, past)
    done = action(store, sid, past, text="Already finished")
    with store.transaction() as tx:
        tx.update("action", done, {"status": "done", "done_by": [OTHER]}, _PM, read_version=1)
    series_module.roll_items(store, TODAY, HERE)
    view = shown(store, sid)
    item = view["next"]["groups"][0]["items"][0]
    assert item["id"] == rolled and item["rolled_from"]["id"] == past and item["rolled_from"]["on"] == PAST
    [old] = view["past"]
    assert old["id"] == past
    assert [i["id"] for i in old["settled"]] == [done]
    assert [i["id"] for i in old["moved"]] == [rolled] and old["moved"][0]["to"]["id"] == first


def test_a_series_with_nothing_open_has_a_next_meeting_and_no_groups(made):
    store, sid, (_, first, _) = made
    view = shown(store, sid)
    assert view["next"]["id"] == first and view["next"]["groups"] == [] and view["next"]["open"] == 0


def test_a_series_with_no_later_meeting_says_how_many_wait(env):
    store = env
    with store.transaction() as tx:
        sid = tx.create("series", {"title": "Print sync", "trust": "trusted"}, _PM).id
    meeting(store, PAST, sid)
    action(store, sid, None)
    view = shown(store, sid)
    assert view["next"] is None and view["open_without_next"] == 1


def test_an_unknown_series_has_no_page(env):
    assert shown(env, "SER-999") is None


def test_the_route_returns_the_page(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    app = create_app(ws, ws.config(env={}, flags={"server.base_path": "/"}), "t", ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": "Bearer t"}) as client:
        with app.state.store.transaction() as tx:
            sid = tx.create("series", {"title": "Print sync", "repeats": "every Thursday", "trust": "trusted"}, _PM).id
        found = client.get(f"/api/series/{sid}/page")
        assert found.status_code == 200
        assert found.json()["title"] == "Print sync" and found.json()["next"] is None
        assert found.json()["usually_with"] == []
        assert client.get("/api/series/SER-999/page").status_code == 404


def test_a_meeting_on_todays_agenda_counts_what_is_open_for_it(made):
    from engine import today

    store, sid, (_, first, second) = made
    action(store, sid, first)
    action(store, sid, second)
    cfg = store.plugins.cfg
    when = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    mine = {a.snapshot: a for a in today.agenda(store, cfg, when)}
    assert mine[first].series == sid and mine[first].open_items == 1


# ---- usually with (design 7.14, answer 30) ------------------------------------------------------------------------


def guests(store, entry, *who, organizer=None, **by_response):
    """Give a meeting its guest list: each person in `who` is on it; `by_response` maps a person to their answer."""
    listed = [{"person": p, "response": by_response.get(p)} for p in who]
    fields = {"attendees": listed, **({"organizer": {"person": organizer}} if organizer else {})}
    with store.transaction() as tx:
        tx.update("event", entry, fields, _PM, read_version=store.read().get("event", entry).version)


def regulars(store, sid, **settings):
    from engine.config.schema import SeriesSettings

    view = page(store.read(), sid, TODAY, HERE, pm=ME, settings=SeriesSettings(**settings))
    return [(r["person"], r["meetings"], r["of"]) for r in view["usually_with"]]


def test_the_people_on_most_of_the_meetings_are_who_the_series_is_usually_with_and_the_person_is_left_out(made):
    store, sid, entries = made
    third = PEOPLE[2]["id"]
    guests(store, entries[0], ME, OTHER, third)
    guests(store, entries[1], ME, OTHER)
    guests(store, entries[2], ME, OTHER, third)
    # the one who is on all of them first, then the one on two of three; the person themselves is never listed
    assert regulars(store, sid) == [(OTHER, 3, 3), (third, 2, 3)]
    view = shown(store, sid)
    assert [r["name"] for r in view["usually_with"]] == [PEOPLE[1]["full_name"], PEOPLE[2]["full_name"]]


def test_the_share_the_least_known_lists_and_the_longest_list_are_settings(made):
    store, sid, entries = made
    third = PEOPLE[2]["id"]
    guests(store, entries[0], OTHER, third)
    guests(store, entries[1], OTHER)
    guests(store, entries[2], OTHER)
    assert regulars(store, sid) == [(OTHER, 3, 3)]
    assert regulars(store, sid, usually_with_share=0.3) == [(OTHER, 3, 3), (third, 1, 3)]
    assert regulars(store, sid, usually_with_share=0.3, usually_with_max=1) == [(OTHER, 3, 3)]
    assert regulars(store, sid, usually_with_min_meetings=4) == []


def test_a_guest_who_declined_is_not_on_the_meeting_and_one_with_no_person_is_not_counted(made):
    store, sid, entries = made
    for entry in entries:
        guests(store, entry, OTHER, **{OTHER: "declined"})
    assert regulars(store, sid) == []
    with store.transaction() as tx:
        for entry in entries:
            tx.update(
                "event",
                entry,
                {"attendees": [{"address": "visitor@example.com", "name": "A Visitor"}]},
                _PM,
                read_version=store.read().get("event", entry).version,
            )
    assert regulars(store, sid) == []


def test_meetings_without_a_guest_list_or_called_off_are_not_counted_either_way(made):
    store, sid, entries = made
    guests(store, entries[0], OTHER)
    guests(store, entries[1], OTHER)
    # the third has no list, so two of two known lists say OTHER is regular
    assert regulars(store, sid) == [(OTHER, 2, 2)]
    guests(store, entries[2], ME)
    with store.transaction() as tx:
        tx.update(
            "event", entries[2], {"cancelled": True}, _PM, read_version=store.read().get("event", entries[2]).version
        )
    assert regulars(store, sid) == [(OTHER, 2, 2)]


def test_the_organizer_counts_as_being_on_the_meeting(made):
    store, sid, entries = made
    for entry in entries:
        guests(store, entry, ME, organizer=OTHER)
    assert regulars(store, sid) == [(OTHER, 3, 3)]


def test_a_series_with_no_guest_lists_has_nobody_it_is_usually_with(made):
    store, sid, _ = made
    assert shown(store, sid)["usually_with"] == []
