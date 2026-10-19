"""Which sign-in a command-line agent runs as (design 6.16): read from the program by a command the account names,
recorded by the account check, and watched on every later check and run. A different sign-in is a Today line with Keep
and Sign in again, and work that needs more than open material waits until the person answers. An account setting
names the levels an identity may see, and work above them waits the same way. A program is faked by a small script."""

import json
import subprocess
import sys
from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import create_app
from engine.ai import identity
from engine.ai.adapters import make_adapter
from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.adapters.stub import StubAdapter
from engine.ai.checked import remember
from engine.ai.router import IdentityHeld, NoProvider, Router, choices
from engine.ai.smoke import account_test
from engine.ai.task import AgentIdentity, AiTask, IdentityUnknown
from engine.config.schema import AgentSettings, ProviderSettings
from engine.dispatcher import process
from engine.intake import hand_in
from engine.storage import Store, WriteContext
from engine.today_queue import queue
from engine.worker import waits_for_its_time
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
_ENGINE = WriteContext(actor="engine", trust="trusted", op="test.sensitivity")
NOTE = "The printer says proof copies will ship on the fifth."
ACCOUNT = "agent"
FIRST, SECOND = "alex@example.com", "sam@example.com"

FAKE_AGENT = r"""
import json, os, sys
mode = sys.argv[1]
if mode == "who":
    print(open(sys.argv[2]).read().strip())
elif mode == "status-json":
    print(json.dumps({"loggedIn": True, "user": {"email": open(sys.argv[2]).read().strip()}}))
elif mode == "status-lines":
    print("agent 1.0")
    print("Signed in as " + open(sys.argv[2]).read().strip() + " (personal)")
elif mode == "env":
    print(",".join(sorted(os.environ)))
elif mode == "broken":
    print("could not reach the sign-in service", file=sys.stderr)
    sys.exit(4)
elif mode == "nothing":
    pass
else:
    sys.stdin.read()
    print(json.dumps({"summary": "Nothing to do.", "ops": []}))
"""


@pytest.fixture
def agent(tmp_path):
    """The fake program and the file whose text is the account it says it runs as."""
    script = tmp_path / "fake_agent.py"
    script.write_text(FAKE_AGENT)
    who = tmp_path / "who.txt"
    who.write_text(FIRST)
    return str(script), who


def agent_settings(script, who, *, mode="who", **more):
    identity_fields = {"identity_command": [sys.executable, script, mode, str(who)], "identity_recheck_seconds": 0}
    return ProviderSettings(
        adapter=CliAgentAdapter.name,
        models={"default": "agent-model"},
        timeout_seconds=10,
        allowed_data=["open", "internal", "restricted"],
        agent=AgentSettings(command=[sys.executable, script, "answer"], **identity_fields, **more),
    )


# ---- reading it from the program ----------------------------------------------------------------------------------


def test_the_identity_is_the_first_line_the_command_prints(agent):
    script, who = agent
    found = CliAgentAdapter(agent_settings(script, who)).identity()
    assert isinstance(found, AgentIdentity) and found.account == FIRST
    assert found.how_read, "the result says how it was read"


def test_a_json_field_a_numbered_line_and_a_pattern_name_where_the_account_is(agent):
    script, who = agent
    by_field = CliAgentAdapter(agent_settings(script, who, mode="status-json", identity_field="user.email")).identity()
    assert by_field.account == FIRST
    by_line = CliAgentAdapter(
        agent_settings(script, who, mode="status-lines", identity_line=2, identity_pattern=r"Signed in as (\S+)")
    ).identity()
    assert by_line.account == FIRST
    whole_line = CliAgentAdapter(agent_settings(script, who, mode="status-lines", identity_line=2)).identity()
    assert whole_line.account == f"Signed in as {FIRST} (personal)"


def test_an_identity_that_cannot_be_read_is_unknown_with_the_reason_never_a_guess(agent):
    script, who = agent
    cases = {
        "the command fails": agent_settings(script, who, mode="broken"),
        "it prints nothing": agent_settings(script, who, mode="nothing"),
        "the field isn't there": agent_settings(script, who, mode="status-json", identity_field="user.name"),
        "the line isn't there": agent_settings(script, who, identity_line=5),
        "the pattern doesn't match": agent_settings(script, who, identity_pattern=r"never (\S+)"),
        "the output isn't JSON for a field": agent_settings(script, who, identity_field="user.email"),
        "the program isn't installed": agent_settings(script, who).model_copy(
            update={
                "agent": AgentSettings(
                    command=[sys.executable, script], identity_command=["no-such-agent-program-here", "who"]
                )
            }
        ),
    }
    for name, settings in cases.items():
        found = CliAgentAdapter(settings).identity()
        assert isinstance(found, IdentityUnknown), name
        assert found.reason.strip(), name


