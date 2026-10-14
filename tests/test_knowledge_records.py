"""Knowledge as records (design 6.22, phase L1): lessons, glossary entries, routing entries and style notes, their ops,
the person's Keep, Discard and Retire, scopes with exclusions, and where each came from.

Nothing here reads knowledge into a packet; that is the next phase. Names and ids come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine import knowledge
from engine.applier import Context, Inputs, apply_changeset
from engine.config.schema import RuleScope
from engine.names import People
from engine.ops import CHANGESET, KNOWLEDGE_OPS
from engine.records import REGISTRY, GlossaryEntry, KnowledgeEvidence, Lesson, RoutingEntry, Scope, StyleNote
from engine.storage import WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip

PM = fixture_records(DEMO_B, "person")[0]["id"]
OTHER = fixture_records(DEMO_B, "person")[1]["id"]
TEAM = fixture_records(DEMO_B, "team")[0]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
PAGE = fixture_records(DEMO_B, "project")[0]["links"][0]["url"]
_TEST = WriteContext(actor="pm", trust="trusted", op="test.knowledge")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC).isoformat()
LESSON = {"op": "lesson.add", "text": "Questions about work another team owns wait for an impact check."}


@pytest.fixture
def app(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "knowledge-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer knowledge-token"}) as client:
        yield client, application.state.store, cfg, tmp_path


def second_project(store) -> str:
    with store.transaction() as tx:
        return tx.create("project", {"name": "A second project"}, _TEST).id


def source(store, **fields) -> str:
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": NOW,
                "kind": "pasted",
                "title": "An input",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                **fields,
            },
            _TEST,
        ).id


def request(store, origin: str, **fields) -> str:
    with store.transaction() as tx:
        return tx.create(
            "request", {"task": "notes", "origin": origin, "state": "done", "created_at": NOW, **fields}, _TEST
        ).id


def apply(store, cfg, ops, *, origin="pm", trust="trusted", source_id=None, actor="assistant", confirmed=False, raw=""):
    """Apply ops the way the applier does for a request of this origin: the changeset id and each op's status."""
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    request_id = request(store, origin, **({"source": source_id} if source_id else {}))
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request_id, source_id, raw, "", trust),
        confirmed_by_pm=confirmed,
        actor=actor,
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def reasons(store, cs_id) -> list[str | None]:
    return [o.get("reason") for o in store.read().get("changeset", cs_id).data["ops"]]


def added(store, cs_id) -> dict:
    record = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]
    return store.read().get(record["kind"], record["id"]).data


def person_adds(store, cfg, op=None):
    """An entry added from the person's own words: active at once. Returns its id."""
    cs_id, _ = apply(store, cfg, [op or LESSON], origin="pm")
    return store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]


def proposal(store, cfg, op=None):
    """An entry proposed from an input: waits for Keep. Returns its id."""
    cs_id, statuses = apply(store, cfg, [op or LESSON], origin="input", trust="untrusted", source_id=source(store))
    assert statuses == ["applied"]
    return store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]


def entry_of(client, entry_id):
    return next(e for e in client.get("/api/knowledge").json() if e["id"] == entry_id)


# ---- the records -----------------------------------------------------------------------------------------------------


def kept(**fields):
    return {
        "id": "X-1",
        "text": "An entry.",
        "origin": "person",
        "learned_at": NOW,
        "status": "active",
        "kept_by": PM,
        "kept_at": NOW,
        **fields,
    }


def test_the_four_kinds_are_core_records_with_their_own_fields_and_one_shape():
    assert knowledge.KINDS == ("lesson", "glossary_entry", "routing_entry", "style_note")
    lesson = Lesson.model_validate(kept(guard="Check the owner first.", signal="SIG-1"))
    glossary = GlossaryEntry.model_validate(kept(term="RTM", meaning="Release to manufacturing"))
    routing = RoutingEntry.model_validate(kept(topic="Print schedule", person=OTHER, negative=True, look_up="the plan"))
    style = StyleNote.model_validate(kept(audience=OTHER, observation="Replaces names with roles."))
    assert glossary.confidence == "assumed" and routing.negative and style.audience == OTHER and lesson.guard
    assert all(
        issubclass(REGISTRY[k], knowledge.KnowledgeRecord) and REGISTRY[k].data_level == "internal"
        for k in knowledge.KINDS
    )
    # Rules share the scope's shape: every field of a rule's target is one of a knowledge entry's.
    assert set(RuleScope.model_fields) <= set(Scope.model_fields)


