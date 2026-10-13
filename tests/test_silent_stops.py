"""No silent stops (design 8.5, 8.6, 8.8): a usage limit pauses its account until the reset and the waiting work resumes
by itself; a run that gave no usable answer is tried again by itself, then goes to the person with why; a program that
finishes without an answer is its own outcome; and held or paused work is a line on Today. A fake adapter and a clock
the test moves stand in for the provider and for time: nothing sleeps and nothing reaches a network."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.adapters.stub import set_responder
from engine.ai.pauses import Pauses, pauses_path, when_text
from engine.ai.router import AccountPaused, Router
from engine.ai.task import AiError, AiTask
from engine.config.schema import AgentSettings, ProviderSettings
from engine.dispatcher import retry
from engine.intake import hand_in
from engine.storage import Store
from engine.today import zone
from engine.today_queue import queue
from engine.worker import RESTART_NEEDED, Events, Worker, waits_for_its_time
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

START = datetime(2026, 10, 13, 15, 0, tzinfo=UTC)
NOTE = "The printer says proof copies will ship on the fifth."
ANSWER = json.dumps({"summary": "Nothing to do.", "ops": []})
TASK = AiTask(kind="notes", instructions="Do it.", stable="Reference.", request="Input.", output_schema={})


class Clock:
    """A clock the test moves; nothing waits for real time."""

    def __init__(self, at: datetime = START):
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def move(self, **by: float) -> None:
        self.at += timedelta(**by)


class Scripted:
    """The provider: answers from a script, in order, and counts the calls. An item that is an AiError is raised."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def __call__(self, task: AiTask) -> str:
        self.calls += 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, AiError):
            raise item
        return item


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    clock = Clock()
    yield ws, cfg, store, clock
    store.close()
    set_responder(None)


def worker_of(env) -> Worker:
    """A worker as the app builds one, with the test's clock for both the worker and the routers it makes."""
    ws, cfg, store, clock = env
    return Worker(
        ws,
        store,
        cfg,
        Events(),
        router_factory=lambda: Router(cfg, store, env={}, now=clock, sleep=lambda s: None),
        now=clock,
    )


def hand(env, text: str = NOTE) -> str:
    ws, _, store, clock = env
    return hand_in(ws, store, note="", pasted=text, now=clock()).request


def data(env, request: str) -> dict:
    return env[2].read().get("request", request).data


def account_of(cfg) -> str:
    return cfg.ai.tiers["routine"].use.partition("/")[0]


def quota(seconds: float | None = 7200) -> AiError:
    return AiError("quota", "HTTP 402: the plan's usage limit is reached", retry_after=seconds)


# ---- a usage limit pauses the account until its reset ----------------------------------------


def adapters_by_account(cfg, answers: dict[str, object]):
    """An adapter factory that answers per account (told apart by their settings objects)."""
    by_settings = {id(cfg.ai.providers[name]): fn for name, fn in answers.items()}

    class Adapter:
        def __init__(self, settings):
            self.fn = by_settings[id(settings)]

        def run(self, task, model):
            from engine.ai.task import AiResult

            return AiResult(text=self.fn(task), model_served="served", seconds=0.0)

    return lambda name, settings, secret: Adapter(settings)


def test_a_usage_limit_with_a_reset_pauses_the_account_and_it_is_not_called_before_then(env):
    _, cfg, store, clock = env
    account = account_of(cfg)
    provider = Scripted(quota(7200), ANSWER)
    router = Router(cfg, store, env={}, now=clock, adapter_factory=adapters_by_account(cfg, {account: provider}))
    with pytest.raises(AccountPaused) as stopped:
        router.call(TASK, request_id="REQ-1")
    assert (stopped.value.account, stopped.value.until) == (account, START + timedelta(hours=2))
    assert provider.calls == 1
    clock.move(hours=1)
    with pytest.raises(AccountPaused):
        router.call(TASK, request_id="REQ-1")
    assert provider.calls == 1, "a paused account is not called again before its reset"
    clock.move(hours=1, seconds=1)
    result, _, _ = router.call(TASK, request_id="REQ-1")
    assert result.text == ANSWER and provider.calls == 2


