"""The command-line agent adapter: a program run locked down in its own folder, its answer read from its output or its
outbox, its errors read from its exit code and error stream only, and a lockdown test in the smoke test."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from engine.ai.adapters import make_adapter
from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.task import AiError, AiTask
from engine.config.schema import AgentSettings, ProviderSettings

FAKE_AGENT = r"""
import json, os, re, sys, time
mode = sys.argv[1]
prompt = sys.stdin.read()
paths = re.findall(r"(/\S+?\.(?:txt|json|md))\b", prompt)
if mode == "stdout":
    print('{"ok": true}')
elif mode == "says-signed-out":
    print("not logged in")
elif mode == "json":
    print(json.dumps({"result": "drafted", "model": "served-model", "usage": {"input_tokens": 12, "output_tokens": 5},
                      "total_cost_usd": 0.02}))
elif mode == "outbox":
    open(paths[-1], "w").write('{"ok": true}')
elif mode == "silent":
    pass
elif mode == "signed-out":
    print("Please sign in again", file=sys.stderr)
    sys.exit(1)
elif mode == "reports-on-output":
    print(json.dumps({"type": "result", "is_error": True, "result": "Not logged in. Please run the login command"}))
    sys.exit(1)
elif mode == "limit":
    sys.exit(7)
elif mode == "sleep":
    time.sleep(5)
elif mode == "env":
    print(json.dumps(sorted(os.environ)))
elif mode == "packet-file":
    print(len(open(sys.argv[2]).read()))
elif mode == "packet-argument":
    print(len(sys.argv[2]))
elif mode == "cwd":
    print(os.getcwd())
elif mode == "obedient":
    for path in paths:
        open(path, "w").write("ok")
elif mode == "locked":
    open(paths[0], "w").write("ok")
