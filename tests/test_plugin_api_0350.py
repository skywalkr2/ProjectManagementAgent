"""Plugin API 0.3.50: a suggested mapping keeps the person's own values, stage status carries the stages' names,
computed cells can share work across one listing, and the testing kit saves workspaces, shows what a plugin
registered and its status, and says plainly when a plugin didn't start."""

import pytest
import yaml

from tests.test_plugin_api_0349 import plugin  # noqa: F401 - the fixture


def test_a_suggested_mapping_keeps_the_persons_values():
    from api.setup_routes import _merged

    mine = {"mature": "My own words.", "nested": {"a": 1}}
    suggested = {"mature": "The add-on's words.", "new": "Added.", "nested": {"a": 2, "b": 3}}
    assert _merged(mine, suggested) == {"mature": "My own words.", "new": "Added.", "nested": {"a": 1, "b": 3}}


def test_the_kit_saves_a_workspace_and_starts_tests_from_fresh_copies(plugin, tmp_path):  # noqa: F811
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path / "one") as ws:
        ws.apply([{"op": "p18/add-goal", "title": "Built once"}])
        saved = ws.save(tmp_path / "saved")
        assert ws.view().find("p18/goal", title="Built once") is not None  # still usable after saving
    for n in range(2):
        with plugin_workspace(from_saved=saved, root=tmp_path / f"copy{n}") as copy:
            assert copy.plugins == ["p18"]
            assert copy.view().find("p18/goal", title="Built once") is not None
            copy.apply([{"op": "p18/add-goal", "title": f"Only in copy {n}"}])
            assert copy.view().find("p18/goal", title=f"Only in copy {1 - n}") is None


def test_the_kit_shows_what_a_plugin_registered_and_its_status(plugin, tmp_path):  # noqa: F811
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        registered = ws.registered()
        assert set(registered["actions"]) == {"p18/close"}
        assert "p18/review" in registered["tasks"] and "p18/goals" in registered["panels"]
        with pytest.raises(TypeError):
            registered["actions"]["p18/other"] = None  # read-only
        assert ws.status().state == "enabled"


def test_a_plugin_that_doesnt_start_raises_a_typed_error_or_opens_to_look_at(plugin, tmp_path):  # noqa: F811
    from engine.plugin_api.testing import PluginDidNotStart, plugin_workspace

    (plugin / "fixture.py").write_text("def register(registrar):\n    raise RuntimeError('broken on purpose')\n")
    with pytest.raises(PluginDidNotStart) as failed, plugin_workspace(plugin, root=tmp_path / "strict"):
        pass
    assert failed.value.plugin == "p18" and failed.value.reason
    with plugin_workspace(plugin, root=tmp_path / "loose", require_started=False) as ws:
        assert ws.status().state != "enabled" and ws.status().reason
        assert ws.registered() == {}


def test_stage_status_names_the_stages_and_computed_cells_share_a_listing(tmp_path):
    from tests.test_plugin_api_0348 import CODE, MANIFEST, workspace

    code = CODE.replace(
        'def words(record, view, settings):\n    return len(record.data["words"].split())',
        "def words(record, view, settings, shared):\n"
        "    shared['calls'] = shared.get('calls', 0) + 1\n"
        "    return shared['calls']",
    )
    ws, cfg, store = workspace(tmp_path, code)
    store.close()
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = dict(MANIFEST)
    manifest["provides"] = {
        "record_types": ["p18/goal", "p18/entry"],
        "ops": ["p18/add-goal", "p18/add-entry"],
        "actions": ["p18/close"],
        "today": ["p18/open-goals", "p18/bad"],
        "panels": ["p18/goals", "p18/entries", "p18/shared"],
        "stage_checks": ["p18/big", "p18/asks"],
        "stages": ["p18/goal"],
        "setup_steps": ["p18/unpriced", "p18/levels"],
    }
    path.write_text(yaml.safe_dump(manifest))
    from engine.applier import apply_as_person
    from engine.plugin_api import ReadView
    from tests.test_plugin_api_0329 import reopen

    cfg, store = reopen(ws, cfg)
    try:
        apply_as_person(store, cfg, [{"op": "p18/add-goal", "title": "Big one"}], "Add")
        goal = store.read().list("p18/goal")[-1]
        apply_as_person(
            store, cfg, [{"op": "p18/add-entry", "goal": goal.id}, {"op": "p18/add-entry", "goal": goal.id}], "Add"
        )
        status = store.plugins._with_files(ReadView(store.read(), "p18")).stage_status(goal)
        assert status.current_label is None and status.next_label == "New"
        rows = store.plugins.panel_rows("p18/entries")
        assert [r["values"]["count"] for r in rows] == [1, 2]  # one shared dict across the listing
        assert [r["values"]["count"] for r in store.plugins.panel_rows("p18/entries")] == [1, 2]  # new per listing
    finally:
        store.close()