def test_no_command_in_the_settings_is_unknown_not_a_guess_from_the_run_command(agent):
    script, who = agent
    plain = ProviderSettings(
        adapter=CliAgentAdapter.name,
        models={"default": "m"},
        agent=AgentSettings(command=[sys.executable, script, "answer"]),
    )
    found = CliAgentAdapter(plain).identity()
    assert isinstance(found, IdentityUnknown) and "how" in found.reason


def test_a_command_that_is_too_slow_is_unknown(agent):
    script, who = agent

    def too_slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    found = CliAgentAdapter(agent_settings(script, who), runner=too_slow).identity()
    assert isinstance(found, IdentityUnknown) and "seconds" in found.reason


def test_the_command_runs_with_the_agents_small_environment(agent, monkeypatch):
    script, who = agent
    monkeypatch.setenv("COCKPIT_SECRET_THING", "x")
    seen = CliAgentAdapter(agent_settings(script, who, mode="env")).identity()
    assert "PATH" in seen.account and "COCKPIT_SECRET_THING" not in seen.account


def test_other_adapters_have_no_identity(agent):
    assert (
        make_adapter(StubAdapter.name, ProviderSettings(adapter="stub", models={"default": "s"}), None).identity()
        is None
    )


# ---- the check records it ----------------------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path, agent):
    """A workspace whose first account is the fake agent, allowed every level, with its client."""
    script, who = agent
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["providers"][ACCOUNT] = {
        "adapter": CliAgentAdapter.name,
        "label": "Writing agent",
        "models": {"default": "agent-model"},
        "allowed_data": ["open", "internal", "restricted"],
        "timeout_seconds": 10,
        "agent": {
            "command": [sys.executable, script, "answer"],
            "identity_command": [sys.executable, script, "who", str(who)],
            "identity_recheck_seconds": 0,
        },
    }
    raw["tiers"]["routine"]["use"] = f"{ACCOUNT}/default"
    raw["tiers"]["deep"]["use"] = f"{ACCOUNT}/default"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer t"
    return ws, cfg, who, client


def base(ws):
    return ws.config(env={}).server.base_path.rstrip("/") + "/api"


def check(ws, cfg):
    """The account check as the Settings screen runs it: test the account, keep what it showed."""
    results = account_test(cfg, {}, ACCOUNT)
    remember(ws, cfg, results)
    return results


def account_row(client, ws):
    rows = client.get(f"{base(ws)}/ai/accounts").json()
    return next(r for r in rows if r["name"] == ACCOUNT)


def test_the_account_check_reads_the_identity_and_records_it(env):
    ws, cfg, _who, client = env
    results = check(ws, cfg)
    part = [r for r in results if r.part == "identity"]
    assert len(part) == 1 and part[0].ok and FIRST in part[0].detail
    assert identity.recorded(ws, ACCOUNT).account == FIRST
    row = account_row(client, ws)
    assert row["runs_as"] == FIRST and row["identity_unknown"] is None and row["identity_changed_to"] is None
    assert row["runs_as_how"]


def test_an_identity_the_check_cannot_read_is_shown_as_unknown_with_why_and_does_not_fail_the_check(env, agent):
    ws, cfg, _who, client = env
    script, who = agent
    cfg.ai.providers[ACCOUNT].agent.identity_command = [sys.executable, script, "broken"]
    results = check(ws, cfg)
    part = next(r for r in results if r.part == "identity")
    assert part.ok, "an unknown identity is no failure of the account's check"
    assert identity.recorded(ws, ACCOUNT) is None
    shown = identity.shown(ws, ACCOUNT)
    assert shown.unknown and "exit code 4" in shown.unknown


