"""The first backup (design 7.8): choosing a backup folder makes the first backup at once, in the background, so the
person isn't asked to back up right after choosing where; and what a backup holds never includes a pasted key."""

import time

from engine.backup import run_backup, state
from engine.config import load_config
from engine.config.yaml_edit import set_key
from engine.setup import keep_key
from engine.storage import Store
from engine.workspace import init_workspace
from tests.test_setup import client


def make(tmp_path):
    """A new workspace started with no template, as a person's is: nothing backed up and no folder chosen."""
    ws = init_workspace(tmp_path / "ws", git=False)
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def _wait(until, seconds=15.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if until():
            return True
        time.sleep(0.05)
    return False


def _choose(c, api, folder):
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    return c.post(f"{api}/setup/backup-folder", json={"path": str(folder), "label": "", "fingerprint": fingerprint})


def test_choosing_a_backup_folder_makes_the_first_backup(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    folder = tmp_path / "drive"
    folder.mkdir()
    assert c.get(f"{api}/status").json()["backup"]["configured"] is False
    assert _choose(c, api, folder).status_code == 200
    # The backup is made without any further request, and the app no longer asks for one.
    assert _wait(lambda: c.get(f"{api}/status").json()["backup"]["last_success"] is not None)
    backup = c.get(f"{api}/status").json()["backup"]
    assert backup["configured"] is True and backup["needs_attention"] is False and backup["last_error"] is None
    copies = [p for p in folder.iterdir() if p.is_dir()]
    assert len(copies) == 1 and (copies[0] / "cockpit.db").is_file() and (copies[0] / "config").is_dir()


def test_a_folder_added_after_a_backup_succeeded_makes_no_extra_backup(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    assert _choose(c, api, first).status_code == 200
    assert _wait(lambda: c.get(f"{api}/status").json()["backup"]["last_success"] is not None)
    assert _choose(c, api, second).status_code == 200
    time.sleep(0.5)
    assert [p for p in second.iterdir()] == []
    assert len([p for p in first.iterdir() if p.is_dir()]) == 1


def test_the_first_backup_records_a_failure_when_the_folder_is_gone(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    folder = tmp_path / "unplugged"
    folder.mkdir()
    worker = c.app.state.worker
    # Settings that name a folder which then goes away, as a drive that was disconnected does.
    path = ws.config_dir / "storage.yaml"
    path.write_text(set_key(path.read_text(), ["backups", "targets"], [{"path": str(folder), "label": ""}]))
    folder.rmdir()
    thread = worker.first_backup_soon()
    assert thread is not None
    thread.join(timeout=15)
    state_now = state(ws, load_config(ws.config_dir, env={}))
    assert state_now.last_success is None and state_now.last_error and "isn't there" in state_now.last_error
    assert state_now.needs_attention is True


def test_two_backups_in_the_same_second_each_get_a_folder(tmp_path):
    from datetime import UTC, datetime

    ws, cfg, store = make(tmp_path)
    folder = tmp_path / "drive"
    folder.mkdir()
    cfg = ws.config(env={}, flags={"storage.backups.targets": [{"path": str(folder), "label": ""}]})
    now = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    run_backup(ws, cfg, now)
    status = run_backup(ws, cfg, now)
    assert status[str(folder)]["last_error"] is None
    assert len([p for p in folder.iterdir() if p.is_dir()]) == 2


def test_a_pasted_key_is_never_in_a_backup(tmp_path):
    ws, cfg, store = make(tmp_path)
    key = "sk-made-up-key-for-this-test"
    keep_key(ws, "my-account", key)
    folder = tmp_path / "drive"
    folder.mkdir()
    flags = {"storage.backups.targets": [{"path": str(folder), "label": ""}]}
    run_backup(ws, ws.config(env={}, flags=flags))
    copies = [p for p in folder.iterdir() if p.is_dir()]
    assert len(copies) == 1
    holders = [p for p in copies[0].rglob("*") if p.is_file() and key.encode() in p.read_bytes()]
    assert holders == []
    assert not any(part == ".cockpit" for p in copies[0].rglob("*") for part in p.parts)
    # The key is where the screen says it is: on this computer, in the workspace's private folder.
    assert (ws.private_dir / "keys" / "my-account").read_text().strip() == key
