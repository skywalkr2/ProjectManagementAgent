"""A password, key or private address typed on the screen is kept in the workspace's private keys folder on this
computer, and the setting holds only where it is kept. A hosted app refuses it, and it never lands in the settings, the
ledger or an answer."""

import logging
import stat
from pathlib import Path

import pytest
import yaml

from engine.config import load_config
from engine.secrets import resolve_secret
from engine.setup import keep_secret, kept_here, secret_name
from tests.conftest import DEMO_B
from tests.test_setup import client, make

#: What a test types where a secret goes. Written so no scan takes it for a real one.
TYPED = "typed-" + "secret-value-1"


def mailbox_kind(c, api):
    return next(k for k in c.get(f"{api}/watch/kinds").json() if k["name"] == "mailbox")


def new_source(kind, label="Work mail"):
    return {"connector": kind["name"], "label": label, "settings": {"host": "mail.example.com", "user": "ada"}}


def sources(ws):
    return load_config(ws.config_dir, env={}).watch.sources


def source_ids(ws):
    return {s.id for s in sources(ws)}


def everywhere_but_the_keys(ws, text):
    """Every file under the workspace outside the keys folder that holds the text."""
    keys = (ws.private_dir / "keys").resolve()
    return [
        p
        for p in ws.root.rglob("*")
        if p.is_file() and keys not in p.resolve().parents and text.encode() in p.read_bytes()
    ]


