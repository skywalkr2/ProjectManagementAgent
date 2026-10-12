"""A run a stop left unfinished: on start the app puts it back in the queue, and one found stuck a second time waits
for the person."""

from datetime import UTC, datetime

import pytest

from engine.config import load_config
from engine.storage import Store, WriteContext
from engine.worker import INTERRUPTED, INTERRUPTED_TWICE, Events, Worker, requeue_interrupted
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
PM = WriteContext("pm", "trusted", "test")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def make_request(store, **more):
    data = {"task": "notes", "origin": "pm", "state": "running", "created_at": NOW.isoformat(), "attempts": 1, **more}
    with store.transaction() as tx:
        return tx.create("request", data, PM).id


def get(store, request_id):
    return store.read().get("request", request_id)


def run_again(store, request_id):
    """What the dispatcher does when it picks the request up: it is running again, one more run started."""
    with store.transaction() as tx:
        cur = tx.get("request", request_id)
        tx.update(
            "request",
            request_id,
            {"state": "running", "waiting": "With the assistant now", "attempts": cur.data["attempts"] + 1},
            PM,
            read_version=cur.version,
        )


def test_a_running_request_is_queued_again_with_a_note(env):
    _, _, store = env
    request = make_request(store)
    queued, held = requeue_interrupted(store)
    assert queued == [request] and held == []
    now = get(store, request)
    assert now.data["state"] == "queued" and now.data["waiting"] == INTERRUPTED
    entries = store.read().ledger(kind="request", record_id=request)
    assert entries[-1]["op"] == "worker.requeue" and entries[-1]["actor"] == "engine"


def test_queuing_it_again_raises_the_queued_event(env, monkeypatch):
    _, _, store = env
    request = make_request(store)
    published = []
    monkeypatch.setattr(
        store.plugins, "publish", lambda event, payload, follows=None: published.append((event, payload))
    )
    requeue_interrupted(store)
    assert ("request.queued", {"id": request}) in published


def test_a_request_found_running_a_second_time_waits_for_the_person(env):
    from engine.dispatcher import dismiss, retry

    _, _, store = env
    request = make_request(store)
    requeue_interrupted(store)
    run_again(store, request)
    queued, held = requeue_interrupted(store)
    assert queued == [] and held == [request]
    now = get(store, request)
    assert now.data["state"] == "needs_you" and now.data["waiting"] == INTERRUPTED_TWICE
    # The usual Try again and Dismiss apply, and a stop after Try again is still not queued without the person.
    retry(store, request)
    assert get(store, request).data["state"] == "queued"
    run_again(store, request)
    assert requeue_interrupted(store) == ([], [request])
    dismiss(store, request, get(store, request).version)
    assert get(store, request).data["dismissed"] is True


def test_a_persons_try_again_is_not_counted_as_an_interruption(env):
    from engine.dispatcher import retry

    _, _, store = env
    request = make_request(store, state="needs_you", attempts=1)
    retry(store, request)
    run_again(store, request)  # two runs have started, but the app has stopped during one only
    assert requeue_interrupted(store) == ([request], [])


def test_requests_in_other_states_are_left_alone(env):
    _, _, store = env
    states = ("queued", "review", "done", "needs_you", "failed")
    ids = {state: make_request(store, state=state, waiting=f"as {state}") for state in states}
    before = {state: get(store, rid).version for state, rid in ids.items()}
    assert requeue_interrupted(store) == ([], [])
    for state, rid in ids.items():
        now = get(store, rid)
        assert (now.data["state"], now.data["waiting"], now.version) == (state, f"as {state}", before[state])


def test_a_granted_approval_is_kept(env):
    _, _, store = env
    request = make_request(store, approval="granted", estimate_usd=0.5)
    requeue_interrupted(store)
    assert get(store, request).data["approval"] == "granted"
    run_again(store, request)
    requeue_interrupted(store)
    now = get(store, request)
    assert now.data["state"] == "needs_you" and now.data["approval"] == "granted" and now.data["estimate_usd"] == 0.5


def test_the_worker_does_it_on_start_before_taking_work(env):
    ws, cfg, store = env
    request = make_request(store)
    worker = Worker(ws, store, cfg, Events(), router_factory=lambda: pytest.fail("nothing runs in this test"))
    worker._stop.set()  # the threads end at once; only what start() does first is under test
    worker.start()
    try:
        assert get(store, request).data["state"] == "queued" and get(store, request).data["waiting"] == INTERRUPTED
    finally:
        worker.stop()


def test_reading_sources_now_wakes_the_reads_at_once_instead_of_at_the_next_minute(env):
    import threading

    ws, cfg, store = env
    worker = Worker(ws, store, cfg, Events(), router_factory=lambda: pytest.fail("nothing runs in this test"))
    reads = []
    second = threading.Event()

    def counted() -> None:
        reads.append(1)
        if len(reads) == 2:
            second.set()

    worker.run_due_watches = counted
    worker.run_due_jobs = lambda: None
    thread = threading.Thread(target=worker._jobs_loop, daemon=True)
    thread.start()
    try:
        worker.read_sources_now()
        assert second.wait(timeout=5), "the reads waited for the minute's check"
    finally:
        worker._stop.set()
        worker._read_now.set()
        thread.join(timeout=5)
