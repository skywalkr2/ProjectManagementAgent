"""Journey tests that need no browser: a person's path through the app's own interface, from a workspace made by the
init command with no template, with the stand-in assistant as the only account. The browser journeys are in
`web/e2e/journeys.spec.ts`; these are the ones whose last step is a file on disk."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.ai.task import AiError
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


# ---- no silent stops: what a person sees when the assistant cannot go on ----------------------------


def _started(tmp_path, *, account: dict | None = None):
    """A workspace made by the init command with the stand-in account (or the given account), and a clock the test
    moves. Returns the workspace and the clock."""
    from tests.test_silent_stops import Clock

    me = fixture_records(DEMO_B, "person")[0]["full_name"]
    workspace = tmp_path / "workspace"
    assert main(["init", str(workspace), "--you", me, "--no-git"]) == 0
    ws = Workspace(workspace)
    _stand_in_account(ws)
    if account is not None:
        path = ws.config_dir / "ai.yaml"
        settings = yaml.safe_load(path.read_text(encoding="utf-8"))
        settings["providers"] = {"agent": account}
        settings["tiers"] = {tier: {"use": "agent/default", "fallback": []} for tier in ("routine", "deep")}
        path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    return ws, Clock(datetime.now(UTC))


def _open_with_clock(ws, tmp_path, clock, on_restart=None):
    """The app on a workspace, its worker keeping the test's time and its router never sleeping."""
    app = create_app(
        ws, ws.config(env={}), TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False, on_restart=on_restart
    )
    worker = app.state.worker
    worker.now = clock
    worker.router_factory = lambda: Router(worker.cfg, worker.store, env={}, now=clock, sleep=lambda s: None)
    return TestClient(app, headers=HEADERS), worker


def _changes(client) -> dict[str, dict]:
    return {c["id"]: c for c in client.get("/api/changes").json()}


def _lines(client, kind: str) -> list[dict]:
    return [line for line in client.get("/api/today/queue").json() if line["kind"] == kind]


NOTES = ("Proof copies ship on the fifth.", "The cover files are due on the ninth.")
NOTHING_TO_DO = json.dumps({"summary": "Nothing to do.", "ops": []})


def test_j7_a_usage_limit_pauses_the_account_shows_on_today_and_the_work_resumes_by_itself(tmp_path):
    """J7. I hand in two notes and give my first go. The account says its usage limit is reached and when it resets.
    Today tells me which account waits until when and how many items wait; nothing is asked of me; I press nothing; at
    the reset (also across a restart of the app) both items are read."""
    from tests.test_silent_stops import Scripted, quota

    ws, clock = _started(tmp_path)
    settings_path = ws.config_dir / "workspace.yaml"
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    settings.setdefault("user", {})["timezone"] = "Pacific/Auckland"
    settings_path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    provider = Scripted(quota(7200), NOTHING_TO_DO)
    set_responder(provider)
    try:
        client, worker = _open_with_clock(ws, tmp_path, clock)
        with client:
            for text in NOTES:
                assert client.post("/api/handin", json={"note": "", "pasted": text}).status_code == 200
            worker.run_pending()
            assert client.post("/api/runs/first-go").json()["started"] == 2
            worker.run_pending()
            account = next(iter(worker.cfg.ai.providers))
            [paused] = _lines(client, "paused")
            assert paused["group"] == "risk" and paused["count"] == 2 and paused["account"] == account
            assert paused["waiting"].startswith(f"Waiting for {account}'s limit to reset at ")
            # The reset time is given on the person's own clock (their time zone), not the server's.
            reset = datetime.fromisoformat(paused["until"])
            assert reset == clock() + timedelta(hours=2)
            assert reset.utcoffset() == reset.astimezone(ZoneInfo("Pacific/Auckland")).utcoffset() != timedelta(0)
            assert [c["state"] for c in _changes(client).values()] == ["queued", "queued"]
            assert all(c["waiting"] == paused["waiting"] for c in _changes(client).values())
            assert provider.calls == 1
        # The app is closed and opened again an hour later: the pause is still in force.
        clock.move(hours=1)
        client, worker = _open_with_clock(ws, tmp_path, clock)
        with client:
            assert worker.run_pending() == 0 and provider.calls == 1
            assert _lines(client, "paused")
            clock.move(hours=1, seconds=1)
            assert worker.run_pending() == 2
            assert sorted(c["state"] for c in _changes(client).values()) == ["review", "review"]
            assert not _lines(client, "paused") and provider.calls == 3
    finally:
        set_responder(None)


