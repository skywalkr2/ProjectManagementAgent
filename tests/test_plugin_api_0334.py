"""Plugin API 0.3.34: work that answers with ops can be about part of a text; a hand-in can say which project it is
about, which the reading sees and which candidates functions get; and each piece of AI work an action offers is kept
or dropped on the review."""

import sys
from datetime import date

import pytest
import yaml

from engine.storage import StoreError
from tests.test_plugin_api_0329 import CREATING, reopen, with_manifest
from tests.test_today_panels_jobs import FIXTURE, MANIFEST, workspace


def test_work_that_answers_with_ops_can_name_a_span():
    from engine.tasks import TaskKind
    from engine.texts import check_part

    review = TaskKind("p/review", ("note",), "notes", "notes")
    assert check_part(review, {"first": 2, "last": 3}) == {"first": 2, "last": 3, "base": None}
    with pytest.raises(ValueError, match="paragraph numbers it reads"):
        check_part(review, {"after": "end"})


NAMING = FIXTURE.replace(
    'registrar.op(AddGoal, "data", add_goal)',
    'registrar.op(AddGoal, "data", add_goal, notes=True, candidates=named)',
).replace(
    "def register(registrar):\n",
    "ASKED = []\n\ndef named(view, settings, project):\n"
    "    ASKED.append(project)\n"
    "    return [(g.id, g.data['title']) for g in view.list('p18/goal')]\n\n"
    "def register(registrar):\n",
)


def test_a_hand_in_names_its_project_for_the_reading_and_the_candidates(tmp_path):
    from engine.intake import IntakeError, hand_in
    from engine.packet import build

    ws, cfg, store = workspace(tmp_path, NAMING)
    store.close()
    (ws.root / "plugins" / "p18" / "plugin.yaml").write_text(yaml.safe_dump(MANIFEST))
    cfg, store = reopen(ws, cfg)
    try:
        project = store.read().list("project")[0]
        handed = hand_in(ws, store, note="Add a goal for the map", project=project.id)
        packet = build(ws, store, cfg, handed.request, date(2030, 3, 4))
        assert f"This is about the project {project.data['name']} ({project.id})." in packet.task.request
        asked = next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "ASKED")).ASKED
        assert asked[-1] == project.id
        with pytest.raises(IntakeError, match="no project"):
            hand_in(ws, store, note="x", project="PRJ-404")
    finally:
        store.close()


def test_each_offered_request_is_kept_or_dropped_on_the_review(tmp_path):
    from engine import actions

    ws, cfg, store = workspace(tmp_path, CREATING)
    store.close()
    with_manifest(ws, actions=["p18/close", "p18/make"])
    cfg, store = reopen(ws, cfg)
    try:
        pending = actions.preview(store, cfg, "p18/make")
        assert [r["id"] for r in pending.requests] == ["r1", "r2", "r3"] and all(r["kept"] for r in pending.requests)
        with pytest.raises(StoreError, match="no request r9"):
            actions.apply(store, cfg, pending.token, {}, {"r9": False})
        pending = actions.preview(store, cfg, "p18/make")
        actions.apply(store, cfg, pending.token, {}, {"r3": False})
        goals = {g.id: g.data["title"] for g in store.read().list("p18/goal")}
        planned = [goals[r.data["about"]["id"]] for r in store.read().list("request") if r.data["task"] == "p18/plan"]
        assert planned == ["A"]  # r2's item was dropped by the plugin's default, r3 by the person
    finally:
        store.close()
