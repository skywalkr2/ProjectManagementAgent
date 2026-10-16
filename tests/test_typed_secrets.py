"""A password, key or private address typed on the screen is kept in the workspace's private keys folder on this
computer, and the setting holds only where it is kept. A hosted app refuses it, and it never lands in the settings, the
ledger or an answer."""

import stat

import pytest

from engine.config import load_config
from engine.setup import keep_secret, kept_here, secret_name
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


def test_a_changed_password_replaces_the_kept_one_and_a_reference_the_person_names_is_left_as_it_is(tmp_path):
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
    kept = ws.private_dir / "keys" / secret_name("source", "work-mail", "password")
    assert kept.read_text().strip() == again
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