def test_j8_an_agent_that_exits_cleanly_with_no_answer_is_retried_then_sent_to_me_and_never_done(tmp_path):
    """J8. My account is a command-line agent that finishes without error and writes no answer. The item is not
    marked done: it is tried again by itself, then it comes to me, saying so in plain words, and Try again works once
    the agent answers."""
    script = tmp_path / "agent.py"
    script.write_text(
        "import re, sys\n"
        "prompt = sys.stdin.read()\n"
        "if sys.argv[1] == 'answers':\n"
        "    open(re.findall(r'(/\\S+?answer\\.json)', prompt)[-1], 'w').write(" + repr(NOTHING_TO_DO) + ")\n"
    )

    def agent(mode: str) -> dict:
        return {
            "adapter": "cli-agent",
            "models": {"default": "agent-model"},
            "allowed_data": ["open", "internal", "restricted"],
            "timeout_seconds": 10,
            "agent": {"command": [sys.executable, str(script), mode], "output_via": "outbox"},
        }

    ws, clock = _started(tmp_path, account=agent("silent"))
    client, worker = _open_with_clock(ws, tmp_path, clock)
    with client:
        client.post("/api/handin", json={"note": "", "pasted": NOTES[0]})
        worker.run_pending()
        assert client.post("/api/runs/first-go").json()["started"] == 1
        seen = set()
        for wait in (0, 30, 60):
            clock.move(seconds=wait)
            worker.run_pending()
            [item] = _changes(client).values()
            seen.add(item["state"])
        assert seen == {"queued", "needs_you"}, "never done, never a result"
        [item] = _changes(client).values()
        assert item["state"] == "needs_you" and item["changeset"] is None
        assert item["waiting"].startswith("Tried 3 times without a usable answer.")
        assert "finished without giving an answer" in item["waiting"]
        [line] = [x for x in client.get("/api/today/queue").json() if x["request"] == item["id"]]
        assert line["group"] == "decide" and line["waiting"] == item["waiting"]
        # The agent is fixed (its account is edited and taken in), and Try again reads the item.
        path = ws.config_dir / "ai.yaml"
        settings = yaml.safe_load(path.read_text(encoding="utf-8"))
        settings["providers"]["agent"]["agent"]["command"][-1] = "answers"
        path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
        assert worker.apply_live()
        assert client.post(f"/api/requests/{item['id']}/retry").status_code == 200
        worker.run_pending()
        assert _changes(client)[item["id"]]["state"] == "review"