"""


@pytest.fixture
def agent_script(tmp_path):
    path = tmp_path / "fake_agent.py"
    path.write_text(FAKE_AGENT)
    return str(path)


def settings(script, mode, *extra, **agent):
    return ProviderSettings(
        adapter=CliAgentAdapter.name,
        models={"default": "agent-model"},
        timeout_seconds=5,
        agent=AgentSettings(command=[sys.executable, script, mode, *extra], **agent),
    )


def task(output="json"):
    return AiTask("notes", "Follow the rules.", "Stable part.", "The request.", {}, output=output)


def test_the_answer_comes_from_the_agents_output(agent_script):
    result = make_adapter(CliAgentAdapter.name, settings(agent_script, "stdout"), None).run(task(), "agent-model")
    assert result.text == '{"ok": true}' and result.model_served == "agent-model"
    assert result.cost_usd is None and result.input_tokens is None


def test_usage_and_cost_come_from_the_agents_json_where_the_settings_say(agent_script):
    fields = {"text": "result", "input_tokens": "usage.input_tokens", "output_tokens": "usage.output_tokens"}
    s = settings(
        agent_script, "json", output_json=True, output_fields={**fields, "cost_usd": "total_cost_usd", "model": "model"}
    )
    result = CliAgentAdapter(s).run(task("text"), "agent-model")
    assert (result.text, result.input_tokens, result.output_tokens) == ("drafted", 12, 5)
    assert result.cost_usd == 0.02 and result.model_served == "served-model"


def test_the_answer_can_come_from_the_outbox(agent_script):
    result = CliAgentAdapter(settings(agent_script, "outbox", output_via="outbox")).run(task(), "agent-model")
    assert result.text == '{"ok": true}'
    with pytest.raises(AiError) as missing:
        CliAgentAdapter(settings(agent_script, "silent", output_via="outbox")).run(task(), "agent-model")
    assert missing.value.kind == "no_output"


def test_the_packet_can_go_in_as_a_file(agent_script):
    s = settings(agent_script, "packet-file", "{packet}", packet_via="file")
    result = CliAgentAdapter(s).run(task(), "agent-model")
    assert int(result.text) == len("Follow the rules.\n\nStable part.\n\nThe request.")


def test_the_packet_can_go_in_as_an_argument_up_to_a_limit(agent_script):
    from engine.ai.adapters.cli_agent import MAX_ARGUMENT_CHARS

    s = settings(agent_script, "packet-argument", "{prompt}", packet_via="argument")
    result = CliAgentAdapter(s).run(task(), "agent-model")
    assert int(result.text) == len("Follow the rules.\n\nStable part.\n\nThe request.")
    huge = AiTask("notes", "x" * (MAX_ARGUMENT_CHARS + 1), "", "", {})
    with pytest.raises(AiError):
        CliAgentAdapter(s).run(huge, "agent-model")


def test_the_agent_runs_in_its_own_folder_with_a_small_environment(agent_script, monkeypatch, tmp_path):
    monkeypatch.setenv("COCKPIT_SECRET_THING", "x")
    monkeypatch.setenv("AGENT_CONFIG", "y")
    names = json.loads(CliAgentAdapter(settings(agent_script, "env", pass_env=["AGENT_CONFIG"])).run(task(), "m").text)
    assert "AGENT_CONFIG" in names and "COCKPIT_SECRET_THING" not in names
    keyed = CliAgentAdapter(settings(agent_script, "env", key_env="AGENT_KEY"), "secret-value")
    assert "AGENT_KEY" in json.loads(keyed.run(task(), "m").text)
    folder = CliAgentAdapter(settings(agent_script, "cwd")).run(task(), "m").text
    assert "cockpit-agent-" in folder and str(tmp_path) not in folder


def test_errors_are_read_from_the_exit_code_and_error_stream_only(agent_script):
    hint = "Run the agent's login command"
    s = settings(agent_script, "signed-out", errors={"auth": ["sign in"]}, sign_in_hint=hint)
    with pytest.raises(AiError) as signed_out:
        CliAgentAdapter(s).run(task(), "m")
    assert signed_out.value.kind == "auth" and signed_out.value.hint == hint
    with pytest.raises(AiError) as limited:
        CliAgentAdapter(settings(agent_script, "limit", errors={"exit_codes": {7: "quota"}})).run(task(), "m")
    assert limited.value.kind == "quota"
    with pytest.raises(AiError) as unknown:
        CliAgentAdapter(settings(agent_script, "limit")).run(task(), "m")
    assert unknown.value.kind == "other"
    # The model writing words that look like an error is an answer, not a failure.
    said = CliAgentAdapter(settings(agent_script, "says-signed-out", errors={"auth": ["logged in"]})).run(task(), "m")
    assert said.text == "not logged in"


def test_a_missing_program_and_a_slow_one_are_classified(agent_script):
    gone = ProviderSettings(adapter=CliAgentAdapter.name, agent=AgentSettings(command=["no-such-agent-program"]))
    with pytest.raises(AiError) as missing:
        CliAgentAdapter(gone).run(task(), "m")
    assert missing.value.kind == "provider_down"
    slow = settings(agent_script, "sleep").model_copy(update={"timeout_seconds": 1})
    with pytest.raises(AiError) as late:
        CliAgentAdapter(slow).run(task(), "m")
    assert late.value.kind == "timeout"


def test_an_account_without_a_command_is_refused():
    with pytest.raises(AiError):
        CliAgentAdapter(ProviderSettings(adapter=CliAgentAdapter.name))


def test_the_lockdown_test_catches_an_agent_that_writes_anywhere(agent_script):
    loose = CliAgentAdapter(settings(agent_script, "obedient", output_via="outbox")).lockdown_test("m")
    assert {c.name: c.ok for c in loose} == {"outbox": True, "outside": False, "shell": False}
    tight = CliAgentAdapter(settings(agent_script, "locked", output_via="outbox")).lockdown_test("m")
    assert all(c.ok for c in tight)
    answers_on_output = CliAgentAdapter(settings(agent_script, "silent")).lockdown_test("m")
    assert [c.name for c in answers_on_output] == ["outside", "shell"] and all(c.ok for c in answers_on_output)


def test_the_smoke_test_runs_the_lockdown_test_once_per_agent_account(agent_script, tmp_path):
    from engine.ai.smoke import smoke_test

    providers = {
        "agent": settings(agent_script, "obedient", output_via="outbox").model_dump(),
    }
    cfg = SimpleNamespace(
        ai=SimpleNamespace(
            providers={"agent": ProviderSettings(**providers["agent"])},
            tiers={
                "routine": SimpleNamespace(use="agent/default", fallback=[], escalate_to=None),
                "deep": SimpleNamespace(use="agent/default", fallback=[], escalate_to=None),
            },
            tasks={},
        )
    )
    results = smoke_test(cfg, {})
    lockdown = [r for r in results if "lockdown" in r.account]
    assert [r.account for r in lockdown] == [
        "agent/default (lockdown: outbox)",
        "agent/default (lockdown: outside)",
        "agent/default (lockdown: shell)",
    ]
    assert [r.ok for r in lockdown] == [True, False, False] and all(r.main for r in lockdown)


def test_a_sign_in_failure_says_what_to_do():
    from engine.dispatcher import _ai_failure

    told = _ai_failure(AiError("auth", "Please sign in again", hint="Run the agent's login command"))
    assert told.startswith("The AI account isn't signed in (Please sign in again).")
    assert told.endswith("Run the agent's login command, then try again.")


def test_the_agent_sees_the_user_name_its_own_sign_in_is_kept_under(agent_script, monkeypatch):
    """An agent whose sign-in is kept in the system's keychain finds it by the user name."""
    monkeypatch.setenv("USER", "someone")
    monkeypatch.setenv("LOGNAME", "someone")
    names = json.loads(CliAgentAdapter(settings(agent_script, "env")).run(task(), "m").text)
    assert {"USER", "LOGNAME"} <= set(names)


