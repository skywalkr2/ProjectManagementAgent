"""Plugin API 0.3.23: requests about an interface item, fields a definition doesn't declare, refusals shown on a
proposal's items, room left for files, a kind's label in refusals, work linked to the change it follows from, and
stages that apply to some records only."""

import dataclasses

import yaml

from tests import test_interfaces as interfaces
from tests.test_plugin_api_0322 import queueing_workspace
from tests.test_today_panels_jobs import FIXTURE, goals, workspace

ITEM_DEFINER = interfaces.DEFINER.replace('task_kinds=("blurb",)', 'task_kinds=("blurb", "polish")').replace(
    '    context.request_from("p16/source@1", "blurb", note, ("project", payload["project"]))\n',
    '    for item in context.interface("p16/source@1", project=payload["project"]):\n'
    '        context.request_from("p16/source@1", "polish", note, item=item)\n',
)
ITEM_PROVIDER = interfaces.PROVIDER.replace(
    '            "words": w.data["words"],\n', '            "words": w.data["words"],\n            "ref": w.id,\n'
).replace(
    '    registrar.provide_interface("p16/source@1", items=items, task_kinds={"blurb": "p17/blurb"})\n',
    '    registrar.task_kind("p17/polish", label="Polish", ops=("note",), on="p17/work")\n'
    "    registrar.provide_interface(\n"
    '        "p16/source@1", items=items, task_kinds={"blurb": "p17/blurb", "polish": "p17/polish"},\n'
    '        about=lambda view, settings, item: ("p17/work", item["ref"]),\n'
    "    )\n",
)


def item_workspace(tmp_path):
    from engine.storage import Store

    provider = {
        **interfaces.PROVIDER_MANIFEST,
        "provides": {**interfaces.PROVIDER_MANIFEST["provides"], "ai_task_kinds": ["p17/blurb", "p17/polish"]},
    }
    ws, cfg, store = interfaces.workspace(tmp_path, provider=provider, code=ITEM_PROVIDER)
    store.close()
    (ws.root / "plugins" / "p16" / "fixture.py").write_text(ITEM_DEFINER)
    store = Store(ws.db_path, cfg=cfg)
    for name in ("p16", "p17"):
        assert store.plugins.active(name), store.plugins.status[name].reason
    return ws, cfg, store


def test_a_request_can_name_an_interface_item_and_the_provider_says_which_record(tmp_path):
    ws, cfg, store = item_workspace(tmp_path)
    try:
        project = interfaces.a_project(cfg, store)
        cs = interfaces.apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "Harbor map"}])
        work = store.read().list("p17/work")[-1]
        request = store.read().list("request")[-1].data
        assert request["task"] == "p17/polish" and request["about"] == {"kind": "p17/work", "id": work.id}
        assert request["follows"] == cs
    finally:
        store.close()


def test_fields_the_definition_doesnt_declare_are_noted(tmp_path):
    ws, cfg, store = item_workspace(tmp_path)
    try:
        project = interfaces.a_project(cfg, store)
        interfaces.apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "Harbor map"}])
        items = store.plugins.read_interface("p16", "p16/source@1")
        assert "ref" not in items[0].data and items[0].key
        assert any("doesn't declare" in n and "ref" in n for n in store.plugins.status["p17"].notes)
    finally:
        store.close()


