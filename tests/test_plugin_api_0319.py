"""Plugin API 0.3.19: actions narrowed with `where`, handlers and jobs staging their own ops, the workspace person's
name, alt text on previews, and a project's owner set with record.set."""

import pytest

from tests.test_today_panels_jobs import FIXTURE, goals, workspace

STAGING = (
    FIXTURE.replace(
        '    status: Literal["open", "done"] = "open"\n',
        '    status: Literal["open", "done"] = "open"\n    checked: bool = False\n    kind: str = "plain"\n',
    )
    .replace(
        "def tidy(context):\n",
        "class Mark(OpModel):\n"
        '    op: Literal["p18/mark"] = "p18/mark"\n'
        '    writes: ClassVar[dict] = {"p18/goal": ("checked",)}\n'
        "    goal: str\n"
        "    version: int\n\n"
        "def mark(op, writer, cfg):\n"
        '    writer.update("p18/goal", op.goal, {"checked": True}, read_version=op.version)\n\n'
        "def tidy(context):\n"
        '    for goal in context.list("p18/goal", status="open"):\n'
        '        context.apply_op({"op": "p18/mark", "goal": goal.id, "version": goal.version})\n',
    )
    .replace(
        '    registrar.op(AddGoal, "data", add_goal)\n',
        '    registrar.op(AddGoal, "data", add_goal)\n    registrar.op(Mark, "data", mark)\n'
        '    registrar.action("p18/shout", label="Shout", run=close, on="p18/goal", where={"kind": "loud"})\n',
    )
)


def staging_workspace(tmp_path, code=STAGING):
    import yaml

    ws, cfg, store = workspace(tmp_path, code)
    store.close()
    manifest_path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["provides"]["ops"].append("p18/mark")
    manifest["provides"]["actions"].append("p18/shout")
    manifest_path.write_text(yaml.safe_dump(manifest))
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p18"), store.plugins.status["p18"].reason
    return ws, cfg, store


def test_a_job_stages_its_own_ops_through_the_applier(tmp_path):
    ws, cfg, store = staging_workspace(tmp_path)
    try:
        goals(cfg, store, "Finish the map")
        assert store.plugins.run_job("p18/tidy") == "ok"
        assert store.read().list("p18/goal")[-1].data["checked"] is True
        changeset = store.read().list("changeset")[-1]
        assert changeset.data["summary"].startswith("p18") and changeset.data["trust"] == "untrusted"
    finally:
        store.close()


def test_a_staged_core_op_turns_the_plugin_off(tmp_path):
    core = STAGING.replace(
        '        context.apply_op({"op": "p18/mark", "goal": goal.id, "version": goal.version})\n',
        '        context.apply_op({"op": "note", "text": "x"})\n',
    )
    ws, cfg, store = staging_workspace(tmp_path, core)
    try:
        goals(cfg, store, "Finish the map")
        assert store.plugins.run_job("p18/tidy") == "failed"
        assert "own ops" in store.plugins.status["p18"].reason
    finally:
        store.close()


def test_an_action_is_offered_only_where_its_filter_matches(tmp_path):
    from engine import actions
    from engine.applier import apply_as_person
    from engine.storage import StoreError

    ws, cfg, store = staging_workspace(tmp_path)
    try:
        goals(cfg, store, "Quiet one")
        quiet = store.read().list("p18/goal")[-1]
        offered = [a.name for a in actions.available(store, "p18/goal", quiet.id)]
        assert "p18/close" in offered and "p18/shout" not in offered
        with pytest.raises(StoreError, match="isn't for this"):
            actions.preview(store, cfg, "p18/shout", {"kind": "p18/goal", "id": quiet.id})
        ref = {"kind": "p18/goal", "id": quiet.id}
        apply_as_person(
            store,
            cfg,
            [{"op": "record.edit", "record": ref, "fields": {"kind": "loud"}, "read_version": quiet.version}],
            "x",
        )
        assert "p18/shout" in [a.name for a in actions.available(store, "p18/goal", quiet.id)]
    finally:
        store.close()


def test_the_workspace_persons_name_is_readable(tmp_path):
    from engine.plugin_api import ReadView

    ws, cfg, store = workspace(tmp_path)
    try:
        view = store.plugins._with_files(ReadView(store.read(), "p18"))
        assert view.user == cfg.workspace.user.person
        person = store.read().get("person", cfg.workspace.user.person)
        assert view.person_name() == person.data["full_name"]
        assert view.person_name("PER-999") == ""
    finally:
        store.close()


def test_a_projects_owner_can_be_set(tmp_path):
    from engine.applier import apply_as_person

    ws, cfg, store = workspace(tmp_path)
    try:
        project = store.read().list("project")[0]
        op = {
            "op": "record.set",
            "kind": "project",
            "id": project.id,
            "field": "owner",
            "value": cfg.workspace.user.person,
        }
        apply_as_person(store, cfg, [op], "Set the owner")
        assert store.read().get("project", project.id).data["owner"] == cfg.workspace.user.person
    finally:
        store.close()


def test_a_preview_carries_alt_text():
    from engine.plugin_api import Preview

    assert Preview("p.png", "image/png", b"x", caption="Page one", alt="A title page in serif type").alt
