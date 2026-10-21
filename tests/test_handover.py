"""Handing a workspace between two computers through the synced folder: the lease, loading the newer copy, refusing
diverged histories until the person keeps one, a folder still syncing, and copies a sync service made on a conflict."""

from datetime import UTC, datetime, timedelta

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B


def set_folder(ws, folder):
    storage = yaml.safe_load((ws.config_dir / "storage.yaml").read_text()) or {}
    storage["sync"] = {"folder": str(folder), "lease_stale_after_minutes": 10}
    (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage))
    return load_config(ws.config_dir, env={})


@pytest.fixture
def two(tmp_path):
    """Computer A with the demo workspace and a synced folder; computer B a fresh, empty workspace on that folder."""
    from engine.workspace import init_workspace

    folder = tmp_path / "synced"
    folder.mkdir()
    a = init_workspace(tmp_path / "a", template=DEMO_B, git=False)
    b = init_workspace(tmp_path / "b", git=False, personal=False)  # a computer joining the folder, as `--sync` makes it
    return a, set_folder(a, folder), b, set_folder(b, folder), folder


def change(ws, cfg, name):
    from engine.applier import apply_as_person
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        apply_as_person(store, cfg, [{"op": "project.add", "name": name}], "Test change")
    finally:
        store.close()


def write(ws, cfg):
    from engine.storage import Store
    from engine.sync import write_folder

    store = Store(ws.db_path, cfg=cfg)
    try:
        return write_folder(store, ws, cfg)
    finally:
        store.close()


def projects(ws, cfg):
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        return sorted(p.data["name"] for p in store.read().list("project"))
    finally:
        store.close()


def test_the_first_computer_takes_the_lease(two):
    from engine.handover import install_id, open_workspace, read_lease

    a, cfg_a, _, _, folder = two
    assert open_workspace(a, cfg_a).action == "first"
    lease = read_lease(folder)
    assert lease.holder == install_id(a) and not lease.released


def test_the_other_computer_is_refused_while_the_lease_is_fresh(two):
    from engine.handover import Refused, open_workspace

    a, cfg_a, b, cfg_b, _ = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    with pytest.raises(Refused, match="This workspace is open on"):
        open_workspace(b, cfg_b)
    later = datetime.now(UTC) + timedelta(minutes=11)
    assert open_workspace(b, cfg_b, now=later).action == "loaded"


def test_after_release_the_other_computer_loads_the_newer_copy(two):
    from engine.handover import install_id, open_workspace, read_lease, release

    a, cfg_a, b, cfg_b, folder = two
    open_workspace(a, cfg_a)
    change(a, cfg_a, "Harbor Survey")
    write(a, cfg_a)
    release(a, cfg_a)
    opened = open_workspace(b, cfg_b)
    assert opened.action == "loaded" and opened.backup
    assert projects(b, cfg_b) == projects(a, cfg_a)
    assert load_config(b.config_dir, env={}).storage.sync.folder == str(folder)  # storage stays per computer
    assert read_lease(folder).holder == install_id(b)
    change(b, cfg_b, "Tide Tables")
    write(b, cfg_b)
    release(b, cfg_b)
    assert open_workspace(a, cfg_a).action == "loaded" and "Tide Tables" in projects(a, cfg_a)


def test_a_computer_ahead_of_the_folder_just_writes(two):
    from engine.handover import open_workspace, release

    a, cfg_a, _, _, _ = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    change(a, cfg_a, "Harbor Survey")
    release(a, cfg_a)
    assert open_workspace(a, cfg_a).action == "newer_here"


def test_diverged_histories_load_nothing_until_one_is_kept(two):
    from engine.handover import Diverged, keep, open_workspace, release

    a, cfg_a, b, cfg_b, folder = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    release(a, cfg_a)
    open_workspace(b, cfg_b)
    release(b, cfg_b)
    change(a, cfg_a, "Made on A")
    change(b, cfg_b, "Made on B")
    write(b, cfg_b)
    release(b, cfg_b)
    with pytest.raises(Diverged, match="both have changes"):
        open_workspace(a, cfg_a)
    assert "Made on B" not in projects(a, cfg_a)
    saved = keep(a, cfg_a, "here")
    assert (a.private_dir / "handover-backups").is_dir() and saved
    with pytest.raises(Diverged):
        open_workspace(b, cfg_b)
    keep(b, cfg_b, "folder")
    assert "Made on A" in projects(b, cfg_b) and "Made on B" not in projects(b, cfg_b)


def test_a_folder_still_syncing_is_never_loaded(two):
    from engine.handover import Refused, open_workspace, release

    a, cfg_a, b, cfg_b, folder = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    release(a, cfg_a)
    ledger = folder / ".cockpit" / "export" / "ledger.jsonl"
    ledger.write_text(ledger.read_text()[:-40])
    with pytest.raises(Refused, match="still bringing in changes"):
        open_workspace(b, cfg_b)
    assert projects(b, cfg_b) == []


def test_conflict_copies_are_shown_and_never_loaded(two):
    from engine.handover import conflict_copies, open_workspace, release

    a, cfg_a, b, cfg_b, folder = two
    change(a, cfg_a, "Harbor Survey")
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    release(a, cfg_a)
    (folder / ".cockpit" / "export" / "ledger (1).jsonl").write_text("{}\n")
    (folder / "Harbor Survey" / "project-LAPTOP.yaml").write_text("name: other\n")
    (folder / "Harbor Survey" / "my own notes.md").write_text("mine\n")
    found = conflict_copies(folder)
    assert ".cockpit/export/ledger (1).jsonl" in found and "Harbor Survey/project-LAPTOP.yaml" in found
    assert "Harbor Survey/my own notes.md" not in found
    opened = open_workspace(b, cfg_b)
    assert opened.action == "loaded" and ".cockpit/export/ledger (1).jsonl" in opened.conflict_copies


def test_the_worker_stops_writing_once_another_computer_holds_the_folder(two):
    from engine.handover import take
    from engine.storage import Store
    from engine.worker import Events, Worker

    a, cfg_a, b, cfg_b, folder = two
    store = Store(a.db_path, cfg=cfg_a)
    try:
        worker = Worker(a, store, cfg_a, Events())
        assert worker.sync_if_changed()
        take(b, cfg_b, ledger=0)
        change(a, cfg_a, "After the takeover")
        assert not worker.sync_if_changed() and worker.sync_lost
        assert "opened on" in worker.sync_problem
        assert not (folder / "After the takeover").exists()
    finally:
        store.close()


def test_closing_releases_the_lease(two):
    from engine.handover import read_lease
    from engine.storage import Store
    from engine.worker import Events, Worker

    a, cfg_a, _, _, folder = two
    store = Store(a.db_path, cfg=cfg_a)
    try:
        worker = Worker(a, store, cfg_a, Events())
        worker.release_folder()
        assert read_lease(folder).released
    finally:
        store.close()


def test_a_new_computer_set_up_on_the_synced_folder_loads_it_and_makes_no_personal_project_of_its_own(two, tmp_path):
    """`cockpit init --sync` takes the folder's workspace whole; a Personal project made here would diverge from it."""
    from engine.cli import main
    from engine.handover import open_workspace, release
    from engine.workspace import Workspace

    a, cfg_a, _, _, folder = two
    open_workspace(a, cfg_a)
    write(a, cfg_a)
    release(a, cfg_a)
    assert main(["init", str(tmp_path / "c"), "--sync", str(folder), "--no-git"]) == 0
    c = Workspace(tmp_path / "c")
    assert projects(c, load_config(c.config_dir, env={})) == projects(a, cfg_a)