def test_the_pause_is_kept_on_disk_so_a_new_process_still_honors_it(env):
    _, cfg, store, clock = env
    account = account_of(cfg)
    provider = Scripted(quota(3600), ANSWER)
    first = Router(cfg, store, env={}, now=clock, adapter_factory=adapters_by_account(cfg, {account: provider}))
    with pytest.raises(AccountPaused):
        first.call(TASK, request_id="REQ-1")
    assert pauses_path(store).is_file()
    # What a restart makes: new objects reading the same workspace.
    second = Router(cfg, store, env={}, now=clock, adapter_factory=adapters_by_account(cfg, {account: provider}))
    with pytest.raises(AccountPaused):
        second.call(TASK, request_id="REQ-1")
    assert provider.calls == 1
    assert Pauses(pauses_path(store), clock).active() == {account: START + timedelta(hours=1)}
    clock.move(hours=2)
    assert Pauses(pauses_path(store), clock).active() == {}


def test_a_fallback_account_takes_the_work_while_the_first_is_paused(env):
    _, cfg, store, clock = env
    first = account_of(cfg)
    cfg.ai.providers["second"] = cfg.ai.providers[first].model_copy()
    cfg.ai.tiers["routine"].fallback = ["second/default"]
    limited, other = Scripted(quota(7200)), Scripted(ANSWER)
    router = Router(
        cfg,
        store,
        env={},
        now=clock,
        adapter_factory=adapters_by_account(cfg, {first: limited, "second": other}),
    )
    for _ in range(2):
        result, choice, _ = router.call(TASK, request_id="REQ-1")
        assert choice.provider == "second" and result.text == ANSWER
    assert limited.calls == 1, "the paused account was tried once and then left alone"


def test_a_limit_with_no_reset_time_is_not_a_pause(env):
    _, cfg, store, clock = env
    router = Router(
        cfg,
        store,
        env={},
        now=clock,
        adapter_factory=adapters_by_account(cfg, {account_of(cfg): Scripted(quota(None))}),
    )
    with pytest.raises(AiError) as stopped:
        router.call(TASK, request_id="REQ-1")
    assert stopped.value.kind == "quota" and not isinstance(stopped.value, AccountPaused)
    assert Pauses(pauses_path(store), clock).active() == {}


def test_a_request_to_slow_down_that_keeps_coming_pauses_for_the_configured_time(env):
    _, cfg, store, clock = env
    cfg.ai.rate_limits.pause_seconds = 900
    busy = Scripted(AiError("rate_limited", "HTTP 429", retry_after=None))
    router = Router(
        cfg,
        store,
        env={},
        now=clock,
        sleep=lambda s: None,
        adapter_factory=adapters_by_account(cfg, {account_of(cfg): busy}),
    )
    with pytest.raises(AccountPaused) as stopped:
        router.call(TASK, request_id="REQ-1")
    assert stopped.value.until == START + timedelta(seconds=900)
    assert busy.calls == cfg.ai.rate_limits.tries


def test_a_waiting_request_says_whose_limit_and_when_in_the_persons_time_and_no_model_name(env):
    ws, cfg, store, clock = env
    provider = Scripted(quota(7200))
    set_responder(provider)
    request = hand(env)
    worker = worker_of(env)
    worker.run_pending()
    waiting = data(env, request)
    local = (START + timedelta(hours=2)).astimezone(zone(cfg))
    expected = f"Waiting for {account_of(cfg)}'s limit to reset at {when_text(cfg, START + timedelta(hours=2), START)}"
    assert waiting["state"] == "queued" and waiting["waiting"] == expected
    assert local.strftime("%I").lstrip("0") in waiting["waiting"]
    assert not any(model in waiting["waiting"] for model in cfg.ai.providers[account_of(cfg)].models.values())
    assert waiting["cause"]["kind"] == "paused" and waiting["cause"]["account"] == account_of(cfg)