def test_a_refused_item_shows_why_and_starts_dropped(tmp_path):
    from engine import actions
    from engine.applier import apply_as_person

    code = FIXTURE.replace(
        "def close(target, context, choices):\n",
        "def name_projects(target, context, choices):\n"
        "    names = ['Harbor', context.list('project')[0].data['name']]\n"
        "    items = [Item(n, 'Add ' + n, [{'op': 'project.add', 'name': n}]) for n in names]\n"
        "    return Proposal('Add projects', items=items, ops=[{'op': 'project.add', 'name': names[1]}])\n\n"
        "def close(target, context, choices):\n",
    ).replace("TodayLine\n", "TodayLine, Item\n")
    code = code.replace(
        '    registrar.action("p18/close", label="Close", run=close, on="p18/goal")\n',
        '    registrar.action("p18/close", label="Close", run=close, on="p18/goal")\n'
        '    registrar.action("p18/projects", label="Add projects", run=name_projects)\n',
    )
    ws, cfg, store = workspace(tmp_path, code)
    store.close()
    manifest_path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["provides"]["actions"].append("p18/projects")
    manifest_path.write_text(yaml.safe_dump(manifest))
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        if not store.read().list("project"):
            apply_as_person(store, cfg, [{"op": "project.add", "name": "Lighthouse"}], "A project")
        taken = store.read().list("project")[0].data["name"]
        pending = actions.preview(store, cfg, "p18/projects")
        by_id = {i["id"]: i for i in pending.items}
        assert by_id["Harbor"]["refused"] is None and by_id["Harbor"]["kept"]
        assert "already a project" in by_id[taken]["refused"] and not by_id[taken]["kept"]
        assert any("already a project" in p for p in pending.problems)
    finally:
        store.close()


def test_limits_give_the_room_left_and_refusals_use_the_kinds_label(tmp_path):
    from engine import actions
    from engine.storage import StoreError

    ws, cfg, store = queueing_workspace(tmp_path)
    try:
        registrar = store.plugins.registrars["p18"]
        seen = {}
        original = registrar.actions["p18/plan-all"].run

        def spy(target, context, choices):
            seen.update(context.limits)
            return original(target, context, choices)

        registrar.actions["p18/plan-all"] = dataclasses.replace(registrar.actions["p18/plan-all"], run=spy)
        actions.preview(store, cfg, "p18/plan-all")
        assert 0 < seen["room_mb"] <= seen["max_total_mb"]
        try:
            actions.preview(store, cfg, "p18/close")
        except StoreError as err:
            assert "works on a goal" in str(err) and "p18/" not in str(err)
        else:
            raise AssertionError("an action on a record needs one")
    finally:
        store.close()


def test_a_stage_that_doesnt_apply_is_passed_over(tmp_path):
    from engine.applier import move_stage
    from engine.ops import StageMoveOp
    from engine.stages import record_status
    from engine.storage import StoreError

    code = FIXTURE.replace(
        "def register(registrar):\n",
        "def is_big(record, view, settings):\n"
        "    return StageCheckResult(record.data['title'].startswith('Big'), 'Only for big goals.')\n\n"
        "def register(registrar):\n"
        '    registrar.stage_check("p18/big", is_big)\n'
        '    registrar.stages("p18/goal", [{"id": "new", "label": "New"}, '
        '{"id": "review", "label": "Review", "applies_if": ["p18/big"]}, {"id": "done", "label": "Done"}])\n',
    ).replace("TodayLine\n", "TodayLine, StageCheckResult\n")
    ws, cfg, store = workspace(tmp_path, code)
    store.close()
    manifest_path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["provides"]["stage_checks"] = ["p18/big"]
    manifest["provides"]["stages"] = ["p18/goal"]
    manifest_path.write_text(yaml.safe_dump(manifest))
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        assert store.plugins.active("p18"), store.plugins.status["p18"].reason
        goals(cfg, store, "Small goal", "Big goal")
        small, big = store.read().list("p18/goal")[-2:]

        def move(record, to):
            fresh = store.read().get(record.kind, record.id)
            return move_stage(
                store, StageMoveOp(record={"kind": record.kind, "id": record.id}, to=to, read_version=fresh.version)
            )

        move(small, "new")
        move(big, "new")
        assert record_status(store, store.read().get(small.kind, small.id))["next"]["id"] == "done"
        assert record_status(store, store.read().get(big.kind, big.id))["next"]["id"] == "review"
        assert [s["id"] for s in record_status(store, store.read().get(small.kind, small.id))["stages"]] == [
            "new",
            "done",
        ]
        try:
            move(small, "review")
        except StoreError as err:
            assert "doesn't apply" in str(err)
        else:
            raise AssertionError("a stage that doesn't apply is refused")
        move(small, "done")
        assert store.read().get(small.kind, small.id).data["stage"] == "done"
        try:
            move(big, "done")
        except StoreError:
            pass
        else:
            raise AssertionError("a stage that applies isn't skipped")
    finally:
        store.close()
