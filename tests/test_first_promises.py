"""The walkthrough's first result (design 7.8): after the mail step, the walkthrough offers to look back over the last
`first_run_days` of mail with its estimate first, and after the person's go it shows a handful of the open promises
found with one follow-up ready to copy. The screens that ask about projects, packs or more accounts come after it.
Names and ids come from the fixtures; the AI is the stub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import first_promises, setup
from engine.config.schema import WatchSource
from engine.names import People
from engine.storage import WriteContext
from tests.conftest import DEMO_B, fixture_records
from tests.test_calendar_mail import N
from tests.test_source_intake import NOW, mail, make, read, requests_of, with_changeset

TOKEN = "first-promises-token"
_TEST = WriteContext(actor="pm", trust="trusted", op="test.first-promises")


@pytest.fixture(autouse=True)
def fake_reads_mail(monkeypatch):
    """The test source stands for a mailbox: it says it reads mail, as a connector's registration does."""
    real = first_promises.reads
    monkeypatch.setattr(first_promises, "reads", lambda c, said=None: ["mail"] if c == "fake" else real(c, said))


def other(cfg) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != cfg.workspace.user.person)


def promise(store, owner: str, text: str, due: str | None = None, **more) -> str:
    """An open action read as a promise (it says how it is known)."""
    data = {"text": text, "owners": [{"person": owner}], "due": due, "basis": "said", **more}
    if "evidence" in data:
        source = next(r.data["source"] for r in store.read().list("request") if r.data.get("intake"))
        data["evidence"] = {"source": source, **data["evidence"]}
    with store.transaction() as tx:
        return tx.create("action", data, _TEST).id


@pytest.fixture
def env(tmp_path):
    """A workspace with one source of mail over the amount to confirm, so its intake waits for the go."""
    ws, cfg, store = make(tmp_path, [mail("a", 2), mail("b", 5), mail("old", 30)], confirm=0.0, price=1000.0)
    yield ws, cfg, store
    store.close()


@pytest.fixture
def api(tmp_path):
    # The routes read the mailbox at the real time, so the mail's dates follow the real clock.
    today = datetime.now(UTC)
    items = [mail("a", 2, now=today), mail("b", 5, now=today), mail("old", 30, now=today)]
    ws, cfg, store = make(tmp_path, items, confirm=0.0, price=1000.0)
    store.close()
    application = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client, application.state.store, ws, cfg


def stage(env) -> first_promises.FirstPromises:
    ws, cfg, store = env
    return first_promises.view(ws, store, cfg, today=NOW.date())


# ---- the order of the screens ------------------------------------------------------------------------------


def test_the_first_result_comes_right_after_mail_and_before_the_screens_that_ask_about_more():
    order = list(setup.WALKTHROUGH_STEPS)
    assert order.index("mail") + 1 == order.index("promises") < order.index("backup") < order.index("people")
    assert order[-1] == "done"  # the extras (a starting template, add-ons) stay on the last screen


def test_the_screen_is_kept_and_resumed_like_any_other(api):
    client, *_ = api
    assert client.post("/api/setup/walkthrough", json={"step": "promises"}).json()["step"] == "promises"
    assert client.get("/api/setup").json()["walkthrough"]["step"] == "promises"


# ---- where it stands ---------------------------------------------------------------------------------------


def test_with_no_account_chosen_nothing_is_offered(env):
    ws, cfg, store = env
    for tier in cfg.ai.tiers.values():
        tier.use = None
    assert first_promises.where(ws, store, cfg).stage == "no_ai"


def test_with_nothing_connected_it_says_so(tmp_path):
    ws, cfg, store = make(tmp_path, [])
    try:
        cfg.watch.sources.clear()
        assert first_promises.where(ws, store, cfg).stage == "no_mail"
    finally:
        store.close()


def test_a_source_that_reads_neither_mail_nor_a_calendar_is_not_what_the_first_result_is_about(env, monkeypatch):
    ws, cfg, store = env
    monkeypatch.setattr(first_promises, "reads", lambda c, said=None: [])
    assert first_promises.where(ws, store, cfg).stage == "no_mail"


def test_before_the_first_read_it_is_reading(env):
    assert stage(env).stage == "reading"