def test_a_record_that_contradicts_itself_does_not_validate():
    proposed = {"origin": "input", "status": "proposed", "kept_by": None, "kept_at": None}
    assert Lesson.model_validate(kept(**proposed)).status == "proposed"
    for bad, why in [
        ({"kept_by": None}, "who kept it"),
        ({**proposed, "discard_reason": "no"}, "reason"),
        ({"pack": "a-pack"}, "names the pack"),
        ({"origin": "pack"}, "names the pack"),
        ({"text": ""}, "at least 1"),
        ({"evidence": {}}, "evidence names"),
        ({"applies_to": {"scope": "projects"}}, "names the projects"),
        ({"applies_to": {"projects": [PROJECT], "except": [PROJECT]}}, "left out"),
        ({"applies_to": {"scope": "workspace", "projects": [PROJECT]}}, "only when"),
    ]:
        with pytest.raises(ValidationError, match=why):
            Lesson.model_validate(kept(**bad))
    with pytest.raises(ValidationError, match="the person or the team"):
        RoutingEntry.model_validate(kept(topic="A topic"))
    assert Lesson.model_validate(kept(origin="pack", pack="a-pack")).pack == "a-pack"


def test_naming_projects_makes_the_scope_those_projects_and_except_is_its_own_key():
    assert Scope.model_validate({"projects": [PROJECT]}).scope == "projects"
    scope = Scope.model_validate({"except": [PROJECT]})
    assert scope.scope == "workspace" and scope.except_ == [PROJECT]
    dumped = scope.model_dump(mode="json", by_alias=True)
    assert dumped["except"] == [PROJECT] and "except_" not in dumped
    assert KnowledgeEvidence.model_validate({"quote": "the exact words"}).quote == "the exact words"


# ---- the ops ---------------------------------------------------------------------------------------------------------


def test_each_add_and_update_op_makes_and_changes_its_record(app):
    _, store, cfg, _ = app
    ops = [
        {"op": "lesson.add", "text": "A lesson.", "guard": "A guard.", "applies_to": {"task_kinds": ["notes"]}},
        {
            "op": "glossary.add",
            "text": "RTM is release to manufacturing.",
            "term": "RTM",
            "meaning": "Release to manufacturing",
            "confidence": "confirmed",
            "id_patterns": ["RTM-[0-9]+"],
            "project": PROJECT,
        },
        {"op": "routing.add", "text": "Ask them about the schedule.", "topic": "Schedule", "person": OTHER},
        {
            "op": "routing.add",
            "text": "They don't answer print questions.",
            "topic": "Print",
            "team": TEAM,
            "negative": True,
            "look_up": "the print plan",
        },
        {
            "op": "style.add",
            "text": "Prefers roles to names.",
            "audience": OTHER,
            "observation": "Replaces names with roles.",
        },
    ]
    cs_id, statuses = apply(store, cfg, ops, origin="pm")
    assert statuses == ["applied"] * 5, reasons(store, cs_id)
    records = [r for o in store.read().get("changeset", cs_id).data["ops"] for r in o["records"]]
    assert [r["kind"] for r in records] == ["lesson", "glossary_entry", "routing_entry", "routing_entry", "style_note"]
    lesson, glossary, route, negative, style = (store.read().get(r["kind"], r["id"]).data for r in records)
    assert lesson["guard"] == "A guard." and lesson["applies_to"]["task_kinds"] == ["notes"]
    assert (glossary["term"], glossary["confidence"], glossary["project"]) == ("RTM", "confirmed", PROJECT)
    assert glossary["id_patterns"] == ["RTM-[0-9]+"] and route["person"] == OTHER and not route["negative"]
    assert negative["negative"] and negative["team"] == TEAM and negative["look_up"] == "the print plan"
    assert style["audience"] == OTHER and style["observation"] == "Replaces names with roles."
    assert all(
        d["status"] == "active" and d["kept_by"] == PM and d["origin"] == "person"
        for d in (lesson, glossary, route, style)
    )

    ids = [r["id"] for r in records]
    cs_id, statuses = apply(
        store,
        cfg,
        [
            {"op": "lesson.update", "id": ids[0], "text": "A better lesson.", "applies_to": {"projects": [PROJECT]}},
            {"op": "glossary.update", "id": ids[1], "meaning": "Ready to make", "confidence": "assumed"},
        ],
        origin="pm",
    )
    assert statuses == ["applied", "applied"], reasons(store, cs_id)
    lesson, glossary = store.read().get("lesson", ids[0]).data, store.read().get("glossary_entry", ids[1]).data
    assert lesson["text"] == "A better lesson." and lesson["guard"] == "A guard."
    assert lesson["applies_to"]["scope"] == "projects" and lesson["applies_to"]["task_kinds"] == []
    assert (glossary["meaning"], glossary["confidence"], glossary["term"]) == ("Ready to make", "assumed", "RTM")


