"""A file kind declares the data level of what is added under it: an upload, a person action's file and a run on the
file all follow it, the person's explicit choice at the upload stands, and a manifest must say it keeps that level."""

from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.ai.adapters import stub
from engine.ai.task import AiResult
from engine.config import load_config
from engine.files import add_file
from engine.storage import WriteContext
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)

FIXTURE = """
from engine.plugin_api import NewFile, PacketParts, Part, Proposal, Settings

class Config(Settings):
    pass

def packet(target, view, settings, note):
    return PacketParts(request=[Part("File", target.data["name"])])

def make_file(target, context, choices):
    return Proposal("Add a file", files=[NewFile("made.txt", "text/plain", b"made", file_kind="p14/secret")])

def register(registrar):
    registrar.file_kind("p14/secret", label="Secret document", accept=("text/plain",), data_level="restricted")
    registrar.file_kind("p14/plain", label="Plain document", accept=("text/plain",))
    registrar.task_kind("p14/read", label="Read", ops=("note",), on="file", packet=packet)
    registrar.action("p14/make", label="Make a file", run=make_file)
"""

PROVIDES = {
    "file_kinds": ["p14/secret", "p14/plain"],
    "ai_task_kinds": ["p14/read"],
    "actions": ["p14/make"],
}


def workspace(tmp_path, levels=("open", "internal", "restricted"), fixture=FIXTURE):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p14"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(fixture)
    manifest = {
        "name": "p14",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "File kind levels fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "requires": {"data_levels": list(levels)},
        "provides": PROVIDES,
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p14"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    ai_file = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(ai_file.read_text())
    data["budgets"]["confirm_above_usd"] = 100
    ai_file.write_text(yaml.safe_dump(data))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def env(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    assert store.plugins.active("p14"), store.plugins.status["p14"].reason
    yield ws, cfg, store
    store.close()


def text_file(env, kind, **more):
    _, cfg, store = env
    return add_file(store, cfg, kind.encode(), name="d.txt", media_type="text/plain", file_kind=kind, **more)


def test_a_restricted_kinds_file_is_restricted_with_no_choice_and_the_persons_lower_choice_is_kept(env):
    assert text_file(env, "p14/secret").data["sensitivity"] == "restricted"
    assert text_file(env, "p14/secret", data_level="internal").data["sensitivity"] == "internal"
    assert text_file(env, "p14/secret", data_level="open").data["sensitivity"] == "open"
    assert text_file(env, "p14/plain").data["sensitivity"] == "internal"
    assert text_file(env, "attachment").data["sensitivity"] == "internal"
    assert text_file(env, "p14/plain", data_level="restricted").data["sensitivity"] == "restricted"


def test_an_upload_with_no_choice_takes_the_kinds_level_and_an_explicit_choice_stands(env):
    from api.app import create_app

    ws, cfg, store = env
    store.close()
    client = TestClient(create_app(ws, cfg, "t", start_worker=False))
    client.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    text = {"Content-Type": "text/plain"}

    def level(query):
        return client.post(f"{api}/files?name=d.txt&{query}", content=b"x", headers=text).json()["data_level"]

    assert level("kind=p14/secret") == "restricted"
    assert level("kind=p14/secret&data_level=internal") == "internal"
    assert level("kind=p14/plain") == "internal"
    assert level("kind=attachment") == "internal"


def test_a_file_a_person_action_makes_takes_the_kinds_level(env):
    from engine import actions

    _, cfg, store = env
    pending = actions.preview(store, cfg, "p14/make")
    actions.apply(store, cfg, pending.token, {})
    made = [f for f in store.read().list("file") if f.data["file_kind"] == "p14/secret"]
    assert [f.data["sensitivity"] for f in made] == ["restricted"]


def test_a_pack_cannot_change_a_files_level_afterwards(env):
    from engine.records import REGISTRY

    file = text_file(env, "p14/secret")
    assert REGISTRY["file"].needs_person("sensitivity", "open")
    assert REGISTRY["file"].needs_person("sensitivity", "internal")
    assert file.data["sensitivity"] == "restricted"


def test_a_manifest_that_doesnt_list_the_level_is_refused_in_plain_words(tmp_path):
    ws, cfg, store = workspace(tmp_path, levels=("open", "internal"))
    try:
        assert not store.plugins.active("p14")
        reason = store.plugins.status["p14"].reason
        assert "p14/secret holds restricted material, which the add-on doesn't say it keeps" in reason
    finally:
        store.close()


def test_a_file_kinds_level_must_be_one_of_the_three(tmp_path):
    bad = FIXTURE.replace('data_level="restricted"', 'data_level="secret"')
    ws, cfg, store = workspace(tmp_path, fixture=bad)
    try:
        assert not store.plugins.active("p14")
        assert "data_level must be open, internal or restricted" in store.plugins.status["p14"].reason
    finally:
        store.close()


def answers(monkeypatch):
    def fake(self, task, model):
        return AiResult(text='{"summary": "Read it.", "ops": []}', model_served="stub", seconds=0.0)

    monkeypatch.setattr(stub.StubAdapter, "run", fake)


def start(store, record):
    with store.transaction() as tx:
        return tx.create(
            "request",
            {
                "task": "p14/read",
                "about": {"kind": "file", "id": record.id},
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


def test_a_run_on_a_restricted_file_goes_only_to_an_account_allowed_restricted(env, monkeypatch):
    _, cfg, store = env
    answers(monkeypatch)
    secret, plain = text_file(env, "p14/secret"), text_file(env, "p14/plain")
    accounts = cfg.ai.providers
    for account in accounts.values():
        account.allowed_data = ["open", "internal"]

    stopped = start(store, secret)
    assert process(env, stopped) is None
    waiting = store.read().get("request", stopped).data
    assert waiting["state"] == "needs_you" and waiting["cause"]["kind"] == "data_level"
    assert waiting["cause"]["level"] == "restricted"

    # The same run on a file that is only internal goes to the same accounts.
    assert process(env, start(store, plain)) is not None

    for account in accounts.values():
        account.allowed_data = ["open", "internal", "restricted"]
    assert process(env, stopped) is not None
