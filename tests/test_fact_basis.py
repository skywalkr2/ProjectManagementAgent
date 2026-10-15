"""How a fact is known (design 6.19): a fact says who it rests on, and an inference only feeds the record: it never
closes anything and never changes a date, an owner or a routing without the person's click.

Names and ids come from the fixtures.
"""

from __future__ import annotations

from engine.applier import Context, Inputs, apply_changeset, release
from engine.names import People
from engine.ops import CHANGESET
from engine.tasks import TASKS
from tests.conftest import DEMO_B, fixture_records
from tests.test_knowledge_records import (  # noqa: F401  (the fixture is used by name)
    app,
    apply,
    reasons,
    request,
    source,
)

PEOPLE = fixture_records(DEMO_B, "person")
PM = PEOPLE[0]["id"]
OTHER = PEOPLE[1]
ACTION = fixture_records(DEMO_B, "action")[0]["id"]
QUESTION = fixture_records(DEMO_B, "question")[0]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
LINE = "The printer wrote that the interior file went out with the afternoon batch."
FROM = f"From: {OTHER['full_name']}\nSubject: Interior file\n\n{LINE}"


def fact(**more):
    return {"op": "fact", "text": "The interior file went out.", "evidence": {"quote": LINE}, **more}


def made(store, cs_id, index=0):
    (touched,) = store.read().get("changeset", cs_id).data["ops"][index]["records"]
    return store.read().get(touched["kind"], touched["id"]).data


def from_outside(store, cfg, ops, raw=FROM):
    return apply(store, cfg, ops, origin="input", trust="untrusted", source_id=source(store), raw=raw)


def from_the_person(store, cfg, ops):
    """The person's own typed note: its words are the note, with no outside source."""
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request(store, "pm"), None, "", LINE, "trusted"),
    )
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


# ---- who a fact rests on ---------------------------------------------------------------------------------------------


def test_a_fact_from_the_persons_note_rests_on_the_person_and_one_from_outside_on_its_sender(app):  # noqa: F811
    _, store, cfg, _ = app
    cs_id, _ = from_the_person(store, cfg, [fact()])
    assert (made(store, cs_id)["basis"], made(store, cs_id)["said_by"]) == ("person", None)
    cs_id, _ = from_outside(store, cfg, [fact()])
    assert (made(store, cs_id)["basis"], made(store, cs_id)["said_by"]) == ("said", OTHER["id"])


def test_a_fact_from_outside_with_no_known_sender_is_said_by_nobody_named(app):  # noqa: F811
    _, store, cfg, _ = app
    cs_id, _ = from_outside(store, cfg, [fact()], raw=LINE)
    assert (made(store, cs_id)["basis"], made(store, cs_id)["said_by"]) == ("said", None)


def test_the_model_can_mark_a_fact_inferred_or_name_who_said_it(app):  # noqa: F811
    _, store, cfg, _ = app
    for run in (from_the_person, from_outside):
        cs_id, statuses = run(store, cfg, [fact(basis="inferred")])
        assert statuses == ["applied"] and made(store, cs_id)["basis"] == "inferred"
        assert made(store, cs_id)["said_by"] is None
    cs_id, _ = from_the_person(store, cfg, [fact(basis="said", said_by=OTHER["full_name"])])
    assert (made(store, cs_id)["basis"], made(store, cs_id)["said_by"]) == ("said", OTHER["id"])


def test_who_said_it_must_be_one_known_person_and_goes_with_basis_said(app):  # noqa: F811
    _, store, cfg, _ = app
    cs_id, statuses = from_the_person(store, cfg, [fact(basis="said", said_by="Nobody Atall")])
    assert statuses == ["refused"] and "isn't one known person" in reasons(store, cs_id)[0]
    cs_id, statuses = from_the_person(store, cfg, [fact(said_by=OTHER["full_name"])])
    assert statuses == ["refused"] and "goes with basis said" in reasons(store, cs_id)[0]


# ---- an inference never closes anything ------------------------------------------------------------------------------


def done(op, **more):
    quote = {"evidence": {"quote": LINE}}
    return {
        "action": {"op": "action.close", "id": ACTION, **quote},
        "question": {"op": "question.done", "id": QUESTION, "answer": "It went out.", **quote},
    }[op] | more


def test_a_close_that_rests_only_on_an_inference_is_held_with_a_plain_reason_and_one_click_closes_it(app):  # noqa: F811
    _, store, cfg, _ = app
    for kind, record in (("action", ACTION), ("question", QUESTION)):
        cs_id, statuses = from_outside(store, cfg, [fact(basis="inferred"), done(kind)])
        assert statuses == ["applied", "held"]
        assert reasons(store, cs_id)[1] == "This rests on something worked out, not something anyone said: close it?"
        assert store.read().get(kind, record).data["status"] not in ("done", "answered")
        release(store, cfg, cs_id, 1)
        assert store.read().get(kind, record).data["status"] in ("done", "answered")


def test_a_close_that_rests_on_something_said_or_on_the_persons_own_note_applies_at_once(app):  # noqa: F811
    _, store, cfg, _ = app
    _, statuses = from_outside(store, cfg, [fact(), done("action")])
    assert statuses == ["applied", "applied"]
    # the person's own deduction closes it as theirs
    _, statuses = from_the_person(store, cfg, [fact(), done("question")])
    assert statuses == ["applied", "applied"]


