"""What the screens need to show learning on a correction's card (design 7.18): the line for each correction (still
learning, a proposal, the person's own words kept at once), the change a proposal was learned from, and the knowledge a
run applied on its changeset. Names and ids come from the fixtures; the AI is the stub.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.dispatcher import send_back
from engine.records import REGISTRY
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_knowledge_records import apply, lesson_saying, person_adds
from tests.test_learn_correction import (
    NOW,
    interior,
    learning,
    lesson_answer,
    run_learning,
    scripted,
)

NOTE = "Interior files go to the editor first."
_TEST = WriteContext(actor="pm", trust="trusted", op="test.learned")


@pytest.fixture
def app(tmp_path):
    from engine.ai.adapters.stub import set_responder

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "learned-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer learned-token"}) as client:
        yield client, (ws, cfg, application.state.store)
    set_responder(None)


def lines(client):
    return client.get("/api/knowledge/learned").json()["lines"]


def test_a_send_back_is_a_learning_line_then_a_proposal_that_names_the_change_it_was_learned_from(app):
    client, env = app
    store = env[2]
    cs_id, _, _ = interior(env)
    assert lines(client) == []
    send_back(store, cs_id, NOTE, now=NOW)
    (queued,) = learning(store)
    (line,) = lines(client)
    assert (line["state"], line["kind"], line["changeset"]) == ("learning", "sent_back", cs_id)
    assert line["proposal"] is None and line["waiting"] == queued.data["waiting"]
    scripted(lesson_answer("go to the editor first"))
    run_learning(env, queued.id)
    (line,) = lines(client)
    assert (line["state"], line["changeset"], line["signal"]) == (
        "proposed",
        cs_id,
        line["proposal"]["evidence"]["signal"],
    )
    assert line["proposal"]["status"] == "proposed" and line["proposal"]["from_changeset"] == cs_id
    assert line["proposal"]["batch"] == "daily" and line["proposal"]["evidence"]["quote"] == "go to the editor first"
    # The proposals list carries the same link, and the redo of the sent-back work points back at the corrected change.
    listed = client.get("/api/knowledge/proposals").json()["proposals"]
    assert [p["from_changeset"] for p in listed] == [cs_id]
    redo = next(c for c in client.get("/api/changes").json() if c["redoes"])
    assert redo["redoes"] == cs_id


def test_a_proposal_that_came_from_an_input_names_no_change_and_has_no_line(app):
    client, env = app
    store = env[2]
    from tests.test_knowledge_records import proposal

    proposal(store, env[1])
    (listed,) = client.get("/api/knowledge/proposals").json()["proposals"]
    assert listed["from_changeset"] is None
    assert lines(client) == []


def test_the_persons_own_words_kept_at_once_are_a_line_with_the_change_to_undo(app):
    client, env = app
    store = env[2]
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, NOTE, now=NOW)
    (queued,) = learning(store)
    signal_id = queued.data["about"]["id"]
    own = person_adds(store, env[1], {**lesson_saying("My own rule."), "signal": signal_id})
    (line,) = lines(client)
    assert line["state"] == "kept" and line["proposal"]["id"] == own and line["proposal"]["status"] == "active"
    created = store.read().ledger(kind="lesson", record_id=own)[0]["changeset"]
    assert line["undo"] == created


def test_the_changes_view_carries_what_a_run_applied_and_the_account_it_first_ran_on(app):
    client, env = app
    store = env[2]
    cs_id, _, _ = interior(env)
    entry = person_adds(store, env[1], lesson_saying("Name the editor first."))
    with store.transaction() as tx:
        found = tx.get("changeset", cs_id)
        tx.update(
            "changeset",
            cs_id,
            {"applied": [entry, "NOPE-9"], "first_on_account": "second"},
            _TEST,
            read_version=found.version,
        )
    item = next(c for c in client.get("/api/changes").json() if c["changeset"] and c["changeset"]["id"] == cs_id)
    shown = item["changeset"]
    assert shown["first_on_account"] == "second"
    (applied,) = shown["applied"]
    stored = store.read().get("lesson", entry)
    assert (applied["id"], applied["kind"], applied["text"], applied["status"]) == (
        entry,
        "lesson",
        "Name the editor first.",
        "active",
    )
    assert applied["version"] == stored.version and applied["applies_to"]["scope"] == "workspace"


def test_an_applied_rule_or_fact_is_listed_with_its_kind(app):
    client, env = app
    store = env[2]
    cs_id, _, _ = interior(env)
    rule_cs, _ = apply(store, env[1], [{"op": "rule.add", "text": "Every risk names who raised it."}], origin="pm")
    rule = store.read().get("changeset", rule_cs).data["ops"][0]["records"][0]["id"]
    with store.transaction() as tx:
        fact = tx.create("fact", {"text": "The interior is due on the 16th."}, _TEST).id
        found = tx.get("changeset", cs_id)
        tx.update("changeset", cs_id, {"applied": [rule, fact]}, _TEST, read_version=found.version)
    item = next(c for c in client.get("/api/changes").json() if c["changeset"] and c["changeset"]["id"] == cs_id)
    kinds = {a["id"]: a["kind"] for a in item["changeset"]["applied"]}
    assert kinds == {rule: "rule", fact: "fact"}
    (the_fact,) = [a for a in item["changeset"]["applied"] if a["kind"] == "fact"]
    assert the_fact["applies_to"] is None and the_fact["id"].startswith(REGISTRY["fact"].prefix)


# ---- "Overlaps with" (design 7.18) ----------------------------------------------------------------------------

_MERGE = WriteContext(actor="pm", trust="trusted", op="test.overlap")


def waiting(client, entry_id):
    return next(p for p in client.get("/api/knowledge/proposals").json()["proposals"] if p["id"] == entry_id)


def entry(store, kind, data):
    from datetime import UTC, datetime

    from tests.test_knowledge_records import PM

    now = datetime(2026, 10, 14, 9, 0, tzinfo=UTC).isoformat()
    base = {"origin": "input", "status": "proposed", "learned_at": now, "trust": "trusted", "applies_to": {}}
    if data.get("status") == "active":
        base |= {"origin": "person", "kept_by": PM, "kept_at": now}
    with store.transaction() as tx:
        return tx.create(kind, {**base, **data}, _MERGE).id


def test_a_proposal_that_says_what_an_entry_already_says_names_the_entry_it_would_merge_with(app):
    client, env = app
    store = env[2]
    kept = entry(store, "lesson", {"text": NOTE, "status": "active"})
    waits = entry(store, "lesson", {"text": NOTE})
    overlap = waiting(client, waits)["overlaps_with"]
    assert overlap == {"id": kept, "kind": "lesson", "text": NOTE, "status": "active"}
    # the entry that is kept is not itself waiting, and a proposal never overlaps itself
    assert kept not in [p["id"] for p in client.get("/api/knowledge/proposals").json()["proposals"]]


def test_a_proposal_over_other_projects_or_other_words_overlaps_nothing(app):
    client, env = app
    store = env[2]
    from tests.test_knowledge_records import PROJECT, second_project

    other = second_project(store)
    entry(
        store, "lesson", {"text": NOTE, "status": "active", "applies_to": {"scope": "projects", "projects": [PROJECT]}}
    )
    apart = entry(store, "lesson", {"text": NOTE, "applies_to": {"scope": "projects", "projects": [other]}})
    different = entry(store, "lesson", {"text": "Covers go to the designer first."})
    assert waiting(client, apart)["overlaps_with"] is None
    assert waiting(client, different)["overlaps_with"] is None


def test_a_meaning_proposed_beside_a_term_the_person_kept_as_unknown_names_that_term(app):
    client, env = app
    store, cfg = env[2], env[1]
    from tests.test_knowledge_records import person_adds, proposal

    unknown = person_adds(
        store,
        cfg,
        {
            "op": "glossary.add",
            "text": "Gutter: not known yet.",
            "term": "Gutter",
            "meaning": "not known",
            "confidence": "unknown",
        },
    )
    meaning = proposal(
        store,
        cfg,
        {"op": "glossary.add", "text": "Gutter: the inner margin.", "term": "Gutter", "meaning": "the inner margin"},
    )
    assert meaning != unknown
    overlap = waiting(client, meaning)["overlaps_with"]
    assert overlap["id"] == unknown and overlap["kind"] == "glossary_entry" and overlap["status"] == "active"


def test_the_learned_line_carries_the_overlap_too(app):
    client, env = app
    store = env[2]
    cs_id, _, _ = interior(env)
    send_back(store, cs_id, NOTE, now=NOW)
    (queued,) = learning(store)
    scripted(lesson_answer("go to the editor first"))
    run_learning(env, queued.id)
    (line,) = lines(client)
    assert line["state"] == "proposed" and line["proposal"]["overlaps_with"] is None
    # the person kept the same wording elsewhere in the meantime: the line now says which entry it would merge with
    kept = entry(store, "lesson", {"text": line["proposal"]["text"], "status": "active"})
    (line,) = lines(client)
    assert line["proposal"]["overlaps_with"]["id"] == kept
