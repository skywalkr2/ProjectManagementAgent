"""Plugin API 0.3.49: a source the person marks as never to be quoted, a plugin setting read under its old name for
one version, a task kind whose answers must include certain ops, and the testing kit's throwaway workspace."""

import pytest
import yaml

from tests.test_today_panels_jobs import FIXTURE, MANIFEST

CODE = (
    FIXTURE.replace(
        "class Config(Settings):\n    pass\n",
        "from pydantic import Field\n\n"
        "class Config(Settings):\n"
        '    limit: int = Field(3, description="How many to show.", json_schema_extra={"renamed_from": "max_items"})\n',
    )
    .replace(
        'registrar.task_kind("p18/plan", label="Plan", ops=("note",), on="p18/goal")',
        'registrar.task_kind("p18/plan", label="Plan", ops=("note",), on="p18/goal")\n'
        '    registrar.task_kind("p18/review", label="Review", ops=("note", "p18/add-goal"),\n'
        '                        requires_ops=("p18/add-goal",))\n'
        '    registrar.subscribe("record.changed", on_changed)\n'
        '    registrar.stages("p18/goal", [{"id": "new", "label": "New"}, {"id": "done", "label": "Done"}])',
    )
    .replace(
        "def register(registrar):\n",
        "def on_changed(payload, context):\n"
        '    if payload.get("kind") == "p18/goal":\n'
        '        context.queue_request("p18/plan", "Plan it", about=("p18/goal", payload["id"]))\n\n'
        "def register(registrar):\n",
    )
)


@pytest.fixture
def plugin(tmp_path):
    folder = tmp_path / "p18"
    folder.mkdir()
    (folder / "fixture.py").write_text(CODE)
    manifest = dict(MANIFEST)
    manifest["provides"] = {
        **MANIFEST["provides"],
        "ai_task_kinds": ["p18/plan", "p18/review"],
        "stages": ["p18/goal"],
    }
    manifest["subscribes"] = ["record.changed"]
    (folder / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    return folder


def test_the_kit_applies_as_the_person_and_the_assistant_and_shows_refusals(plugin, tmp_path):
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        done = ws.apply([{"op": "p18/add-goal", "title": "Map the harbor"}])
        assert done.status == "applied" and done.applied[0]["title"] == "Map the harbor"
        goal = ws.view().find("p18/goal", title="Map the harbor")
        assert goal is not None
        refused = ws.apply([{"op": "record.set", "kind": "project", "id": "PRJ-404", "field": "status", "value": "x"}])
        assert refused.refused
        by_assistant = ws.apply([{"op": "p18/add-goal", "title": "Second"}], as_person=False)
        assert by_assistant.status in ("applied", "held")


def test_the_kit_runs_actions_events_stages_and_the_folder(plugin, tmp_path):
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        ws.apply([{"op": "p18/add-goal", "title": "Map"}])
        goal = ws.view().find("p18/goal", title="Map")
        proposal = ws.action("p18/close", goal)
        assert proposal.summary == "Close Map"
        assert proposal.apply().status in ("applied", "held")
        queued = ws.emit("record.changed", {"kind": "p18/goal", "id": goal.id})
        assert [q["task"] for q in queued] == ["p18/plan"]
        assert ws.stage_status(goal).next == "new"
        assert ws.move_stage(goal, "new").status == "applied"
        assert ws.view().get("p18/goal", goal.id).data["stage"] == "new"
        assert isinstance(ws.folder(), dict)


def test_a_task_kind_that_must_report_gets_a_fix_round_for_an_empty_answer(plugin, tmp_path):
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        assert ws.store.plugins.task_kind("p18/review").requires_ops == ("p18/add-goal",)
        only_a_note = {"summary": "Nothing.", "ops": [{"op": "note", "text": "Nothing to add."}]}
        seen = []

        def answer(task):
            seen.append(task.request)
            if len(seen) == 1:
                return only_a_note
            return {"summary": "One.", "ops": [{"op": "p18/add-goal", "title": "Found one"}]}

        fixed = ws.ask("p18/review", answer=answer)
        assert len(seen) == 2 and "p18/add-goal" in seen[1]
        assert fixed.outcome is not None and fixed.outcome.applied[0]["title"] == "Found one"
        never = ws.ask("p18/review", answer=only_a_note)
        assert never.outcome is not None and never.outcome.status == "rejected" and not never.outcome.applied

    from engine.plugin_api import Registrar

    with pytest.raises(ValueError, match="requires_ops"):
        Registrar("p18", {}, None).task_kind("p18/x", label="X", ops=("note",), requires_ops=("p18/add-goal",))


def test_a_renamed_setting_reads_under_its_old_name_and_is_saved_under_the_new(plugin, tmp_path):
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, settings={"p18": {"max_items": 5}}, root=tmp_path) as ws:
        assert ws.store.plugins.registrars["p18"].config.limit == 5
        assert any("max_items" in note for note in ws.store.plugins.status["p18"].notes)
        from engine.settings import fingerprint, save

        save(
            ws.ws,
            ws.cfg,
            ws.store,
            changes={"plugins/p18.limit": 7},
            reset=[],
            read_fingerprint=fingerprint(ws.ws.config_dir),
        )
        written = yaml.safe_load((ws.ws.config_dir / "plugins" / "p18.yaml").read_text())
        assert written.get("limit") == 7 and "max_items" not in written


def test_a_source_can_be_marked_never_to_quote_and_its_content_stays_fixed(plugin, tmp_path):
    from engine.plugin_api.testing import plugin_workspace

    with plugin_workspace(plugin, root=tmp_path) as ws:
        from datetime import UTC, datetime

        from engine.storage import WriteContext

        with ws.store.transaction() as tx:
            source = tx.create(
                "source",
                {
                    "received_at": datetime.now(UTC).isoformat(),
                    "kind": "pasted",
                    "title": "A pasted page",
                    "content_hash": "a" * 64,
                    "trust": "untrusted",
                },
                WriteContext("pm", "trusted", "test"),
            )
        assert source.data["excerpts"] == "allowed"
        marked = ws.apply(
            [
                {
                    "op": "record.edit",
                    "record": {"kind": "source", "id": source.id},
                    "fields": {"excerpts": "never"},
                    "read_version": source.version,
                }
            ]
        )
        assert marked.status == "applied"
        assert ws.view().get("source", source.id).data["excerpts"] == "never"
        fresh = ws.store.read().get("source", source.id)
        changed = ws.apply(
            [
                {
                    "op": "record.edit",
                    "record": {"kind": "source", "id": source.id},
                    "fields": {"content_hash": "0" * 64},
                    "read_version": fresh.version,
                }
            ]
        )
        assert changed.refused and "can't be changed" in changed.refused[0]
