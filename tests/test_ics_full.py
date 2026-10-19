"""Calendars from .ics, full featured (design 6.2, 6.32): a link or a file on this computer, repeating events expanded
over a window that is a setting, invitations and their attendees kept on calendar entries, Windows time zone names, and
a changed or cancelled occurrence touching only that occurrence. Read through the connector and through a source's
read, with no network and no AI."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from engine.config import load_config
from engine.connectors import ConnectorContext, ConnectorError, EventDetails, checked_poll
from engine.connectors.calendar import CalendarSettings, read_calendar
from engine.storage import Store, WriteContext
from engine.today import agenda
from engine.watch import refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

ICS = Path(__file__).parent / "fixtures" / "ics"
NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
ZONE = "America/New_York"
_TEST = WriteContext("pm", "trusted", "test")

PEOPLE = fixture_records(DEMO_B, "person")
ME = PEOPLE[0]  # the person running the app (workspace.user.person)
ORGANIZER = next(p for p in PEOPLE if (p.get("how_to_reach") or {}).get("email"))  # known by address in the fixtures
ME_ADDRESS = ME["full_name"].lower().replace(" ", ".") + "@example.com"
ORGANIZER_ADDRESS = ORGANIZER["how_to_reach"]["email"]


def text_of(name: str) -> str:
    return (
        (ICS / name)
        .read_text()
        .replace("@@ME_NAME@@", ME["full_name"])
        .replace("@@ME_ADDRESS@@", ME_ADDRESS)
        .replace("@@ORGANIZER_NAME@@", ORGANIZER["full_name"])
        .replace("@@ORGANIZER_ADDRESS@@", ORGANIZER_ADDRESS)
    )


def context(tmp_path, **more):
    return ConnectorContext(tmp_path, now=NOW, timezone=ZONE, **more)


def read(tmp_path, name_or_text, **settings):
    """A file's items through the connector, as it reads a file on this computer."""
    path = tmp_path / "calendar.ics"
    path.write_text(text_of(name_or_text) if name_or_text.endswith(".ics") else name_or_text)
    poll = read_calendar(CalendarSettings(file=str(path), **settings), {}, context(tmp_path))
    checked_poll(poll)
    return {i.key: i for i in poll.items}


def starts(item):
    return [o.start for o in item.event.occurrences]


# ---- a link and a file ---------------------------------------------------------------------------------------------


def test_a_file_on_this_computer_is_read_and_read_again_when_it_changes(tmp_path):
    path = tmp_path / "work.ics"
    path.write_text(text_of("invitation.ics"))
    settings = CalendarSettings(file=str(path))
    first = read_calendar(settings, {}, context(tmp_path))
    (item,) = first.items
    assert item.title == "Floor plan walkthrough" and item.event.where == "Main hall"
    assert first.complete is False and first.state["modified"]
    path.write_text(path.read_text().replace("Floor plan walkthrough", "Floor plan walkthrough, second round"))
    again = read_calendar(settings, first.state, context(tmp_path))
    assert again.items[0].title.endswith("second round") and again.items[0].key == item.key
    assert again.items[0].text != item.text


def test_a_link_or_a_file_is_needed_and_not_both():
    with pytest.raises(ValueError, match="link or a file"):
        CalendarSettings()
    with pytest.raises(ValueError, match="link or a file"):
        CalendarSettings(address="env:CAL_ADDRESS", file="/somewhere/work.ics")
    assert CalendarSettings(address="env:CAL_ADDRESS").file == ""
    assert CalendarSettings(file="/somewhere/work.ics").address == ""


def test_a_file_that_is_missing_or_not_a_calendar_says_so(tmp_path):
    with pytest.raises(ConnectorError) as missing:
        read_calendar(CalendarSettings(file=str(tmp_path / "gone.ics")), {}, context(tmp_path))
    assert missing.value.kind == "not_found"
    (tmp_path / "note.ics").write_text("Just a note")
    with pytest.raises(ConnectorError) as wrong:
        read_calendar(CalendarSettings(file=str(tmp_path / "note.ics")), {}, context(tmp_path))
    assert wrong.value.kind == "no_access" and "doesn't hold a calendar" in wrong.value.detail
    (tmp_path / "big.ics").write_text("BEGIN:VCALENDAR\n" + "X-NOTE:" + "a" * 2048 + "\nEND:VCALENDAR\n")
    with pytest.raises(ConnectorError) as large:
        read_calendar(CalendarSettings(file=str(tmp_path / "big.ics"), max_kb=1), {}, context(tmp_path))
    assert large.value.kind == "no_access" and "larger than" in large.value.detail


