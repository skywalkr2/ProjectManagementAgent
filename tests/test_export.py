import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.config import load_config
from engine.evaluate import load_cases
from engine.selfcheck import check_workspace_fixture
from engine.storage import Store, StoreError, WriteContext
from engine.storage.export import commit_export, export_data, import_data
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records
from tests.roundtrip import round_trip

PM = WriteContext(actor="pm", trust="trusted", op="test")


def same_dirs(a, b) -> bool:
    def contents(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    return contents(a) == contents(b)


def test_fixture_round_trips(demo):
    assert check_workspace_fixture(demo) == []


def test_import_loads_every_fixture_record(demo, store):
    count = import_data(store, demo / "data")
    expected = sum(len(json.loads(p.read_text())) for p in (demo / "data").rglob("*.json"))
    assert count == expected


def test_history_versions_and_deletions_survive_the_round_trip(demo, tmp_path):
    first = Store(tmp_path / "a.db", cfg=load_config(demo / "config", env={}))
    import_data(first, demo / "data")
    pid = fixture_records(demo, "person")[0]["id"]
    with first.transaction() as tx:
        tx.update("person", pid, {"role": "Changed role"}, PM, read_version=1)
        doomed = tx.create("person", {"full_name": "Temporary"}, PM)
        tx.delete("person", doomed.id, PM, read_version=1)
    export_data(first, tmp_path / "e1")
    before = (first.read().ledger(), first.read().sequences())
    first.close()

    second = Store(tmp_path / "b.db", cfg=load_config(demo / "config", env={}))
    import_data(second, tmp_path / "e1")
    assert (second.read().ledger(), second.read().sequences()) == before
    assert second.read().get("person", pid).version == 2
    assert second.read().get("person", doomed.id, include_deleted=True).deleted
    with second.transaction() as tx:
        assert tx.create("person", {"full_name": "Next"}, PM).id != doomed.id
    second.close()

    third = Store(tmp_path / "c.db", cfg=load_config(demo / "config", env={}))
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


def test_the_round_trip_comparison_notices_a_difference(demo, tmp_path, monkeypatch):
    """A control for the comparison itself: a load that changes one record is reported, and an exact one is not."""
    import tests.roundtrip as roundtrip

    cfg = load_config(demo / "config", env={})
    store = Store(tmp_path / "live.db", cfg=cfg)
    import_data(store, demo / "data")
    assert round_trip(store, cfg, tmp_path / "exact")["differences"] == []
    pid = fixture_records(demo, "person")[0]["id"]
    real = roundtrip.import_data

    def altered(fresh, folder):
        loaded = real(fresh, folder)
        with fresh.transaction() as tx:
            tx.update("person", pid, {"role": "Another role"}, PM, read_version=1)
        return loaded

    monkeypatch.setattr(roundtrip, "import_data", altered)
    found = round_trip(store, cfg, tmp_path / "altered")["differences"]
    store.close()
    assert any(pid in line for line in found)
    assert any("ledger" in line for line in found)


def test_a_workspace_used_through_the_screens_round_trips(tmp_path):
    """Hand-ins, a review and an undo go through the HTTP API; the export, loaded into a fresh database, holds the same
    records, versions, ids and ledger, and exporting that again writes the same files."""
    cases = {c["id"]: c for c in load_cases(DEMO_B)}
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    app = create_app(ws, cfg, "round-trip-token", ui_dist=tmp_path / "no-ui")
    store = app.state.store
    try:
        with TestClient(app, headers={"Authorization": "Bearer round-trip-token"}) as client:
            changesets = {}
            for case_id in ("production-checkin", "printer-proof-date"):
                case = cases[case_id]
                set_responder(lambda task, case=case: json.dumps(case["stub_answer"]))
                handed = client.post("/api/handin", json={"note": "", "pasted": case["pasted"]})
                assert handed.status_code == 200
                assert app.state.worker.run_pending() == 1
                item = next(i for i in client.get("/api/changes").json() if i["id"] == handed.json()["request"])
                changesets[case_id] = item["changeset"]["id"]
            assert client.post(f"/api/changesets/{changesets['production-checkin']}/looks-good").status_code == 200
            undone = client.post(f"/api/changesets/{changesets['printer-proof-date']}/undo", json={})
            assert undone.status_code == 200 and undone.json()["restored"]
            proof = changesets["printer-proof-date"]
            entries = [e for e in store.read().ledger(kind="fact") if e["changeset"] == proof]
            assert {e["op"] for e in entries} >= {"undo"}
            assert store.read().list("fact") == []
            assert len(store.read().list("fact", include_deleted=True)) == 1
            report = round_trip(store, cfg, tmp_path / "round-trip")
            assert report["differences"] == []
            assert report["ledger"] > len(entries)
    finally:
        set_responder(None)
