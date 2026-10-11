"""Draft task kinds: the model writes prose, the core wraps it as a pending version of a long text field, lints run on
it with a fix round, and a draft cut off at the output limit is continued once, then held."""

from datetime import UTC, datetime

import pytest
import yaml

from engine.ai.adapters import stub
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.ai.task import AiResult
from engine.config import load_config
from engine.dispatcher import process
from engine.storage import WriteContext
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
TEXT = "The ferry left at dawn.\n\nNobody on the pier waved.\n"

FIXTURE = """
import re
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import LintFinding, LongText, OpModel, PacketParts, Part, Record, Settings

class Config(Settings):
    pass

class Chapter(Record):
    record_kind: ClassVar[str] = "p09/chapter"
    prefix: ClassVar[str] = "CHB"
    title: str
    body: Annotated[str | None, LongText("plain")] = None

class AddChapter(OpModel):
    op: Literal["p09/add-chapter"] = "p09/add-chapter"
    writes: ClassVar[dict] = {"p09/chapter": ("*",)}
    title: str
    text: str

def add_chapter(op, writer, cfg):
    chapter = writer.create("p09/chapter", {"title": op.title})
    writer.set_text("p09/chapter", chapter.id, "body", op.text)

def packet(target, view, settings, note):
    return PacketParts(request=[Part("Current text", view.text(target, "body"))])

def no_very(op, view, settings):
    match = re.search(r"\\bvery \\w+", op.text)
    return [LintFinding("Leans on 'very'.", passage=match.group(0), guidance="Use one exact word.")] if match else []

def register(registrar):
    registrar.record_type(Chapter)
    registrar.op(AddChapter, "data", add_chapter)
    registrar.task_kind(
        "p09/revise", label="Revise the chapter", output="draft", field="body", on="p09/chapter", packet=packet
    )
    registrar.lint("p09/no-very", no_very, ops=("text.draft",), severity="return")
"""


def workspace(tmp_path, fixture=FIXTURE):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p09"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(fixture)
    manifest = {
        "name": "p09",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Drafts fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {
            "record_types": ["p09/chapter"],
            "ops": ["p09/add-chapter"],
            "ai_task_kinds": ["p09/revise"],
            "lints": ["p09/no-very"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p09"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    assert store.plugins.active("p09"), store.plugins.status["p09"].reason
    yield ws, cfg, store
    store.close()
    set_responder(None)


def chapter(env):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    _, cfg, store = env
    cs = CHANGESET.validate_python(
        {"ops": [{"op": "p09/add-chapter", "title": "The Crossing", "text": TEXT}]},
        context={"op_models": store.plugins.ops},
    )
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-0", None, "", "", "trusted"), actor="pm"
    )
    apply_changeset(cs, [], ctx, run=None)
    return store.read().list("p09/chapter")[-1]


def start(env, record):
    _, _, store = env
    with store.transaction() as tx:
        return tx.create(
            "request",
            {
                "task": "p09/revise",
                "about": {"kind": record.kind, "id": record.id},
                "origin": "pm",
                "state": "queued",
                "created_at": NOW.isoformat(),
            },
            WriteContext("pm", "trusted", "ui"),
        ).id


def run(env, request_id):
    ws, cfg, store = env
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def answers(monkeypatch, *results):
    """The stub answers with these AiResults in turn (the last one repeats), recording what it was asked."""
    asked, queue = [], list(results)

    def fake(self, task, model):
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(stub.StubAdapter, "run", fake)
    return asked


def prose(text, truncated=False):
    return AiResult(text=text, model_served="stub", seconds=0.0, truncated=truncated)


def pending(store, record):
    return [v for v in store.read().list("text_version") if v.data["owner_id"] == record.id][-1]


def test_a_draft_task_answers_in_prose_and_files_a_pending_version(env, monkeypatch):
    _, _, store = env
    record = chapter(env)
    revised = "The ferry left before dawn.\n\nNobody on the pier waved.\n"
    asked = answers(monkeypatch, prose(revised))
    cs_id = run(env, start(env, record))
    assert asked[0].output == "text" and "Answer with the text only" in asked[0].request
    assert "# Op reference" not in asked[0].stable
    version = pending(store, record)
    assert version.data["status"] == "pending" and version.data["source"] == "draft" and version.data["base"] == 1
    assert [s["kind"] for s in version.data["authorship"]] == ["assistant_edit", "person"]
    assert version.data["run"]
    assert store.read().get("changeset", cs_id).data["ops"][0]["op"]["op"] == "text.draft"


def test_a_fenced_answer_loses_its_fence(env, monkeypatch):
    _, _, store = env
    record = chapter(env)
    answers(monkeypatch, prose("```\nThe ferry left early.\n```"))
    run(env, start(env, record))
    from engine.texts import read_text

    assert read_text(store, pending(store, record).data["sha256"]) == "The ferry left early.\n"


def test_a_draft_cut_off_is_continued_once(env, monkeypatch):
    _, _, store = env
    record = chapter(env)
    asked = answers(monkeypatch, prose("The ferry left be", truncated=True), prose("fore dawn.\n"))
    run(env, start(env, record))
    from engine.texts import read_text

    assert read_text(store, pending(store, record).data["sha256"]) == "The ferry left before dawn.\n"
    assert "<so-far>\nThe ferry left be\n</so-far>" in asked[1].request


def test_a_draft_cut_off_twice_waits_for_the_person(env, monkeypatch):
    _, _, store = env
    record = chapter(env)
    answers(monkeypatch, prose("The ferry", truncated=True), prose(" left", truncated=True))
    request_id = start(env, record)
    assert run(env, request_id) is None
    waiting = store.read().get("request", request_id).data
    assert waiting["state"] == "needs_you" and "cut off at the output limit twice" in waiting["waiting"]


def test_a_return_lint_on_a_draft_gets_a_fix_round(env, monkeypatch):
    _, _, store = env
    record = chapter(env)
    asked = answers(monkeypatch, prose("A very calm crossing.\n"), prose("A glassy crossing.\n"))
    run(env, start(env, record))
    from engine.texts import read_text

    assert len(asked) == 2 and 'the passage: "very calm"' in asked[1].request
    assert read_text(store, pending(store, record).data["sha256"]) == "A glassy crossing.\n"


def test_a_draft_task_must_name_a_long_text_field(tmp_path):
    broken = FIXTURE.replace('output="draft", field="body"', 'output="draft", field="title"')
    ws, cfg, store = workspace(tmp_path, broken)
    assert "isn't a long text field" in store.plugins.status["p09"].reason
    store.close()