def test_a_hosted_app_refuses_a_file_on_a_computer_plainly(tmp_path):
    (tmp_path / "work.ics").write_text(text_of("invitation.ics"))
    with pytest.raises(ConnectorError) as refused:
        read_calendar(CalendarSettings(file=str(tmp_path / "work.ics")), {}, context(tmp_path, hosted=True))
    assert refused.value.kind == "no_access" and "link" in refused.value.detail


# ---- repeating events -----------------------------------------------------------------------------------------------


def test_a_weekly_series_is_expanded_with_its_moved_occurrence_and_its_skipped_date(tmp_path):
    found = read(tmp_path, "weekly-series.ics")
    (series,) = found.values()  # the changed occurrence is part of its series, not an item of its own
    assert series.key == "series-1@calendar.example.com" and series.event.repeats.startswith("FREQ=WEEKLY")
    assert starts(series) == [
        "2030-03-04T09:00:00+00:00",
        "2030-03-12T14:00:00+00:00",  # the 11th, moved
        "2030-03-25T09:00:00+00:00",  # the 18th is skipped
        "2030-04-01T09:00:00+00:00",
        "2030-04-08T09:00:00+00:00",
    ]
    moved = series.event.occurrences[1]
    assert (moved.was, moved.title, moved.where) == ("2030-03-11T09:00:00+00:00", "Harbor stand-up (moved)", "Room 5")
    assert moved.end == "2030-03-12T15:00:00+00:00" and not moved.cancelled
    assert series.event.start == "2030-03-04T09:00:00+00:00" and series.event.end == "2030-03-04T10:00:00+00:00"
    assert "Repeats: " in series.text and "2030-03-18" not in series.text


def test_a_date_moved_beyond_the_window_is_still_that_date_and_not_a_skipped_one(tmp_path):
    far = text_of("weekly-series.ics").replace("DTSTART:20300312T140000Z", "DTSTART:20300820T140000Z")
    far = far.replace("DTEND:20300312T150000Z", "DTEND:20300820T150000Z")
    (series,) = read(tmp_path, far, expand_days=60).values()
    assert [o.start for o in series.event.occurrences][:3] == [
        "2030-03-04T09:00:00+00:00",
        "2030-03-25T09:00:00+00:00",
        "2030-04-01T09:00:00+00:00",
    ]
    moved = series.event.occurrences[-1]
    assert (moved.start, moved.was) == ("2030-08-20T14:00:00+00:00", "2030-03-11T09:00:00+00:00")


def test_the_window_repeats_are_expanded_over_is_a_setting(tmp_path):
    short = read(tmp_path, "weekly-series.ics", expand_days=10)
    (series,) = short.values()
    assert starts(series) == ["2030-03-04T09:00:00+00:00", "2030-03-12T14:00:00+00:00"]
    assert CalendarSettings(file="/somewhere/work.ics").expand_days == 60
    long = read(tmp_path, "weekly-series.ics", expand_days=366)
    assert len(starts(next(iter(long.values())))) == 5  # the rule's own count ends it


def test_an_unsupported_rule_part_shows_the_first_date_with_a_note(tmp_path):
    (item,) = read(tmp_path, "unsupported-rule.ics").values()
    assert item.title == "Tide table review" and item.event.start == "2030-03-06T09:00:00+00:00"
    assert [o.start for o in item.event.occurrences] == ["2030-03-06T09:00:00+00:00"]
    assert len(item.event.notes) == 1 and "first date" in item.event.notes[0]
    assert "first date" in item.text


# ---- changed and cancelled occurrences -------------------------------------------------------------------------------


def test_a_cancelled_occurrence_is_marked_and_the_others_stay(tmp_path):
    found = read(tmp_path, "cancelled-occurrence.ics")
    series = found["midweek-1@calendar.example.com"]
    assert [(o.start, o.cancelled) for o in series.event.occurrences] == [
        ("2030-03-06T10:00:00+00:00", False),
        ("2030-03-13T10:00:00+00:00", True),
        ("2030-03-20T10:00:00+00:00", False),
        ("2030-03-27T10:00:00+00:00", False),
    ]
    assert not series.event.cancelled
    called_off = found["one-off-1@calendar.example.com"]
    assert called_off.event.cancelled and "Status: CANCELLED" in called_off.text