def test_waiting_requests_resume_by_themselves_at_the_reset_without_anyone_pressing_anything(env):
    _, cfg, store, clock = env
    provider = Scripted(quota(7200), ANSWER)
    set_responder(provider)
    first, second = hand(env), hand(env, NOTE + " Also the covers.")
    worker = worker_of(env)
    worker.run_pending()
    assert provider.calls == 1, "only the first request reached the provider"
    assert [data(env, r)["state"] for r in (first, second)] == ["queued", "queued"]
    clock.move(hours=1)
    assert worker.run_pending() == 0 and provider.calls == 1, "nothing runs while the limit has not reset"
    # A restart in between: a new worker on the same workspace, still waiting.
    worker = worker_of(env)
    assert worker.run_pending() == 0 and provider.calls == 1
    clock.move(hours=1, seconds=1)
    assert worker.run_pending() == 2
    assert [data(env, r)["state"] for r in (first, second)] == ["review", "review"]
    assert all(data(env, r)["cause"] is None for r in (first, second))


def test_changing_the_accounts_lets_waiting_requests_try_the_new_setup_at_once(env):
    from engine.worker import release_paused

    _, cfg, store, clock = env
    set_responder(Scripted(quota(7200), ANSWER))
    request = hand(env)
    worker_of(env).run_pending()
    assert data(env, request)["cause"]["kind"] == "paused"
    assert release_paused(store) == 1
    assert data(env, request)["cause"] is None and Pauses(pauses_path(store), clock).active() == {}


# ---- an empty or failed run is tried again by itself, then goes to the person ----------------------------------------


def test_an_empty_answer_is_retried_with_a_growing_wait_then_goes_to_the_person_with_why(env):
    _, cfg, store, clock = env
    assert cfg.dispatch.retries == 2 and cfg.dispatch.retry_wait_seconds == 30
    provider = Scripted("")
    set_responder(provider)
    request = hand(env)
    worker = worker_of(env)
    worker.run_pending()
    after_first = provider.calls
    waiting = data(env, request)
    assert waiting["state"] == "queued" and waiting["retries"] == 1 and waiting["cause"]["kind"] == "retry"
    assert "Trying again at" in waiting["waiting"] and "try 2 of 3" in waiting["waiting"]
    assert waits_for_its_time(waiting, clock())
    # Not before its time.
    assert worker.run_pending() == 0 and provider.calls == after_first
    clock.move(seconds=30)
    worker.run_pending()
    assert data(env, request)["retries"] == 2 and provider.calls > after_first
    second_wait = datetime.fromisoformat(data(env, request)["cause"]["until"]) - clock()
    assert second_wait == timedelta(seconds=60)
    clock.move(seconds=60)
    worker.run_pending()
    stopped = data(env, request)
    assert stopped["state"] == "needs_you" and stopped["cause"] is None
    assert stopped["waiting"].startswith("Tried 3 times without a usable answer.")
    assert not any(word in stopped["waiting"] for word in ("JSON", "op reference", "Value error", "None"))
    # The person's Try again starts the count afresh.
    retry(store, request)
    assert data(env, request)["state"] == "queued" and data(env, request)["retries"] == 0


@pytest.mark.parametrize("kind", ["timeout", "provider_down", "other", "invalid_output", "no_output"])
def test_a_failed_call_that_another_try_may_clear_is_retried(env, kind):
    set_responder(Scripted(AiError(kind, "it went wrong")))
    request = hand(env)
    worker_of(env).run_pending()
    waiting = data(env, request)
    assert waiting["state"] == "queued" and waiting["retries"] == 1 and waiting["cause"]["kind"] == "retry"


@pytest.mark.parametrize("kind", ["auth", "no_key", "refused", "quota"])
def test_a_failure_another_try_cannot_clear_goes_to_the_person_at_once(env, kind):
    set_responder(Scripted(AiError(kind, "it went wrong")))
    request = hand(env)
    worker_of(env).run_pending()
    assert data(env, request)["state"] == "needs_you" and data(env, request)["retries"] == 0


def test_no_retries_configured_means_the_first_failure_goes_to_the_person(env):
    _, cfg, store, clock = env
    cfg.dispatch.retries = 0
    set_responder(Scripted(""))
    request = hand(env)
    worker_of(env).run_pending()
    stopped = data(env, request)
    assert stopped["state"] == "needs_you" and not stopped["waiting"].startswith("Tried")


# ---- a lost network waits for the network, and uses up no tries ----------------------------------------


def offline() -> AiError:
    return AiError("offline", "name resolution failed")


