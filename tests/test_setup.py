"""Settings from the screens and the first-run setup: keys described for forms, saves that keep comments and never
race, steps that know when they are done, a backup folder, an AI account with its key kept on this computer, plugin
steps, and a restart to use what was saved."""

import os
import stat
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.config import load_config
from engine.config.yaml_edit import remove_key, set_key
from engine.setup import known_endpoints
from tests.conftest import DEMO_B
from tests.test_today_panels_jobs import FIXTURE
from tests.test_today_panels_jobs import workspace as plugin_workspace

#: The adapter of the first kind of account the catalog offers (a server on this computer).
COMMON = known_endpoints()[0]["adapter"]


def make(tmp_path, env=None):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env=env or {})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def client(ws, cfg, store):
    from api.app import create_app

    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    return c, cfg.server.base_path.rstrip("/") + "/api"


# ---- editing the files -----------------------------------------------------------------------------------------------


def test_a_key_is_changed_in_place_keeping_comments():
    text = "# about this file\nversion: 1\nname: Demo   # what it is called\nuser:\n  full_name: Ada\n\n# the end\n"
    changed = set_key(text, ["name"], "Harbor work")
    assert "# about this file" in changed and "# what it is called" in changed and "# the end" in changed
    assert yaml.safe_load(changed)["name"] == "Harbor work"
    added = set_key(text, ["user", "timezone"], "Europe/Lisbon")
    assert yaml.safe_load(added)["user"] == {"full_name": "Ada", "timezone": "Europe/Lisbon"}
    removed = remove_key(text, ["user", "full_name"])
    assert yaml.safe_load(removed)["user"] == {} and "# the end" in removed


def test_a_key_inside_a_one_line_mapping_still_gets_the_right_value():
    text = "version: 1\nmodels: {small: a, large: b}\n"
    assert yaml.safe_load(set_key(text, ["models", "small"], "c"))["models"] == {"small": "c", "large": "b"}


# ---- settings --------------------------------------------------------------------------------------------------------


def test_settings_are_described_for_the_forms(tmp_path, monkeypatch):
    monkeypatch.setenv("COCKPIT__UI__TOAST_SECONDS", "3")
    ws, cfg, store = make(tmp_path, env={"COCKPIT__UI__TOAST_SECONDS": "3"})
    c, api = client(ws, cfg, store)
    view = c.get(f"{api}/settings").json()
    items = {i["key"]: i for i in view["items"]}
    assert items["workspace.name"]["type"] == "text" and items["workspace.name"]["basic"]
    assert items["server.port"]["editable"] is False
    assert items["stages.moves"]["type"] == "choice" and items["stages.moves"]["options"] == ["person", "rule"]
    assert items["ai.providers"]["type"] == "other" and not items["ai.providers"]["editable"]
    assert items["ui.toast_seconds"]["locked"] and items["ui.toast_seconds"]["source"] == "env"
    assert "workspace.version" not in items and view["fingerprint"]


def test_a_feature_switch_comes_first_and_its_settings_name_it(tmp_path):
    from engine import settings

    _, cfg, store = make(tmp_path)
    store.close()
    found = settings.describe(cfg)
    order = {s.key: n for n, s in enumerate(found)}
    by_key = {s.key: s for s in found}
    switched = [s for s in found if s.enabled_by]
    assert switched
    for s in switched:
        switch = by_key.get(s.enabled_by)
        assert switch is not None, f"{s.key} names an unknown switch {s.enabled_by}"
        assert switch.type in ("yes_no", "text"), f"{s.enabled_by} can't be on or off"
        assert order[switch.key] < order[s.key], f"{s.enabled_by} must come before {s.key}"
        assert switch.basic or not s.basic, f"{s.key} is shown first but its switch {s.enabled_by} isn't"
    assert by_key["storage.backups.every_hours"].enabled_by == "storage.backups.automatic"
    backups = [s.key for s in found if s.group == "storage.backups"]
    assert backups[0] == "storage.backups.automatic"
    assert by_key["storage.sync.folder"].picker == "folder"
    assert all(s.picker in (None, "folder", "file") for s in found)
    assert all(s.type == "text" for s in found if s.picker)


