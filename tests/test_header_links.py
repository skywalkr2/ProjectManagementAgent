"""Links to the person's own pages (design 7.1, 7.9; roadmap B-6b): a list of names and web addresses in Settings that
the header shows, each opening in a new tab. It is a config key with a schema, a default, a description and demo values.
The names and addresses come from the fictional workspaces' settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.config.schema import UiFile
from engine.settings import describe, fingerprint, save
from engine.storage import Store
from engine.worker import is_live
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, FIXTURES

WEB = "https" + "://"


def demo_links(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    return ws, ws.config(env={}).ui.links


def test_a_new_workspace_has_no_links_and_the_key_is_described():
    assert UiFile().links == []
    description = UiFile.model_fields["links"].description or ""
    assert "header" in description.lower() and "new tab" in description.lower()


def test_a_link_is_a_name_and_a_web_address_and_nothing_else(tmp_path):
    _, links = demo_links(tmp_path)
    ok = UiFile.model_validate({"links": links})
    assert ok.links == links
    here = links[0]["address"]
    for bad in (
        {"name": "", "address": here},
        {"name": "x" * 41, "address": here},
        {"name": "No scheme", "address": here.removeprefix(WEB)},
        {"name": "Script", "address": "javascript:alert(1)"},
        {"name": "File", "address": "file:///etc/passwd"},
        {"name": "Spaces", "address": f"{here} more"},
        {"name": "Extra", "address": here, "icon": "x"},
        {"name": "Missing"},
    ):
        with pytest.raises(ValidationError):
            UiFile.model_validate({"links": [bad]})
    with pytest.raises(ValidationError):
        UiFile.model_validate({"links": [{"name": str(i), "address": here} for i in range(40)]})


def test_a_links_words_are_trimmed(tmp_path):
    _, links = demo_links(tmp_path)
    padded = UiFile.model_validate(
        {"links": [{"name": f"  {links[0]['name']} ", "address": f" {links[0]['address']}  "}]}
    )
    assert padded.links == [links[0]]


@pytest.mark.parametrize("demo", FIXTURES, ids=lambda p: p.name)
def test_both_fictional_workspaces_have_demo_links_on_example_dot_com(demo, tmp_path):
    ws = init_workspace(tmp_path / "ws", template=demo, git=False)
    links = ws.config(env={}).ui.links
    assert len(links) >= 2 and all(link["address"].startswith(WEB) and ".example." in link["address"] for link in links)


def test_the_screens_can_change_the_list_and_it_takes_effect_without_a_restart(tmp_path):
    ws, links = demo_links(tmp_path)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        item = next(s for s in describe(cfg, store.plugins, ws.config_dir) if s.key == "ui.links")
        assert item.editable and item.type == "other" and item.value == links
        changed = [{"name": "Release board", "address": links[0]["address"]}]
        saved = save(
            ws, cfg, store, changes={"ui.links": changed}, reset=[], read_fingerprint=fingerprint(ws.config_dir)
        )
        assert [c["key"] for c in saved.changes] == ["ui.links"]
        assert ws.config(env={}).ui.links == changed
        assert is_live("ui.links")
        with pytest.raises(Exception, match="web address"):
            save(
                ws,
                cfg,
                store,
                changes={"ui.links": [{"name": "Bad", "address": "ftp://x"}]},
                reset=[],
                read_fingerprint=saved.fingerprint,
            )
    finally:
        store.close()
