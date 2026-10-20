"""Backups offer the cloud-drive folders found on the computer, by name (the first-run review's F4, N6): the drives
looked for are a config list of names and where each lives on macOS, Windows and Linux; the first one found is
recommended; the folder made inside it is shown as a path of plain names; and "Back up now and continue" saves it and
makes the first backup before the person moves on."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine import cloud_folders
from engine.config import load_config
from engine.config.schema import BackupSettings, CloudFolder
from engine.setup import check_backup_folder
from tests.conftest import DEMO_A, DEMO_B
from tests.test_first_backup import _watching, make
from tests.test_setup import client

SYSTEMS = ("macos", "windows", "linux")


def a_drive(home: Path, drive: CloudFolder, system: str) -> Path | None:
    """Make the folder a drive keeps on this system, inside a fake home folder, from its own listed place."""
    places = getattr(drive, system)
    if not places:
        return None
    place = places[0].replace("*", "Example")
    folder = home / place
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ---- the list is config ---------------------------------------------------------------------------------------------


def test_the_drives_looked_for_are_a_config_list_with_a_place_for_each_system():
    shipped = BackupSettings().cloud_folders
    assert len(shipped) >= 3
    for drive in shipped:
        assert drive.name
        assert any(getattr(drive, system) for system in SYSTEMS)
    assert len({d.name for d in shipped}) == len(shipped)
    assert BackupSettings().cloud_path and all(part for part in BackupSettings().cloud_path)


def test_both_fictional_workspaces_carry_demo_values_for_the_list():
    for demo in (DEMO_A, DEMO_B):
        written = yaml.safe_load((demo / "config" / "storage.yaml").read_text())["backups"]
        assert written["cloud_folders"] and written["cloud_path"], demo.name
        cfg = load_config(demo / "config", env={})
        assert [d.name for d in cfg.storage.backups.cloud_folders] == [d["name"] for d in written["cloud_folders"]]


# ---- finding them ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("system", SYSTEMS)
def test_a_drive_is_found_where_its_entry_says_it_lives_on_that_system(tmp_path, system):
    home = tmp_path / "home"
    home.mkdir()
    drives = BackupSettings().cloud_folders
    made = {d.name: a_drive(home, d, system) for d in drives}
    expected = [d.name for d in drives if made[d.name] is not None]
    found = cloud_folders.found(drives, home, system)
    assert [f.name for f in found] == expected
    for f in found:
        assert f.root.is_dir() and f.root.is_relative_to(home)


def test_nothing_found_when_no_drive_folder_exists(tmp_path):
    assert cloud_folders.found(BackupSettings().cloud_folders, tmp_path, "linux") == []


def test_a_place_that_is_a_file_or_missing_is_skipped(tmp_path):
    drive = next(d for d in BackupSettings().cloud_folders if d.linux)
    (tmp_path / drive.linux[0].replace("*", "x")).write_text("not a folder")
    assert cloud_folders.found([drive], tmp_path, "linux") == []


def test_the_order_of_the_list_decides_which_is_first(tmp_path):
    drives = [d for d in BackupSettings().cloud_folders if d.linux][:2]
    for d in reversed(drives):
        a_drive(tmp_path, d, "linux")
    assert [f.name for f in cloud_folders.found(drives, tmp_path, "linux")] == [d.name for d in drives]


def test_a_pattern_in_a_place_matches_a_folder_with_any_name_there(tmp_path):
    drive = CloudFolder(name="Test drive", linux=["Sync - *"])
    (tmp_path / "Sync - Work").mkdir()
    found = cloud_folders.found([drive], tmp_path, "linux")
    assert [f.root.name for f in found] == ["Sync - Work"]


def test_the_shown_path_is_plain_names_joined_with_an_arrow():
    assert cloud_folders.shown(["Backups", "Example App"]) == "Backups › Example App"


def test_the_folder_made_inside_a_drive_is_the_configured_path_under_it(tmp_path):
    made = cloud_folders.make_backup_folder(tmp_path, ["Backups", "Example App"])
    assert made == tmp_path / "Backups" / "Example App" and made.is_dir()
    assert cloud_folders.make_backup_folder(tmp_path, ["Backups", "Example App"]) == made  # again changes nothing


# ---- the screen's routes --------------------------------------------------------------------------------------------


def with_home(monkeypatch, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def test_the_step_lists_the_drives_found_by_name_with_the_first_recommended_and_no_raw_path(tmp_path, monkeypatch):
    home = tmp_path / "home"
    with_home(monkeypatch, home)
    ws, cfg, store = make(tmp_path)
    system = cloud_folders.system_name()
    here = [d for d in cfg.storage.backups.cloud_folders if getattr(d, system)][:2]
    assert len(here) == 2
    for d in reversed(here):  # made in the opposite order: the list's order decides, not the order they were made
        a_drive(home, d, system)
    c, api = client(ws, cfg, store)
    listed = c.get(f"{api}/setup/backup-folders").json()
    assert [f["name"] for f in listed["folders"]] == [d.name for d in here]
    assert [f["recommended"] for f in listed["folders"]] == [True, False]
    assert listed["shown"] == cloud_folders.shown(cfg.storage.backups.cloud_path)
    assert str(home) not in str(listed)


def test_with_no_drive_folder_the_list_is_empty(tmp_path, monkeypatch):
    with_home(monkeypatch, tmp_path / "empty-home")
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    assert c.get(f"{api}/setup/backup-folders").json()["folders"] == []


def test_backing_up_to_a_drive_makes_its_folder_saves_it_and_makes_the_first_backup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    with_home(monkeypatch, home)
    ws, cfg, store = make(tmp_path)
    system = cloud_folders.system_name()
    drive = next(d for d in cfg.storage.backups.cloud_folders if getattr(d, system))
    root = a_drive(home, drive, system)
    c, api = client(ws, cfg, store)
    started = _watching(c.app.state.worker)
    assert c.get(f"{api}/status").json()["backup"]["configured"] is False
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    done = c.post(f"{api}/setup/backup-folder/cloud", json={"name": drive.name, "fingerprint": fingerprint})
    assert done.status_code == 200, done.text
    made = root.joinpath(*cfg.storage.backups.cloud_path)
    assert made.is_dir() and check_backup_folder(ws, str(made)).ok
    saved = load_config(ws.config_dir, env={}).storage.backups.targets
    assert [(Path(t.path), t.label) for t in saved] == [(made.resolve(), drive.name)]
    # The first backup was made before the answer, so the warning is gone when the person moves on.
    backup = c.get(f"{api}/status").json()["backup"]
    assert started and backup["last_success"] is not None and backup["needs_attention"] is False
    assert [p for p in made.iterdir() if p.is_dir()]


def test_a_drive_that_is_not_in_the_list_or_not_on_this_computer_is_refused(tmp_path, monkeypatch):
    with_home(monkeypatch, tmp_path / "home")
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    drive = cfg.storage.backups.cloud_folders[0]
    for name in ("No such drive", drive.name):
        refused = c.post(f"{api}/setup/backup-folder/cloud", json={"name": name, "fingerprint": fingerprint})
        assert refused.status_code == 400
    assert load_config(ws.config_dir, env={}).storage.backups.targets == []
