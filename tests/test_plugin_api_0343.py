"""Plugin API 0.3.43: a plugin reads records of a project together with those of the projects above or below it."""

import pytest

from engine.config import load_config
from engine.plugin_api import PluginMisuse, ReadView
from engine.storage import WriteContext
from tests.conftest import DEMO_B

W = WriteContext("pm", "trusted", "test")


@pytest.fixture
def family(tmp_path):
    """A series with two books, the first with a part of its own; an action in each."""
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    store = Store(ws.db_path, cfg=load_config(ws.config_dir, env={}))
    me = store.read().list("person")[0].id
    with store.transaction() as tx:
        series = tx.create("project", {"name": "Series"}, W).id
        one = tx.create("project", {"name": "One", "parent": series}, W).id
        two = tx.create("project", {"name": "Two", "parent": series}, W).id
        part = tx.create("project", {"name": "Part", "parent": one}, W).id
        for pid in (series, one, two, part):
            tx.create("action", {"text": f"Do {pid}", "project": pid, "owners": [{"person": me}]}, W)
    yield store, series, one, two, part
    store.close()


def projects_of(found):
    return [r.data["project"] for r in found]


def test_ancestors_and_descendants_in_nearest_first_order(family):
    store, series, one, two, part = family
    view = ReadView(store.read(), "p43")
    assert projects_of(view.list("action", project=part, ancestors=True)) == [part, one, series]
    assert projects_of(view.list("action", project=series, descendants=True)) == [series, one, two, part]
    assert projects_of(view.list("action", project=one, ancestors=True, descendants=True)) == [one, series, part]
    assert projects_of(view.list("action", project=one)) == [one]
    assert view.list("action", project=part, ancestors=True, text=f"Do {series}")[0].data["project"] == series
    with pytest.raises(PluginMisuse):
        view.list("action", project=None, ancestors=True)
