"""Each catalog entry produces the request or command its service's own documentation asks for (design 6.16). The
entries to check and the quoted messages and bodies are read from `tests/fixtures/ai/catalog-claims.yaml`, so no
service is named here; every case builds the adapter from the catalog entry itself and looks at what it sends."""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import httpx
import pytest
import yaml

from engine.ai.adapters import ADAPTERS
from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.task import AiError, AiTask
from engine.config.schema import ProviderSettings
from engine.setup import known_endpoints

CLAIMS = yaml.safe_load((Path(__file__).parent / "fixtures" / "ai" / "catalog-claims.yaml").read_text("utf-8"))
COMMON = next(e["adapter"] for e in known_endpoints() if not e["settings"].get("agent"))
classify_http_error = sys.modules[ADAPTERS[COMMON].__module__].classify_http_error
HOSTED = "https" + "://models.example.com/v1"
JSON_TASK = AiTask("notes", "Do it.", "Reference.", "Input.", {}, output="json")
TEXT_TASK = AiTask("notes", "Do it.", "Reference.", "Input.", {}, output="text")


def entry(entry_id: str) -> dict:
    return next(e for e in known_endpoints() if e["id"] == entry_id)


def settings_of(entry_id: str, **extra) -> ProviderSettings:
    kind = entry(entry_id)
    return ProviderSettings.model_validate(
        {
            **kind["settings"],
            "adapter": kind["adapter"],
            "base_url": kind["base_url"] or HOSTED,
            **extra,
        }
    )


def chat_requests(entry_id: str, task: AiTask, **extra) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    adapter = ADAPTERS[entry(entry_id)["adapter"]](
        settings_of(entry_id, **extra), "k", transport=httpx.MockTransport(handler)
    )
    adapter.run(task, "m")
    return seen


def chat_body(entry_id: str, task: AiTask = JSON_TASK) -> dict:
    return json.loads(chat_requests(entry_id, task)[0].content)


# ---- chat-format entries: the request body ------------


@pytest.mark.parametrize("entry_id", CLAIMS["no_temperature"])
def test_an_entry_whose_models_refuse_a_temperature_sends_none(entry_id):
    assert "temperature" not in chat_body(entry_id)


@pytest.mark.parametrize("entry_id", CLAIMS["no_json_mode"])
def test_an_entry_with_no_json_object_mode_asks_for_none(entry_id):
    assert "response_format" not in chat_body(entry_id)


@pytest.mark.parametrize(("entry_id", "param"), sorted(CLAIMS["max_tokens_param"].items()))
def test_an_entry_names_the_setting_for_the_most_tokens_its_service_takes(entry_id, param):
    body = chat_body(entry_id)
    assert body[param] == JSON_TASK.max_output and "max_tokens" not in body


def test_every_other_entry_keeps_the_common_name_for_the_most_tokens():
    for kind in known_endpoints():
        if kind["adapter"] == COMMON and kind["id"] not in CLAIMS["max_tokens_param"]:
            assert "max_tokens_param" not in kind["settings"], kind["id"]
    assert ProviderSettings().max_tokens_param == "max_tokens"


@pytest.mark.parametrize(("entry_id", "address"), sorted(CLAIMS["base_url"].items()))
def test_an_entry_sends_to_the_documented_address(entry_id, address):
    assert entry(entry_id)["base_url"] == address
    request = chat_requests(entry_id, JSON_TASK)[0]
    assert str(request.url) == f"{address}/chat/completions"


@pytest.mark.parametrize("entry_id", CLAIMS["effort_param"])
def test_an_entry_whose_service_documents_an_effort_setting_sends_the_tiers_effort(entry_id):
    kind = entry(entry_id)
    assert kind["settings"]["effort_param"] == "reasoning_effort"
    body = json.loads(chat_requests(entry_id, AiTask("notes", "a", "b", "c", {}, effort="low"))[0].content)
    assert body["reasoning_effort"] == "low"


# ---- the effort settings stay where the documentation confirms them ------------


def test_the_effort_settings_are_set_on_exactly_the_entries_whose_documentation_confirms_them():
    for kind in known_endpoints():
        agent = kind["settings"].get("agent") or {}
        assert ("effort_param" in kind["settings"]) is (kind["id"] in CLAIMS["effort_param"]), kind["id"]
        assert agent.get("effort_option") == CLAIMS["effort_option"].get(kind["id"]), kind["id"]
    assert set(CLAIMS["effort_unset"]).isdisjoint({*CLAIMS["effort_param"], *CLAIMS["effort_option"]})
    for entry_id in CLAIMS["effort_unset"]:
        kind = entry(entry_id)
        assert "effort_param" not in kind["settings"]
        assert "effort_option" not in (kind["settings"].get("agent") or {})


