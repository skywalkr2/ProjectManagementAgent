"""Updating a source checkout, restoring a whole backup into a new workspace, and the fresh-workspace self-check."""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import cli
from engine.backup import RestoreError, restore_backup, run_backup
from engine.cli import INSTALL_STEP, LOCAL_CHANGES, NO_NODE, RESTART_NOTE, main, update_checkout
from engine.selfcheck import check_fresh_workspace
from engine.storage import Store
from engine.storage.lease import Lease
from engine.workspace import init_workspace, resolve
from tests.conftest import DEMO_A

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)

# ---- cockpit update --------------------------------------------------------------------------------------------------


class FakeRunner:
    """Stands in for the command runner: records every command, answers the questions about the checkout, and can make
    one step fail."""

    def __init__(self, status: str = "", heads: tuple[str, ...] = ("aaa1111", "bbb2222"), fail: tuple[str, ...] = ()):
        self.calls: list[list[str]] = []
        self.status = status
        self.heads = list(heads)
        self.fail = fail

    def __call__(self, command: list[str], cwd: Path, capture: bool) -> tuple[int, str]:
        self.calls.append(command)
        if command[:2] == ["git", "status"]:
            return 0, self.status
        if command[:2] == ["git", "rev-parse"]:
            return 0, self.heads.pop(0) + "\n"
        if self.fail and tuple(command[: len(self.fail)]) == self.fail:
            return 3, ""
        return 0, ""

    def steps(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] not in (["git", "status"], ["git", "rev-parse"])]


@pytest.fixture
def checkout(tmp_path) -> Path:
    (tmp_path / "src" / ".git").mkdir(parents=True)
    (tmp_path / "src" / "web").mkdir()
    return tmp_path / "src"


def update(checkout, runner, npm="npm"):
    said: list[str] = []
    code = update_checkout(checkout, runner, which=lambda name: npm, say=said.append)
    return code, said


def test_a_clean_checkout_runs_the_four_steps_in_order_and_ends_with_the_commits(checkout):
    runner = FakeRunner()
    code, said = update(checkout, runner)
    assert code == 0
    assert runner.steps() == [
        ["git", "pull", "--ff-only"],
        ["uv", "sync", "--inexact"],
        ["npm", "--prefix", "web", "install"],
        ["npm", "--prefix", "web", "run", "build"],
    ]
    assert any("[1/4]" in line for line in said) and any("[4/4]" in line for line in said)
    assert "Updated from aaa1111 to bbb2222." in said
    assert said[-1] == RESTART_NOTE == "If the app is running, it shows Restart now."


def test_an_unchanged_checkout_says_it_is_already_up_to_date(checkout):
    code, said = update(checkout, FakeRunner(heads=("aaa1111", "aaa1111")))
    assert code == 0 and "Already up to date." in said and said[-1] == RESTART_NOTE


def test_local_changes_refuse_before_any_step(checkout):
    runner = FakeRunner(status=" M engine/cli.py\n")
    code, said = update(checkout, runner)
    assert code == 1
    assert runner.steps() == []
    assert any(LOCAL_CHANGES in line for line in said)


@pytest.mark.parametrize(
    ("failing", "ran"),
    [
        (("git", "pull"), 1),
        (("uv", "sync"), 2),
        (("npm", "--prefix", "web", "install"), 3),
        (("npm", "--prefix", "web", "run"), 4),
    ],
)
def test_a_failing_step_stops_the_rest_and_names_itself_with_its_exit_code(checkout, failing, ran):
    runner = FakeRunner(fail=failing)
    code, said = update(checkout, runner)
    assert code == 1
    assert len(runner.steps()) == ran
    assert "exit code 3" in said[-1] and "Nothing after it was run" in said[-1]
    assert RESTART_NOTE not in said


def test_without_npm_the_web_steps_are_skipped_and_it_says_so(checkout):
    runner = FakeRunner()
    code, said = update(checkout, runner, npm=None)
    assert code == 0
    assert runner.steps() == [["git", "pull", "--ff-only"], ["uv", "sync", "--inexact"]]
    assert NO_NODE in said and said[-1] == RESTART_NOTE


def test_a_checkout_without_web_screens_has_two_steps_and_no_node_message(checkout):
    (checkout / "web").rmdir()
    runner = FakeRunner()
    code, said = update(checkout, runner, npm=None)
    assert code == 0 and len(runner.steps()) == 2 and NO_NODE not in said


def test_an_installed_package_prints_the_install_step_and_does_nothing(tmp_path):
    runner = FakeRunner()
    said: list[str] = []
    code = update_checkout(tmp_path, runner, which=lambda name: "npm", say=said.append)
    assert code != 0
    assert runner.calls == []
    assert said == [INSTALL_STEP] and "install.sh" in INSTALL_STEP and "install.ps1" in INSTALL_STEP


def test_the_command_runs_in_the_source_folder(monkeypatch, checkout, capsys):
    calls: list[tuple[list[str], Path]] = []

    def run(command, cwd, capture):
        calls.append((command, cwd))
        return (0, "abc1234\n" if command[1] == "rev-parse" else "") if capture else (0, "")

    monkeypatch.setattr(cli, "repo_root", lambda: checkout)
    monkeypatch.setattr(cli, "run_command", run)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert main(["update"]) == 0
    assert all(cwd == checkout for _, cwd in calls)
    assert "Restart now" in capsys.readouterr().out


# ---- cockpit restore -------------------------------------------------------------------------------------------------


def digest(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()
    }


