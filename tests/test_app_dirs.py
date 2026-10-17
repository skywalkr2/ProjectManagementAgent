from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from engine.app_dirs import app_dirs


@pytest.mark.parametrize("system", ["Darwin", "macOS", "DARWIN"])
def test_desktop_library_folders(system):
    result = app_dirs(system, {}, "/Users/rowan", "DeskHelper")
    assert result.data == PurePosixPath("/Users/rowan/Library/Application Support/DeskHelper")
    assert result.logs == PurePosixPath("/Users/rowan/Library/Logs/DeskHelper")
    assert result.cache == PurePosixPath("/Users/rowan/Library/Caches/DeskHelper")
    assert result.addons == result.data / "addons"


def test_windows_overrides_and_case_insensitive_keys():
    result = app_dirs(
        "Windows", {"appdata": r"D:\Roaming", "LocalAppData": r"E:\Local"}, r"C:\Users\Rowan", "DeskHelper"
    )
    assert result.data == PureWindowsPath(r"E:\Local\DeskHelper\data")
    assert result.logs == PureWindowsPath(r"E:\Local\DeskHelper\logs")
    assert result.cache == PureWindowsPath(r"E:\Local\DeskHelper\cache")
    assert result.addons == result.data / "addons"


@pytest.mark.parametrize("value", [None, "", "   ", "relative", r"C:relative", r"\rooted"])
def test_windows_fallbacks(value):
    env = {} if value is None else {"APPDATA": value, "LOCALAPPDATA": value}
    result = app_dirs("win32", env, r"C:\Users\Rowan", "DeskHelper")
    assert result.data == PureWindowsPath(r"C:\Users\Rowan\AppData\Local\DeskHelper\data")
    assert result.logs == PureWindowsPath(r"C:\Users\Rowan\AppData\Local\DeskHelper\logs")
    assert result.cache == PureWindowsPath(r"C:\Users\Rowan\AppData\Local\DeskHelper\cache")


def test_windows_data_never_follows_the_roaming_folder():
    result = app_dirs("Windows", {"APPDATA": r"\\host\share\profiles"}, r"C:\Users\Rowan", "DeskHelper")
    assert result.data == PureWindowsPath(r"C:\Users\Rowan\AppData\Local\DeskHelper\data")
    assert not result.data.is_relative_to(result.logs) and not result.logs.is_relative_to(result.data)


@pytest.mark.parametrize("value", [None, "", " \t", "relative", "~/data", "$HOME/data"])
def test_xdg_fallbacks(value):
    env = {} if value is None else dict.fromkeys(("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"), value)
    result = app_dirs("Linux", env, "/home/rowan", "desk-helper")
    assert result.data == PurePosixPath("/home/rowan/.local/share/desk-helper")
    assert result.logs == PurePosixPath("/home/rowan/.local/state/desk-helper/logs")
    assert result.cache == PurePosixPath("/home/rowan/.cache/desk-helper")


def test_xdg_overrides():
    result = app_dirs(
        "Linux",
        {"XDG_DATA_HOME": "/data", "XDG_STATE_HOME": "/state", "XDG_CACHE_HOME": "/cache"},
        "/home/rowan",
        "desk-helper",
    )
    assert result.data == PurePosixPath("/data/desk-helper")
    assert result.logs == PurePosixPath("/state/desk-helper/logs")
    assert result.cache == PurePosixPath("/cache/desk-helper")


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../escape",
        r"a\b",
        "a/b",
        "A:",
        "a\n",
        "name.",
        " name",
        "name ",
        "CON",
        "nul.txt",
        "COM1",
        "LPT9",
    ],
)
def test_invalid_names(name):
    with pytest.raises(ValueError):
        app_dirs("Linux", {}, "/home/rowan", name)


@pytest.mark.parametrize("system,home", [("Linux", "relative"), ("Windows", "/home/rowan"), ("Darwin", "~")])
def test_absolute_home_required(system, home):
    with pytest.raises(ValueError):
        app_dirs(system, {}, home, "DeskHelper")


def test_unknown_system():
    with pytest.raises(ValueError):
        app_dirs("Other", {}, "/home/rowan", "DeskHelper")


@pytest.mark.parametrize("key", ["XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"])
def test_install_environment_falls_back(key):
    result = app_dirs(
        "Linux", {key: "/opt/helper/content/../private"}, "/home/rowan", "desk-helper", install_dir="/opt/helper"
    )
    for path in (result.data, result.logs, result.addons, result.cache):
        assert not path.is_relative_to("/opt/helper")
    assert result.data == PurePosixPath("/home/rowan/.local/share/desk-helper")


def test_windows_install_comparison_is_case_insensitive():
    result = app_dirs(
        "Windows", {"LOCALAPPDATA": r"D:\APP\data"}, r"C:\Users\Rowan", "DeskHelper", install_dir=r"d:\app"
    )
    assert result.data == PureWindowsPath(r"C:\Users\Rowan\AppData\Local\DeskHelper\data")


def test_similar_prefix_is_not_inside():
    result = app_dirs(
        "Linux", {"XDG_DATA_HOME": "/opt/helper-data"}, "/home/rowan", "desk-helper", install_dir="/opt/helper"
    )
    assert result.data == PurePosixPath("/opt/helper-data/desk-helper")


def test_addons_are_checked_separately():
    with pytest.raises(ValueError):
        app_dirs("Linux", {}, "/home/rowan", "desk-helper", install_dir="/home/rowan/.local/share/desk-helper/addons")


@pytest.mark.parametrize(
    "system,home", [("Linux", "/home/rowan"), ("Darwin", "/Users/rowan"), ("Windows", r"C:\Users\Rowan")]
)
def test_unsafe_fallback_raises(system, home):
    with pytest.raises(ValueError):
        app_dirs(system, {}, home, "DeskHelper", install_dir=home)


def test_relative_installation_rejected():
    with pytest.raises(ValueError):
        app_dirs("Linux", {}, "/home/rowan", "desk-helper", install_dir="relative")


def test_inputs_unchanged_and_result_frozen():
    env = {"XDG_DATA_HOME": "/data"}
    result = app_dirs("Linux", env, "/home/rowan", "desk-helper")
    assert env == {"XDG_DATA_HOME": "/data"}
    with pytest.raises(FrozenInstanceError):
        result.data = PurePosixPath("/elsewhere")
