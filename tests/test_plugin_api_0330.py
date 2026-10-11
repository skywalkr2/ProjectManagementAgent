"""Plugin API 0.3.30: validators that read the plugin's settings, an origin that names the run's request and the part
it works on, and a limit of its own for the work an action queues."""

import sys
from types import SimpleNamespace

import pytest
import yaml

from engine.storage import StoreError
from tests.test_plugin_api_0329 import CREATING, reopen, with_manifest
from tests.test_today_panels_jobs import FIXTURE, workspace

SIZED = FIXTURE.replace(
    "class Config(Settings):\n    pass\n",
    "from pydantic import Field\n\n"
    "class Config(Settings):\n"
    "    longest: int = Field(5, description='The longest title.')\n",
).replace(
    "def register(registrar):\n",
    "SEEN = []\n\n"
    "def short(op, view, origin, settings):\n"
    "    SEEN.append(settings)\n"
    "    return ['Too long.'] if len(op.title) > settings.longest else []\n\n"
    "def plain(op, view):\n"
    "    return []\n\n"
    "def register(registrar):\n"
    '    registrar.op_validator("p18/add-goal", short)\n'
    '    registrar.op_validator("p18/add-goal", plain)\n',
)


def test_a_validator_with_a_settings_parameter_gets_the_plugins_settings(tmp_path):
    from engine.ops import CHANGESET

    ws, cfg, store = workspace(tmp_path, SIZED)
    store.close()
    with_manifest(ws, op_validators=["p18/add-goal"])
    cfg, store = reopen(ws, cfg)
    try:
        cs = CHANGESET.validate_python(
            {"summary": "x", "ops": [{"op": "p18/add-goal", "title": "Far too long"}]},
            context={"op_models": store.plugins.ops},
        )
        assert store.plugins.validators(cs.ops[0]) == ["Too long."]
        seen = next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "SEEN")).SEEN
        assert seen[-1].longest == 5
        assert store.plugins.active("p18")  # the two-argument validator still runs without settings
    finally:
        store.close()


def test_the_origin_names_the_request_and_its_part():
    from engine.applier import Inputs, origin_of

    request = SimpleNamespace(
        id="REQ-7",
        data={"task": "p18/plan", "about": {"kind": "p18/goal", "id": "GOL-1"}, "part": {"first": "p2", "last": "p4"}},
    )
    store = SimpleNamespace(read=lambda: SimpleNamespace(get=lambda kind, rid: request if rid == "REQ-7" else None))
    ctx = SimpleNamespace(
        store=store,
        inputs=Inputs("REQ-7", None, "", "", "untrusted"),
        actor="assistant",
        confirmed_by_pm=False,
        via=None,
    )
    origin = origin_of(ctx)
    assert origin["request"] == "REQ-7" and origin["part"] == {"first": "p2", "last": "p4"}
    assert origin["task"] == "p18/plan" and origin["actor"] == "assistant"
    alone = origin_of(SimpleNamespace(**{**vars(ctx), "inputs": Inputs("", None, "", "", "trusted"), "actor": "pm"}))
    assert alone["request"] is None and alone["part"] is None


def test_an_actions_queued_work_has_its_own_limit(tmp_path):
    from engine import actions

    ws, cfg, store = workspace(tmp_path, CREATING)
    store.close()
    with_manifest(ws, actions=["p18/close", "p18/make"])
    path = ws.config_dir / "workspace.yaml"
    data = yaml.safe_load(path.read_text())
    data.setdefault("plugins", {}).setdefault("actions", {}).update({"max_requests": 2, "max_items": 2000})
    path.write_text(yaml.safe_dump(data))
    cfg, store = reopen(ws, cfg)
    try:
        with pytest.raises(StoreError, match="more than 2 requests"):
            actions.preview(store, cfg, "p18/make")  # three requests, two items
    finally:
        store.close()
