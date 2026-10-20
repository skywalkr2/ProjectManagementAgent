"""A plain calendar entry needs no AI run (design 6.2, 6.32; the functional designer's answer F20, B-7).

An entry of a calendar file with no one else invited, no description and no change to a date a promise is due at is
kept in the app's calendar by rule: no run of the assistant and no Review line. One whose title starts with a task verb
(a language setting) is offered as a to-do with one click, by rule. One whose title names a known person, or a promise's
words, is linked to them by rule, so a promise due at it moves with it. The assistant still reads an invitation from
someone else, an entry with a description, and one that moved a date a promise is due at. Names, addresses and ids
come from the fixtures; the calendar is a file."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.config import load_config
from engine.connectors import EventDetails
from engine.storage import Store, WriteContext
from engine.today import agenda
from engine.today_queue import queue
from engine.watch import hand_in_recent, refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
_TEST = WriteContext("pm", "trusted", "test")
TOKEN = "plain-entries-token"
PEOPLE = fixture_records(DEMO_B, "person")
ME = PEOPLE[0]
ME_ADDRESS = ME["full_name"].lower().replace(" ", ".") + "@example.com"
ORGANIZER = next(p for p in PEOPLE if (p.get("how_to_reach") or {}).get("email"))
ORGANIZER_ADDRESS = ORGANIZER["how_to_reach"]["email"]
_FIRSTS = [p["full_name"].split()[0] for p in PEOPLE]
KNOWN = next(p for p in PEOPLE[1:] if _FIRSTS.count(p["full_name"].split()[0]) == 1)  # a first name only they have
FIRST_NAME = KNOWN["full_name"].split()[0]
SHARED = next(f for f in _FIRSTS if _FIRSTS.count(f) > 1)  # a first name two people share
EMPTY = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Fictional//Calendar//EN\nEND:VCALENDAR\n"


def vevent(uid, title, *, day="20300309", hour="15", description=None, invited=False, with_me=False, status=None):
    lines = ["BEGIN:VEVENT", f"UID:{uid}@calendar.example.com", "DTSTAMP:20300301T080000Z"]
    lines += [f"DTSTART:{day}T{hour}0000Z", f"DTEND:{day}T{int(hour) + 1}0000Z", f"SUMMARY:{title}"]
    if status:
        lines.append(f"STATUS:{status}")
    if description:
        lines.append(f"DESCRIPTION:{description}")
    if invited:
        lines.append(f"ORGANIZER;CN={ORGANIZER['full_name']}:mailto:{ORGANIZER_ADDRESS}")
        lines.append(f"ATTENDEE;CN={ME['full_name']};PARTSTAT=NEEDS-ACTION:mailto:{ME_ADDRESS}")
    if with_me:
        lines.append(f"ATTENDEE;CN={ME['full_name']};PARTSTAT=ACCEPTED:mailto:{ME_ADDRESS}")
    lines.append("END:VEVENT")
    return "\n".join(lines)


def calendar(*events: str, method: str | None = None) -> str:
    head = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Fictional//Calendar//EN\n" + (
        f"METHOD:{method}\n" if method else ""
    )
    return head + "\n".join(events) + "\nEND:VCALENDAR\n"


def _build(tmp_path):
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
    return ws, cfg, path


def _identify(store):
    with store.transaction() as tx:
        found = tx.get("person", ME["id"])
        reach = {**(found.data.get("how_to_reach") or {}), "email": ME_ADDRESS}
        tx.update("person", ME["id"], {"how_to_reach": reach}, _TEST, read_version=found.version)


@pytest.fixture
def cal(tmp_path):
    ws, cfg, path = _build(tmp_path)
    store = Store(ws.db_path, cfg=cfg)
    _identify(store)

    def put(text, at=NOW):
        path.write_text(text)
        return refresh(ws, store, cfg, "calendar", at)

    put(EMPTY, NOW - timedelta(hours=2))  # the first read only notes what is there
    yield ws, cfg, store, put
    store.close()


def entry_of(store, title):
    return next(e for e in store.read().find("event", {"source": "calendar"}) if e.data["title"] == title)


def requests(store):
    return store.read().list("request")


def open_actions():
    return [a for a in fixture_records(DEMO_B, "action") if a.get("status", "open") == "open"]


# ---- plain entries are filed by rule ----------------------------------------------------------------------


def test_a_plain_entry_is_kept_in_the_calendar_by_rule_with_no_run_and_no_review_line(cal):
    ws, cfg, store, put = cal
    result = put(calendar(vevent("a", "Planning reminder")))
    assert result.new == [] and result.changed == []
    assert requests(store) == []
    found = entry_of(store, "Planning reminder")
    assert found.data["plain"] is True and found.data["invitation"] is False
    assert [x for x in queue(ws, store, cfg, NOW) if x.kind in ("review", "decide", "go", "first_go")] == []
    assert [i.title for i in agenda(store, cfg, NOW, NOW.date() + timedelta(days=10))] == ["Planning reminder"]


def test_an_entry_with_only_the_person_on_the_attendee_list_is_still_plain(cal):
    ws, cfg, store, put = cal
    assert put(calendar(vevent("a", "Block out the morning", with_me=True))).new == []
    assert entry_of(store, "Block out the morning").data["plain"] is True


def test_an_invitation_from_someone_else_is_read_by_the_assistant(cal):
    ws, cfg, store, put = cal
    result = put(calendar(vevent("a", "Floor plan walkthrough", invited=True), method="REQUEST"))
    assert len(result.new) == 1 and entry_of(store, "Floor plan walkthrough").data["plain"] is False


def test_an_entry_with_a_description_is_read_by_the_assistant(cal):
    ws, cfg, store, put = cal
    result = put(calendar(vevent("a", "Planning reminder", description="Bring the proofs and the budget sheet")))
    assert len(result.new) == 1 and entry_of(store, "Planning reminder").data["plain"] is False


def test_a_connector_that_does_not_say_whether_an_entry_has_a_description_is_read_by_the_assistant():
    from engine.entry_rules import is_plain

    said = EventDetails(start="2030-03-09T15:00:00+00:00", entries=True, described=False)
    silent = EventDetails(start="2030-03-09T15:00:00+00:00", entries=True)
    assert is_plain(said, set(), set()) and not is_plain(silent, set(), set())


def test_a_changed_plain_entry_is_still_filed_by_rule_and_keeps_its_place(cal):
    ws, cfg, store, put = cal
    put(calendar(vevent("a", "Planning reminder")))
    first = entry_of(store, "Planning reminder")
    result = put(calendar(vevent("a", "Planning reminder", day="20300311")), NOW + timedelta(hours=1))
    assert result.changed == [] and requests(store) == []
    moved = entry_of(store, "Planning reminder")
    assert moved.id == first.id and moved.data["start"].startswith("2030-03-11")


def test_an_entry_that_moved_a_date_a_promise_is_due_at_is_read_by_the_assistant_and_the_promise_follows(cal):
    ws, cfg, store, put = cal
    put(calendar(vevent("a", "Planning reminder")))
    entry = entry_of(store, "Planning reminder")
    promise = open_actions()[0]["id"]
    with store.transaction() as tx:
        current = tx.get("action", promise)
        tx.update("action", promise, {"due_event": entry.id, "due": "2030-03-09"}, _TEST, read_version=current.version)
    result = put(calendar(vevent("a", "Planning reminder", day="20300312")), NOW + timedelta(hours=1))
    assert len(result.changed) == 1
    assert store.read().get("action", promise).data["due"] == "2030-03-12"


def test_a_called_off_plain_entry_is_filed_by_rule_and_still_tells_the_promise_due_at_it(cal):
    ws, cfg, store, put = cal
    put(calendar(vevent("a", "Planning reminder")))
    entry = entry_of(store, "Planning reminder")
    promise = open_actions()[0]["id"]
    with store.transaction() as tx:
        current = tx.get("action", promise)
        tx.update("action", promise, {"due_event": entry.id, "due": "2030-03-09"}, _TEST, read_version=current.version)
    put(calendar(vevent("a", "Planning reminder", status="CANCELLED")), NOW + timedelta(hours=1))
    assert entry_of(store, "Planning reminder").data["cancelled"] is True
    assert [n["text"] for n in store.read().get("action", promise).data["news"]] == [
        "Planning reminder on 2030-03-09 was called off"
    ]


def test_the_first_hand_in_of_what_a_source_holds_leaves_plain_entries_out(tmp_path):
    ws, cfg, path = _build(tmp_path)
    store = Store(ws.db_path, cfg=cfg)
    try:
        _identify(store)
        path.write_text(
            calendar(
                vevent("a", "Planning reminder", day="20300304"),
                vevent("b", "Budget review", day="20300304", description="Numbers for the printer"),
            )
        )
        refresh(ws, store, cfg, "calendar", NOW)  # the first read only notes what is there
        assert requests(store) == []
        assert len(hand_in_recent(ws, store, cfg, "calendar", NOW)) == 1  # only the one with a description
    finally:
        store.close()


# ---- a task-like title is offered as a to-do ----------------------------------------------------------------------


def offers(store, cfg):
    return {i.title: i.todo_offer for i in agenda(store, cfg, NOW, NOW.date() + timedelta(days=10))}


def test_a_plain_entry_whose_first_word_is_a_task_verb_is_offered_as_a_to_do_and_others_are_not(cal):
    ws, cfg, store, put = cal
    put(
        calendar(
            vevent("a", "Pay the deposit", day="20300307"),
            vevent("b", "Planning reminder", day="20300307"),
            vevent("c", "Pay the invoice", day="20300307", description="Use the card on file"),
            vevent("d", "Send the rota", day="20300307", invited=True),
        )
    )
    assert offers(store, cfg) == {
        "Pay the deposit": "Pay the deposit",
        "Planning reminder": None,
        "Pay the invoice": None,
        "Send the rota": None,
    }


def test_the_task_verbs_are_a_language_setting_with_a_description_and_demo_values(tmp_path):
    from engine.config.schema import LanguageFile

    assert LanguageFile.model_fields["task_verbs"].description
    assert "pay" in LanguageFile().task_verbs and "send" in LanguageFile().task_verbs
    for name in ("demo-a", "demo-b"):
        language = yaml.safe_load((DEMO_B.parent / name / "config" / "language.yaml").read_text())
        assert language["task_verbs"] == LanguageFile().task_verbs


def test_changing_the_verbs_changes_what_is_offered(cal):
    ws, cfg, store, put = cal
    put(calendar(vevent("a", "Pay the deposit", day="20300307"), vevent("b", "Ponder the plan", day="20300307")))
    cfg.language.task_verbs = ["ponder"]
    assert offers(store, cfg) == {"Pay the deposit": None, "Ponder the plan": "Ponder the plan"}


REAL = datetime.now(UTC)
TOMORROW = (REAL + timedelta(days=1)).date()
THEN = TOMORROW.strftime("%Y%m%d")


@pytest.fixture
def api(tmp_path):
    ws, cfg, path = _build(tmp_path)
    cfg = load_config(ws.config_dir, env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        store = app.state.store
        _identify(store)
        path.write_text(EMPTY)
        refresh(ws, store, cfg, "calendar", REAL - timedelta(hours=2))
        path.write_text(calendar(vevent("a", "Pay the deposit", day=THEN), vevent("b", "Planning reminder", day=THEN)))
        refresh(ws, store, cfg, "calendar", REAL)
        yield client, store, cfg


def test_one_click_makes_the_to_do_for_the_person_due_at_the_entry_and_the_offer_goes(api):
    client, store, cfg = api
    entry = entry_of(store, "Pay the deposit")
    made = client.post(f"/api/events/{entry.id}/todo")
    assert made.status_code == 200, made.text
    action = store.read().get("action", made.json()["action"])
    assert action.data["text"] == "Pay the deposit" and action.data["status"] == "open"
    assert [o["person"] for o in action.data["owners"]] == [ME["id"]]
    assert (action.data["due"], action.data["due_event"]) == (TOMORROW.isoformat(), entry.id)
    assert action.data["event"] == entry.id
    rows = {r["title"]: r["todo_offer"] for r in client.get("/api/today/agenda").json()}
    assert rows["Pay the deposit"] is None
    assert client.post(f"/api/events/{entry.id}/todo").status_code == 409  # made once


def test_undoing_the_to_do_brings_the_offer_back(api):
    from engine.dispatcher import undo_changeset

    client, store, cfg = api
    entry = entry_of(store, "Pay the deposit")
    made = client.post(f"/api/events/{entry.id}/todo").json()
    undo_changeset(store, made["changeset"])
    assert store.read().get("action", made["action"]) is None
    rows = {r["title"]: r["todo_offer"] for r in client.get("/api/today/agenda").json()}
    assert rows["Pay the deposit"] == "Pay the deposit"


def test_the_to_do_follows_the_entry_when_the_calendar_moves_it(api):
    from engine.applier import follow_event

    client, store, cfg = api
    entry = entry_of(store, "Pay the deposit")
    action = client.post(f"/api/events/{entry.id}/todo").json()["action"]
    later = TOMORROW + timedelta(days=1)
    with store.transaction() as tx:
        tx.update(
            "event",
            entry.id,
            {"start": f"{later}T15:00:00+00:00", "end": f"{later}T16:00:00+00:00"},
            _TEST,
            read_version=tx.get("event", entry.id).version,
        )
        follow_event(tx, entry.id, _TEST)
    assert store.read().get("action", action).data["due"] == later.isoformat()


def test_an_entry_that_is_not_task_like_is_refused_a_to_do_and_an_unknown_one_is_not_found(api):
    client, store, cfg = api
    assert client.post(f"/api/events/{entry_of(store, 'Planning reminder').id}/todo").status_code == 409
    assert client.post("/api/events/EVT-NOPE/todo").status_code == 404


def test_the_agenda_api_carries_the_offer(api):
    client, store, cfg = api
    rows = client.get("/api/today/agenda").json()
    assert {r["title"]: r.get("todo_offer") for r in rows} == {
        "Pay the deposit": "Pay the deposit",
        "Planning reminder": None,
    }


# ---- linked to a known person, or to a promise's words ---------------------------------------------------------------


def test_an_entry_whose_title_names_a_known_person_is_linked_to_them(cal):
    ws, cfg, store, put = cal
    put(
        calendar(
            vevent("a", f"Lunch with {KNOWN['full_name']}", day="20300307"),
            vevent("b", f"Coffee with {FIRST_NAME}", day="20300307"),
            vevent("c", "Lunch with Nobody Known", day="20300307"),
        )
    )
    assert entry_of(store, f"Lunch with {KNOWN['full_name']}").data["people"] == [KNOWN["id"]]
    assert entry_of(store, f"Coffee with {FIRST_NAME}").data["people"] == [KNOWN["id"]]
    assert entry_of(store, "Lunch with Nobody Known").data["people"] == []


def test_a_first_name_two_people_share_links_nobody_and_a_full_name_links_the_one(cal):
    ws, cfg, store, put = cal
    both = [p for p in PEOPLE if p["full_name"].split()[0] == SHARED]
    put(
        calendar(
            vevent("a", f"Coffee with {SHARED}", day="20300307"),
            vevent("b", f"Lunch with {both[0]['full_name']}", day="20300307"),
        )
    )
    assert entry_of(store, f"Coffee with {SHARED}").data["people"] == []
    assert entry_of(store, f"Lunch with {both[0]['full_name']}").data["people"] == [both[0]["id"]]


def test_the_person_themselves_named_in_a_title_links_nobody(cal):
    ws, cfg, store, put = cal
    put(calendar(vevent("a", f"Quiet time for {ME['full_name']}", day="20300307")))
    assert entry_of(store, f"Quiet time for {ME['full_name']}").data["people"] == []


def promise(store, text, *, due):
    action = open_actions()[0]["id"]
    with store.transaction() as tx:
        current = tx.get("action", action)
        tx.update("action", action, {"text": text, "due": due, "due_event": None}, _TEST, read_version=current.version)
    return action


def test_an_entry_that_names_a_promises_words_on_the_promises_day_is_linked_and_the_promise_moves_with_it(cal):
    ws, cfg, store, put = cal
    action = promise(store, "Return the signed contract to the printer", due="2030-03-07")
    put(calendar(vevent("a", "Return the signed contract", day="20300307")))
    entry = entry_of(store, "Return the signed contract")
    assert store.read().get("action", action).data["due_event"] == entry.id
    put(calendar(vevent("a", "Return the signed contract", day="20300310")), NOW + timedelta(hours=1))
    assert store.read().get("action", action).data["due"] == "2030-03-10"


def test_a_promise_on_another_day_or_with_no_day_or_other_words_is_not_linked(cal):
    ws, cfg, store, put = cal
    entries = calendar(
        vevent("a", "Return the signed contract", day="20300307"), vevent("b", "Book the room", day="20300307")
    )
    elsewhere = promise(store, "Return the signed contract to the printer", due="2030-03-20")
    put(entries)
    assert store.read().get("action", elsewhere).data["due_event"] is None
    undated = promise(store, "Return the signed contract to the printer", due=None)
    put(entries.replace("SUMMARY:Book the room", "SUMMARY:Book the large room"), NOW + timedelta(hours=1))
    assert store.read().get("action", undated).data["due_event"] is None
    other_words = promise(store, "Order the bookmarks", due="2030-03-07")
    put(entries, NOW + timedelta(hours=2))
    assert store.read().get("action", other_words).data["due_event"] is None