def test_an_update_names_something_and_only_changes_what_is_proposed_or_active(app):
    _, store, cfg, _ = app
    from engine.ops import OP_MODELS

    with pytest.raises(ValidationError, match="name what to change"):
        OP_MODELS["lesson.update"].model_validate({"op": "lesson.update", "id": "LES-1"})
    entry_id = person_adds(store, cfg)
    assert apply(store, cfg, [{"op": "knowledge.retire", "id": entry_id}], origin="pm")[1] == ["applied"]
    cs_id, statuses = apply(store, cfg, [{"op": "lesson.update", "id": entry_id, "text": "Again."}], origin="pm")
    assert statuses == ["refused"] and "retired" in reasons(store, cs_id)[0]
    cs_id, statuses = apply(store, cfg, [{"op": "knowledge.retire", "id": entry_id}], origin="pm")
    assert statuses == ["refused"] and "nothing to retire" in reasons(store, cs_id)[0]
    glossary_id = person_adds(store, cfg, {"op": "glossary.add", "text": "T.", "term": "T", "meaning": "M"})
    cs_id, statuses = apply(store, cfg, [{"op": "lesson.update", "id": glossary_id, "text": "No."}], origin="pm")
    assert statuses == ["refused"] and "isn't a lesson" in reasons(store, cs_id)[0]
    assert apply(store, cfg, [{"op": "knowledge.retire", "id": "NOTE-1"}], origin="pm")[1] == ["refused"]


def test_a_lesson_from_the_persons_own_words_is_active_at_once_and_from_an_input_it_is_proposed(app):
    _, store, cfg, _ = app
    own = store.read().get("lesson", person_adds(store, cfg)).data
    assert (own["status"], own["origin"], own["trust"], own["kept_by"]) == ("active", "person", "trusted", PM)
    assert own["kept_at"] and own["learned_at"]
    from_input = store.read().get("lesson", proposal(store, cfg)).data
    assert (from_input["status"], from_input["origin"], from_input["trust"]) == ("proposed", "input", "untrusted")
    assert from_input["kept_by"] is None and from_input["kept_at"] is None
    # The assistant's own generalization, with nothing outside behind it, is a proposal too.
    cs_id, statuses = apply(store, cfg, [LESSON], origin="schedule")
    assert statuses == ["applied"]
    assert added(store, cs_id)["status"] == "proposed" and added(store, cs_id)["origin"] == "assistant"
    # So is content the person reports on an item's button: a note typed there is not their rule.
    reported = source(store, kind="note:action", trust="trusted")
    cs_id, statuses = apply(store, cfg, [LESSON], origin="pm", source_id=reported)
    assert (
        statuses == ["applied"]
        and added(store, cs_id)["status"] == "proposed"
        and added(store, cs_id)["origin"] == "input"
    )


def test_changing_or_retiring_an_active_entry_from_anyone_but_the_person_waits_for_them(app):
    _, store, cfg, _ = app
    entry_id = person_adds(store, cfg)
    changing = [{"op": "lesson.update", "id": entry_id, "text": "Reworded by the assistant."}]
    cs_id, statuses = apply(store, cfg, changing, origin="input", trust="untrusted", source_id=source(store))
    assert statuses == ["held"] and "needs your confirmation" in reasons(store, cs_id)[0]
    cs_id, statuses = apply(store, cfg, [{"op": "knowledge.retire", "id": entry_id}], origin="schedule")
    assert statuses == ["held"]
    assert store.read().get("lesson", entry_id).data["status"] == "active" and "Reworded" not in str(
        store.read().get("lesson", entry_id).data
    )
    # The person releasing a held change applies it as theirs.
    from engine.applier import release

    release(store, cfg, cs_id, 0)
    assert store.read().get("lesson", entry_id).data["status"] == "retired"


