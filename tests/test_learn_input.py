"""Learning from inputs (design 6.22, phase L3i): what an input's own run proposes (a term, who answers, a fact that
replaces another), the rules-only scan for new terms, "not me, ask X" in a reply, and an answer to the assistant's
question that teaches at once. Names and ids come from the fixtures; the AI is the stub.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import learn, new_terms, proposals
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import process
from engine.intake import hand_in
from engine.ops import KNOWLEDGE_OPS
from engine.packet import build
from engine.storage import Store, WriteContext
from engine.tasks import TASKS
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_plugin_learning import make_env

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.learn-input")
PEOPLE = fixture_records(DEMO_B, "person")
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
PAGE = fixture_records(DEMO_B, "project")[0]["links"][0]["url"]
MAIL = PEOPLE[1]["how_to_reach"]["email"]
OPEN_QUESTION = next(q for q in fixture_records(DEMO_B, "question") if q.get("kind") != "decision")
DECISION = next(q for q in fixture_records(DEMO_B, "question") if q.get("kind") == "decision")
SPEAKER = next(p for p in PEOPLE if p["id"] == OPEN_QUESTION["to"])
NAMED = next(p for p in PEOPLE if p["id"] not in (SPEAKER["id"], DECISION["to"]))


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def make(store, kind, data) -> str:
    with store.transaction() as tx:
        return tx.create(kind, data, _TEST).id


def read(env, pasted: str, ops: list[dict]):
    """Hand a pasted input in and let the stub read it with these ops. Returns the request and its changeset."""
    ws, cfg, store = env
    set_responder(lambda task: json.dumps({"summary": "Read it.", "topic": "a topic", "ops": ops}))
    handed = hand_in(ws, store, pasted=pasted, now=NOW)
    return handed.request, process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)


def entries(store, kind) -> list:
    return store.read().list(kind)


def statuses(store, cs_id) -> list[str]:
    return [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


# ---- what an input's own run proposes --------------------------------------------------------------------------------


def test_a_run_proposing_a_term_a_routing_entry_and_a_superseding_fact_makes_three_proposals(env):
    _, _, store = env
    older = make(
        store, "fact", {"text": "The Zorbit export ships on the 5th.", "project": PROJECT, "as_of": "2026-09-01"}
    )
    said = "The Zorbit export now ships on the 12th."
    pasted = f"From: {SPEAKER['full_name']}\n\nNot me, ask {NAMED['full_name']}. {said}"
    ops = [
        {
            "op": "glossary.add",
            "text": "Zorbit: not known yet",
            "term": "Zorbit",
            "meaning": "not known yet",
            "confidence": "unknown",
            "evidence": {"quote": "The Zorbit export"},
        },
        {
            "op": "routing.add",
            "text": f"Questions about the export go to {NAMED['full_name']}.",
            "topic": "the export",
            "person": NAMED["id"],
            "evidence": {"quote": f"Not me, ask {NAMED['full_name']}"},
        },
        {"op": "fact", "text": said, "project": PROJECT, "supersedes": older, "evidence": {"quote": said}},
    ]
    _, cs_id = read(env, pasted, ops)
    assert statuses(store, cs_id) == ["applied"] * 3
    (term,) = entries(store, "glossary_entry")
    (route,) = entries(store, "routing_entry")
    assert (term.data["status"], term.data["origin"], term.data["confidence"]) == ("proposed", "input", "unknown")
    assert (route.data["status"], route.data["origin"], route.data["person"]) == ("proposed", "input", NAMED["id"])
    newer = next(f for f in entries(store, "fact") if f.id != older)
    assert newer.data["supersedes"] == older and newer.data["trust"] == "untrusted"
    assert {p.kind for p in proposals.proposals(store.read())} == {"glossary_entry", "routing_entry"}


def test_the_notes_packet_offers_the_learning_ops_and_says_when_to_propose_them(env):
    ws, cfg, store = env
    assert {"glossary.add", "routing.add"} <= set(TASKS["notes"].ops)
    assert KNOWLEDGE_OPS & set(TASKS["notes"].ops) == {"glossary.add", "routing.add"}
    handed = hand_in(ws, store, pasted="Anything at all.", now=NOW)
    packet = build(ws, store, cfg, handed.request, TODAY)
    assert '"routing.add"' in packet.task.stable and '"glossary.add"' in packet.task.stable
    assert "not me, ask X" in packet.task.instructions and "supersedes" in packet.task.instructions


@pytest.fixture
def own_env(tmp_path):
    ws, cfg, store = make_env(tmp_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def test_work_that_learns_on_its_own_gets_no_learning_ops_no_prompt_rules_and_no_scan(own_env):
    ws, cfg, store = own_env
    cast = make(store, "p52/cast", {"name": "The harbor master", "project": PROJECT})
    chapter = make(store, "p52/chapter", {"title": "The Crossing", "text": "A line.", "project": PROJECT})
    pasted = f"Not me, ask {NAMED['full_name']}. The QXZ gateway is new."
    ops = [
        {"op": "glossary.add", "text": "QXZ: not known yet", "term": "QXZ", "meaning": "not known yet"},
        {"op": "routing.add", "text": "The gateway goes to them.", "topic": "the gateway", "person": NAMED["id"]},
    ]
    results = {}
    for name, about in (("own", ("p52/cast", cast)), ("core", ("p52/chapter", chapter))):
        set_responder(lambda task: json.dumps({"summary": "Read it.", "topic": "a topic", "ops": ops}))
        handed = hand_in(ws, store, pasted=f"{pasted} {name}", now=NOW)
        with store.transaction() as tx:
            current = tx.get("request", handed.request)
            about_it = {"about": {"kind": about[0], "id": about[1]}}
            tx.update("request", handed.request, about_it, _TEST, read_version=current.version)
        packet = build(ws, store, cfg, handed.request, TODAY)
        changeset = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
        made = {e.id for kind in ("glossary_entry", "routing_entry") for e in entries(store, kind)}
        results[name] = (packet, changeset, made)
    own_packet, own_cs, own_made = results["own"]
    core_packet, core_cs, core_made = results["core"]
    assert own_made == set() and statuses(store, own_cs) == ["refused", "refused"]
    assert '"glossary.add"' not in own_packet.task.stable and '"routing.add"' not in own_packet.task.stable
    assert "not me, ask X" not in own_packet.task.instructions
    assert len(core_made) == 2 and statuses(store, core_cs) == ["applied", "applied"]
    assert "not me, ask X" in core_packet.task.instructions


# ---- the scan for new terms ------------------------------------------------------------------------------------------


def test_the_scan_finds_unknown_acronyms_and_camel_case_names_and_skips_what_is_known():
    patterns = ["\\b[A-Z]{2,}[0-9]*\\b", "\\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\\b"]
    text = (
        "The XYZ gateway and the LoadHub service are new. FYI, OK with ZED and PRJ-12.\n"
        "> QUOTEDTHING was said before.\n"
        f"[quoted] OLDTHING too. See {PAGE}/ABCDEF or mail {MAIL} about XYZ again."
    )
    found = new_terms.candidates(text, patterns, ["fyi", "OK"])
    assert [term for term, _ in found] == ["XYZ", "LoadHub", "ZED"]
    assert found[0][1] == text.splitlines()[0]


def seed_known(store) -> dict:
    """A glossary term, a project, a person and a team whose names look like terms, so the scan must skip them."""
    return {
        "glossary": make(
            store,
            "glossary_entry",
            {
                "text": "ZED: a name",
                "term": "ZED",
                "meaning": "a name",
                "confidence": "confirmed",
                "origin": "person",
                "status": "active",
                "kept_by": PEOPLE[0]["id"],
                "kept_at": NOW.isoformat(),
                "learned_at": NOW.isoformat(),
            },
        ),
        "project": make(store, "project", {"name": "QRS Rollout"}),
        "person": make(store, "person", {"full_name": "Wil McTavish"}),
        "team": make(store, "team", {"name": "VPX Crew"}),
    }


def scan(env, text: str, **more) -> tuple[str, list[str]]:
    ws, cfg, store = env
    handed = hand_in(ws, store, pasted=text, now=NOW)
    return handed.request, new_terms.scan(store, cfg, handed.request, text, NOW, **more)


def test_the_scan_proposes_each_new_term_as_unknown_from_the_input_and_skips_known_names(env):
    _, _, store = env
    seed_known(store)
    text = (
        "ZED and QRS were discussed with McTavish and the VPX crew.\nThe XYZ gateway and the LoadHub service are new."
    )
    request, made = scan(env, text)
    terms = [store.read().get("glossary_entry", i).data for i in made]
    assert [t["term"] for t in terms] == ["XYZ", "LoadHub"]
    for entry in terms:
        assert (entry["status"], entry["origin"], entry["confidence"], entry["trust"]) == (
            "proposed",
            "input",
            "unknown",
            "untrusted",
        )
        assert entry["evidence"]["request"] == request and entry["evidence"]["quote"] in text
    assert {p.kind for p in proposals.proposals(store.read())} == {"glossary_entry"}
    assert scan(env, text)[1] == []  # nothing is new the second time


def test_the_scan_stops_at_the_configured_number_for_one_input_and_never_when_it_is_zero(env):
    _, cfg, store = env
    text = "AAA, BBB, CCC, DDD and EEE are all new."
    cfg.dispatch.knowledge.new_terms_per_input = 2
    request, made = scan(env, text)
    assert len(made) == 2
    again = new_terms.scan(store, cfg, request, text, NOW)
    assert again == []  # the input already has its two
    cfg.dispatch.knowledge.new_terms_per_input = 0
    assert scan(env, "FFF and GGG are new.")[1] == []


def test_the_scan_does_not_bring_back_a_term_the_person_just_discarded(env):
    _, _, store = env
    request, made = scan(env, "The HHH gateway is new.")
    (entry,) = made
    current = store.read().get("glossary_entry", entry)
    with store.transaction() as tx:
        tx.update("glossary_entry", entry, {"status": "discarded"}, _TEST, read_version=current.version)
        tx.create("signal", {"kind": "discarded", "refs": [entry], "at": NOW.isoformat()}, _TEST)
    assert scan(env, "The HHH gateway is mentioned again.")[1] == []


def test_a_run_on_an_input_scans_it_after_the_answer_applies_and_work_that_learns_on_its_own_is_left_alone(env):
    _, _, store = env
    _, cs_id = read(env, "The QXZ gateway moves next week.", [])
    assert statuses(store, cs_id) == []
    (entry,) = entries(store, "glossary_entry")
    assert (entry.data["term"], entry.data["status"], entry.data["origin"]) == ("QXZ", "proposed", "input")
    assert entry.data["evidence"]["source"] and entry.data["evidence"]["quote"] == "The QXZ gateway moves next week."


# ---- "not me, ask X" -------------------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "learn-input-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer learn-input-token"}) as client:
        yield client, application.state.store, cfg, ws
    set_responder(None)


def test_a_reply_that_says_not_me_ask_x_proposes_routing_and_leaves_the_question_open(api):
    client, store, cfg, ws = api
    qid = OPEN_QUESTION["id"]
    words = f"Not me, ask {NAMED['full_name']}. I only saw the summary."
    posted = client.post(f"/api/questions/{qid}/reply", json={"text": f"From: {SPEAKER['full_name']}\n\n{words}"})
    assert posted.status_code == 200, posted.text
    topic = "who confirms the acknowledgments page"
    ops = [
        {
            "op": "routing.add",
            "text": f"Questions about {topic} go to {NAMED['full_name']}.",
            "topic": topic,
            "person": NAMED["id"],
            "evidence": {"quote": f"Not me, ask {NAMED['full_name']}"},
        },
        {
            "op": "routing.add",
            "text": f"{SPEAKER['full_name']} does not answer questions about {topic}.",
            "topic": topic,
            "person": SPEAKER["id"],
            "negative": True,
            "evidence": {"quote": "I only saw the summary"},
        },
    ]
    set_responder(lambda task: json.dumps({"summary": "Passed on.", "topic": "a topic", "ops": ops}))
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), posted.json()["request"], now=NOW)
    assert statuses(store, cs_id) == ["applied", "applied"]
    found = {e.data["person"]: e.data for e in entries(store, "routing_entry")}
    assert found[NAMED["id"]]["status"] == "proposed" and not found[NAMED["id"]]["negative"]
    assert found[SPEAKER["id"]]["status"] == "proposed" and found[SPEAKER["id"]]["negative"]
    assert found[NAMED["id"]]["origin"] == "input" and found[NAMED["id"]]["trust"] == "untrusted"
    assert store.read().get("question", qid).data["status"] != "answered"


# ---- an answer to the assistant teaches -----------------------------------------------------------------------------


def test_an_answer_to_the_assistants_question_records_a_signal_and_queues_learning_at_once(api):
    client, store, cfg, ws = api
    qid = DECISION["id"]
    answer = "Soft touch, and don't ask me about finishes on the paperback list again."
    done = client.post(f"/api/questions/{qid}/answer", json={"text": answer})
    assert done.status_code == 200, done.text
    (signal,) = [s for s in entries(store, "signal") if s.data["kind"] == "answered_assistant"]
    assert signal.data["refs"] == [qid] and signal.data["note"] == answer
    (queued,) = [r for r in entries(store, "request") if r.data["task"] == learn.TASK]
    assert queued.data["about"] == {"kind": "signal", "id": signal.id}
    assert queued.data["state"] == "queued" and not queued.data.get("cause")  # not waiting for the next batch
    assert "starting now" in queued.data["waiting"]
    packet = build(ws, store, cfg, queued.id, TODAY)
    assert answer in packet.task.request and DECISION["title"] in packet.task.request
    assert "answered a question the assistant asked them" in packet.task.request


def test_a_bare_yes_and_an_answer_for_someone_else_record_no_such_signal(api):
    client, store, _, _ = api
    assert client.post(f"/api/questions/{DECISION['id']}/answer", json={"text": "Yes"}).status_code == 200
    other = OPEN_QUESTION["id"]
    said = "She said the page is final and no more names are coming."
    assert client.post(f"/api/questions/{other}/answer", json={"text": said}).status_code == 200
    assert not [s for s in entries(store, "signal") if s.data["kind"] == "answered_assistant"]
    assert not [r for r in entries(store, "request") if r.data["task"] == learn.TASK]
