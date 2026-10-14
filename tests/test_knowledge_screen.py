"""Phase L3, the Knowledge screen's server side (design 7.18, 6.16, 6.22): how much each entry and rule was used, the
list of standing rules, and the Today line for an account in a fallback chain that can't stand in yet.

The use counts and the chain line are plain functions over records and are tested on records; the routes get one API
test each. Names and ids come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.checked import cannot_stand_in, remember
from engine.ai.smoke import account_test
from engine.ai.task import AiError
from engine.knowledge_use import Use, use_of
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, connection_answer, fixture_records, without_first_go

PM = fixture_records(DEMO_B, "person")[0]["id"]
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
_TEST = WriteContext(actor="pm", trust="trusted", op="test.knowledge-screen")


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


def lesson(store, text="Ask whoever owns the work.", status="active") -> str:
    data = {"text": text, "origin": "person", "status": status, "learned_at": NOW.isoformat()}
    if status == "active":
        data |= {"kept_by": PM, "kept_at": NOW.isoformat()}
    return make(store, "lesson", data)


def rule(store, name, status="active", **fields) -> str:
    data = {
        "name": name,
        "text": "A standing rule.",
        "origin": "person",
        "status": status,
        "learned_at": NOW.isoformat(),
    }
    return make(store, "rule", data | fields)


def run(store, *, given=(), applied_rules=(), at=NOW) -> str:
    log = {"given": [*given, *applied_rules], "rules_applied": list(applied_rules)}
    return make(
        store,
        "run",
        {
            "task": "notes",
            "provider": "stub",
            "model": "stub",
            "tier": "routine",
            "outcome": "ok",
            "started_at": at.isoformat(),
            "knowledge": log,
        },
    )


def changeset(store, run_id, *, applied=()) -> str:
    request = make(store, "request", {"task": "notes", "origin": "pm", "state": "done", "created_at": NOW.isoformat()})
    return make(
        store,
        "changeset",
        {
            "request": request,
            "ops": [],
            "status": "applied",
            "trust": "trusted",
            "run": run_id,
            "applied": list(applied),
            "created_at": NOW.isoformat(),
        },
    )


# ---- use counts ------------------------------------------------------------------------------------------------------


def test_use_counts_runs_that_applied_an_entry_runs_that_were_given_it_and_when_it_was_last_used(env):
    _, _, store = env
    cited, quiet, never_given, standing = lesson(store), lesson(store), lesson(store), rule(store, "standing")
    earlier, later = NOW - timedelta(days=5), NOW - timedelta(days=2)
    # The first run was given two entries and its changeset cites one; a second changeset of the same run citing it
    # again counts the run once.
    first = run(store, given=[cited, quiet], at=earlier)
    changeset(store, first, applied=[cited])
    changeset(store, first, applied=[cited])
    # The second run was given the same, cites it again and applies the rule by the log's own count.
    second = run(store, given=[cited, quiet], applied_rules=[standing], at=later)
    changeset(store, second, applied=[cited])
    # A third was given only the quiet one and applied nothing; a run with no knowledge log counts for nothing.
    run(store, given=[quiet], at=NOW)
    make(
        store,
        "run",
        {
            "task": "notes",
            "provider": "stub",
            "model": "stub",
            "tier": "routine",
            "outcome": "ok",
            "started_at": NOW.isoformat(),
        },
    )
    found = use_of(store.read())
    assert found[cited] == Use(used=2, given=2, last_used=later)
    assert found[quiet] == Use(used=0, given=3, last_used=None)
    assert found[standing] == Use(used=1, given=1, last_used=later)
    assert never_given not in found, "an entry no run was given has no use at all"


# ---- the route -------------------------------------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    application = create_app(ws, cfg, "screen-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer screen-token"}) as client:
        yield client, application.state.store


def test_the_knowledge_list_carries_how_much_each_entry_was_used(app):
    client, store = app
    used, unused = lesson(store, "Used wording."), lesson(store, "Unused wording.")
    began = datetime.now(UTC) - timedelta(days=2)
    run_id = run(store, given=[used], at=began)
    changeset(store, run_id, applied=[used])
    body = {e["id"]: e for e in client.get("/api/knowledge").json()}
    assert (body[used]["used"], body[used]["given"]) == (1, 1)
    assert datetime.fromisoformat(body[used]["last_used"]) == began
    assert (body[unused]["used"], body[unused]["given"], body[unused]["last_used"]) == (0, 0, None)


def test_the_rules_list_has_each_rule_with_its_reach_what_it_constrains_where_it_came_from_and_its_use(app):
    client, store = app
    scope = {"scope": "projects", "projects": [PROJECT]}
    applied = rule(store, "applied-rule", constrains=["question.add"], applies_to=scope)
    enforced = rule(store, "enforced-rule", check="a-check")
    retired = rule(store, "old-rule", status="retired")
    began = datetime.now(UTC) - timedelta(days=1)
    run(store, applied_rules=[applied], at=began)
    got = client.get("/api/knowledge/rules")
    assert got.status_code == 200, got.text
    body = {r["id"]: r for r in got.json()}
    assert {applied, enforced, retired} <= set(body)
    one = body[applied]
    assert (one["name"], one["status"], one["learned_from"], one["trust"]) == (
        "applied-rule",
        "active",
        "person",
        "trusted",
    )
    assert one["version"] == store.read().get("rule", applied).version
    assert one["constrains"] == ["question.add"] and one["applies_to"]["projects"] == [PROJECT]
    assert (one["used"], one["given"], one["enforced"]) == (1, 1, False)
    assert datetime.fromisoformat(one["last_used"]) == began
    assert body[enforced]["enforced"] is True and body[enforced]["used"] == 0
    assert [r["id"] for r in client.get("/api/knowledge/rules", params={"status": "retired"}).json()] == [retired]
    assert client.get("/api/knowledge/rules", params={"status": "nonsense"}).status_code == 422


# ---- an account that can't stand in ----------------------------------------------------------------------------------


def add_account(ws, name, **more) -> None:
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"][name] = {"adapter": "stub", "models": {"default": "scripted"}, "allowed_data": ["open"], **more}
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def hand_edit_chain(ws, *names, tier="routine"):
    """Put accounts in a tier's chain by editing the file, which the save's own refusal never sees."""
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["tiers"][tier]["fallback"] = [f"{name}/default" for name in names]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return ws.config(env={}, flags={"storage.backups.automatic": False})


def account_lines(ws, cfg, store):
    return [line for line in queue(ws, store, cfg, NOW) if line.kind == "account_check"]


def test_an_unchecked_account_in_a_hand_edited_chain_has_a_line_until_its_check_passes(env):
    ws, _, store = env
    without_first_go(ws.config_dir)
    add_account(ws, "second")
    cfg = hand_edit_chain(ws, "second")
    (line,) = account_lines(ws, cfg, store)
    assert (line.group, line.account, line.tier, line.model, line.check_failed) == (
        "risk",
        "second",
        "routine",
        "default",
        False,
    )
    # A test with no tier doesn't count for the tier's work; the test for that tier does, and the line goes.
    set_responder(connection_answer)
    remember(ws, cfg, account_test(cfg, {}, "second", store=store))
    assert len(account_lines(ws, cfg, store)) == 1
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert account_lines(ws, cfg, store) == []


def test_a_checked_or_accepted_account_has_no_line_and_neither_has_an_account_outside_every_chain(env):
    ws, _, store = env
    without_first_go(ws.config_dir)
    add_account(ws, "second")
    add_account(ws, "third", accepted_unchecked=True)
    add_account(ws, "elsewhere")
    cfg = hand_edit_chain(ws, "second", "third")
    set_responder(connection_answer)
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert account_lines(ws, cfg, store) == []
    assert cannot_stand_in(ws, cfg) == []


def test_a_failed_check_has_a_line_that_says_so_even_for_an_accepted_account_and_goes_when_it_passes(env):
    ws, _, store = env
    without_first_go(ws.config_dir)
    add_account(ws, "second")
    add_account(ws, "third", accepted_unchecked=True)
    cfg = hand_edit_chain(ws, "second", "third")
    set_responder(lambda task: (_ for _ in ()).throw(AiError("other", "refused")))
    for name in ("second", "third"):
        remember(ws, cfg, account_test(cfg, {}, name, tier="routine", store=store))
    found = {line.account: line for line in account_lines(ws, cfg, store)}
    assert {name: line.check_failed for name, line in found.items()} == {"second": True, "third": True}
    set_responder(connection_answer)
    for name in ("second", "third"):
        remember(ws, cfg, account_test(cfg, {}, name, tier="routine", store=store))
    assert account_lines(ws, cfg, store) == []


def test_the_line_comes_back_when_the_account_is_changed_after_it_passed(env):
    ws, _, store = env
    without_first_go(ws.config_dir)
    add_account(ws, "second")
    cfg = hand_edit_chain(ws, "second")
    set_responder(connection_answer)
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    assert account_lines(ws, cfg, store) == []
    add_account(ws, "second", timeout_seconds=77)
    changed = hand_edit_chain(ws, "second")
    (line,) = account_lines(ws, changed, store)
    assert line.check_failed is False, "a changed account is unchecked, not failed"


def test_the_today_route_carries_the_account_line_with_what_its_test_needs(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    without_first_go(ws.config_dir)
    add_account(ws, "second")
    cfg = hand_edit_chain(ws, "second")
    application = create_app(ws, cfg, "screen-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer screen-token"}) as client:
        lines = [line for line in client.get("/api/today/queue").json() if line["kind"] == "account_check"]
    assert [(x["account"], x["tier"], x["model"], x["check_failed"]) for x in lines] == [
        ("second", "routine", "default", False)
    ]
