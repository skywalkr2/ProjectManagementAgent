"""The new-start walkthrough (design 7.8): the server keeps where it stands (the screen the person is on, closed,
finished). It opens by itself on every visit while naming yourself or choosing an AI account is missing, otherwise only
on the first visit, and resumes at the kept screen. The setup steps it is a view
of are grouped by screen: an add-on that reads mail or a calendar has its sign-in and steps under mail and calendar, and
the optional extras never count toward finishing."""

from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine import setup
from engine.connectors import reads
from engine.packs import summary
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_sign_in import signing as signing  # noqa: F401 - the fixture
from tests.test_sign_in_sources import _app, _with_sources, sign_in

TOKEN = "t"


def _fresh(tmp_path):
    """A workspace as `cockpit init` makes it with no template, and the app on it."""
    ws = init_workspace(tmp_path / "ws", git=False)
    return ws, _open(ws)


def _open(ws):
    """The app on a workspace, started again from its files as a restart does."""
    cfg = ws.config(env={})
    c = TestClient(create_app(ws, cfg, TOKEN, start_worker=False, ui_dist=ws.root / "no-ui"))
    c.headers["Authorization"] = f"Bearer {TOKEN}"
    return c


def _view(c):
    return c.get("/api/setup").json()


def _steps(c):
    return {s["id"]: s for s in _view(c)["steps"]}


def test_the_walkthrough_opens_by_itself_on_a_new_workspace_at_its_first_screen(tmp_path):
    _, c = _fresh(tmp_path)
    walk = _view(c)["walkthrough"]
    assert walk == {"open": True, "step": "you", "closed": False, "finished": False}


def test_the_screen_the_person_is_on_is_kept_and_is_where_it_resumes_after_a_restart(tmp_path):
    ws, c = _fresh(tmp_path)
    assert c.post("/api/setup/walkthrough", json={"step": "mail"}).json()["step"] == "mail"
    again = _open(ws)  # the app started again from the same workspace
    walk = _view(again)["walkthrough"]
    assert walk["open"] and walk["step"] == "mail" and not walk["closed"]


def test_finish_later_keeps_its_screen_and_it_opens_again_next_visit_while_you_or_an_ai_account_is_missing(tmp_path):
    ws, c = _fresh(tmp_path)
    c.post("/api/setup/walkthrough", json={"step": "ai"})
    closed = c.post("/api/setup/walkthrough", json={"closed": True}).json()
    assert closed["closed"] and closed["step"] == "ai"
    again = _view(_open(ws))  # the next visit, after a restart
    assert again["walkthrough"]["open"] and again["walkthrough"]["step"] == "ai"
    assert not again["finished"]  # Today's setup line still has work to show


def _found(named=True):
    """Setup steps as the walkthrough sees them: You done or not, People not done."""
    return [setup.Step(i, d, False, group=i, counted=True) for i, d in {"workspace": named, "people": False}.items()]


def test_once_you_and_an_ai_account_are_set_it_opens_by_itself_only_on_the_first_visit(tmp_path):
    """The person's path: they don't add people yet. The walkthrough doesn't come back on later visits; People waits on
    Today's setup line. Without their name or any AI account chosen, it comes back on every visit."""
    ws, c = _fresh(tmp_path)
    from types import SimpleNamespace

    def settings(use):
        tiers = {"routine": SimpleNamespace(use=use)}
        return SimpleNamespace(workspace=SimpleNamespace(demo=False), ai=SimpleNamespace(tiers=tiers))

    cfg, no_account = settings("an-account/a-model"), settings(None)
    assert setup.walkthrough(ws, cfg, _found()).open  # the first visit
    c.post("/api/setup/walkthrough", json={"step": "people"})  # it was shown
    assert not setup.walkthrough(ws, cfg, _found()).open
    c.post("/api/setup/walkthrough", json={"closed": True})
    assert not setup.walkthrough(ws, cfg, _found()).open
    assert setup.walkthrough(ws, cfg, _found(named=False)).open
    assert setup.walkthrough(ws, no_account, _found()).open
    c.post("/api/setup/walkthrough", json={"finished": True})
    assert setup.walkthrough(ws, no_account, _found()).open
    assert not setup.walkthrough(ws, cfg, _found()).open


def test_an_unknown_screen_is_refused_and_nothing_is_kept(tmp_path):
    _, c = _fresh(tmp_path)
    assert c.post("/api/setup/walkthrough", json={"step": "nowhere"}).status_code == 422
    assert _view(c)["walkthrough"]["step"] == "you"


