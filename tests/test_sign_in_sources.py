"""A sign-in starts the sources its plugin declares (plugin API 0.3.54): signing in is the whole setup. Each sign-in's
sources are added once, only where nothing reads with that connector yet, and a sign-in made earlier gets them when
the app starts."""

from urllib.parse import parse_qs, urlsplit

import yaml
from fastapi.testclient import TestClient

from engine.config import load_config
from tests.test_sign_in import AUTH, SIGNING, landing
from tests.test_sign_in import signing as signing  # noqa: F401 - the fixture

READING = SIGNING.replace(
    '        scopes=["read", "offline"], params={"access_type": "offline"},\n',
    '        scopes=["read", "offline"], params={"access_type": "offline"},\n'
    '        sources=[{"connector": "p18/inbox", "label": "Your inbox", "settings": {"folders": ["INBOX"]}}],\n',
).replace(
    "def register(registrar):\n",
    "from pydantic import BaseModel, Field\n"
    "from engine.plugin_api import Poll\n\n"
    "class InboxSettings(BaseModel):\n"
    "    folders: list[str] = Field(default_factory=list)\n\n"
    "def poll_inbox(settings, state, context):\n"
    "    return Poll([], {})\n\n"
    "def register(registrar):\n"
    "    registrar.connector('p18/inbox', label='Inbox', settings=InboxSettings, poll=poll_inbox)\n",
)


def _with_sources(ws):
    plugin = ws.root / "plugins" / "p18"
    (plugin / "fixture.py").write_text(READING)
    manifest = yaml.safe_load((plugin / "plugin.yaml").read_text())
    manifest["provides"]["connectors"] = ["p18/inbox"]
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))


def _app(ws, cfg):
    from api.app import create_app
    from tests.test_plugin_api_0329 import reopen

    cfg, store = reopen(ws, cfg)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), follow_redirects=False)
    c.headers["Authorization"] = "Bearer t"
    return c, cfg.server.base_path.rstrip("/") + "/api"


def sources(ws):
    return [s.model_dump(mode="json") for s in load_config(ws.config_dir, env={}).watch.sources]


def sign_in(c, api):
    url = c.post(f"{api}/sign-ins/p18/service/start").json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert url.startswith(AUTH)
    assert "sign_in=done" in landing(c.get(f"{api}/sign-ins/callback", params={"state": state, "code": "good"}))


def test_signing_in_starts_the_declared_sources_once(signing):  # noqa: F811
    ws, cfg, store, _ = signing
    store.close()
    _with_sources(ws)
    c, api = _app(ws, cfg)
    before = len(sources(ws))
    sign_in(c, api)
    added = [s for s in sources(ws) if s["connector"] == "p18/inbox"]
    assert len(sources(ws)) == before + 1 and added[0]["label"] == "Your inbox"
    assert added[0]["settings"] == {"folders": ["INBOX"]} and added[0]["enabled"] is not False
    # The person removes it; signing in again doesn't bring it back.
    kept = [s for s in sources(ws) if s["connector"] != "p18/inbox"]
    config = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    config["sources"] = kept
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(config))
    sign_in(c, api)
    assert not [s for s in sources(ws) if s["connector"] == "p18/inbox"]
    # The row says what isn't read, and one click starts it again.
    row = c.get(f"{api}/sign-ins").json()[0]
    assert row["not_reading"] == ["Your inbox"]
    again = c.post(f"{api}/sign-ins/p18/service/sources")
    assert again.status_code == 200 and again.json()["not_reading"] == []
    assert [s["label"] for s in sources(ws) if s["connector"] == "p18/inbox"] == ["Your inbox"]


def test_a_sign_in_made_earlier_gets_its_sources_when_the_app_starts(signing):  # noqa: F811
    from engine import sign_in as flow

    ws, cfg, store, _ = signing
    s = store.plugins.sign_ins()["p18/service"]
    flow.keep(ws.root / ".cockpit" / "keys" / "p18", s, {"access_token": "a", "expires_at": 9e9, "refresh_token": "r"})
    store.close()
    _with_sources(ws)
    _app(ws, cfg)
    assert [s["label"] for s in sources(ws) if s["connector"] == "p18/inbox"] == ["Your inbox"]


def test_a_sign_ins_sources_are_taken_in_quietly(signing):  # noqa: F811
    """A source a sign-in adds reads its first mail the quiet way (one total, one go, one list to look over), not the
    last day's items one by one (design 6.32)."""
    ws, cfg, store, _ = signing
    store.close()
    _with_sources(ws)
    c, api = _app(ws, cfg)
    sign_in(c, api)
    added = [s for s in sources(ws) if s["connector"] == "p18/inbox"]
    assert [s["first_run"] for s in added] == ["intake"]