def test_an_account_that_is_not_an_agent_has_nothing_recorded(env):
    ws, cfg, _who, client = env
    check(ws, cfg)
    stub = next(n for n, p in cfg.ai.providers.items() if p.adapter == "stub")
    results = account_test(cfg, {}, stub)
    remember(ws, cfg, results)
    assert not [r for r in results if r.part == "identity"]
    rows = {r["name"]: r for r in client.get(f"{base(ws)}/ai/accounts").json()}
    assert rows[stub]["runs_as"] is None and rows[stub]["identity_unknown"] is None


# ---- a change is a line, and work that needs a level waits ----------------------------------------------------------


def identity_lines(ws, cfg):
    store = Store(ws.db_path, cfg=cfg)
    try:
        return [x for x in queue(ws, store, cfg, NOW) if x.kind == "identity"]
    finally:
        store.close()


def call_at(ws, cfg, level):
    store = Store(ws.db_path, cfg=cfg)
    try:
        task = AiTask("notes", "Follow the rules.", "Stable part.", "The request.", {}, output="json")
        return Router(cfg, store, env={}).call(task, request_id=None, data_level=level)
    finally:
        store.close()


def test_the_same_identity_on_a_later_check_makes_no_line(env):
    ws, cfg, _who, _client = env
    check(ws, cfg)
    check(ws, cfg)
    assert identity_lines(ws, cfg) == []


def test_a_different_identity_on_a_later_check_makes_a_today_line_and_holds_work_above_open(env):
    ws, cfg, who, client = env
    check(ws, cfg)
    who.write_text(SECOND)
    check(ws, cfg)
    [line] = identity_lines(ws, cfg)
    assert (line.account, line.text, line.subject, line.state) == (ACCOUNT, SECOND, FIRST, "changed")
    assert identity.recorded(ws, ACCOUNT).account == FIRST, "the earlier identity stands until the person answers"
    assert account_row(client, ws)["identity_changed_to"] == SECOND
    with pytest.raises(IdentityHeld) as held:
        call_at(ws, cfg, "internal")
    assert held.value.account == ACCOUNT and held.value.why == "changed" and SECOND in str(held.value)
    result, choice, _run = call_at(ws, cfg, "open")
    assert choice.provider == ACCOUNT and result.text, "open material still goes"


def test_a_run_that_finds_a_different_identity_makes_the_line_and_waits(env):
    ws, cfg, who, _client = env
    check(ws, cfg)
    who.write_text(SECOND)  # no check in between: the run itself looks
    with pytest.raises(IdentityHeld):
        call_at(ws, cfg, "internal")
    assert [x.text for x in identity_lines(ws, cfg)] == [SECOND]


def test_a_run_looks_again_only_after_the_configured_time(env):
    ws, cfg, who, _client = env
    check(ws, cfg)
    cfg.ai.providers[ACCOUNT].agent.identity_recheck_seconds = 3600
    who.write_text(SECOND)
    result, _choice, _run = call_at(ws, cfg, "internal")
    assert result.text, "a sign-in read a moment ago isn't read again for every run"
    assert identity_lines(ws, cfg) == []


def test_a_request_that_needs_a_level_waits_with_why_and_goes_after_keep(env):
    ws, cfg, who, client = env
    check(ws, cfg)
    who.write_text(SECOND)
    check(ws, cfg)
    store = Store(ws.db_path, cfg=cfg)
    try:
        request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
        assert process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW) is None
        waiting = store.read().get("request", request).data
        assert waiting["state"] == "queued" and waiting["cause"]["kind"] == "identity"
        assert waiting["cause"]["account"] == ACCOUNT
        assert SECOND in waiting["waiting"] and "keep" in waiting["waiting"].lower()
        assert "until you answer" in waiting["waiting"]
        assert waits_for_its_time(waiting, NOW), "the worker leaves it alone until the person answers"
    finally:
        store.close()
    done = client.post(f"{base(ws)}/ai/accounts/{ACCOUNT}/identity/keep")
    assert done.status_code == 200, done.text
    assert identity.recorded(ws, ACCOUNT).account == SECOND
    assert identity_lines(ws, cfg) == []
    store = Store(ws.db_path, cfg=cfg)
    try:
        released = store.read().get("request", request).data
        assert released["state"] == "queued" and not released.get("cause")
        process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
        assert store.read().get("request", request).data["state"] != "queued"
        assert store.read().list("run"), "the run went"
    finally:
        store.close()


