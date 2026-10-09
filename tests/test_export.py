import filecmp
import subprocess

import pytest

from engine.selfcheck import check_workspace_fixture
from engine.storage import Store, StoreError, WriteContext
from engine.storage.export import commit_export, export_data, import_data
from tests.conftest import fixture_records

PM = WriteContext(actor="pm", trust="trusted", op="test")


def same_dirs(a, b) -> bool:
    cmp = filecmp.dircmp(a, b)
    return not (cmp.left_only or cmp.right_only or cmp.diff_files)


def test_fixture_round_trips(demo):
    assert check_workspace_fixture(demo) == []


def test_import_loads_every_fixture_record(demo, store):
    count = import_data(store, demo / "data")
    expected = sum(len(fixture_records(demo, k)) for k in ("person", "team", "project", "action", "question"))
    assert count == expected


def test_history_versions_and_deletions_survive_the_round_trip(demo, tmp_path):
    first = Store(tmp_path / "a.db")
    import_data(first, demo / "data")
    pid = fixture_records(demo, "person")[0]["id"]
    with first.transaction() as tx:
        tx.update("person", pid, {"role": "Changed role"}, PM, read_version=1)
        doomed = tx.create("person", {"full_name": "Temporary"}, PM)
        tx.delete("person", doomed.id, PM, read_version=1)
    export_data(first, tmp_path / "e1")
    before = (first.read().ledger(), first.read().sequences())
    first.close()

    second = Store(tmp_path / "b.db")
    import_data(second, tmp_path / "e1")
    assert (second.read().ledger(), second.read().sequences()) == before
    assert second.read().get("person", pid).version == 2
    assert second.read().get("person", doomed.id, include_deleted=True).deleted
    with second.transaction() as tx:
        assert tx.create("person", {"full_name": "Next"}, PM).id != doomed.id
    second.close()

    third = Store(tmp_path / "c.db")
    import_data(third, tmp_path / "e1")
    export_data(third, tmp_path / "e2")
    third.close()
    assert same_dirs(tmp_path / "e1", tmp_path / "e2")


def test_import_needs_an_empty_database(demo, store):
    import_data(store, demo / "data")
    with pytest.raises(StoreError, match="empty database"):
        import_data(store, demo / "data")


def test_export_commits_to_the_workspace_git(workspace):
    store = Store(workspace.db_path)
    pid = fixture_records(workspace.root, "person")[0]["id"]
    with store.transaction() as tx:
        tx.update("person", pid, {"role": "New role"}, PM, read_version=1)
    export_data(store, workspace.data_dir)
    store.close()
    assert commit_export(workspace.root, "Export")
    assert not commit_export(workspace.root, "Nothing new")
    log = subprocess.run(["git", "-C", str(workspace.root), "log", "--oneline"], capture_output=True, text=True)
    assert len(log.stdout.strip().splitlines()) >= 1
