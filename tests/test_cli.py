import os
import subprocess
from pathlib import Path

import pytest
import yaml

from engine.cli import main
from engine.storage import Store
from engine.storage.lease import Lease
from tests.conftest import DEMO_B, fixture_records


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


def test_evaluate_with_the_stub_checks_the_cases(capsys):
    from tests.conftest import DEMO_B

    assert main(["evaluate", "--from", str(DEMO_B), "--stub", "--runs", "1", "--case", "close-action"]) == 0
    out = capsys.readouterr().out
    assert "close-action" in out and "Overall pass rate: 100%" in out


def test_evaluate_with_a_missing_key_fails_and_says_so(tmp_path, capsys):
    import yaml

    from tests.conftest import DEMO_B, add_example_account

    ai = yaml.safe_load((DEMO_B / "config" / "ai.yaml").read_text())
    real, model, _ = add_example_account(ai)
    ai["providers"][real]["auth"] = "env:COCKPIT_TEST_KEY_THAT_IS_NOT_SET"
    path = tmp_path / "ai.yaml"
    path.write_text(yaml.safe_dump(ai))
    args = ["evaluate", "--from", str(DEMO_B), "--account", f"{real}/{model}", "--ai-config", str(path), "--runs", "1"]
    assert main([*args, "--case", "close-action", "--json"]) == 1
    assert "wasn't found" in capsys.readouterr().out


def test_backup_needs_a_target_then_copies(tmp_path, demo, capsys, monkeypatch):
    ws = tmp_path / "ws"
    main(["init", str(ws), "--from", str(demo), "--no-git"])
    monkeypatch.setenv("COCKPIT__STORAGE__BACKUPS__TARGETS", "[]")
    assert main(["backup", "-w", str(ws)]) == 1
    monkeypatch.setenv("COCKPIT__STORAGE__BACKUPS__TARGETS", f'[{{"path": "{tmp_path / "offsite"}"}}]')
    assert main(["backup", "-w", str(ws)]) == 1  # the folder isn't there: never created on this computer's disk
    (tmp_path / "offsite").mkdir()
    assert main(["backup", "-w", str(ws)]) == 0
    assert len(list((tmp_path / "offsite").iterdir())) == 1
    assert "Backed up" in capsys.readouterr().out


def test_a_fresh_workspace_knows_who_you_are(tmp_path):
    target = tmp_path / "mine"
    assert (
        main(["init", str(target), "--no-git", "--you", "Pat Example", "--name", "My Press", "--assistant", "Ada"]) == 0
    )
    from engine.workspace import Workspace

    ws = Workspace(target)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    me = store.read().get("person", cfg.workspace.user.person)
    store.close()
    assert me.data["full_name"] == "Pat Example"  # the one place the name is kept
    assert "  full_name:" not in (target / "config" / "workspace.yaml").read_text()
    assert cfg.workspace.name == "My Press" and cfg.workspace.assistant_name == "Ada"
    assert "# " in (target / "config" / "workspace.yaml").read_text()


def test_a_workspace_in_a_temporary_folder_gets_a_notice(tmp_path):
    from engine.cli import TEMP_FOLDER, temp_folder_notice

    roots = [tmp_path / "scratch"]
    assert temp_folder_notice(roots[0] / "ws", roots) == TEMP_FOLDER
    assert temp_folder_notice(roots[0], roots) == TEMP_FOLDER
    assert temp_folder_notice(tmp_path / "home" / "ws", roots) is None
    assert temp_folder_notice(tmp_path / "scratchy", roots) is None
    assert temp_folder_notice(tmp_path / "x", []) is None


def test_the_real_temporary_folders_are_recognised(tmp_path, monkeypatch):
    from engine import cli

    monkeypatch.undo()  # the suite blanks the system folders; here they are the point
    assert cli.temp_folder_notice(tmp_path / "ws") == cli.TEMP_FOLDER  # pytest's folders are inside the system's
    assert cli.temp_folder_notice(tmp_path / "ws", cli.system_temp_roots()) == cli.TEMP_FOLDER
    assert cli.temp_folder_notice(Path(tmp_path.anchor) / "no-such-home-xyz" / "ws") is None


def test_init_says_when_the_folder_will_be_emptied(tmp_path, capsys, monkeypatch):
    from engine import cli

    monkeypatch.setattr(cli, "system_temp_roots", lambda: (tmp_path,))
    assert main(["init", str(tmp_path / "ws"), "--no-git"]) == 0
    assert cli.TEMP_FOLDER in capsys.readouterr().err


