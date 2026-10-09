"""Shared fixtures. Tests read names and ids from the fictional workspaces instead of writing them out, so the
specificity scan holds for tests too."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.selfcheck import FIXTURES
from engine.storage import Store
from engine.workspace import Workspace, init_workspace

DEMO_A, DEMO_B = FIXTURES


def fixture_records(ws_root: Path, kind: str) -> list[dict]:
    path = ws_root / "data" / f"{kind}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@pytest.fixture(params=FIXTURES, ids=lambda p: p.name)
def demo(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def workspace(tmp_path: Path, demo: Path) -> Workspace:
    return init_workspace(tmp_path / "ws", template=demo)