def test_a_save_writes_the_file_records_the_change_and_never_races(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    done = c.post(f"{api}/settings", json={"changes": {"workspace.name": "Harbor work"}, "fingerprint": fingerprint})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["changes"][0]["key"] == "workspace.name" and body["changes"][0]["after"] == "Harbor work"
    assert load_config(ws.config_dir, env={}).workspace.name == "Harbor work"
    again = c.post(f"{api}/settings", json={"changes": {"workspace.name": "Other"}, "fingerprint": fingerprint})
    assert again.status_code == 409
    from engine.storage import Store

    reread = Store(ws.db_path)
    try:
        assert reread.read().list("setting_change")[-1].data["key"] == "workspace.name"
    finally:
        reread.close()


def test_a_bad_value_or_a_locked_key_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("COCKPIT__UI__TOAST_SECONDS", "3")
    ws, cfg, store = make(tmp_path, env={"COCKPIT__UI__TOAST_SECONDS": "3"})
    c, api = client(ws, cfg, store)
    before = (ws.config_dir / "storage.yaml").read_text()
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    bad = c.post(f"{api}/settings", json={"changes": {"storage.backups.keep": 0}, "fingerprint": fingerprint})
    assert bad.status_code == 400 and "keep" in bad.json()["detail"]
    assert (ws.config_dir / "storage.yaml").read_text() == before
    locked = c.post(f"{api}/settings", json={"changes": {"ui.toast_seconds": 9}, "fingerprint": fingerprint})
    assert locked.status_code == 400 and "environment variable" in locked.json()["detail"]
    server = c.post(f"{api}/settings", json={"changes": {"server.port": 9000}, "fingerprint": fingerprint})
    assert server.status_code == 400


def test_a_key_goes_back_to_its_default(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    done = c.post(f"{api}/settings", json={"reset": ["storage.backups.keep"], "fingerprint": fingerprint}).json()
    assert done["changes"][0]["is_default"]
    data = yaml.safe_load((ws.config_dir / "storage.yaml").read_text())
    assert "keep" not in data["backups"]


# ---- setup steps -----------------------------------------------------------------------------------------------------


def test_steps_say_what_is_done_and_can_be_skipped(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    steps = {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}
    assert list(steps)[:7] == ["workspace", "template", "ai", "backup", "people", "first_note", "addons"]
    assert not steps["first_note"]["done"]
    assert c.post(f"{api}/setup/first_note/skip").status_code == 200
    view = c.get(f"{api}/setup").json()
    assert {s["id"]: s for s in view["steps"]}["first_note"]["skipped"] and view["local"]
    c.post(f"{api}/setup/first_note/reopen")
    assert not {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}["first_note"]["skipped"]


def test_a_backup_folder_is_checked_then_added(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    inside = c.get(f"{api}/setup/folder-check", params={"path": str(ws.root / "data")}).json()
    assert not inside["ok"] and "outside the workspace" in inside["problem"]
    missing = c.get(f"{api}/setup/folder-check", params={"path": str(tmp_path / "nowhere")}).json()
    assert not missing["ok"]
    folder = tmp_path / "drive"
    folder.mkdir()
    assert c.get(f"{api}/setup/folder-check", params={"path": str(folder)}).json()["ok"]
    listing = c.get(f"{api}/setup/folders", params={"path": str(tmp_path)}).json()
    assert "drive" in listing["folders"] and listing["parent"]
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    added = c.post(
        f"{api}/setup/backup-folder", json={"path": str(folder), "label": "drive", "fingerprint": fingerprint}
    )
    assert added.status_code == 200, added.text
    targets = load_config(ws.config_dir, env={}).storage.backups.targets
    assert targets[-1].path == str(folder.resolve()) and targets[-1].label == "drive"


def test_an_ai_account_keeps_a_pasted_key_on_this_computer(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    assert [e["id"] for e in c.get(f"{api}/ai/endpoints").json()] == [e["id"] for e in known_endpoints()]
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    account = {
        "name": "my-account",
        "adapter": COMMON,
        "base_url": "http://localhost:11434/v1",
        "key": "not-a-real-key",
        "models": {"small": "small-model"},
        "allowed_data": ["open", "internal"],
        "use_for": ["routine"],
        "fingerprint": fingerprint,
    }
    done = c.post(f"{api}/ai/accounts", json=account)
    assert done.status_code == 200, done.text
    ai = (ws.config_dir / "ai.yaml").read_text()
    assert "not-a-real-key" not in ai
    loaded = load_config(ws.config_dir, env={})
    provider = loaded.ai.providers["my-account"]
    assert provider.auth.startswith("file:") and loaded.ai.tiers["routine"].use == "my-account/small"
    key_file = ws.private_dir / "keys" / "my-account"
    assert key_file.read_text().strip() == "not-a-real-key"
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    twice = c.post(f"{api}/ai/accounts", json={**account, "fingerprint": fingerprint})
    assert twice.status_code == 409
    # Undo posts the values from before: the account goes and the tier gets its old account back.
    undo = {"changes": {}, "reset": [], "fingerprint": fingerprint}
    for change in done.json()["changes"]:
        if change["was_default"]:
            undo["reset"].append(change["key"])
        else:
            undo["changes"][change["key"]] = change["before"]
    undone = c.post(f"{api}/settings", json=undo)
    assert undone.status_code == 200, undone.text
    assert "my-account" not in load_config(ws.config_dir, env={}).ai.providers


def test_a_template_is_listed_and_applied(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    assert "client-work" in [t["id"] for t in c.get(f"{api}/templates").json()]
    assert c.post(f"{api}/templates/apply", json={"id": "client-work"}).json()["plugins"] == ["kit"]
    assert {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}["template"]["done"]


@pytest.mark.skipif(os.environ.get("COCKPIT_TEST_CORE_ONLY") == "1", reason="the kit plugin is off in this run")
def test_a_template_already_set_up_counts_as_done(tmp_path):
    ws, cfg, store = make(tmp_path)
    from engine import setup, templates

    kit = ws.config_dir / "plugins" / "kit.yaml"
    have = {t["id"] for t in yaml.safe_load(kit.read_text())["types"]}
    expected = {
        t["id"]
        for t in templates.shipped()
        if {k["id"] for k in yaml.safe_load(t["path"].read_text())["plugins"]["kit"]["types"]} <= have
    }
    assert expected, "the demo workspace sets up a shipped template's item types"
    step = {s.id: s for s in setup.steps(ws, cfg, store)}["template"]
    assert step.done
    c, api = client(ws, cfg, store)
    assert {t["id"] for t in c.get(f"{api}/templates").json() if t["set_up"]} == expected
    assert all(t["adds"] for t in c.get(f"{api}/templates").json())


def test_a_template_not_yet_set_up_is_not_done(tmp_path):
    ws, cfg, store = make(tmp_path)
    from engine import setup

    kit = ws.config_dir / "plugins" / "kit.yaml"
    settings = yaml.safe_load(kit.read_text())
    settings["types"] = []
    kit.write_text(yaml.safe_dump(settings))
    try:
        assert not {s.id: s for s in setup.steps(ws, cfg, store)}["template"].done
    finally:
        store.close()


# ---- plugin steps and restarting -------------------------------------------------------------------------------------


def test_a_plugin_adds_a_setup_step(tmp_path):
    code = FIXTURE.replace(
        "    registrar.job(",
        '    registrar.setup_step("p18/first-goal", label="Add your first goal", '
        'done=lambda view, settings: bool(view.list("p18/goal")))\n    registrar.job(',
    )
    ws, cfg, store = plugin_workspace(tmp_path, code)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["provides"]["setup_steps"] = ["p18/first-goal"]
    path.write_text(yaml.safe_dump(manifest))
    from engine import setup
    from engine.applier import apply_as_person
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        assert store.plugins.active("p18"), store.plugins.status["p18"].reason
        step = next(s for s in setup.steps(ws, cfg, store) if s.plugin == "p18")
        assert step.id == "p18/first-goal" and step.label == "Add your first goal" and not step.done
        apply_as_person(store, cfg, [{"op": "p18/add-goal", "title": "Map"}], "A goal")
        assert next(s for s in setup.steps(ws, cfg, store) if s.plugin == "p18").done
    finally:
        store.close()


def test_the_app_restarts_only_when_the_person_asks(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    asked = []
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: asked.append(True))
    try:
        assert not worker.restart_due() and not worker.needs_restart()
        text = (ws.config_dir / "storage.yaml").read_text()
        (ws.config_dir / "storage.yaml").write_text(set_key(text, ["export", "commit"], not cfg.storage.export.commit))
        assert worker.needs_restart() and not worker.restart_due() and asked == []  # shown, never on its own
        assert worker.restart_for == ["storage.export.commit"]  # and says what waits for it
        worker.request_restart()
        assert worker.restart_due() and asked == [True]
        assert not worker.restart_due() and asked == [True]
    finally:
        store.close()


def test_live_settings_are_taken_in_at_once_and_a_mixed_change_waits(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: None)
    try:
        text = (ws.config_dir / "workspace.yaml").read_text()
        (ws.config_dir / "workspace.yaml").write_text(set_key(text, ["name"], "Changed"))
        assert worker.needs_restart() is False and cfg.workspace.name == "Changed"  # in use already
        ai = (ws.config_dir / "ai.yaml").read_text()
        (ws.config_dir / "ai.yaml").write_text(set_key(ai, ["budgets", "per_run_usd"], 0.5))
        assert worker.needs_restart() is False and cfg.ai.budgets.per_run_usd == 0.5
        text = (ws.config_dir / "workspace.yaml").read_text()
        storage = (ws.config_dir / "storage.yaml").read_text()
        (ws.config_dir / "workspace.yaml").write_text(set_key(text, ["name"], "Again"))
        (ws.config_dir / "storage.yaml").write_text(
            set_key(storage, ["export", "commit"], not cfg.storage.export.commit)
        )
        assert worker.needs_restart() is True and cfg.workspace.name == "Changed"  # nothing half taken in
    finally:
        store.close()


def test_a_backup_folder_is_taken_in_without_a_restart(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: None)
    try:
        folder = tmp_path / "drive"
        folder.mkdir()
        storage = (ws.config_dir / "storage.yaml").read_text()
        targets = [{"path": str(folder)}]
        (ws.config_dir / "storage.yaml").write_text(set_key(storage, ["backups", "targets"], targets))
        assert worker.needs_restart() is False
        assert [t.path for t in cfg.storage.backups.targets] == [str(folder)]
    finally:
        store.close()


def test_restart_is_asked_for_and_refused_when_the_app_cant_start_itself(tmp_path):
    from api.app import create_app

    ws, cfg, store = make(tmp_path)
    store.close()
    plain = TestClient(create_app(ws, cfg, "t", start_worker=False))
    plain.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    refused = plain.post(f"{api}/restart")
    assert refused.status_code == 409 and "start it again" in refused.text
    assert plain.get(f"{api}/status").json()["can_restart"] is False
    plain.close()
    asked = []
    able = TestClient(create_app(ws, cfg, "t", start_worker=False, on_restart=lambda: asked.append(True)))
    able.headers["Authorization"] = "Bearer t"
    assert able.post(f"{api}/restart").json() == {"restarting": True}
    assert able.app.state.worker.restart_due() and asked == [True]


@pytest.mark.parametrize("mode", ["hosted"])
def test_a_hosted_app_never_takes_a_pasted_key_or_lists_folders(tmp_path, mode):
    ws, cfg, store = make(tmp_path)
    app_host = yaml.safe_load((Path(__file__).parent / "fixtures" / "network" / "network.yaml").read_text())["app_host"]
    update = {"mode": mode, "public_url": "https" + f"://{app_host}"}  # the address a hosted app answers to
    cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=update)}, sources={})
    c, api = client(ws, cfg, store)
    assert c.get(f"{api}/setup/folders").status_code == 403
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    account = {
        "name": "x",
        "adapter": COMMON,
        "key": "k",
        "models": {"a": "b"},
        "fingerprint": fingerprint,
    }
    assert c.post(f"{api}/ai/accounts", json=account).status_code == 400


def test_a_restart_that_fails_says_how_to_start_again(monkeypatch, capsys):
    import engine.cli

    def refused(*args):
        raise OSError("not allowed here")

    monkeypatch.setattr(engine.cli.os, "execv", refused)
    monkeypatch.setattr(engine.cli.os, "name", "posix")
    monkeypatch.setattr(engine.cli.sys, "orig_argv", ["python", "cockpit", "serve", "-w", "ws"])
    assert engine.cli.restart_self() == 1
    err = capsys.readouterr().err
    assert "couldn't restart by itself" in err and "cockpit serve -w ws" in err


def test_a_restart_never_starts_the_demo_over_or_opens_another_tab(monkeypatch):
    import engine.cli

    ran = []
    monkeypatch.setattr(engine.cli.os, "execv", lambda exe, args: ran.append(args))
    monkeypatch.setattr(engine.cli.os, "name", "posix")
    monkeypatch.setattr(engine.cli.sys, "orig_argv", ["python", "cockpit", "demo", "~/d", "--fresh", "--open"])
    monkeypatch.delenv(engine.cli.RESTARTED, raising=False)
    engine.cli.restart_self()
    assert ran and "--fresh" not in ran[0] and ran[0][-3:] == ["demo", "~/d", "--open"]
    assert engine.cli.os.environ.get(engine.cli.RESTARTED) == "1"  # read once by the new start, then dropped


def test_the_person_the_app_is_for_is_named_on_their_record(tmp_path):
    from engine.storage import Store, WriteContext
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "fresh", git=False)
    cfg = ws.config(env={})
    c, api = client(ws, cfg, Store(ws.db_path, cfg=cfg))
    assert c.get(f"{api}/me").json() == {"person": None, "full_name": ""}
    made = c.post(f"{api}/me", json={"full_name": "  Sam   Tester "}).json()
    assert made["full_name"] == "Sam Tester" and made["person"]
    assert ws.config(env={}).workspace.user.person == made["person"]  # linked in the settings by id only
    renamed = c.post(f"{api}/me", json={"full_name": "Sam T. Tester"}).json()
    assert renamed["person"] == made["person"]
    store = Store(ws.db_path)
    try:
        assert store.read().get("person", made["person"]).data["full_name"] == "Sam T. Tester"
        with store.transaction() as tx:
            tx.create("person", {"full_name": "Robin Other"}, WriteContext(actor="pm", trust="trusted", op="t"))
    finally:
        store.close()
    assert c.post(f"{api}/me", json={"full_name": "robin other"}).status_code == 409


# ---- choosing a service and its models -------------------------------------------------------------------------------


def a_service(models=("model-b", "model-a"), status=200, seen=None):
    """The common adapter, answered by a fake service instead of the network."""
    import httpx

    from engine.ai import adapters

    def answer(request):
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": "invalid_api_key"}})
        data = [{"id": m, "context_length": 32000, "pricing": {"prompt": "0.000001"}} for m in models]
        return httpx.Response(200, json={"data": data})

    base = adapters.ADAPTERS[COMMON]

    class Faked(base):
        def __init__(self, settings, secret=None):
            super().__init__(settings, secret, transport=httpx.MockTransport(answer))

    return Faked


def test_a_service_is_picked_by_name_and_its_models_listed_with_an_unsaved_key(tmp_path, monkeypatch):
    from engine.ai import adapters

    seen = []
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_service(seen=seen))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kinds = c.get(f"{api}/ai/endpoints").json()
    service = next(k for k in kinds if k["needs_key"] and k["base_url"] and k["key_url"])
    assert all(k["local"] is False for k in kinds if k["needs_key"])
    listed = c.post(f"{api}/ai/models", json={"endpoint": service["id"], "key": "not-a-real-key"}).json()
    assert [m["id"] for m in listed["models"]] == ["model-a", "model-b"] and listed["problem"] is None
    assert listed["models"][0]["input_per_million"] == 1 and listed["models"][0]["context_tokens"] == 32000
    assert seen[0].headers["authorization"] == "Bearer not-a-real-key"
    assert not (ws.private_dir / "keys").exists()  # nothing kept until the account is added
    unkeyed = c.post(f"{api}/ai/models", json={"endpoint": service["id"]}).json()
    assert unkeyed["models"] == [] and "needs a key" in unkeyed["problem"]
    assert c.post(f"{api}/ai/models", json={"endpoint": "no-such-kind"}).status_code == 400


def test_a_key_the_service_refuses_is_said_in_plain_words(tmp_path, monkeypatch):
    from engine.ai import adapters

    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_service(status=401))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    service = next(k for k in c.get(f"{api}/ai/endpoints").json() if k["needs_key"] and k["base_url"])
    listed = c.post(f"{api}/ai/models", json={"endpoint": service["id"], "key": "wrong"}).json()
    assert listed["models"] == [] and "didn't accept the key" in listed["problem"]


