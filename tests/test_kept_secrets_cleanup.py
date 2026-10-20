"""An old kept secret that no setting refers to is removed after `storage.kept_secrets.keep_days`, and removing a
source or an account removes the secrets kept for it, once no Undo points at them any more (F13)."""

from datetime import UTC, datetime, timedelta

from engine import kept_secrets
from engine.config import load_config
from engine.setup import keep_secret, secret_name
from engine.storage import Store
from tests.test_setup import client, make
from tests.test_typed_secrets import TYPED, _added_with_password, mailbox_kind, new_source, sources

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def keys_of(ws):
    folder = ws.private_dir / "keys"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def live(ws):
    return load_config(ws.config_dir, env={})


def sweep(ws, cfg, now):
    store = Store(ws.db_path, cfg=cfg)
    try:
        return kept_secrets.sweep(ws, store, cfg, now)
    finally:
        store.close()


def changed_password(c, api, fingerprint, value="other-secret"):
    done = c.post(f"{api}/watch/sources/work-mail", json={"secrets": {"password": value}, "fingerprint": fingerprint})
    assert done.status_code == 200, done.text
    return done.json()


def test_the_settings_for_keeping_old_secrets_have_defaults_and_descriptions(tmp_path):
    ws, cfg, store = make(tmp_path)
    store.close()
    kept = cfg.storage.kept_secrets
    assert (kept.keep_days, kept.undo_grace_minutes) == (30, 10)
    from engine.settings import describe

    shown = {s.key: s for s in describe(cfg)}
    for key in ("storage.kept_secrets.keep_days", "storage.kept_secrets.undo_grace_minutes"):
        assert shown[key].description and shown[key].editable