def test_a_lost_network_waits_without_counting_a_try_and_runs_when_the_network_is_back(env):
    _, cfg, _, clock = env
    provider = Scripted(offline(), offline(), offline(), offline(), ANSWER)
    set_responder(provider)
    request = hand(env)
    worker = worker_of(env)
    worker.run_pending()
    began = clock()
    waiting = data(env, request)
    assert waiting["state"] == "queued" and waiting["retries"] == 0 and waiting["cause"]["kind"] == "offline"
    assert datetime.fromisoformat(waiting["cause"]["since"]) == began
    wait = timedelta(seconds=cfg.dispatch.offline_check_seconds)
    assert datetime.fromisoformat(waiting["cause"]["until"]) == began + wait
    assert waiting["waiting"].startswith("Waiting for the network since ") and "Checking again at" in waiting["waiting"]
    # It is looked at again only after its wait, never in a loop, and more times than a failing service gets tries.
    assert worker.run_pending() == 0 and provider.calls == 1
    for _ in range(cfg.dispatch.retries + 1):
        clock.move(seconds=cfg.dispatch.offline_check_seconds)
        assert worker.run_pending() == 1
        again = data(env, request)
        assert again["state"] == "queued" and again["retries"] == 0
        assert datetime.fromisoformat(again["cause"]["since"]) == began
    clock.move(seconds=cfg.dispatch.offline_check_seconds)
    assert worker.run_pending() == 1
    done = data(env, request)
    assert done["state"] == "review" and done["retries"] == 0 and done["cause"] is None
    assert provider.calls == 5


def test_a_wait_for_the_network_records_its_first_miss_only_not_one_run_per_look(env):
    _, cfg, store, clock = env
    set_responder(Scripted(offline(), offline(), offline(), offline(), ANSWER))
    request = hand(env)
    worker = worker_of(env)

    def runs(kind):
        return [r for r in store.read().list("run") if r.data.get("error_kind") == kind]

    worker.run_pending()
    for _ in range(2):
        clock.move(seconds=cfg.dispatch.offline_check_seconds)
        assert worker.run_pending() == 1
    assert data(env, request)["state"] == "queued" and len(runs("offline")) == 1
    clock.move(seconds=cfg.dispatch.offline_check_seconds)
    worker.run_pending()
    clock.move(seconds=cfg.dispatch.offline_check_seconds)
    worker.run_pending()
    assert data(env, request)["state"] == "review" and len(runs("offline")) == 1
    assert [r.data["outcome"] for r in store.read().list("run")].count("ok") == 1


def test_a_lost_network_never_reaches_the_person_however_long_it_lasts(env):
    _, cfg, _, clock = env
    set_responder(Scripted(offline()))
    request = hand(env)
    worker = worker_of(env)
    for _ in range(cfg.dispatch.retries + 4):
        worker.run_pending()
        clock.move(seconds=cfg.dispatch.offline_check_seconds)
    stopped = data(env, request)
    assert stopped["state"] == "queued" and stopped["retries"] == 0 and stopped["cause"]["kind"] == "offline"


def test_a_service_that_is_down_still_counts_its_tries(env):
    _, cfg, _, clock = env
    set_responder(Scripted(AiError("provider_down", "HTTP 503: overloaded")))
    request = hand(env)
    worker = worker_of(env)
    for _ in range(cfg.dispatch.retries + 1):
        worker.run_pending()
        clock.move(minutes=10)
    stopped = data(env, request)
    assert stopped["state"] == "needs_you" and stopped["waiting"].startswith(f"Tried {cfg.dispatch.retries + 1} times")


def test_a_lost_network_is_one_today_line_after_the_configured_minutes_and_goes_when_it_is_back(env):
    ws, cfg, store, clock = env
    set_responder(Scripted(offline()))
    first = hand(env)
    second = hand(env, NOTE + " Also the covers.")
    worker = worker_of(env)
    worker.run_pending()
    assert all(line.kind != "offline" for line in queue(ws, store, cfg, clock()))
    clock.move(minutes=cfg.dispatch.offline_line_after_minutes - 1)
    worker.run_pending()
    assert all(line.kind != "offline" for line in queue(ws, store, cfg, clock()))
    clock.move(minutes=1)
    worker.run_pending()
    [line] = [x for x in queue(ws, store, cfg, clock()) if x.kind == "offline"]
    assert line.group == "risk" and line.count == 2 and line.waiting == "Waiting for the network"
    assert line.waiting_since == START.isoformat()
    set_responder(Scripted(ANSWER))
    clock.move(seconds=cfg.dispatch.offline_check_seconds)
    worker.run_pending()
    assert data(env, first)["state"] == "review" and data(env, second)["state"] == "review"
    assert all(line.kind != "offline" for line in queue(ws, store, cfg, clock()))