def test_keep_with_nothing_to_keep_is_refused(env):
    ws, cfg, _who, client = env
    check(ws, cfg)
    assert client.post(f"{base(ws)}/ai/accounts/{ACCOUNT}/identity/keep").status_code == 409
    assert client.post(f"{base(ws)}/ai/accounts/nobody/identity/keep").status_code == 404


def test_going_back_to_the_recorded_identity_clears_the_line_and_frees_the_work(env):
    ws, cfg, who, _client = env
    check(ws, cfg)
    who.write_text(SECOND)
    check(ws, cfg)
    assert identity_lines(ws, cfg)
    who.write_text(FIRST)  # the person signed in again as the first account
    check(ws, cfg)
    assert identity_lines(ws, cfg) == []
    assert call_at(ws, cfg, "internal")[0].text


def test_a_change_while_the_identity_is_unreadable_is_no_change(env, agent):
    ws, cfg, _who, _client = env
    script, _ = agent
    check(ws, cfg)
    cfg.ai.providers[ACCOUNT].agent.identity_command = [sys.executable, script, "broken"]
    check(ws, cfg)
    assert identity_lines(ws, cfg) == []
    assert identity.recorded(ws, ACCOUNT).account == FIRST, "unknown doesn't erase what was read"


# ---- a level that doesn't fit ------------------------------------------------------------------------------------


def test_the_identity_level_is_a_list_of_levels_and_unset_by_default():
    assert ProviderSettings(adapter="stub").identity_level is None
    assert ProviderSettings(adapter="stub", identity_level=["open", "internal"]).identity_level == ["open", "internal"]
    with pytest.raises(ValueError):
        ProviderSettings(adapter="stub", identity_level=["secret"])


def test_work_above_the_levels_an_identity_may_see_waits_for_the_person(env):
    ws, cfg, _who, client = env
    cfg.ai.providers[ACCOUNT].identity_level = ["open", "internal"]
    check(ws, cfg)
    with pytest.raises(IdentityHeld) as held:
        choices(cfg, "notes", "restricted")
    assert held.value.why == "level" and held.value.account == ACCOUNT and held.value.level == "restricted"
    assert "restricted" in str(held.value)
    assert choices(cfg, "notes", "internal")[0].provider == ACCOUNT


def test_a_level_that_does_not_fit_is_not_taken_for_a_data_level_stop_the_person_could_allow(env):
    ws, cfg, _who, _client = env
    cfg.ai.providers[ACCOUNT].allowed_data = ["open"]
    with pytest.raises(NoProvider) as stopped:
        choices(cfg, "notes", "internal")
    assert not isinstance(stopped.value, IdentityHeld) and stopped.value.level == "internal"


def test_a_request_on_work_marked_restricted_waits_for_a_personal_identity_and_has_a_line(env):
    ws, cfg, _who, client = env
    cfg.ai.providers[ACCOUNT].identity_level = ["open", "internal"]
    check(ws, cfg)
    store = Store(ws.db_path, cfg=cfg)
    try:
        request = hand_in(ws, store, note="", pasted=NOTE, now=NOW).request
        with store.transaction() as tx:
            current = tx.get("request", request)
            tx.update("request", request, {"sensitivity": "restricted"}, _ENGINE, read_version=current.version)
        process(ws, store, cfg, Router(cfg, store, env={}), request, now=NOW)
        waiting = store.read().get("request", request).data
        assert waiting["state"] == "queued"
        wanted = {"kind": "identity", "account": ACCOUNT, "why": "level", "level": "restricted"}
        assert {k: v for k, v in waiting["cause"].items() if k in wanted} == wanted
        lines = [x for x in queue(ws, store, cfg, NOW) if x.kind == "identity"]
        assert [(x.account, x.text, x.state, x.names, x.count) for x in lines] == [
            (ACCOUNT, FIRST, "level", ["restricted"], 1)
        ]
    finally:
        store.close()


def test_the_state_lives_in_the_private_folder_and_nothing_in_it_is_a_setting(env):
    ws, cfg, _who, _client = env
    check(ws, cfg)
    kept = json.loads((ws.private_dir / identity.STATE_FILE).read_text())
    assert kept[ACCOUNT]["recorded"]["account"] == FIRST


def test_no_vendor_name_or_url_is_in_the_code_that_reads_or_holds_the_identity():
    from engine.selfcheck.scans import scan_boundary, scan_patterns, scan_providers

    assert scan_providers() == [] and scan_patterns() == [] and scan_boundary() == []