def test_a_close_shares_nothing_with_an_inference_when_it_quotes_other_words_and_is_not_held(app):  # noqa: F811
    _, store, cfg, _ = app
    other = {"evidence": {"quote": "Delivered"}}
    raw = f"{FROM}\nDelivered"
    _, statuses = from_outside(store, cfg, [fact(basis="inferred"), done("action", **other)], raw=raw)
    assert statuses == ["applied", "applied"]


def test_a_close_resting_on_an_inference_and_on_something_said_is_not_held(app):  # noqa: F811
    _, store, cfg, _ = app
    _, statuses = from_outside(store, cfg, [fact(basis="inferred"), fact(), done("action")])
    assert statuses == ["applied", "applied", "applied"]


# ---- an inference never changes a date, an owner or a routing --------------------------------------------------------


def test_a_date_an_owner_or_a_routing_resting_only_on_an_inference_is_held(app):  # noqa: F811
    _, store, cfg, _ = app
    due = {"op": "record.set", "kind": "action", "id": ACTION, "field": "due", "value": "2026-11-01"}
    owner = {"op": "record.set", "kind": "project", "id": PROJECT, "field": "owner", "value": OTHER["id"]}
    routing = {"op": "routing.add", "text": "T.", "topic": "the printer", "person": PEOPLE[2]["id"]}
    for op in (due, owner, routing):
        cs_id, statuses = from_outside(store, cfg, [fact(basis="inferred"), {**op, "evidence": {"quote": LINE}}])
        assert statuses == ["applied", "held"], op["op"]
        assert reasons(store, cs_id)[1].startswith("This rests on something worked out")
    assert store.read().get("action", ACTION).data["due"] == fixture_records(DEMO_B, "action")[0]["due"]
    assert store.read().get("project", PROJECT).data["owner"] == PM


def test_the_same_changes_resting_on_something_said_apply_and_other_fields_are_not_held(app):  # noqa: F811
    _, store, cfg, _ = app
    due = {"op": "record.set", "kind": "action", "id": ACTION, "field": "due", "value": "2026-11-01"}
    _, statuses = from_outside(store, cfg, [fact(), {**due, "evidence": {"quote": LINE}}])
    assert statuses == ["applied", "applied"]
    notes = {"op": "record.set", "kind": "action", "id": ACTION, "field": "notes", "value": "Went out."}
    _, statuses = from_outside(store, cfg, [fact(basis="inferred"), {**notes, "evidence": {"quote": LINE}}])
    assert statuses == ["applied", "applied"]


def test_the_person_confirming_a_held_change_makes_it_and_the_inferred_fact_stays_marked(app):  # noqa: F811
    _, store, cfg, _ = app
    due = {"op": "record.set", "kind": "action", "id": ACTION, "field": "due", "value": "2026-11-01"}
    cs_id, _ = from_outside(store, cfg, [fact(basis="inferred"), {**due, "evidence": {"quote": LINE}}])
    release(store, cfg, cs_id, 1)
    assert store.read().get("action", ACTION).data["due"] == "2026-11-01"
    assert made(store, cs_id)["basis"] == "inferred"


# ---- "I asked them to confirm" ------------------------------------------------------------------------------------


def test_reading_notes_is_offered_the_mark_as_asked_op_and_an_ask_is_not():
    assert "question.mark_sent" in TASKS["notes"].ops
    assert "question.mark_sent" not in TASKS["ask"].ops


def test_a_note_saying_the_person_already_asked_files_the_question_as_asked(app):  # noqa: F811
    _, store, cfg, _ = app
    asked = {"op": "question.mark_sent", "id": QUESTION}
    cs_id, statuses = from_the_person(store, cfg, [asked])
    assert statuses == ["applied"]
    assert store.read().get("question", QUESTION).data["status"] == "sent"
    cs_id, statuses = from_outside(
        store, cfg, [{"op": "question.mark_sent", "id": fixture_records(DEMO_B, "question")[1]["id"]}]
    )
    assert statuses == ["refused"] and "only the person" in reasons(store, cs_id)[0]


def test_the_notes_prompt_says_when_a_fact_is_inferred_and_when_to_mark_a_question_asked():
    from pathlib import Path

    text = (Path(__file__).parent.parent / "engine" / "prompts" / "notes.md").read_text(encoding="utf-8")
    assert '"basis": "inferred"' in text and "waits for the PM" in text
    assert "question.mark_sent" in text


# ---- a series fact ------------------------------------------------------------------------------------------------


def test_a_fact_marked_to_reach_the_projects_inside_its_own_is_kept_so_and_needs_its_project(app):  # noqa: F811
    _, store, cfg, _ = app
    cs_id, statuses = from_the_person(store, cfg, [fact(project=PROJECT, reaches_children=True)])
    assert statuses == ["applied"] and made(store, cs_id)["reaches_children"] is True
    cs_id, _ = from_the_person(store, cfg, [fact(project=PROJECT)])
    assert made(store, cs_id)["reaches_children"] is False
    cs_id, statuses = from_the_person(store, cfg, [fact(reaches_children=True)])
    assert statuses == ["refused"] and "needs the project" in reasons(store, cs_id)[0]