def test_after_the_first_read_the_look_back_is_offered_with_what_it_would_cost_and_nothing_has_run(env):
    ws, cfg, store = env
    read(env)
    shown = stage(env)
    assert (shown.stage, shown.days, shown.count, shown.unpriced) == ("offer", 14, 2, 0)
    assert shown.sources == ["Inbox"] and shown.estimate_usd is not None and shown.estimate_usd > 0
    assert shown.promises == [] and shown.follow_up is None
    assert not store.read().list("run") or all(r.data.get("smoke") for r in store.read().list("run"))
    assert {r.data["state"] for r in requests_of(store, intake="m")} == {"needs_you"}


def test_the_go_starts_everything_the_offer_counted_once(env):
    ws, cfg, store = env
    read(env)
    assert first_promises.go(ws, store, cfg) == 2
    assert first_promises.go(ws, store, cfg) == 0
    assert {r.data["state"] for r in requests_of(store, intake="m")} == {"queued"}
    working = stage(env)
    assert (working.stage, working.count, working.finished) == ("working", 2, 0)


def test_while_some_requests_are_held_and_others_still_queued_it_is_working_not_a_part_of_the_offer(env):
    ws, cfg, store = env
    read(env)
    first, *_ = requests_of(store, intake="m")
    with store.transaction() as tx:
        tx.update(
            "request",
            first.id,
            {"state": "queued", "approval": None, "waiting": None},
            _TEST,
            read_version=tx.get("request", first.id).version,
        )
    assert stage(env).stage == "working"


def test_a_look_back_that_started_by_itself_but_waits_on_the_first_go_is_offered_and_the_go_covers_it(tmp_path):
    ws, cfg, store = make(tmp_path, [mail("a", 2)], confirm=100.0, price=1.0)
    try:
        read((ws, cfg, store))
        (held,) = requests_of(store, intake="m")
        with store.transaction() as tx:  # as the dispatcher holds a first run: no run has happened yet
            tx.update(
                "request",
                held.id,
                {"state": "needs_you", "approval": "required", "waiting": "Waiting for you to start the assistant."},
                _TEST,
                read_version=tx.get("request", held.id).version,
            )
        offer = first_promises.where(ws, store, cfg)
        assert (offer.stage, offer.count) == ("offer", 1)
        assert first_promises.go(ws, store, cfg) == 1
        assert requests_of(store, intake="m")[0].data["state"] == "queued"
    finally:
        store.close()


def test_when_every_request_has_finished_it_is_ready_with_the_promises_soonest_day_first(env):
    ws, cfg, store = env
    read(env)
    first_promises.go(ws, store, cfg)
    for r in requests_of(store, intake="m"):
        with_changeset(store, r.id, [("action.add", "applied")])
    me, they = cfg.workspace.user.person, other(cfg)
    undated = promise(store, they, "Send the floor plan")
    late = promise(store, me, "Book the room", "2026-11-09")
    soon = promise(store, they, "Confirm the headcount", "2026-11-02", promised_to=[me])
    plain = None
    with store.transaction() as tx:  # a plain to-do is not a promise
        plain = tx.create("action", {"text": "Water the plants", "owners": [{"person": me}]}, _TEST).id
    shown = stage(env)
    assert shown.stage == "ready"
    assert [p.action for p in shown.promises] == [soon, late, undated] and plain not in {
        p.action for p in shown.promises
    }
    assert shown.more == 0
    people = People(store, cfg)
    assert shown.promises[0].owner == people.owner({"person": they}) and not shown.promises[0].mine
    assert shown.promises[0].promised_to == [people.name(me)] and shown.promises[1].mine


def test_it_shows_only_as_many_as_the_setting_says_and_counts_the_rest(env):
    ws, cfg, store = env
    read(env)
    first_promises.go(ws, store, cfg)
    for r in requests_of(store, intake="m"):
        with_changeset(store, r.id, [("action.add", "applied")])
    they = other(cfg)
    ids = [promise(store, they, f"Task {n}", f"2026-11-0{n}") for n in range(1, 6)]
    cfg.ui.walkthrough.first_promises = 3
    shown = stage(env)
    assert [p.action for p in shown.promises] == ids[:3] and shown.more == 2


def test_the_setting_has_a_default_and_a_description():
    from engine.config.schema import WalkthroughSettings

    field = WalkthroughSettings.model_fields["first_promises"]
    assert field.get_default() == 5 and field.description


