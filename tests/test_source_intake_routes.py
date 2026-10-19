"""The routes of a newly added source's intake (design 6.32): the one go, the list marked seen with Undo, the preview
and the look further back, what the sources list says about how far back a source was looked, and what the changes
list and Today show. Names come from the fixtures; the AI is the stub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from tests.test_source_intake import item, mail, make, requests_of, with_changeset

TOKEN = "intake-token"


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def api(tmp_path):
    """A workspace with a mail source of new, middle-aged and old mail and a page, over the amount to confirm."""
    at = now()
    items = [mail("new", 2, now=at), mail("a", 20, now=at), mail("c", 150, now=at), item("page", now=at)]
    ws, cfg, store = make(tmp_path, items, confirm=0.0, price=1000.0)  # a price that rounds to more than nothing
    store.close()
    application = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, application.state.store, ws, cfg


def read(client):
    return client.post("/api/watch/m/read")


def kinds(client, *wanted):
    return [x for x in client.get("/api/today/queue").json() if x["kind"] in wanted]


def test_the_first_read_shows_the_look_back_date_and_the_choices_on_the_source(api):
    client, store, ws, cfg = api
    before = client.get("/api/watch").json()[0]
    assert before["looked_back_to"] is None and before["look_back_choices"] == []
    assert read(client).status_code == 200
    (shown,) = client.get("/api/watch").json()
    assert shown["looked_back_to"] == (now() - timedelta(days=14)).date().isoformat()
    assert shown["look_back_choices"] == [30, 90, 365]


def test_the_intake_is_one_line_on_today_and_the_changes_list_has_none_of_the_held_requests(api):
    client, store, ws, cfg = api
    read(client)
    (line,) = kinds(client, "intake_go")
    assert (line["group"], line["source"], line["subject"], line["count"], line["days"]) == (
        "decide",
        "m",
        "Inbox",
        2,
        14,
    )
    assert line["estimate_usd"] > 0 and line["unpriced"] == 0
    assert not [c for c in client.get("/api/changes").json() if c["state"] == "needs_you"]


def test_the_go_route_starts_them_all_once(api):
    client, store, ws, cfg = api
    read(client)
    assert client.post("/api/watch/m/intake/go").json() == {"started": 2}
    assert client.post("/api/watch/m/intake/go").json() == {"started": 0}
    assert kinds(client, "intake_go") == []
    changes = [c for c in client.get("/api/changes").json() if c["intake"] == "m"]
    assert len(changes) == 2 and {c["state"] for c in changes} == {"queued"}
    assert client.post("/api/watch/nobody/intake/go").status_code == 404


def test_opening_the_list_marks_it_seen_and_undo_gives_the_line_back(api):
    client, store, ws, cfg = api
    read(client)
    client.post("/api/watch/m/intake/go")
    for r in requests_of(store, intake="m"):
        with_changeset(store, r.id, [("action.add", "applied")])
    (line,) = kinds(client, "intake_review")
    assert (line["group"], line["subject"], line["count"], line["outcome"]) == (
        "review",
        "Inbox",
        2,
        {"actions_added": 2},
    )
    assert kinds(client, "review") == []
    seen = client.post("/api/watch/m/intake/seen").json()
    assert len(seen["requests"]) == 2
    assert kinds(client, "intake_review") == [] and len(kinds(client, "review")) == 2
    assert client.post("/api/watch/m/intake/seen").json() == {"requests": []}
    assert client.post("/api/watch/m/intake/unseen", json=seen).json() == {"restored": 2}
    assert len(kinds(client, "intake_review")) == 1 and kinds(client, "review") == []


def test_the_preview_counts_and_prices_and_the_look_back_takes_in_the_older_mail_and_moves_the_date(api):
    client, store, ws, cfg = api
    read(client)
    before = len(client.get("/api/changes").json())
    preview = client.get("/api/watch/m/look-back", params={"days": 30}).json()
    assert (preview["count"], preview["reaches"], preview["available_from"]) == (1, True, None)
    assert preview["estimate_usd"] > 0
    assert len(client.get("/api/changes").json()) == before, "the preview writes nothing"
    ninety = client.get("/api/watch/m/look-back", params={"days": 90}).json()
    assert ninety["count"] == 1
    year = client.get("/api/watch/m/look-back", params={"days": 365}).json()
    assert year["count"] == 2 and year["estimate_usd"] > ninety["estimate_usd"]
    # The mail starts 150 days back, so a year can't be reached and the answer says where it does start.
    assert (year["reaches"], year["available_from"]) == (False, (now() - timedelta(days=150)).date().isoformat())
    done = client.post("/api/watch/m/look-back", json={"days": 90}).json()
    assert (done["taken"], done["started"], done["reaches"]) == (1, False, True)  # over the amount to confirm: held
    (line,) = kinds(client, "intake_go")
    assert line["count"] == 3, "one line for the source, with what was already waiting"
    (shown,) = client.get("/api/watch").json()
    assert shown["looked_back_to"] == (now() - timedelta(days=14 + 90)).date().isoformat()
    assert client.post("/api/watch/m/intake/go").json() == {"started": 3}


def test_a_choice_that_is_not_in_the_list_and_a_source_with_no_mail_are_refused(api):
    client, store, ws, cfg = api
    read(client)
    assert client.get("/api/watch/m/look-back", params={"days": 45}).status_code == 409
    assert client.post("/api/watch/m/look-back", json={"days": 45}).status_code == 409
    assert client.get("/api/watch/nobody/look-back", params={"days": 30}).status_code == 404