def test_a_kinds_form_marks_the_settings_that_hold_a_secret(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    items = {i["key"]: i for i in mailbox_kind(c, api)["items"]}
    assert items["password"]["secret"] is True
    assert items["host"]["secret"] is False and items["user"]["secret"] is False
    calendar = next(k for k in c.get(f"{api}/watch/kinds").json() if k["name"] == "calendar")
    assert {i["key"]: i["secret"] for i in calendar["items"]}["address"] is True


def test_a_pasted_password_is_kept_in_a_private_file_and_only_the_reference_is_written(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    added = c.post(
        f"{api}/watch/sources",
        json={**new_source(mailbox_kind(c, api)), "secrets": {"password": TYPED}, "fingerprint": fingerprint},
    )
    assert added.status_code == 200, added.text
    assert TYPED not in added.text
    kept = ws.private_dir / "keys" / secret_name("source", "work-mail", "password")
    assert kept.read_text().strip() == TYPED
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600 and stat.S_IMODE(kept.parent.stat().st_mode) == 0o700
    source = next(s for s in sources(ws) if s.id == "work-mail")
    assert source.settings["password"] == f"file:{kept.resolve()}"
    assert everywhere_but_the_keys(ws, TYPED) == []
    # The list says where it is read from, never what it is.
    listed = next(s for s in c.get(f"{api}/watch").json() if s["id"] == "work-mail")
    assert listed["secrets"] == [{"field": "password", "where": "kept", "name": None}]
    assert TYPED not in c.get(f"{api}/settings").text


def test_a_changed_password_is_kept_beside_the_old_one_and_a_reference_the_person_names_is_left_as_it_is(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    added = c.post(
        f"{api}/watch/sources",
        json={**new_source(mailbox_kind(c, api)), "secrets": {"password": TYPED}, "fingerprint": fingerprint},
    )
    again = TYPED + "-again"
    changed = c.post(
        f"{api}/watch/sources/work-mail",
        json={"secrets": {"password": again}, "fingerprint": added.json()["fingerprint"]},
    )
    assert changed.status_code == 200, changed.text
    first = ws.private_dir / "keys" / secret_name("source", "work-mail", "password")
    kept = first.with_name(first.name + "-2")
    assert kept.read_text().strip() == again and first.read_text().strip() == TYPED
    source = next(s for s in sources(ws) if s.id == "work-mail")
    assert source.settings["host"] == "mail.example.com" and source.settings["password"] == f"file:{kept.resolve()}"
    # Giving where it is kept instead changes the reference, and says so on the list.
    instead = c.post(
        f"{api}/watch/sources/work-mail",
        json={
            "settings": {**source.settings, "password": "env:MAIL_PASSWORD"},
            "fingerprint": changed.json()["fingerprint"],
        },
    )
    assert instead.status_code == 200, instead.text
    listed = next(s for s in c.get(f"{api}/watch").json() if s["id"] == "work-mail")
    assert listed["secrets"] == [{"field": "password", "where": "env", "name": "MAIL_PASSWORD"}]
    assert not kept_here(ws, "env:MAIL_PASSWORD")


def test_a_calendars_private_address_can_be_pasted_too(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    address = "https" + "://calendar.example.com/private/abc.ics"
    added = c.post(
        f"{api}/watch/sources",
        json={"connector": "calendar", "label": "Team", "secrets": {"address": address}, "fingerprint": fingerprint},
    )
    assert added.status_code == 200, added.text
    assert address not in added.text and everywhere_but_the_keys(ws, address) == []
    assert (ws.private_dir / "keys" / "source-team-address").read_text().strip() == address


def test_a_hosted_app_refuses_a_pasted_secret(tmp_path):
    ws, cfg, store = make(tmp_path)
    update = {"mode": "hosted", "public_url": "https" + "://app.example.com"}
    cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=update)}, sources={})
    c, api = client(ws, cfg, store)
    before = source_ids(ws)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    refused = c.post(
        f"{api}/watch/sources",
        json={**new_source(mailbox_kind(c, api)), "secrets": {"password": TYPED}, "fingerprint": fingerprint},
    )
    assert refused.status_code == 400 and "can't be pasted" in refused.json()["detail"]
    assert TYPED not in refused.text and not (ws.private_dir / "keys").exists()
    assert source_ids(ws) == before


@pytest.mark.parametrize(
    ("secrets", "settings", "why"),
    [
        ({"host": TYPED}, {"user": "ada"}, "isn't a setting this kind of source keeps secret"),
        ({"nothing": TYPED}, {"user": "ada"}, "isn't a setting this kind of source keeps secret"),
        ({"password": "   "}, {"user": "ada"}, "Type or paste it"),
        ({"password": TYPED}, {"user": "ada", "password": "env:SOME_NAME"}, "not both"),
    ],
)
def test_a_pasted_value_for_a_setting_that_is_not_secret_or_given_twice_is_refused(tmp_path, secrets, settings, why):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    before = source_ids(ws)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    body = {
        "connector": "mailbox",
        "label": "Work mail",
        "settings": {"host": "mail.example.com", **settings},
        "secrets": secrets,
        "fingerprint": fingerprint,
    }
    refused = c.post(f"{api}/watch/sources", json=body)
    assert refused.status_code == 400 and why in refused.json()["detail"]
    assert TYPED not in refused.text
    assert source_ids(ws) == before and not (ws.private_dir / "keys").exists()


def test_a_source_that_fails_its_checks_leaves_nothing_kept(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    body = {"connector": "mailbox", "label": "Work mail", "settings": {}, "secrets": {"password": TYPED}}
    assert c.post(f"{api}/watch/sources", json={**body, "fingerprint": fingerprint}).status_code == 400
    assert not (ws.private_dir / "keys").exists()
    # A refused save (the settings changed meanwhile) removes a file it made, and keeps one that was already there.
    good = {**body, "settings": {"host": "mail.example.com", "user": "ada"}}
    assert c.post(f"{api}/watch/sources", json={**good, "fingerprint": "stale"}).status_code == 409
    assert not (ws.private_dir / "keys" / "source-work-mail-password").exists()


def test_keeping_a_secret_names_its_file_safely_and_knows_its_own(tmp_path):
    ws, _cfg, store = make(tmp_path)
    store.close()
    assert secret_name("source", "Work Mail", "auth.password") == "source-work-mail-auth-password"
    reference = keep_secret(ws, "source-x-password", TYPED)
    assert kept_here(ws, reference) and not kept_here(ws, "file:/somewhere/else") and not kept_here(ws, None)
    with pytest.raises(Exception, match="lowercase letters"):
        keep_secret(ws, "../escape", TYPED)


def _added_with_password(c, api):
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    added = c.post(
        f"{api}/watch/sources",
        json={**new_source(mailbox_kind(c, api)), "secrets": {"password": TYPED}, "fingerprint": fingerprint},
    )
    assert added.status_code == 200, added.text
    return added.json(), fingerprint


def test_a_refused_save_leaves_the_kept_password_and_the_settings_as_they_were(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    _, stale = _added_with_password(c, api)
    before = next(s for s in sources(ws) if s.id == "work-mail").settings["password"]
    refused = c.post(f"{api}/watch/sources/work-mail", json={"secrets": {"password": "other"}, "fingerprint": stale})
    assert refused.status_code == 409
    assert next(s for s in sources(ws) if s.id == "work-mail").settings["password"] == before
    kept = sorted(p.name for p in (ws.private_dir / "keys").iterdir())
    assert kept == [secret_name("source", "work-mail", "password")]
    assert (ws.private_dir / "keys" / kept[0]).read_text().strip() == TYPED


def test_undoing_a_password_change_brings_back_the_password_that_worked(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    before = next(s for s in sources(ws) if s.id == "work-mail").settings["password"]
    changed = c.post(
        f"{api}/watch/sources/work-mail", json={"secrets": {"password": "other"}, "fingerprint": added["fingerprint"]}
    )
    assert changed.status_code == 200, changed.text
    undo = {"changes": {}, "reset": [], "fingerprint": changed.json()["fingerprint"]}
    for change in changed.json()["changes"]:
        undo["changes"][change["key"]] = change["before"]
    assert c.post(f"{api}/settings", json=undo).status_code == 200
    restored = next(s for s in sources(ws) if s.id == "work-mail").settings["password"]
    assert restored == before
    assert Path(restored.removeprefix("file:")).read_text().strip() == TYPED


# ---- an add-on's own secrets ----------------------------------------------------------------------------------------

ADDON = "keyed"
ADDON_SECRETS = ["api-key", "client-secret"]
ADDON_MANIFEST = {
    "name": ADDON,
    "version": "0.1.0",
    "plugin_api": ">=0.3,<0.4",
    "description": "An add-on that needs two secrets",
    "entry": "fixture:register",
    "config_schema": "fixture:Config",
    "provides": {},
    "requires": {"secrets": ADDON_SECRETS},
}
ADDON_CODE = """
from engine.plugin_api import Settings

class Config(Settings):
    pass

def register(registrar):
    pass
"""


def addon_workspace(tmp_path, hosted=False):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    folder = ws.root / "plugins" / ADDON
    folder.mkdir(parents=True)
    (folder / "fixture.py").write_text(ADDON_CODE)
    (folder / "plugin.yaml").write_text(yaml.safe_dump(ADDON_MANIFEST))
    file = ws.config_dir / "workspace.yaml"
    settings = yaml.safe_load(file.read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], ADDON]
    file.write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    if hosted:
        update = {"mode": "hosted", "public_url": "https" + "://app.example.com"}
        cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=update)}, sources={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def addon_url(api, name):
    return f"{api}/addons/{ADDON}/secrets/{name}"


def fingerprint_of(c, api):
    return c.get(f"{api}/settings").json()["fingerprint"]


def addon_secret_state(c, api):
    listed = next(a for a in c.get(f"{api}/addon-secrets").json() if a["plugin"] == ADDON)
    return {s["secret"]: (s["where"], s["name"]) for s in listed["secrets"]}


def workspace_secrets(ws):
    return load_config(ws.config_dir, env={}).workspace.plugins.secrets.get(ADDON, {})


def test_an_addon_lists_the_secrets_it_declares_and_where_each_is_read_from(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    assert addon_secret_state(c, api) == {"api-key": ("none", None), "client-secret": ("none", None)}


def test_an_addons_secret_typed_on_the_screen_is_kept_privately_and_only_the_reference_is_written(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    done = c.post(addon_url(api, "api-key"), json={"value": TYPED, "fingerprint": fingerprint_of(c, api)})
    assert done.status_code == 200, done.text
    assert TYPED not in done.text
    kept = ws.private_dir / "keys" / secret_name("addon", ADDON, "api-key")
    assert kept.read_text().strip() == TYPED
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600 and stat.S_IMODE(kept.parent.stat().st_mode) == 0o700
    assert workspace_secrets(ws) == {"api-key": f"file:{kept.resolve()}"}
    assert everywhere_but_the_keys(ws, TYPED) == []
    assert addon_secret_state(c, api) == {"api-key": ("kept", None), "client-secret": ("none", None)}
    assert TYPED not in c.get(f"{api}/settings").text and TYPED not in c.get(f"{api}/addon-secrets").text
    # The add-on reads it back through the core, as it would a reference the person wrote by hand.
    assert resolve_secret(workspace_secrets(ws)["api-key"]) == TYPED


def test_typing_one_secret_leaves_the_add_ons_other_secrets_as_they_were(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    first = c.post(addon_url(api, "api-key"), json={"reference": "MY_KEY", "fingerprint": fingerprint_of(c, api)})
    assert first.status_code == 200, first.text
    second = c.post(addon_url(api, "client-secret"), json={"value": TYPED, "fingerprint": first.json()["fingerprint"]})
    assert second.status_code == 200, second.text
    held = workspace_secrets(ws)
    assert held["api-key"] == "env:MY_KEY" and held["client-secret"].startswith("file:")
    assert addon_secret_state(c, api) == {"api-key": ("env", "MY_KEY"), "client-secret": ("kept", None)}


def test_replacing_an_addons_secret_keeps_the_old_file_and_undo_brings_the_old_one_back(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    first = c.post(addon_url(api, "api-key"), json={"value": TYPED, "fingerprint": fingerprint_of(c, api)})
    again = TYPED + "-again"
    changed = c.post(addon_url(api, "api-key"), json={"value": again, "fingerprint": first.json()["fingerprint"]})
    assert changed.status_code == 200, changed.text
    old = ws.private_dir / "keys" / secret_name("addon", ADDON, "api-key")
    new = old.with_name(old.name + "-2")
    assert old.read_text().strip() == TYPED and new.read_text().strip() == again
    assert workspace_secrets(ws)["api-key"] == f"file:{new.resolve()}"
    undo = {"changes": {c_["key"]: c_["before"] for c_ in changed.json()["changes"]}, "reset": []}
    assert c.post(f"{api}/settings", json={**undo, "fingerprint": changed.json()["fingerprint"]}).status_code == 200
    assert resolve_secret(workspace_secrets(ws)["api-key"]) == TYPED


def test_undoing_the_first_time_an_addons_secret_was_given_takes_it_away_again(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    done = c.post(addon_url(api, "api-key"), json={"value": TYPED, "fingerprint": fingerprint_of(c, api)})
    changes = done.json()["changes"]
    assert [x["key"] for x in changes] == [f"workspace.plugins.secrets.{ADDON}.api-key"] and changes[0]["was_default"]
    undo = {"changes": {}, "reset": [x["key"] for x in changes], "fingerprint": done.json()["fingerprint"]}
    assert c.post(f"{api}/settings", json=undo).status_code == 200
    assert workspace_secrets(ws).get("api-key") is None
    assert addon_secret_state(c, api)["api-key"] == ("none", None)


def test_an_addon_secret_is_a_typed_value_or_a_place_never_both_nor_neither_nor_one_it_did_not_declare(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = fingerprint_of(c, api)
    both = c.post(addon_url(api, "api-key"), json={"value": TYPED, "reference": "X", "fingerprint": fingerprint})
    neither = c.post(addon_url(api, "api-key"), json={"value": "  ", "fingerprint": fingerprint})
    other = c.post(addon_url(api, "not-declared"), json={"value": TYPED, "fingerprint": fingerprint})
    unknown = c.post(f"{api}/addons/nobody/secrets/api-key", json={"value": TYPED, "fingerprint": fingerprint})
    assert [r.status_code for r in (both, neither)] == [400, 400]
    assert [r.status_code for r in (other, unknown)] == [404, 404]
    assert all(TYPED not in r.text for r in (both, neither, other, unknown))
    assert workspace_secrets(ws) == {} and not (ws.private_dir / "keys").exists()


def test_a_refused_save_of_an_addon_secret_leaves_no_file_behind_and_keeps_the_one_in_use(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path)
    c, api = client(ws, cfg, store)
    stale = fingerprint_of(c, api)
    first = c.post(addon_url(api, "api-key"), json={"value": TYPED, "fingerprint": stale})
    assert first.status_code == 200
    refused = c.post(addon_url(api, "api-key"), json={"value": "other", "fingerprint": stale})
    assert refused.status_code == 409
    assert sorted(p.name for p in (ws.private_dir / "keys").iterdir()) == [secret_name("addon", ADDON, "api-key")]


def test_a_hosted_app_refuses_a_typed_addon_secret_but_takes_where_it_is_kept(tmp_path):
    ws, cfg, store = addon_workspace(tmp_path, hosted=True)
    c, api = client(ws, cfg, store)
    refused = c.post(addon_url(api, "api-key"), json={"value": TYPED, "fingerprint": fingerprint_of(c, api)})
    assert refused.status_code == 400 and "can't be pasted" in refused.json()["detail"]
    assert TYPED not in refused.text and not (ws.private_dir / "keys").exists() and workspace_secrets(ws) == {}
    given = c.post(
        addon_url(api, "api-key"), json={"reference": "env:HOSTED_KEY", "fingerprint": fingerprint_of(c, api)}
    )
    assert given.status_code == 200, given.text
    assert addon_secret_state(c, api)["api-key"] == ("env", "HOSTED_KEY")


# ---- the backup key -------------------------------------------------------------------------------------------------


def backup_key_state(c, api):
    view = c.get(f"{api}/backup-key").json()
    return view["where"], view["name"]


def encrypt_setting(ws):
    return load_config(ws.config_dir, env={}).storage.backups.encrypt


def test_a_backup_key_typed_on_the_screen_is_kept_privately_and_only_the_reference_is_written(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    assert backup_key_state(c, api) == ("none", None)
    done = c.post(f"{api}/backup-key", json={"value": TYPED, "fingerprint": fingerprint_of(c, api)})
    assert done.status_code == 200, done.text
    assert TYPED not in done.text and done.json()["made"] is None
    kept = ws.private_dir / "keys" / "backup-key"
    assert kept.read_text().strip() == TYPED
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600 and stat.S_IMODE(kept.parent.stat().st_mode) == 0o700
    assert encrypt_setting(ws) == f"file:{kept.resolve()}"
    assert everywhere_but_the_keys(ws, TYPED) == []
    assert backup_key_state(c, api) == ("kept", None)
    assert TYPED not in c.get(f"{api}/settings").text and TYPED not in c.get(f"{api}/backup-key").text


def test_replacing_the_backup_key_keeps_the_old_one_so_older_backups_can_still_be_read(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    first = c.post(f"{api}/backup-key", json={"value": TYPED, "fingerprint": fingerprint_of(c, api)})
    again = TYPED + "-again"
    second = c.post(f"{api}/backup-key", json={"value": again, "fingerprint": first.json()["fingerprint"]})
    assert second.status_code == 200, second.text
    old = ws.private_dir / "keys" / "backup-key"
    new = old.with_name("backup-key-2")
    assert old.read_text().strip() == TYPED and new.read_text().strip() == again
    assert encrypt_setting(ws) == f"file:{new.resolve()}"


def test_a_backup_key_can_be_given_as_a_place_it_is_kept_and_not_both(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    both = c.post(
        f"{api}/backup-key",
        json={"value": TYPED, "reference": "X", "make": True, "fingerprint": fingerprint_of(c, api)},
    )
    nothing = c.post(f"{api}/backup-key", json={"fingerprint": fingerprint_of(c, api)})
    assert both.status_code == 400 and nothing.status_code == 400 and TYPED not in both.text
    assert encrypt_setting(ws) == "" and not (ws.private_dir / "keys").exists()
    by_name = c.post(f"{api}/backup-key", json={"reference": "BACKUP_KEY", "fingerprint": fingerprint_of(c, api)})
    assert by_name.status_code == 200, by_name.text
    assert encrypt_setting(ws) == "env:BACKUP_KEY" and backup_key_state(c, api) == ("env", "BACKUP_KEY")


def test_make_one_for_me_keeps_a_strong_key_and_shows_it_once_in_that_answer_only(tmp_path, caplog):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    with caplog.at_level(logging.DEBUG):
        made = c.post(f"{api}/backup-key", json={"make": True, "fingerprint": fingerprint_of(c, api)})
    assert made.status_code == 200, made.text
    key = made.json()["made"]
    assert isinstance(key, str) and len(key) >= 32
    kept = ws.private_dir / "keys" / "backup-key"
    assert kept.read_text().strip() == key and stat.S_IMODE(kept.stat().st_mode) == 0o600
    assert encrypt_setting(ws) == f"file:{kept.resolve()}"
    # Shown once: nothing else the app answers or writes holds it, and the log doesn't.
    assert everywhere_but_the_keys(ws, key) == []
    assert key not in caplog.text
    for later in (f"{api}/settings", f"{api}/backup-key", f"{api}/addon-secrets", f"{api}/watch"):
        assert key not in c.get(later).text
    assert key not in str(made.json()["changes"])
    # A second one is a different key, kept beside the first.
    again = c.post(f"{api}/backup-key", json={"make": True, "fingerprint": made.json()["fingerprint"]})
    assert again.json()["made"] != key and (kept.with_name("backup-key-2")).read_text().strip() == again.json()["made"]
    assert kept.read_text().strip() == key


def test_a_hosted_app_refuses_a_typed_or_made_backup_key(tmp_path):
    ws, cfg, store = make(tmp_path)
    update = {"mode": "hosted", "public_url": "https" + "://app.example.com"}
    cfg = cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=update)}, sources={})
    c, api = client(ws, cfg, store)
    for body in ({"value": TYPED}, {"make": True}):
        refused = c.post(f"{api}/backup-key", json={**body, "fingerprint": fingerprint_of(c, api)})
        assert refused.status_code == 400 and "can't be pasted" in refused.json()["detail"]
        assert TYPED not in refused.text
    assert not (ws.private_dir / "keys").exists() and encrypt_setting(ws) == ""
    given = c.post(f"{api}/backup-key", json={"reference": "env:BACKUP_KEY", "fingerprint": fingerprint_of(c, api)})
    assert given.status_code == 200, given.text


def test_a_refused_save_of_the_backup_key_leaves_no_file_behind(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    refused = c.post(f"{api}/backup-key", json={"value": TYPED, "fingerprint": "stale"})
    assert refused.status_code == 409
    assert not (ws.private_dir / "keys" / "backup-key").exists()


# ---- the core's own mailbox and calendar ----------------------------------------------------------------------------


def test_the_mailbox_password_and_the_calendars_private_address_are_typed_kept_and_never_written_elsewhere(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    address = "https" + "://calendar.example.com/private/token-9f2.ics"
    mail = c.post(
        f"{api}/watch/sources",
        json={
            **new_source(mailbox_kind(c, api)),
            "secrets": {"password": TYPED},
            "fingerprint": fingerprint_of(c, api),
        },
    )
    assert mail.status_code == 200, mail.text
    calendar = c.post(
        f"{api}/watch/sources",
        json={
            "connector": "calendar",
            "label": "Team",
            "secrets": {"address": address},
            "fingerprint": mail.json()["fingerprint"],
        },
    )
    assert calendar.status_code == 200, calendar.text
    for text in (TYPED, address):
        assert text not in mail.text + calendar.text
        assert everywhere_but_the_keys(ws, text) == []  # the settings, the ledger and the database included
        assert text not in c.get(f"{api}/settings").text + c.get(f"{api}/watch").text
    keys = ws.private_dir / "keys"
    for name, text in (("source-work-mail-password", TYPED), ("source-team-address", address)):
        assert (keys / name).read_text().strip() == text and stat.S_IMODE((keys / name).stat().st_mode) == 0o600
    by_id = {s.id: s for s in sources(ws)}
    assert by_id["work-mail"].settings["password"] == f"file:{(keys / 'source-work-mail-password').resolve()}"
    assert by_id["team"].settings["address"] == f"file:{(keys / 'source-team-address').resolve()}"
    listed = {s["id"]: s["secrets"] for s in c.get(f"{api}/watch").json()}
    assert listed["team"] == [{"field": "address", "where": "kept", "name": None}]


def test_a_calendar_takes_a_typed_address_or_a_file_on_this_computer_not_both(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    address = "https" + "://calendar.example.com/private/token-77.ics"
    both = c.post(
        f"{api}/watch/sources",
        json={
            "connector": "calendar",
            "label": "Team",
            "settings": {"file": str(tmp_path / "team.ics")},
            "secrets": {"address": address},
            "fingerprint": fingerprint_of(c, api),
        },
    )
    assert both.status_code == 400 and address not in both.text
    assert not (ws.private_dir / "keys").exists() and "team" not in source_ids(ws)
    # A file needs no secret, so nothing is kept for it.
    file_only = c.post(
        f"{api}/watch/sources",
        json={
            "connector": "calendar",
            "label": "Team",
            "settings": {"file": str(tmp_path / "team.ics")},
            "fingerprint": fingerprint_of(c, api),
        },
    )
    assert file_only.status_code == 200, file_only.text
    assert not (ws.private_dir / "keys").exists()
    # Changing it to a typed address (and away from the file) keeps only the address.
    changed = c.post(
        f"{api}/watch/sources/team",
        json={
            "settings": {"file": ""},
            "secrets": {"address": address},
            "fingerprint": file_only.json()["fingerprint"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert address not in changed.text and everywhere_but_the_keys(ws, address) == []
    assert (ws.private_dir / "keys" / "source-team-address").read_text().strip() == address