def test_the_web_screens_notice_compares_the_build_with_the_sources(tmp_path):
    import os

    from engine.cli import STALE_BUILD, web_build_notice

    assert web_build_notice(tmp_path) is None  # no web sources here: nothing to compare
    src = tmp_path / "web" / "src"
    src.mkdir(parents=True)
    page = src / "App.tsx"
    page.write_text("x")
    assert web_build_notice(tmp_path) == STALE_BUILD  # never built
    built = tmp_path / "web" / "dist" / "index.html"
    built.parent.mkdir(parents=True)
    built.write_text("x")
    os.utime(page, (1_000, 1_000))
    os.utime(built, (2_000, 2_000))
    assert web_build_notice(tmp_path) is None
    nested = src / "components"
    nested.mkdir()
    (nested / "New.tsx").write_text("x")
    os.utime(nested / "New.tsx", (3_000, 3_000))
    assert web_build_notice(tmp_path) == STALE_BUILD


def test_the_repository_root_comes_from_the_package_not_the_current_folder(tmp_path, monkeypatch):
    from engine.cli import repo_root

    monkeypatch.chdir(tmp_path)
    assert (repo_root() / "engine" / "cli.py").is_file()


def test_ai_test_says_where_a_failing_key_was_read_from_and_never_shows_it(tmp_path, demo, capsys, monkeypatch):
    import yaml

    target = tmp_path / "ws"
    main(["init", str(target), "--from", str(demo), "--no-git"])
    from tests.conftest import add_example_account

    path = target / "config" / "ai.yaml"
    ai = yaml.safe_load(path.read_text())
    real, model, name = add_example_account(ai)
    ai["tiers"]["deep"]["use"] = f"{real}/{model}"
    path.write_text(yaml.safe_dump(ai))
    monkeypatch.delenv(name, raising=False)
    assert main(["ai", "test", "-w", str(target)]) == 1
    assert f"key from the secret named {name}" in capsys.readouterr().out
    key_file = tmp_path / "key.txt"
    key_file.write_text("a-secret-value")
    ai["providers"][real]["auth"] = f"file:{tmp_path / 'missing.txt'}"
    path.write_text(yaml.safe_dump(ai))
    assert main(["ai", "test", "-w", str(target)]) == 1
    out = capsys.readouterr().out
    assert f"key from the file {tmp_path / 'missing.txt'}" in out and "a-secret-value" not in out


def test_evaluate_runs_a_workspaces_own_cases_with_its_own_ai_setup(tmp_path, capsys):
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    assert (ws.root / "evals").is_dir()
    assert main(["evaluate", "-w", str(ws.root), "--stub", "--runs", "1", "--case", "close-action"]) == 0
    out = capsys.readouterr().out
    assert "close-action" in out and "Overall pass rate: 100%" in out


def test_evaluate_without_cases_says_where_to_find_some(tmp_path, capsys):
    (tmp_path / "ws" / "config").mkdir(parents=True)
    assert main(["evaluate", "-w", str(tmp_path / "ws")]) == 1
    assert "--from" in capsys.readouterr().err


def test_a_new_workspace_gets_no_note_about_an_untested_ai_account(tmp_path):
    from engine.cli import untested_ai_note
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "fresh", git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        assert untested_ai_note(ws, cfg, store) is None
    finally:
        store.close()


def test_a_workspace_with_an_untested_ai_account_gets_the_note(tmp_path):
    from engine.cli import untested_ai_note
    from engine.storage import Store
    from engine.workspace import init_workspace
    from tests.conftest import add_example_account

    ws = init_workspace(tmp_path / "with-account", git=False)
    provider, model, _ = add_example_account(ws.config_dir / "ai.yaml")
    ai = yaml.safe_load((ws.config_dir / "ai.yaml").read_text())
    ai.setdefault("tiers", {})["routine"] = {"use": f"{provider}/{model}"}
    (ws.config_dir / "ai.yaml").write_text(yaml.safe_dump(ai))
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        note = untested_ai_note(ws, cfg, store)
    finally:
        store.close()
    assert note is not None and "hasn't passed its test" in note


def _start_without_serving(monkeypatch, tmp_path):
    """`cockpit` with the server replaced by a recorder, and the home folder a temporary one."""
    import engine.cli as cli

    served = []

    def serve(args):
        served.append(Path(args.workspace))
        cli.remember_workspace(Path(args.workspace).resolve())
        return 0

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.delenv("COCKPIT_WORKSPACE", raising=False)
    monkeypatch.setattr(cli, "cmd_serve", serve)
    return served


