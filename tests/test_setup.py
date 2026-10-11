"""Settings from the screens and the first-run setup: keys described for forms, saves that keep comments and never
race, steps that know when they are done, a backup folder, an AI account with its key kept on this computer, plugin
steps, and a restart to use what was saved."""

import os
import stat

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
    assert list(steps)[:6] == ["workspace", "template", "ai", "backup", "people", "first_note"]
    assert not steps["template"]["done"]
    assert c.post(f"{api}/setup/template/skip").status_code == 200
    view = c.get(f"{api}/setup").json()
    assert {s["id"]: s for s in view["steps"]}["template"]["skipped"] and view["local"]
    c.post(f"{api}/setup/template/reopen")
    assert not {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}["template"]["skipped"]


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


def test_saved_settings_restart_the_app_once_between_requests(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    asked = []
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: asked.append(True))
    try:
        assert not worker.restart_due()
        text = (ws.config_dir / "workspace.yaml").read_text()
        (ws.config_dir / "workspace.yaml").write_text(set_key(text, ["name"], "Changed"))
        assert worker.restart_due() and asked == [True]
        assert not worker.restart_due() and asked == [True]
    finally:
        store.close()


@pytest.mark.parametrize("mode", ["hosted"])
def test_a_hosted_app_never_takes_a_pasted_key_or_lists_folders(tmp_path, mode):
    ws, cfg, store = make(tmp_path)
    cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update={"mode": mode})}, sources={})
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


def test_restarting_is_promised_only_when_something_on_disk_changed(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: None)
    try:
        assert worker.needs_restart() is False  # nothing changed: the screen must not say it is restarting
        text = (ws.config_dir / "workspace.yaml").read_text()
        (ws.config_dir / "workspace.yaml").write_text(set_key(text, ["name"], "Changed"))
        assert worker.needs_restart() is True
        assert Worker(ws, store, cfg, Events()).needs_restart() is False  # can't restart itself: never promised
    finally:
        store.close()


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
