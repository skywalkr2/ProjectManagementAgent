"""The scheduled readable export: written and committed on the interval, never sent anywhere, and off for a workspace
that has no repository to keep it in."""

import logging
import subprocess
from datetime import UTC, datetime

from engine.storage import Store, WriteContext
from engine.worker import Events, Worker
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.test_silent_stops import Clock

PM = WriteContext(actor="pm", trust="trusted", op="test")


def _commits(root) -> int:
    log = subprocess.run(["git", "-C", str(root), "log", "--oneline"], capture_output=True, text=True, check=True)
    return len(log.stdout.strip().splitlines())


def _changed_role(store, text: str) -> None:
    pid = fixture_records(DEMO_B, "person")[0]["id"]
    with store.transaction() as tx:
        tx.update("person", pid, {"role": text}, PM, read_version=store.read().get("person", pid).version)


def test_the_scheduled_export_is_committed_on_the_interval_and_never_pushed(workspace, tmp_path):
    offsite = tmp_path / "offsite.git"
    subprocess.run(["git", "init", "-q", "--bare", str(offsite)], check=True, capture_output=True)
    cfg = workspace.config(env={}, flags={"storage.export.every_minutes": 60, "storage.export.remote": str(offsite)})
    store = Store(workspace.db_path)
    clock = Clock(datetime.now(UTC))
    worker = Worker(workspace, store, cfg, Events(), now=clock)
    try:
        before = _commits(workspace.root)
        _changed_role(store, "First change")
        assert worker.export_if_due()  # never written on a schedule: due at once
        assert _commits(workspace.root) == before + 1
        _changed_role(store, "Second change")
        clock.move(minutes=59)
        assert not worker.export_if_due() and _commits(workspace.root) == before + 1
        clock.move(minutes=2)  # a computer waking long after the interval catches up at once
        assert worker.export_if_due() and _commits(workspace.root) == before + 2
        assert not worker.export_if_due()
    finally:
        store.close()
    sent = subprocess.run(["git", "-C", str(offsite), "for-each-ref"], capture_output=True, text=True, check=True)
    assert sent.stdout == ""  # the remote is not offered yet: nothing is sent anywhere


def test_the_interval_is_taken_in_at_once_and_the_commit_switch_waits_for_a_restart():
    from engine.worker import is_live

    assert is_live("storage.export.every_minutes") and not is_live("storage.export.commit")


def test_a_workspace_without_a_repository_gets_no_scheduled_export_and_says_so_once(tmp_path, caplog):
    ws = init_workspace(tmp_path / "plain", template=DEMO_B, git=False)
    store = Store(ws.db_path)
    worker = Worker(ws, store, ws.config(env={}), Events(), now=lambda: datetime.now(UTC))
    before = {p.name: p.read_bytes() for p in ws.data_dir.iterdir() if p.is_file()}
    try:
        _changed_role(store, "A change")
        with caplog.at_level(logging.INFO, logger="engine.worker"):
            assert not worker.export_if_due() and not worker.export_if_due()
    finally:
        store.close()
    assert len([r for r in caplog.records if "no git repository" in r.getMessage()]) == 1
    assert {p.name: p.read_bytes() for p in ws.data_dir.iterdir() if p.is_file()} == before
