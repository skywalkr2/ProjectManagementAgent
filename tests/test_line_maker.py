"""Who made the item a Today line is about (design 7.7; change log 181): read from the change that made the item and
from the item, never stored, and never part of anything copied, shared or sent.

Names, ids and addresses come from the fixtures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import line_maker, outward
from engine.storage import Store, WriteContext
from engine.storage.export import export_data
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_today_queue import api as queue_api  # noqa: F401
from tests.test_today_queue import hand_in

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
PERSON = fixture_records(DEMO_B, "person")[0]["id"]
PAGE = fixture_records(DEMO_B, "project")[0]["links"][0]["url"]


@dataclass
class FakeLine:
    """The parts of a queue line the maker reads."""

    kind: str
    question: str | None = None
    actions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    changeset: str | None = None
    op: int | None = None
    did: dict | None = None
    subject: str | None = None
    count: int = 1


@pytest.fixture
def store(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    store = Store(ws.db_path, cfg=ws.config(env={}))
    yield store
    store.close()


def ctx(actor="assistant", **kw):
    return WriteContext(actor=actor, trust="trusted", op="test.maker", **kw)


def make_source(store, **fields) -> str:
    with store.transaction() as tx:
        return tx.create(
            "source",
            {
                "received_at": NOW,
                "kind": "pasted",
                "title": "A mail",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                **fields,
            },
            ctx("engine"),
        ).id


def make_change(store, source: str | None = None, ops=None, **fields) -> tuple[str, str]:
    """A request and the change that answers it; returns the change's id and the request's."""
    with store.transaction() as tx:
        req = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "input",
                "state": "done",
                "created_at": NOW,
                **({"source": source} if source else {}),
            },
            ctx("engine"),
        ).id
        cs = tx.create(
            "changeset",
            {
                "request": req,
                "status": "applied",
                "trust": "untrusted",
                "created_at": NOW,
                "ops": ops or [],
                **fields,
            },
            ctx("engine"),
        ).id
    return cs, req


def make_action(store, *, actor="assistant", change=None, request=None, **fields) -> str:
    with store.transaction() as tx:
        return tx.create(
            "action",
            {"text": "Send the file", "owners": [{"person": PERSON}], "status": "open", **fields},
            ctx(actor, changeset=change, request=request),
        ).id


def make_question(store, *, actor="assistant", change=None, request=None, **fields) -> str:
    with store.transaction() as tx:
        return tx.create(
            "question",
            {"to": PERSON, "title": "Which one?", "kind": "decision", **fields},
            ctx(actor, changeset=change, request=request),
        ).id


def test_a_suggested_question_names_the_assistant_the_input_and_has_no_answer_yet(store):
    source = make_source(store, url=PAGE)
    change, request = make_change(store, source)
    question = make_question(store, change=change, request=request, source=source)
    made = line_maker.of_line(store.read(), FakeLine("decision", question=question))
    assert made["kind"] == "assistant" and made["state"] == "suggested" and made["rule"] is None
    assert made["answered"] is None and made["inferred"] is False
    assert made["source"]["title"] == "A mail"
    assert made["source"]["origin"] == {"kind": "link", "url": PAGE, "source": source}


def test_a_question_the_person_answered_says_how_and_when(store):
    source = make_source(store)
    change, request = make_change(store, source)
    question = make_question(store, change=change, request=request)
    found = store.read().get("question", question)
    with store.transaction() as tx:
        tx.update(
            "question",
            question,
            {"status": "answered", "answer": "The later one"},
            ctx("pm"),
            read_version=found.version,
        )
    made = line_maker.of_line(store.read(), FakeLine("question", question=question))
    assert made["state"] == "suggested"
    assert made["source"]["origin"]["kind"] == "source" and made["source"]["origin"]["source"] == source
    assert (made["answered"]["how"], made["answered"]["answer"]) == ("answered", "The later one")
    assert made["answered"]["on"] is not None


def test_an_item_added_from_what_was_said_names_the_input_and_one_worked_out_says_so(store):
    source = make_source(store)
    change, request = make_change(store, source)
    said = make_action(store, change=change, request=request, source=source, basis="said")
    worked_out = make_action(store, change=change, request=request, source=source, basis="inferred")
    view = store.read()
    one = line_maker.of_line(view, FakeLine("promise", actions=[said]))
    two = line_maker.of_line(view, FakeLine("promise", actions=[worked_out]))
    assert (one["kind"], one["state"], one["inferred"]) == ("assistant", "added", False)
    assert (two["kind"], two["state"], two["inferred"]) == ("assistant", "added", True)
    assert one["source"]["origin"]["source"] == source


def test_the_source_comes_from_the_request_when_the_item_names_none(store):
    source = make_source(store)
    change, request = make_change(store, source)
    action = make_action(store, change=change, request=request)
    made = line_maker.of_line(store.read(), FakeLine("reply", actions=[action]))
    assert made["source"]["origin"]["source"] == source


def test_a_change_made_by_a_rule_names_the_rule(store):
    change, request = make_change(store, make_source(store), by_rule="reply_answered")
    action = make_action(store, actor="engine", change=change, request=request)
    made = line_maker.of_line(store.read(), FakeLine("promise", actions=[action]))
    assert made["kind"] == "rule" and made["rule"]["id"] == "reply_answered" and made["state"] == "added"


def test_the_persons_own_item_is_the_persons(store):
    action = make_action(store, actor="pm")
    made = line_maker.of_line(store.read(), FakeLine("overdue", actions=[action]))
    assert made["kind"] == "person" and made["source"] is None


def test_an_item_the_engine_or_an_import_made_names_no_maker(store):
    action = make_action(store, actor="import")
    assert line_maker.of_line(store.read(), FakeLine("promise", actions=[action])) is None


def test_a_held_item_is_suggested_by_its_change_and_one_applied_is_added(store):
    source = make_source(store)
    ops = [
        {"index": 0, "op": {"op": "action.add", "text": "x", "basis": "inferred"}, "status": "held", "group": "g"},
        {"index": 1, "op": {"op": "action.add", "text": "y"}, "status": "applied", "group": "g", "label": "Do y"},
    ]
    change, _ = make_change(store, source, ops=ops)
    view = store.read()
    held = line_maker.of_line(view, FakeLine("held", changeset=change, op=0))
    assert (held["kind"], held["state"], held["inferred"]) == ("assistant", "suggested", True)
    review = line_maker.of_line(view, FakeLine("review", changeset=change, did={"op": "x"}, subject="Do y"))
    assert (review["kind"], review["state"], review["inferred"]) == ("assistant", "added", False)


def test_a_held_item_the_person_kept_says_it_was_kept(store):
    source = make_source(store)
    change, request = make_change(store, source)
    question = make_question(store, change=change, request=request)
    found = store.read().get("question", question)
    with store.transaction() as tx:
        tx.update("question", question, {"status": "answered", "answer": "Yes"}, ctx("pm"), read_version=found.version)
    ops = [
        {"index": 0, "op": {"op": "action.add", "text": "y"}, "status": "applied", "group": "g", "question": question}
    ]
    cs, _ = make_change(store, source, ops=ops)
    made = line_maker.of_line(store.read(), FakeLine("review", changeset=cs, did={"op": "x"}))
    assert made["state"] == "suggested" and made["answered"]["how"] == "kept" and made["answered"]["on"]


def test_an_escalation_is_the_assistants_suggestion_whoever_made_the_item(store):
    action = make_action(store, actor="pm")
    made = line_maker.of_line(store.read(), FakeLine("escalate", actions=[action]))
    assert (made["kind"], made["state"]) == ("assistant", "suggested")


def test_a_line_about_several_things_has_no_maker(store):
    a, b = make_action(store, actor="pm"), make_action(store, actor="pm")
    assert line_maker.of_line(store.read(), FakeLine("overdue", actions=[a, b], count=2)) is None
    assert line_maker.of_line(store.read(), FakeLine("nudge", actions=[a])) is None


def test_a_record_the_engine_wrote_as_part_of_an_assistants_change_is_the_assistants(store):
    change, request = make_change(store, make_source(store))
    question = make_question(store, actor="engine", change=change, request=request)
    made = line_maker.of_line(store.read(), FakeLine("who_is", question=question))
    assert (made["kind"], made["state"]) == ("assistant", "suggested")


# ---- the route, and the attribution never going outward -------------------------------------------------------------


@pytest.fixture
def served(queue_api):  # noqa: F811
    return queue_api


SHEET = json.loads((Path(__file__).parents[1] / "web/src/wording/en.json").read_text(encoding="utf-8"))
ATTRIBUTION = [SHEET[k] for k in SHEET if k.startswith("made_by.") and k.endswith(".assistant")]


def handed_in(client, base, worker):
    for case_id in ("no-owner", "production-checkin", "decision-for-pm", "shared-first-name"):
        hand_in(client, base, worker, case_id)
    return client.get(f"{base}/today/queue").json()


def test_the_queue_carries_the_maker_only_on_lines_about_one_item(served):
    client, base, worker = served
    lines = handed_in(client, base, worker)
    made = [line for line in lines if line["made_by"]]
    assert {line["kind"] for line in made} >= {"owner", "review", "reply", "who_is"}
    for line in made:
        assert line["made_by"]["kind"] == "assistant"
        assert line["made_by"]["state"] == ("suggested" if line["kind"] in ("owner", "who_is") else "added")
        assert line["made_by"]["source"]["origin"]["kind"] in ("source", "link")
    # A line about several things, or about no one item, names no maker.
    for line in lines:
        if line["kind"] in ("send", "nudge", "backup", "unfiled") or (line["kind"] == "review" and line["count"] > 1):
            assert line["made_by"] is None


def test_the_attribution_is_in_no_message_to_copy_no_export_and_no_record(served, tmp_path):
    """Paths checked: the Follow-ups messages (the text copied to someone), every file of the data export (what another
    person or computer receives, which holds every stored record), and the guard that every act's parts and every
    published text pass (`outward.check_outgoing`). The attribution is built on the person's screen from the line, so
    none reaches any of them; and if its words were ever put into outward text the guard refuses them by the
    assistant's name."""
    client, base, worker = served
    store, cfg = client.app_store, worker.cfg
    lines = handed_in(client, base, worker)
    assert any(line["made_by"] for line in lines)
    names = outward.assistant_names(store.read(), cfg.workspace.assistant_name)
    phrases = [p.replace("{assistant}", "").strip() for p in ATTRIBUTION]
    for section in client.get(f"{base}/followups").json():
        for text in (section["message"], (section.get("nudge") or {}).get("text") or ""):
            assert outward.name_in(text, names) is None
            assert not any(p in text for p in phrases)
    written = export_data(store, tmp_path / "exported")
    assert written
    for path in written:
        body = path.read_text(encoding="utf-8")
        assert "made_by" not in body and not any(p in body for p in phrases)
    # The guard refuses an attribution that names the assistant, by any name it has had.
    for template in ATTRIBUTION:
        for name in names:
            problem = outward.outgoing_problem(store.read(), cfg, {"a shared page": template.format(assistant=name)})
            assert problem is not None and name in problem
