"""Phase L2: what a rule constrains, whether it applied or was only present, and the review of standing rules
(design 6.22).

The decisions are plain functions over records and are tested on records; one pipeline test follows a request to its
run, and one API test covers Keep and Narrow. Names and ids come from the fixtures.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config.schema import KnowledgeSettings, RulesFile
from engine.dispatcher import process, signal
from engine.intake import hand_in
from engine.knowledge_section import stable_section
from engine.rule_review import due, last_acted, review
from engine.rule_use import applied_by, constrained_by_ops, record_applied
from engine.rules import seed_rules
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

PEOPLE = fixture_records(DEMO_B, "person")
PM = PEOPLE[0]["id"]
OTHER = PEOPLE[1]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
SETTINGS = KnowledgeSettings()
LONG_AGO = NOW - timedelta(days=SETTINGS.rule_review_days + 10)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.rule-review")


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


def rule(store, name, *, text="A standing rule.", learned=LONG_AGO, **fields) -> str:
    data = {"name": name, "text": text, "origin": "person", "status": "active", "learned_at": learned.isoformat()}
    return make(store, "rule", data | fields)


def update(store, record_id, fields) -> None:
    with store.transaction() as tx:
        current = tx.get("rule", record_id)
        tx.update("rule", record_id, fields, _TEST, read_version=current.version)


def run(store, *, present=(), applied=(), at=NOW - timedelta(days=1), moved=(), chars=100) -> str:
    log = {
        "given": [*present, *applied],
        "rules_present": list(present),
        "rules_applied": list(applied),
        "rules_moved": list(moved),
        "stable_chars": chars,
    }
    return make(
        store,
        "run",
        {
            "task": "notes",
            "provider": "stub",
            "model": "stub",
            "tier": "low",
            "outcome": "ok",
            "started_at": at.isoformat(),
            "knowledge": log,
        },
    )


def flagged(store, now=NOW, settings=SETTINGS):
    return review(store.read(), settings, now)


def names_of(store, found) -> list[str]:
    return [store.read().get("rule", f.id).data["name"] for f in found.flagged]


# ---- applied versus present ------------------------------------------------------------------------------------------


def test_an_op_of_a_constrained_kind_or_a_constrained_field_that_is_set_counts():
    ops = [{"op": "question.add", "to": PM, "title": "Which?"}, {"op": "action.add", "text": "Do it", "owners": [PM]}]
    assert constrained_by_ops(["question.add"], ops)
    assert constrained_by_ops(["action.add.owners"], ops)
    assert constrained_by_ops(["event.add", "action.add"], ops)
    # A field the op leaves empty or doesn't have is not set; another kind of op doesn't match.
    assert not constrained_by_ops(["action.add.due"], ops)
    assert not constrained_by_ops(["action.add.owners"], [{"op": "action.add", "text": "Do it", "owners": []}])
    assert not constrained_by_ops(["action.close"], ops)
    assert not constrained_by_ops([], ops)


def test_a_check_that_ran_on_the_output_applies_a_rule_that_names_it_and_one_that_didnt_run_does_not():
    checked = SimpleNamespace(data={"check": "a-check", "constrains": []})
    prose = SimpleNamespace(data={"check": None, "constrains": []})
    assert applied_by(checked, [], checks_ran={"a-check"})
    assert not applied_by(checked, [], checks_ran=set())
    assert not applied_by(checked, [], checks_ran={"another-check"})
    assert not applied_by(prose, [], checks_ran={"a-check"})


def test_a_run_marks_the_rules_its_changeset_shows_applied_and_the_rest_stay_present(env):
    _, _, store = env
    by_kind = rule(store, "by-kind", constrains=["question.add"])
    by_field = rule(store, "by-field", constrains=["action.add.owners"])
    unset_field = rule(store, "unset-field", constrains=["action.add.due"])
    prose = rule(store, "prose")
    request = make(store, "request", {"task": "notes", "origin": "pm", "state": "done", "created_at": NOW.isoformat()})
    run_id = run(store, present=[by_kind, by_field, unset_field, prose])
    ops = [
        {"index": 0, "op": {"op": "question.add", "to": PM, "title": "Which?"}, "status": "held", "group": "op0"},
        {"index": 1, "op": {"op": "action.add", "text": "Do it", "owners": [PM]}, "status": "refused", "group": "op1"},
    ]
    changeset = make(
        store,
        "changeset",
        {
            "request": request,
            "ops": ops,
            "status": "held",
            "trust": "trusted",
            "run": run_id,
            "created_at": NOW.isoformat(),
        },
    )
    assert record_applied(store, run_id, changeset) == [by_kind, by_field]
    log = store.read().get("run", run_id).data["knowledge"]
    assert log["rules_applied"] == [by_kind, by_field] and log["rules_present"] == [unset_field, prose]


def test_a_later_correction_that_names_a_rule_counts_it_on_the_run_it_corrects_and_only_then(env):
    _, _, store = env
    named = rule(store, "named")
    other = rule(store, "other")
    run_id = run(store, present=[named, other])
    unrelated = run(store, present=[named])
    signal(store, "sent_back", [named], run=run_id)
    log = store.read().get("run", run_id).data["knowledge"]
    assert log["rules_applied"] == [named] and log["rules_present"] == [other]
    assert store.read().get("run", unrelated).data["knowledge"]["rules_applied"] == []
    # A correction naming a rule the run wasn't given, or no run at all, changes nothing; naming one twice counts once.
    signal(store, "sent_back", [other], run=unrelated)
    signal(store, "sent_back", [named], run=run_id)
    signal(store, "sent_back", [other])
    assert store.read().get("run", unrelated).data["knowledge"]["rules_applied"] == []
    assert store.read().get("run", run_id).data["knowledge"]["rules_applied"] == [named]


def test_a_processed_run_carries_the_rules_applied_present_and_moved(env):
    ws, cfg, store = env
    quote = "The printer slot moved"
    applied = rule(store, "owners-rule", constrains=["action.add.owners"])
    present = rule(store, "due-rule", constrains=["action.add.due"])
    # A rule too long for the always-sent budget moves out of it; it is still given, with the runs it covers.
    cfg.dispatch.knowledge.stable_budget = 500
    heavy = rule(store, "heavy-rule", text="Keep every question short. " * 20)
    moved = stable_section(store.read(), "notes", cfg.dispatch.knowledge).moved
    assert moved
    answer = {"ops": [{"op": "action.add", "text": "Confirm it", "owners": [PM], "evidence": {"quote": quote}}]}
    set_responder(lambda task: json.dumps(answer))
    handed = hand_in(ws, store, pasted=f"Subject: Slot\n\n{quote}.", now=NOW, project=PROJECT)
    process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    (the_run,) = store.read().list("run")
    log = the_run.data["knowledge"]
    assert log["rules_applied"] == [applied]
    assert set(log["rules_present"]) == {present, heavy}
    assert log["rules_moved"] == moved
    assert set(log["given"]) >= {applied, present, heavy}


def test_a_seeded_rule_and_a_rule_added_by_an_op_carry_what_they_constrain(env):
    _, cfg, store = env
    store.plugins.cfg.files["rules"] = RulesFile(
        rules=[{"id": "seeded", "text": "Name an owner.", "constrains": ["action.add.owners"]}]
    )
    assert seed_rules(store) == ["seeded"]
    seeded = next(r for r in store.read().list("rule") if r.data["name"] == "seeded")
    assert seeded.data["constrains"] == ["action.add.owners"]
    from engine.applier import apply_as_person

    apply_as_person(
        store,
        cfg,
        [{"op": "rule.add", "text": "Ask first.", "constrains": ["question.add", "question.add"]}],
        "Add a rule",
    )
    added = next(r for r in store.read().list("rule") if r.data["origin"] == "person")
    assert added.data["constrains"] == ["question.add"]


# ---- the review ------------------------------------------------------------------------------------------------------


def test_the_review_flags_a_rule_present_but_never_applied_most_present_first(env):
    _, _, store = env
    quiet = rule(store, "quiet")
    busy = rule(store, "busy")
    used = rule(store, "used")
    for _ in range(3):
        run(store, present=[busy])
    run(store, present=[busy, quiet], applied=[used])
    run(store, present=[quiet], applied=[used])
    found = flagged(store)
    assert [(f.id, f.present, f.applied) for f in found.flagged] == [(busy, 4, 0), (quiet, 2, 0)]


def test_the_review_orders_by_present_count_and_never_flags_a_rule_a_check_enforces(env):
    _, _, store = env
    few = rule(store, "few")
    many = rule(store, "many")
    checked = rule(store, "checked", check="a-check")
    for _ in range(4):
        run(store, present=[many, checked])
    run(store, present=[few])
    found = flagged(store)
    assert [(f.id, f.present) for f in found.flagged] == [(many, 4), (few, 1)]
    assert checked not in [f.id for f in found.flagged]


def test_an_applied_rule_is_never_flagged_and_neither_is_one_that_was_never_given(env):
    _, _, store = env
    applied_once = rule(store, "applied-once")
    never_given = rule(store, "never-given")
    for _ in range(3):
        run(store, present=[applied_once])
    run(store, applied=[applied_once])
    assert flagged(store).flagged == [] and never_given


def test_only_active_rules_in_the_window_and_old_enough_are_flagged(env):
    _, _, store = env
    young = rule(store, "young", learned=NOW - timedelta(days=3))
    retired = rule(store, "retired", status="retired")
    outside = rule(store, "outside")
    run(store, present=[young, retired])
    run(store, present=[outside], at=NOW - timedelta(days=SETTINGS.rule_review_days + 1))
    assert flagged(store).flagged == []
    # With the window widened the older run counts; the young rule still hasn't had a whole window.
    wide = KnowledgeSettings(rule_review_days=SETTINGS.rule_review_days + 5)
    assert [f.id for f in flagged(store, settings=wide).flagged] == [outside]


def test_keeping_a_rule_starts_its_count_again(env):
    _, _, store = env
    rule_id = rule(store, "kept-rule")
    run(store, present=[rule_id])
    assert [f.id for f in flagged(store).flagged] == [rule_id]
    update(store, rule_id, {"reviewed_at": (NOW - timedelta(days=2)).isoformat()})
    assert flagged(store).flagged == []
    # A whole window later, still present and never applied, it is flagged again.
    later = NOW + timedelta(days=SETTINGS.rule_review_days)
    run(store, present=[rule_id], at=later - timedelta(days=1))
    assert [f.id for f in flagged(store, now=later).flagged] == [rule_id]


def test_the_review_reports_the_latest_size_against_the_budget_and_the_rules_moved(env):
    _, _, store = env
    assert (flagged(store).stable_chars, flagged(store).moved) == (0, 0)
    run(store, at=NOW - timedelta(days=5), chars=900, moved=["RULE-1", "RULE-2"])
    run(store, at=NOW - timedelta(days=1), chars=1200, moved=["RULE-3"])
    found = flagged(store)
    assert (found.stable_chars, found.stable_budget, found.moved) == (1200, SETTINGS.stable_budget, 1)
    assert found.needed


# ---- the line on Today -----------------------------------------------------------------------------------------------


def lines(env, now=NOW):
    ws, cfg, store = env
    return [line for line in queue(ws, store, cfg, now) if line.kind == "rule_review"]


def test_the_line_appears_only_when_a_rule_is_flagged_or_rules_were_moved(env):
    _, _, store = env
    quiet = rule(store, "quiet")
    assert lines(env) == []
    run(store, present=[quiet], chars=640)
    (line,) = lines(env)
    assert (line.group, line.count, line.rules, line.stable_size, line.moved, line.days) == (
        "review",
        1,
        [quiet],
        640,
        0,
        30,
    )
    assert line.stable_budget == SETTINGS.stable_budget
    # With nothing flagged, rules moved out of the always-sent part are enough.
    update(store, quiet, {"status": "retired"})
    assert lines(env) == []
    run(store, moved=[quiet], chars=900, at=NOW - timedelta(hours=1))
    (line,) = lines(env)
    assert (line.count, line.moved) == (0, 1)


def test_the_line_returns_at_most_once_a_period_after_the_person_acts_on_it(env):
    _, cfg, store = env
    quiet = rule(store, "quiet")
    other = rule(store, "other")
    run(store, present=[quiet, other])
    assert len(lines(env)) == 1
    acted = NOW + timedelta(days=1)
    update(store, other, {"status": "retired"})
    signal(store, "retired", [other], now=acted)
    every = cfg.dispatch.knowledge.rule_review_every_days
    assert last_acted(store.read()) == acted
    assert lines(env, now=acted + timedelta(days=every - 1)) == []
    assert due(store.read(), cfg.dispatch.knowledge, acted + timedelta(days=every)) is True
    (line,) = lines(env, now=acted + timedelta(days=every))
    assert line.rules == [quiet]
    # An act on something that isn't a rule is not the review being acted on.
    other_signal = NOW + timedelta(days=every * 3)
    signal(store, "kept", ["LES-1"], now=other_signal)
    assert last_acted(store.read()) == acted


def test_not_now_starts_the_lines_week_without_deciding_anything_even_when_only_rules_moved(env):
    _, cfg, store = env
    quiet = rule(store, "quiet")
    run(store, present=[quiet])
    said = NOW + timedelta(days=1)
    signal(store, "not_now", [quiet], now=said)
    every = cfg.dispatch.knowledge.rule_review_every_days
    assert last_acted(store.read()) == said
    assert lines(env, now=said + timedelta(days=every - 1)) == []
    assert len(lines(env, now=said + timedelta(days=every))) == 1
    assert store.read().get("rule", quiet).data["status"] == "active"
    # The line about rules moved out of the always-sent part has no rule to name; "not now" still puts it off.
    update(store, quiet, {"status": "retired"})
    run(store, moved=[quiet], at=said + timedelta(days=every * 2) - timedelta(hours=1))
    later = said + timedelta(days=every * 2)
    assert len(lines(env, now=later)) == 1
    signal(store, "not_now", [], now=later)
    assert lines(env, now=later + timedelta(days=1)) == []


# ---- Keep and Narrow -------------------------------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "review-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer review-token"}) as client:
        yield client, application.state.store


def signals(store, kind):
    return [s for s in store.read().list("signal") if s.data["kind"] == kind]


def test_the_review_route_lists_the_flagged_rules_with_counts_and_the_size(app):
    client, store = app
    quiet = rule(store, "quiet", constrains=["question.add"])
    rule(store, "checked", check="a-check")
    started = datetime.now(UTC) - timedelta(days=1)
    for _ in range(2):
        run(store, present=[quiet], at=started, chars=700, moved=["RULE-9"])
    got = client.get("/api/knowledge/rules/review")
    assert got.status_code == 200, got.text
    body = got.json()
    assert [(r["id"], r["present"], r["applied"]) for r in body["flagged"]] == [(quiet, 2, 0)]
    assert body["flagged"][0]["version"] == store.read().get("rule", quiet).version
    assert (body["days"], body["stable_chars"], body["moved"], body["due"]) == (30, 700, 1, True)


def test_keep_resets_the_clock_with_a_signal_and_undo_puts_the_old_clock_back(app):
    client, store = app
    quiet = rule(store, "quiet")
    version = store.read().get("rule", quiet).version
    done = client.post(f"/api/knowledge/{quiet}/keep-rule", json={"read_version": version})
    assert done.status_code == 200, done.text
    assert store.read().get("rule", quiet).data["reviewed_at"] is not None
    assert [s.data["refs"] for s in signals(store, "kept")] == [[quiet]]
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert store.read().get("rule", quiet).data["reviewed_at"] is None
    # A stale version, a rule that isn't active and an id that isn't a rule are refused.
    assert client.post(f"/api/knowledge/{quiet}/keep-rule", json={"read_version": version}).status_code == 409
    version = store.read().get("rule", quiet).version
    client.post(f"/api/knowledge/{quiet}/retire", json={"read_version": version})
    version = store.read().get("rule", quiet).version
    assert client.post(f"/api/knowledge/{quiet}/keep-rule", json={"read_version": version}).status_code == 409
    assert client.post("/api/knowledge/NOPE-1/keep-rule", json={"read_version": 1}).status_code == 404


def test_narrow_changes_the_scope_as_the_persons_own_edit_with_a_new_signal_and_undo(app):
    client, store = app
    quiet = rule(store, "quiet")
    version = store.read().get("rule", quiet).version
    scope = {"scope": "projects", "projects": [PROJECT]}
    done = client.post(f"/api/knowledge/{quiet}/narrow", json={"read_version": version, "applies_to": scope})
    assert done.status_code == 200, done.text
    assert store.read().get("rule", quiet).data["applies_to"]["projects"] == [PROJECT]
    assert [s.data["refs"] for s in signals(store, "narrowed")] == [[quiet]]
    changeset = store.read().get("changeset", done.json()["changeset"])
    assert changeset.data["ops"][0]["op"]["op"] == "record.edit"
    assert client.post(f"/api/changesets/{done.json()['changeset']}/undo", json={}).status_code == 200
    assert store.read().get("rule", quiet).data["applies_to"]["scope"] == "workspace"
    bad = client.post(
        f"/api/knowledge/{quiet}/narrow",
        json={"read_version": store.read().get("rule", quiet).version, "applies_to": {"scope": "projects"}},
    )
    assert bad.status_code == 422


def test_not_now_route_records_a_signal_names_the_flagged_rules_and_changes_no_rule(app):
    client, store = app
    quiet = rule(store, "quiet")
    run(store, present=[quiet], at=datetime.now(UTC) - timedelta(days=1))
    assert client.get("/api/knowledge/rules/review").json()["due"] is True
    before = store.read().get("rule", quiet)
    put_off = client.post("/api/knowledge/rules/review/not-now")
    assert put_off.status_code == 200, put_off.text
    (said,) = signals(store, "not_now")
    assert said.data["refs"] == [quiet] and said.data["run"] is None and said.data["changeset"] is None
    every = timedelta(days=KnowledgeSettings().rule_review_every_days)
    assert datetime.fromisoformat(put_off.json()["until"]) - datetime.fromisoformat(said.data["at"]) == every
    assert client.get("/api/knowledge/rules/review").json()["due"] is False
    assert store.read().get("rule", quiet).version == before.version
