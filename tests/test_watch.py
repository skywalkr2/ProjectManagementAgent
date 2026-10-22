"""Watchers (design 6.4): a source is read through its connector, compared with what was seen, and each real
difference is handed in as outside content; a first read only notes what is there; failures ask once; plugins add
connectors."""

from datetime import UTC, datetime, timedelta

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)


def make(tmp_path, sources, **watch):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({"version": 1, "sources": sources, **watch}))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


@pytest.fixture
def folder_source(tmp_path):
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "plan.md").write_text("Line one\nLine two\n")
    ws, cfg, store = make(
        tmp_path,
        [
            {
                "id": "shared",
                "connector": "folder",
                "label": "Shared notes",
                "first_run": "baseline",
                "settings": {"path": str(folder)},
            }
        ],
    )
    yield ws, cfg, store, folder
    store.close()


def source_text(ws, store, request_id):
    request = store.read().get("request", request_id)
    source = store.read().get("source", request.data["source"])
    return source, (ws.sources_dir / f"{source.data['content_hash']}.txt").read_text()


def test_the_first_read_only_notes_what_is_there(folder_source):
    from engine.watch import refresh

    ws, cfg, store, _ = folder_source
    result = refresh(ws, store, cfg, "shared", NOW)
    assert result.outcome == "baseline" and result.new == []
    assert [s.data["key"] for s in store.read().find("snapshot", {"source": "shared"})] == ["plan.md"]
    assert not [r for r in store.read().list("request") if r.data.get("origin") == "input"]


def test_new_changed_and_gone_items_are_handed_in_as_outside_content(folder_source):
    from engine.watch import refresh

    ws, cfg, store, folder = folder_source
    refresh(ws, store, cfg, "shared", NOW)
    (folder / "plan.md").write_text("Line one\nLine two, revised\n")
    (folder / "extra.txt").write_text("A new note")
    result = refresh(ws, store, cfg, "shared", NOW + timedelta(hours=1))
    assert len(result.new) == 1 and len(result.changed) == 1
    source, text = source_text(ws, store, result.changed[0])
    assert source.data["trust"] == "untrusted" and source.data["watched"]["change"] == "changed"
    assert "-Line two" in text and "+Line two, revised" in text and "It now reads:" in text
    request = store.read().get("request", result.new[0])
    assert request.data["origin"] == "input" and request.data["state"] == "queued"
    assert source_text(ws, store, result.new[0])[1].startswith("New in Shared notes: extra.txt")
    (folder / "extra.txt").unlink()
    gone = refresh(ws, store, cfg, "shared", NOW + timedelta(hours=2))
    assert len(gone.removed) == 1 and "no longer in Shared notes" in source_text(ws, store, gone.removed[0])[1]
    assert refresh(ws, store, cfg, "shared", NOW + timedelta(hours=3)).new == []


def test_first_run_all_hands_in_everything(tmp_path):
    from engine.watch import refresh

    items = [{"key": "a", "title": "A", "text": "first"}, {"key": "b", "title": "B", "text": "second"}]
    ws, cfg, store = make(
        tmp_path, [{"id": "s", "connector": "fake", "first_run": "all", "settings": {"items": items}}]
    )
    try:
        assert len(refresh(ws, store, cfg, "s", NOW).new) == 2
    finally:
        store.close()


def test_failures_ask_once_and_a_good_read_ends_the_question(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [{"id": "s", "connector": "fake", "label": "Board", "settings": {"error": "auth"}}],
        failures_before_asking=2,
    )
    try:
        pm = cfg.workspace.user.person
        assert pm, "the demo workspace names the PM"
        first = refresh(ws, store, cfg, "s", NOW)
        assert first.outcome == "failed" and "Sign in" in first.problem
        refresh(ws, store, cfg, "s", NOW + timedelta(hours=1))
        refresh(ws, store, cfg, "s", NOW + timedelta(hours=2))
        asked = [q for q in store.read().list("question") if (q.data.get("resolves") or {}).get("kind") == "watch"]
        assert len(asked) == 1 and asked[0].data["title"] == "Board can't be read"
        store.close()
        (ws.config_dir / "watch.yaml").write_text(
            yaml.safe_dump({"version": 1, "sources": [{"id": "s", "connector": "fake", "label": "Board"}]})
        )
        from engine.storage import Store

        cfg = load_config(ws.config_dir, env={})
        store = Store(ws.db_path, cfg=cfg)
        assert refresh(ws, store, cfg, "s", NOW + timedelta(hours=3)).outcome == "baseline"
        assert store.read().get("question", asked[0].id).data["status"] == "dropped"
    finally:
        store.close()


