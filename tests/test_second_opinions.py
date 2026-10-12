"""Roles and independent second opinions: a check runs on an account other than the ones that wrote the record it is
about, or on the same account only when the person accepts that, and the run records which it was."""

import json
from datetime import UTC, datetime

import pytest
import yaml

from engine.ai.adapters import stub
from engine.ai.router import Independence, NoProvider, choices
from engine.ai.task import AiResult
from engine.config import load_config
from engine.storage import WriteContext
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import LongText, OpModel, PacketParts, Part, Record, RefTo, Settings

class Config(Settings):
    pass

class Chapter(Record):
    record_kind: ClassVar[str] = "p12/chapter"
    prefix: ClassVar[str] = "CHR"
    title: str
    body: Annotated[str | None, LongText("plain")] = None

class Finding(Record):
    record_kind: ClassVar[str] = "p12/finding"
    prefix: ClassVar[str] = "FDR"
    chapter: Annotated[str, RefTo("p12/chapter")]
    note: str

class AddFinding(OpModel):
    op: Literal["p12/add-finding"] = "p12/add-finding"
    writes: ClassVar[dict] = {"p12/finding": ("*",)}
    chapter: str
    note: str

def add_finding(op, writer, cfg):
    writer.create("p12/finding", {"chapter": op.chapter, "note": op.note})

def packet(target, view, settings, note):
    return PacketParts(request=[Part("Text", view.text(target, "body"))])

def register(registrar):
    registrar.record_type(Chapter)
    registrar.record_type(Finding)
    registrar.op(AddFinding, "data", add_finding)
    registrar.task_kind("p12/draft", label="Draft", output="draft", field="body", on="p12/chapter", packet=packet)
    registrar.task_kind(
        "p12/review", label="Review", ops=("p12/add-finding",), on="p12/chapter", packet=packet, role="check"
    )
