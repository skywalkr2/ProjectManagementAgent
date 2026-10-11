"""Plugin task kinds: their own prompt and guidance, the record a run is about, what the run sees (parts marked by
trust and by whether they may be quoted), evidence checked against that material, and defaults the workspace
overrides."""

import json
from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config import load_config
from engine.dispatcher import process
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
CHAPTER = "The ferry left at dawn. Nobody on the pier waved, and the gulls followed it out past the breakwater."

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import EvidenceIn, OpModel, PacketParts, Part, Record, RefTo, Settings, StoreError

class Config(Settings):
    pass

class Chapter(Record):
    record_kind: ClassVar[str] = "p05/chapter"
    prefix: ClassVar[str] = "CHP"
    title: str
    text: str = ""

class Finding(Record):
    record_kind: ClassVar[str] = "p05/finding"
    prefix: ClassVar[str] = "FND"
    chapter: Annotated[str, RefTo("p05/chapter")]
    note: str
    quote: str

class AddChapter(OpModel):
    op: Literal["p05/add-chapter"] = "p05/add-chapter"
    writes: ClassVar[dict] = {"p05/chapter": ("*",)}
    title: str
    text: str = ""

class AddFinding(OpModel):
    op: Literal["p05/add-finding"] = "p05/add-finding"
    writes: ClassVar[dict] = {"p05/finding": ("*",)}
    chapter: str
    note: str
    evidence: EvidenceIn

def add_chapter(op, writer, cfg):
    writer.create("p05/chapter", {"title": op.title, "text": op.text})

def add_finding(op, writer, cfg):
    writer.create("p05/finding", {"chapter": op.chapter, "note": op.note, "quote": op.evidence.quote})

def packet(target, view, settings, note):
    if not target.data["text"]:
        raise StoreError("This chapter has no text yet.")
    return PacketParts(
        stable=[Part("Style sheet", "Past tense, close third person.", trusted=True)],
        request=[
            Part("Chapter " + target.id, target.data["text"]),
            Part("The writer's plan", "The ferry is a symbol of leaving home.", reference_only=True),
        ],
    )

def register(registrar):
    registrar.record_type(Chapter)
    registrar.record_type(Finding)
    registrar.op(AddChapter, "data", add_chapter)
    registrar.op(AddFinding, "data", add_finding)
    registrar.task_kind(
        "p05/review",
        ops=("p05/add-finding",),
        label="Review the chapter",
        prompt="p05/review",
        playbook="p05/review",
        on="p05/chapter",
        packet=packet,
        max_output=1500,
        expected_output=300,
        tier="routine",
    )