def test_no_network_is_not_a_failure(tmp_path):
    from engine.watch import failures_in_a_row, refresh

    ws, cfg, store = make(tmp_path, [{"id": "s", "connector": "fake", "settings": {"error": "offline"}}])
    try:
        assert refresh(ws, store, cfg, "s", NOW).outcome == "offline"
        assert failures_in_a_row(store, "s") == 0
    finally:
        store.close()


def test_bad_settings_and_unknown_connectors_fail_with_the_reason(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [
            {"id": "bad", "connector": "folder", "settings": {"nothing": 1}},
            {"id": "none", "connector": "nobody/here"},
        ],
    )
    try:
        assert "settings don't fit" in refresh(ws, store, cfg, "bad", NOW).problem
        missing = refresh(ws, store, cfg, "none", NOW).problem
        assert (
            'add-on "nobody" that reads it isn\'t installed here' in missing and "Change, on Connections" not in missing
        )
    finally:
        store.close()


def test_a_source_whose_add_on_is_off_or_stopped_says_which_and_what_to_do(tmp_path):
    from types import SimpleNamespace

    from engine.watch import missing_connector

    ws, cfg, store = make(tmp_path, [])
    try:
        store.plugins.candidates["mailer"] = tmp_path / "plugin.yaml"
        assert "is turned off. Turn it on in Add-ons" in missing_connector(store, cfg, "mailer/calendar")
        cfg.workspace.plugins.enabled.append("mailer")
        store.plugins.status["mailer"] = SimpleNamespace(state="disabled", reason="it needs a newer app")
        assert "stopped (it needs a newer app)" in missing_connector(store, cfg, "mailer/calendar")
        store.plugins.status["mailer"] = SimpleNamespace(state="loaded", reason=None)
        assert "doesn't read this kind of connection" in missing_connector(store, cfg, "mailer/calendar")
        assert "no way to read it" in missing_connector(store, cfg, "folder-gone")
    finally:
        store.plugins.candidates.pop("mailer", None)
        store.plugins.status.pop("mailer", None)
        store.close()


PLUGIN = """
from typing import ClassVar
from pydantic import BaseModel
from engine.plugin_api import Poll, Settings, SourceItem

class Config(Settings):
    pass

class BoardSettings(BaseModel):
    board: str
    crash: bool = False

def poll(settings, state, context):
    if settings.crash:
        raise RuntimeError("broken")
    return Poll([SourceItem("card-1", "Card one", "Board " + settings.board)], {"seen": 1})

def register(registrar):
    registrar.connector("p19/board", label="A board", settings=BoardSettings, poll=poll)
"""


def plugin_workspace(tmp_path, crash=False):
    from engine.storage import Store

    ws, cfg, store = make(
        tmp_path,
        [{"id": "b", "connector": "p19/board", "first_run": "all", "settings": {"board": "x", "crash": crash}}],
    )
    store.close()
    folder = ws.root / "plugins" / "p19"
    folder.mkdir(parents=True)
    (folder / "fixture.py").write_text(PLUGIN)
    manifest = {
        "name": "p19",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Connector fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"connectors": ["p19/board"]},
    }
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p19"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p19"), store.plugins.status["p19"].reason
    return ws, cfg, store