def test_the_evidence_is_kept_apart_from_the_wording_and_names_where_it_came_from(app):
    _, store, cfg, _ = app
    src = source(store)
    with store.transaction() as tx:
        signal = tx.create("signal", {"kind": "sent_back", "refs": [], "at": NOW}, _TEST).id
    op = {**LESSON, "signal": signal, "evidence": {"quote": "some exact words"}}
    cs_id, statuses = apply(store, cfg, [op], origin="input", trust="untrusted", source_id=src, raw="nothing like it")
    assert statuses == ["refused"] and "isn't in the input" in reasons(store, cs_id)[0]
    cs_id, statuses = apply(
        store, cfg, [op], origin="input", trust="untrusted", source_id=src, raw="It said some exact words, once."
    )
    assert statuses == ["applied"]
    data = added(store, cs_id)
    request_id = store.read().get("changeset", cs_id).data["request"]
    assert data["text"] == LESSON["text"] and data["signal"] == signal
    assert data["evidence"] == {
        "quote": "some exact words",
        "source": src,
        "request": request_id,
        "signal": signal,
        "changeset": None,
    }
    # A correction that was about a change names that change.
    corrected, _ = apply(store, cfg, [{"op": "lesson.add", "text": "T."}], origin="pm")
    with store.transaction() as tx:
        sent_back = tx.create("signal", {"kind": "sent_back", "refs": [corrected], "at": NOW}, _TEST).id
    cs_id, _ = apply(store, cfg, [{**LESSON, "signal": sent_back}], origin="pm")
    assert added(store, cs_id)["evidence"]["changeset"] == corrected


def test_what_an_op_names_must_exist_and_the_scope_must_hold_together(app):
    _, store, cfg, _ = app
    for bad, why in [
        ({**LESSON, "applies_to": {"except": ["PRJ-999"]}}, "no project PRJ-999"),
        ({**LESSON, "applies_to": {"people": ["PER-999"]}}, "no person PER-999"),
        ({**LESSON, "signal": "SIG-999"}, "no signal SIG-999"),
        ({"op": "routing.add", "text": "T.", "topic": "T", "person": "PER-999"}, "no person PER-999"),
        ({"op": "routing.add", "text": "T.", "topic": "T"}, "the person or the team"),
        ({"op": "style.add", "text": "T.", "audience": "PER-999", "observation": "O"}, "no person PER-999"),
        ({"op": "glossary.add", "text": "T.", "term": "T", "meaning": "M", "project": "PRJ-999"}, "no project PRJ-999"),
    ]:
        cs_id, statuses = apply(store, cfg, [bad], origin="pm")
        assert statuses == ["refused"] and why in reasons(store, cs_id)[0], (bad, reasons(store, cs_id))
    with pytest.raises(ValidationError, match="names the projects"):
        CHANGESET.validate_python({"ops": [{**LESSON, "applies_to": {"scope": "projects"}}]})
    ok = {"op": "style.add", "text": "T.", "audience": "Printers, in general", "observation": "O"}
    assert apply(store, cfg, [ok], origin="pm")[1] == ["applied"]


def test_undo_of_each_op_takes_the_change_back(app):
    _, store, cfg, _ = app
    cs_id, statuses = apply(store, cfg, [LESSON], origin="pm")
    entry_id = store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]
    from engine.applier import undo

    assert undo(store, cs_id).restored == [0]
    assert store.read().get("lesson", entry_id) is None  # an add is undone: the entry is gone, its id is not reused
    entry_id = person_adds(store, cfg)
    cs_id, _ = apply(
        store, cfg, [{"op": "lesson.update", "id": entry_id, "text": "Changed.", "guard": "Guard."}], origin="pm"
    )
    assert undo(store, cs_id).restored == [0]
    assert (
        store.read().get("lesson", entry_id).data["text"] == LESSON["text"]
        and store.read().get("lesson", entry_id).data["guard"] is None
    )
    cs_id, _ = apply(store, cfg, [{"op": "knowledge.retire", "id": entry_id}], origin="pm")
    assert store.read().get("lesson", entry_id).data["status"] == "retired"
    assert undo(store, cs_id).restored == [0]
    assert store.read().get("lesson", entry_id).data["status"] == "active"


