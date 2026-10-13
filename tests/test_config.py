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
    env = {"COCKPIT__WORKSPACE__OUR_ACCOUNTS": "[me, boss]", "COCKPIT__STORAGE__EXPORT__COMMIT": "false"}
    cfg = load_config(None, env=env)
    assert cfg.workspace.our_accounts == ["me", "boss"]
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


def test_the_pms_name_moves_from_the_settings_to_their_person_record(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine.storage import Store
    from engine.workspace import init_workspace
    from tests.conftest import DEMO_B

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "workspace.yaml"
    pid = load_config(ws.config_dir, env={}).workspace.user.person
    text = path.read_text().replace("  person: ", "  full_name: Renamed Person\n  aliases: [Ren, me]\n  person: ", 1)
    path.write_text(text)
    cfg = load_config(ws.config_dir, env={})
    assert cfg.moved == {"workspace.user.full_name": "Renamed Person", "workspace.user.aliases": ["Ren", "me"]}
    TestClient(create_app(ws, cfg, "t", start_worker=False))
    after = path.read_text()
    assert "  full_name:" not in after and "  aliases:" not in after and f"person: {pid}" in after
    store = Store(ws.db_path)
    try:
        me = store.read().get("person", pid)
        assert me.data["full_name"] == "Renamed Person" and "Ren" in me.data["aliases"]
        assert "me" not in me.data["aliases"]  # "me" always means the PM; it isn't stored
    finally:
        store.close()
    assert load_config(ws.config_dir, env={}).moved == {}


def test_yaml_is_read_by_the_compiled_parser_with_the_same_data(monkeypatch):
    import engine.yaml_load as reading

    text = "a: 1\nb: [x, y]\nc:\n  - d: 2026-01-02\n    e: 'q'\n"
    assert reading.COMPILED_SAFE_LOADER is not None  # the test environment installs the compiled parser
    expected = yaml.safe_load(text)
    calls = []
    real = yaml.load
    monkeypatch.setattr(yaml, "load", lambda stream, Loader: calls.append(Loader) or real(stream, Loader=Loader))
    assert reading.load_yaml(text) == expected
    assert calls == [reading.COMPILED_SAFE_LOADER]


def test_a_mistyped_settings_file_still_names_the_line_and_quotes_it(tmp_path):
    write(tmp_path, "server", "port: 9000\nhost: [a, b\nbase_path: /\n")
    with pytest.raises(ConfigError) as err:
        load_config(tmp_path, env={})
    assert "server.yaml: not valid YAML" in str(err.value) and "line 2" in str(err.value)
    assert "host: [a, b" in str(err.value)  # the pure-Python parser's longer message, used for the error