def test_j9_work_held_for_a_restart_is_the_first_line_on_today_and_runs_after_the_restart_i_choose(tmp_path):
    """J9. A setting that needs a restart changes while the app runs. New work is held; Today's first line says how
    many requests wait and offers Restart now. Nothing restarts until I press it; after the restart the held work is
    read."""
    from tests.test_silent_stops import Scripted

    ws, clock = _started(tmp_path)
    provider = Scripted(NOTHING_TO_DO)
    set_responder(provider)
    restarted: list[int] = []
    try:
        client, worker = _open_with_clock(ws, tmp_path, clock, on_restart=lambda: restarted.append(1))
        with client:
            assert client.post("/api/handin", json={"note": "", "pasted": NOTES[0]}).status_code == 200
            worker.run_pending()
            assert client.post("/api/runs/first-go").json()["started"] == 1
            worker.run_pending()
            # A setting the running app can't take in is changed (a person's edit in Settings does the same).
            path = ws.config_dir / "dispatch.yaml"
            settings = yaml.safe_load(path.read_text(encoding="utf-8"))
            settings["fix_rounds"] = 2
            path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
            for text in NOTES:
                client.post("/api/handin", json={"note": "", "pasted": text + " (after the change)"})
            worker.run_pending()
            assert client.get("/api/status").json()["restart_needed"]
            lines = client.get("/api/today/queue").json()
            assert lines[0]["kind"] == "restart" and lines[0]["group"] == "decide" and lines[0]["count"] == 2
            calls = provider.calls
            worker.run_pending()
            assert provider.calls == calls and restarted == [] and not worker.restart_requested
            # Restart now is the person's choice.
            assert client.post("/api/restart").json() == {"restarting": True}
            assert worker.restart_due() and restarted == [1]
        client, worker = _open_with_clock(ws, tmp_path, clock)
        with client:
            worker.run_pending()
            assert not _lines(client, "restart")
            states = [c["state"] for c in _changes(client).values()]
            assert states.count("review") == 3 and provider.calls > calls
    finally:
        set_responder(None)


def test_j10_an_empty_run_is_retried_by_itself_then_goes_to_me_with_why_and_try_again_works(tmp_path):
    """J10. The assistant answers with nothing. The item waits and says when it will try again, twice; then it comes
    to me, saying it was tried three times; Try again reads it once the assistant answers."""
    from tests.test_silent_stops import Scripted

    ws, clock = _started(tmp_path)
    set_responder(Scripted(""))
    try:
        client, worker = _open_with_clock(ws, tmp_path, clock)
        with client:
            client.post("/api/handin", json={"note": "", "pasted": NOTES[0]})
            worker.run_pending()
            assert client.post("/api/runs/first-go").json()["started"] == 1
            worker.run_pending()
            [item] = _changes(client).values()
            assert item["state"] == "queued" and "Trying again at" in item["waiting"]
            assert "try 2 of 3" in item["waiting"]
            assert not [x for x in client.get("/api/today/queue").json() if x["request"] == item["id"]]
            clock.move(seconds=30)
            worker.run_pending()
            assert "try 3 of 3" in _changes(client)[item["id"]]["waiting"]
            clock.move(seconds=60)
            worker.run_pending()
            stopped = _changes(client)[item["id"]]
            assert stopped["state"] == "needs_you"
            assert stopped["waiting"].startswith("Tried 3 times without a usable answer.")
            [line] = [x for x in client.get("/api/today/queue").json() if x["request"] == item["id"]]
            assert line["group"] == "decide" and line["waiting"] == stopped["waiting"]
            set_responder(Scripted(NOTHING_TO_DO))
            assert client.post(f"/api/requests/{item['id']}/retry").status_code == 200
            worker.run_pending()
            assert _changes(client)[item["id"]]["state"] == "review"
    finally:
        set_responder(None)


# ---- waking up after sleep -------------------------------------------------------------------------


def _watch_runs(worker, source: str) -> list[str]:
    return [r.data["outcome"] for r in worker.store.read().find("watch_run", {"source": source})]


