"""One place for every open action and every open question (design 7.5, roadmap B-6a "cleaned up end to end").

Each open action comes with its owners, due date, project and parent project, where it came from, its state and what is
near enough to be the same action; each open question with who it waits on and since when. A near-duplicate is merged
into the row it is offered on, with one Undo; a to-do nobody has touched for a while is stale, and Today says so.
Names, ids and dates come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.open_items import open_actions, open_questions, stale_actions
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "open-items-token"
NOW = datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_PM = WriteContext(actor="pm", trust="trusted", op="test")
PEOPLE = fixture_records(DEMO_B, "person")
ME = PEOPLE[0]["id"]
OTHER = PEOPLE[1]["id"]
THIRD = PEOPLE[3]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, app.state.store, cfg


def add_action(store, text, *, owners=(ME,), by=_PM, **more) -> str:
    data = {"text": text, "owners": [{"person": p} for p in owners], "project": PROJECT["id"], **more}
    with store.transaction() as tx:
        return tx.create("action", data, by).id


def stamp(store, kind, record_id, when: datetime) -> None:
    """Make every ledger entry of a record as old as `when`, as a clock that had been then would have."""
    with store.transaction() as tx:
        tx.sql(
            "UPDATE ledger SET at=? WHERE kind=? AND record_id=?",
            (when.isoformat(timespec="seconds"), kind, record_id),
        )


def by_id(rows):
    return {r.id: r for r in rows}


def test_every_open_action_is_listed_with_its_owners_due_project_and_state(env):
    _, cfg, store = env
    rows = by_id(open_actions(store, cfg, TODAY))
    fixtures = fixture_records(DEMO_B, "action")
    live = {a["id"] for a in fixtures if a.get("status", "open") in ("open", "held")}
    assert set(rows) == live, "done and dropped actions are not open items"
    shared = next(a for a in fixtures if len(a.get("owners", [])) == 2)
    row = rows[shared["id"]]
    names = {p["id"]: p["full_name"] for p in PEOPLE}
    assert [o.name for o in row.owners] == [names[o["person"]] for o in shared["owners"]]
    assert (row.due, row.project, row.project_name) == (shared["due"], PROJECT["id"], PROJECT["name"])
    unowned = next(a for a in fixtures if a.get("status") == "held")
    assert rows[unowned["id"]].owners == [] and rows[unowned["id"]].state == "no_owner"


def test_an_action_with_no_owner_names_the_question_that_asks_who(env):
    _, cfg, store = env
    held = next(a for a in fixture_records(DEMO_B, "action") if a.get("status") == "held")["id"]
    assert by_id(open_actions(store, cfg, TODAY))[held].owner_question is None
    with store.transaction() as tx:
        asking = tx.create(
            "question", {"to": ME, "title": "Pick an owner", "resolves": {"kind": "owner", "action": held}}, _PM
        ).id
    assert by_id(open_actions(store, cfg, TODAY))[held].owner_question == asking


def test_an_owner_shows_with_their_team_as_the_workspace_writes_owners(env):
    ws, _, store = env
    cfg = ws.config(env={}, flags={"workspace.owner_format": "{full_name} ({team})"})
    team = next(t for t in fixture_records(DEMO_B, "team") if t["id"] == PEOPLE[0]["team"])
    action = add_action(store, "Ring the printer", owners=(ME,))
    with store.transaction() as tx:
        rec = tx.get("action", action)
        tx.update("action", action, {"owners": [{"person": ME, "team": team["id"]}]}, _PM, read_version=rec.version)
    row = by_id(open_actions(store, cfg, TODAY))[action]
    assert row.owners[0].name == f"{PEOPLE[0]['full_name']} ({team['name']})" and row.owners[0].team == team["id"]


def test_a_project_inside_a_project_carries_its_parent_tag(env):
    _, cfg, store = env
    with store.transaction() as tx:
        series = tx.create("project", {"name": "The whole list", "status": "On track"}, _PM).id
        rec = tx.get("project", PROJECT["id"])
        tx.update("project", PROJECT["id"], {"parent": series}, _PM, read_version=rec.version)
    action = add_action(store, "Ring the printer")
    row = by_id(open_actions(store, cfg, TODAY))[action]
    assert (row.project_name, row.parent_name) == (PROJECT["name"], "The whole list")
    assert by_id(open_actions(store, cfg, TODAY))[action].notes is None


def test_the_states_are_overdue_on_hold_no_owner_stale_and_open(env):
    _, cfg, store = env
    late = add_action(store, "Chase the late proof", due=(TODAY - timedelta(days=2)).isoformat())
    held = add_action(store, "Wait for the printer", due=(TODAY - timedelta(days=2)).isoformat())
    with store.transaction() as tx:
        rec = tx.get("action", held)
        tx.update(
            "action",
            held,
            {"on_hold": {"waiting_for": "the printer", "since": TODAY.isoformat()}},
            _PM,
            read_version=rec.version,
        )
    old = add_action(store, "Tidy the style sheet")
    stamp(store, "action", old, NOW - timedelta(days=cfg.ui.today.stale_after_days + 1))
    fresh = add_action(store, "Reorder the paper")
    rows = by_id(open_actions(store, cfg, TODAY, now=NOW))
    assert rows[late].state == "overdue"
    assert rows[held].state == "on_hold" and rows[held].on_hold == "the printer"
    assert rows[old].state == "stale"
    assert rows[fresh].state == "open"


def test_a_stale_to_do_is_the_persons_own_undated_open_one_nobody_has_touched(env):
    ws, cfg, store = env
    long_ago = NOW - timedelta(days=cfg.ui.today.stale_after_days + 5)
    own = add_action(store, "Tidy the style sheet")
    dated = add_action(store, "Send the proof", due=(TODAY + timedelta(days=30)).isoformat())
    theirs = add_action(store, "Fix the cover file", owners=(OTHER,))
    paused = add_action(
        store, "Wait on the printer", on_hold={"waiting_for": "the printer", "since": TODAY.isoformat()}
    )
    for record in (own, dated, theirs, paused):
        stamp(store, "action", record, long_ago)
    found = [r.id for r in stale_actions(store, cfg, NOW)]
    assert found == [own]
    assert stale_actions(store, _with(ws, 0), NOW) == [], "zero turns it off"


def _with(ws, days: int):
    return ws.config(env={}, flags={"ui.today.stale_after_days": days})


def test_todays_queue_has_one_line_for_the_stale_to_dos(env):
    ws, cfg, store = env
    long_ago = NOW - timedelta(days=cfg.ui.today.stale_after_days + 5)
    a = add_action(store, "Tidy the style sheet")
    b = add_action(store, "Sort the old proofs")
    for record in (a, b):
        stamp(store, "action", record, long_ago)
    lines = [line for line in queue(ws, store, cfg, NOW) if line.kind == "stale"]
    assert len(lines) == 1
    line = lines[0]
    assert (line.group, line.count) == ("review", 2) and set(line.actions) == {a, b}
    assert line.waiting_days >= cfg.ui.today.stale_after_days
    assert [x for x in queue(ws, store, _with(ws, 0), NOW) if x.kind == "stale"] == []


def test_a_to_do_with_no_owner_is_already_a_line_on_today(env):
    ws, cfg, store = env
    held = next(a for a in fixture_records(DEMO_B, "action") if a.get("status") == "held")["id"]
    with store.transaction() as tx:
        tx.create(
            "question",
            {"to": ME, "title": "Pick an owner", "resolves": {"kind": "owner", "action": held}},
            _PM,
        )
    owner_lines = [line for line in queue(ws, store, cfg, NOW) if line.kind == "owner"]
    assert held in [a for line in owner_lines for a in line.actions]


def test_every_open_question_says_who_it_waits_on_and_since_when(env):
    _, cfg, store = env
    fixtures = fixture_records(DEMO_B, "question")
    rows = by_id(open_questions(store, cfg, TODAY))
    assert set(rows) == {q["id"] for q in fixtures}
    asked = next(q for q in fixtures if q["to"] != ME)
    decision = next(q for q in fixtures if q["to"] == ME)
    assert rows[asked["id"]].state == "not_sent" and rows[asked["id"]].to == asked["to"]
    assert rows[decision["id"]].state == "yours"
    sent_on = TODAY - timedelta(days=6)
    with store.transaction() as tx:
        rec = tx.get("question", asked["id"])
        tx.update(
            "question",
            asked["id"],
            {
                "status": "sent",
                "sent_at": datetime(sent_on.year, sent_on.month, sent_on.day, 9, tzinfo=UTC).isoformat(),
            },
            _PM,
            read_version=rec.version,
        )
    row = by_id(open_questions(store, cfg, TODAY))[asked["id"]]
    assert (row.state, row.since, row.waiting_days) == ("waiting", sent_on.isoformat(), 6)
    assert row.to_name == next(p["full_name"] for p in PEOPLE if p["id"] == asked["to"])
    assert row.project_name == PROJECT["name"] and row.projects == [PROJECT["id"]]
    with store.transaction() as tx:
        rec = tx.get("question", asked["id"])
        tx.update("question", asked["id"], {"status": "answered"}, _PM, read_version=rec.version)
    assert asked["id"] not in by_id(open_questions(store, cfg, TODAY))


def test_two_alike_to_dos_of_one_project_and_owner_each_offer_the_other(env):
    _, cfg, store = env
    a = add_action(store, "Order the sample copies for the reviewers")
    b = add_action(store, "Order the sample copies for the reviewers today")
    rows = by_id(open_actions(store, cfg, TODAY))
    assert rows[a].duplicate.id == b and rows[b].duplicate.id == a
    assert rows[a].duplicate.text == "Order the sample copies for the reviewers today"
    assert rows[a].duplicate.version == store.read().get("action", b).version


def test_alike_to_dos_of_another_owner_or_project_or_done_are_not_offered(env):
    _, cfg, store = env
    a = add_action(store, "Order the sample copies for the reviewers")
    add_action(store, "Order the sample copies for the reviewers", owners=(THIRD,))
    other = add_action(store, "Order the sample copies for the reviewers", project=None)
    done = add_action(store, "Order the sample copies for the reviewers", status="done")
    rows = by_id(open_actions(store, cfg, TODAY))
    assert rows[a].duplicate is None and rows[other].duplicate is None and done not in rows


def test_how_alike_is_the_same_setting_the_lint_uses(env):
    ws, _, store = env
    a = add_action(store, "Order the sample copies for the reviewers")
    b = add_action(store, "Order the sample copies")
    assert by_id(open_actions(store, ws.config(env={}), TODAY))[a].duplicate is None
    loose = ws.config(env={}, flags={"checks.tuning.near_duplicate_action.similarity": 0.5})
    assert by_id(open_actions(store, loose, TODAY))[a].duplicate.id == b


def test_an_action_says_where_it_came_from(env):
    _, cfg, store = env
    with store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": "2026-10-01T00:00:00+00:00",
                "kind": "pasted",
                "title": "An input",
                "content_hash": "0" * 64,
                "trust": "untrusted",
            },
            _PM,
        ).id
    action = add_action(store, "Ring the printer", source=source)
    plain = add_action(store, "Ring the binder")
    rows = by_id(open_actions(store, cfg, TODAY))
    assert rows[action].origin == {"kind": "source", "source": source}
    assert rows[plain].origin is None


# ---- through the API ------------------------------------------------------------------------------------------------


def test_the_api_lists_both_with_what_a_row_needs(api):
    client, store, _ = api
    action = add_action(store, "Ring the printer", notes="Ask about the paper too")
    found = client.get("/api/open-items").json()
    row = next(a for a in found["actions"] if a["id"] == action)
    assert (
        row["owners"][0]["name"]
        and row["project_name"] == PROJECT["name"]
        and row["notes"] == "Ask about the paper too"
    )
    assert row["version"] == store.read().get("action", action).version
    assert {q["id"] for q in found["questions"]} == {q["id"] for q in fixture_records(DEMO_B, "question")}
    assert found["stale_days"] > 0


def test_merging_keeps_this_one_closes_the_other_with_one_undo_and_a_signal(api):
    client, store, _ = api
    a = add_action(store, "Order the sample copies for the reviewers")
    b = add_action(
        store, "Order the sample copies for the reviewers today", due=(TODAY + timedelta(days=3)).isoformat()
    )
    row = next(x for x in client.get("/api/open-items").json()["actions"] if x["id"] == a)
    done = client.post(
        f"/api/actions/{a}/merge",
        json={"other": b, "read_version": row["version"], "other_version": row["duplicate"]["version"]},
    )
    assert done.status_code == 200, done.text
    kept, closed = store.read().get("action", a).data, store.read().get("action", b).data
    assert kept["status"] == "open" and closed["status"] == "dropped"
    assert "Order the sample copies for the reviewers today" in kept["notes"]
    assert kept["due"] == (TODAY + timedelta(days=3)).isoformat(), "the earlier of the two dates, here the only one"
    assert kept["text"] in closed["dropped_reason"]
    assert [s.data["kind"] for s in store.read().list("signal")] == ["dropped"]
    listed = {x["id"] for x in client.get("/api/open-items").json()["actions"]}
    assert a in listed and b not in listed
    undone = client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={"ops": None})
    assert undone.status_code == 200
    assert store.read().get("action", b).data["status"] == "open"
    assert store.read().get("action", a).data.get("notes") in (None, "")


def test_merging_refuses_a_row_that_changed_and_changes_nothing(api):
    client, store, _ = api
    a = add_action(store, "Order the sample copies for the reviewers")
    b = add_action(store, "Order the sample copies for the reviewers today")
    stale = store.read().get("action", a).version - 1 or 1
    with store.transaction() as tx:
        rec = tx.get("action", a)
        tx.update("action", a, {"notes": "Changed since"}, _PM, read_version=rec.version)
    done = client.post(
        f"/api/actions/{a}/merge",
        json={"other": b, "read_version": stale, "other_version": store.read().get("action", b).version},
    )
    assert done.status_code == 409
    assert store.read().get("action", b).data["status"] == "open"
    assert store.read().get("action", a).data["notes"] == "Changed since"


def test_merging_will_not_close_an_action_that_is_not_open_or_is_the_same_one(api):
    client, store, _ = api
    a = add_action(store, "Order the sample copies for the reviewers")
    done = add_action(store, "Order the sample copies for the reviewers today", status="done")
    version = store.read().get("action", a).version
    for other in (done, a):
        refused = client.post(
            f"/api/actions/{a}/merge",
            json={"other": other, "read_version": version, "other_version": store.read().get("action", other).version},
        )
        assert refused.status_code == 409


def test_an_owner_change_from_the_row_is_the_persons_edit_with_undo_and_a_signal(api):
    client, store, _ = api
    action = add_action(store, "Ring the printer", owners=(OTHER,), by=WriteContext("assistant", "trusted", "test"))
    version = store.read().get("action", action).version
    done = client.post(
        "/api/records/edit",
        json={"kind": "action", "id": action, "fields": {"owners": [{"person": THIRD}]}, "read_version": version},
    )
    assert done.status_code == 200, done.text
    assert [o["person"] for o in store.read().get("action", action).data["owners"]] == [THIRD]
    assert [s.data["kind"] for s in store.read().list("signal")] == ["edited"]
    client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={"ops": None})
    assert [o["person"] for o in store.read().get("action", action).data["owners"]] == [OTHER]