"""


def workspace(tmp_path, ai=None):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p12"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p12",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Second opinions fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p12/chapter", "p12/finding"],
            "ops": ["p12/add-finding"],
            "ai_task_kinds": ["p12/draft", "p12/review"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p12"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    ai_file = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(ai_file.read_text())
    data["providers"]["second"] = {"adapter": "stub", "models": {"default": "scripted"}, "allowed_data": ["internal"]}
    data["budgets"]["confirm_above_usd"] = 100
    for key, value in (ai or {}).items():
        data[key] = value
    ai_file.write_text(yaml.safe_dump(data))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p12"), store.plugins.status["p12"].reason
    return ws, cfg, store


def answers(monkeypatch, *texts):
    queue = list(texts)

    def fake(self, task, model):
        text = queue.pop(0) if len(queue) > 1 else queue[0]
        return AiResult(text=text, model_served="stub", seconds=0.0)

    monkeypatch.setattr(stub.StubAdapter, "run", fake)


def start(store, task, record):
    with store.transaction() as tx:
        return tx.create(
            "request",
            {
                "task": task,
                "about": {"kind": record.kind, "id": record.id},
                "origin": "pm",
                "state": "queued",
                "created_at": NOW.isoformat(),
            },
            WriteContext("pm", "trusted", "ui"),
        ).id


def process(env, request_id):
    from engine.ai.router import Router
    from engine.dispatcher import process as dispatch

    ws, cfg, store = env
    return dispatch(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def drafted_chapter(env, monkeypatch):
    """A chapter whose text the assistant drafted on the `stub` account."""
    _, _, store = env
    with store.transaction() as tx:
        record = tx.create("p12/chapter", {"title": "The Crossing"}, WriteContext("pm", "trusted", "ui"))
    answers(monkeypatch, "The ferry left at dawn.\n")
    process(env, start(store, "p12/draft", record))
    return store.read().get("p12/chapter", record.id)


def review_answer(record):
    return json.dumps(
        {"summary": "One finding.", "ops": [{"op": "p12/add-finding", "chapter": record.id, "note": "Say who waits."}]}
    )


def last_run(store, request_id):
    return [r for r in store.read().list("run") if r.data["request"] == request_id][-1]


def test_choices_leave_out_the_accounts_that_wrote_the_work(tmp_path):
    tiers = {"routine": {"use": "stub/default", "fallback": ["second/default"]}, "deep": {"use": "stub/default"}}
    ws, cfg, store = workspace(tmp_path, {"tiers": tiers})
    store.close()
    picked = choices(cfg, "x", "internal", tier="routine", independent=Independence(frozenset({"stub"})))
    assert [c.provider for c in picked] == ["second"]
    last = choices(cfg, "x", "internal", tier="routine", independent=Independence(frozenset({"stub"}), True))
    assert [c.provider for c in last] == ["second", "stub"]
    with pytest.raises(NoProvider, match="needs an account other than the one that wrote the work"):
        choices(cfg, "x", "internal", tier="routine", independent=Independence(frozenset({"stub", "second"})))
    mine = choices(cfg, "x", "internal", use="stub/default", independent=Independence(frozenset({"stub"})))
    assert [c.provider for c in mine] == ["stub"]


def test_a_check_runs_on_another_account(tmp_path, monkeypatch):
    ai = {
        "tiers": {
            "routine": {"use": "stub/default", "escalate_to": "deep"},
            "deep": {"use": "stub/default"},
            "review": {"use": "stub/default", "fallback": ["second/default"]},
        },
        "roles": {"check": {"tier": "review"}},
    }
    env = workspace(tmp_path, ai)
    _, _, store = env
    record = drafted_chapter(env, monkeypatch)
    answers(monkeypatch, review_answer(record))
    request_id = start(store, "p12/review", record)
    assert process(env, request_id) is not None
    run = last_run(store, request_id)
    assert run.data["provider"] == "second" and run.data["tier"] == "review"
    assert run.data["independence"] == "other_account"
    store.close()


def test_a_check_with_no_other_account_waits_and_says_why(tmp_path, monkeypatch):
    env = workspace(tmp_path, {"roles": {"check": {"tier": "deep"}}})
    _, _, store = env
    record = drafted_chapter(env, monkeypatch)
    answers(monkeypatch, review_answer(record))
    request_id = start(store, "p12/review", record)
    assert process(env, request_id) is None
    waiting = store.read().get("request", request_id).data
    assert waiting["state"] == "needs_you" and "other than the one that wrote the work (stub)" in waiting["waiting"]
    store.close()


def test_the_same_account_when_the_person_accepts_it(tmp_path, monkeypatch):
    env = workspace(tmp_path, {"roles": {"check": {"tier": "deep", "same_account": True}}})
    _, _, store = env
    record = drafted_chapter(env, monkeypatch)
    answers(monkeypatch, review_answer(record))
    request_id = start(store, "p12/review", record)
    assert process(env, request_id) is not None
    run = last_run(store, request_id)
    assert run.data["provider"] == "stub" and run.data["independence"] == "same_account"
    draft_run = [r for r in store.read().list("run") if r.data["task"] == "p12/draft"][-1]
    assert draft_run.data["independence"] is None
    store.close()


def test_a_kinds_own_setting_wins_over_its_role(tmp_path, monkeypatch):
    ai = {
        "roles": {"check": {"tier": "deep", "same_account": True}},
        "tasks": {"notes": {"tier": "routine"}, "p12/review": {"tier": "routine", "same_account": False}},
    }
    env = workspace(tmp_path, ai)
    ws, cfg, store = env
    from engine.tasks import settings

    assert settings(cfg, store.plugins.task_kind("p12/review")).tier == "routine"
    record = drafted_chapter(env, monkeypatch)
    answers(monkeypatch, review_answer(record))
    request_id = start(store, "p12/review", record)
    assert process(env, request_id) is None
    store.close()


def test_a_role_must_name_a_tier(tmp_path):
    with pytest.raises(Exception, match="the 'check' role names the tier 'nowhere'"):
        workspace(tmp_path, {"roles": {"check": {"tier": "nowhere"}}})


def test_a_task_kinds_role_is_one_of_three():
    from engine.plugin_api import Registrar, Settings

    registrar = Registrar("p13", Settings())
    with pytest.raises(ValueError, match="role is"):
        registrar.task_kind("p13/x", ops=("note",), role="judge")
