"""Add-ons from the screen with no command line: a catalog's address is added in place and read at once, and a read
token for a private release file is typed there and kept like any typed secret (the settings hold only where)."""

import hashlib
import stat

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import pack_install, packs
from engine.config import load_config
from tests.test_pack_install import RELEASE, WEB, wheel
from tests.test_setup import make

CATALOG = f"{WEB}catalog.example.com/packs.yaml"
OTHER = f"{WEB}other.example.com/packs.yaml"
TOKEN = "read-" + "token-value-1"


@pytest.fixture
def screen(tmp_path, monkeypatch):
    """The app with no catalog listed; whichever catalog is added lists one installable add-on."""
    data = wheel()
    entry = packs.Entry(
        id="packdemo", name="Pack demo", release={"url": RELEASE, "sha256": hashlib.sha256(data).hexdigest()}
    )
    bare = packs.Entry(id="bare", name="Bare", install="Ask the publisher.")
    monkeypatch.setattr(packs, "read_feeds", lambda urls, *a, **k: [packs.Feed(u, [entry, bare]) for u in urls])
    tokens: list = []

    def download(url, sha, token=None, client=None):
        tokens.append(token)
        if token != TOKEN:
            raise pack_install.NeedsToken("the release file couldn't be read: it may be private")
        return data

    monkeypatch.setattr(pack_install, "download", download)
    place = tmp_path / "site"
    place.mkdir()
    monkeypatch.setattr(pack_install, "target", lambda: place)
    ws, cfg, store = make(tmp_path)
    store.close()
    return ws, cfg, tokens


def start(ws, cfg):
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    return c, cfg.server.base_path.rstrip("/") + "/api"


def hosted(cfg):
    update = {"mode": "hosted", "public_url": f"{WEB}app.example.com"}
    return cfg.__class__(files={**cfg.files, "server": cfg.server.model_copy(update=update)}, sources={})


def feeds_of(ws):
    return list(load_config(ws.config_dir, env={}).workspace.plugins.catalog.feeds)


def fingerprint(c, api):
    return c.get(f"{api}/settings").json()["fingerprint"]


def test_a_catalog_added_from_the_screen_is_saved_and_listed_without_a_restart(screen):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    assert c.get(f"{api}/packs").json()["feeds"] == []
    added = c.post(f"{api}/packs/catalogs", json={"address": f" {CATALOG} ", "fingerprint": fingerprint(c, api)})
    assert added.status_code == 200, added.text
    assert added.json()["needs_restart"] is False
    assert feeds_of(ws) == [CATALOG]
    view = c.post(f"{api}/packs/refresh").json()
    assert [(f["address"], f["removable"]) for f in view["feeds"]] == [(CATALOG, True)]
    assert {p["id"]: p["release_host"] for p in view["available"]} == {"packdemo": "releases.example.com", "bare": None}
    assert {p["id"]: p["installable"] for p in view["available"]} == {"packdemo": True, "bare": False}


@pytest.mark.parametrize(
    "address",
    [
        "",
        "catalog.example.com/packs.yaml",
        "http" + "://catalog.example.com/packs.yaml",
        f"{WEB}",
        f"{WEB}a b.example.com/x",
    ],
)
def test_an_address_that_isnt_an_https_address_is_refused_in_plain_words(screen, address):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    refused = c.post(f"{api}/packs/catalogs", json={"address": address, "fingerprint": fingerprint(c, api)})
    assert refused.status_code == 400 and "starting with https://" in refused.json()["detail"]
    assert feeds_of(ws) == []


def test_a_catalog_listed_twice_is_refused_and_one_can_be_taken_off_again(screen):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    first = c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    again = c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": first.json()["fingerprint"]})
    assert again.status_code == 409 and "already" in again.json()["detail"]
    second = c.post(f"{api}/packs/catalogs", json={"address": OTHER, "fingerprint": first.json()["fingerprint"]})
    assert feeds_of(ws) == [CATALOG, OTHER]
    gone = c.post(
        f"{api}/packs/catalogs/remove", json={"address": CATALOG, "fingerprint": second.json()["fingerprint"]}
    )
    assert gone.status_code == 200 and feeds_of(ws) == [OTHER]
    missing = c.post(
        f"{api}/packs/catalogs/remove", json={"address": CATALOG, "fingerprint": gone.json()["fingerprint"]}
    )
    assert missing.status_code == 404