def test_a_model_server_on_this_computer_is_found_without_a_key(tmp_path, monkeypatch):
    from engine.ai import adapters

    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_service(models=("local-model",)))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    found = c.get(f"{api}/ai/local").json()
    local = [k for k in known_endpoints() if k["local"] and k["adapter"] == COMMON]
    assert [f["endpoint"] for f in found] == [k["id"] for k in local] and found[0]["models"] == ["local-model"]
    assert all("restricted" in k["allowed_data"] for k in local)


def test_an_account_of_a_known_kind_starts_with_its_settings(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kind = next((k for k in known_endpoints() if k["settings"]), None)
    assert kind is not None
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    done = c.post(
        f"{api}/ai/accounts",
        json={
            "name": "picked",
            "adapter": kind["adapter"],
            "endpoint": kind["id"],
            "base_url": kind["base_url"],
            "key": "not-a-real-key",
            "models": {"everyday": "some-model", "harder": "bigger-model"},
            "use": {"routine": "everyday", "deep": "harder"},
            "fingerprint": fingerprint,
        },
    )
    assert done.status_code == 200, done.text
    loaded = load_config(ws.config_dir, env={})
    assert loaded.ai.tiers["routine"].use == "picked/everyday" and loaded.ai.tiers["deep"].use == "picked/harder"
    provider = loaded.ai.providers["picked"]
    for key, value in kind["settings"].items():
        assert getattr(provider, key) == value


@pytest.mark.skipif(os.environ.get("COCKPIT_TEST_CORE_ONLY") == "1", reason="the example plugin is off in this run")
def test_an_add_ons_settings_are_a_form_group_saved_to_its_own_file(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    view = c.get(f"{api}/settings").json()
    mine = {i["key"]: i for i in view["items"] if i["plugin"] == "example"}
    assert mine and all(i["file"] == "plugins/example" and i["group"] == "plugins/example" for i in mine.values())
    label = mine["plugins/example.draft_label"]
    assert label["type"] == "text" and label["editable"] and label["source"] == "file"
    assert "plugins/example.version" not in mine
    path = ws.config_dir / "plugins" / "example.yaml"
    comments = [line for line in path.read_text().splitlines() if line.startswith("#")]
    done = c.post(
        f"{api}/settings",
        json={"changes": {"plugins/example.draft_label": "Noted"}, "fingerprint": view["fingerprint"]},
    )
    assert done.status_code == 200, done.text
    change = done.json()["changes"][0]
    assert change["key"] == "plugins/example.draft_label" and change["after"] == "Noted" and change["before"]
    assert yaml.safe_load(path.read_text())["draft_label"] == "Noted"
    assert all(line in path.read_text() for line in comments)  # the file's comments stay
    fingerprint = done.json()["fingerprint"]
    wrong = c.post(
        f"{api}/settings", json={"changes": {"plugins/example.ask_on_add": "maybe"}, "fingerprint": fingerprint}
    )
    assert wrong.status_code >= 400 and "ask_on_add" in wrong.text
    unknown = c.post(f"{api}/settings", json={"changes": {"plugins/nobody.thing": 1}, "fingerprint": fingerprint})
    assert unknown.status_code >= 400


def test_the_ai_test_says_in_plain_words_whether_each_kind_of_work_answered(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    lines = c.post(f"{api}/ai/test").json()
    assert lines and len({(x["tier"], x["account"]) for x in lines}) == len(lines)  # one line each
    for x in lines:
        assert "/" not in x["account"] and "temperature" not in x["account"] and "max output" not in x["detail"]
        assert x["ok"] is False or x["detail"] == "answered"


def test_an_account_is_listed_changed_and_removed_with_undo(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    kind = next(k for k in known_endpoints() if k["needs_key"] and k["base_url"])
    added = c.post(
        f"{api}/ai/accounts",
        json={
            "name": "mine",
            "adapter": kind["adapter"],
            "endpoint": kind["id"],
            "base_url": kind["base_url"],
            "key": "first-key",
            "models": {"everyday": "a-model"},
            "use": {"routine": "everyday"},
            "fingerprint": fingerprint,
        },
    ).json()
    listed = {a["name"]: a for a in c.get(f"{api}/ai/accounts").json()}
    assert listed["mine"]["kind"] == kind["id"] and listed["mine"]["used_for"] == ["routine"]
    assert listed["mine"]["has_key"] and "first-key" not in str(listed)
    changed = c.post(
        f"{api}/ai/accounts/mine",
        json={"key": "second-key", "models": {"everyday": "b-model"}, "fingerprint": added["fingerprint"]},
    )
    assert changed.status_code == 200, changed.text
    assert (ws.private_dir / "keys" / "mine").read_text().strip() == "second-key"
    assert load_config(ws.config_dir, env={}).ai.providers["mine"].models == {"everyday": "b-model"}
    removed = c.post(f"{api}/ai/accounts/mine/remove", json={"fingerprint": changed.json()["fingerprint"]})
    assert removed.status_code == 200, removed.text
    after = load_config(ws.config_dir, env={})
    assert "mine" not in after.ai.providers and not (after.ai.tiers["routine"].use or "").startswith("mine/")
    assert removed.json()["needs_restart"] is False  # AI accounts apply live
    # Undo puts it back, as a settings undo does: the values from before.
    undo = {"changes": {}, "reset": [], "fingerprint": removed.json()["fingerprint"]}
    for change in removed.json()["changes"]:
        undo["changes"][change["key"]] = change["before"]
    assert c.post(f"{api}/settings", json=undo).status_code == 200
    assert "mine" in load_config(ws.config_dir, env={}).ai.providers
    assert c.post(f"{api}/ai/accounts/nobody/remove", json={"fingerprint": "x"}).status_code == 404


def test_built_in_agents_start_with_their_tools_off_and_say_if_installed(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kinds = c.get(f"{api}/ai/endpoints").json()
    generic = next(k for k in kinds if k["id"] == "agent")
    agents = [k for k in kinds if k["program"]]
    assert len(agents) >= 4
    assert all(k["adapter"] == generic["adapter"] and k["installed"] in (True, False) for k in agents)
    for kind in agents:
        command = kind["settings"]["agent"]["command"]
        assert command[0] == kind["program"]
        assert kind["settings"]["agent"]["packet_via"] in ("stdin", "argument")
        assert "{prompt}" in command or kind["settings"]["agent"]["packet_via"] != "argument"
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    first = agents[0]
    made = c.post(
        f"{api}/ai/accounts",
        json={
            "name": "agent-one",
            "adapter": first["adapter"],
            "endpoint": first["id"],
            "models": {"everyday": (first["model_examples"] or ["default"])[0]},
            "fingerprint": fingerprint,
        },
    )
    assert made.status_code == 200, made.text
    provider = load_config(ws.config_dir, env={}).ai.providers["agent-one"]
    assert provider.agent is not None and provider.agent.command == first["settings"]["agent"]["command"]
    assert provider.kind == first["id"]
    picks_own = next(k for k in agents if k["model_optional"])
    made = c.post(
        f"{api}/ai/accounts",
        json={
            "name": "agent-two",
            "adapter": picks_own["adapter"],
            "endpoint": picks_own["id"],
            "models": {},
            "use_for": ["routine"],
            "fingerprint": made.json()["fingerprint"],
        },
    )
    assert made.status_code == 200, made.text
    saved = load_config(ws.config_dir, env={})
    assert list(saved.ai.providers["agent-two"].models) == ["default"]
    assert saved.ai.tiers["routine"].use.startswith("agent-two/")


def test_an_account_says_whether_its_key_is_there_and_can_be_tested_before_it_does_work(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    stand_in = next(name for name, p in cfg.ai.providers.items() if p.adapter == "stub")
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    kinds = c.get(f"{api}/ai/endpoints").json()
    service = next(k for k in kinds if k["needs_key"] and k["base_url"])
    made = c.post(
        f"{api}/ai/accounts",
        json={
            "name": "unset-key",
            "adapter": service["adapter"],
            "endpoint": service["id"],
            "key_ref": "env:COCKPIT_TEST_KEY_NOT_SET",
            "models": {"everyday": "model-x"},
            "fingerprint": fingerprint,
        },
    )
    assert made.status_code == 200, made.text
    accounts = {a["name"]: a for a in c.get(f"{api}/ai/accounts").json()}
    assert accounts["unset-key"]["key_state"] == "missing"
    assert "COCKPIT_TEST_KEY_NOT_SET" in accounts["unset-key"]["key_where"]
    assert accounts[stand_in]["key_state"] == "none"
    tested = c.post(f"{api}/ai/accounts/{stand_in}/test").json()
    assert tested == [{"tier": "account", "account": stand_in, "main": True, "ok": True, "detail": "answered"}]
    missing = c.post(f"{api}/ai/accounts/unset-key/test").json()
    assert not missing[0]["ok"] and "COCKPIT_TEST_KEY_NOT_SET" in missing[0]["detail"]
    assert c.post(f"{api}/ai/accounts/nobody/test").status_code == 404


@pytest.mark.skipif(os.environ.get("COCKPIT_TEST_CORE_ONLY") == "1", reason="the bundled add-ons are off in this run")
def test_the_add_ons_step_is_done_until_an_installed_add_on_is_off(tmp_path):
    from engine import setup

    ws, cfg, store = make(tmp_path)
    try:
        assert {s.id: s for s in setup.steps(ws, cfg, store)}["addons"].done
        folder = ws.root / "plugins" / "spare"
        folder.mkdir(parents=True)
        (folder / "plugin.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "spare",
                    "version": "0.1.0",
                    "plugin_api": ">=0.3,<0.4",
                    "description": "An add-on left off",
                    "entry": "spare:register",
                    "config_schema": "spare:Config",
                }
            )
        )
        assert setup.addons_off(ws, cfg) == ["spare"]
        assert not {s.id: s for s in setup.steps(ws, cfg, store)}["addons"].done
    finally:
        store.close()


def test_an_installed_add_on_is_turned_on_and_off_with_undo(tmp_path):
    ws, cfg, store = make(tmp_path)
    folder = ws.root / "plugins" / "spare"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "spare",
                "version": "0.1.0",
                "plugin_api": ">=0.3,<0.4",
                "description": "An add-on left off",
                "entry": "spare:register",
                "config_schema": "spare:Config",
            }
        )
    )
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    assert c.post(f"{api}/packs/nothing-here/on", json={"fingerprint": fingerprint}).status_code == 404
    turned = c.post(f"{api}/packs/spare/on", json={"fingerprint": fingerprint})
    assert turned.status_code == 200, turned.text
    assert turned.json()["needs_restart"] is True
    assert "spare" in load_config(ws.config_dir, env={}).workspace.plugins.enabled
    again = c.post(f"{api}/packs/spare/on", json={"fingerprint": turned.json()["fingerprint"]})
    assert again.status_code == 409
    off = c.post(f"{api}/packs/spare/off", json={"fingerprint": turned.json()["fingerprint"]})
    assert off.status_code == 200 and "spare" not in load_config(ws.config_dir, env={}).workspace.plugins.enabled


def test_a_source_is_added_changed_and_removed_from_the_screens_without_a_restart(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: None)
    c, api = client(ws, cfg, store)
    kinds = {k["name"]: k for k in c.get(f"{api}/watch/kinds").json()}
    folder_kind = next(k for k in kinds.values() if k["plugin"] is None and any(i["key"] == "path" for i in k["items"]))
    folder = tmp_path / "inbox"
    folder.mkdir()
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    bad = c.post(
        f"{api}/watch/sources",
        json={"connector": folder_kind["name"], "label": "Shared notes", "settings": {}, "fingerprint": fingerprint},
    )
    assert bad.status_code == 400 and "path" in bad.text
    added = c.post(
        f"{api}/watch/sources",
        json={
            "connector": folder_kind["name"],
            "label": "Shared notes",
            "settings": {"path": str(folder)},
            "fingerprint": fingerprint,
        },
    )
    assert added.status_code == 200, added.text
    assert added.json()["needs_restart"] is False
    assert worker.needs_restart() is False  # watched sources are taken in at once
    listed = {s["id"]: s for s in c.get(f"{api}/watch").json()}
    assert "shared-notes" in listed and listed["shared-notes"]["label"] == "Shared notes"
    again = c.post(
        f"{api}/watch/sources",
        json={
            "connector": folder_kind["name"],
            "label": "Shared notes",
            "settings": {"path": str(folder)},
            "fingerprint": added.json()["fingerprint"],
        },
    )
    assert again.status_code == 200 and "shared-notes-2" in {s["id"] for s in c.get(f"{api}/watch").json()}
    changed = c.post(
        f"{api}/watch/sources/shared-notes",
        json={"every_minutes": 15, "enabled": False, "fingerprint": again.json()["fingerprint"]},
    )
    assert changed.status_code == 200
    source = next(s for s in load_config(ws.config_dir, env={}).watch.sources if s.id == "shared-notes")
    assert source.every_minutes == 15 and source.enabled is False
    removed = c.post(f"{api}/watch/sources/shared-notes/remove", json={"fingerprint": changed.json()["fingerprint"]})
    assert removed.status_code == 200
    assert "shared-notes" not in {s.id for s in load_config(ws.config_dir, env={}).watch.sources}
    assert c.post(f"{api}/watch/sources/nothing/remove", json={"fingerprint": "x"}).status_code == 404


def test_an_add_on_turned_on_shows_as_on_and_one_left_off_stops_the_step_asking(tmp_path):
    from engine import setup

    ws, cfg, store = make(tmp_path)
    folder = ws.root / "plugins" / "spare"
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "spare",
                "version": "0.1.0",
                "plugin_api": ">=0.3,<0.4",
                "description": "An add-on left off",
                "entry": "spare:register",
                "config_schema": "spare:Config",
            }
        )
    )
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    steps = {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}
    assert not steps["addons"]["done"]
    assert c.post(f"{api}/packs/spare/off", json={"fingerprint": fingerprint}).status_code == 200  # leave it off
    assert "spare" in setup._state(ws)["addons_decided"]
    assert c.post(f"{api}/setup/addons/leave-off").status_code == 200  # and any other add-on left off
    assert {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}["addons"]["done"]
    turned = c.post(f"{api}/packs/spare/on", json={"fingerprint": fingerprint})
    assert turned.status_code == 200
    spare = next(p for p in c.get(f"{api}/packs").json()["installed"] if p["name"] == "spare")
    assert spare["enabled"] is True  # as saved, before the restart
    assert "spare" not in setup.addons_off(ws, load_config(ws.config_dir, env={}))


