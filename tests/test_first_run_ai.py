"""The AI step for a person who has never made an account (the first-run review's F2, N3, N4): the recommended service
and its alternative come from the catalog's data, the steps carry their links, a key is checked when it is pasted and
before anything is saved (every kind of work, with the exact settings), a failure is said in words that fit the kind of
account, and a new account reads only open material until the person says more."""

from __future__ import annotations

import json
import os

import pytest

from engine.ai import adapters
from engine.ai.smoke import _problem, where_of
from engine.ai.task import AgentIdentity, AiError, AiResult
from engine.config import load_config
from engine.config.schema import ProviderSettings
from engine.setup import known_endpoints
from tests.conftest import connection_answer
from tests.test_setup import COMMON, client, make

#: Made-up addresses are built from this, so no address is written out whole.
WEB = "https" + "://"
HOSTED = [e for e in known_endpoints() if e["needs_key"] and e["base_url"] and not e["local"]]


# ---- the recommendation is data -------------------------------------------------------------------------------------


def test_the_catalog_names_one_recommended_service_and_one_alternative_and_both_take_a_key():
    kinds = known_endpoints()
    recommended = [e for e in kinds if e["recommended"]]
    alternative = [e for e in kinds if e["alternative"]]
    assert len(recommended) == 1 and len(alternative) == 1
    assert recommended[0]["id"] != alternative[0]["id"]
    for pick in (*recommended, *alternative):
        assert pick["needs_key"] and pick["base_url"] and not pick["local"]
        # The numbered steps each have their button: make an account, add credit, make a key.
        assert pick["signup_url"].startswith("https://") and pick["credit_url"].startswith("https://")
        assert pick["key_url"].startswith("https://")


def test_nothing_else_is_marked_and_the_rest_are_offered_under_something_else():
    kinds = known_endpoints()
    marked = {e["id"] for e in kinds if e["recommended"] or e["alternative"]}
    rest = [e for e in kinds if e["id"] not in marked]
    assert rest and not any(e["recommended"] or e["alternative"] for e in rest)
    # Command-line agents, local servers and custom services are all in the rest.
    assert {e["id"] for e in rest if e["adapter"] == "cli-agent"} and {e["id"] for e in rest if e["local"]}