def test_a_read_token_typed_on_the_screen_is_kept_privately_and_the_install_then_uses_it(screen):
    ws, cfg, tokens = screen
    c, api = start(ws, cfg)
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    # Without a token the install says a token would fix it, in a header the screen reads.
    refused = c.post(f"{api}/packs/packdemo/install")
    assert refused.status_code == 409 and refused.headers["X-Cockpit-Needs"] == "read-token"
    assert tokens == [None]
    kept = c.post(f"{api}/packs/packdemo/token", json={"token": f" {TOKEN} ", "fingerprint": fingerprint(c, api)})
    assert kept.status_code == 200, kept.text
    assert TOKEN not in kept.text and kept.json()["needs_restart"] is False
    file = ws.private_dir / "keys" / "release-token-releases-example-com"
    assert file.read_text().strip() == TOKEN
    assert stat.S_IMODE(file.stat().st_mode) == 0o600 and stat.S_IMODE(file.parent.stat().st_mode) == 0o700
    held = load_config(ws.config_dir, env={}).workspace.plugins.catalog.release_tokens
    assert held == {"releases.example.com": f"file:{file.resolve()}"}
    assert TOKEN not in (ws.config_dir / "workspace.yaml").read_text()
    done = c.post(f"{api}/packs/packdemo/install")
    assert done.status_code == 200, done.text
    assert tokens[-1] == TOKEN


def test_a_read_token_can_be_given_as_where_it_is_kept_instead(screen):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    given = c.post(
        f"{api}/packs/packdemo/token", json={"reference": "RELEASE_TOKEN", "fingerprint": fingerprint(c, api)}
    )
    assert given.status_code == 200, given.text
    held = load_config(ws.config_dir, env={}).workspace.plugins.catalog.release_tokens
    assert held == {"releases.example.com": "env:RELEASE_TOKEN"}
    assert not (ws.private_dir / "keys").exists()
    # A token whose variable isn't set says a token is needed.
    missing = c.post(f"{api}/packs/packdemo/install")
    assert missing.status_code == 409 and missing.headers["X-Cockpit-Needs"] == "read-token"


def test_a_hosted_app_refuses_a_typed_token_but_takes_where_it_is_kept(screen):
    ws, cfg, _ = screen
    c, api = start(ws, hosted(cfg))
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    refused = c.post(f"{api}/packs/packdemo/token", json={"token": TOKEN, "fingerprint": fingerprint(c, api)})
    assert refused.status_code == 400 and "can't be pasted" in refused.json()["detail"]
    assert TOKEN not in refused.text and not (ws.private_dir / "keys").exists()
    assert load_config(ws.config_dir, env={}).workspace.plugins.catalog.release_tokens == {}
    given = c.post(
        f"{api}/packs/packdemo/token", json={"reference": "env:RELEASE_TOKEN", "fingerprint": fingerprint(c, api)}
    )
    assert given.status_code == 200


@pytest.mark.parametrize("body", [{}, {"token": " "}, {"token": TOKEN, "reference": "env:X"}])
def test_a_token_needs_exactly_one_of_a_typed_value_or_a_place(screen, body):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    refused = c.post(f"{api}/packs/packdemo/token", json={**body, "fingerprint": fingerprint(c, api)})
    assert refused.status_code == 400 and "one of the two" in refused.json()["detail"]
    assert not (ws.private_dir / "keys").exists()


def test_a_token_for_an_add_on_with_no_release_or_no_catalog_entry_is_refused(screen):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    no_release = c.post(f"{api}/packs/bare/token", json={"token": TOKEN, "fingerprint": fingerprint(c, api)})
    assert no_release.status_code == 409
    unknown = c.post(f"{api}/packs/nothing/token", json={"token": TOKEN, "fingerprint": fingerprint(c, api)})
    assert unknown.status_code == 404
    assert not (ws.private_dir / "keys").exists()


def test_a_refused_save_takes_back_a_token_it_kept(screen):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    stale = c.post(f"{api}/packs/packdemo/token", json={"token": TOKEN, "fingerprint": "stale"})
    assert stale.status_code == 409
    assert not (ws.private_dir / "keys" / "release-token-releases-example-com").exists()


def test_saving_a_read_token_can_be_undone_through_the_settings(screen):
    ws, cfg, _ = screen
    c, api = start(ws, cfg)
    c.post(f"{api}/packs/catalogs", json={"address": CATALOG, "fingerprint": fingerprint(c, api)})
    kept = c.post(f"{api}/packs/packdemo/token", json={"token": TOKEN, "fingerprint": fingerprint(c, api)})
    change = kept.json()["changes"][0]
    assert change["key"] == "workspace.plugins.catalog.release_tokens"
    undone = c.post(
        f"{api}/settings",
        json={"changes": {change["key"]: change["before"]}, "reset": [], "fingerprint": kept.json()["fingerprint"]},
    )
    assert undone.status_code == 200, undone.text
    assert load_config(ws.config_dir, env={}).workspace.plugins.catalog.release_tokens == {}
