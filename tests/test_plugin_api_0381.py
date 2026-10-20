"""Plugin API 0.3.81: a plugin's Today line names the group of the queue it belongs in.

The group is one of the core's own (decide, risk, review, send); anything else fails the contributor like any bad line,
and a line with no group stays valid, shows under the fallback heading and is warned about by the plugin check.
"""

import logging

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.config import load_config
from engine.plugin_api import PLUGIN_API_VERSION, TODAY_GROUPS
from tests.conftest import DEMO_B

FIXTURE = """
from engine.plugin_api import Settings, TodayLine

class Config(Settings):
    pass

def lines(view, settings):
    return [
        TodayLine("late", "Approve the post for Friday", group="review", until="2026-10-23"),
        TodayLine("early", "Reply to the printer", group="review", until="2026-10-20"),
        TodayLine("loose", "Look at the numbers"),
    ]

def bad(view, settings):
    return [TodayLine("odd", "Not a group", group="first")]

def register_open(registrar):
    registrar.today("g81/open", lines=lines)

def register_bad(registrar):
    registrar.today("g81/bad", lines=bad)
"""


def manifest(today):
    entry = "fixture:register_bad" if today == ["g81/bad"] else "fixture:register_open"
    return {
        "name": "g81",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Today lines with groups",
        "entry": entry,
        "config_schema": "fixture:Config",
        "provides": {"today": today},
    }


def workspace(tmp_path, today):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "g81"
    plugin.mkdir(parents=True)
    (plugin / "fixture.py").write_text(FIXTURE)
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest(today)))
    settings = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    settings["plugins"]["enabled"] = [*settings["plugins"]["enabled"], "g81"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(settings))
    storage = yaml.safe_load((ws.config_dir / "storage.yaml").read_text())
    storage["backups"]["automatic"] = False
    (ws.config_dir / "storage.yaml").write_text(yaml.safe_dump(storage))
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def test_the_version_is_this_one_or_later_and_the_groups_are_the_cores():
    assert tuple(int(n) for n in PLUGIN_API_VERSION.split(".")) >= (0, 3, 81)
    assert TODAY_GROUPS == ("decide", "risk", "review", "send")


def test_a_line_names_its_group_and_one_without_is_still_a_line_and_warned_about_once(tmp_path, caplog):
    ws, cfg, store = workspace(tmp_path, ["g81/open"])
    assert store.plugins.active("g81"), store.plugins.status["g81"].reason
    with caplog.at_level(logging.WARNING):
        found = store.plugins.today()
        store.plugins.today()
    groups = {line.id: line.group for _, line in found}
    assert groups == {"late": "review", "early": "review", "loose": None}
    warned = [r for r in caplog.records if "name no group" in r.getMessage()]
    assert len(warned) == 1 and "g81" in warned[0].getMessage()
    store.close()


def test_the_api_carries_each_lines_group(tmp_path):
    from api.app import create_app

    ws, cfg, store = workspace(tmp_path, ["g81/open"])
    store.close()
    app = create_app(ws, cfg, "test-token", start_worker=False)
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as client:
        lines = client.get("/api/plugin-today").json()
    assert {line["id"]: line["group"] for line in lines} == {"late": "review", "early": "review", "loose": None}


def test_a_group_that_is_not_the_cores_fails_the_contributor_like_any_bad_line(tmp_path):
    ws, cfg, store = workspace(tmp_path, ["g81/bad"])
    assert store.plugins.today() == []
    assert any("group" in n for n in store.plugins.status["g81"].notes)
    store.close()


def test_the_plugin_check_warns_about_lines_with_no_group_without_failing(tmp_path):
    from engine.pack_check import check

    ws, cfg, store = workspace(tmp_path, ["g81/open"])
    store.close()
    report = check(ws.root / "plugins" / "g81")
    assert report.ok, report.failed
    assert any("no group" in w for w in report.warned)
    assert any(line.startswith("WARN") for line in report.lines())


@pytest.mark.parametrize("name", TODAY_GROUPS)
def test_each_core_group_is_accepted(name):
    from engine.plugin_api import TodayLine

    assert TodayLine("x", "A line", group=name).group == name
