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

from engine.config import load_config
from engine.selfcheck import FIXTURES
from engine.storage import Store
from engine.workspace import Workspace, init_workspace

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


@pytest.fixture
def workspace(tmp_path: Path, demo: Path) -> Workspace:
    return init_workspace(tmp_path / "ws", template=demo)


@pytest.fixture(autouse=True)
def _no_temp_folder_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests work in temporary folders on purpose; the command's "this folder is emptied" notice is tested directly."""
    monkeypatch.setattr("engine.cli.system_temp_roots", lambda: ())
