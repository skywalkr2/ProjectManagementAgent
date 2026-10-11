"""The core's web client, the feed connector, and plugins reaching only their declared hosts with their declared
secrets."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from engine.config import load_config
from engine.connectors import ConnectorContext, ConnectorError
from engine.connectors.feed import FeedSettings, parse, read_feed
from engine.net import WebClient
from tests.test_watch import make

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)

FIXTURES = Path(__file__).parent / "fixtures" / "network"
RSS = (FIXTURES / "rss.xml").read_bytes()
ATOM = (FIXTURES / "atom.xml").read_bytes()
N = yaml.safe_load((FIXTURES / "network.yaml").read_text())
NEWS, API, OTHER, ELSEWHERE, EVIL = (
    N[k] for k in ("news_host", "api_host", "other_host", "elsewhere_host", "evil_host")
)


def answering(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url}"
        if key not in routes:
            return httpx.Response(404)
        status, body, headers = routes[key]
        return httpx.Response(status, content=body, headers=headers or {})

    return httpx.MockTransport(handler)


def test_the_web_client_reaches_only_allowed_hosts_over_https():
    client = WebClient([NEWS], transport=answering({f"GET https://{NEWS}/feed": (200, b"ok", None)}))
    assert client.get(f"https://{NEWS}/feed").text == "ok"
    with pytest.raises(ConnectorError) as other:
        client.get(f"https://{ELSEWHERE}/feed")
    assert other.value.kind == "no_access"
    with pytest.raises(ConnectorError) as plain:
        client.get(f"http://{NEWS}/feed")
    assert plain.value.kind == "no_access"


def test_failures_become_connector_error_kinds():
    routes = {
        f"GET https://{API}/a": (401, b"", None),
        f"GET https://{API}/b": (503, b"", None),
        f"GET https://{API}/c": (400, b"pending", None),
        f"GET https://{API}/r": (302, b"", {"location": f"https://{EVIL}/x"}),
    }
    client = WebClient([API], transport=answering(routes))
    kinds = []
    for path in ("a", "b", "missing", "r"):
        with pytest.raises(ConnectorError) as err:
            client.get(f"https://{API}/{path}")
        kinds.append(err.value.kind)
    assert kinds == ["auth", "outage", "not_found", "no_access"]
    assert client.get(f"https://{API}/c").status == 400  # the caller decides what a 400 means

    def offline(request):
        raise httpx.ConnectError("no route to host")

    with pytest.raises(ConnectorError) as gone:
        WebClient([API], transport=httpx.MockTransport(offline)).get(f"https://{API}/a")
    assert gone.value.kind == "offline"


def test_a_feed_is_read_as_items_with_plain_text(tmp_path):
    items = parse(RSS, 10)
    assert [i.key for i in items] == ["n-1", "n-2"]
    assert (
        items[0].text == "The evening ferry leaves at six." and items[0].link == f"https://{NEWS}{N['first_link_path']}"
    )
    atom = parse(ATOM, 10)[0]
    assert (atom.key, atom.title, atom.author, atom.text) == (
        N["atom_key"],
        "Map revised",
        N["atom_author"],
        "New legend.",
    )
    client = WebClient([NEWS], transport=answering({f"GET https://{NEWS}/rss": (200, RSS, None)}))
    poll = read_feed(FeedSettings(url=f"https://{NEWS}/rss"), {}, ConnectorContext(tmp_path, web=client))
    assert len(poll.items) == 2 and poll.complete is False


def test_a_feed_that_declares_entities_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel></channel></rss>'
    with pytest.raises(ConnectorError) as err:
        parse(bomb, 10)
    assert err.value.kind == "no_access"


PLUGIN = """
from pydantic import BaseModel
from engine.plugin_api import ConnectorError, Poll, Settings, SourceItem

class Config(Settings):
    pass

class BoardSettings(BaseModel):
    board: str
    api_host: str
    other_host: str
    elsewhere: bool = False

def poll(settings, state, context):
    token = context.secret("token")
    if token is None:
        raise ConnectorError("auth", "no token yet")
    host = "https://" + (settings.other_host if settings.elsewhere else settings.api_host)
    cards = context.web.get(host + "/boards/" + settings.board, headers={"Authorization": "Bearer " + token}).json()
    context.keep_secret("token", token + "-refreshed")
    return Poll([SourceItem(c["id"], c["title"], c["text"]) for c in cards], {})

def register(registrar):
    registrar.connector("p20/board", label="A board", settings=BoardSettings, poll=poll)
"""


def plugin_workspace(tmp_path, monkeypatch, *, elsewhere=False, secrets=None):
    import engine.net
    from engine.storage import Store

    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        if request.url.host != API:
            return httpx.Response(500)
        return httpx.Response(200, json=[{"id": "c1", "title": "Card", "text": "Ship the map"}])

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(handler))
    source = {
        "id": "b",
        "connector": "p20/board",
        "first_run": "all",
        "settings": {"board": "x", "elsewhere": elsewhere, "api_host": API, "other_host": OTHER},
    }
    ws, cfg, store = make(tmp_path, [source])
    store.close()
    folder = ws.root / "plugins" / "p20"
    folder.mkdir(parents=True)
    (folder / "fixture.py").write_text(PLUGIN)
    manifest = {
        "name": "p20",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Network connector fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "provides": {"connectors": ["p20/board"]},
        "requires": {"network": [API], "secrets": ["token"]},
    }
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "p20"]
    if secrets is not None:
        settings["plugins"]["secrets"] = {"p20": secrets}
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p20"), store.plugins.status["p20"].reason
    return ws, cfg, store, seen


def test_a_plugin_connector_reaches_its_host_with_its_secret(tmp_path, monkeypatch):
    from engine.watch import refresh

    token_file = tmp_path / "token.txt"
    token_file.write_text("abc")
    ws, cfg, store, seen = plugin_workspace(tmp_path, monkeypatch, secrets={"token": f"file:{token_file}"})
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert len(result.new) == 1 and seen["auth"] == "Bearer abc"
        kept = ws.private_dir / "keys" / "p20" / "token"
        assert kept.read_text().strip() == "abc-refreshed" and oct(kept.stat().st_mode)[-3:] == "600"
    finally:
        store.close()


def test_without_a_secret_the_source_asks_to_sign_in(tmp_path, monkeypatch):
    from engine.watch import refresh

    ws, cfg, store, _ = plugin_workspace(tmp_path, monkeypatch)
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert result.outcome == "failed" and "Sign in" in result.problem
    finally:
        store.close()


def test_a_plugin_never_reaches_a_host_it_didnt_declare(tmp_path, monkeypatch):
    from engine.watch import refresh

    ws, cfg, store, _ = plugin_workspace(tmp_path, monkeypatch, elsewhere=True, secrets={"token": "env:P20_TOKEN"})
    monkeypatch.setenv("P20_TOKEN", "abc")
    try:
        result = refresh(ws, store, cfg, "b", NOW)
        assert result.outcome == "failed" and "isn't a host" in result.problem
    finally:
        store.close()
