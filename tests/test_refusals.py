"""Refusals counted per check, the seed lessons they bring into a packet, and the batch prefix not being frozen
(design 6.6, 6.22). Names and ids come from the fixtures.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from engine import invariants
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config.schema import KnowledgeSettings
from engine.dispatcher import process
from engine.intake import hand_in
from engine.packet import build
from engine.refusals import floor_counts, refusal_shares, seed_id, seed_section
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


def limits(share: float, of_last: int, min_runs: int = 1) -> KnowledgeSettings:
    return KnowledgeSettings(refusals_to_packet={"share": share, "of_last": of_last, "min_runs": min_runs})


def a_run(store, task: str, refused_by: list[str], *, whole: list[str] = (), at: datetime = NOW) -> str:
    """A request the assistant answered, with a changeset whose single op was refused by these checks."""
    problems = [{"check": name, "severity": "refuse", "op": 0, "message": "no"} for name in refused_by]
    problems.append({"check": "blocked-wording", "severity": "warn", "op": 0, "message": "only a warning"})
    with store.transaction() as tx:
        request = tx.create(
            "request", {"task": task, "origin": "pm", "state": "review", "created_at": at.isoformat()}, _TEST
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
                "started_at": at.isoformat(),
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
                "created_at": at.isoformat(),
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


def test_no_seed_lesson_enters_below_the_minimum_number_of_runs(env):
    _, _, store = env
    for _ in range(3):
        a_run(store, TASK, ["evidence"])  # every run refused, but few runs
    view = store.read()

    assert seed_section(view, TASK, limits(0.05, 50, min_runs=4)).ids == []
    assert seed_section(view, TASK, limits(0.05, 50, min_runs=3)).ids == ["SEED-evidence"]
    a_run(store, TASK, [])
    assert seed_section(store.read(), TASK, limits(0.05, 50, min_runs=4)).ids == ["SEED-evidence"]


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
    cfg.dispatch.knowledge.refusals_to_packet.min_runs = 2
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
    cfg.dispatch.knowledge.refusals_to_packet.min_runs = 1
    handed = hand_in(ws, store, pasted="Subject: Proof\n\nThe proof ships soon.", now=NOW)
    process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)

    assert refusal_shares(store.read(), TASK, 50) == {"evidence": 1.0}
    again = hand_in(ws, store, pasted="Subject: Jacket\n\nThe jacket is final.", now=NOW)
    packet = build(ws, store, cfg, again.request, TODAY)
    assert SEEDED["evidence"].seed in packet.task.stable and packet.knowledge.given == ["SEED-evidence"]


def test_a_refusal_a_fix_round_repaired_is_counted_from_the_runs_knowledge_log(env):
    ws, cfg, store = env
    bad = {"ops": [{"op": "fact", "text": "Proof ships Nov 5", "evidence": {"quote": "words nobody wrote"}}]}
    good = {"ops": [{"op": "fact", "text": "The proof is late", "evidence": {"quote": "The proof is late"}}]}
    answers = [json.dumps(bad), json.dumps(good)]
    set_responder(lambda task: answers.pop(0) if len(answers) > 1 else answers[0])
    handed = hand_in(ws, store, pasted="Subject: Proof\n\nThe proof is late.", now=NOW)

    process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)

    calls = store.read().find("run", {"request": handed.request})
    assert len(calls) == 2
    assert [c.data["knowledge"]["refused_checks"] for c in calls] == [["evidence"], []]
    (changeset,) = store.read().list("changeset")
    assert changeset.data["status"] == "applied"  # nothing was refused in the end
    assert refusal_shares(store.read(), TASK, 50) == {"evidence": 1.0}


def test_the_refusals_setting_has_its_defaults_and_both_demo_workspaces_set_it():
    from engine.config import load_config

    default = KnowledgeSettings().refusals_to_packet
    assert (default.share, default.of_last, default.min_runs) == (0.05, 50, 10)
    assert (default.floor, default.floor_days) == (3, 7)
    for root in (DEMO_B, DEMO_B.parent / "demo-a"):
        loaded = load_config(root / "config", env={}).dispatch.knowledge.refusals_to_packet
        assert (loaded.share, loaded.of_last, loaded.min_runs) == (0.05, 50, 10)
        assert (loaded.floor, loaded.floor_days) == (3, 7)
        assert "refusals_to_packet" in (root / "config" / "dispatch.yaml").read_text(encoding="utf-8")


# ---- the floor for rare work -----------------------------------------------------------------------------------------


def test_the_same_check_refusing_the_floor_times_in_its_days_brings_its_lesson_whatever_the_share(env):
    _, _, store = env
    settings = KnowledgeSettings()  # the defaults: 3 refusals in 7 days, and no lesson before 10 runs
    floor = settings.refusals_to_packet.floor
    for _ in range(floor - 1):
        a_run(store, TASK, ["evidence"])
    assert seed_section(store.read(), TASK, settings, today=TODAY).ids == []
    a_run(store, TASK, ["evidence"])
    view = store.read()
    assert seed_section(view, TASK, settings).ids == []  # the share rule alone: too few runs counted
    floored = seed_section(view, TASK, settings, today=TODAY)
    assert floored.ids == ["SEED-evidence"] and SEEDED["evidence"].seed in floored.text
    # Every run was refused by the check, so the share doesn't matter: nor does another kind of work's count.
    assert seed_section(view, OTHER_TASK, settings, today=TODAY).ids == []


def test_the_floor_counts_runs_of_the_same_check_within_its_days_only(env):
    _, _, store = env
    settings = KnowledgeSettings()
    days = settings.refusals_to_packet.floor_days
    a_run(store, TASK, ["evidence"], at=NOW - timedelta(days=days))  # one day too old
    a_run(store, TASK, ["evidence"], at=NOW - timedelta(days=days - 1))
    a_run(store, TASK, ["evidence"])
    a_run(store, TASK, ["targets"])
    a_run(store, TASK, ["targets"])
    a_run(store, TASK, ["targets"], at=NOW - timedelta(days=2))
    a_run(store, TASK, ["evidence", "targets"], at=NOW + timedelta(days=1))  # not yet: after today
    assert floor_counts(store.read(), TASK, settings, TODAY) == {"evidence": 2, "targets": 3}
    # Different checks never add up: only the one at the floor brings its lesson.
    assert seed_section(store.read(), TASK, settings, today=TODAY).ids == ["SEED-targets"]


def test_a_check_counts_once_per_run_for_the_floor_and_the_floor_is_a_setting(env):
    _, _, store = env
    a_run(store, TASK, ["evidence", "evidence"], whole=["evidence"])
    a_run(store, TASK, ["evidence"])
    view = store.read()
    assert floor_counts(view, TASK, KnowledgeSettings(), TODAY) == {"evidence": 2}
    two = KnowledgeSettings(refusals_to_packet={"floor": 2})
    assert seed_section(view, TASK, two, today=TODAY).ids == ["SEED-evidence"]
    one_day = KnowledgeSettings(refusals_to_packet={"floor": 2, "floor_days": 1})
    assert seed_section(view, TASK, one_day, today=TODAY + timedelta(days=1)).ids == []


def test_a_packet_carries_the_floored_lesson_and_logs_it(env):
    ws, cfg, store = env
    for _ in range(cfg.dispatch.knowledge.refusals_to_packet.floor):
        a_run(store, TASK, ["evidence"])
    handed = hand_in(ws, store, pasted="Subject: One\n\nThe proof is late.", now=NOW)
    packet = build(ws, store, cfg, handed.request, TODAY)
    assert SEEDED["evidence"].seed in packet.task.stable and packet.knowledge.given == ["SEED-evidence"]
    quiet = build(ws, store, cfg, handed.request, TODAY + timedelta(days=30))
    assert SEEDED["evidence"].seed not in quiet.task.stable and quiet.knowledge.given == []


# ---- the batch prefix is not frozen ----------------------------------------------------------------------------------


def test_the_second_input_of_a_batch_sees_the_action_the_first_one_created(env):
    ws, cfg, store = env
    setter = person("Editor")
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