def test_the_endpoints_route_carries_the_recommendation_and_the_step_links(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    shown = {k["id"]: k for k in c.get(f"{api}/ai/endpoints").json()}
    for kind in known_endpoints():
        got = shown[kind["id"]]
        assert bool(got["recommended"]) is kind["recommended"] and bool(got["alternative"]) is kind["alternative"]
        assert got["signup_url"] == kind["signup_url"] and got["credit_url"] == kind["credit_url"]


# ---- the data question: a new account reads only open material ------------------------------------------------------


def test_a_new_account_reads_only_open_material_until_the_person_allows_more(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kind = next(e for e in HOSTED)
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    added = c.post(
        f"{api}/ai/accounts",
        json={
            "name": "fresh",
            "adapter": kind["adapter"],
            "endpoint": kind["id"],
            "key": "not-a-real-key",
            "models": {"everyday": "model-a"},
            "fingerprint": fingerprint,
        },
    )
    assert added.status_code == 200, added.text
    assert load_config(ws.config_dir, env={}).ai.providers["fresh"].allowed_data == ["open"]


def test_checking_a_key_never_widens_what_an_account_may_read(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service())
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kind = HOSTED[0]
    before = (ws.config_dir / "ai.yaml").read_text()
    got = c.post(f"{api}/ai/account-check", json=check_body(kind)).json()
    assert got["ok"] and (ws.config_dir / "ai.yaml").read_text() == before
    assert not (ws.private_dir / "keys").exists()  # nothing is kept before the account is added


# ---- messages that fit the kind of account --------------------------------------------------------------------------


def test_a_hosted_account_never_gets_the_advice_for_a_local_one():
    hosted = ProviderSettings(adapter="a", base_url=f"{WEB}api.example.com/v1")
    local = ProviderSettings(adapter="a", base_url="http://localhost:1234/v1")
    lan = ProviderSettings(adapter="a", base_url="http://192.168.1.20:8000/v1")
    program = ProviderSettings(adapter="b")
    assert [where_of(s) for s in (hosted, local, lan, program)] == ["hosted", "local", "local", "program"]
    down = AiError("provider_down", "[Errno 61] Connection refused")
    said = _problem(down, "hosted")
    assert "internet connection" in said and "start it" not in said and "address" not in said
    assert "start it if it runs on this computer" in _problem(down, "local")
    assert "internet connection" in _problem(AiError("offline", "no route"), "hosted")
    assert "Errno" not in said


def test_listing_models_says_the_same_things_by_kind(tmp_path, monkeypatch):
    from engine.setup import list_models

    def refuse(self, *a, **k):
        raise AiError("provider_down", "refused")

    monkeypatch.setattr(adapters.ADAPTERS[COMMON], "list_models", refuse)
    hosted = HOSTED[0]
    local = next(e for e in known_endpoints() if e["local"])
    _, said_hosted = list_models(hosted, hosted["base_url"], "k")
    _, said_local = list_models(local, local["base_url"], None)
    assert "internet connection" in said_hosted and "start it" not in said_hosted
    assert "start it if it runs on this computer" in said_local


# ---- the check on paste ---------------------------------------------------------------------------------------------


def a_working_service(fail: AiError | None = None, seen: list | None = None):
    """The common adapter with a fake service behind it: it answers every kind of work the way a working account does,
    or fails with the error given."""
    base = adapters.ADAPTERS[COMMON]

    class Fake(base):
        def __init__(self, settings, secret=None):
            self.settings, self.secret = settings, secret

        def run(self, task, model):
            if seen is not None:
                seen.append((task.kind, model, task.temperature, task.max_output, self.secret))
            if fail is not None:
                raise fail
            return AiResult(text=connection_answer(task), model_served=model, seconds=0.0)

        def list_models(self):
            return {}

    return Fake


def check_body(kind, **over):
    body = {
        "endpoint": kind["id"],
        "key": "not-a-real-key",
        "models": {"everyday": "model-a", "harder": "model-b"},
        "use": {"routine": "everyday", "deep": "harder"},
    }
    return {**body, **over}


def test_a_pasted_key_is_checked_for_every_kind_of_work_with_the_exact_settings_before_it_is_saved(
    tmp_path, monkeypatch
):
    seen: list = []
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service(seen=seen))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    kind = HOSTED[0]
    got = c.post(f"{api}/ai/account-check", json=check_body(kind)).json()
    assert got["ok"] is True and got["reason"] == "works"
    tiers = list(cfg.ai.tiers)
    assert len(tiers) >= 2
    asked = {(k, model, temperature, limit) for k, model, temperature, limit, _ in seen}
    # Every kind of work that runs on each tier is tried with the temperature and output limit it will use there, on the
    # model that tier would use: the harder model for the harder tier, the everyday one for the rest.
    for tier_name in tiers:
        model = "model-b" if tier_name == "deep" else "model-a"
        for task_name, settings in cfg.ai.tasks.items():
            if settings.tier == tier_name:
                assert (task_name, model, settings.temperature, settings.max_output) in asked
    assert {secret for *_, secret in seen} == {"not-a-real-key"}


def test_a_key_the_service_refuses_says_so_in_words_that_fit_a_hosted_service(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service(AiError("auth", '{"error": {"message": "bad"}}')))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    got = c.post(f"{api}/ai/account-check", json=check_body(HOSTED[0])).json()
    assert got["ok"] is False and got["reason"] == "key_refused"
    assert "key" in got["message"] and "accept" in got["message"]
    assert "bad" not in got["message"]  # the service's own words aren't the explanation


def test_an_account_with_no_credit_says_so(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service(AiError("quota", "insufficient_quota")))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    got = c.post(f"{api}/ai/account-check", json=check_body(HOSTED[0])).json()
    assert got["ok"] is False and got["reason"] == "no_credit"
    assert "credit" in got["message"]


@pytest.mark.parametrize("kind_of_failure", ["provider_down", "offline", "timeout"])
def test_a_service_that_cant_be_reached_says_to_check_the_internet(tmp_path, monkeypatch, kind_of_failure):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service(AiError(kind_of_failure, "[Errno 61] refused")))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    got = c.post(f"{api}/ai/account-check", json=check_body(HOSTED[0])).json()
    assert got["ok"] is False and got["reason"] == "unreachable"
    assert "internet" in got["message"] and "start it" not in got["message"] and "Errno" not in got["message"]