def test_an_old_kept_secret_nothing_refers_to_is_removed_after_the_configured_days(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    first = secret_name("source", "work-mail", "password")
    changed_password(c, api, added["fingerprint"])
    assert keys_of(ws) == [first, first + "-2"]
    cfg = live(ws)
    # Just replaced: an Undo may still point at the old one, and it hasn't waited the days.
    assert sweep(ws, cfg, NOW + timedelta(minutes=1)) == []
    assert sweep(ws, cfg, NOW + timedelta(days=29)) == []
    assert keys_of(ws) == [first, first + "-2"]
    removed = sweep(ws, cfg, NOW + timedelta(days=31))
    assert removed == [first]
    assert keys_of(ws) == [first + "-2"], "the one the source uses is never removed"
    assert sweep(ws, cfg, NOW + timedelta(days=90)) == []


def test_the_days_are_a_setting(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    first = secret_name("source", "work-mail", "password")
    done = changed_password(c, api, added["fingerprint"])
    fp = c.post(
        f"{api}/settings", json={"changes": {"storage.kept_secrets.keep_days": 2}, "fingerprint": done["fingerprint"]}
    )
    assert fp.status_code == 200, fp.text
    cfg = live(ws)
    sweep(ws, cfg, NOW)
    assert sweep(ws, cfg, NOW + timedelta(days=3)) == [first]


def test_a_secret_the_settings_still_name_is_never_removed_however_old(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    _added_with_password(c, api)
    name = secret_name("source", "work-mail", "password")
    cfg = live(ws)
    sweep(ws, cfg, NOW)
    assert sweep(ws, cfg, NOW + timedelta(days=400)) == []
    assert keys_of(ws) == [name]


def test_undo_restoring_an_old_secret_finds_it_while_it_still_points_there(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    first = secret_name("source", "work-mail", "password")
    done = changed_password(c, api, added["fingerprint"])
    cfg = live(ws)
    # An old save whose Undo is still on offer: the sweep waits, however many days the setting says.
    cfg.storage.kept_secrets.keep_days = 1
    assert sweep(ws, cfg, datetime.now(UTC) + timedelta(minutes=2)) == []
    undo = {c_["key"]: c_["before"] for c_ in done["changes"]}
    back = c.post(f"{api}/settings", json={"changes": undo, "reset": [], "fingerprint": done["fingerprint"]})
    assert back.status_code == 200
    assert next(s for s in sources(ws) if s.id == "work-mail").settings["password"].endswith(first)
    assert (ws.private_dir / "keys" / first).read_text().strip() == TYPED


def test_a_file_the_app_did_not_keep_for_a_setting_is_never_swept(tmp_path):
    ws, cfg, store = make(tmp_path)
    store.close()
    folder = ws.private_dir / "keys"
    folder.mkdir(parents=True)
    token = folder / "sign-in-mail--ada-example-com.json"
    token.write_text("{}")
    keep_secret(ws, "unrelated-secret", TYPED)
    assert sweep(ws, cfg, NOW) == []
    removed = sweep(ws, cfg, NOW + timedelta(days=60))
    assert removed == ["unrelated-secret"] and token.exists()


def test_the_backup_key_is_never_swept_because_older_backups_need_it(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fp = c.get(f"{api}/settings").json()["fingerprint"]
    first = c.post(f"{api}/backup-key", json={"value": "first-backup-key", "fingerprint": fp})
    assert first.status_code == 200, first.text
    second = c.post(
        f"{api}/backup-key", json={"value": "second-backup-key", "fingerprint": first.json()["fingerprint"]}
    )
    assert second.status_code == 200, second.text
    assert len(keys_of(ws)) == 2
    cfg = live(ws)
    sweep(ws, cfg, NOW)
    assert sweep(ws, cfg, NOW + timedelta(days=400)) == []
    assert len(keys_of(ws)) == 2


def test_removing_a_source_removes_its_kept_secrets_once_no_undo_points_at_them_and_says_so(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    name = secret_name("source", "work-mail", "password")
    removed = c.post(f"{api}/watch/sources/work-mail/remove", json={"fingerprint": added["fingerprint"]})
    assert removed.status_code == 200, removed.text
    body = removed.json()
    # The Undo of the removal brings the source back with its password, so the file waits for the Undo to run out.
    assert (body["kept_secrets_going"], body["kept_secrets_undo_minutes"]) == (1, 10)
    assert keys_of(ws) == [name]
    cfg = live(ws)
    assert sweep(ws, cfg, datetime.now(UTC) + timedelta(minutes=5)) == []
    assert sweep(ws, cfg, datetime.now(UTC) + timedelta(minutes=11)) == [name]
    assert keys_of(ws) == []


def test_undoing_the_removal_of_a_source_cancels_the_removal_of_its_secrets(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    name = secret_name("source", "work-mail", "password")
    removed = c.post(f"{api}/watch/sources/work-mail/remove", json={"fingerprint": added["fingerprint"]}).json()
    undo = {c_["key"]: c_["before"] for c_ in removed["changes"]}
    assert (
        c.post(
            f"{api}/settings", json={"changes": undo, "reset": [], "fingerprint": removed["fingerprint"]}
        ).status_code
        == 200
    )
    cfg = live(ws)
    assert sweep(ws, cfg, datetime.now(UTC) + timedelta(days=90)) == []
    assert keys_of(ws) == [name]


def test_with_no_grace_a_removed_sources_secrets_go_at_once(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    added, _ = _added_with_password(c, api)
    fp = c.post(
        f"{api}/settings",
        json={"changes": {"storage.kept_secrets.undo_grace_minutes": 0}, "fingerprint": added["fingerprint"]},
    ).json()
    removed = c.post(f"{api}/watch/sources/work-mail/remove", json={"fingerprint": fp["fingerprint"]}).json()
    assert removed["kept_secrets_going"] == 1 and keys_of(ws) == []


def test_removing_an_ai_account_removes_every_key_kept_for_it_after_the_grace(tmp_path):
    from engine.setup import known_endpoints

    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kind = next(k for k in known_endpoints() if k["needs_key"] and k["base_url"])
    fp = c.get(f"{api}/settings").json()["fingerprint"]
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
            "fingerprint": fp,
        },
    ).json()
    changed = c.post(f"{api}/ai/accounts/mine", json={"key": "second-key", "fingerprint": added["fingerprint"]}).json()
    assert keys_of(ws) == ["mine", "mine-2"]
    removed = c.post(f"{api}/ai/accounts/mine/remove", json={"fingerprint": changed["fingerprint"]}).json()
    assert removed["kept_secrets_going"] == 2 and removed["kept_secrets_undo_minutes"] == 10
    cfg = live(ws)
    assert sweep(ws, cfg, datetime.now(UTC) + timedelta(minutes=2)) == []
    assert sorted(sweep(ws, cfg, datetime.now(UTC) + timedelta(minutes=12))) == ["mine", "mine-2"]
    assert keys_of(ws) == []


def test_removing_something_with_nothing_kept_says_nothing_about_secrets(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fp = c.get(f"{api}/settings").json()["fingerprint"]
    given = new_source(mailbox_kind(c, api), "Other")
    given["settings"] = {**given["settings"], "password": "env:MAIL_PASSWORD"}
    added = c.post(f"{api}/watch/sources", json={**given, "fingerprint": fp})
    assert added.status_code == 200, added.text
    added = added.json()
    removed = c.post(f"{api}/watch/sources/other/remove", json={"fingerprint": added["fingerprint"]}).json()
    assert removed["kept_secrets_going"] is None


def test_the_worker_sweeps_kept_secrets_on_its_own_schedule(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    keep_secret(ws, "stale-secret", TYPED)
    clock = {"now": NOW}
    worker = Worker(ws, store, cfg, Events(), now=lambda: clock["now"])
    assert worker.sweep_kept_secrets_if_due() == []
    clock["now"] = NOW + timedelta(days=40)
    assert worker.sweep_kept_secrets_if_due() == ["stale-secret"]