def test_an_agent_that_reports_its_failure_on_its_output_is_understood(agent_script):
    """Some agents print their errors on their output, not on the error stream; the account says so, and only then
    (and only for a failed run) is that report read."""
    fields = {"text": "result"}
    told = settings(
        agent_script,
        "reports-on-output",
        output_json=True,
        output_fields=fields,
        errors={"auth": ["not logged in"], "report_on_output": True},
        sign_in_hint="Run the agent's login command",
    )
    with pytest.raises(AiError) as failed:
        CliAgentAdapter(told).run(task(), "m")
    assert failed.value.kind == "auth" and "Not logged in" in failed.value.detail
    untold = settings(agent_script, "reports-on-output", output_json=True, output_fields=fields)
    with pytest.raises(AiError) as unread:
        CliAgentAdapter(untold).run(task(), "m")
    assert unread.value.kind == "other" and "Not logged in" not in unread.value.detail


def test_an_agent_preset_shows_why_a_signed_out_test_failed_in_plain_words(agent_script):
    """The person's path: an agent account made from a preset whose agent prints its errors on its output, not signed
    in, tested. The test says it isn't signed in, quotes the agent's own words and says what to do, with no internal
    label."""
    from engine.ai.smoke import smoke_test
    from engine.setup import known_endpoints

    presets = [e for e in known_endpoints() if e["adapter"] == CliAgentAdapter.name]
    reporting = [e for e in presets if e["settings"].get("agent", {}).get("errors", {}).get("report_on_output")]
    assert reporting
    for preset in reporting:
        agent = dict(preset["settings"]["agent"])
        agent["command"] = [sys.executable, agent_script, "reports-on-output"]
        account = ProviderSettings(adapter=CliAgentAdapter.name, models={"default": "agent-model"}, agent=agent)
        tier = SimpleNamespace(use="agent/default", fallback=[], escalate_to=None)
        cfg = SimpleNamespace(ai=SimpleNamespace(providers={"agent": account}, tiers={"account": tier}, tasks={}))
        first = smoke_test(cfg, {})[0]
        assert not first.ok, preset["id"]
        assert "Not logged in" in first.detail and agent["sign_in_hint"].rstrip(".") in first.detail, first.detail
        assert not first.detail.startswith(("auth", "other")) and "exit code" not in first.detail


# ---- the program's version -------------------------------------------------------------------------------------------


def test_the_program_version_is_the_first_line_the_version_check_prints(agent_script):
    one = settings(
        agent_script, "stdout", version_command=[sys.executable, "-c", "print('agent 1.2.3'); print('more')"]
    )
    assert CliAgentAdapter(one).program_version() == "agent 1.2.3"
    assert CliAgentAdapter(settings(agent_script, "stdout")).program_version().startswith("Python "), (
        "with no version check set up, the program is asked for --version"
    )


def test_a_version_that_cannot_be_read_is_none_never_a_guess(agent_script):
    failing = settings(agent_script, "stdout", version_command=[sys.executable, "-c", "raise SystemExit(3)"])
    silent = settings(agent_script, "stdout", version_command=[sys.executable, "-c", "pass"])
    missing = settings(agent_script, "stdout", version_command=["no-such-agent-program-here"])
    assert [CliAgentAdapter(s).program_version() for s in (failing, silent, missing)] == [None, None, None]

    def too_slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    slow = CliAgentAdapter(settings(agent_script, "stdout", version_timeout_seconds=2), runner=too_slow)
    assert slow.program_version() is None


def test_the_version_check_runs_with_the_agents_small_environment(agent_script, monkeypatch):
    monkeypatch.setenv("COCKPIT_SECRET_THING", "x")
    show = [sys.executable, "-c", "import os; print(','.join(sorted(os.environ)))"]
    seen = CliAgentAdapter(settings(agent_script, "stdout", version_command=show)).program_version()
    assert "PATH" in seen and "COCKPIT_SECRET_THING" not in seen