def test_the_learning_ops_are_neither_offered_when_reading_notes_nor_to_a_plugins_action(app):
    _, store, _, _ = app
    from engine.actions import ACTION_CORE_OPS
    from engine.tasks import TASKS

    assert set(store.plugins.ops) >= KNOWLEDGE_OPS and not KNOWLEDGE_OPS & ACTION_CORE_OPS
    assert not KNOWLEDGE_OPS & set(TASKS["notes"].ops) and not KNOWLEDGE_OPS & set(TASKS["ask"].ops)
    assert {store.plugins.tiers[name] for name in KNOWLEDGE_OPS} == {"system"}


# ---- the person's Keep, Discard and Retire ---------------------------------------------------------------------------


def signals(store, kind):
    return [s for s in store.read().list("signal") if s.data["kind"] == kind]


def test_keep_with_an_edited_text_makes_it_active_and_the_person_its_author(app):
    client, store, cfg, _ = app
    entry_id = proposal(store, cfg)
    row = entry_of(client, entry_id)
    assert row["status"] == "proposed" and row["learned_from"] == "input" and row["kept_by"] is None
    kept_body = {
        "read_version": row["version"],
        "text": "My own wording of the lesson.",
        "applies_to": {"except": [second_project(store)]},
    }
    done = client.post(f"/api/knowledge/{entry_id}/keep", json=kept_body)
    assert done.status_code == 200, done.text
    row = entry_of(client, entry_id)
    assert (row["status"], row["kept_by"], row["text"]) == ("active", PM, "My own wording of the lesson.")
    assert row["kept_at"] and row["learned_from"] == "input" and row["trust"] == "untrusted"
    assert (
        row["applies_to"]["scope"] == "workspace" and row["applies_to"]["except"] == kept_body["applies_to"]["except"]
    )
    assert [s.data["refs"] for s in signals(store, "kept")] == [[entry_id]]
    undone = client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={})
    assert undone.status_code == 200 and undone.json()["restored"]
    row = entry_of(client, entry_id)
    assert row["status"] == "proposed" and row["kept_by"] is None and row["text"] == LESSON["text"]
    assert row["applies_to"]["except"] == [] and len(signals(store, "kept")) == 1  # undoing records no signal
    stale = client.post(f"/api/knowledge/{entry_id}/keep", json={"read_version": row["version"] - 1})
    assert stale.status_code == 409 and "changed since" in stale.json()["detail"]
    assert client.post("/api/knowledge/LES-99/keep", json={"read_version": 1}).status_code == 404
    assert client.post("/api/knowledge/NOTE-1/keep", json={"read_version": 1}).status_code == 404


def test_only_a_proposal_can_be_kept_and_where_an_entry_came_from_cannot_be_edited(app):
    client, store, cfg, _ = app
    entry_id = proposal(store, cfg)
    row = entry_of(client, entry_id)
    assert client.post(f"/api/knowledge/{entry_id}/keep", json={"read_version": row["version"]}).status_code == 200
    again = client.post(f"/api/knowledge/{entry_id}/keep", json={"read_version": entry_of(client, entry_id)["version"]})
    assert again.status_code == 409 and "isn't waiting" in again.json()["detail"]
    # Where an entry came from can't be rewritten by an edit, the person's included.
    edit = {
        "op": "record.edit",
        "record": {"kind": "lesson", "id": entry_id},
        "fields": {"origin": "person", "trust": "trusted"},
    }
    cs_id, statuses = apply(
        store,
        cfg,
        [{**edit, "read_version": entry_of(client, entry_id)["version"]}],
        origin="pm",
        confirmed=True,
        actor="pm",
    )
    assert statuses == ["refused"] and "can't be changed this way" in reasons(store, cs_id)[0]