def test_j11_a_scheduled_read_missed_in_sleep_runs_once_on_waking_and_a_lost_network_files_nothing(tmp_path):
    """J11. My source is read every 15 minutes. The computer sleeps for eight hours and wakes with no network yet.
    The read runs once (not once for each missed turn); nothing is filed for the lost network, no question, no
    request, no Today line; and the source does not look read just now: it says it found no network and still shows
    when it was last really read. Once the network is back, the next read runs once, hands in only what is new, and
    only then shows the new time."""
    ws, clock = _started(tmp_path)
    notes = [{"key": f"note-{n}", "title": f"Note {n}", "text": text} for n, text in enumerate(NOTES)]
    source = {
        "id": "notes",
        "connector": "fake",
        "label": "Notes",
        "every_minutes": 15,
        "first_run": "all",
        "settings": {"items": notes},
    }
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": [source]}), encoding="utf-8")
    client, worker = _open_with_clock(ws, tmp_path, clock)
    with client:
        first_read = clock()
        assert worker.run_due_watches() == 1
        assert _watch_runs(worker, "notes") == ["ok"]
        assert len(_changes(client)) == 2
        lines = client.get("/api/today/queue").json()

        clock.move(hours=8)  # the computer sleeps through thirty-two turns and wakes with no network
        worker.cfg.watch.sources[0].settings["error"] = "offline"
        assert worker.run_due_watches() == 1
        assert _watch_runs(worker, "notes") == ["ok", "offline"]
        assert worker.run_due_watches() == 0  # not tried again in a loop
        row = next(s for s in client.get("/api/watch").json() if s["id"] == "notes")
        assert row["last"]["outcome"] == "offline" and row["failures"] == 0 and row["problem"] is None
        assert datetime.fromisoformat(row["read_at"]) == first_read  # still the time of the read that worked
        assert len(_changes(client)) == 2 and client.get("/api/today/queue").json() == lines
        assert not worker.store.read().list("question")

        clock.move(minutes=14)
        assert worker.run_due_watches() == 0
        clock.move(minutes=1)
        del worker.cfg.watch.sources[0].settings["error"]
        worker.cfg.watch.sources[0].settings["items"] = [*notes, {"key": "note-2", "title": "Note 2", "text": "New."}]
        assert worker.run_due_watches() == 1
        assert _watch_runs(worker, "notes") == ["ok", "offline", "ok"]
        assert len(_changes(client)) == 3  # only the new note was handed in
        row = next(s for s in client.get("/api/watch").json() if s["id"] == "notes")
        assert row["last"]["outcome"] == "ok" and datetime.fromisoformat(row["read_at"]) == clock()


def test_j12_a_request_run_with_no_network_waits_for_it_and_runs_once_when_it_is_back(tmp_path):
    """J12. The computer wakes with no network and the assistant has a request to read. The item waits, saying it is
    waiting for the network; no try is used up and nothing is asked of me. After a quarter of an hour Today has one
    line asking me to check the connection, with how many items wait and since when. When the network returns the item
    is read once, the line goes, and the item is there to review."""
    from tests.test_silent_stops import Scripted

    ws, clock = _started(tmp_path)
    cut_off = Scripted(AiError("offline", "name resolution failed"))
    set_responder(cut_off)
    try:
        client, worker = _open_with_clock(ws, tmp_path, clock)
        with client:
            client.post("/api/handin", json={"note": "", "pasted": NOTES[0]})
            worker.run_pending()
            assert client.post("/api/runs/first-go").json()["started"] == 1
            began = clock()
            worker.run_pending()
            [item] = _changes(client).values()
            assert item["state"] == "queued" and item["waiting"].startswith("Waiting for the network since ")
            assert worker.store.read().get("request", item["id"]).data["retries"] == 0
            assert not _lines(client, "offline")

            clock.move(minutes=16)  # the computer sleeps on; the network is still down when it is looked at again
            worker.run_pending()
            stuck = _changes(client)[item["id"]]
            assert stuck["state"] == "queued" and worker.store.read().get("request", item["id"]).data["retries"] == 0
            [line] = _lines(client, "offline")
            assert line["group"] == "risk" and line["count"] == 1 and line["waiting"] == "Waiting for the network"
            assert datetime.fromisoformat(line["waiting_since"]) == began
            assert not [x for x in client.get("/api/today/queue").json() if x["kind"] in ("failed", "refused", "go")]

            set_responder(Scripted(NOTHING_TO_DO))  # the network is back
            clock.move(seconds=worker.cfg.dispatch.offline_check_seconds)
            assert worker.run_pending() == 1
            assert _changes(client)[item["id"]]["state"] == "review"
            assert not _lines(client, "offline")
            assert cut_off.calls == 2 and len(worker.store.read().list("changeset")) == 1
    finally:
        set_responder(None)
