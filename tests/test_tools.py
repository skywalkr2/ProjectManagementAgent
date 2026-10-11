"""Outside programs a plugin declares (design 3.2, 3.5): found per computer, probed, run without a shell in a fresh
folder with a timeout and a minimal environment, files collected within caps, and every run recorded."""

import sys
from pathlib import Path

import pytest
import yaml

from engine.config import load_config
from engine.tools import ToolError, ToolLimits, Tools, read_locations
from tests.conftest import DEMO_B

PROGRAM = r"""
import os, sys, time, pathlib
args = sys.argv[1:]
if args == ["--version"]:
    print("fakeprog version 2.4.1"); sys.exit(0)
if args and args[0] == "sleep":
    time.sleep(float(args[1])); sys.exit(0)
if args and args[0] == "shout":
    print("x" * int(args[1])); sys.exit(0)
if args and args[0] == "env":
    print("\n".join(sorted(os.environ))); sys.exit(0)
if args and args[0] == "build":
    source = pathlib.Path(args[1]).read_text()
    pathlib.Path("out").mkdir()
    pathlib.Path("out/book.txt").write_text(source.upper())
    pathlib.Path("out/big.bin").write_bytes(b"0" * 3000)
    pathlib.Path("report.log").write_text("ok")
    os.symlink("/etc/hostname", "out/link.txt")
    print(os.getcwd())
    print("warning: something", file=sys.stderr)
    sys.exit(3)
"""


@pytest.fixture
def program(tmp_path):
    script = tmp_path / "fakeprog.py"
    script.write_text(PROGRAM)
    return {"fakeprog": {"command": [sys.executable, str(script)]}}


def tools(locations, **limits):
    return Tools(locations, ToolLimits(**limits))


def test_a_tool_is_probed_for_its_version(program):
    runner = tools(program)
    assert runner.probe("fakeprog", "fakeprog --version", "2.0").version == "2.4.1"
    old = runner.probe("fakeprog", "fakeprog --version", "3.1")
    assert not old.found and "older than 3.1" in old.reason
    missing = tools({}, probe_timeout_seconds=5).probe("not-a-real-program-here", "not-a-real-program-here -v", "")
    assert not missing.found and "isn't installed" in missing.reason


def test_a_run_gets_its_files_returns_what_it_wrote_and_leaves_nothing_behind(program):
    result = tools(program, collect_file_mb=0.002).run(
        "fakeprog", ["build", "in/chapter.txt"], {"in/chapter.txt": b"plain words"}, collect=["out/*", "*.log"]
    )
    assert result.returncode == 3 and "warning: something" in result.stderr and not result.timed_out
    assert result.files == {"out/book.txt": b"PLAIN WORDS", "report.log": b"ok"}
    reasons = {o["name"]: o["reason"] for o in result.omitted}
    assert "larger than" in reasons["out/big.bin"] and "not a regular file" in reasons["out/link.txt"]
    assert not Path(result.stdout.strip()).exists()


def test_the_total_cap_omits_files_rather_than_cutting_them(program):
    result = tools(program, collect_total_mb=0.002).run("fakeprog", ["build", "a"], {"a": b"x"}, collect=["out/*"])
    assert set(result.files) == {"out/book.txt"}
    assert any(o["name"] == "out/big.bin" and "total" in o["reason"] for o in result.omitted)


def test_a_call_may_lower_caps_but_never_raise_them(program):
    runner = tools(program, collect_file_mb=0.002)
    raised = runner.run("fakeprog", ["build", "a"], {"a": b"x"}, collect=["out/*"], max_file_mb=50)
    assert "out/big.bin" not in raised.files
    lowered = tools(program).run("fakeprog", ["build", "a"], {"a": b"x"}, collect=["out/*"], max_file_mb=0.001)
    assert set(lowered.files) == {"out/book.txt"}


@pytest.mark.parametrize("bad", ["../escape.txt", "/etc/passwd", "a/../../b"])
def test_names_and_patterns_stay_inside_the_folder(program, bad):
    runner = tools(program)
    with pytest.raises(ToolError, match="inside the working folder"):
        runner.run("fakeprog", ["env"], {bad: b"x"})
    with pytest.raises(ToolError, match="inside the working folder"):
        runner.run("fakeprog", ["env"], collect=[bad])


def test_a_run_that_overruns_is_stopped(program):
    result = tools(program).run("fakeprog", ["sleep", "30"], timeout=0.5)
    assert result.timed_out and result.returncode == -1 and result.seconds < 10


def test_the_timeout_may_be_given_in_place(program):
    assert tools(program).run("fakeprog", ["sleep", "30"], {}, 0.5).timed_out


def test_a_timeout_above_the_maximum_is_held_to_it(program):
    result = tools(program, max_timeout_seconds=0.5).run("fakeprog", ["sleep", "30"], timeout=600)
    assert result.timed_out