def test_discard_keeps_the_proposal_with_its_reason_and_undo_brings_it_back(app):
    client, store, cfg, _ = app
    entry_id = proposal(store, cfg)
    row = entry_of(client, entry_id)
    done = client.post(
        f"/api/knowledge/{entry_id}/discard", json={"read_version": row["version"], "reason": "  Too broad. "}
    )
    assert done.status_code == 200, done.text
    row = entry_of(client, entry_id)
    assert (row["status"], row["discard_reason"], row["kept_by"]) == ("discarded", "Too broad.", None)
    assert [s.data["refs"] for s in signals(store, "discarded")] == [[entry_id]]
    assert signals(store, "discarded")[0].data["note"] is None
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    row = entry_of(client, entry_id)
    assert row["status"] == "proposed" and row["discard_reason"] is None
    # With no reason given, none is kept; and a discarded entry can't be discarded or kept again.
    assert client.post(f"/api/knowledge/{entry_id}/discard", json={"read_version": row["version"]}).status_code == 200
    row = entry_of(client, entry_id)
    assert row["status"] == "discarded" and row["discard_reason"] is None
    assert client.post(f"/api/knowledge/{entry_id}/keep", json={"read_version": row["version"]}).status_code == 409
    assert client.post(f"/api/knowledge/{entry_id}/discard", json={"read_version": row["version"]}).status_code == 409


def test_retire_ends_an_active_entry_and_undo_makes_it_active_again(app):
    client, store, cfg, _ = app
    entry_id = person_adds(store, cfg)
    row = entry_of(client, entry_id)
    done = client.post(f"/api/knowledge/{entry_id}/retire", json={"read_version": row["version"]})
    assert done.status_code == 200, done.text
    row = entry_of(client, entry_id)
    assert row["status"] == "retired" and row["kept_by"] == PM and row["text"] == LESSON["text"]
    assert [s.data["refs"] for s in signals(store, "retired")] == [[entry_id]]
    assert client.post(f"/api/knowledge/{entry_id}/retire", json={"read_version": row["version"]}).status_code == 409
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert entry_of(client, entry_id)["status"] == "active"
    proposed = proposal(store, cfg)
    refused = client.post(
        f"/api/knowledge/{proposed}/retire", json={"read_version": entry_of(client, proposed)["version"]}
    )
    assert refused.status_code == 409 and "nothing to retire" in refused.json()["detail"]


def test_keeping_needs_the_person_to_be_known(app):
    client, store, cfg, _ = app
    entry_id = proposal(store, cfg)
    cfg.workspace.user.person = None
    row = entry_of(client, entry_id)
    refused = client.post(f"/api/knowledge/{entry_id}/keep", json={"read_version": row["version"]})
    assert refused.status_code == 409 and "Say who you are first" in refused.json()["detail"]


# ---- the list, and where each came from ------------------------------------------------------------------------------


def test_the_list_filters_by_kind_and_status_and_carries_each_entrys_own_fields(app):
    client, store, cfg, _ = app
    person_adds(store, cfg)
    person_adds(store, cfg, {"op": "glossary.add", "text": "T.", "term": "TERM", "meaning": "Means this"})
    person_adds(store, cfg, {"op": "routing.add", "text": "R.", "topic": "Topic", "person": OTHER, "negative": True})
    proposed = proposal(store, cfg, {"op": "style.add", "text": "S.", "audience": OTHER, "observation": "Brief."})
    allof = client.get("/api/knowledge").json()
    assert [e["kind"] for e in allof].count("lesson") == 1 and len(allof) == 4
    assert [e["id"] for e in client.get("/api/knowledge", params={"status": "proposed"}).json()] == [proposed]
    assert {e["kind"] for e in client.get("/api/knowledge", params={"status": "active"}).json()} == {
        "lesson",
        "glossary_entry",
        "routing_entry",
    }
    glossary = client.get("/api/knowledge", params={"kind": "glossary_entry"}).json()
    assert [(e["term"], e["meaning"], e["confidence"], e["guard"]) for e in glossary] == [
        ("TERM", "Means this", "assumed", None)
    ]
    routing = client.get("/api/knowledge", params={"kind": "routing_entry", "status": "active"}).json()
    assert routing[0]["person"] == OTHER and routing[0]["negative"] is True and routing[0]["team"] is None
    assert client.get("/api/knowledge", params={"kind": "lesson", "status": "retired"}).json() == []
    assert client.get("/api/knowledge", params={"kind": "fact"}).status_code == 422
    assert client.get("/api/knowledge", params={"status": "pending"}).status_code == 422


