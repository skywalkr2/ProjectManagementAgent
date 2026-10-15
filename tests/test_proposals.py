"""Phase L3, the rules for proposals (design 6.22): a rule is a proposal like the rest, duplicates merge, a proposal
close to a recent discard is not shown, "just this time" is remembered, one Today line holds everything learned,
proposals from inputs expire, and corrections recorded before this phase are learned from once.

Names and ids come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import catch_up, proposals
from engine import search as workspace_search
from engine.dispatcher import signal
from engine.intake import hand_in
from engine.knowledge_section import stable_section
from engine.workspace import Workspace, init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_knowledge_records import (
    NOW,
    OTHER,
    PM,
    PROJECT,
    TEAM,
    apply,
    lesson_saying,
    person_adds,
    proposal,
    reasons,
    request,
    second_project,
    signals,
    source,
)

RULE = {"op": "rule.add", "text": "Every risk names who raised it."}


@pytest.fixture
def app(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "proposals-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer proposals-token"}) as client:
        yield client, application.state.store, cfg, tmp_path


def rule_of(store, cs_id):
    record = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]
    return store.read().get("rule", record["id"])


def proposed_rule(store, cfg, op=None):
    cs_id, statuses = apply(store, cfg, [op or RULE], origin="input", trust="untrusted", source_id=source(store))
    assert statuses == ["applied"]
    return rule_of(store, cs_id)


def queue(client):
    return {line["kind"]: line for line in client.get("/api/today/queue").json()}


def waiting(client):
    return client.get("/api/knowledge/proposals").json()


def post(client, entry_id, action, store=None, **body):
    kind = "rule" if entry_id.startswith("RULE-") else None
    found = (
        store.read().get(kind, entry_id)
        if kind
        else next(e for e in client.get("/api/knowledge").json() if e["id"] == entry_id)
    )
    version = found.version if kind else found["version"]
    return client.post(f"/api/knowledge/{entry_id}/{action}", json={"read_version": version, **body})


# ---- rules become proposals ----------------------------------------


def test_a_rule_from_an_input_is_a_proposal_and_from_the_persons_note_is_active_with_undo(app):
    client, store, cfg, _ = app
    from_input = proposed_rule(store, cfg)
    assert (from_input.data["status"], from_input.data["origin"], from_input.data["trust"]) == (
        "proposed",
        "input",
        "untrusted",
    )
    assert from_input.data["kept_by"] is None
    # Content the person reports on a button that relays someone else is not their rule.
    reported = source(store, kind="note:they_finished", trust="trusted")
    cs_id, statuses = apply(store, cfg, [{**RULE, "text": "Reported rule."}], origin="pm", source_id=reported)
    assert statuses == ["applied"] and rule_of(store, cs_id).data["status"] == "proposed"
    # The assistant's own generalization is a proposal too.
    cs_id, _ = apply(store, cfg, [{**RULE, "text": "Its own rule."}], origin="schedule")
    assert rule_of(store, cs_id).data["status"] == "proposed" and rule_of(store, cs_id).data["origin"] == "assistant"
    # The person's own words apply at once.
    cs_id, statuses = apply(store, cfg, [{**RULE, "text": "The person's rule."}], origin="pm")
    own = rule_of(store, cs_id)
    assert statuses == ["applied"] and (own.data["status"], own.data["kept_by"], own.data["origin"]) == (
        "active",
        PM,
        "person",
    )
    undone = client.post(f"/api/changesets/{cs_id}/undo", json={})
    assert undone.status_code == 200 and not [r for r in store.read().list("rule") if r.id == own.id]


def test_keeping_a_rule_proposal_makes_the_restatement_theirs_and_the_source_stays_outside_evidence(app):
    client, store, cfg, _ = app
    quote = "from now on every risk names who raised it"
    cs_id, _ = apply(
        store,
        cfg,
        [{**RULE, "evidence": {"quote": quote}}],
        origin="input",
        trust="untrusted",
        source_id=source(store),
        raw=quote,
    )
    found = rule_of(store, cs_id)
    listed = waiting(client)["proposals"]
    assert [(p["id"], p["kind"], p["came_from"], p["batch"]) for p in listed] == [(found.id, "rule", "input", "daily")]
    assert listed[0]["evidence"]["quote"] == quote and listed[0]["text"] == RULE["text"]
    done = post(client, found.id, "keep", store, text="Every risk names its owner.")
    assert done.status_code == 200, done.text
    kept = store.read().get("rule", found.id).data
    assert (kept["status"], kept["kept_by"], kept["trust"], kept["text"]) == (
        "active",
        PM,
        "trusted",
        "Every risk names its owner.",
    )
    assert kept["evidence"]["quote"] == quote and kept["origin"] == "input"
    # The packet carries the restatement the person kept, as guidance, and never the source's own words.
    section = stable_section(store.read(), "notes", cfg.dispatch.knowledge).text
    assert "Every risk names its owner." in section and "<untrusted" not in section and quote not in section
    undone = client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={})
    assert undone.status_code == 200
    again = store.read().get("rule", found.id).data
    assert (again["status"], again["trust"], again["text"]) == ("proposed", "untrusted", RULE["text"])


def test_held_rule_decisions_move_once_to_the_catch_up_list_and_running_twice_moves_them_once(app):
    client, store, cfg, _ = app
    op = {**RULE, "text": "A rule that was held."}
    held_source = source(store)
    request_id = request(store, "input", source=held_source)
    with store.transaction() as tx:
        from engine.storage import WriteContext

        cs_id = tx.create(
            "changeset",
            {
                "request": request_id,
                "ops": [
                    {
                        "index": 0,
                        "op": op,
                        "status": "held",
                        "group": "op0",
                        "records": [],
                        "reason": "changes how the product behaves; needs your confirmation",
                        "problems": [],
                    }
                ],
                "status": "held",
                "trust": "untrusted",
                "created_at": NOW,
            },
            WriteContext(actor="engine", trust="trusted", op="test.held"),
        ).id
        waiting_request = tx.get("request", request_id)
        tx.update(
            "request",
            request_id,
            {"changeset": cs_id},
            WriteContext(actor="engine", trust="trusted", op="test.held"),
            read_version=waiting_request.version,
        )
    assert [line["kind"] for line in client.get("/api/today/queue").json()].count("held") == 1
    now = datetime.now(UTC)
    state = catch_up.start(store, cfg, now)
    (moved,) = store.read().list("rule")
    assert moved.data["status"] == "proposed" and moved.data["text"] == op["text"]
    assert state.rules == [moved.id]
    changeset = store.read().get("changeset", cs_id)
    assert changeset.data["status"] == "applied" and changeset.data["ops"][0]["records"][0]["id"] == moved.id
    lines = queue(client)
    assert "held" not in lines and lines["catch_up"]["count"] == 1 and lines["catch_up"]["group"] == "review"
    assert "learned" not in lines  # counted once, on the catch-up list
    again = catch_up.start(store, cfg, now + timedelta(minutes=1))
    assert [r.id for r in store.read().list("rule")] == [moved.id] and again.rules == [moved.id]
    listed = client.get("/api/knowledge/catch-up").json()
    assert [p["id"] for p in listed["proposals"]] == [moved.id] and listed["proposals"][0]["batch"] == "catch_up"
    assert waiting(client)["proposals"] == []


# ---- proposal rules ----------------------------------------


def test_a_duplicate_merges_into_the_entry_it_repeats_and_links_the_evidence(app):
    client, store, cfg, _ = app
    active = person_adds(store, cfg)
    cs_id, statuses = apply(
        store,
        cfg,
        [
            {
                **lesson_saying(" questions about work another team owns   WAIT for an impact check "),
                "evidence": {"quote": "first quote"},
            }
        ],
        origin="input",
        trust="untrusted",
        source_id=source(store),
        raw="first quote",
    )
    record = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]
    assert statuses == ["applied"] and record == active and len(store.read().list("lesson")) == 1
    merged = store.read().get("lesson", active).data
    assert merged["status"] == "active" and merged["text"].startswith("Questions about work another team owns")
    assert [e["quote"] for e in merged["more_evidence"]] == ["first quote"]
    # Two proposals of the same thing leave one, with both pieces of evidence.
    first = proposal(store, cfg, lesson_saying("Always copy the planner."))
    cs_id, _ = apply(
        store,
        cfg,
        [{**lesson_saying("always copy the planner"), "evidence": {"quote": "second quote"}}],
        origin="input",
        trust="untrusted",
        source_id=source(store),
        raw="second quote",
    )
    assert store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"] == first
    assert len([e for e in store.read().list("lesson") if e.data["status"] == "proposed"]) == 1
    assert [e["quote"] for e in store.read().get("lesson", first).data["more_evidence"]] == ["second quote"]
    # A glossary term and a rule merge the same way; a lesson for a project it doesn't overlap is another one.
    proposal(store, cfg, {"op": "glossary.add", "text": "T.", "term": "RTM", "meaning": "Release to manufacturing"})
    proposal(store, cfg, {"op": "glossary.add", "text": "T.", "term": "rtm", "meaning": "Another reading"})
    assert len(store.read().list("glossary_entry")) == 1
    one = proposed_rule(store, cfg)
    assert proposed_rule(store, cfg, {**RULE, "text": "every risk names who raised it"}).id == one.id
    here = proposal(store, cfg, {**lesson_saying("Keep the index current."), "applies_to": {"projects": [PROJECT]}})
    there = {"projects": [second_project(store)]}
    assert proposal(store, cfg, {**lesson_saying("Keep the index current."), "applies_to": there}) != here
    assert (
        proposal(store, cfg, {**lesson_saying("Keep the index current."), "applies_to": {"projects": [PROJECT]}})
        == here
    )


def test_a_proposal_close_to_a_recent_discard_is_not_shown_and_an_old_discard_is_forgotten(app):
    client, store, cfg, _ = app
    first = proposal(store, cfg, lesson_saying("Never ask the planner about print dates directly"))
    assert post(client, first, "discard", reason="wrong").status_code == 200
    close = lesson_saying("Never ask the planner about print dates directly please")
    shown = proposal(store, cfg, close)
    held_back = store.read().get("lesson", shown).data
    assert held_back["status"] == "discarded" and held_back["discard_reason"] == proposals.NEAR_DISCARD_REASON
    assert waiting(client)["proposals"] == []
    # Something else is shown.
    other = proposal(store, cfg, lesson_saying("Name the owner on every risk."))
    assert [p["id"] for p in waiting(client)["proposals"]] == [other]
    # A discard older than the hold no longer counts.
    store.clock = lambda: (
        datetime.now(UTC) + timedelta(days=cfg.dispatch.knowledge.discards_hold_days + 1)
    ).isoformat()
    later = proposal(store, cfg, lesson_saying("Never ask the planner about print dates directly, thanks"))
    assert store.read().get("lesson", later).data["status"] == "proposed"


def test_just_this_time_records_its_signal_discards_and_the_repeat_is_marked(app):
    client, store, cfg, _ = app
    first = proposal(store, cfg, lesson_saying("Catering work goes to the second person."))
    done = post(client, first, "just-this-time")
    assert done.status_code == 200, done.text
    found = store.read().get("lesson", first).data
    assert found["status"] == "discarded" and found["discard_reason"] == proposals.JUST_THIS_TIME_REASON
    assert [s.data["refs"] for s in signals(store, "just_this_time")] == [[first]]
    assert signals(store, "discarded") == [] and waiting(client)["proposals"] == []
    # The same correction proposed again is shown, with what was said before.
    again = proposal(store, cfg, lesson_saying("catering work goes to the second person"))
    assert again != first
    (shown,) = waiting(client)["proposals"]
    assert shown["id"] == again and shown["status"] == "proposed" and shown["just_this_time_before"] == 1
    # A proposal about something else has no mark.
    other = proposal(store, cfg, lesson_saying("Name the owner on every risk."))
    marks = {p["id"]: p["just_this_time_before"] for p in waiting(client)["proposals"]}
    assert marks == {again: 1, other: 0}
    # Undo puts the first back to proposed, and it no longer counts as set aside.
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert store.read().get("lesson", first).data["status"] == "proposed"
    marks = {p["id"]: p["just_this_time_before"] for p in waiting(client)["proposals"]}
    assert marks[again] == 0
    # Only a proposal can be set aside this way.
    assert post(client, person_adds(store, cfg, lesson_saying("Active one.")), "just-this-time").status_code == 409


# ---- a discarded proposal means don't act on it ---------------------------------------------------------------

TOPIC = "Cover finish decisions"
THIRD = next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] not in (PM, OTHER))
NOW_DT = datetime.fromisoformat(NOW)


def routing_op(topic=TOPIC, person=OTHER, **more):
    return {"op": "routing.add", "text": "Ask them about it.", "topic": topic, "person": person, **more}


def from_a_saved_input(ws, store, cfg, words, op):
    """Hand in an input that can be searched and propose `op` from it. Returns the input and the proposal."""
    source_id = hand_in(ws, store, pasted=words, now=NOW_DT).source
    cs_id, statuses = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=source_id, raw=words)
    assert statuses == ["applied"]
    return source_id, store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]


def search_inputs(ws, store, words):
    query = workspace_search.Query(words=words, kinds=("inputs",))
    return {h.id: h for h in workspace_search.search(ws, store, query, limit=10)}, query


def test_search_flags_an_input_whose_proposal_was_discarded_but_not_one_kept_or_set_aside(app):
    client, store, cfg, tmp_path = app
    ws = Workspace(tmp_path / "ws")
    gone, gone_entry = from_a_saved_input(
        ws, store, cfg, "Cover finish questions go to them, says the note.", routing_op()
    )
    aside, aside_entry = from_a_saved_input(
        ws,
        store,
        cfg,
        "Cover finish questions also go to them, says another note.",
        routing_op("Cover finish approvals"),
    )
    plain, _ = from_a_saved_input(ws, store, cfg, "Cover finish questions are still open, says a third note.", RULE)
    discarded = post(client, gone_entry, "discard")
    assert discarded.status_code == 200
    assert post(client, aside_entry, "just-this-time").status_code == 200
    day = signals(store, "discarded")[0].data["at"][:10]
    hits, query = search_inputs(ws, store, "cover finish questions")
    assert hits[gone].discarded == f"routing proposal discarded on {day}"
    assert hits[aside].discarded is None and hits[plain].discarded is None
    assert f"(routing proposal discarded on {day})" in workspace_search.render([hits[gone]], query, 1, 1)
    assert "discarded" not in workspace_search.render([hits[aside], hits[plain]], query, 1, 1)
    # Undoing the discard takes the flag away with it.
    undone = client.post(f"/api/changesets/{discarded.json()['changeset']}/undo", json={})
    assert undone.status_code == 200
    assert search_inputs(ws, store, "cover finish questions")[0][gone].discarded is None


def test_a_routing_that_matches_a_discarded_proposal_is_refused_unless_it_rests_on_the_persons_words(app):
    client, store, cfg, _ = app
    first = proposal(store, cfg, routing_op())
    assert post(client, first, "discard").status_code == 200

    def again(op, **how):
        return apply(store, cfg, [op], **{"origin": "input", "trust": "untrusted", "source_id": source(store), **how})

    cs_id, statuses = again(routing_op("Cover finish decision approvals"))  # the same topic, plurals folded
    assert statuses == ["refused"]
    assert first in reasons(store, cs_id)[0] and "own words" in reasons(store, cs_id)[0]
    for other in (
        routing_op("Print schedule dates"),  # another topic
        routing_op(person=THIRD),  # another person
        routing_op(negative=True),  # the opposite statement
        {**routing_op(), "person": None, "team": TEAM},  # another who
    ):
        assert again(other)[1] == ["applied"], other
    assert again(routing_op("Cover finish decision approvals"), origin="pm", trust="trusted")[1] == ["applied"]
    assert again(routing_op(), actor="pm", origin="pm", trust="trusted")[1] == ["applied"]
    # A proposal the person only set aside "just this time" is not a no.
    aside = proposal(store, cfg, routing_op("Schedule sign-off requests"))
    assert post(client, aside, "just-this-time").status_code == 200
    assert again(routing_op("Schedule sign-off requests"))[1] == ["applied"]
    # The setting decides how much of the topic must match.
    cfg.dispatch.knowledge.routing_match = 1.0
    assert again(routing_op("Cover finish approvals"))[1] == ["applied"]


# ---- one line for everything learned ----------------------------------------


def test_the_line_counts_both_origins_and_how_many_expired_since_the_person_last_looked(app):
    client, store, cfg, _ = app
    from_input = proposal(store, cfg, lesson_saying("From an input."))
    corrected = signal(store, "sent_back", [PROJECT], note="Wrong owner.")
    own = proposal(store, cfg, {**lesson_saying("From a correction."), "signal": corrected})
    second_corrected = signal(store, "undone", [PROJECT])
    kept_later = proposal(store, cfg, {**lesson_saying("Another correction."), "signal": second_corrected})
    listed = {p["id"]: p["came_from"] for p in waiting(client)["proposals"]}
    assert listed == {from_input: "input", own: "correction", kept_later: "correction"}
    line = queue(client)["learned"]
    assert (line["group"], line["count"], line["origins"], line["expired"]) == (
        "review",
        3,
        {"input": 1, "correction": 2},
        0,
    )
    # An input proposal expires; the corrections stay and the line says one expired.
    swept = proposals.expire_due(
        store, datetime.now(UTC) + timedelta(days=15), cfg.dispatch.knowledge.proposals_expire_days
    )
    assert swept == [from_input]
    line = queue(client)["learned"]
    assert (line["count"], line["origins"], line["expired"]) == (2, {"correction": 2}, 1)
    # Looking over one of them starts the count again.
    assert post(client, own, "keep").status_code == 200
    line = queue(client)["learned"]
    assert (line["count"], line["expired"]) == (1, 0)
    assert post(client, kept_later, "discard").status_code == 200
    assert "learned" not in queue(client)


def test_the_sweep_expires_input_proposals_after_the_days_and_never_correction_ones(app):
    client, store, cfg, _ = app
    days = cfg.dispatch.knowledge.proposals_expire_days
    assert days == 14
    from_input = proposal(store, cfg, lesson_saying("From an input."))
    rule = proposed_rule(store, cfg)
    corrected = signal(store, "sent_back", [PROJECT])
    own = proposal(store, cfg, {**lesson_saying("From a correction."), "signal": corrected})
    now = datetime.now(UTC)
    assert proposals.expire_due(store, now + timedelta(days=days - 1), days) == []
    assert sorted(proposals.expire_due(store, now + timedelta(days=days + 1), days)) == sorted([from_input, rule.id])
    assert store.read().get("lesson", from_input).data["status"] == "expired"
    assert store.read().get("rule", rule.id).data["status"] == "expired"
    assert store.read().get("lesson", own).data["status"] == "proposed"
    assert proposals.expire_due(store, now + timedelta(days=365), days) == []  # a correction never expires
    # The worker runs it once a day.
    worker = client.app.state.worker
    late = proposal(store, cfg, lesson_saying("Another input."))
    worker.now = lambda: now + timedelta(days=days + 1)
    assert worker.sweep_proposals_if_due() == [late]
    assert worker.sweep_proposals_if_due() == []


# ---- the catch-up list ----------


def test_the_catch_up_list_caps_and_ranks_the_corrections_from_before_and_is_made_once(app):
    client, store, cfg, _ = app
    elsewhere = second_project(store)
    for kind, refs in (
        ("undone", [PROJECT]),
        ("undone", [PROJECT]),
        ("undone", [PROJECT]),
        ("sent_back", [PROJECT]),
        ("sent_back", [PROJECT]),
        ("dropped", [elsewhere]),
        ("set_aside", [PROJECT]),  # mail set aside is never learned from
        ("kept", [PROJECT]),  # nor is what the person did to what was learned
    ):
        signal(store, kind, refs)
    found = catch_up.groups_of(store.read())
    assert [(g.key[0], g.count) for g in found] == [("undone", 3), ("sent_back", 2), ("dropped", 1)]
    chosen, left_out = catch_up.select(found, 2)
    assert [g.key[0] for g in chosen] == ["undone", "sent_back"] and left_out == 1
    # Made once, at the configured size, with the count left out.
    cfg.dispatch.knowledge.catch_up_max = 2
    catch_up.state_path(store).unlink()
    state = catch_up.start(store, cfg, datetime.now(UTC) + timedelta(minutes=1))
    assert [g.key[0] for g in state.groups] == ["undone", "sent_back"] and state.left_out == 1
    signal(store, "undone", [elsewhere])  # recorded after the list was made: not part of it
    again = catch_up.start(store, cfg, datetime.now(UTC) + timedelta(minutes=2))
    assert [g.key for g in again.groups] == [g.key for g in state.groups] and again.made_at == state.made_at
    # A kind of correction is learned from once: an entry that cites one of its corrections takes it off the list.
    assert [g.key[0] for g in catch_up.waiting(store.read(), state)] == ["undone", "sent_back"]
    proposal(store, cfg, {**lesson_saying("Learned from an undo."), "signal": state.groups[0].signals[0]})
    assert [g.key[0] for g in catch_up.waiting(store.read(), state)] == ["sent_back"]
    lines = queue(client)
    assert lines["catch_up"]["count"] == 1 and lines["catch_up"]["left_out"] == 1 and "learned" not in lines
    listed = client.get("/api/knowledge/catch-up").json()
    assert (listed["waiting"], listed["left_out"], listed["most"]) == (1, 1, 2)
    assert [p["text"] for p in listed["proposals"]] == ["Learned from an undo."]