def test_a_plugin_adds_a_connector(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = plugin_workspace(tmp_path)
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert len(result.new) == 1 and "Board x" in source_text(ws, store, result.new[0])[1]
        assert store.read().find("watch_run", {"source": "b"})[-1].data["state"] == {"seen": 1}
    finally:
        store.close()


def test_a_crashing_connector_is_contained(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = plugin_workspace(tmp_path, crash=True)
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert result.outcome == "failed" and store.plugins.active("p19")
        assert "connector p19/board failed" in store.plugins.status["p19"].notes[-1]
    finally:
        store.close()


def test_the_worker_reads_due_sources_and_the_route_shows_them(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app

    items = [{"key": "a", "title": "A", "text": "first"}]
    ws, cfg, store = make(tmp_path, [{"id": "s", "connector": "fake", "label": "Board", "settings": {"items": items}}])
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    assert app.state.worker.run_due_watches() == 1 and app.state.worker.run_due_watches() == 0
    listed = c.get(f"{api}/watch").json()
    assert listed[0]["label"] == "Board" and listed[0]["last"]["outcome"] == "baseline" and listed[0]["items"] == 1
    assert c.post(f"{api}/watch/s/read").json()["last"]["outcome"] == "ok"
    assert c.post(f"{api}/watch/nothing/read").status_code == 404


# ---- triage and folding ----------------------------------------------------------------------------------------------


def fake(items):
    return {"id": "s", "connector": "fake", "label": "Board", "first_run": "all", "settings": {"items": items}}


def reread(tmp_path, ws, store, items, **watch):
    """Change what the stand-in source holds and read it again."""
    from engine.storage import Store
    from engine.watch import refresh

    store.close()
    current = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    current["sources"] = [fake(items)]
    current.update(watch)
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(current))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    return cfg, store, refresh(ws, store, cfg, "s", NOW + timedelta(hours=len(store.read().list("watch_run"))))


RULES = [
    {"name": "Spacing", "kind": "cosmetic", "why": "Closed: {reason}."},
    {"name": "Ours", "kind": "by-us"},
    {"name": "Scratch", "kind": "name-matches", "params": {"patterns": ["*.tmp"]}},
    {"name": "Budget only", "kind": "terms-absent", "params": {"terms": ["budget"]}, "sources": ["s"]},
]


def test_triage_rules_close_changes_with_a_reason(tmp_path):
    from engine.watch import refresh

    items = [{"key": "a", "title": "Plan", "text": "The budget is ten.\nLunch at noon."}]
    ws, cfg, store = make(tmp_path, [fake(items)], triage=RULES)
    try:
        assert len(refresh(ws, store, cfg, "s", NOW).new) == 1
        cfg, store, spaced = reread(tmp_path, ws, store, [{**items[0], "text": "The budget  is ten\nLunch at noon."}])
        closed = store.read().get("request", spaced.changed[0])
        assert closed.data["state"] == "done" and closed.data["auto_closed"]["rule"] == "Spacing"
        assert closed.data["waiting"].startswith("Closed by Spacing: Closed: only spacing")
        cfg, store, other = reread(tmp_path, ws, store, [{**items[0], "text": "The budget  is ten\nLunch at one."}])
        assert store.read().get("request", other.changed[0]).data["auto_closed"]["rule"] == "Budget only"
        cfg, store, real = reread(tmp_path, ws, store, [{**items[0], "text": "The budget is twelve.\nLunch at one."}])
        assert store.read().get("request", real.changed[0]).data["state"] == "queued"
    finally:
        store.close()


def test_changes_by_our_own_accounts_and_scratch_files_are_closed(tmp_path):
    from engine.storage import Store
    from engine.watch import refresh

    items = [
        {"key": "x.tmp", "title": "x.tmp", "text": "scratch"},
        {"key": "b", "title": "Notes", "text": "Mine, the budget", "author": "Cockpit assistant"},
    ]
    ws, cfg, store = make(tmp_path, [fake(items)], triage=RULES)
    store.close()
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["our_accounts"] = ["Cockpit Assistant"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        result = refresh(ws, store, cfg, "s", NOW)
        rules = sorted(store.read().get("request", r).data["auto_closed"]["rule"] for r in result.new)
        assert rules == ["Ours", "Scratch"]
        mine = next(
            store.read().get("request", r) for r in result.new if "Ours" in str(store.read().get("request", r).data)
        )
        assert store.read().get("source", mine.data["source"]).data["watched"]["by_us"]
    finally:
        store.close()


def my_id():
    """The person running the fictional workspace, from its settings."""
    return load_config(DEMO_B / "config", env={}).workspace.user.person


def watched_of(tmp_path, items, *, source=None, accounts=None, ours=None):
    """Read a source once and return the `watched` marks of each item it handed in, by item key, with the packet each
    was given, under the named accounts. `source` adds to the source's own entry."""
    from engine.packet import build
    from engine.storage import Store
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [{**fake(items), **(source or {})}])
    store.close()
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["our_accounts"] = ours or []
    settings["user"]["accounts"] = accounts or []
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        found = {}
        for request_id in refresh(ws, store, cfg, "s", NOW).new:
            record = store.read().get("source", store.read().get("request", request_id).data["source"])
            packet = build(ws, store, cfg, request_id, NOW.date()).task.request
            found[record.data["watched"]["key"]] = (record.data["watched"], packet)
        return cfg, found
    finally:
        store.close()


def test_a_source_that_names_the_person_as_its_author_holds_their_own_work(tmp_path):
    items = [{"key": "a", "title": "Plan", "text": "First line.", "author": "someone else"}]
    me = my_id()
    _, found = watched_of(tmp_path, items, source={"author": me})
    marks, packet = found["a"]
    assert marks["by_you"] and not marks["by_us"] and marks["credited_to"] == me
    assert ' author="you"' in packet and "by_us" not in packet


def test_a_change_made_under_one_of_the_persons_names_is_theirs_and_the_apps_own_names_are_kept_apart(tmp_path):
    items = [
        {"key": "mine", "title": "Mine", "text": "One.", "author": "Casey  Example"},
        {"key": "app", "title": "Published", "text": "Two.", "author": "Cockpit Assistant"},
        {"key": "both", "title": "Both", "text": "Three.", "author": "Shared Name"},
        {"key": "other", "title": "Other", "text": "Four.", "author": "A Colleague"},
    ]
    _, found = watched_of(
        tmp_path, items, accounts=["casey example", "Shared Name"], ours=["Cockpit Assistant", "Shared Name"]
    )
    flags = {key: (marks["by_you"], marks["by_us"]) for key, (marks, _) in found.items()}
    assert flags == {"mine": (True, False), "app": (False, True), "both": (True, False), "other": (False, False)}
    assert ' author="you"' in found["mine"][1] and 'by_us="yes"' not in found["mine"][1]
    assert 'by_us="yes"' in found["app"][1] and 'author="you"' not in found["app"][1]
    assert "author=" not in found["other"][1] and "by_us" not in found["other"][1]


def test_a_source_that_names_a_colleague_or_a_team_credits_its_changes_to_them_by_name(tmp_path):
    from tests.conftest import fixture_records

    person = next(p for p in fixture_records(DEMO_B, "person") if p["id"] != my_id())
    team = fixture_records(DEMO_B, "team")[0]
    items = [{"key": "a", "title": "Plan", "text": "First line.", "author": "any"}]
    for owner, name in ((person["id"], person["full_name"]), (team["id"], team["name"])):
        _, found = watched_of(tmp_path / owner, items, source={"author": owner})
        marks, packet = found["a"]
        assert not marks["by_you"] and marks["credited_to"] == owner
        assert f' author="{name}"' in packet


def test_a_source_names_no_author_by_default(tmp_path):
    items = [{"key": "a", "title": "Plan", "text": "First line."}]
    _, found = watched_of(tmp_path, items)
    marks, packet = found["a"]
    assert marks["credited_to"] is None and not marks["by_you"] and "author=" not in packet


def test_a_newer_change_folds_in_the_older_one_still_waiting(tmp_path):
    from engine.watch import refresh

    items = [{"key": "a", "title": "Plan", "text": "First."}]
    ws, cfg, store = make(tmp_path, [fake(items)])
    try:
        first = refresh(ws, store, cfg, "s", NOW).new[0]
        cfg, store, second = reread(tmp_path, ws, store, [{**items[0], "text": "Second."}])
        newer = second.changed[0]
        older = store.read().get("request", first).data
        assert older["state"] == "done" and older["folded_into"] == newer
        text = source_text(ws, store, newer)[1]
        assert text.index("New in Board: Plan") < text.index("Then:") < text.index("+Second.")
    finally:
        store.close()


def test_a_closed_change_can_be_taken_a_closer_look_at(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine.watch import refresh

    items = [{"key": "a", "title": "Plan", "text": "One budget."}]
    ws, cfg, store = make(tmp_path, [fake(items)], triage=RULES)
    refresh(ws, store, cfg, "s", NOW)
    cfg, store, spaced = reread(tmp_path, ws, store, [{**items[0], "text": "One  budget"}])
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    listed = c.get(f"{api}/auto-closed").json()
    assert listed[0]["rule"] == "Spacing" and listed[0]["source"] == "Board" and listed[0]["change"] == "changed"
    done = c.post(f"{api}/requests/{listed[0]['id']}/closer-look", json={"read_version": listed[0]["version"]})
    assert done.status_code == 200, done.text
    assert c.get(f"{api}/auto-closed").json() == []
    from engine.storage import Store

    again = Store(ws.db_path)
    try:
        request = again.read().get("request", listed[0]["id"]).data
        assert request["state"] == "queued" and request["auto_closed"] is None
        assert again.read().list("signal")[-1].data["kind"] == "pulled_back"
    finally:
        again.close()


MATCHER_PLUGIN = PLUGIN.replace(
    "def register(registrar):\n",
    "def never_mind(change, params):\n"
    "    if params.get('crash'):\n"
    "        raise RuntimeError('broken')\n"
    "    return 'it is a card' if change['key'].startswith('card') else None\n\n"
    "def register(registrar):\n"
    '    registrar.triage_matcher("p19/cards", match=never_mind)\n',
)


def test_a_plugin_adds_a_triage_matcher_and_a_crash_counts_as_no_match(tmp_path, caplog):
    from engine.storage import Store
    from engine.watch import refresh

    ws, cfg, store = plugin_workspace(tmp_path)
    store.close()
    (ws.root / "plugins" / "p19" / "fixture.py").write_text(MATCHER_PLUGIN)
    manifest_path = ws.root / "plugins" / "p19" / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["provides"]["triage_matchers"] = ["p19/cards"]
    manifest_path.write_text(yaml.safe_dump(manifest))
    watch = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    watch["triage"] = [
        {"name": "Crashing", "kind": "p19/cards", "params": {"crash": True}},
        {"name": "Cards", "kind": "p19/cards"},
    ]
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(watch))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert store.read().get("request", result.new[0]).data["auto_closed"] == {
            "rule": "Cards",
            "reason": "it is a card",
        }
        assert "triage matcher p19/cards failed: broken" in caplog.text and store.plugins.active("p19")
    finally:
        store.close()


def test_a_source_already_being_read_is_not_read_twice(tmp_path, monkeypatch):
    import threading

    from engine import watch

    items = [{"key": "a", "title": "A", "text": "first"}]
    ws, cfg, store = make(
        tmp_path, [{"id": "s", "connector": "fake", "first_run": "all", "settings": {"items": items}}]
    )
    inside, release = threading.Event(), threading.Event()
    real_poll = watch._poll

    def slow_poll(*args):
        inside.set()
        assert release.wait(timeout=10)
        return real_poll(*args)

    monkeypatch.setattr(watch, "_poll", slow_poll)
    first = []
    try:
        thread = threading.Thread(target=lambda: first.append(watch.refresh(ws, store, cfg, "s", NOW)))
        thread.start()
        assert inside.wait(timeout=10)
        second = watch.refresh(ws, store, cfg, "s", NOW)
        assert second.outcome == "busy" and second.note == watch.ALREADY_READING and second.new == []
        assert not store.read().find("watch_run", {"source": "s"})  # the skipped read left no run behind
        release.set()
        thread.join(timeout=10)
        assert first[0].outcome == "ok" and len(first[0].new) == 1
        handed = [r for r in store.read().list("request") if r.data.get("origin") == "input"]
        assert len(handed) == 1  # the item was handed in once
        monkeypatch.setattr(watch, "_poll", real_poll)
        assert watch.refresh(ws, store, cfg, "s", NOW + timedelta(hours=1)).outcome == "ok"  # the lock was let go
    finally:
        release.set()
        store.close()


def test_a_read_that_fails_lets_the_lock_go(tmp_path):
    from engine import watch

    ws, cfg, store = make(tmp_path, [{"id": "s", "connector": "fake", "settings": {"error": "auth"}}])
    try:
        assert watch.refresh(ws, store, cfg, "s", NOW).outcome == "failed"
        assert watch.refresh(ws, store, cfg, "s", NOW + timedelta(hours=1)).outcome == "failed"
    finally:
        store.close()


def test_the_read_now_route_leaves_a_source_being_read_alone(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine import watch

    items = [{"key": "a", "title": "A", "text": "first"}]
    ws, cfg, store = make(
        tmp_path, [{"id": "s", "connector": "fake", "first_run": "all", "settings": {"items": items}}]
    )
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    lock = watch._read_lock(ws, "s")
    assert lock.acquire(blocking=False)
    try:
        assert c.post(f"{api}/watch/s/read").status_code == 200
        assert c.get(f"{api}/watch").json()[0]["last"] is None  # nothing was read while it was held
    finally:
        lock.release()
    assert c.post(f"{api}/watch/s/read").status_code == 200
    assert c.get(f"{api}/watch").json()[0]["last"]["outcome"] == "ok"


def test_the_test_only_kind_is_not_offered_but_a_source_set_up_with_it_still_reads_and_shows(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine.connectors import CORE
    from engine.watch import refresh

    items = [{"key": "a", "title": "A", "text": "first"}]
    ws, cfg, store = make(
        tmp_path, [{"id": "s", "connector": "fake", "first_run": "all", "settings": {"items": items}}]
    )
    try:
        stand_in = CORE["fake"]
        assert stand_in.test_only
        assert len(refresh(ws, store, cfg, "s", NOW).new) == 1
    finally:
        store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    kinds = c.get(f"{api}/watch/kinds").json()
    assert stand_in.name not in {k["name"] for k in kinds} and stand_in.label not in {k["label"] for k in kinds}
    assert {k["name"] for k in kinds} >= {name for name, kind in CORE.items() if not kind.test_only}
    shown = c.get(f"{api}/watch").json()
    assert [(s["id"], s["connector"], s["connector_label"]) for s in shown] == [("s", stand_in.name, stand_in.label)]


def unread_lines(ws, store, cfg, now):
    from engine.today_queue import queue

    return [line for line in queue(ws, store, cfg, now) if line.kind == "source_unread"]


def test_a_source_failing_longer_than_its_gap_is_a_line_for_the_person(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [{"id": "s", "connector": "fake", "label": "Board", "every_minutes": 30, "settings": {"error": "auth"}}],
    )
    try:
        assert cfg.watch.unread_gap_factor == 2
        refresh(ws, store, cfg, "s", NOW)
        assert unread_lines(ws, store, cfg, NOW + timedelta(minutes=59)) == []  # within twice its own gap
        (line,) = unread_lines(ws, store, cfg, NOW + timedelta(minutes=61))
        assert (line.group, line.source, line.subject, line.problem_kind) == ("risk", "s", "Board", "auth")
        assert "Sign in" in (line.text or "")  # what went wrong and what to do, as the source's problem says it
        assert datetime.fromisoformat(line.waiting_since) == NOW  # never read: since its first try
    finally:
        store.close()


def test_the_gap_factor_is_a_setting_and_a_good_read_ends_the_line(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [{"id": "s", "connector": "fake", "label": "Board", "every_minutes": 30, "settings": {"error": "auth"}}],
        unread_gap_factor=1,
    )
    try:
        refresh(ws, store, cfg, "s", NOW)
        assert unread_lines(ws, store, cfg, NOW + timedelta(minutes=29)) == []
        assert len(unread_lines(ws, store, cfg, NOW + timedelta(minutes=31))) == 1
        store.close()
        (ws.config_dir / "watch.yaml").write_text(
            yaml.safe_dump({"version": 1, "sources": [{"id": "s", "connector": "fake", "label": "Board"}]})
        )
        from engine.storage import Store

        cfg = load_config(ws.config_dir, env={})
        store = Store(ws.db_path, cfg=cfg)
        assert refresh(ws, store, cfg, "s", NOW + timedelta(hours=2)).outcome == "baseline"
        assert unread_lines(ws, store, cfg, NOW + timedelta(hours=2)) == []
    finally:
        store.close()


def test_no_network_and_a_turned_off_source_are_not_a_line_and_one_line_stands_in_for_the_question(tmp_path):
    from engine.today_queue import queue
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [
            {"id": "away", "connector": "fake", "label": "Away", "every_minutes": 30, "settings": {"error": "offline"}},
            {
                "id": "off",
                "connector": "fake",
                "label": "Off",
                "enabled": False,
                "every_minutes": 30,
                "settings": {"error": "auth"},
            },
            {"id": "s", "connector": "fake", "label": "Board", "every_minutes": 30, "settings": {"error": "auth"}},
        ],
        failures_before_asking=2,
    )
    try:
        for source in ("away", "s"):
            for hours in (0, 1, 2):
                refresh(ws, store, cfg, source, NOW + timedelta(hours=hours))
        asked = [q for q in store.read().list("question") if (q.data.get("resolves") or {}).get("kind") == "watch"]
        assert len(asked) == 1  # the question is filed, and Today shows the one line for that source instead of it
        now = NOW + timedelta(hours=3)
        lines = queue(ws, store, cfg, now)
        assert [line.source for line in lines if line.kind == "source_unread"] == ["s"]
        assert not [line for line in lines if line.question == asked[0].id]
    finally:
        store.close()


def test_the_line_for_an_unread_source_is_served_on_the_queue(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine.watch import refresh

    ws, cfg, store = make(
        tmp_path,
        [{"id": "s", "connector": "fake", "label": "Board", "every_minutes": 30, "settings": {"error": "auth"}}],
    )
    try:
        refresh(ws, store, cfg, "s", datetime.now(UTC) - timedelta(hours=3))
    finally:
        store.close()
    client = TestClient(create_app(ws, cfg, "t", start_worker=False), headers={"Authorization": "Bearer t"})
    (line,) = [
        line
        for line in client.get(cfg.server.base_path.rstrip("/") + "/api/today/queue").json()
        if line["kind"] == "source_unread"
    ]
    assert (line["group"], line["source"], line["subject"], line["problem_kind"]) == ("risk", "s", "Board", "auth")
    assert line["waiting_since"] and "Sign in" in line["text"]


def test_a_source_not_read_successfully_within_the_stale_hours_is_named_by_when_it_was_last_read(tmp_path):
    from engine.watch import refresh, stale_since

    ws, cfg, store = make(
        tmp_path,
        [
            {"id": "read", "connector": "fake", "label": "Work mailbox", "every_minutes": 30},
            {
                "id": "failing",
                "connector": "fake",
                "label": "Board",
                "every_minutes": 30,
                "settings": {"error": "auth"},
            },
            {"id": "never", "connector": "fake", "label": "Archive", "every_minutes": 30, "enabled": False},
        ],
        stale_after_hours=6,
    )
    try:
        refresh(ws, store, cfg, "read", NOW)
        refresh(ws, store, cfg, "failing", NOW)
        by_id = {s.id: s for s in cfg.watch.sources}
        within = NOW + timedelta(hours=cfg.watch.stale_after_hours)
        after = within + timedelta(minutes=1)
        assert stale_since(store, cfg, by_id["read"], within) is None, "exactly the hours is not more than them"
        assert stale_since(store, cfg, by_id["read"], after) == str(
            store.read().find("watch_run", {"source": "read"})[-1].data["started_at"]
        )
        assert stale_since(store, cfg, by_id["failing"], after) is None, "never read: not read yet, a state of its own"
        assert stale_since(store, cfg, by_id["never"], after) is None, "turned off"
        refresh(ws, store, cfg, "read", after)
        assert stale_since(store, cfg, by_id["read"], after) is None, "a good read ends it"
    finally:
        store.close()