def test_a_service_on_this_computer_gets_its_own_advice(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service(AiError("provider_down", "refused")))
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    local = next(e for e in known_endpoints() if e["local"] and e["adapter"] == COMMON)
    got = c.post(f"{api}/ai/account-check", json={"endpoint": local["id"], "models": {"everyday": "m"}}).json()
    assert got["reason"] == "unreachable" and "start it if it runs on this computer" in got["message"]


def test_a_missing_key_is_asked_for_not_called_refused(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service())
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    got = c.post(f"{api}/ai/account-check", json={"endpoint": HOSTED[0]["id"], "models": {"everyday": "m"}}).json()
    assert got["ok"] is False and got["reason"] == "key_missing"


def test_a_key_account_says_the_service_does_not_name_whose_account_it_is(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service())
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    got = c.post(f"{api}/ai/account-check", json=check_body(HOSTED[0])).json()
    assert got["identity"] is None and got["identity_unknown"]
    assert "key" in got["identity_unknown"]


def test_an_agents_check_finds_the_sign_in_it_runs_as():
    from engine.ai import key_check

    class Agent:
        def __init__(self, settings, secret=None):
            pass

        def run(self, task, model):
            return AiResult(text=connection_answer(task), model_served=model, seconds=0.0)

        def identity(self):
            return AgentIdentity("sam@example.com", "from the program's own status")

        def lockdown_test(self, model):
            return []

    cfg = load_config(make_cfg_dir(), env={})
    settings = ProviderSettings(adapter="agent-x", models={"everyday": "m"})
    got = key_check.check_account(cfg, os.environ, settings, None, adapter_factory=lambda name, s, secret: Agent(s))
    assert got.ok and got.identity == "sam@example.com" and got.identity_unknown is None


def test_an_agent_whose_sign_in_cant_be_told_says_so_in_plain_words():
    from engine.ai import key_check
    from engine.ai.task import IdentityUnknown

    class Agent:
        def __init__(self, settings, secret=None):
            pass

        def run(self, task, model):
            return AiResult(text=connection_answer(task), model_served=model, seconds=0.0)

        def identity(self):
            return IdentityUnknown("the program doesn't say")

        def lockdown_test(self, model):
            return []

    cfg = load_config(make_cfg_dir(), env={})
    settings = ProviderSettings(adapter="agent-x", models={"everyday": "m"})
    got = key_check.check_account(cfg, os.environ, settings, None, adapter_factory=lambda name, s, secret: Agent(s))
    assert got.ok and got.identity is None and "the program doesn't say" in got.identity_unknown


def make_cfg_dir():
    from tests.conftest import DEMO_B

    return DEMO_B / "config"


def test_the_route_is_refused_for_a_kind_that_does_not_exist(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    assert (
        c.post(f"{api}/ai/account-check", json={"endpoint": "no-such-kind", "models": {"everyday": "m"}}).status_code
        == 400
    )


def test_the_result_is_json_the_screen_can_read(tmp_path, monkeypatch):
    monkeypatch.setitem(adapters.ADAPTERS, COMMON, a_working_service())
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    got = c.post(f"{api}/ai/account-check", json=check_body(HOSTED[0]))
    assert set(got.json()) == {"ok", "reason", "message", "identity", "identity_unknown"}
    json.dumps(got.json())