def test_the_origin_of_an_entry_is_the_page_else_the_saved_text_else_the_change_and_its_request(app):
    client, store, cfg, _ = app
    from engine.origin import origins

    def added_id(cs_id):
        return store.read().get("changeset", cs_id).data["ops"][0]["records"][0]["id"]

    def propose(**src):
        source_id = source(store, **src)
        op = {**LESSON, "evidence": {"quote": "an exact quote"}}
        cs_id, statuses = apply(
            store, cfg, [op], origin="input", trust="untrusted", source_id=source_id, raw="an exact quote"
        )
        assert statuses == ["applied"]
        return added_id(cs_id), source_id

    # An input with a page: the link. The address is read from the source the evidence names.
    with_page, with_page_source = propose(url=PAGE)
    assert entry_of(client, with_page)["origin"] == {
        "kind": "link",
        "url": PAGE,
        "source": with_page_source,
        "changeset": None,
        "request": None,
    }
    # An input saved with no page of its own: its saved text.
    saved, saved_source = propose()
    assert entry_of(client, saved)["origin"]["kind"] == "source"
    assert entry_of(client, saved)["origin"]["source"] == saved_source
    # No input behind it: the change that made it and the request behind that change.
    cs_id, _ = apply(store, cfg, [LESSON], origin="pm")
    own = added_id(cs_id)
    request_id = store.read().get("changeset", cs_id).data["request"]
    assert entry_of(client, own)["origin"] == {
        "kind": "change",
        "url": None,
        "source": None,
        "changeset": cs_id,
        "request": request_id,
    }
    assert origins(store.read(), "lesson", [own, "LES-99"])["LES-99"] is None
    # An entry made with no history behind it shows no link.
    with store.transaction() as tx:
        bare = tx.create(
            "lesson",
            {"text": "T.", "origin": "seed", "learned_at": NOW},
            WriteContext("import", "trusted", "import"),
        ).id
        tx.sql("DELETE FROM ledger WHERE record_id=?", (bare,))
    assert entry_of(client, bare)["origin"] is None


# ---- exclusions, and the export -------------------------------------------------------------------------------------


def test_everywhere_except_a_project_round_trips_through_the_record_the_api_and_the_export(app):
    client, store, cfg, tmp_path = app
    spare = second_project(store)
    entry_id = person_adds(store, cfg, {**LESSON, "applies_to": {"except": [spare], "task_kinds": ["notes"]}})
    stored = store.read().get("lesson", entry_id).data["applies_to"]
    assert stored["scope"] == "workspace" and stored["except"] == [spare] and "except_" not in stored
    assert entry_of(client, entry_id)["applies_to"]["except"] == [spare]
    refused, _ = apply(
        store, cfg, [{"op": "lesson.update", "id": entry_id, "applies_to": {"except": ["PRJ-999"]}}], origin="pm"
    )
    assert reasons(store, refused) == ["there is no project PRJ-999"]
    # A project an entry names is still in use: it can't be deleted from under it.
    from engine.records import referrers

    assert ("lesson", entry_id) in referrers(store.read(), "project", spare)
    report = round_trip(store, cfg, tmp_path / "round-trip")
    assert report["differences"] == [], report
    from engine.storage import Store
    from engine.storage.export import import_data

    fresh = Store(tmp_path / "again.db", cfg=cfg)
    try:
        import_data(fresh, tmp_path / "round-trip" / "export-1")
        assert fresh.read().get("lesson", entry_id).data == store.read().get("lesson", entry_id).data
        assert fresh.read().get("lesson", entry_id).data["applies_to"]["except"] == [spare]
    finally:
        fresh.close()


def test_every_kind_of_knowledge_is_in_the_export_and_loads_back(app):
    client, store, cfg, tmp_path = app
    person_adds(store, cfg)
    person_adds(
        store, cfg, {"op": "glossary.add", "text": "T.", "term": "T", "meaning": "M", "id_patterns": ["T-[0-9]+"]}
    )
    person_adds(store, cfg, {"op": "routing.add", "text": "R.", "topic": "Topic", "person": OTHER, "negative": True})
    kept_id = proposal(store, cfg, {"op": "style.add", "text": "S.", "audience": OTHER, "observation": "Brief."})
    row = entry_of(client, kept_id)
    client.post(f"/api/knowledge/{kept_id}/keep", json={"read_version": row["version"], "text": "Edited."})
    report = round_trip(store, cfg, tmp_path / "round-trip")
    assert report["differences"] == [], report
    exported = {p.stem for p in (tmp_path / "round-trip" / "export-1").glob("*.json")}
    assert set(knowledge.KINDS) <= exported
