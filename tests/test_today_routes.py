"""Top priorities and This week through the API: the shapes the screen reads (design 7.7). The ranking and the week
have their own engine tests (`tests/test_top_priorities.py`, `tests/test_this_week.py`)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine.storage import WriteContext
from engine.today import zone
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "today-routes-token"
_TEST = WriteContext(actor="pm", trust="trusted", op="test.today-routes")


@pytest.fixture
def api(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__UI__TODAY__TOP_PRIORITIES_LINES": "50"}, flags={"server.base_path": "/"})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, "/api", app.state.store, cfg, app.state.worker


def test_an_overdue_to_do_comes_with_what_mark_done_and_reassign_need(api):
    client, base, store, cfg, worker = api
    today = worker.now().astimezone(zone(cfg)).date()
    with store.transaction() as tx:
        made = tx.create(
            "action",
            {
                "text": "Send the proofs",
                "owners": [{"person": cfg.workspace.user.person}],
                "due": (today - timedelta(days=2)).isoformat(),
            },
            _TEST,
        )
    found = client.get(f"{base}/today/priorities").json()
    line = next(x for x in found["lines"] if x["action"] == made.id)
    assert line["rank"] == "overdue" and line["kind"] == "action" and line["text"] == "Send the proofs"
    assert line["version"] == made.version and [o["person"] for o in line["owners"]] == [cfg.workspace.user.person]
    assert line["owners"][0]["name"] and line["person_name"]
    assert set(found) == {"lines", "more", "blocked", "coming"}


def test_top_priorities_counts_what_is_blocked(api):
    client, base, _, _, _ = api
    assert client.get(f"{base}/today/priorities").json()["blocked"] == 0


def test_this_week_names_its_days_and_what_is_due_in_it(api):
    client, base, store, cfg, worker = api
    today = worker.now().astimezone(zone(cfg)).date()
    with store.transaction() as tx:
        tx.create(
            "action",
            {"text": "Send it today", "owners": [{"person": cfg.workspace.user.person}], "due": today.isoformat()},
            _TEST,
        )
    week = client.get(f"{base}/today/week").json()
    assert week["first"] <= week["last"] and set(week) == {"first", "last", "due", "waiting", "meetings"}
    assert any(d["text"] == "Send it today" and d["mine"] for d in week["due"])