"""


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p05"
    (plugin / "prompts").mkdir(parents=True)
    (plugin / "guidance").mkdir()
    (plugin / "prompts" / "review.md").write_text("You review one chapter for {{assistant_name}}'s writer.")
    (plugin / "guidance" / "review.md").write_text("Point to the exact passage for every finding.")
    manifest = {
        "name": "p05",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Plugin task kinds fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p05/chapter", "p05/finding"],
            "ops": ["p05/add-chapter", "p05/add-finding"],
            "ai_task_kinds": ["p05/review"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (plugin / "fixture.py").write_text(FIXTURE)
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p05"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p05"), store.plugins.status["p05"].reason
    yield ws, cfg, store
    store.close()
    set_responder(None)


def chapter(env, text=CHAPTER):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    _, cfg, store = env
    ops = [{"op": "p05/add-chapter", "title": "The Crossing", "text": text}]
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-0", None, "", "", "trusted"))
    apply_changeset(cs, [], ctx, run=None)
    return store.read().list("p05/chapter")[-1]


def start(env, record, note=""):
    from engine.plugin_host import check_about

    _, _, store = env
    about = {"kind": record.kind, "id": record.id}
    with store.transaction() as tx:
        check_about(tx, store.plugins.task_kind("p05/review"), about)
        from engine.storage import WriteContext

        return tx.create(
            "request",
            {
                "task": "p05/review",
                "note": note or None,
                "about": about,
                "origin": "pm",
                "state": "queued",
                "created_at": NOW.isoformat(),
            },
            WriteContext("pm", "trusted", "ui"),
        ).id


def answer(*bodies):
    asked = []
    queue = [json.dumps(b) for b in bodies]

    def responder(task):
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    set_responder(responder)
    return asked


def finding(record, quote):
    return {
        "summary": "One finding.",
        "ops": [
            {
                "op": "p05/add-finding",
                "chapter": record.id,
                "note": "Nobody waves: say why.",
                "evidence": {"quote": quote},
            }
        ],
    }


def run(env, request_id):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def test_a_run_sees_the_plugins_prompt_guidance_and_parts_in_order(env):
    _, _, store = env
    record = chapter(env)
    asked = answer(finding(record, "Nobody on the pier waved"))
    cs_id = run(env, start(env, record, note="Look at the opening."))
    task = asked[0]
    assert task.instructions.startswith("You review one chapter for") and "{{" not in task.instructions
    assert "Point to the exact passage" in task.stable and "Past tense, close third person." in task.stable
    assert 'quote="no"' in task.request and "Never quote or reproduce" in task.stable
    assert (
        f'<untrusted source="Chapter {record.id}">' in task.request and "<note>\nLook at the opening." in task.request
    )
    assert "# People" not in task.stable  # a plugin's run sees what its packet gives it, not the notes context
    assert task.max_output == 1500
    found = store.read().list("p05/finding")
    assert cs_id and found[0].data["quote"] == "Nobody on the pier waved"
    ledger = [e for e in store.read().ledger() if e["record_id"] == found[0].id and e["evidence"]]
    assert ledger[0]["evidence"]["source"] == f"p05/chapter:{record.id}"


def test_evidence_must_come_from_material_the_run_may_quote(env):
    _, _, store = env
    record = chapter(env)
    answer(finding(record, "The ferry is a symbol of leaving home"))  # from the reference-only plan
    cs_id = run(env, start(env, record))
    ops = store.read().get("changeset", cs_id).data["ops"] if cs_id else []
    assert store.read().list("p05/finding") == []
    assert not ops or ops[0]["status"] == "refused"


def test_a_packet_that_cant_be_built_waits_for_the_person_with_its_reason(env):
    _, _, store = env
    record = chapter(env, text="")
    request_id = start(env, record)
    assert run(env, request_id) is None
    request = store.read().get("request", request_id).data
    assert request["state"] == "needs_you" and request["waiting"] == "This chapter has no text yet."


def test_work_on_record_content_is_untrusted(env):
    _, _, store = env
    record = chapter(env)
    answer(finding(record, "Nobody on the pier waved"))
    cs_id = run(env, start(env, record))
    assert store.read().get("changeset", cs_id).data["trust"] == "untrusted"


def test_the_workspace_overrides_a_task_kinds_defaults_field_by_field(env, tmp_path):
    from engine.tasks import settings

    ws, _, store = env
    kind = store.plugins.task_kind("p05/review")
    cfg = ws.config(env={}, flags={"ai.tasks.p05/review": {"max_output": 900}})
    chosen = settings(cfg, kind)
    assert chosen.max_output == 900 and chosen.expected_output == 300


def test_the_workspace_overrides_a_plugins_prompt(env):
    ws, _, store = env
    record = chapter(env)
    (ws.root / "prompts" / "p05").mkdir(parents=True, exist_ok=True)
    (ws.root / "prompts" / "p05" / "review.md").write_text("A house prompt for chapter reviews.")
    asked = answer(finding(record, "Nobody on the pier waved"))
    run(env, start(env, record))
    assert asked[0].instructions == "A house prompt for chapter reviews."


def test_a_task_kind_on_a_record_needs_one_of_that_kind(env):
    from engine.plugin_host import check_about
    from engine.storage import StoreError

    _, _, store = env
    kind = store.plugins.task_kind("p05/review")
    with store.transaction() as tx:
        with pytest.raises(StoreError, match="works on a chapter"):
            check_about(tx, kind, None)
        with pytest.raises(StoreError, match="no chapter"):
            check_about(tx, kind, {"kind": "p05/chapter", "id": "CHP-99"})


def test_a_missing_prompt_file_refuses_the_plugin(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p05"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    manifest = {
        "name": "p05",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "x",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p05/chapter", "p05/finding"],
            "ops": ["p05/add-chapter", "p05/add-finding"],
            "ai_task_kinds": ["p05/review"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p05"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    assert "prompts/review.md is missing" in store.plugins.status["p05"].reason
    store.close()


def test_the_person_starts_a_task_kind_on_a_record_through_the_api(env):
    from api.app import create_app

    ws, cfg, store = env
    record = chapter(env)
    store.close()
    token = "test-token"
    client = TestClient(create_app(ws, cfg, token, start_worker=False))
    client.headers["Authorization"] = f"Bearer {token}"
    api = cfg.server.base_path.rstrip("/") + "/api"
    offered = client.get(f"{api}/task-kinds", params={"kind": "p05/chapter"}).json()
    assert offered == [{"name": "p05/review", "label": "Review the chapter", "on": "p05/chapter"}]
    started = client.post(f"{api}/task-kinds/p05/review/start", json={"about": {"kind": record.kind, "id": record.id}})
    assert started.status_code == 200, started.text
    refused = client.post(f"{api}/task-kinds/p05/review/start", json={})
    assert refused.status_code == 409 and "works on a chapter" in refused.json()["detail"]


# ---- refusals --------------------------------------------------------------------------------------------------------


def test_a_refusal_waits_for_the_person_and_is_never_retried_or_escalated(env, monkeypatch):
    from engine.ai.adapters import stub
    from engine.ai.task import AiResult

    _, _, store = env
    record = chapter(env)
    calls = []

    def run_refused(self, task, model):
        calls.append(task)
        return AiResult(text="", model_served="stub", seconds=0.0, refused=True, refusal="Declined under policy 4.")

    monkeypatch.setattr(stub.StubAdapter, "run", run_refused)
    request_id = start(env, record)
    assert run(env, request_id) is None
    assert len(calls) == 1  # no fix round, no fallback account, no stronger tier
    request = store.read().get("request", request_id).data
    assert request["state"] == "needs_you"
    assert request["waiting"].startswith("The AI account refused this under its own rules (Declined under policy 4)")
    runs = [r.data for r in store.read().list("run") if r.data["request"] == request_id]
    assert runs[-1]["outcome"] == "refused" and runs[-1]["error_detail"] == "Declined under policy 4."
    from fastapi.testclient import TestClient

    from api.app import create_app

    ws, cfg, _ = env
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    changes = c.get(cfg.server.base_path.rstrip("/") + "/api/changes").json()
    assert next(item for item in changes if item["id"] == request_id)["refused"] is True


def test_the_adapter_reads_refusals_from_the_provider_signal_only():
    import sys

    import httpx

    from engine.ai.adapters import ADAPTERS

    http_adapter = next(cls for name, cls in ADAPTERS.items() if name != "stub")
    classify_http_error = sys.modules[http_adapter.__module__].classify_http_error

    body = {"error": {"code": "content_policy_violation", "message": "No."}}
    assert classify_http_error(httpx.Response(400, json=body)).kind == "refused"
    worded = {"error": {"code": "bad_request", "message": "content policy violation"}}
    assert classify_http_error(httpx.Response(400, json=worded)).kind == "other"  # words alone never decide


def test_after_a_refusal_the_person_sends_it_to_another_account(env, monkeypatch):
    from engine.ai.router import accounts
    from engine.dispatcher import retry

    ws, cfg, store = env
    record = chapter(env)
    request_id = start(env, record)
    with store.transaction() as tx:
        from engine.storage import WriteContext

        cur = tx.get("request", request_id)
        tx.update(
            "request",
            request_id,
            {"state": "needs_you"},
            WriteContext("engine", "trusted", "x"),
            read_version=cur.version,
        )
    options = accounts(cfg, "internal")
    assert options
    with pytest.raises(ValueError, match="isn't an account"):
        retry(store, request_id, use="nowhere/nothing")
    retry(store, request_id, use=options[0])
    assert store.read().get("request", request_id).data["use"] == options[0]
    asked = answer(finding(record, "Nobody on the pier waved"))
    assert run(env, request_id) is not None and asked
    runs = [r.data for r in store.read().list("run") if r.data["request"] == request_id]
    assert runs[-1]["provider"] == options[0].partition("/")[0]


# ---- content levels -----------------------------------------------------------------------------------------------


def test_routing_skips_accounts_that_dont_take_the_material(env):
    from engine.ai.router import NoProvider, accounts, choices

    ws, _, _ = env
    flags = {
        "ai.content_levels": {"mature": "Adult material."},
        "ai.providers.stub.content_levels": [],
    }
    cfg = ws.config(env={}, flags=flags)
    with pytest.raises(NoProvider, match="doesn't take mature material"):
        choices(cfg, "notes", "internal", content=frozenset({"mature"}))
    assert choices(cfg, "notes", "internal")  # material with no levels goes as before
    assert accounts(cfg, "internal", frozenset({"mature"})) == []
    takes_it = ws.config(env={}, flags={**flags, "ai.providers.stub.content_levels": ["mature"]})
    assert choices(takes_it, "notes", "internal", content=frozenset({"mature"}))


def test_a_runs_levels_come_from_its_record_and_project(env):
    from engine.dispatcher import content_levels
    from engine.storage import WriteContext

    _, _, store = env
    record = chapter(env)
    project = store.read().list("project")[0]
    with store.transaction() as tx:
        tx.update(
            "project",
            project.id,
            {"content_levels": ["mature"]},
            WriteContext("pm", "trusted", "x"),
            read_version=project.version,
        )
    assert content_levels(store, {"about": {"kind": "project", "id": project.id}}) == frozenset({"mature"})
    assert content_levels(store, {"about": {"kind": record.kind, "id": record.id}}) == frozenset()


def test_unknown_levels_on_an_account_are_refused_in_the_settings(env):
    from engine.config import ConfigError

    ws, _, _ = env
    with pytest.raises(ConfigError, match="not in content_levels"):
        ws.config(env={}, flags={"ai.providers.stub.content_levels": ["nope"]})


def test_only_the_person_sets_a_records_content_levels(env):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    _, cfg, store = env
    ops = [
        {
            "op": "record.set",
            "kind": "project",
            "id": store.read().list("project")[0].id,
            "field": "content_levels",
            "value": ["mature"],
        }
    ]
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-0", None, "", "", "trusted"))
    cs_id = apply_changeset(cs, [], ctx, run=None)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "refused"
