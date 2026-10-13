"""Names in context (design 6.11): a bare first name resolves only for someone in the input's context, a name with a
different initial is held, and the received date rides with the input into the packet. Names and ids come from the
fictional workspace's records."""

from datetime import UTC, date, datetime, timedelta

import pytest
import yaml

from engine.config import load_config
from engine.names import People, header_entries
from tests.conftest import DEMO_B, fixture_records

PEOPLE = {p["id"]: p for p in fixture_records(DEMO_B, "person")}
PM = "PER-1"


def person(role):
    return next(p for p in PEOPLE.values() if p.get("role") == role)


def first(p):
    return p["full_name"].split()[0]


def surname(p):
    return p["full_name"].split()[-1]


def people(context=()):
    return People.from_records(PEOPLE, PM, context=context)


def shared_first_name():
    """The two people who answer to the same first name."""
    by_first = {}
    for p in PEOPLE.values():
        by_first.setdefault(first(p), []).append(p)
    return next(v for v in by_first.values() if len(v) > 1)


# ---- resolving, with and without context -----------------------------------------------------------------------------


def test_a_first_name_only_one_person_has_needs_context():
    sam = person("Typesetter")
    held = people().resolve(first(sam))
    assert held.status == "ambiguous" and held.candidates == (sam["id"],), "held, offering the one person it could be"
    assert people(context=[sam["id"]]).resolve(first(sam)).person == sam["id"]
    assert people(context=[PM]).resolve(first(sam)).status != "ok", "someone else's presence doesn't count"


def test_the_pm_is_always_in_context():
    assert people().resolve(first(PEOPLE[PM])).person == PM


def test_a_first_name_two_people_share_resolves_to_the_one_in_context():
    one, other = shared_first_name()
    name = first(one)
    assert people().resolve(name).status == "ambiguous"
    assert people(context=[one["id"]]).resolve(name).person == one["id"]
    assert people(context=[other["id"]]).resolve(name).person == other["id"]
    both = people(context=[one["id"], other["id"]]).resolve(name)
    assert both.status == "ambiguous" and set(both.candidates) == {one["id"], other["id"]}


def test_full_names_aliases_ids_and_me_resolve_without_context():
    sam = person("Typesetter")
    theo = person("Cover designer")
    assert people().resolve(sam["full_name"].upper()).person == sam["id"]
    assert people().resolve(sam["id"]).person == sam["id"]
    assert theo["aliases"][0] == first(theo), "the fixture gives this person their first name as an alias"
    assert people().resolve(theo["aliases"][0]).person == theo["id"], "a set alias resolves as it always did"
    for me in ("me", "Me", "myself", "I"):
        assert people().resolve(me).person == PM


def test_a_different_initial_or_surname_is_held_even_with_the_first_name_in_context():
    one, other = shared_first_name()
    wrong = next(c for c in "QXZJ" if all(not surname(p).upper().startswith(c) for p in (one, other)))
    for text in (f"{first(one)} {wrong}.", f"{first(one)} {wrong}", f"{first(one)} {wrong}ogwell"):
        r = people(context=[one["id"]]).resolve(text)
        assert r.status == "ambiguous" and set(r.candidates) == {one["id"], other["id"]}, text


def test_a_name_with_a_different_initial_is_held_when_only_one_person_has_that_first_name():
    sam = person("Typesetter")
    wrong = next(c for c in "QXZJ" if not surname(sam).upper().startswith(c))
    r = people(context=[sam["id"]]).resolve(f"{first(sam)} {wrong}.")
    assert r.status == "ambiguous" and r.candidates == (sam["id"],)


def test_an_initial_or_surname_fragment_that_matches_resolves():
    one, other = shared_first_name()
    for p in (one, other):
        for text in (
            f"{first(p)} {surname(p)[0]}.",
            f"{first(p)} {surname(p)[:3].lower()}",
            f"{first(p)} {surname(p)}",
        ):
            assert people().resolve(text).person == p["id"], text


def test_an_unknown_name_stays_unknown():
    r = people(context=list(PEOPLE)).resolve("Nobody Atall")
    assert r.status == "unknown" and r.candidates == ()


# ---- who is in a thread ----------------------------------------------------------------------------------------------


