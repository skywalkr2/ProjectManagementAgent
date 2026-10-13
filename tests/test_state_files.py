"""The small state files kept in the workspace's private folder are written whole and changed one at a time, so request
threads and the worker's threads never lose each other's changes or read a half-written file. One test per file that
several threads touch, and one for the helper they share."""

import json
import os
import stat
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import backup, handover, sign_in_sources
from engine.ai import smoke
from engine.ai.catalog import Catalogs
from engine.ai.pauses import Pauses
from engine.ai.task import ModelInfo
from engine.state_file import changing, write_whole
from engine.workspace import Workspace

THREADS = 8


def run_together(work, count: int = THREADS) -> None:
    """Start `count` threads on `work(n)` at the same moment; any error a thread hits is raised here."""
    start = threading.Barrier(count)
    problems: list[BaseException] = []

    def go(n: int) -> None:
        try:
            start.wait()
            work(n)
        except BaseException as err:  # reported by the test thread
            problems.append(err)

    threads = [threading.Thread(target=go, args=(n,)) for n in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if problems:
        raise problems[0]


def private(tmp_path: Path) -> SimpleNamespace:
    """The part of a workspace these files need: its private folder."""
    return SimpleNamespace(private_dir=tmp_path / ".cockpit")


# ---- the helper ------------------------------------------------------------------------------------------------------


def test_write_whole_replaces_the_file_in_one_step_and_leaves_nothing_behind(tmp_path):
    target = tmp_path / "folder" / "state.json"
    write_whole(target, "one")
    write_whole(target, "two\n")
    assert target.read_text(encoding="utf-8") == "two\n"
    assert [p.name for p in target.parent.iterdir()] == ["state.json"]
    # A failure while writing leaves the earlier file as it was and no temporary file.
    with pytest.raises(TypeError):
        write_whole(target, 5)  # type: ignore[arg-type]
    assert target.read_text(encoding="utf-8") == "two\n"
    assert [p.name for p in target.parent.iterdir()] == ["state.json"]


@pytest.mark.skipif(os.name == "nt", reason="file modes")
def test_write_whole_with_a_mode_is_never_readable_more_widely(tmp_path):
    target = tmp_path / "secret"
    write_whole(target, "value", mode=0o600)
    write_whole(target, "other", mode=0o600)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_changing_one_file_runs_one_change_at_a_time_and_is_reentrant(tmp_path):
    path = tmp_path / "counter"
    write_whole(path, "0")

    def add(_n: int) -> None:
        for _ in range(20):
            with changing(path), changing(path):
                write_whole(path, str(int(path.read_text(encoding="utf-8")) + 1))

    run_together(add)
    assert path.read_text(encoding="utf-8") == str(THREADS * 20)


# ---- one test for each file several threads touch --------------------------------------------------------------------


def test_sign_ins_finishing_together_each_stay_recorded_as_started(tmp_path):
    ws = private(tmp_path)
    names = [f"plugin/sign-in-{n}" for n in range(THREADS)]
    run_together(lambda n: sign_in_sources._remember(ws, {names[n]}))
    assert sign_in_sources._started(ws) == set(names)


def test_the_install_id_and_the_token_are_made_once_whoever_asks_first(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    ids: list[str] = []
    tokens: list[str] = []

    def ask(_n: int) -> None:
        ids.append(handover.install_id(ws))
        tokens.append(ws.install_token())

    run_together(ask)
    assert len(set(ids)) == 1 and len(set(tokens)) == 1
    assert (ws.private_dir / "install-id").read_text(encoding="utf-8").strip() == ids[0]
    assert (ws.private_dir / "token").read_text(encoding="utf-8").strip() == tokens[0]


def test_model_catalogs_kept_by_two_readers_of_one_file_both_stay(tmp_path):
    path = tmp_path / ".cockpit" / "ai-catalog.json"
    both_have_read = threading.Barrier(2)
    one, other = Catalogs(path, 24), Catalogs(path, 24)

    def fetch(info: ModelInfo):
        def read():
            both_have_read.wait(timeout=10)
            return {"model": info}

        return read

    def ask(n: int) -> None:
        (one, other)[n].model(f"provider-{n}", "model", fetch(ModelInfo(context_tokens=n + 1)))

    run_together(ask, 2)
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(kept) == ["provider-0", "provider-1"]


def test_pauses_made_together_each_stay_and_a_reader_never_finds_half_a_file(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    pauses = Pauses(tmp_path / ".cockpit" / "ai-pauses.json", lambda: now)
    until = now + timedelta(hours=1)
    run_together(lambda n: pauses.pause(f"account-{n}", until))
    assert sorted(pauses.active()) == [f"account-{n}" for n in range(THREADS)]


def _write_and_read(write, read, text_size: int = 200_000) -> None:
    """A writer replaces the file again and again while readers read it: a reader that ever finds it half written
    (empty, or cut off) fails the test."""
    stop = threading.Event()
    problems: list[BaseException] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                read()
            except BaseException as err:  # reported by the test thread
                problems.append(err)
                return

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in readers:
        t.start()
    try:
        for n in range(60):
            write(n, "x" * text_size)
    finally:
        stop.set()
        for t in readers:
            t.join()
    assert not problems


def test_the_last_backup_result_is_never_read_half_written(tmp_path):
    ws = private(tmp_path)
    ws.private_dir.mkdir()

    def write(n: int, filler: str) -> None:
        backup._save(ws, {"target": {"last_success": f"{n}", "last_error": filler}})

    def read() -> None:
        # `due` and `state` read this while a backup is writing it.
        found = backup._load(ws)
        assert found == {} or found["target"]["last_error"].startswith("x")

    # A file that can't be read is reported as nothing kept, never as an error.
    (ws.private_dir / backup.STATUS_FILE).write_text("{cut off", encoding="utf-8")
    assert backup._load(ws) == {}
    _write_and_read(write, read)
    # The reader above only passes for whole files, and a whole file is always valid JSON.
    json.loads((ws.private_dir / backup.STATUS_FILE).read_text(encoding="utf-8"))


def test_the_last_connection_test_is_never_read_half_written(tmp_path):
    ws = SimpleNamespace(private_dir=tmp_path / ".cockpit", config_dir=tmp_path / "config")
    ws.config_dir.mkdir()

    def write(_n: int, filler: str) -> None:
        smoke.record(ws, [smoke.SmokeResult("main", "account", True, True, filler)])  # type: ignore[arg-type]

    def read() -> None:
        smoke.untested_since_change(ws)  # type: ignore[arg-type]
        found = smoke.last_test(ws)  # type: ignore[arg-type]
        assert found is None or found["passed"] is True

    _write_and_read(write, read)
