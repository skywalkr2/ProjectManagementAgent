"""Plugin API 0.3.45: an answer whose ops depend on each other applies whole or not at all; the person's accept or
send-back raises changeset.reviewed; references are honored deeper; an action can price the runs it queues."""

import json
from datetime import UTC, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.storage import WriteContext
from tests.test_today_panels_jobs import FIXTURE, workspace

TOGETHER = FIXTURE.replace(
    'registrar.task_kind("p18/plan", label="Plan", ops=("note",), on="p18/goal")',
    'registrar.task_kind("p18/plan", label="Plan", ops=("note",), on="p18/goal")\n'
    '    registrar.task_kind("p18/apart", label="Apart", ops=("p18/add-goal",))\n'
    '    registrar.task_kind("p18/both", label="Both", ops=("p18/add-goal",), all_or_nothing=True)',
)
ANSWER = {
    "summary": "Two goals.",
    "ops": [{"op": "p18/add-goal", "title": "One"}, {"op": "p18/add-goal", "title": "Two", "status": "lost"}],
}


def ask(ws, store, cfg, task):
    from engine.ai.router import Router
    from engine.dispatcher import process

    with store.transaction() as tx:
        request = tx.create(
            "request",
            {
                "task": task,
                "origin": "pm",
                "state": "queued",
                "note": "plan",
                "created_at": datetime.now(UTC).isoformat(),
            },
            WriteContext("pm", "trusted", "test"),
        )
    process(ws, store, cfg, Router(cfg, store, env={}), request.id)
    return store.read().get("request", request.id)


@pytest.fixture
def env(tmp_path):
    import yaml

    from engine.storage import Store

    ws, cfg, store = workspace(tmp_path, TOGETHER)
    store.close()
    manifest = ws.root / "plugins" / "p18" / "plugin.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["provides"]["ai_task_kinds"] = ["p18/plan", "p18/apart", "p18/both"]
    manifest.write_text(yaml.safe_dump(data))
    store = Store(ws.db_path, cfg=cfg)
    set_responder(lambda task: json.dumps(ANSWER))
    yield ws, cfg, store
    store.close()
    set_responder(None)


def goals(store):
    return sorted(g.data["title"] for g in store.read().list("p18/goal"))


def test_an_all_or_nothing_answer_applies_whole_or_not_at_all(env):
    ws, cfg, store = env
    assert store.plugins.active("p18"), store.plugins.status["p18"].reason
    assert store.plugins.task_kind("p18/both").all_or_nothing
    ask(ws, store, cfg, "p18/apart")
    assert goals(store) == ["One"]  # independent ops: the good one applied
    ask(ws, store, cfg, "p18/both")
    assert goals(store) == ["One"]  # together: nothing from that answer


def published(store):
    events = []
    original = store.plugins.publish
    store.plugins.publish = lambda event, data, **kw: (events.append((event, data)), original(event, data, **kw))
    return events


def test_accepting_or_sending_back_an_answer_raises_changeset_reviewed(env):
    from engine.dispatcher import looks_good, send_back

    ws, cfg, store = env
    events = published(store)
    accepted = ask(ws, store, cfg, "p18/apart")
    looks_good(store, accepted.data["changeset"])
    payload = next(d for e, d in events if e == "changeset.reviewed")
    assert payload == {
        "id": accepted.data["changeset"],
        "outcome": "accepted",
        "request": accepted.id,
        "task": "p18/apart",
        "part": None,
        "about": None,
    }
    again = ask(ws, store, cfg, "p18/apart")
    send_back(store, again.data["changeset"], "Only one goal, please.")
    sent = [d for e, d in events if e == "changeset.reviewed" and d["outcome"] == "sent_back"]
    assert sent and sent[0]["id"] == again.data["changeset"] and sent[0]["request"] == again.id


def test_references_are_found_six_levels_into_a_record():
    from typing import Annotated, ClassVar

    from pydantic import BaseModel

    from engine.records import MAX_REF_DEPTH, Record, RefTo, ref_fields

    class L6(BaseModel):
        who: Annotated[str, RefTo("person")]

    class L5(BaseModel):
        inner: L6

    class L4(BaseModel):
        inner: L5

    class L3(BaseModel):
        inner: list[L4]

    class L2(BaseModel):
        inner: L3

    class Deep(Record):
        record_kind: ClassVar[str] = "p45/deep"
        prefix: ClassVar[str] = "DEP"
        top: L2

    assert MAX_REF_DEPTH == 6
    assert ("top.inner.inner[].inner.inner.who", "person") in ref_fields(Deep)


def test_an_action_prices_the_runs_it_would_queue(env):
    from engine.ai.router import Router
    from engine.plugin_api import ActionContext, PluginMisuse

    _, cfg, store = env
    router = Router(cfg, store, env={})
    context = ActionContext(
        store.read(),
        "p18",
        store.plugins.registrars["p18"].config,
        None,
        estimator=lambda task, i, o: router.estimate_for(task, i, o),
    )
    priced = context.estimate("p18/apart", 2000, 500)
    assert priced is None or priced >= 0  # None when the account has no listed price
    assert ActionContext(store.read(), "p18", store.plugins.registrars["p18"].config, None).estimate("note", 1) is None
    with pytest.raises(PluginMisuse):
        context.estimate("other/work", 10)
