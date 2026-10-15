"""Phase L3, the last items (design 6.16, 6.22, 6.8): the learning runs for the catch-up list are queued once and held
for one go with one total; the router never falls through to a backup account that can't stand in; a send-back's packet
shows the items its work touched as they are now. Names and ids come from the fixtures; the AI is the stub.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import catch_up, learn
from engine import packet as packets
from engine.ai.adapters.stub import set_responder
from engine.ai.checked import remember
from engine.ai.router import NoProvider, Router, choices
from engine.ai.smoke import account_test
from engine.ai.task import AiError, AiTask
from engine.config.schema import Price
from engine.dispatcher import process, send_back
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, connection_answer, fixture_records
from tests.test_knowledge_records import lesson_saying, proposal
from tests.test_learn_correction import NOTHING, interior, run_learning, scripted
from tests.test_quality import add_account, first_run_env

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 15)
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
ACTION = fixture_records(DEMO_B, "action")[0]["id"]
QUESTION = fixture_records(DEMO_B, "question")[0]["id"]
_TEST = WriteContext(actor="pm", trust="trusted", op="test.catch-up-learning")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    cfg.ai.prices["stub/default"] = Price(input_per_million=10.0, output_per_million=10.0)
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def earlier(store, kind: str, refs: list[str], minute: int = 0, at: datetime | None = None) -> str:
    """A correction recorded before the assistant could learn from it: a signal with no learning request."""
    at = (at or NOW.replace(hour=8, minute=minute)).isoformat()
    with store.transaction() as tx:
        return tx.create(
            "signal", {"kind": kind, "refs": refs, "changeset": None, "run": None, "note": None, "at": at}, _TEST
        ).id


def three_kinds(store) -> dict[str, list[str]]:
    """Two undos of the same kind of thing, a send-back and a dropped question: three kinds of correction."""
    return {
        "undone": [earlier(store, "undone", [ACTION], 1), earlier(store, "undone", [ACTION], 2)],
        "sent_back": [earlier(store, "sent_back", [ACTION], 3)],
        "dropped": [earlier(store, "dropped", [QUESTION], 4)],
    }


def learning(store) -> list:
    return [r for r in store.read().list("request") if r.data["task"] == learn.TASK]


# ---- the catch-up list's learning runs -------------------------------------------------------------------------------


def test_the_catch_up_learning_is_queued_once_for_each_kind_and_held_for_one_go_with_one_total(env):
    ws, cfg, store = env
    found = three_kinds(store)
    catch_up.start(store, cfg, NOW)
    made = catch_up.queue_learning(ws, store, cfg, now=NOW)
    held = learning(store)
    assert sorted(made) == sorted(r.id for r in held) and len(held) == 3, "one run for each kind of correction"
    # Each kind is learned from through its newest correction, and nothing runs or is spent before the go.
    assert {r.data["about"]["id"] for r in held} == {found["undone"][1], found["sent_back"][0], found["dropped"][0]}
    for r in held:
        assert (r.data["state"], r.data["approval"], r.data["waiting"]) == ("needs_you", "required", catch_up.WAITING)
        assert r.data["estimate_usd"] > 0
    assert not store.read().has("run")
    # Today has one line with the count and the total, and no line of its own for each run.
    lines = queue(ws, store, cfg, NOW)
    (batch,) = [x for x in lines if x.kind == "catch_up_go"]
    assert batch.count == 3 and batch.unpriced == 0
    assert batch.estimate_usd == pytest.approx(sum(r.data["estimate_usd"] for r in held))
    assert not [x for x in lines if x.kind in ("go", "refused", "failed")]
    # Running it again queues nothing new.
    assert catch_up.queue_learning(ws, store, cfg, now=NOW) == []
    assert len(learning(store)) == 3
    # The go starts them all; a run then goes through the usual path.
    assert catch_up.grant_go(store) == 3
    assert {(r.data["state"], r.data["approval"]) for r in learning(store)} == {("queued", "granted")}
    assert not [x for x in queue(ws, store, cfg, NOW) if x.kind == "catch_up_go"]
    scripted(NOTHING)
    run_learning(env, held[0].id, at=NOW)
    assert store.read().get("request", held[0].id).data["state"] != "queued"
    assert store.read().has("run")


def test_a_kind_already_learned_from_or_netted_out_or_already_queued_is_skipped(env):
    ws, cfg, store = env
    found = three_kinds(store)
    state = catch_up.start(store, cfg, NOW)
    # Learned from: an entry cites one of the kind's corrections.
    proposal(store, cfg, {**lesson_saying("Learned from an undo."), "signal": found["undone"][0]})
    # Netted out: the newest correction of a kind was undone, so it doesn't teach; its only correction is skipped.
    netted = store.read().get("signal", found["dropped"][0])
    with store.transaction() as tx:
        tx.create(
            "request",
            {
                "task": learn.TASK,
                "about": {"kind": "signal", "id": netted.id},
                "origin": "schedule",
                "state": "done",
                "waiting": learn.NETTED_WAITING,
                "created_at": NOW.isoformat(),
            },
            _TEST,
        )
    made = catch_up.queue_learning(ws, store, cfg, now=NOW)
    assert [store.read().get("request", r).data["about"]["id"] for r in made] == found["sent_back"]
    assert [g.key[0] for g in catch_up.waiting(store.read(), state)] == ["dropped", "sent_back"]
    # A kind with a learning request already queued is covered, whatever the request's state.
    assert catch_up.queue_learning(ws, store, cfg, now=NOW) == []


def test_a_kind_is_learned_from_through_an_older_correction_when_the_newest_was_netted_out(env):
    ws, cfg, store = env
    older, newest = earlier(store, "undone", [ACTION], 1), earlier(store, "undone", [ACTION], 2)
    catch_up.start(store, cfg, NOW)
    with store.transaction() as tx:
        tx.create(
            "request",
            {
                "task": learn.TASK,
                "about": {"kind": "signal", "id": newest},
                "origin": "schedule",
                "state": "done",
                "waiting": learn.NETTED_WAITING,
                "created_at": NOW.isoformat(),
            },
            _TEST,
        )
    (made,) = catch_up.queue_learning(ws, store, cfg, now=NOW)
    assert store.read().get("request", made).data["about"]["id"] == older


def test_nothing_is_queued_while_learning_is_off_or_before_the_list_is_made(env):
    ws, cfg, store = env
    three_kinds(store)
    assert catch_up.queue_learning(ws, store, cfg, now=NOW) == [], "no list yet"
    catch_up.start(store, cfg, NOW)
    cfg.dispatch.knowledge.learn = False
    assert catch_up.queue_learning(ws, store, cfg, now=NOW) == [] and learning(store) == []


def test_the_worker_queues_the_catch_up_learning_once_when_it_starts_and_the_go_runs_it(env):
    from engine.worker import Events, Worker

    ws, cfg, store = env
    three_kinds(store)
    catch_up.start(store, cfg, NOW)
    worker = Worker(ws, store, cfg, Events(), lambda: Router(cfg, store, env={}))
    assert len(worker.queue_catch_up_learning()) == 3
    assert worker.queue_catch_up_learning() == [], "once for each start of the app"
    scripted(NOTHING)
    assert worker.run_pending() == 0, "held runs are not processed"
    assert catch_up.grant_go(store) == 3
    assert worker.run_pending() == 3


def test_the_go_route_starts_the_held_runs_and_today_has_one_line_for_them_and_the_changes_list_none(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={}, flags={"storage.backups.automatic": False})
    cfg.ai.prices["stub/default"] = Price(input_per_million=10.0, output_per_million=10.0)
    application = create_app(ws, cfg, "catch-up-token", ui_dist=tmp_path / "no-ui", start_worker=False)
    with TestClient(application, headers={"Authorization": "Bearer catch-up-token"}) as client:
        store = application.state.store
        before = datetime.now(UTC) - timedelta(hours=1)
        earlier(store, "undone", [ACTION], at=before)
        earlier(store, "dropped", [QUESTION], at=before)
        catch_up.state_path(store).unlink()
        catch_up.start(store, cfg)
        assert len(catch_up.queue_learning(ws, store, cfg)) == 2
        lines = [x for x in client.get("/api/today/queue").json() if x["kind"] == "catch_up_go"]
        assert [(x["group"], x["count"], x["unpriced"]) for x in lines] == [("decide", 2, 0)]
        assert lines[0]["estimate_usd"] > 0
        assert not [c for c in client.get("/api/changes").json() if c["state"] == "needs_you"]
        assert client.post("/api/knowledge/catch-up/go").json() == {"started": 2}
        assert client.post("/api/knowledge/catch-up/go").json() == {"started": 0}
        assert not [x for x in client.get("/api/today/queue").json() if x["kind"] == "catch_up_go"]
        assert {c["state"] for c in client.get("/api/changes").json()} == {"queued"}


# ---- an unchecked backup is skipped at run time ----------------------------------------------------------------------

TASK = AiTask(kind="notes", instructions="Do it.", stable="Reference.", request="Input.", output_schema={})


def providers_called(store) -> set[str]:
    return {r.data["provider"] for r in store.read().list("run")}


def test_the_router_skips_an_unchecked_or_failed_backup_and_takes_a_checked_or_accepted_one(env):
    ws, _, store = env
    cfg, router = first_run_env(ws, store)  # the main account is down; "second" is the one backup
    cfg.ai.providers["second"].accepted_unchecked = False
    # Never checked: the backup is not tried, so the main account's failure is the answer.
    with pytest.raises(AiError) as failed:
        router.call(TASK, request_id=None)
    assert failed.value.kind == "provider_down" and providers_called(store) == {"stub"}
    # Accepted without a check: it stands in.
    cfg.ai.providers["second"].accepted_unchecked = True
    _, choice, _ = router.call(TASK, request_id=None)
    assert choice.provider == "second"
    # A failed check is skipped even when the person accepted the account.
    set_responder(lambda task: (_ for _ in ()).throw(AiError("other", "refused")))
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    with pytest.raises(AiError):
        router.call(TASK, request_id=None)
    # Checked and passed: it stands in again.
    set_responder(connection_answer)
    remember(ws, cfg, account_test(cfg, {}, "second", tier="routine", store=store))
    cfg.ai.providers["second"].accepted_unchecked = False
    _, choice, _ = router.call(TASK, request_id=None)
    assert choice.provider == "second"


def test_when_skipping_an_unchecked_backup_leaves_no_account_the_run_waits_with_the_usual_stop_and_line(env):
    ws, _, store = env
    add_account(ws, "second")
    cfg = ws.config(env={}, flags={"ai.tiers.routine.fallback": ["second/default"]})
    cfg.ai.providers["stub"].allowed_data = ["open"]
    cfg.ai.providers["second"].allowed_data = ["open", "internal", "restricted"]
    # With the backup allowed to count, it would take internal material; unchecked, it is left out.
    assert [c.provider for c in choices(cfg, "notes", "internal")] == ["second"]
    with pytest.raises(NoProvider, match="second"):
        choices(cfg, "notes", "internal", unchecked={("routine", "second/default")})
    with pytest.raises(NoProvider, match="backup"):
        Router(cfg, store, env={}).call(TASK, request_id=None, data_level="internal")
    # The run's request stops for the person with that reason, as any run no account can take does.
    from engine.intake import hand_in

    request = hand_in(ws, store, pasted="Interior files are due.", now=NOW).request
    process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
    stopped = store.read().get("request", request).data
    assert stopped["state"] == "needs_you" and not store.read().has("run")
    assert "backup" in stopped["waiting"]


# ---- a send-back's packet carries the items as they are now ----------------------------------------------------------


def test_a_send_backs_packet_shows_each_item_the_work_touched_as_it_is_now_and_where_it_is(env):
    ws, cfg, store = env
    cs_id, action, words = interior(env)
    # Sent back and taken back: the action the work made is gone, and the packet says so before anything changes.
    redo = send_back(store, cs_id, "Send it to the editor first.", now=NOW)
    packet = packets.build(ws, store, cfg, redo, TODAY).task.request
    assert "The earlier work, as it stands now" in packet
    block = packet.split("The earlier work, as it stands now", 1)[1]
    assert action in block and "taken back when the work was sent back" in block and '"gone": true' in block
    assert "Send it to the editor first." in packet


def test_a_send_back_that_keeps_the_work_shows_the_items_as_they_stand_after_later_changes(env):
    ws, cfg, store = env
    cs_id, action, _ = interior(env)
    redo = send_back(store, cs_id, "Move the date.", now=NOW, undo_first=False)
    with store.transaction() as tx:
        current = tx.get("action", action)
        tx.update(
            "action", action, {"text": "Reworded since the work was sent back"}, _TEST, read_version=current.version
        )
    packet = packets.build(ws, store, cfg, redo, TODAY).task.request
    block = packet.split("The earlier work, as it stands now", 1)[1]
    assert "Reworded since the work was sent back" in block, "the current version, not the one the work made"
    assert "kept from the earlier work" in block and '"gone"' not in block
    items = json.loads(block.split('<untrusted source="records">\n', 1)[1].split("\n</untrusted>", 1)[0])
    assert [(i["kind"], i["id"]) for i in items] == [("action", action)]


def test_a_request_that_redoes_nothing_has_no_such_block(env):
    ws, cfg, store = env
    from engine.intake import hand_in

    request = hand_in(ws, store, pasted="Interior files are due.", now=NOW).request
    assert "The earlier work, as it stands now" not in packets.build(ws, store, cfg, request, TODAY).task.request