# ---- time zones --------------------------------------------------------------------------------------------------


def test_windows_zone_names_are_read_in_their_iana_zone(tmp_path):
    found = read(tmp_path, "windows-zones.ics")
    pacific = found["pacific-1@calendar.example.com"].event
    assert (pacific.start, pacific.end) == ("2030-03-05T09:00:00-08:00", "2030-03-05T10:00:00-08:00")
    assert pacific.notes == ()


def test_a_zone_nobody_knows_is_read_in_the_calendars_default_zone_with_a_note(tmp_path):
    found = read(tmp_path, "windows-zones.ics")
    unknown = found["unknown-zone-1@calendar.example.com"].event
    assert unknown.start == "2030-03-06T10:00:00-05:00"  # the person's zone, since the calendar names none
    assert len(unknown.notes) == 1 and "Nowhere Standard Time" in unknown.notes[0]
    floating = found["floating-1@calendar.example.com"].event
    assert floating.start == "2030-03-07T08:00:00-05:00" and floating.notes == ()
    named = text_of("windows-zones.ics").replace("PRODID", "X-WR-TIMEZONE:Europe/Paris\nPRODID")
    own = read(tmp_path, named)["unknown-zone-1@calendar.example.com"].event
    assert own.start == "2030-03-06T10:00:00+01:00", "the calendar's own zone comes before the person's"


# ---- invitations and attendees -----------------------------------------------------------------------------------


def test_an_invitation_carries_who_invited_and_who_is_asked(tmp_path):
    (item,) = read(tmp_path, "invitation.ics").values()
    event = item.event
    assert event.method == "REQUEST" and event.entries
    assert (event.organizer.name, event.organizer.address) == (ORGANIZER["full_name"], ORGANIZER_ADDRESS)
    assert [(a.name, a.address, a.response) for a in event.attendees] == [
        (ORGANIZER["full_name"], ORGANIZER_ADDRESS, "accepted"),
        (ME["full_name"], ME_ADDRESS, "tentative"),
        ("Dara Keene", "dara.keene@example.com", "needs-action"),
    ]
    assert f"Organizer: {ORGANIZER['full_name']}" in item.text and "Dara Keene" in item.text


# ---- through a source's read -------------------------------------------------------------------------------------


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "work.ics"
    sources = [
        {
            "id": "calendar",
            "connector": "calendar",
            "label": "Work calendar",
            "first_run": "baseline",
            "settings": {"file": str(path), "days_ahead": 30, "expand_days": 60},
        }
    ]
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": sources}))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    with store.transaction() as tx:
        found = tx.get("person", ME["id"])
        reach = {**(found.data.get("how_to_reach") or {}), "email": ME_ADDRESS}
        tx.update("person", ME["id"], {"how_to_reach": reach}, _TEST, read_version=found.version)

    def put(name_or_text, at=NOW):
        path.write_text(text_of(name_or_text) if name_or_text.endswith(".ics") else name_or_text)
        return refresh(ws, store, cfg, "calendar", at)

    yield ws, cfg, store, put
    store.close()


def entries(store, **equals):
    found = store.read().find("event", {"source": "calendar", **equals})
    return sorted(found, key=lambda e: (e.data["start"], e.data["key"]))


def starts_of(store, **equals):
    return [e.data["start"] for e in entries(store, **equals)]


def promise_due_at(store, entry, due):
    """The first open promise in the fixtures, due at a calendar entry."""
    action = next(a for a in fixture_records(DEMO_B, "action") if a.get("status", "open") == "open")
    with store.transaction() as tx:
        current = tx.get("action", action["id"])
        tx.update("action", action["id"], {"due_event": entry.id, "due": due}, _TEST, read_version=current.version)
    return action["id"]


def action_data(store, action_id):
    return store.read().get("action", action_id).data


