"""Finding packs (design 3.11): catalog feeds read on request and kept for offline use, what a pack adds, reaches and
keeps written from its manifest, its AI jobs priced on the workspace's own accounts, and the Add-ons routes."""

from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import engine.net
from engine import packs
from engine.config import load_config
from tests.conftest import DEMO_B

FIXTURES = Path(__file__).parent / "fixtures" / "network"
N = yaml.safe_load((FIXTURES / "network.yaml").read_text())
FEED_TEXT = (FIXTURES / "packs.yaml").read_text()
FEED = f"https://{N['catalog_host']}/packs.yaml"


def test_a_feed_keeps_good_entries_and_notes_the_rest():
    feed = packs.parse(FEED, FEED_TEXT)
    assert [e.id for e in feed.entries] == ["bindery"]
    assert any("entry 2" in n for n in feed.notes) and any("listed twice" in n for n in feed.notes)
    assert any("entry 4" in n for n in feed.notes)  # an http homepage is refused
    assert packs.parse(FEED, "just words").error and packs.parse(FEED, "version: 2\npacks: []").error


def test_the_summary_comes_from_the_manifest_not_the_description():
    entry = packs.parse(FEED, FEED_TEXT).entries[0]
    what = packs.summary(entry.provides, entry.requires)
    assert what["adds"]["item_types"] == ["book", "chapter"] and what["adds"]["screens"] == 1
    assert what["adds"]["ai_work"] == 2 and what["adds"]["today"] == 1
    assert what["reaches"] == {
        "sign_ins": ["print service"],
        "hosts": ["print.example.com"],
        "programs": ["ebook-checker"],
        "keys": 1,
    }
    assert what["keeps"] == "restricted"
    assert packs.compatible(entry, "0.3.33") is True and packs.compatible(entry, "0.4.0") is False


def test_feeds_are_kept_and_read_again_only_when_old_or_asked(tmp_path, monkeypatch):
    calls = []

    def serve(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=FEED_TEXT) if len(calls) < 3 else httpx.Response(503)

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(serve))
    first = packs.read_feeds([FEED], tmp_path, 24, now=1000.0)
    assert first[0].entries and len(calls) == 1
    packs.read_feeds([FEED], tmp_path, 24, now=2000.0)
    assert len(calls) == 1  # fresh enough: the kept copy
    packs.read_feeds([FEED], tmp_path, 24, now=2000.0 + 25 * 3600)
    assert len(calls) == 2
    offline = packs.read_feeds([FEED], tmp_path, 24, refresh=True, now=3000.0 + 50 * 3600)
    assert offline[0].entries and "kept earlier" in offline[0].notes[0]


def test_ai_jobs_are_priced_on_the_workspaces_accounts(tmp_path):
    from engine.ai.router import Router
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        job = packs.parse(FEED, FEED_TEXT).entries[0].ai_jobs[0]
        router = Router(cfg, store, env={})
        unpriced = packs.job_cost(cfg, router, job)
        assert unpriced["usd"] is None and unpriced["tokens"] == 10_000 and unpriced["account"]
        use = cfg.ai.tiers["routine"].use
        priced_cfg = load_config(
            ws.config_dir,
            env={},
            flags={f"ai.prices.{use}": {"input_per_million": 1.0, "output_per_million": 4.0}},
        )
        priced = packs.job_cost(priced_cfg, Router(priced_cfg, store, env={}), job)
        assert priced["usd"] == pytest.approx((6000 * 1.0 + 4000 * 4.0) / 1e6)
    finally:
        store.close()


def test_the_add_ons_routes_list_available_and_installed(tmp_path, monkeypatch):
    from api.app import create_app
    from engine.workspace import init_workspace

    monkeypatch.setattr(engine.net, "TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(200, text=FEED_TEXT)))
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["catalog"]["feeds"] = [FEED]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    cfg = load_config(ws.config_dir, env={})
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    body = c.get(f"{api}/packs").json()
    pack = body["available"][0]
    assert pack["id"] == "bindery" and pack["compatible"] is True and pack["installed_version"] is None
    assert pack["homepage_domain"] == N["catalog_host"] and pack["feed"] == N["catalog_host"]
    assert pack["what"]["keeps"] == "restricted" and [j["label"] for j in pack["costs"]][0] == "Drafting a chapter"
    assert body["feeds"][0]["notes"]
    installed = {p["name"]: p for p in body["installed"]}
    assert installed["example"]["enabled"] is ("example" in cfg.workspace.plugins.enabled)  # off in core-only runs
    assert installed["example"]["what"]["adds"]["item_types"] == ["reminder"]
    assert c.post(f"{api}/packs/refresh").status_code == 200
    settings["plugins"]["catalog"]["enabled"] = False
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    off = TestClient(create_app(ws, load_config(ws.config_dir, env={}), "t", start_worker=False))
    off.headers["Authorization"] = "Bearer t"
    assert off.get(f"{api}/packs").json()["available"] == []


def test_the_shipped_feed_template_reads_cleanly():
    template = Path(__file__).parents[1] / "deploy" / "pack-catalog.example.yaml"
    feed = packs.parse(FEED, template.read_text())
    assert len(feed.entries) == 1 and not feed.notes and feed.error is None