def test_one_follow_up_is_ready_for_someone_who_owes_something_shown(env):
    ws, cfg, store = env
    read(env)
    first_promises.go(ws, store, cfg)
    for r in requests_of(store, intake="m"):
        with_changeset(store, r.id, [("action.add", "applied")])
    me, they = cfg.workspace.user.person, other(cfg)
    promise(store, me, "Book the room", "2026-11-09")
    owed = promise(store, they, "Send the floor plan", "2026-11-02")
    shown = stage(env)
    assert shown.follow_up is not None and shown.follow_up.person == they
    people = People(store, cfg)
    assert shown.follow_up.name == people.name(they)
    assert "Send the floor plan" in shown.follow_up.message and shown.follow_up.to_send >= 1
    assert owed in {p.action for p in shown.promises}


def test_with_no_promises_it_is_ready_and_empty(env):
    ws, cfg, store = env
    read(env)
    first_promises.go(ws, store, cfg)
    for r in requests_of(store, intake="m"):
        with_changeset(store, r.id, [("note", "applied")])
    shown = stage(env)
    assert (shown.stage, shown.promises, shown.more, shown.follow_up) == ("ready", [], 0, None)


# ---- what is read: the account, the folders, the day, and what wasn't ----------------------------------------


def with_account(cfg, *, sent: dict | None = None) -> str:
    """The test source reads as the person's account; `sent` adds a second source that is the person's own sent mail."""
    account = cfg.workspace.user.accounts[0]
    cfg.watch.sources[0].account = account
    if sent is not None:
        cfg.watch.sources.append(
            WatchSource(
                id="s", connector="fake", label="Sent", account=account, author=cfg.workspace.user.person, settings=sent
            )
        )
    return account


def finish(env):
    """Every intake request has its result, as when the assistant has done the look back."""
    ws, cfg, store = env
    first_promises.go(ws, store, cfg)
    for r in requests_of(store, intake="m") + requests_of(store, intake="s"):
        with_changeset(store, r.id, [("note", "applied")])


def test_before_the_start_it_names_the_account_the_folders_and_the_day_the_read_goes_back_to(env):
    ws, cfg, store = env
    account = with_account(cfg, sent={"items": [mail("out", 3)]})
    from engine.watch import refresh

    read(env)
    refresh(ws, store, cfg, "s", NOW)
    shown = stage(env)
    assert shown.stage == "offer"
    (place,) = shown.coverage
    back = (NOW - timedelta(days=cfg.watch.sources[0].first_run_days)).date()
    assert (place.kind, place.account, place.missing_sent) == ("mail", account, False)
    assert [(f.source, f.name, f.sent, f.from_date) for f in place.folders] == [
        ("m", "Inbox", False, back),
        ("s", "Sent", True, back),
    ]
    assert shown.complete  # every source was read and the sent mail is among them


def test_the_day_it_goes_back_to_follows_the_sources_own_setting_even_before_it_is_first_read(env):
    ws, cfg, store = env
    cfg.watch.sources[0].first_run_days = 5
    shown = stage(env)
    assert shown.stage == "reading"
    (place,) = shown.coverage
    assert place.folders[0].from_date == NOW.date() - timedelta(days=5) and place.folders[0].outcome == "not_yet"
    assert not shown.complete


def test_a_source_whose_first_read_is_not_the_quiet_look_back_has_no_day(env):
    ws, cfg, store = env
    cfg.watch.sources[0].first_run = "baseline"
    assert stage(env).coverage[0].folders[0].from_date is None


def test_a_mailbox_is_named_by_its_user_and_its_folder(env):
    ws, cfg, store = env
    person = cfg.workspace.user.person
    box = WatchSource(
        id="box",
        connector="mailbox",
        label="Work mail",
        author=person,
        settings={"host": N["mail_host"], "user": N["mail_user"], "folder": "Sent Items"},
    )
    (place,) = first_promises._places(ws, store, cfg, [box], NOW.date())
    assert (place.kind, place.account, place.missing_sent) == ("mail", N["mail_user"], False)
    (folder,) = place.folders
    assert (folder.name, folder.folder, folder.sent) == ("Work mail", "Sent Items", True)


