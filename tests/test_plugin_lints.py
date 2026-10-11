"""Plugin lints: soft checks on the assistant's proposals, with the passage and the guidance, a default severity the
workspace overrides, and a fix round on "return"."""

import json
from datetime import UTC, datetime

import pytest
import yaml

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config import load_config
from engine.dispatcher import process
from engine.intake import hand_in
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)

FIXTURE = """
import re
from engine.plugin_api import LintFinding, Settings

class Config(Settings):
    pass

def no_very(op, view, settings):
    match = re.search(r"\\bvery \\w+", op.text)
    if match is None:
        return []
    return [LintFinding("Leans on 'very'.", passage=match.group(0), guidance="Use one exact word instead.")]

def register(registrar):
    registrar.lint("p07/no-very", no_very, ops=("note",), severity=SEVERITY)
"""


def workspace(tmp_path, severity="return", fixture=FIXTURE, checks=None):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p07"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(fixture.replace("SEVERITY", repr(severity)))
    manifest = {
        "name": "p07",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Lints fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"lints": ["p07/no-very"]},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p07"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    if checks:
        current = yaml.safe_load((ws.config_dir / "checks.yaml").read_text())
        current["lints"].update(checks)
        (ws.config_dir / "checks.yaml").write_text(yaml.safe_dump(current))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture(autouse=True)
def no_responder():
    yield
    set_responder(None)


def answers(*texts):
    asked, queue = [], [json.dumps({"summary": "A note.", "ops": [{"op": "note", "text": t}]}) for t in texts]

    def responder(task):
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    set_responder(responder)
    return asked


def run(ws, cfg, store):
    handed = hand_in(ws, store, note="", pasted="Remember the launch party.", now=NOW)
    return process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)


def test_a_return_lint_sends_its_passage_and_guidance_back_for_a_fix(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    asked = answers("Plan a very nice launch party.", "Plan a lavish launch party.")
    cs_id = run(ws, cfg, store)
    assert len(asked) == 2
    assert 'the passage: "very nice"' in asked[1].request and "Use one exact word instead." in asked[1].request
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "applied"
    store.close()


def test_the_workspace_can_soften_a_lint_to_a_warning(tmp_path):
    ws, cfg, store = workspace(tmp_path, checks={"p07/no-very": "warn"})
    asked = answers("Plan a very nice launch party.")
    cs_id = run(ws, cfg, store)
    assert len(asked) == 1
    op = store.read().get("changeset", cs_id).data["ops"][0]
    assert op["status"] == "applied" and op["problems"][0]["passage"] == "very nice"
    store.close()


def test_a_lint_turned_off_finds_nothing(tmp_path):
    ws, cfg, store = workspace(tmp_path, checks={"p07/no-very": "off"})
    answers("Plan a very nice launch party.")
    cs_id = run(ws, cfg, store)
    assert store.read().get("changeset", cs_id).data["ops"][0]["problems"] == []
    store.close()


def test_a_lint_that_raises_turns_its_plugin_off_and_the_work_goes_on(tmp_path):
    broken = FIXTURE.replace("match = re.search", "raise RuntimeError('bug')\n    match = re.search")
    ws, cfg, store = workspace(tmp_path, fixture=broken)
    answers("Plan a very nice launch party.")
    cs_id = run(ws, cfg, store)
    assert store.read().get("changeset", cs_id).data["ops"][0]["status"] == "applied"
    assert not store.plugins.active("p07")
    store.close()


def test_a_lint_can_never_default_to_refusing(tmp_path):
    ws, cfg, store = workspace(tmp_path, severity="refuse")
    assert "default severity" in store.plugins.status["p07"].reason
    store.close()
