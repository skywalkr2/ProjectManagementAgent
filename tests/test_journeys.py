"""Journey tests that need no browser: a person's path through the app's own interface, from a workspace made by the
init command with no template, with the stand-in assistant as the only account. The browser journeys are in
`web/e2e/journeys.spec.ts`; these are the ones whose last step is a file on disk."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.backup import restore_backup
from engine.cli import main
from engine.workspace import Workspace
from tests.conftest import DEMO_B, fixture_records

TOKEN = "test-token-value"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def _stand_in_account(ws: Workspace) -> None:
    """The account a person has set up, as its settings file holds it: the stand-in, for every kind of work. (The
    screen's Add account never offers the stand-in; this is the one setup step a test must do for them.)"""
    path = ws.config_dir / "ai.yaml"
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    settings["providers"] = {
        "stub": {
            "adapter": "stub",
            "models": {"default": "scripted"},
            "allowed_data": ["open", "internal", "restricted"],
        }
    }
    settings["tiers"] = {tier: {"use": "stub/default", "fallback": []} for tier in ("routine", "deep")}
    path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")


def _counts(database: Path) -> tuple[dict[str, int], int]:
    conn = sqlite3.connect(database)
    try:
        kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind"))
        return kinds, conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
    finally:
        conn.close()


def _open(ws: Workspace, tmp_path: Path):
    """The app on this workspace, as a person's browser reaches it (no screens needed)."""
    app = create_app(ws, ws.config(env={}), TOKEN, ui_dist=tmp_path / "no-ui")
    return TestClient(app, headers=HEADERS), app


def _what_the_screens_show(client: TestClient) -> dict:
    """What the first screens are built from: what changed, and what Today asks of the person and lists for them."""
    return {
        "changes": client.get("/api/changes").json(),
        "queue": client.get("/api/today/queue").json(),
        "todo": client.get("/api/today/todo").json(),
        "people": client.get("/api/people").json(),
    }


def test_j5_a_backup_of_a_working_workspace_restores_to_the_same_screens_and_ledger(tmp_path, capsys):
    """J5. I start a workspace with no template, hand in a note and let the assistant read it, back up to a folder
    I chose, restore that backup into a new folder, and open it: Today and What changed show what they showed, and the
    ledger is as long."""
    me = fixture_records(DEMO_B, "person")[0]["full_name"]
    workspace = tmp_path / "workspace"
    assert main(["init", str(workspace), "--you", me, "--no-git"]) == 0
    ws = Workspace(workspace)
    _stand_in_account(ws)
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    set_responder(None)  # the stand-in answers by its own rules
    try:
        client, app = _open(ws, tmp_path)
        with client:
            # The backup folder is chosen on screen: it is checked, saved, and taken in without a restart.
            fingerprint = client.get("/api/settings").json()["fingerprint"]
            chosen = client.post(
                "/api/setup/backup-folder", json={"path": str(offsite), "label": "", "fingerprint": fingerprint}
            )
            assert chosen.status_code == 200, chosen.text
            app.state.worker.apply_live()
            assert client.get("/api/status").json()["backup"]["configured"] is True

            # A note is handed in; nothing runs until the first go, then the assistant reads it.
            handed = client.post(
                "/api/handin",
                json={
                    "note": "",
                    "pasted": "I will send the venue list by 2026-11-02.\nDecided: the offsite is on a Friday.",
                },
            )
            assert handed.status_code == 200, handed.text
            app.state.worker.run_pending()
            held = [line for line in client.get("/api/today/queue").json() if line["kind"] == "first_go"]
            assert len(held) == 1 and held[0]["count"] == 1
            assert client.post("/api/runs/first-go").json()["started"] == 1
            app.state.worker.run_pending()
            shown = _what_the_screens_show(client)
            assert shown["todo"], "the action the assistant filed for me is in my list"
            assert any(change["state"] == "review" for change in shown["changes"])
            assert not [line for line in shown["queue"] if line["kind"] == "first_go"]

            # Choosing the folder made the first backup; Back up now makes another, with everything done since.
            status = client.post("/api/backup")
            assert status.status_code == 200, status.text
            assert status.json()["backup"]["last_success"] and not status.json()["backup"]["needs_attention"]
        first, dated = sorted(offsite.iterdir())
        assert _counts(first / "cockpit.db") != _counts(dated / "cockpit.db")
        before = _counts(ws.db_path)

        # Restore it into a new folder and open that: the same screens, the same ledger.
        restored = restore_backup(dated, tmp_path / "restored")
        assert _counts(restored.workspace.db_path) == before and restored.ledger == before[1] > 0
        again, _ = _open(restored.workspace, tmp_path)
        with again:
            assert _what_the_screens_show(again) == shown

        # The same restore, by the command a person types.
        capsys.readouterr()
        target = tmp_path / "by-command"
        assert main(["restore", "--backup", str(dated), str(target)]) == 0
        said = capsys.readouterr().out
        assert str(target.resolve()) in said and "serve" in said
        assert _counts(target / "cockpit.db") == before
    finally:
        set_responder(None)