def test_every_occurrence_becomes_an_entry_of_one_series(source):
    ws, cfg, store, put = source
    put("weekly-series.ics")
    found = entries(store)
    assert [e.data["start"] for e in found] == [
        "2030-03-04T09:00:00+00:00",
        "2030-03-12T14:00:00+00:00",
        "2030-03-25T09:00:00+00:00",
        "2030-04-01T09:00:00+00:00",
        "2030-04-08T09:00:00+00:00",
    ]
    assert len({e.data["series"] for e in found}) == 1 and found[0].data["series"]
    assert store.read().get("series", found[0].data["series"]).data["title"] == "Harbor stand-up"
    moved = found[1].data
    assert moved["key"] == "series-1@calendar.example.com#2030-03-11T09:00:00+00:00"
    assert (moved["title"], moved["where"], moved["trust"]) == ("Harbor stand-up (moved)", "Room 5", "untrusted")
    assert found[0].data["title"] == "Harbor stand-up" and found[0].data["end"] == "2030-03-04T10:00:00+00:00"
    again = put("weekly-series.ics", NOW + timedelta(hours=1))
    assert [e.id for e in entries(store)] == [e.id for e in found], "a second read makes no second entry"
    assert again.new == [] and again.changed == []


def test_an_invitation_is_marked_with_who_invited_and_the_persons_own_answer(source):
    ws, cfg, store, put = source
    put("invitation.ics")
    (entry,) = entries(store)
    data = entry.data
    assert data["invitation"] is True and data["response"] == "tentative"
    assert data["organizer"]["person"] == ORGANIZER["id"] and data["organizer"]["name"] == ORGANIZER["full_name"]
    by_address = {a["address"]: a for a in data["attendees"]}
    assert by_address[ORGANIZER_ADDRESS]["person"] == ORGANIZER["id"]
    assert by_address[ME_ADDRESS]["person"] == ME["id"] and by_address[ME_ADDRESS]["response"] == "tentative"
    unknown = by_address["dara.keene@example.com"]
    assert unknown["person"] is None and unknown["name"] == "Dara Keene" and unknown["response"] == "needs-action"
    assert data["series"] is None and data["where"] == "Main hall"


def test_a_meeting_the_person_organizes_is_not_an_invitation(source):
    ws, cfg, store, put = source
    put("own-event.ics")
    (entry,) = entries(store)
    assert entry.data["invitation"] is False and entry.data["response"] == "accepted"
    assert len(entry.data["attendees"]) == 2


def test_a_promise_due_at_a_moved_occurrence_moves_with_it_and_one_due_at_another_stays(source):
    ws, cfg, store, put = source
    plain = text_of("weekly-series.ics").split("BEGIN:VEVENT\nUID:series-1@calendar.example.com\nDTSTAMP:20300302")[0]
    put(plain + "END:VCALENDAR\n")
    found = {e.data["start"]: e for e in entries(store)}
    eleventh, twenty_fifth = found["2030-03-11T09:00:00+00:00"], found["2030-03-25T09:00:00+00:00"]
    open_actions = [a for a in fixture_records(DEMO_B, "action") if a.get("status", "open") == "open"]
    assert len(open_actions) >= 2
    first, second = open_actions[0]["id"], open_actions[1]["id"]
    with store.transaction() as tx:
        for action_id, entry, due in ((first, eleventh, "2030-03-11"), (second, twenty_fifth, "2030-03-25")):
            current = tx.get("action", action_id)
            tx.update("action", action_id, {"due_event": entry.id, "due": due}, _TEST, read_version=current.version)
    before = {e.id: e.data["start"] for e in entries(store)}
    put("weekly-series.ics", NOW + timedelta(hours=1))
    after = {e.id: e.data["start"] for e in entries(store)}
    key = "series-1@calendar.example.com#2030-03-11T09:00:00+00:00"
    assert store.read().get("event", eleventh.id).data["key"] == key
    assert after[eleventh.id] == "2030-03-12T14:00:00+00:00", "the moved occurrence keeps its entry"
    changed = {i for i in before if before[i] != after.get(i)}
    assert changed == {eleventh.id} | {i for i in before if i not in after}, "only the moved one and the skipped one"
    assert len(after) == len(before)
    assert action_data(store, first)["due"] == "2030-03-12" and action_data(store, first)["news"] == []
    assert action_data(store, second)["due"] == "2030-03-25" and action_data(store, second)["news"] == []
    # The calendar moved a promise without the person: it is in what changed since yesterday, as the meeting's doing.
    from engine import since_yesterday
    from engine.names import People

    plan = since_yesterday.build(ws, store.read(), cfg, People(store, cfg), datetime.now(UTC) + timedelta(minutes=1))
    moved = [e for e in plan.entries if e.record == ("action", first)]
    assert [(e.act, e.because, e.day, e.seen) for e in moved] == [("moved", "meeting", "2030-03-12", False)]