def test_another_account_in_the_chain_takes_the_work_when_one_has_no_connection(env):
    ws, cfg, store, clock = env
    cfg.ai.providers["second"] = cfg.ai.providers[account_of(cfg)].model_copy()
    cfg.ai.tiers["routine"].fallback = ["second/default"]
    cfg.ai.tiers["deep"].fallback = ["second/default"]
    request = hand(env)

    def cut_off(task):
        raise offline()

    factory = adapters_by_account(cfg, {account_of(cfg): cut_off, "second": lambda task: ANSWER})
    worker = Worker(
        ws,
        store,
        cfg,
        Events(),
        router_factory=lambda: Router(cfg, store, env={}, adapter_factory=factory, now=clock, sleep=lambda s: None),
        now=clock,
    )
    worker.run_pending()
    assert data(env, request)["state"] == "review" and data(env, request)["cause"] is None


# ---- a program that finishes without an answer is its own outcome ----------------------------------------


AGENT = r"""
import sys
mode = sys.argv[1]
sys.stdin.read()
if mode == "empty-file":
    import re
    open(re.findall(r"(/\S+?\.json)", sys.argv[2])[-1], "w").write("   ")
elif mode == "limit":
    print("Usage limit reached. Resets in 5400 seconds.", file=sys.stderr)
    sys.exit(7)
"""


@pytest.fixture
def agent_script(tmp_path):
    path = tmp_path / "fake_agent.py"
    path.write_text(AGENT)
    return str(path)


def agent(script, mode, *extra, **more):
    return ProviderSettings(
        adapter=CliAgentAdapter.name,
        models={"default": "agent-model"},
        timeout_seconds=5,
        agent=AgentSettings(command=[sys.executable, script, mode, *extra], **more),
    )


def test_a_program_that_exits_cleanly_with_nothing_on_its_output_is_no_output_never_an_empty_answer(agent_script):
    with pytest.raises(AiError) as silent:
        CliAgentAdapter(agent(agent_script, "silent")).run(TASK, "agent-model")
    assert silent.value.kind == "no_output"
    json_mode = agent(agent_script, "silent", output_json=True, output_fields={"text": "result"})
    with pytest.raises(AiError) as empty_json:
        CliAgentAdapter(json_mode).run(TASK, "agent-model")
    assert empty_json.value.kind == "no_output"


def test_an_empty_answer_file_and_a_missing_one_are_both_no_output(agent_script):
    blank = agent(agent_script, "empty-file", "{prompt}", output_via="outbox", packet_via="argument")
    with pytest.raises(AiError) as written_empty:
        CliAgentAdapter(blank).run(TASK, "agent-model")
    assert written_empty.value.kind == "no_output"
    with pytest.raises(AiError) as missing:
        CliAgentAdapter(agent(agent_script, "silent", output_via="outbox")).run(TASK, "agent-model")
    assert missing.value.kind == "no_output"


def test_a_failed_exit_is_still_read_from_the_exit_code_and_stream_not_called_no_output(agent_script):
    failing = agent(agent_script, "limit", errors={"exit_codes": {7: "quota"}})
    with pytest.raises(AiError) as limited:
        CliAgentAdapter(failing).run(TASK, "agent-model")
    assert limited.value.kind == "quota"


def test_a_reset_time_in_the_error_stream_is_read_only_where_the_account_says_to(agent_script):
    told = agent(agent_script, "limit", errors={"exit_codes": {7: "quota"}, "reset": [r"resets in (\d+) seconds"]})
    with pytest.raises(AiError) as limited:
        CliAgentAdapter(told).run(TASK, "agent-model")
    assert limited.value.kind == "quota" and limited.value.retry_after == 5400
    untold = agent(agent_script, "limit", errors={"exit_codes": {7: "quota"}})
    with pytest.raises(AiError) as unknown:
        CliAgentAdapter(untold).run(TASK, "agent-model")
    assert unknown.value.retry_after is None


