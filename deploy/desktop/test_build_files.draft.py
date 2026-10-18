import json
import re
import runpy
import sys
import types
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
import yaml
from build_support.build_model import bundled_data, release_versions


@pytest.mark.parametrize(
    "tag,display,numeric",
    [
        ("v1.2.3", "1.2.3", "1.2.3"),
        ("v0.1.0rc1", "0.1.0rc1", "0.1.0"),
        ("v1.2.3a2", "1.2.3a2", "1.2.3"),
        ("v1.2.3.post1", "1.2.3.post1", "1.2.3"),
    ],
)
def test_release_versions(tag, display, numeric):
    assert release_versions(tag) == (display, numeric)


@pytest.mark.parametrize(
    "tag", ["1.2.3", "v1.2", "v1.2.3.4", "v1.2.3+local", "v1!1.2.3", "v1.2.3\nX=bad", "v65536.0.0", "vnext", ""]
)
def test_invalid_tags(tag):
    with pytest.raises(ValueError):
        release_versions(tag)


@pytest.mark.parametrize("root", [PurePosixPath("/fictional/repo"), PureWindowsPath(r"C:\fictional\repo")])
def test_data_folder_layout(root):
    result = bundled_data(root)
    assert tuple(destination for _, destination in result) == (
        "web/dist",
        "engine/defaults",
        "engine/guide",
        "prompts",
        "plugins",
    )
    assert all(source == str(root / destination) for source, destination in result)


def test_launcher_calls_the_given_entry_point(monkeypatch):
    calls = []
    engine = types.ModuleType("engine")
    cli = types.ModuleType("engine.cli")
    cli.main = lambda: calls.append("main") or 37
    monkeypatch.setitem(sys.modules, "engine", engine)
    monkeypatch.setitem(sys.modules, "engine.cli", cli)
    monkeypatch.setattr("multiprocessing.freeze_support", lambda: calls.append("freeze_support"))
    path = Path(__file__).resolve().parents[1] / "build_support" / "launcher.py"
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(path), run_name="__main__")
    assert result.value.code == 37
    assert calls == ["freeze_support", "main"]


@pytest.mark.parametrize("filename,system", [("cockpit_macos.spec", "darwin"), ("cockpit_windows.spec", "win32")])
def test_specs_preserve_resources_and_disable_console(monkeypatch, filename, system):
    root = Path(__file__).resolve().parents[1]
    observed = {}
    data = list(bundled_data(root))
    common = types.ModuleType("freeze_common")

    def inputs(actual_root, actual_system):
        assert actual_root == root and actual_system == system
        return {
            "datas": data,
            "hiddenimports": ["engine.cli"],
            "architecture": "arm64",
            "version": "0.1.0",
            "numeric_version": "0.1.0",
        }

    common.freeze_inputs = inputs
    monkeypatch.setitem(sys.modules, "freeze_common", common)
    monkeypatch.setattr(sys, "path", list(sys.path))

    def analysis(*args, **kwargs):
        observed["analysis"] = kwargs
        return types.SimpleNamespace(pure=(), scripts=(), binaries=(), datas=data)

    def executable(*args, **kwargs):
        observed["exe"] = kwargs
        return object()

    def bundle(*args, **kwargs):
        observed["bundle"] = kwargs
        return object()

    runpy.run_path(
        str(root / "build_support" / filename),
        init_globals={
            "SPECPATH": str(root / "build_support"),
            "Analysis": analysis,
            "PYZ": lambda *args: object(),
            "EXE": executable,
            "COLLECT": lambda *args, **kwargs: object(),
            "BUNDLE": bundle,
        },
    )
    assert observed["analysis"]["datas"] == data
    assert observed["exe"]["console"] is False
    assert observed["exe"]["exclude_binaries"] is True
    assert observed["exe"]["upx"] is False
    if system == "darwin":
        assert observed["exe"]["target_arch"] == "arm64"
        assert observed["exe"]["codesign_identity"] is None
        assert observed["bundle"]["name"] == "Thimbleby.app"
    else:
        assert observed["exe"]["contents_directory"] == "_internal"


def test_workflow_native_matrix_and_immutable_actions():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github" / "workflows" / "desktop.yml").read_text())
    assert workflow["on"] == {"push": {"tags": ["v*"]}}
    assert workflow["permissions"] == {"contents": "read"}
    matrix = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]
    assert {(item["target"], item["runner"], item["python_arch"]) for item in matrix} == {
        ("macos-arm64", "macos-15", "arm64"),
        ("macos-x86_64", "macos-15-intel", "x64"),
        ("windows-x64", "windows-2022", "x64"),
    }
    for step in workflow["jobs"]["build"]["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w/-]+@[a-f0-9]{40}", step["uses"])


def test_installer_per_user_and_installs_the_whole_folder():
    root = Path(__file__).resolve().parents[1]
    text = (root / "build_support" / "windows.iss").read_text()
    assert "PrivilegesRequired=lowest" in text
    assert "DefaultDirName={localappdata}\\Programs\\Thimbleby" in text
    assert "PrivilegesRequiredOverridesAllowed" not in text
    assert "recursesubdirs createallsubdirs" in text
    assert "[UninstallDelete]" not in text


def test_compiler_download_has_an_exact_version_and_hash():
    root = Path(__file__).resolve().parents[1]
    tool = json.loads((root / "build_support" / "tool_downloads.yaml").read_text())["inno_setup"]
    assert tool["version"] == "6.4.3"
    assert tool["url"].endswith("/innosetup-6.4.3.exe")
    assert re.fullmatch(r"[a-f0-9]{64}", tool["sha256"])