def test_a_cancelled_occurrence_marks_only_that_entry_and_tells_the_promise_due_at_it(source):
    ws, cfg, store, put = source
    master = text_of("cancelled-occurrence.ics").split(
        "BEGIN:VEVENT\nUID:midweek-1@calendar.example.com\nDTSTAMP:20300303"
    )[0]
    put(master + "END:VCALENDAR\n")
    found = {e.data["start"]: e for e in entries(store)}
    assert len(found) == 4 and not any(e.data["cancelled"] for e in found.values())
    thirteenth, twentieth = found["2030-03-13T10:00:00+00:00"], found["2030-03-20T10:00:00+00:00"]
    open_actions = [a for a in fixture_records(DEMO_B, "action") if a.get("status", "open") == "open"]
    called, kept = open_actions[0]["id"], open_actions[1]["id"]
    with store.transaction() as tx:
        for action_id, entry, due in ((called, thirteenth, "2030-03-13"), (kept, twentieth, "2030-03-20")):
            current = tx.get("action", action_id)
            tx.update("action", action_id, {"due_event": entry.id, "due": due}, _TEST, read_version=current.version)
    put("cancelled-occurrence.ics", NOW + timedelta(hours=1))
    after = {e.data["start"]: e.data for e in entries(store, series=thirteenth.data["series"])}
    assert [s for s, d in after.items() if d["cancelled"]] == ["2030-03-13T10:00:00+00:00"]
    news = action_data(store, called)["news"]
    assert len(news) == 1 and "called off" in news[0]["text"] and "Midweek check-in" in news[0]["text"]
    assert action_data(store, called)["due"] == "2030-03-13", "the date stays; the person decides what to do"
    assert action_data(store, kept)["news"] == [] and action_data(store, kept)["due"] == "2030-03-20"
    put("cancelled-occurrence.ics", NOW + timedelta(hours=2))
    assert len(action_data(store, called)["news"]) == 1, "the news is given once"
    single = entries(store, key="one-off-1@calendar.example.com")
    assert single == [], "a single event called off before it was ever kept makes no entry"


def test_a_skipped_date_removes_only_that_occurrences_entry_from_the_series(source):
    ws, cfg, store, put = source
    no_skip = text_of("weekly-series.ics").replace("EXDATE:20300318T090000Z\n", "")
    put(no_skip)
    assert "2030-03-18T09:00:00+00:00" in starts_of(store)
    eighteenth = next(e for e in entries(store) if e.data["start"] == "2030-03-18T09:00:00+00:00")
    promise = promise_due_at(store, eighteenth, "2030-03-18")
    put("weekly-series.ics", NOW + timedelta(hours=1))
    flagged = {e.data["start"]: e.data["cancelled"] for e in entries(store)}
    assert flagged.pop("2030-03-18T09:00:00+00:00") is True
    assert not any(flagged.values()) and len(flagged) == 5
    assert "called off" in action_data(store, promise)["news"][0]["text"]


def test_an_unsupported_rule_is_kept_as_its_first_date_with_the_note(source):
    ws, cfg, store, put = source
    put("unsupported-rule.ics")
    (entry,) = entries(store)
    assert entry.data["start"] == "2030-03-06T09:00:00+00:00" and entry.data["series"] is None
    assert len(entry.data["notes"]) == 1 and "first date" in entry.data["notes"][0]


def test_an_outlook_zoned_meeting_keeps_its_instant_on_the_entry(source):
    ws, cfg, store, put = source
    put("windows-zones.ics")
    found = {e.data["title"]: e.data for e in entries(store)}
    assert found["Dock survey"]["start"] == "2030-03-05T09:00:00-08:00"
    assert found["Chart review"]["notes"] and found["Morning walk-through"]["notes"] == []