def test_an_iso_reset_time_is_turned_into_seconds_from_now(agent_script):
    in_an_hour = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    error = CliAgentAdapter(
        agent(agent_script, "limit", errors={"reset": [r"until (\S+)"], "exit_codes": {7: "quota"}})
    ).classify_error(7, f"limit reached until {in_an_hour}", None)
    assert error.kind == "quota" and 3500 < error.retry_after <= 3600


def test_no_output_from_the_agent_is_retried_then_sent_to_the_person_and_never_done(env):
    set_responder(Scripted(AiError("no_output", "the agent finished without an answer")))
    request = hand(env)
    worker = worker_of(env)
    _, cfg, _, clock = env
    for wait in (0, 30, 60):
        clock.move(seconds=wait)
        worker.run_pending()
        assert data(env, request)["state"] in ("queued", "needs_you")
    stopped = data(env, request)
    assert stopped["state"] == "needs_you" and stopped["changeset"] is None
    assert "finished without giving an answer" in stopped["waiting"]


# ---- Today ----------------------------------------


def test_held_work_is_the_first_decide_line_with_its_count_and_nothing_restarts(env):
    ws, cfg, store, clock = env
    first, second = hand(env), hand(env, NOTE + " Also the covers.")
    worker = worker_of(env)
    # A change that needs a restart is waiting: new work is held, not run.
    worker.restart_needed = RESTART_NEEDED
    worker._hold_queued()
    lines = queue(ws, store, cfg, clock())
    assert lines[0].kind == "restart" and lines[0].group == "decide" and lines[0].count == 2
    assert lines[0].waiting == RESTART_NEEDED
    assert all(line.kind != "restart" for line in lines[1:])
    assert not worker.restarting and not worker.restart_requested
    assert [data(env, r)["state"] for r in (first, second)] == ["queued", "queued"]


def test_the_restart_line_comes_before_the_first_go_and_before_decisions(env):
    ws, cfg, store, clock = env
    cfg.ai.budgets.first_go = True
    waiting_for_go = hand(env)
    set_responder(Scripted(ANSWER))
    worker = worker_of(env)
    worker.run_pending()
    assert data(env, waiting_for_go)["approval"] == "required"
    held = hand(env, NOTE + " Held for a restart.")
    worker.restart_needed = RESTART_NEEDED
    worker._hold_queued()
    kinds = [line.kind for line in queue(ws, store, cfg, clock())]
    assert kinds.index("restart") == 0 and kinds.index("restart") < kinds.index("first_go")
    assert data(env, held)["waiting"] == RESTART_NEEDED


def test_no_restart_line_when_nothing_is_held(env):
    ws, cfg, store, clock = env
    hand(env)
    assert all(line.kind != "restart" for line in queue(ws, store, cfg, clock()))


def test_a_paused_account_is_a_risk_line_with_the_time_and_the_count_waiting(env):
    ws, cfg, store, clock = env
    set_responder(Scripted(quota(7200)))
    hand(env)
    hand(env, NOTE + " Also the covers.")
    worker_of(env).run_pending()
    [line] = [x for x in queue(ws, store, cfg, clock()) if x.kind == "paused"]
    assert line.group == "risk" and line.count == 2 and line.account == account_of(cfg)
    assert line.until == (START + timedelta(hours=2)).isoformat()
    assert (
        line.waiting
        == f"Waiting for {account_of(cfg)}'s limit to reset at {when_text(cfg, START + timedelta(hours=2), START)}"
    )
    clock.move(hours=3)
    assert all(x.kind != "paused" for x in queue(ws, store, cfg, clock()))


def test_a_pause_with_nothing_waiting_on_it_is_no_line(env):
    ws, cfg, store, clock = env
    Pauses(pauses_path(store), clock).pause(account_of(cfg), START + timedelta(hours=1))
    assert all(line.kind != "paused" for line in queue(ws, store, cfg, clock()))
