from pathlib import Path

import pytest
import yaml

from engine.config import FILES, ConfigError, load_config, render_default_file


def write(dir_: Path, name: str, text: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_defaults_without_any_files():
    cfg = load_config(None, env={})
    assert cfg.server.port == 8765
    assert cfg.server.base_path == "/"
    assert all(layer == "default" for _, _, layer in cfg.flat())


def test_layers_in_order_file_env_flag(tmp_path):
    write(tmp_path, "server", "port: 9000\nhost: 0.0.0.0\n")
    cfg = load_config(tmp_path, env={"COCKPIT__SERVER__PORT": "9100"}, flags={"server.host": "127.0.0.1"})
    assert cfg.server.port == 9100
    assert cfg.server.host == "127.0.0.1"
    sources = {path: layer for path, _, layer in cfg.flat()}
    assert sources["server.port"] == "env"
    assert sources["server.host"] == "flag"
    assert sources["server.base_path"] == "default"


def test_env_reaches_nested_keys_and_parses_values():
    env = {"COCKPIT__WORKSPACE__USER__ALIASES": "[me, boss]", "COCKPIT__STORAGE__EXPORT__COMMIT": "false"}
    cfg = load_config(None, env=env)
    assert cfg.workspace.user.aliases == ["me", "boss"]
    assert cfg.storage.export.commit is False


def test_unrelated_environment_is_ignored():
    cfg = load_config(None, env={"COCKPIT__NOT_A_FILE__X": "1", "OTHER": "2"})
    assert cfg.server.port == 8765


def test_unknown_key_is_an_error_naming_it(tmp_path):
    write(tmp_path, "server", "prot: 9000\n")
    with pytest.raises(ConfigError, match="server.prot"):
        load_config(tmp_path, env={})


def test_newer_file_version_is_refused(tmp_path):
    write(tmp_path, "storage", "version: 99\n")
    with pytest.raises(ConfigError, match="newer than this program"):
        load_config(tmp_path, env={})


@pytest.mark.parametrize("bad", ["admin", "/admin/"])
def test_base_path_shape(tmp_path, bad):
    write(tmp_path, "server", f"base_path: {bad}\n")
    with pytest.raises(ConfigError, match="base_path"):
        load_config(tmp_path, env={})


@pytest.mark.parametrize("name", list(FILES))
def test_default_files_are_valid_yaml_and_load_as_defaults(tmp_path, name):
    text = render_default_file(name)
    assert yaml.safe_load(text) is not None
    write(tmp_path, name, text)
    cfg = load_config(tmp_path, env={})
    assert getattr(cfg, name) == FILES[name]()
    assert text.count("#") >= len(FILES[name].model_fields)


def test_fixture_workspaces_load(demo):
    cfg = load_config(demo / "config", env={})
    assert cfg.workspace.name