def test_cockpit_on_its_own_makes_a_workspace_in_the_home_folder_the_first_time(tmp_path, monkeypatch, capsys):
    served = _start_without_serving(monkeypatch, tmp_path)
    assert main([]) == 0
    home = tmp_path / "home"
    assert (home / "Cockpit" / "config").is_dir()
    assert served == [home / "Cockpit"]
    assert "Made your workspace in" in capsys.readouterr().out


def test_cockpit_on_its_own_reopens_the_workspace_started_last(tmp_path, monkeypatch):
    from engine.workspace import init_workspace

    served = _start_without_serving(monkeypatch, tmp_path)
    other = init_workspace(tmp_path / "elsewhere", git=False).root
    import engine.cli as cli

    cli.remember_workspace(other)
    assert main([]) == 0
    assert served == [other]
    assert not (tmp_path / "home" / "Cockpit").exists()


def test_cockpit_on_its_own_never_makes_a_workspace_in_a_folder_with_other_files(tmp_path, monkeypatch, capsys):
    served = _start_without_serving(monkeypatch, tmp_path)
    folder = tmp_path / "home" / "Cockpit"
    folder.mkdir()
    (folder / "notes.txt").write_text("mine")
    assert main([]) == 1
    assert served == []
    assert "already holds other files" in capsys.readouterr().err


def _checkout_with_script(tmp_path):
    """A stand-in source checkout with the command its environment installs."""
    root = tmp_path / "checkout"
    (root / ".git").mkdir(parents=True)
    script = root / ".venv" / "bin" / "cockpit"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\n")
    return root, script


@pytest.mark.skipif(os.name == "nt", reason="the command link is for macOS and Linux")
def test_running_from_a_checkout_makes_cockpit_work_in_any_folder(tmp_path):
    """The person's path: they run `uv run cockpit` in the source folder once; afterwards `cockpit` works anywhere,
    pointing at that checkout, and they are told so once."""
    from engine.cli import link_command

    root, script = _checkout_with_script(tmp_path)
    bin_dir = tmp_path / "bin"
    said: list[str] = []
    env = {"HOME": str(tmp_path), "XDG_BIN_HOME": str(bin_dir), "PATH": str(bin_dir)}
    link_command(root, script, env, said.append)
    link = bin_dir / "cockpit"
    assert link.is_symlink() and link.resolve() == script.resolve()
    assert len(said) == 1 and "any folder" in said[0]
    link_command(root, script, env, said.append)
    assert len(said) == 1  # already in place: nothing more is said


@pytest.mark.skipif(os.name == "nt", reason="the command link is for macOS and Linux")
def test_the_command_link_never_replaces_an_installed_cockpit_and_says_when_a_new_terminal_is_needed(tmp_path):
    from engine.cli import link_command

    root, script = _checkout_with_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    installed = bin_dir / "cockpit"
    installed.write_text("#!/bin/sh\n# an installed copy\n")
    said: list[str] = []
    link_command(root, script, {"HOME": str(tmp_path), "XDG_BIN_HOME": str(bin_dir), "PATH": ""}, said.append)
    assert not installed.is_symlink() and "installed copy" in installed.read_text() and said == []

    other = tmp_path / "bin2"
    said.clear()
    link_command(root, script, {"HOME": str(tmp_path), "XDG_BIN_HOME": str(other), "PATH": "/usr/bin"}, said.append)
    assert (other / "cockpit").is_symlink() and "new terminal" in said[0]


@pytest.mark.skipif(os.name == "nt", reason="the command link is for macOS and Linux")
def test_a_link_left_by_a_removed_checkout_is_replaced(tmp_path):
    from engine.cli import link_command

    root, script = _checkout_with_script(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "cockpit").symlink_to(tmp_path / "gone" / ".venv" / "bin" / "cockpit")
    link_command(root, script, {"HOME": str(tmp_path), "XDG_BIN_HOME": str(bin_dir), "PATH": str(bin_dir)}, print)
    assert (bin_dir / "cockpit").resolve() == script.resolve()


def test_no_link_is_made_outside_a_checkout(tmp_path):
    from engine.cli import link_command

    root, script = _checkout_with_script(tmp_path)
    (root / ".git").rmdir()
    bin_dir = tmp_path / "bin"
    link_command(root, script, {"HOME": str(tmp_path), "XDG_BIN_HOME": str(bin_dir), "PATH": ""}, print)
    assert not (bin_dir / "cockpit").exists()
