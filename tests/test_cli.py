import subprocess

from engine.cli import main
from engine.storage import Store
from engine.storage.lease import Lease
from tests.conftest import fixture_records


def test_init_from_a_fixture_loads_records_and_commits(tmp_path, demo, capsys):
    target = tmp_path / "ws"
    assert main(["init", str(target), "--from", str(demo)]) == 0
    store = Store(target / "cockpit.db")
    assert len(store.read().list("person")) == len(fixture_records(demo, "person"))
    store.close()
    assert (target / "data" / "ledger.jsonl").exists()
    log = subprocess.run(["git", "-C", str(target), "log", "--oneline"], capture_output=True, text=True)
    assert "Create workspace" in log.stdout
    ignored = (target / ".gitignore").read_text()
    assert "cockpit.db" in ignored and ".cockpit/" in ignored


def test_init_without_a_template_writes_commented_defaults(tmp_path):
    target = tmp_path / "fresh"
    assert main(["init", str(target), "--no-git"]) == 0
    text = (target / "config" / "server.yaml").read_text()
    assert "# " in text and "port: 8765" in text


def test_init_refuses_a_folder_with_files(tmp_path, capsys):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "file.txt").write_text("hi")
    assert main(["init", str(tmp_path / "x")]) == 1
    assert "isn't empty" in capsys.readouterr().err


def test_config_show_explains_each_value(tmp_path, demo, capsys, monkeypatch):
    target = tmp_path / "ws"
    main(["init", str(target), "--from", str(demo), "--no-git"])
    capsys.readouterr()
    monkeypatch.setenv("COCKPIT__SERVER__PORT", "9999")
    assert main(["config", "show", "--workspace", str(target)]) == 0
    out = capsys.readouterr().out
    assert "server.port" in out and "9999" in out and "(env)" in out and "(file)" in out


def test_missing_workspace_has_a_clear_message(capsys, monkeypatch):
    monkeypatch.delenv("COCKPIT_WORKSPACE", raising=False)
    assert main(["export"]) == 1
    assert "No workspace given" in capsys.readouterr().err


def test_takeover_frees_a_workspace_left_open(tmp_path, demo, capsys):
    target = tmp_path / "ws"
    main(["init", str(target), "--from", str(demo), "--no-git"])
    store = Store(target / "cockpit.db")
    Lease(store, holder="crashed").acquire()
    store.close()
    assert main(["takeover", "--workspace", str(target)]) == 1
    assert "still looks alive" in capsys.readouterr().err
    assert main(["takeover", "--workspace", str(target), "--force"]) == 0
