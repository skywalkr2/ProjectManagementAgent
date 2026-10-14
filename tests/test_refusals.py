"""Refusals counted per check, the seed lessons they bring into a packet, and the batch prefix not being frozen
(design 6.6, 6.22). Names and ids come from the fixtures.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from engine import invariants
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config.schema import KnowledgeSettings
from engine.dispatcher import process
from engine.intake import hand_in
from engine.packet import build
from engine.refusals import refusal_shares, seed_id, seed_section
from engine.storage import Store, WriteContext
from engine.worker import Events, Worker
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 14)
TASK = "notes"
OTHER_TASK = "ask"
SEEDED = invariants.load()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.refusals")


def person(role: str) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p.get("role") == role)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def limits(share: float, of_last: int) -> KnowledgeSettings:
    return KnowledgeSettings(refusals_to_packet={"share": share, "of_last": of_last})


def a_run(store, task: str, refused_by: list[str], *, whole: list[str] = ()) -> str:
    """A request the assistant answered, with a changeset whose single op was refused by these checks."""
    problems = [{"check": name, "severity": "refuse", "op": 0, "message": "no"} for name in refused_by]
    problems.append({"check": "blocked-wording", "severity": "warn", "op": 0, "message": "only a warning"})
    with store.transaction() as tx:
        request = tx.create(
            "request", {"task": task, "origin": "pm", "state": "review", "created_at": NOW.isoformat()}, _TEST
        )
        run = tx.create(
            "run",
            {
                "request": request.id,
                "task": task,
                "provider": "p",
                "model": "m",
                "tier": "t",
                "outcome": "ok",
                "started_at": NOW.isoformat(),
            },
            _TEST,
        )
        changeset = tx.create(
            "changeset",
            {
                "request": request.id,
                "run": run.id,
                "status": "rejected" if refused_by else "applied",
                "trust": "trusted",
                "created_at": NOW.isoformat(),
                "ops": [{"index": 0, "status": "refused", "problems": problems}],
                "problems": [{"check": name, "severity": "refuse", "op": None, "message": "no"} for name in whole],
            },
            _TEST,
        )
        tx.update("request", request.id, {"changeset": changeset.id}, _TEST, read_version=request.version)
    return request.id


def test_the_share_of_each_check_is_the_runs_it_refused_over_the_runs_counted(env):
    _, _, store = env
    a_run(store, TASK, ["evidence", "targets"])
    a_run(store, TASK, ["evidence"], whole=["required-ops"])
    a_run(store, TASK, [])
    a_run(store, TASK, [])
    a_run(store, OTHER_TASK, ["question-links"])

    shares = refusal_shares(store.read(), TASK, 50)

    # Warnings never count, a check counts once per run however many ops it refused, and another kind's runs are apart.
    assert shares == {"evidence": 0.5, "required-ops": 0.25, "targets": 0.25}
    assert refusal_shares(store.read(), OTHER_TASK, 50) == {"question-links": 1.0}
    assert refusal_shares(store.read(), "never-run", 50) == {}


def test_only_the_last_runs_are_counted(env):
    _, _, store = env
    a_run(store, TASK, ["evidence"])
    a_run(store, TASK, ["evidence"])
    a_run(store, TASK, [])
    a_run(store, TASK, ["targets"])

    assert refusal_shares(store.read(), TASK, 2) == {"targets": 0.5}
    assert refusal_shares(store.read(), TASK, 4) == {"evidence": 0.5, "targets": 0.25}


def test_a_changeset_without_an_assistant_run_is_not_a_run(env):
    _, _, store = env
    with store.transaction() as tx:
        request = tx.create(
            "request", {"task": TASK, "origin": "pm", "state": "done", "created_at": NOW.isoformat()}, _TEST
        )
        changeset = tx.create(
            "changeset",
            {"request": request.id, "status": "applied", "trust": "trusted", "created_at": NOW.isoformat()},
            _TEST,
        )
        tx.update("request", request.id, {"changeset": changeset.id}, _TEST, read_version=request.version)
    a_run(store, TASK, ["evidence"])

    assert refusal_shares(store.read(), TASK, 50) == {"evidence": 1.0}


def test_a_seed_lesson_enters_at_the_share_and_not_below_it(env):
    _, _, store = env
    a_run(store, TASK, ["evidence"])
    for _ in range(3):
        a_run(store, TASK, [])
    view = store.read()  # a quarter of the last four runs

    at = seed_section(view, TASK, limits(0.25, 4))
    below = seed_section(view, TASK, limits(0.26, 4))

    assert at.ids == [seed_id("evidence")] == ["SEED-evidence"]
    assert SEEDED["evidence"].seed in at.text and "the product's own guidance" in at.text
    assert below.text == "" and below.ids == []
    assert seed_section(view, OTHER_TASK, limits(0.0, 4)).ids == []  # a share of none still needs a refusal


def test_seed_lessons_come_in_the_files_order_and_only_for_checks_that_have_one(env):
    _, _, store = env
    a_run(store, TASK, ["targets", "evidence", "blocked-wording", "question-links"])

    seeded = seed_section(store.read(), TASK, limits(0.5, 10))

    assert seeded.ids == [seed_id(name) for name in SEEDED if name in ("targets", "evidence", "question-links")]
    assert seeded.ids == ["SEED-targets", "SEED-evidence", "SEED-question-links"]
    assert seeded.text.splitlines()[0].startswith("# ") and len(seeded.text.splitlines()) == 4
    assert seeded == seed_section(store.read(), TASK, limits(0.5, 10))  # the same text each time: a stable prefix


def test_a_packet_carries_the_seed_lesson_in_its_stable_part_and_logs_it(env):
    ws, cfg, store = env
    cfg.dispatch.knowledge.refusals_to_packet.of_last = 2
    cfg.dispatch.knowledge.refusals_to_packet.share = 0.5
    a_run(store, TASK, ["evidence"])
    a_run(store, TASK, [])
    handed = hand_in(ws, store, pasted="Subject: One\n\nThe proof is late.", now=NOW)

    packet = build(ws, store, cfg, handed.request, TODAY)

    assert SEEDED["evidence"].seed in packet.task.stable and SEEDED["evidence"].seed not in packet.task.request
    assert packet.knowledge.given == ["SEED-evidence"]
    assert packet.task.stable.index("# Where this kind of work often goes wrong") < packet.task.stable.index(
        "# Open actions"
    )

    # One more run without a refusal puts the share under the line, and the lesson leaves the packet.
    a_run(store, TASK, [])
    a_run(store, TASK, [])
    later = build(ws, store, cfg, handed.request, TODAY)
    assert SEEDED["evidence"].seed not in later.task.stable and later.knowledge.given == []


def test_a_refusal_the_applier_records_is_counted_and_brings_its_lesson_next_time(env):
    ws, cfg, store = env
    bad = {"ops": [{"op": "fact", "text": "Proof ships Nov 5", "evidence": {"quote": "words nobody wrote"}}]}
    set_responder(lambda task: json.dumps(bad))
    cfg.dispatch.knowledge.refusals_to_packet.of_last = 1
    handed = hand_in(ws, store, pasted="Subject: Proof\n\nThe proof ships soon.", now=NOW)
    process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)

    assert refusal_shares(store.read(), TASK, 50) == {"evidence": 1.0}
    again = hand_in(ws, store, pasted="Subject: Jacket\n\nThe jacket is final.", now=NOW)
    packet = build(ws, store, cfg, again.request, TODAY)
    assert SEEDED["evidence"].seed in packet.task.stable and packet.knowledge.given == ["SEED-evidence"]


def test_the_refusals_setting_has_its_defaults_and_both_demo_workspaces_set_it():
    from engine.config import load_config

    default = KnowledgeSettings().refusals_to_packet
    assert (default.share, default.of_last) == (0.05, 50)
    for root in (DEMO_B, DEMO_B.parent / "demo-a"):
        loaded = load_config(root / "config", env={}).dispatch.knowledge.refusals_to_packet
        assert (loaded.share, loaded.of_last) == (0.05, 50)
        assert "refusals_to_packet" in (root / "config" / "dispatch.yaml").read_text(encoding="utf-8")


# ---- the batch prefix is not frozen ----------------------------------------------------------------------------------


def test_the_second_input_of_a_batch_sees_the_action_the_first_one_created(env):
    ws, cfg, store = env
    setter = person("Typesetter")
    quote = "to send the sample chapter to the reviewers by the 16th"
    action_text = "Send the sample chapter to the reviewers"
    seen = []
    first = {
        "summary": "One action.",
        "ops": [
            {"op": "action.add", "text": action_text, "owners": [setter["full_name"]], "evidence": {"quote": quote}}
        ],
    }

    def respond(task):
        seen.append(task)
        return json.dumps(first if len(seen) == 1 else {"summary": "Nothing new.", "ops": []})

    set_responder(respond)
    one = hand_in(ws, store, pasted=f"Sample: {setter['full_name']} {quote}.", now=NOW)
    two = hand_in(ws, store, pasted="Interior: the sample chapter is due on the 16th.", now=NOW)
    worker = Worker(ws, store, cfg, Events(), router_factory=lambda: Router(cfg, store, env={}), now=lambda: NOW)

    assert worker.run_pending() == 2

    (action,) = [a for a in store.read().list("action") if a.data["text"] == action_text]
    assert store.read().get("request", one.request).data["state"] == "review"
    assert store.read().get("request", two.request).data["state"] == "review"
    first_open, second_open = (
        task.stable.split("# Open actions\n", 1)[1].split("\n\n# ", 1)[0] for task in (seen[0], seen[1])
    )
    assert action_text not in first_open
    assert action.id in second_open and action_text in second_open
    # Only the open items differ: everything before them is the same, so that part of the prefix still caches.
    assert seen[0].stable.split("# Open actions")[0] == seen[1].stable.split("# Open actions")[0]
