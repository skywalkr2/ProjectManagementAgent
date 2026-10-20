"""Review and send lines carry the project they are about, so a row can tag it when Today mixes projects (design 7.7).

A review line takes the project the person named for the request, else the one its work is about, else the one every
change names; a send or nudge line takes the one project everything it lists belongs to, and none when they differ.
Names and ids come from the fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
TODAY = NOW.date()
_TEST = WriteContext(actor="pm", trust="trusted", op="test.line-projects")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={"COCKPIT__WORKSPACE__USER__TIMEZONE": "UTC"})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def me(cfg) -> str:
    return cfg.workspace.user.person


def other(cfg) -> str:
    return next(p["id"] for p in fixture_records(DEMO_B, "person") if p["id"] != me(cfg))


def projects(store) -> list[str]:
    """The fixture's first project and one more, made here, so a test can tell two projects apart."""
    known = [p.id for p in store.read().list("project")]
    with store.transaction() as tx:
        made = tx.create("project", {"name": "A second fictional book"}, _TEST).id
    return [known[0], made]


def lines(env, kind):
    ws, cfg, store = env
    return [x for x in queue(ws, store, cfg, NOW) if x.kind == kind]


def a_review(store, *, project=None, op_projects=()):
    """A request whose work waits for a look, with a changeset that applied one action per project in `op_projects`."""
    with store.transaction() as tx:
        cs = tx.create(
            "changeset",
            {
                "request": "REQ-0",
                "summary": "Filed.",
                "status": "applied",
                "trust": "trusted",
                "created_at": NOW.isoformat(),
                "ops": [
                    {
                        "index": i,
                        "status": "applied",
                        "op": {"op": "action.add", "text": f"Do thing {i}", "project": p},
                        "label": f"Do thing {i}",
                    }
                    for i, p in enumerate(op_projects)
                ],
            },
            _TEST,
        )
        req = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "pm",
                "state": "review",
                "changeset": cs.id,
                "project": project,
                "created_at": NOW.isoformat(),
            },
            _TEST,
        )
    return req.id


def test_a_review_line_takes_the_project_the_person_named_for_the_request(env):
    _, _, store = env
    first, second, *_ = projects(store)
    request = a_review(store, project=first, op_projects=[second])
    (line,) = [x for x in lines(env, "review") if x.request == request]
    assert line.project == first


def test_a_review_line_takes_the_one_project_every_change_names_and_none_when_they_differ(env):
    _, _, store = env
    first, second, *_ = projects(store)
    one = a_review(store, op_projects=[first, first])
    many = a_review(store, op_projects=[first, second])
    found = {x.request: x.project for x in lines(env, "review")}
    assert found[one] == first and found[many] is None


def a_sent_question(store, to, project, *, days_ago=0):
    sent = (NOW - timedelta(days=days_ago)).isoformat()
    with store.transaction() as tx:
        return tx.create(
            "question",
            {"to": to, "title": "Can the proofs ship?", "status": "sent", "sent_at": sent, "projects": [project]},
            _TEST,
        ).id


def an_unsent_question(store, to, project):
    with store.transaction() as tx:
        return tx.create(
            "question", {"to": to, "title": "Who prints it?", "status": "open", "projects": [project]}, _TEST
        ).id


def test_a_send_line_carries_the_project_all_its_questions_share_and_none_when_they_differ(env):
    _, cfg, store = env
    first, second, *_ = projects(store)
    who = other(cfg)
    an_unsent_question(store, who, first)
    (line,) = [x for x in lines(env, "send") if x.person == who]
    assert line.project == first
    an_unsent_question(store, who, second)
    (line,) = [x for x in lines(env, "send") if x.person == who]
    assert line.project is None


def test_a_nudge_line_carries_the_project_of_what_is_waiting(env):
    _, cfg, store = env
    first, *_ = projects(store)
    who = other(cfg)
    a_sent_question(store, who, first, days_ago=cfg.ui.followups.question_after_days + 3)
    (line,) = [x for x in lines(env, "nudge") if x.person == who]
    assert line.project == first
