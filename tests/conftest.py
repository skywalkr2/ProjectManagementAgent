"""Shared fixtures. Tests read names and ids from the fictional workspaces instead of writing them out, so the
specificity scan holds for tests too."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from tests import speedups

# Faster parsing, plugin lookup, route validators and prepared workspaces; before the product's modules are imported.
speedups.install()

from engine.config import load_config  # noqa: E402
from engine.selfcheck import FIXTURES  # noqa: E402
from engine.storage import Store  # noqa: E402
from engine.workspace import Workspace, init_workspace  # noqa: E402

# Text a person reads that names a settings file, a key, a secret reference or a command fails the response while the
# whole suite runs (api/screen_text.py).
os.environ["COCKPIT_CHECK_WORDING"] = "1"

# Run the same core suite against copied fixtures without bundled contributions.
# Plugin contract tests are run separately with their plugins explicitly enabled.
_CORE_FIXTURES = None
if os.environ.get("COCKPIT_TEST_CORE_ONLY") == "1":
    _CORE_FIXTURES = tempfile.TemporaryDirectory(prefix="cockpit-core-fixtures-")
    copied = []
    for original in FIXTURES:
        target = Path(_CORE_FIXTURES.name) / original.name
        shutil.copytree(original, target)
        settings = target / "config" / "workspace.yaml"
        raw = yaml.safe_load(settings.read_text())
        raw["plugins"]["enabled"] = []
        settings.write_text(yaml.safe_dump(raw))
        stages_path = target / "config" / "stages.yaml"
        stages = yaml.safe_load(stages_path.read_text())
        stages["types"] = {kind: value for kind, value in stages["types"].items() if "/" not in kind}
        stages_path.write_text(yaml.safe_dump(stages))
        for child in (target / "data").iterdir():
            if child.is_dir():
                shutil.rmtree(child)
        copied.append(target)
    FIXTURES = tuple(copied)

DEMO_A, DEMO_B = FIXTURES


def fixture_records(ws_root: Path, kind: str) -> list[dict]:
    path = ws_root / "data" / f"{kind}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@pytest.fixture(params=FIXTURES, ids=lambda p: p.name)
def demo(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture
def store(tmp_path: Path, demo: Path) -> Store:
    s = Store(tmp_path / "test.db", cfg=load_config(demo / "config", env={}))
    yield s
    s.close()


def without_first_go(config_dir: Path) -> None:
    """Let AI runs start on their own in a workspace's copy of the fixture settings. The first runs wait for one go
    by default (`first_go`), which only the tests about that wait should see."""
    path = config_dir / "ai.yaml"
    path.write_text(path.read_text().replace("first_go: true", "first_go: false"))


@pytest.fixture
def workspace(tmp_path: Path, demo: Path) -> Workspace:
    ws = init_workspace(tmp_path / "ws", template=demo)
    without_first_go(ws.config_dir)
    return ws


@pytest.fixture(autouse=True)
def _no_temp_folder_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests work in temporary folders on purpose; the command's "this folder is emptied" notice is tested directly."""
    monkeypatch.setattr("engine.cli.system_temp_roots", lambda: ())


@pytest.fixture(autouse=True)
def _client_at_the_apps_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app answers only to its own address (design 12.1), so a test client built on an app starts at that address,
    read from the app's own settings, unless the test names another one. This is the one place the tests follow the
    rule; the product allows no test address."""
    from starlette.testclient import TestClient

    original = TestClient.__init__

    def at_the_apps_address(self, app, *args, **kwargs):
        worker = getattr(getattr(app, "state", None), "worker", None)
        if "base_url" not in kwargs and not args and worker is not None:
            server = worker.cfg.server
            # The address a person would open: the listen address, or the public one when hosted.
            kwargs["base_url"] = (server.mode == "hosted" and server.public_url) or f"http://127.0.0.1:{server.port}"
        original(self, app, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", at_the_apps_address)


def add_example_account(ai_yaml: Path | dict) -> tuple[str, str, str]:
    """Add the example AI account (tests/fixtures/ai/example-account.yaml: a key from an environment variable) to an
    ai.yaml, a file written back or its loaded dict. The fictional workspaces list only the stand-in account, so
    tests about keys and model names add this one. Returns (name, model, env var)."""
    import yaml

    example = yaml.safe_load((Path(__file__).parent / "fixtures" / "ai" / "example-account.yaml").read_text())
    data = yaml.safe_load(ai_yaml.read_text()) if isinstance(ai_yaml, Path) else ai_yaml
    data.setdefault("providers", {})[example["name"]] = example["provider"]
    if isinstance(ai_yaml, Path):
        ai_yaml.write_text(yaml.safe_dump(data, sort_keys=False))
    return example["name"], example["model"], example["env"]


def connection_answer(task) -> str:
    """What a working account answers the connection test with: the plain ok line for each kind of work, and one lesson
    to keep for the learning round-trip."""
    from engine.ai.learning_check import CHECK_REQUEST

    if task.request != CHECK_REQUEST:
        return '{"ok": true}'
    lesson = {"op": "lesson.add", "text": "Ask whoever owns the delivery.", "guard": "Name the delivery's owner."}
    return json.dumps({"summary": "A lesson.", "topic": "delivery dates", "ops": [lesson]})