@pytest.fixture
def backup(tmp_path):
    """A workspace made from demo-a that an old computer had open, and one dated backup of it."""
    ws = init_workspace(tmp_path / "ws", template=DEMO_A, git=False)
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(offsite), "label": "test"}]})
    (ws.root / "texts").mkdir()
    (ws.root / "texts" / "note.md").write_text("kept text\n", encoding="utf-8")
    store = Store(ws.db_path)
    Lease(store, holder="the old computer").acquire()
    store.close()
    run_backup(ws, cfg, NOW)
    (folder,) = list(offsite.iterdir())
    return ws, folder


def counts(db: Path) -> tuple[dict[str, int], int]:
    conn = sqlite3.connect(db)
    try:
        kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind"))
        return kinds, conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
    finally:
        conn.close()


def test_a_restored_backup_has_the_same_records_and_ledger_and_opens_as_a_workspace(backup, tmp_path):
    ws, folder = backup
    before = digest(folder)
    target = tmp_path / "restored"
    restored = restore_backup(folder, target)
    assert counts(target / "cockpit.db") == counts(ws.db_path)
    assert counts(target / "cockpit.db")[1] > 0
    assert restored.ledger == counts(ws.db_path)[1] and restored.records == sum(counts(ws.db_path)[0].values())
    assert (target / "config").is_dir() and (target / "texts" / "note.md").read_text() == "kept text\n"
    opened = resolve(target)
    store = Store(opened.db_path, cfg=opened.config())
    try:
        assert len(store.read().list("person")) == counts(ws.db_path)[0]["person"]
    finally:
        store.close()
    assert digest(folder) == before  # the backup was only read


def test_the_restored_copy_is_free_to_open_here(backup, tmp_path):
    _, folder = backup
    # The backup was taken while the old computer held the workspace.
    old = sqlite3.connect(folder / "cockpit.db")
    assert old.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 1
    old.close()
    restored = restore_backup(folder, tmp_path / "restored")
    store = Store(restored.workspace.db_path)
    try:
        assert Lease(store, holder="this computer").current() is None
        Lease(store, holder="this computer").acquire()  # no takeover needed
    finally:
        store.close()


def test_the_command_prints_the_folder_and_the_serve_line(backup, tmp_path, capsys):
    _, folder = backup
    target = tmp_path / "restored"
    assert main(["restore", "--backup", str(folder), str(target)]) == 0
    out = capsys.readouterr().out
    assert str(target.resolve()) in out and f"cockpit serve -w {target.resolve()}" in out


def test_a_folder_that_has_files_is_never_written_into(backup, tmp_path, capsys):
    _, folder = backup
    target = tmp_path / "busy"
    target.mkdir()
    (target / "mine.txt").write_text("keep me")
    assert main(["restore", "--backup", str(folder), str(target)]) == 1
    assert "isn't empty" in capsys.readouterr().err
    assert [p.name for p in target.iterdir()] == ["mine.txt"]


def test_an_empty_existing_folder_is_fine(backup, tmp_path):
    _, folder = backup
    target = tmp_path / "empty"
    target.mkdir()
    restore_backup(folder, target)
    assert (target / "cockpit.db").is_file()


def test_a_folder_without_a_database_is_refused(tmp_path, capsys):
    source = tmp_path / "not-a-backup"
    source.mkdir()
    (source / "readme.txt").write_text("hello")
    target = tmp_path / "restored"
    assert main(["restore", "--backup", str(source), str(target)]) == 1
    assert "no database" in capsys.readouterr().err
    assert not target.exists()


def test_a_damaged_database_is_refused_and_nothing_is_made(backup, tmp_path):
    _, folder = backup
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "cockpit.db").write_bytes(b"this is not a database " * 300)
    target = tmp_path / "restored"
    with pytest.raises(RestoreError, match="can't be restored"):
        restore_backup(broken, target)
    assert not target.exists()
    assert [p.name for p in broken.iterdir()] == ["cockpit.db"]


def test_a_truncated_database_is_refused(backup, tmp_path):
    _, folder = backup
    cut = tmp_path / "cut"
    cut.mkdir()
    data = (folder / "cockpit.db").read_bytes()
    (cut / "cockpit.db").write_bytes(data[: len(data) // 2])
    with pytest.raises(RestoreError, match="can't be restored"):
        restore_backup(cut, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_a_database_that_fails_the_integrity_check_is_refused(backup, tmp_path, monkeypatch):
    _, folder = backup
    from engine import backup as backup_module

    real = backup_module._read_only

    class Wrapped:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, *args):
            if sql == "PRAGMA integrity_check":
                return iter([("row 3 missing from index ledger_record",)])
            return self.conn.execute(sql, *args)

        def close(self):
            self.conn.close()

    monkeypatch.setattr(backup_module, "_read_only", lambda path: Wrapped(real(path)))
    with pytest.raises(RestoreError, match="damaged"):
        restore_backup(folder, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_a_target_inside_the_backup_is_refused(backup):
    _, folder = backup
    with pytest.raises(RestoreError, match="inside the backup"):
        restore_backup(folder, folder / "again")
    assert not (folder / "again").exists()


# ---- the fresh-workspace self-check ----------------------------------------------------------------------------------


def test_a_fresh_workspace_shows_no_problem():
    assert check_fresh_workspace() == []


def test_the_fresh_workspace_check_reports_an_account_that_reads_as_failing(monkeypatch):
    monkeypatch.setattr("engine.ai.smoke.ai_state", lambda ws, cfg, store: ("failing", "refused"))
    (finding,) = check_fresh_workspace()
    assert "failing" in finding.message
