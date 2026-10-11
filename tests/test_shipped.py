"""Shipped files: found in the installed package when it carries them, else in the checkout; the demo command makes a
demo workspace once and serves it; the wheel's build hook ships every file but a workspace's runtime files."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

import engine.cli
from engine.cli import main
from engine.shipped import CHECKOUT, demo, shipped


def test_a_packaged_copy_wins_over_the_checkout(tmp_path):
    assert shipped("templates", packaged=tmp_path) == CHECKOUT / "templates"
    assert shipped("web", packaged=tmp_path) == CHECKOUT / "web" / "dist"
    (tmp_path / "templates").mkdir()
    assert shipped("templates", packaged=tmp_path) == tmp_path / "templates"
    assert demo("demo-a", packaged=tmp_path) == CHECKOUT / "workspaces" / "demo-a"
    with pytest.raises(KeyError):
        demo("someone-elses")


def test_the_demo_command_makes_the_demo_once_then_serves_it(tmp_path, monkeypatch, capsys):
    served = []
    monkeypatch.setattr(engine.cli, "cmd_serve", lambda args: served.append(args) or 0)
    folder = tmp_path / "try"
    assert main(["demo", str(folder), "--which", "demo-a"]) == 0
    assert "Everything in it is made up" in capsys.readouterr().out
    assert served[-1].workspace == str(folder) and served[-1].open_browser is True
    (folder / "marker").write_text("kept")
    assert main(["demo", str(folder), "--no-open"]) == 0
    assert (folder / "marker").exists() and served[-1].open_browser is False
    assert main(["demo", str(folder), "--fresh"]) == 0
    assert not (folder / "marker").exists()


def test_the_demo_command_leaves_a_real_workspace_alone(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(engine.cli, "cmd_serve", lambda args: 0)
    real = tmp_path / "real"
    assert main(["init", str(real), "--no-git"]) == 0
    assert main(["demo", str(real), "--fresh"]) == 1
    assert "isn't a demo" in capsys.readouterr().err and (real / "config").is_dir()


def test_the_build_hook_skips_runtime_files(tmp_path, monkeypatch):
    stand_in = types.ModuleType("interface")
    stand_in.BuildHookInterface = object  # the build tool isn't installed with the app; only the file walk is tested
    monkeypatch.setitem(sys.modules, "hatchling.builders.hooks.plugin.interface", stand_in)
    spec = importlib.util.spec_from_file_location("hatch_build_under_test", CHECKOUT / "hatch_build.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "workspace.yaml").write_text("demo: true\n")
    for name in ("cockpit.db", "cockpit.db-wal", ".cockpit/lease.json", "data/__pycache__/x.pyc"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")
    assert [rel for _, rel in hook._files(tmp_path)] == [Path("config/workspace.yaml")]
