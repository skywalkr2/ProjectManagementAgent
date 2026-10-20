"""The routes read the app's clock (the worker's `now`), never the real one: with that clock set to a day far from
today, a route of each module answers for that day. A route that read the real clock would answer for today."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai.adapters import ADAPTERS
from engine.storage import WriteContext
from engine.watch import refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_today_dashboard import event, make

_PM = WriteContext("pm", "trusted", "test")
LATER = datetime(2031, 3, 4, 12, 0, tzinfo=UTC)  # years after any day the suite runs on
EARLIER = datetime(2020, 3, 2, 12, 0, tzinfo=UTC)  # years before it


def app_at(tmp_path, clock, ws=None, cfg=None):
    ws = ws or init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = cfg or ws.config(env={}, flags={"server.base_path": "/", "storage.backups.automatic": False})
    app = create_app(ws, cfg, "clock-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    app.state.worker.now = lambda: clock
    return app, TestClient(app, headers={"Authorization": "Bearer clock-token"})


def test_the_agenda_lists_the_events_of_the_apps_day(tmp_path):
    items = [event("soon", (LATER + timedelta(minutes=1)).isoformat(), (LATER + timedelta(minutes=2)).isoformat())]
    ws, cfg, store = make(tmp_path, items)
    refresh(ws, store, cfg, "s", LATER)
    store.close()
    app, client = app_at(tmp_path, LATER, ws, cfg)
    with client:
        assert [a["title"] for a in client.get("/api/today/agenda").json()] == ["Event soon"]


def test_the_ai_accounts_warn_of_a_key_ending_by_the_apps_day(tmp_path):
    soon = (LATER.date() + timedelta(days=3)).isoformat()
    app, client = app_at(tmp_path, LATER)
    with client:
        fingerprint = client.get("/api/settings").json()["fingerprint"]
        added = client.post(
            "/api/ai/accounts",
            json={
                "name": "added",
                "adapter": next(a for a in ADAPTERS if a not in ("stub", "cli-agent")),
                "key_ref": "env:SHARED_KEY",
                "credential_expires": soon,
                "models": {"default": "m"},
                "fingerprint": fingerprint,
            },
        )
        assert added.status_code == 200, added.text
        [shown] = [a for a in client.get("/api/ai/accounts").json() if a["name"] == "added"]
        assert shown["key_ending"] is True


def test_putting_off_the_rules_review_runs_from_the_apps_moment(tmp_path):
    app, client = app_at(tmp_path, LATER)
    with client:
        put_off = client.post("/api/knowledge/rules/review/not-now")
        assert put_off.status_code == 200, put_off.text
        days = app.state.worker.cfg.dispatch.knowledge.rule_review_every_days
        assert datetime.fromisoformat(put_off.json()["until"]) == LATER + timedelta(days=days)


def test_open_items_count_the_days_untouched_up_to_the_apps_day(tmp_path):
    app, client = app_at(tmp_path, LATER)
    with client:
        owner = next(p.id for p in app.state.store.read().list("person"))
        with app.state.store.transaction() as tx:
            tx.create("action", {"text": "Send the interior file", "owners": [{"person": owner}]}, _PM)
        [found] = [a for a in client.get("/api/open-items").json()["actions"] if a["text"] == "Send the interior file"]
        assert found["state"] == "stale" and found["untouched_days"] > 365


def test_the_quality_window_ends_on_the_apps_day(tmp_path):
    app, client = app_at(tmp_path, LATER)
    with client:
        assert client.get("/api/quality").json()["until"] == LATER.date().isoformat()


def test_a_series_page_takes_the_meeting_the_apps_day_has_not_reached_as_next(tmp_path):
    app, client = app_at(tmp_path, EARLIER)
    with client:
        with app.state.store.transaction() as tx:
            sid = tx.create("series", {"title": "Print sync", "repeats": "every Thursday", "trust": "trusted"}, _PM).id
            start = (EARLIER.date() + timedelta(days=3)).isoformat()
            tx.create("event", {"title": "Print sync", "start": start, "series": sid, "trust": "trusted"}, _PM)
        found = client.get(f"/api/series/{sid}/page").json()
        assert found["next"] is not None and found["past"] == []


def test_an_ask_is_stamped_with_the_apps_moment(tmp_path):
    app, client = app_at(tmp_path, LATER)
    with client:
        made = client.post("/api/ask", json={"question": "What is due this week?"})
        assert made.status_code == 200, made.text
        request = app.state.store.read().get("request", made.json()["id"])
        assert datetime.fromisoformat(request.data["created_at"]) == LATER