# ---- command-line entries: the command and the input ------------


class Recorder:
    """A stand-in for starting the program: keeps what it was started with and answers with the output its settings
    say to read."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.calls: list[dict] = []
        self.done = (stdout, returncode, stderr)

    def __call__(self, args, **kwargs):
        self.calls.append({"args": list(args), **kwargs})
        out, code, err = self.done
        return subprocess.CompletedProcess(args, code, out, err)


def agent_output(settings: ProviderSettings, text: str = "ok") -> str:
    agent = settings.agent
    if not agent.output_json:
        return text
    document: dict = {}
    node = document
    *parents, last = agent.output_fields.text.split(".")
    for part in parents:
        node = node.setdefault(part, {})
    node[last] = text
    return json.dumps(document)


def start(entry_id: str, task: AiTask = TEXT_TASK, **recorder) -> tuple[Recorder, ProviderSettings]:
    """Run the entry's own agent settings against a recorder, the program's name swapped for one that exists."""
    settings = settings_of(entry_id, models={"default": "agent-model"})
    settings.agent.command[0] = sys.executable
    run = Recorder(**{"stdout": agent_output(settings), **recorder})
    CliAgentAdapter(settings, runner=run).run(task, "agent-model")
    return run, settings


def test_the_entry_that_asks_before_trusting_a_folder_trusts_its_own_empty_working_folder():
    kind = entry(CLAIMS["skip_trust"]["entry"])
    assert CLAIMS["skip_trust"]["flag"] in kind["settings"]["agent"]["command"]
    run, _ = start(CLAIMS["skip_trust"]["entry"])
    assert CLAIMS["skip_trust"]["flag"] in run.calls[0]["args"]


@pytest.mark.parametrize(("entry_id", "option"), sorted(CLAIMS["effort_option"].items()))
def test_a_command_line_entry_passes_the_tiers_effort_in_its_programs_own_form(entry_id, option):
    run, _ = start(entry_id, AiTask("notes", "a", "b", "c", {}, output="text", effort="low"))
    args = run.calls[0]["args"]
    wanted = [part.replace("{effort}", "low") for part in option]
    assert any(args[i : i + len(wanted)] == wanted for i in range(len(args))), args


def test_the_packet_goes_to_the_program_on_its_standard_input_not_on_the_command_line():
    entry_id = CLAIMS["packet_on_stdin"]
    assert entry(entry_id)["settings"]["agent"]["packet_via"] == "stdin"
    task = AiTask("notes", "Unmistakable instructions.", "Unmistakable reference.", "Unmistakable request.", {})
    run, _ = start(entry_id, task)
    call = run.calls[0]
    for words in ("Unmistakable instructions.", "Unmistakable reference.", "Unmistakable request."):
        assert words in call["input"]
        assert not any("Unmistakable" in part for part in call["args"])
    assert "{prompt}" not in call["args"]


@pytest.mark.parametrize("entry_id", sorted(CLAIMS["lockdown"]))
def test_the_command_that_runs_carries_the_options_its_programs_documentation_gives_for_denying_tools(entry_id):
    run, _ = start(entry_id)
    args = run.calls[0]["args"]
    for option in CLAIMS["lockdown"][entry_id]:
        assert any(args[i : i + len(option)] == option for i in range(len(args))), (option, args)


def test_an_entry_whose_program_documents_no_way_to_stop_reading_makes_no_claim_that_it_cant_use_tools():
    case = CLAIMS["no_tool_denial_documented"]
    assert case["entry"] not in CLAIMS["lockdown"]
    assert case["claim"] not in entry(case["entry"])["note"]


def test_no_entry_that_leaves_its_program_able_to_read_says_its_tools_are_off():
    for entry_id in [e["id"] for e in known_endpoints() if e["settings"].get("agent")]:
        if entry_id not in CLAIMS["lockdown"] and entry_id != "agent":
            assert CLAIMS["no_tool_denial_documented"]["claim"] not in entry(entry_id)["note"]


# ---- the program's own messages ------------


@pytest.mark.parametrize("case", CLAIMS["program_messages"], ids=lambda c: c["message"])
def test_a_program_message_is_read_as_what_it_documents(case):
    adapter = CliAgentAdapter(settings_of(case["entry"], models={"default": "m"}))
    assert adapter.classify_error(1, case["message"], None).kind == case["kind"]


def test_a_program_that_reports_on_its_output_has_its_message_read_from_there():
    case = next(c for c in CLAIMS["program_messages"] if c["kind"] == "quota")
    settings = settings_of(case["entry"], models={"default": "m"})
    settings.agent.command[0] = sys.executable
    assert settings.agent.errors.report_on_output
    report = json.dumps({"is_error": True, "result": case["message"]})
    with pytest.raises(AiError) as caught:
        CliAgentAdapter(settings, runner=Recorder(stdout=report, returncode=1)).run(TEXT_TASK, "m")
    assert caught.value.kind == "quota"


# ---- a refused key answered with a 400 ------------


def listing_error(entry_id: str, status: int, body: dict, **extra) -> AiError:
    adapter = ADAPTERS[entry(entry_id)["adapter"]](
        settings_of(entry_id, **extra),
        "k",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    )
    with pytest.raises(AiError) as caught:
        adapter.list_models()
    return caught.value


def generation_error(entry_id: str, status: int, body: dict) -> AiError:
    adapter = ADAPTERS[entry(entry_id)["adapter"]](
        settings_of(entry_id), "k", transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    )
    with pytest.raises(AiError) as caught:
        adapter.run(JSON_TASK, "m")
    return caught.value


@pytest.mark.parametrize("case", CLAIMS["refused_key"], ids=lambda c: c["entry"])
def test_a_400_on_the_model_list_means_the_key_was_refused_where_the_entry_says_so(case):
    assert listing_error(case["entry"], 400, case["body"]).kind == "auth"


@pytest.mark.parametrize("case", CLAIMS["refused_key"], ids=lambda c: c["entry"])
def test_the_recorded_body_on_a_request_for_work_stays_unclassified(case):
    """The body carries no code that separates a refused key from any other bad request, and wording is never read."""
    assert generation_error(case["entry"], 400, case["body"]).kind == "other"


def test_a_reason_code_the_entry_names_means_the_key_was_refused_on_a_request_for_work():
    case = next(c for c in CLAIMS["refused_key"] if "reason_body" in c)
    assert entry(case["entry"])["settings"]["auth_reasons"]
    assert generation_error(case["entry"], 400, case["reason_body"]).kind == "auth"
    assert generation_error(case["entry"], 400, case["other_reason_body"]).kind == "other"


def test_the_status_alone_is_not_read_as_a_refused_key_on_an_entry_that_does_not_say_so():
    for entry_id in CLAIMS["no_key_refused_setting"]:
        kind = entry(entry_id)
        assert "key_refused_status_on_models" not in kind["settings"] and "auth_reasons" not in kind["settings"]
        body = CLAIMS["refused_key"][0]["body"]
        assert listing_error(entry_id, 400, body).kind == "other"
        assert listing_error(entry_id, 401, body).kind == "auth"


def test_both_settings_default_to_empty_and_the_status_must_be_listed():
    plain = ProviderSettings()
    assert plain.auth_reasons == [] and plain.key_refused_status_on_models == []
    response = httpx.Response(400, json=CLAIMS["refused_key"][0]["body"])
    assert classify_http_error(response, plain, listing=True).kind == "other"
    listed = ProviderSettings(key_refused_status_on_models=[400])
    assert classify_http_error(response, listed, listing=True).kind == "auth"
    assert classify_http_error(response, listed).kind == "other"


# ---- paging through the model list ------------


def paged(pages: dict[str | None, dict], **extra) -> tuple[dict, list[dict]]:
    asked: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=pages[request.url.params.get("after_id")])

    adapter = ADAPTERS[COMMON](
        ProviderSettings(adapter=COMMON, base_url=HOSTED, **extra),
        "k",
        transport=httpx.MockTransport(handler),
    )
    return adapter.list_models(), asked


def test_a_model_list_that_says_more_follow_is_read_page_by_page():
    pages = {
        None: {"data": [{"id": "a"}, {"id": "b"}], "has_more": True, "last_id": "b"},
        "b": {"data": [{"id": "c"}], "has_more": False, "last_id": "c"},
    }
    found, asked = paged(pages)
    assert list(found) == ["a", "b", "c"]
    assert asked == [{}, {"after_id": "b"}]


def test_a_list_with_no_paging_is_one_request():
    found, asked = paged({None: {"data": [{"id": "a"}]}})
    assert list(found) == ["a"] and asked == [{}]


def test_the_pages_read_are_bounded_by_a_setting():
    pages = {None: {"data": [{"id": "m0"}], "has_more": True, "last_id": "m0"}}
    pages.update(
        {f"m{n}": {"data": [{"id": f"m{n + 1}"}], "has_more": True, "last_id": f"m{n + 1}"} for n in range(20)}
    )
    found, asked = paged(pages, model_list_pages=3)
    assert len(asked) == 3 and list(found) == ["m0", "m1", "m2"]
    assert ProviderSettings().model_list_pages >= 1


def test_a_list_that_repeats_itself_stops():
    pages = {
        None: {"data": [{"id": "a"}], "has_more": True, "last_id": "a"},
        "a": {"data": [{"id": "a"}], "has_more": True, "last_id": "a"},
    }
    found, asked = paged(pages)
    assert list(found) == ["a"] and len(asked) == 2


# ---- a saved account's check lists the models first ------------


class Service:
    """A stand-in for the service: answers the model list and the chat request as told, and keeps what was asked."""

    def __init__(self, listing: httpx.Response):
        self.listing = listing
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return self.listing
        sent = json.loads(request.content)["messages"][-1]["content"]
        answer = connection_answer(types.SimpleNamespace(request=sent))
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    def factory(self):
        return lambda name, settings, secret: ADAPTERS[name](settings, secret, transport=httpx.MockTransport(self))


def connection_answer(task) -> str:
    from tests.conftest import connection_answer as answer

    return answer(task)


def listed_cfg(entry_id: str):
    from engine.config import load_config
    from tests.conftest import DEMO_B

    settings = settings_of(entry_id, models={"everyday": "m"})
    cfg = load_config(DEMO_B / "config", env={})
    return cfg, settings


def refused_listing() -> httpx.Response:
    return httpx.Response(400, json=CLAIMS["refused_key"][0]["body"])


def test_a_pasted_key_the_service_refuses_on_its_model_list_is_told_as_a_refused_key():
    import os

    from engine.ai import key_check

    cfg, settings = listed_cfg(CLAIMS["list_first"]["entry"])
    service = Service(refused_listing())
    got = key_check.check_account(cfg, os.environ, settings, "k", adapter_factory=service.factory())
    assert not got.ok and got.reason == "key_refused"
    assert [p for p in service.paths if not p.endswith("/models")] == [], "no request for work was sent"
    assert len(service.paths) == 1, "one extra request at most"


def test_a_saved_account_whose_key_the_service_refuses_on_its_model_list_fails_as_a_refused_key():
    from dataclasses import replace

    from engine.ai.smoke import account_test

    cfg, settings = listed_cfg(CLAIMS["list_first"]["entry"])
    ai = cfg.ai.model_copy(update={"providers": {**cfg.ai.providers, "saved": settings}})
    service = Service(refused_listing())
    results = account_test(
        replace(cfg, files={**cfg.files, "ai": ai}),
        {},
        "saved",
        service.factory(),
    )
    failed = [r for r in results if not r.ok]
    assert failed and all(r.error_kind == "auth" for r in failed)
    assert [p for p in service.paths if not p.endswith("/models")] == []
    assert len(service.paths) == 1


def test_a_model_list_that_fails_for_another_reason_does_not_stop_the_check_of_work():
    import os

    from engine.ai import key_check

    cfg, settings = listed_cfg(CLAIMS["list_first"]["entry"])
    service = Service(httpx.Response(CLAIMS["list_first"]["list_failure_status"], json={"error": {}}))
    got = key_check.check_account(cfg, os.environ, settings, "k", adapter_factory=service.factory())
    assert got.ok and got.reason == "works"
    assert sum(p.endswith("/models") for p in service.paths) == 1
    assert any(not p.endswith("/models") for p in service.paths)


def test_an_account_that_names_no_refused_status_on_its_list_is_not_listed_before_the_check():
    import os

    from engine.ai import key_check

    entry_id = CLAIMS["no_key_refused_setting"][0]
    cfg, settings = listed_cfg(entry_id)
    service = Service(refused_listing())
    got = key_check.check_account(cfg, os.environ, settings, "k", adapter_factory=service.factory())
    assert got.ok
    assert not any(p.endswith("/models") for p in service.paths)