def test_header_entries_come_from_the_leading_header_block_only():
    text = "From: A One <a@example.com>\nTo: B Two,\n  C Three <c@example.com>\nCc: D Four\nSubject: S\n\n"
    text += "From: E Five\nBody"
    assert header_entries(text) == ["A One <a@example.com>", "B Two", "C Three <c@example.com>", "D Four"]
    assert header_entries("Minutes\n\nTo: nobody") == []
    assert header_entries("") == []


def test_entries_match_a_person_by_address_or_full_name():
    maya = shared_first_name()[0]
    address = maya.get("how_to_reach", {}).get("email")
    by_name = people().match_entries(
        [f"{maya['full_name']} <someone@example.com>", "Nobody Atall", "A <a@example.com>"]
    )
    assert by_name == {maya["id"]}
    if address:
        assert people().match_entries([f"Another Name <{address.upper()}>"]) == {maya["id"]}
    assert people().match_entries([first(maya)]) == set(), "a bare first name on a header says nothing"


# ---- the context of an input -----------------------------------------------------------------------------------------


def workspace(tmp_path, sources=None):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    if sources is not None:
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": sources}))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def test_a_hand_ins_project_and_thread_headers_put_people_in_context(tmp_path):
    from engine.intake import hand_in

    one, other = shared_first_name()
    owner_of_project_work = next(
        a["owners"][0]["person"]
        for a in fixture_records(DEMO_B, "action")
        if a.get("project") == "PRJ-1" and a.get("owners")
    )
    ws, cfg, store = workspace(tmp_path)
    try:
        plain = hand_in(ws, store, pasted=f"Notes: {first(one)} will call.")
        assert People.for_input(store, cfg, plain.request).resolve(first(one)).status == "ambiguous"
        with_headers = hand_in(ws, store, pasted=f"From: {PEOPLE[PM]['full_name']}\nTo: {other['full_name']}\n\nHi")
        context = People.for_input(
            store, cfg, with_headers.request, text="From: x\nTo: " + other["full_name"] + "\n\nHi"
        )
        assert context.resolve(first(other)).person == other["id"]
        in_project = hand_in(ws, store, pasted="Notes: a note", project="PRJ-1")
        roster = People.for_input(store, cfg, in_project.request)
        assert owner_of_project_work in roster.in_context and PM in roster.in_context
        project_owners = {
            a["owners"][0]["person"] for a in fixture_records(DEMO_B, "action") if a.get("project") == "PRJ-1"
        }
        in_project_person = next(p for p in PEOPLE.values() if first(p) == first(one) and p["id"] in project_owners)
        assert roster.resolve(first(one)).person == in_project_person["id"]
    finally:
        store.close()


def test_a_watched_messages_sender_and_participants_put_people_in_context(tmp_path):
    from engine.watch import refresh

    one, other = shared_first_name()
    item = {
        "key": "m1",
        "title": "Launch reading",
        "text": f"Notes only: {first(other)} will send the list.",
        "message": {
            "sender": f"{PEOPLE[PM]['full_name']} <a@example.com>",
            "received": "2026-10-06T09:00:00+00:00",
            "participants": [f"{other['full_name']} <b@example.com>"],
        },
    }
    ws, cfg, store = workspace(
        tmp_path,
        [{"id": "m", "connector": "fake", "label": "Inbox", "first_run": "all", "settings": {"items": [item]}}],
    )
    try:
        result = refresh(ws, store, cfg, "m", datetime(2026, 10, 9, 9, 0, tzinfo=UTC))
        snap = store.read().find("snapshot", {"source": "m"})[0]
        assert snap.data["message"]["participants"] == [f"{other['full_name']} <b@example.com>"]
        assert People.for_input(store, cfg, result.new[0]).resolve(first(other)).person == other["id"]
        assert People.for_input(store, cfg, result.new[0]).resolve(first(one)).status == "ambiguous"
    finally:
        store.close()


# ---- the received date -----------------------------------------------------------------------------------------------