def test_the_sandbox_workspaces_do_not_open_it_by_themselves(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    assert not _view(_open(ws))["walkthrough"]["open"]


def test_skipping_every_step_still_brings_it_back_while_you_and_an_ai_account_are_missing(tmp_path):
    ws, c = _fresh(tmp_path)
    for step in ("workspace", "ai", "mail", "backup", "people"):
        c.post(f"/api/setup/{step}/skip")
    view = _view(c)
    assert view["finished"] and view["walkthrough"]["open"]


def test_the_screen_to_open_at_is_the_first_with_something_left_when_none_was_kept(tmp_path):
    ws, c = _fresh(tmp_path)
    c.post("/api/setup/workspace/skip")
    c.post("/api/setup/ai/skip")
    assert _view(c)["walkthrough"]["step"] == "mail"


def test_steps_belong_to_a_screen_and_only_the_five_that_matter_count(tmp_path):
    _, c = _fresh(tmp_path)
    steps = _steps(c)
    on = {s: (steps[s]["group"], steps[s]["counted"]) for s in setup.CORE_STEPS}
    assert on == {
        "workspace": ("you", True),
        "ai": ("ai", True),
        "mail": ("mail", True),
        "backup": ("backup", True),
        "people": ("people", True),
        "template": ("done", False),
        "first_note": ("done", False),
        "addons": ("done", False),
    }


def test_finishing_does_not_need_the_optional_extras(tmp_path):
    _, c = _fresh(tmp_path)
    assert not _view(c)["finished"]
    for step in ("workspace", "ai", "mail", "backup", "people"):
        c.post(f"/api/setup/{step}/skip")
    view = _view(c)
    # The extras stay undone (add-ons is done here only because nothing the person installed is off).
    extras = [s for s in view["steps"] if s["group"] == "done" and s["id"] != "addons"]
    assert view["finished"] and extras and not any(s["done"] or s["skipped"] for s in extras)


def test_mail_counts_as_set_up_when_a_mail_or_calendar_source_is_read(tmp_path):
    ws, c = _fresh(tmp_path)
    assert not _steps(c)["mail"]["done"]
    path = ws.config_dir / "watch.yaml"
    config = yaml.safe_load(path.read_text()) or {}
    config["sources"] = [
        {
            "id": "mine",
            "label": "My mail",
            "connector": "mailbox",
            "settings": {"host": "mail.example.com", "user": "me@example.com", "password": "env:MAIL_PASSWORD"},
        }
    ]
    path.write_text(yaml.safe_dump(config))
    assert _steps(_open(ws))["mail"]["done"]


def test_what_a_connector_reads_comes_from_its_name():
    assert reads("mailbox") == ["mail"] and reads("calendar") == ["calendar"]
    assert reads("p18/inbox") == ["mail"] and reads("google/mail") == ["mail"] and reads("x/calendar") == ["calendar"]
    assert reads("folder") == [] and reads("feed") == [] and reads("p18/goals") == []
    provides = {"connectors": ["p18/mail", "p18/calendar", "p18/files"], "sign_ins": ["p18/account"]}
    assert summary(provides, {})["reads"] == ["mail", "calendar"]
    assert summary({"connectors": ["p18/files"]}, {})["reads"] == []


def test_a_sign_in_of_an_add_on_that_reads_mail_is_under_mail_and_calendar_and_is_not_counted(signing):  # noqa: F811
    ws, cfg, store, _ = signing
    store.close()
    _with_sources(ws)
    c, api = _app(ws, cfg)
    found = next(s for s in c.get(f"{api}/setup").json()["steps"] if s["sign_in"] == "p18/service")
    assert found["group"] == "mail" and not found["counted"] and not found["done"]
    assert not {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}["mail"]["done"]
    sign_in(c, api)
    steps = {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}
    assert steps["p18/service"]["done"] and steps["mail"]["done"]


def test_a_sign_in_of_an_add_on_that_reads_no_mail_is_an_optional_extra(signing):  # noqa: F811
    ws, cfg, store, _ = signing
    found = next(s for s in setup.steps(ws, cfg, store) if s.sign_in == "p18/service")
    assert found.group == "done" and not found.counted
    assert not {s.id: s for s in setup.steps(ws, cfg, store)}["mail"].done


def test_the_add_ons_that_come_with_the_app_are_not_listed_to_turn_on_and_not_on_the_add_ons_screen_while_off(tmp_path):
    """The person's path: a new workspace never asks about the app's own samples and kits, and the Add-ons screen only
    shows them once turned on, or in a sandbox workspace."""
    from engine.plugin_manifest import shipped_plugins

    ws, c = _fresh(tmp_path)
    shipped = shipped_plugins()
    assert shipped and not shipped & set(setup.addons_off(ws, ws.config(env={})))
    listed = {p["name"] for p in c.get("/api/packs").json()["installed"]}
    assert not shipped & listed
    sandbox = init_workspace(tmp_path / "sandbox", template=DEMO_B, git=False)
    assert shipped <= {p["name"] for p in _open(sandbox).get("/api/packs").json()["installed"]}
