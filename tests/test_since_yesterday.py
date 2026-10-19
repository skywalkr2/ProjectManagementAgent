"""What changed since yesterday (design 6.32 "Dependability", 6.35): everything the assistant or a rule did to the
person's records since the start of the previous day on their clock (or since they last looked, whichever is later),
newest first, one entry per record, each with what was done, the record's words, the reason with the quote and who said
it, whether the person has seen it, and the change and op for Undo. The person's own changes and held items are not
listed. One Today line, "Look over what changed since yesterday", counts what is unseen; opening the list marks it
seen. Names, ids and texts come from the fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import since_yesterday
from engine.applier import Context, Inputs, apply_changeset, undo
from engine.names import People
from engine.ops import CHANGESET
from engine.records import REGISTRY
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.watch import refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_set_aside import LISTS, mail
from tests.test_set_aside import make as make_mail

_TEST = WriteContext(actor="pm", trust="trusted", op="test.since-yesterday")
TOKEN = "since-yesterday-token"
ZONE = "America/Los_Angeles"
# 9:00 AM on October 19 in Los Angeles. The previous day began at 7:00 UTC on October 18.
NOW = datetime(2026, 10, 19, 16, 0, tzinfo=UTC)
START = datetime(2026, 10, 18, 7, 0, tzinfo=UTC)
BEFORE = datetime(2026, 10, 18, 6, 30, tzinfo=UTC)  # 11:30 PM on October 17 there: the day before yesterday
ADDED_AT = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
CLOSED_AT = datetime(2026, 10, 18, 19, 0, tzinfo=UTC)
MOVED_AT = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
ASIDE_AT = datetime(2026, 10, 19, 8, 0, tzinfo=UTC)
OWN_AT = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
PEOPLE = fixture_records(DEMO_B, "person")
ACTIONS = fixture_records(DEMO_B, "action")
ME = next(p for p in PEOPLE if p["id"] == "PER-1")
SENDER = next(p for p in PEOPLE if p["role"] == "Editor")
ENV = {"COCKPIT__WORKSPACE__USER__TIMEZONE": ZONE}


def an_action(owner: str) -> dict:
    return next(a for a in ACTIONS if a.get("status", "open") == "open" and a["owners"][0]["person"] == owner)


MINE = an_action(ME["id"])  # the person's own open action
THEIRS = next(a for a in ACTIONS if a.get("status", "open") == "open" and a["owners"][0]["person"] != ME["id"])
FLOOR_PLAN = "Send the floor plan to the venue"
FLOOR_QUOTE = "I will send the floor plan to the venue this week"
CLOSE_QUOTE = f"{THEIRS['text'].lower()} this morning, it is done"
MOVE_QUOTE = f"{MINE['text'].lower()} by October 30 instead"


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env=ENV)
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def a_source(store, *, author: str, by_you: bool = False, key: str = "k") -> str:
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": NOW.isoformat(),
                "kind": "watched:mailbox",
                "title": "A message",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                "watched": {
                    "source": "inbox",
                    "key": f"<{key}@example.com>",
                    "change": "new",
                    "author": author,
                    "by_you": by_you,
                    "by_us": False,
                },
            },
            _TEST,
        ).id


def apply_at(env, ops, at, *, quote_in: str, author: str | None = None, by_you: bool = False, origin="input", key="k"):
    """Apply ops at a given moment as the assistant does for an input that says `quote_in` (a message from `author`),
    or as the person's own note. Returns the changeset's id."""
    ws, cfg, store = env
    source = (
        a_source(store, author=author or SENDER["full_name"], by_you=by_you, key=key) if origin == "input" else None
    )
    with store.transaction() as tx:
        fields = {"task": "notes", "origin": origin, "state": "done", "created_at": at.isoformat()}
        request = tx.create("request", {**fields, **({"source": source} if source else {})}, _TEST).id
    own = origin == "pm"
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request, source, quote_in, "", "trusted" if own else "untrusted"),
        actor="pm" if own else "assistant",
        confirmed_by_pm=own,
    )
    changeset = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    return apply_changeset(changeset, [], ctx, run=None, now=at)


def add_op(text=FLOOR_PLAN, quote=FLOOR_QUOTE, **more) -> dict:
    return {"op": "action.add", "text": text, "owners": [ME["id"]], "evidence": {"quote": quote}, **more}


def close_op(action: dict = THEIRS, quote=CLOSE_QUOTE) -> dict:
    return {"op": "action.close", "id": action["id"], "evidence": {"quote": quote}}


def move_op(action: dict = MINE, quote=MOVE_QUOTE) -> dict:
    return {"op": "action.move", "id": action["id"], "due": "2026-10-30", "evidence": {"quote": quote}}


def entries(env, now=NOW):
    ws, cfg, store = env
    return since_yesterday.build(ws, store.read(), cfg, People(store, cfg), now)


def acts(plan) -> list[tuple[str, str]]:
    return [(e.act, e.title) for e in plan.entries]


def line_of(env, now=NOW):
    ws, cfg, store = env
    return next((x for x in queue(ws, store, cfg, now) if x.kind == "since_yesterday"), None)


def a_day(env):
    """The day the brief describes: a promise added, one closed by an input, one moved, mail set aside and a change the
    person made themselves, with one more promise added the evening before the window began. Returns the changesets."""
    ws, cfg, store = env
    apply_at(
        env,
        [add_op("Order the flowers for the launch", "I will order the flowers for the launch")],
        BEFORE,
        quote_in="I will order the flowers for the launch",
        key="before",
    )
    made = {
        "added": apply_at(env, [add_op()], ADDED_AT, quote_in=f"Hello. {FLOOR_QUOTE}. Thanks.", key="added"),
        "closed": apply_at(
            env,
            [close_op()],
            CLOSED_AT,
            quote_in=f"Sent {CLOSE_QUOTE}.",
            author=ME["full_name"],
            by_you=True,
            key="closed",
        ),
        "moved": apply_at(
            env,
            [move_op()],
            MOVED_AT,
            quote_in=f"Moving to {MOVE_QUOTE}.",
            author=ME["full_name"],
            by_you=True,
            key="moved",
        ),
    }
    own = next(
        a
        for a in ACTIONS
        if a["id"] not in (MINE["id"], THEIRS["id"])
        and a.get("status", "open") == "open"
        and a["owners"][0]["person"] == ME["id"]
    )
    drop = {"op": "action.drop", "id": own["id"], "reason": "Not needed", "evidence": {"quote": own["text"]}}
    made["own"] = apply_at(env, [drop], OWN_AT, quote_in=own["text"], origin="pm")
    return made


# ---- the list -------------------------------------------------------------------------------------------------------


def test_the_list_holds_what_the_assistant_did_newest_first_with_quotes_and_reporters_and_not_the_persons_own(env):
    made = a_day(env)
    plan = entries(env)
    assert [(e.act, e.title) for e in plan.entries] == [
        ("moved", MINE["text"]),
        ("closed", THEIRS["text"]),
        ("added", FLOOR_PLAN),
    ]
    moved, closed, added = plan.entries
    assert (added.quote, added.said_by, added.said_by_name, added.because) == (
        FLOOR_QUOTE,
        SENDER["id"],
        SENDER["full_name"],
        "said",
    )
    assert (closed.quote, closed.said_by, closed.by_you) == (CLOSE_QUOTE, ME["id"], True)
    assert (moved.quote, moved.day) == (MOVE_QUOTE, "2026-10-30")
    assert [(e.changeset, e.op) for e in plan.entries] == [(made["moved"], 0), (made["closed"], 0), (made["added"], 0)]
    assert all(e.record is not None and e.record[0] == "action" for e in plan.entries)
    assert (plan.since, plan.until) == (START, NOW)
    assert made["own"] not in {e.changeset for e in plan.entries}


def test_a_set_aside_mail_is_listed_with_the_rules_reason_and_undo_that_puts_it_back(tmp_path):
    ws, _, store = make_mail(tmp_path, [mail("by-rule", f"a@{LISTS}", bulk=True)])
    cfg = ws.config(env=ENV)
    try:
        refresh(ws, store, cfg, "m", ASIDE_AT)
        (entry,) = since_yesterday.build(ws, store.read(), cfg, People(store, cfg), NOW).entries
        snapshot = next(s for s in store.read().list("snapshot"))
        assert (entry.act, entry.because, entry.undo) == ("set_aside", "sorting", "set_aside")
        assert entry.title == snapshot.data["title"] and entry.reason and entry.snapshot == snapshot.id
        assert entry.version == snapshot.version and not entry.seen
    finally:
        store.close()


def test_a_change_a_rule_closed_before_the_assistant_read_it_is_listed_as_closed_by_a_rule(tmp_path):
    from tests.test_silent_closes import closed_by_a_rule

    ws, cfg, store, request = closed_by_a_rule(tmp_path)
    try:
        cfg = ws.config(env=ENV)
        created = store.read().get("request", request).data["created_at"]
        found = since_yesterday.build(
            ws, store.read(), cfg, People(store, cfg), datetime.fromisoformat(str(created)) + timedelta(hours=1)
        )
        (entry,) = found.entries
        assert (entry.act, entry.because, entry.undo, entry.request) == ("closed", "rule", "closer_look", request)
        assert entry.reason and "spacing" in entry.reason and not entry.seen
    finally:
        store.close()


def test_a_repeat_of_an_open_promise_is_listed_as_merged_into_it(env):
    ws, cfg, store = env
    owed = {"promised_to": [SENDER["id"]]}
    first = apply_at(env, [add_op(**owed)], ADDED_AT - timedelta(days=3), quote_in=FLOOR_QUOTE, key="first")
    again = apply_at(env, [add_op(**owed)], ADDED_AT, quote_in=f"Again: {FLOOR_QUOTE}", key="again")
    (action,) = [a for a in store.read().list("action") if a.data["text"] == FLOOR_PLAN]
    (entry,) = entries(env).entries
    assert (entry.act, entry.title, entry.record, entry.changeset) == (
        "merged",
        FLOOR_PLAN,
        ("action", action.id),
        again,
    )
    assert first != again


def test_news_on_a_promise_is_listed_as_news_heard_with_what_was_heard(env):
    ws, cfg, store = env
    op = {
        "op": "action.news",
        "id": THEIRS["id"],
        "text": "The proofs are at the printer",
        "evidence": {"quote": CLOSE_QUOTE},
    }
    apply_at(env, [op], ADDED_AT, quote_in=CLOSE_QUOTE)
    (entry,) = entries(env).entries
    assert (entry.act, entry.title, entry.detail) == ("news", THEIRS["text"], "The proofs are at the printer")


def test_a_promise_added_then_closed_is_one_entry_the_newest(env):
    ws, cfg, store = env
    apply_at(env, [add_op()], ADDED_AT, quote_in=FLOOR_QUOTE, key="a")
    (action,) = [a for a in store.read().list("action") if a.data["text"] == FLOOR_PLAN]
    quote = f"{FLOOR_PLAN.lower()} is done"
    apply_at(
        env,
        [close_op({"id": action.id}, quote)],
        CLOSED_AT,
        quote_in=quote,
        author=ME["full_name"],
        by_you=True,
        key="b",
    )
    (entry,) = entries(env).entries
    assert (entry.act, entry.title) == ("closed", FLOOR_PLAN)


def test_a_promise_waiting_for_an_owner_and_an_op_released_from_held_are_not_listed(env):
    ws, cfg, store = env
    apply_at(env, [{**add_op(), "owners": []}], ADDED_AT, quote_in=FLOOR_QUOTE)
    held = apply_at(env, [close_op()], CLOSED_AT, quote_in=CLOSE_QUOTE)
    assert [o["status"] for o in store.read().get("changeset", held).data["ops"]] == ["held"]
    assert entries(env).entries == []  # the held close has its own line
    from engine.applier import release

    release(store, cfg, held, 0)  # the person kept it: their own decision
    assert entries(env).entries == []


# ---- the window -----------------------------------------------------------------------------------------------------


def test_the_window_starts_at_the_beginning_of_the_previous_day_on_the_persons_clock(env):
    ws, cfg, store = env
    assert since_yesterday.window_start(cfg, NOW, None) == START
    summer = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)  # the clocks changed on March 8 in Los Angeles
    assert since_yesterday.window_start(cfg, summer, None) == datetime(2026, 3, 8, 8, 0, tzinfo=UTC)


def test_a_change_at_11_30_pm_the_day_before_yesterday_is_outside_and_just_after_midnight_is_inside(env):
    ws, cfg, store = env
    apply_at(
        env,
        [add_op("Order the flowers for the launch", "order the flowers")],
        BEFORE,
        quote_in="order the flowers",
        key="out",
    )
    apply_at(env, [add_op()], START + timedelta(minutes=30), quote_in=FLOOR_QUOTE, key="in")
    assert acts(entries(env)) == [("added", FLOOR_PLAN)]


def test_the_window_starts_at_the_last_look_when_that_is_later(env):
    a_day(env)
    ws, cfg, store = env
    since_yesterday.mark_seen(store, cfg, ADDED_AT + timedelta(minutes=1))
    assert [e.act for e in entries(env).entries] == ["moved", "closed"]
    since_yesterday.mark_seen(store, cfg, CLOSED_AT + timedelta(minutes=1))
    assert [e.act for e in entries(env).entries] == ["moved"]


# ---- seen, and the Today line ---------------------------------------------------------------------------------------


def test_nothing_unseen_means_no_line_and_a_day_of_changes_is_one_line_with_counts(env):
    ws, cfg, store = env
    assert line_of(env) is None
    a_day(env)
    line = line_of(env)
    assert (line.group, line.kind, line.count, line.key) == ("risk", "since_yesterday", 3, "since_yesterday")
    assert line.outcome == {"added": 1, "closed": 1, "moved": 1}


def test_the_line_ranks_in_the_risk_group_below_promises(env):
    ws, cfg, store = env
    a_day(env)
    ranked = [x.kind for x in queue(ws, store, cfg, NOW) if x.group == "risk"]
    assert ranked[-1] == "since_yesterday"
    assert ranked.index("since_yesterday") > max((i for i, k in enumerate(ranked) if k == "promise"), default=-1)


def test_opening_the_list_marks_it_seen_the_line_goes_and_a_new_change_brings_it_back(env):
    ws, cfg, store = env
    a_day(env)
    shown = entries(env)
    assert [e.seen for e in shown.entries] == [False, False, False]
    since_yesterday.mark_seen(store, cfg, shown.until)
    assert line_of(env) is None
    assert since_yesterday.looked_at(store.read(), ME["id"]) == NOW
    later = NOW + timedelta(hours=1)
    apply_at(
        env,
        [add_op("Order the flowers for the launch", "order the flowers")],
        later,
        quote_in="order the flowers",
        key="new",
    )
    line = line_of(env, later + timedelta(minutes=5))
    assert (line.count, line.outcome) == (1, {"added": 1})
    # A change that arrives after the list was drawn is not swallowed by marking what was drawn.
    since_yesterday.mark_seen(store, cfg, NOW)
    assert since_yesterday.looked_at(store.read(), ME["id"]) == NOW  # an older mark never moves the look back
    assert line_of(env, later + timedelta(minutes=5)).count == 1


def test_the_look_is_one_small_record_per_person_that_only_moves_forward(env):
    ws, cfg, store = env
    since_yesterday.mark_seen(store, cfg, NOW)
    since_yesterday.mark_seen(store, cfg, NOW + timedelta(hours=2))
    since_yesterday.mark_seen(store, cfg, NOW + timedelta(hours=1))
    (found,) = store.read().list("look")
    assert (found.data["person"], datetime.fromisoformat(str(found.data["at"]))) == (ME["id"], NOW + timedelta(hours=2))
    assert "look" in REGISTRY


def test_a_close_the_person_looked_over_is_listed_as_seen_and_no_longer_counts(env):
    from engine.dispatcher import looks_good

    made = a_day(env)
    ws, cfg, store = env
    looks_good(store, made["closed"])
    plan = entries(env)
    assert {e.act: e.seen for e in plan.entries} == {"moved": False, "closed": True, "added": False}
    assert line_of(env).outcome == {"added": 1, "moved": 1}


# ---- Undo -----------------------------------------------------------------------------------------------------------


def test_undo_from_a_row_restores_the_record_and_the_row_leaves_the_list(env):
    made = a_day(env)
    ws, cfg, store = env
    closed = next(e for e in entries(env).entries if e.act == "closed")
    assert store.read().get("action", THEIRS["id"]).data["status"] == "done"
    report = undo(store, closed.changeset, [closed.op])
    assert report.restored == [closed.op]
    assert store.read().get("action", THEIRS["id"]).data["status"] == "open"
    assert [e.act for e in entries(env).entries] == ["moved", "added"]
    assert closed.changeset == made["closed"]


# ---- changes made by rules ------------------------------------------------------------------------------------------


def test_a_promise_whose_date_followed_its_meeting_is_listed_as_moved_by_a_rule(env):
    ws, cfg, store = env
    with store.transaction() as tx:
        event = tx.create(
            "event",
            {
                "title": "Walkthrough",
                "start": "2026-10-25T14:00:00+00:00",
                "end": "2026-10-25T15:00:00+00:00",
                "trust": "trusted",
            },
            _TEST,
        ).id
        tx.update(
            "action",
            MINE["id"],
            {"due_event": event, "due": "2026-10-25"},
            _TEST,
            read_version=tx.get("action", MINE["id"]).version,
        )
    quote = "the walkthrough has moved to Tuesday, October 27, 3:00 pm UTC"
    op = {
        "op": "event.set",
        "id": event,
        "start": "2026-10-27T15:00:00+00:00",
        "end": "2026-10-27T16:00:00+00:00",
        "evidence": {"quote": quote},
    }
    cs = apply_at(env, [op], ADDED_AT, quote_in=f"Note: {quote}.", key="meeting")
    (entry,) = entries(env).entries
    assert (entry.act, entry.title, entry.because, entry.day) == ("moved", MINE["text"], "meeting", "2026-10-27")
    assert (entry.changeset, entry.op, entry.quote) == (cs, 0, None)


def test_a_reply_owed_closed_by_the_persons_sent_mail_is_listed_as_closed_by_a_rule_with_the_day_they_replied(tmp_path):
    from tests.test_reply_lines import ASKER, SUBJECT, make_reply, named, sent
    from tests.test_reply_lines import NOW as REPLY_NOW

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env=ENV)
    store = Store(ws.db_path, cfg=cfg)
    try:
        with store.transaction() as tx:
            found = tx.get("person", ME["id"])
            reach = {**found.data.get("how_to_reach", {}), "email": "the.person@example.com"}
            tx.update("person", ME["id"], {"how_to_reach": reach}, _TEST, read_version=found.version)
        env = (ws, cfg, store)
        action = make_reply(env, received=REPLY_NOW - timedelta(hours=5), subject=SUBJECT)
        sent(
            env,
            to=[named(ASKER, ASKER["how_to_reach"]["email"])],
            subject="Re: " + SUBJECT,
            received=REPLY_NOW - timedelta(hours=1),
        )
        from engine import reply_lines

        (cs_id,) = reply_lines.close_answered(ws, store, cfg, REPLY_NOW)
        found = since_yesterday.build(ws, store.read(), cfg, People(store, cfg), REPLY_NOW + timedelta(hours=1))
        (entry,) = found.entries
        assert (entry.act, entry.because, entry.by_you, entry.record) == ("closed", "replied", True, ("action", action))
        assert (
            entry.changeset == cs_id
            and entry.day == (REPLY_NOW - timedelta(hours=1)).astimezone(since_yesterday.zone(cfg)).date().isoformat()
        )
        assert store.read().get("changeset", cs_id).data["by_rule"] == "reply_answered"
    finally:
        store.close()


# ---- the words ------------------------------------------------------------------------------------------------------


def test_the_words_of_the_list_and_the_line_come_from_the_wording_sheet():
    words = json.loads((Path(__file__).parent.parent / "web/src/wording/en.json").read_text(encoding="utf-8"))
    acts_ = ("added", "closed", "moved", "merged", "dropped", "set_aside", "news")
    for act in acts_:
        assert "{title}" in words[f"since.act.{act}"] and "{why}" in words[f"since.act.{act}"], act
        assert words[f"queue.since.count.{act}"].strip(), act
    for key in ("said", "said_you", "said_unknown", "reason", "rule", "sorting", "replied", "meeting", "nothing"):
        assert words[f"since.why.{key}"].strip(), key
    assert words["queue.since.title"] == "Look over what changed since yesterday"
    assert words["since.empty"] == "Nothing changed since yesterday."


# ---- the screen's API -----------------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env=ENV, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        client.ws, client.cfg, client.store = ws, cfg, app.state.store
        app.state.worker.now = lambda: NOW
        yield client


def test_after_a_day_of_promises_arriving_closing_and_moving_the_line_is_there_and_an_unseen_close_opens_from_it(api):
    env = (api.ws, api.cfg, api.store)
    made = a_day(env)
    line = next(x for x in api.get("/api/today/queue").json() if x["kind"] == "since_yesterday")
    assert (line["group"], line["count"], line["outcome"]) == ("risk", 3, {"added": 1, "closed": 1, "moved": 1})
    body = api.get("/api/since-yesterday").json()
    assert body["unseen"] == 3 and [e["act"] for e in body["entries"]] == ["moved", "closed", "added"]
    closed = next(e for e in body["entries"] if e["act"] == "closed")
    assert closed["seen"] is False and closed["quote"] == CLOSE_QUOTE and closed["title"] == THEIRS["text"]
    assert (closed["changeset"], closed["op"], closed["undo"]) == (made["closed"], 0, "changeset")
    assert closed["record"] == {"kind": "action", "id": THEIRS["id"]}
    assert closed["said_by_name"] == ME["full_name"] and closed["by_you"] is True
    # The close is also one of those listed as closed without the person seeing.
    assert made["closed"] in {c["changeset"] for c in api.get("/api/silent-closes").json()["closes"]}
    # Opening the list marks it seen, as of the moment it was drawn: the line goes.
    assert api.post("/api/since-yesterday/seen", json={"until": body["as_of"]}).status_code == 200
    assert not any(x["kind"] == "since_yesterday" for x in api.get("/api/today/queue").json())
    again = api.get("/api/since-yesterday").json()
    assert again["entries"] == [] and again["unseen"] == 0
    # Undo from a row restores the promise.
    done = api.post(f"/api/changesets/{closed['changeset']}/undo", json={"ops": [closed["op"]]})
    assert done.status_code == 200 and done.json()["restored"] == [0]
    assert api.store.read().get("action", THEIRS["id"]).data["status"] == "open"


def test_an_empty_day_serves_an_empty_list(api):
    body = api.get("/api/since-yesterday").json()
    assert body["entries"] == [] and body["unseen"] == 0
    assert api.post("/api/since-yesterday/seen", json={"until": body["as_of"]}).status_code == 200