def test_after_a_read_with_one_folder_failed_that_folder_is_named_as_not_read_and_the_result_is_not_complete(env):
    ws, cfg, store = env
    with_account(cfg, sent={"error": "outage"})
    from engine.watch import refresh

    read(env)
    refresh(ws, store, cfg, "s", NOW)
    finish(env)
    shown = stage(env)
    assert shown.stage == "ready"
    (place,) = shown.coverage
    assert {f.name: f.outcome for f in place.folders} == {"Inbox": "read", "Sent": "failed"}
    assert not place.missing_sent  # a sent folder is set up; it just wasn't read
    assert not shown.complete


def test_a_folder_not_tried_yet_is_not_read_and_the_result_is_not_complete(env):
    ws, cfg, store = env
    with_account(cfg, sent={"items": [mail("out", 3)]})
    read(env)  # the sent source has not been read
    finish(env)
    shown = stage(env)
    assert {f.name: f.outcome for f in shown.coverage[0].folders} == {"Inbox": "read", "Sent": "not_yet"}
    assert not shown.complete


def test_a_mail_source_with_no_sent_folder_says_so_and_is_never_complete(env):
    ws, cfg, store = env
    account = with_account(cfg)
    read(env)
    finish(env)
    shown = stage(env)
    assert shown.stage == "ready"
    (place,) = shown.coverage
    assert (place.account, place.missing_sent) == (account, True)
    assert not shown.complete


def test_a_sent_folder_that_is_switched_off_counts_as_missing(env):
    ws, cfg, store = env
    with_account(cfg, sent={"items": []})
    cfg.watch.sources[1].enabled = False
    assert stage(env).coverage[0].missing_sent


def test_with_nothing_to_read_there_is_no_coverage(tmp_path):
    ws, cfg, store = make(tmp_path, [])
    try:
        cfg.watch.sources.clear()
        shown = first_promises.where(ws, store, cfg)
        assert shown.coverage == [] and not shown.complete
    finally:
        store.close()


# ---- the routes --------------------------------------------------------------------------------------------


def test_the_route_says_where_it_stands_and_its_go_starts_the_look_back_once(api):
    client, store, ws, cfg = api
    assert client.get("/api/setup/first-promises").json()["stage"] == "reading"
    assert client.post("/api/watch/m/read").status_code == 200
    offer = client.get("/api/setup/first-promises").json()
    assert (offer["stage"], offer["count"], offer["days"], offer["sources"]) == ("offer", 2, 14, ["Inbox"])
    assert offer["estimate_usd"] > 0 and offer["promises"] == [] and offer["follow_up"] is None
    (place,) = offer["coverage"]
    back = (datetime.now(UTC).date() - timedelta(days=14)).isoformat()
    assert (place["kind"], place["missing_sent"], offer["complete"]) == ("mail", True, False)
    assert [(f["name"], f["outcome"], f["sent"], f["from_date"]) for f in place["folders"]] == [
        ("Inbox", "read", False, back)
    ]
    assert client.post("/api/setup/first-promises/go").json() == {"started": 2}
    assert client.post("/api/setup/first-promises/go").json() == {"started": 0}
    assert client.get("/api/setup/first-promises").json()["stage"] == "working"
    # Today's line for the same go is gone: it was the same go.
    queue = client.get("/api/today/queue").json()
    assert not [x for x in queue if x["kind"] == "intake_go"]


def test_the_route_lists_the_promises_and_the_follow_up_when_the_work_is_done(api):
    client, store, ws, cfg = api
    client.post("/api/watch/m/read")
    client.post("/api/setup/first-promises/go")
    for r in requests_of(store, intake="m"):
        with_changeset(store, r.id, [("action.add", "applied")])
    they = other(cfg)
    due = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()
    owed = promise(store, they, "Send the floor plan", due, evidence={"quote": "I'll send the floor plan"})
    ready = client.get("/api/setup/first-promises").json()
    assert ready["stage"] == "ready" and ready["more"] == 0
    (one,) = ready["promises"]
    assert (one["action"], one["text"], one["due"], one["mine"], one["quote"]) == (
        owed,
        "Send the floor plan",
        due,
        False,
        "I'll send the floor plan",
    )
    assert ready["follow_up"]["person"] == they and "Send the floor plan" in ready["follow_up"]["message"]
    # Copying it is the Follow-ups screen's own route: it keeps the copy as copied.
    done = client.post(f"/api/followups/{they}/mark-sent", json={"text": ready["follow_up"]["message"]}).json()
    assert done["actions"] >= 1
    assert len(store.read().list("copy")) == 1