def test_long_output_is_cut_and_says_so(program):
    result = tools(program, output_kb=1).run("fakeprog", ["shout", "5000"])
    assert result.output_cut and len(result.stdout) == 1024


def test_the_environment_is_minimal(program, monkeypatch):
    monkeypatch.setenv("COCKPIT_TEST_SECRET", "do-not-pass")
    program["fakeprog"]["env"] = {"FAKEPROG_MODE": "test"}
    names = tools(program).run("fakeprog", ["env"]).stdout.split()
    assert "COCKPIT_TEST_SECRET" not in names and "FAKEPROG_MODE" in names and "HOME" in names


def test_locations_are_read_per_computer(tmp_path):
    path = tmp_path / "tools.yaml"
    path.write_text(yaml.safe_dump({"one": "/opt/one", "two": {"command": ["java", "-jar", "two.jar"]}}))
    assert read_locations(path) == {
        "one": {"command": ["/opt/one"], "env": {}},
        "two": {"command": ["java", "-jar", "two.jar"], "env": {}},
    }
    assert read_locations(tmp_path / "missing.yaml") == {}
    path.write_text(yaml.safe_dump({"bad": {"env": {}}}))
    with pytest.raises(ToolError, match="needs a path or a command"):
        read_locations(path)


FIXTURE = """
from engine.plugin_api import Settings

class Config(Settings):
    pass

def register(registrar):
    pass
"""


def workspace_with(tmp_path, program, tools_declared):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p03"
    plugin.mkdir(parents=True)
    manifest = {
        "name": "p03",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Tool fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "requires": {"tools": tools_declared},
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (plugin / "fixture.py").write_text(FIXTURE)
    enabled = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    enabled["plugins"]["enabled"] = [*enabled["plugins"]["enabled"], "p03"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(enabled))
    (ws.root / ".cockpit").mkdir(exist_ok=True)
    (ws.root / ".cockpit" / "tools.yaml").write_text(yaml.safe_dump(program))
    return ws


def open_store(ws):
    from engine.storage import Store

    return Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))


def declared(name="fakeprog", **extra):
    return {"name": name, "min_version": "2.0", "probe": f"{name} --version", **extra}


def test_a_missing_required_tool_keeps_the_plugin_off(tmp_path, program):
    ws = workspace_with(tmp_path, program, [declared("absent-program")])
    store = open_store(ws)
    assert not store.plugins.active("p03")
    assert "needs absent-program" in store.plugins.status["p03"].reason
    store.close()


def test_a_missing_optional_tool_only_turns_off_its_features(tmp_path, program):
    ws = workspace_with(tmp_path, program, [declared(), declared("absent-program", optional=True)])
    store = open_store(ws)
    assert store.plugins.active("p03")
    status = store.plugins.status["p03"].tools
    assert status["fakeprog"] == "found 2.4.1" and "isn't installed" in status["absent-program"]
    box = store.plugins.tool_box("p03")
    assert box.available("fakeprog") and not box.available("absent-program")
    store.close()


def test_a_plugin_runs_only_declared_tools_and_each_run_is_recorded(tmp_path, program):
    ws = workspace_with(tmp_path, program, [declared()])
    store = open_store(ws)
    box = store.plugins.tool_box("p03")
    with pytest.raises(ToolError, match="isn't declared"):
        box.run("python", ["-c", "print(1)"])
    result = box.run("fakeprog", ["build", "chapter.txt"], {"chapter.txt": b"words"}, collect=["out/book.txt"])
    assert result.files == {"out/book.txt": b"WORDS"}
    run = store.read().list("tool_run")[-1].data
    assert run["plugin"] == "p03" and run["tool"] == "fakeprog" and run["returncode"] == 3
    assert run["version"] == "2.4.1"
    assert run["inputs"] == ["chapter.txt"] and run["collected"] == [{"name": "out/book.txt", "size": 5}]
    assert "warning: something" in run["stderr_tail"]
    store.close()


def test_a_probe_must_start_with_the_tools_name(tmp_path, program):
    ws = workspace_with(tmp_path, program, [{**declared(), "probe": "sh -c 'fakeprog --version'"}])
    store = open_store(ws)
    assert "must start with the tool's name" in store.plugins.status["p03"].reason
    store.close()


def test_drive_letter_paths_are_refused(program):
    with pytest.raises(ToolError):
        tools(program).run("fakeprog", ["env"], {"C:/x.txt": b"x"})


def test_the_program_is_not_given_a_shell(program, tmp_path):
    marker = tmp_path / "marker"
    result = tools(program).run("fakeprog", ["shout", f"1; touch {marker}"])
    assert not marker.exists() and result.returncode != 0