def test_a_list_written_at_its_keys_own_indent_is_edited_in_place():
    import yaml

    from engine.config.yaml_edit import set_key

    text = "# kept\nretries: 3\nsources:\n- id: a\n  label: A\nlast: true\n"
    edited = set_key(text, ["sources"], [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])
    assert yaml.safe_load(edited) == {
        "retries": 3,
        "sources": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "last": True,
    }
    assert edited.startswith("# kept")


def test_a_real_account_takes_over_the_tiers_still_on_the_stand_in(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    assert {t.use.split("/")[0] for t in cfg.ai.tiers.values()} == {"stub"}
    account = {
        "name": "mine",
        "adapter": COMMON,
        "base_url": "http://localhost:11434/v1",
        "key": "not-a-real-key",
        "models": {"small": "small-model"},
        "allowed_data": ["open", "internal"],
        "fingerprint": c.get(f"{api}/settings").json()["fingerprint"],
    }
    assert c.post(f"{api}/ai/accounts", json=account).status_code == 200
    tiers = load_config(ws.config_dir, env={}).ai.tiers
    assert {name: t.use for name, t in tiers.items()} == {name: "mine/small" for name in tiers}
    # A second account leaves the tiers on the first.
    second = {**account, "name": "other", "fingerprint": c.get(f"{api}/settings").json()["fingerprint"]}
    assert c.post(f"{api}/ai/accounts", json=second).status_code == 200
    assert {t.use for t in load_config(ws.config_dir, env={}).ai.tiers.values()} == {"mine/small"}