def test_a_watched_items_received_date_is_its_own_received_time_not_when_it_changed_or_was_read(tmp_path):
    from engine.watch import refresh

    received = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)
    item = {
        "key": "m1",
        "title": "Spine file",
        "text": "From: someone\n\nI'll send it by Friday.",
        "changed_at": (received + timedelta(days=2)).isoformat(),
        "message": {"sender": "someone", "received": received.isoformat()},
    }
    ws, cfg, store = workspace(
        tmp_path,
        [{"id": "m", "connector": "fake", "label": "Inbox", "first_run": "all", "settings": {"items": [item]}}],
    )
    try:
        result = refresh(ws, store, cfg, "m", received + timedelta(days=3))
        request = store.read().get("request", result.new[0])
        source = store.read().get("source", request.data["source"])
        assert source.data["received_at"] == received
    finally:
        store.close()


def test_an_item_with_no_received_time_is_dated_when_it_was_read(tmp_path):
    from engine.watch import refresh

    item = {"key": "n1", "title": "A note", "text": "A line.", "changed_at": "2020-01-01T00:00:00+00:00"}
    ws, cfg, store = workspace(
        tmp_path,
        [{"id": "m", "connector": "fake", "label": "Board", "first_run": "all", "settings": {"items": [item]}}],
    )
    try:
        read_at = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
        result = refresh(ws, store, cfg, "m", read_at)
        request = store.read().get("request", result.new[0])
        assert store.read().get("source", request.data["source"]).data["received_at"] == read_at
    finally:
        store.close()


def test_the_packet_states_the_inputs_received_date_beside_todays(tmp_path):
    from engine.intake import hand_in
    from engine.packet import build

    tuesday = datetime(2026, 10, 6, 14, 0, tzinfo=UTC)
    friday = date(2026, 10, 9)
    ws, cfg, store = workspace(tmp_path)
    try:
        handed = hand_in(ws, store, pasted="Subject: Spine\n\nI'll send it by Friday.", now=tuesday)
        request = build(ws, store, cfg, handed.request, friday).task.request
        assert "Today is 2026-10-09 (Friday)." in request
        assert "received on 2026-10-06 (Tuesday)" in request
        note_only = hand_in(ws, store, note="Chase the printer by Friday.", now=tuesday)
        assert "received on 2026-10-06 (Tuesday)" in build(ws, store, cfg, note_only.request, friday).task.request
    finally:
        store.close()


def test_the_received_date_is_the_day_in_the_workspaces_time_zone(tmp_path):
    from engine.intake import hand_in
    from engine.packet import build

    # Late evening in the workspace's zone is already the next day in UTC.
    late = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
    ws, cfg, store = workspace(tmp_path)
    try:
        handed = hand_in(ws, store, pasted="Subject: Late\n\nBody", now=late)
        request = build(ws, store, cfg, handed.request, date(2026, 10, 7)).task.request
        assert "received on 2026-10-06 (Tuesday)" in request
    finally:
        store.close()


# ---- the golden set --------------------------------------------------------------------------------------------------


def test_every_golden_case_carries_its_received_date_and_the_clock_freezes_there(monkeypatch):
    import engine.evaluate as ev

    cases = ev.load_cases(DEMO_B)
    assert cases and all(isinstance(c["received"], (str, date)) for c in cases)
    seen = []
    real = ev.hand_in
    monkeypatch.setattr(ev, "hand_in", lambda *a, **k: (seen.append(k["now"]), real(*a, **k))[1])
    original = ev.load_cases
    monkeypatch.setattr(
        ev,
        "load_cases",
        lambda t: [{**c, "received": "2026-10-06"} for c in original(t) if c["id"] == "relative-due-date"],
    )
    ev.evaluate(DEMO_B, stub=True, env={})
    assert [n.date() for n in seen] == [date(2026, 10, 6)]


def test_a_case_without_a_received_date_is_refused(monkeypatch, tmp_path):
    import shutil

    import engine.evaluate as ev

    template = tmp_path / "template"
    shutil.copytree(DEMO_B, template)
    path = template / "evals" / "no-owner.yaml"
    path.write_text(path.read_text().replace("received: '2026-10-09'\n", ""))
    with pytest.raises(ValueError, match="no-owner.*received"):
        ev.load_cases(template)


def test_the_new_golden_cases_exist():
    from engine.evaluate import load_cases

    ids = {c["id"] for c in load_cases(DEMO_B)}
    assert {"first-name-in-thread", "different-initial-held", "unknown-person"} <= ids