def test_the_agenda_shows_each_occurrence_once_and_links_its_entry(source):
    ws, cfg, store, put = source
    put("weekly-series.ics")
    put("cancelled-occurrence.ics", NOW + timedelta(hours=1))
    cfg.ui.today.agenda_days_ahead = 40
    rows = agenda(store, cfg, NOW + timedelta(hours=1))
    stand_ups = [r for r in rows if r.title.startswith("Harbor stand-up")]
    assert [(r.title, r.days[0].isoformat()) for r in stand_ups] == [
        ("Harbor stand-up", "2030-03-04"),
        ("Harbor stand-up (moved)", "2030-03-12"),
        ("Harbor stand-up", "2030-03-25"),
        ("Harbor stand-up", "2030-04-01"),
        ("Harbor stand-up", "2030-04-08"),
    ]
    by_start = {e.data["start"]: e.id for e in entries(store)}
    assert {r.entry for r in stand_ups} <= set(by_start.values()) and len({r.entry for r in stand_ups}) == 5
    assert all(not r.own for r in stand_ups)
    midweek = [r for r in rows if r.title == "Midweek check-in"]
    assert sum(r.cancelled for r in midweek) == 1 and len(midweek) == 4
    # Nothing is listed twice: the entries mirror the source's events, so only the events are shown.
    assert len({(r.title, r.days[0]) for r in rows}) == len(rows)


def test_entries_and_their_attendees_survive_an_export_and_import(source, tmp_path):
    from tests.roundtrip import round_trip

    ws, cfg, store, put = source
    put("invitation.ics")
    put("weekly-series.ics", NOW + timedelta(hours=1))
    assert round_trip(store, cfg, tmp_path / "again")["differences"] == []


# ---- on screen ---------------------------------------------------------------------------------------------------


def test_the_calendar_source_form_offers_a_file_picker_and_lists_calendar_files(tmp_path):
    from tests.test_setup import client, make

    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    calendar = next(k for k in c.get(f"{api}/watch/kinds").json() if k["name"] == "calendar")
    items = {i["key"]: i for i in calendar["items"]}
    assert items["file"]["picker"] == "file" and items["address"]["picker"] is None
    assert "expand_days" in items and items["expand_days"]["default"] == 60
    folder = tmp_path / "mine"
    folder.mkdir()
    (folder / "work.ics").write_text(text_of("invitation.ics"))
    (folder / "notes.txt").write_text("not a calendar")
    (folder / ".hidden.ics").write_text("x")
    listing = c.get(f"{api}/setup/folders", params={"path": str(folder), "files": ".ics"}).json()
    assert listing["files"] == ["work.ics"] and listing["folders"] == []
    plain = c.get(f"{api}/setup/folders", params={"path": str(folder)}).json()
    assert plain["files"] == []


def test_a_file_source_is_added_from_the_picker_and_a_hosted_app_refuses_it(tmp_path):
    from tests.test_setup import client, make

    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    path = tmp_path / "work.ics"
    path.write_text(text_of("invitation.ics"))
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    body = {"connector": "calendar", "label": "Work file", "settings": {"file": str(path)}, "fingerprint": fingerprint}
    both = c.post(f"{api}/watch/sources", json={**body, "settings": {"file": str(path), "address": "env:X"}})
    assert both.status_code == 400 and "link or a file" in both.json()["detail"]
    added = c.post(f"{api}/watch/sources", json=body)
    assert added.status_code == 200, added.text
    source = next(s for s in load_config(ws.config_dir, env={}).watch.sources if s.id == "work-file")
    assert source.settings["file"] == str(path)

    hosted = {"mode": "hosted", "public_url": "https" + "://app.example.com"}
    hosted_cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=hosted)}, sources={})
    c2, api2 = client(ws, hosted_cfg, store)
    fingerprint = c2.get(f"{api2}/settings").json()["fingerprint"]
    refused = c2.post(f"{api2}/watch/sources", json={**body, "label": "Another", "fingerprint": fingerprint})
    assert refused.status_code == 400 and "link" in refused.json()["detail"]
    assert "Another" not in {s.label for s in load_config(ws.config_dir, env={}).watch.sources}


def test_an_event_detail_with_an_attendee_that_is_not_text_is_refused():
    from engine.connectors import EventPerson, Poll, SourceItem

    ok = EventDetails("2030-03-04T09:00:00+00:00", attendees=(EventPerson("a@example.com", "A", "accepted"),))
    checked_poll(Poll([SourceItem("k", "t", "x", event=ok)]))
    bad = EventDetails("2030-03-04T09:00:00+00:00", attendees=("a@example.com",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="attendees"):
        checked_poll(Poll([SourceItem("k", "t", "x", event=bad)]))
