"""A new AI account fills its tiers on its own (design 6.16, "A recommended setup per service"): the catalog's
preset for the service names a model family and an effort per tier, a service with no preset is split by price, the
person's own choice always wins, and a tier's effort reaches the adapter only where the account says how.

The planner is tested directly (it is pure); the route tests cover only what needs the route: the plan written
through the settings save, the response's lists and the takeover of the stand-in. They share one workspace."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from starlette.testclient import TestClient

from api.app import create_app
from engine import setup
from engine.ai.adapters import ADAPTERS
from engine.ai.adapters.cli_agent import CliAgentAdapter
from engine.ai.checked import is_checked
from engine.ai.presets import clean_presets, match_family, plan_tiers
from engine.ai.router import Router
from engine.ai.smoke import _params_for_tier, smoke_test
from engine.ai.task import AiTask, ModelInfo
from engine.config import load_config
from engine.config.schema import AgentSettings, ProviderSettings
from engine.setup import known_endpoints
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

COMMON = known_endpoints()[0]["adapter"]
HOSTED = "https" + "://models.example.com/v1"
TASK = AiTask("notes", "Do it.", "Reference.", "Input.", {})


def preset_kind(cli: bool = False):
    return next(e for e in known_endpoints() if e["tier_presets"] and (e["adapter"] == "cli-agent") == cli)


def ids_for(kind, *, leave_out=(), per_family=2):
    """Model ids built from the catalog's own family words, each family twice (older one listed first), plus a decoy
    that matches none, in an order that doesn't follow the tiers."""
    families = {t: p["family"] for t, p in kind["tier_presets"].items() if t not in leave_out}
    ids = ["decoy-model"]
    for tier in reversed(list(families)):
        ids += [f"x-{families[tier].upper()}-{n}" for n in range(per_family)]
    return ids


def tier(escalate_to=None):
    return SimpleNamespace(escalate_to=escalate_to)


def stock_tiers():
    """The tiers a new workspace has: routine escalating to deep, both still on the stand-in."""
    return {"routine": tier("deep"), "deep": tier()}, {"routine", "deep"}


def never_priced():
    raise AssertionError("prices asked for")


def short_names(ids):
    return {f"m{n}": i for n, i in enumerate(ids)}


def plan(entry, models, tiers=None, stand_in=None, prices=never_priced):
    stock, stock_stand_in = stock_tiers()
    return plan_tiers(
        entry, models, stock if tiers is None else tiers, stock_stand_in if stand_in is None else stand_in, prices
    )


# ---- the catalog ----------------------------------------------------------------------------------------------------


def test_presets_name_families_and_never_ids():
    for kind in known_endpoints():
        for tier_name, preset in kind["tier_presets"].items():
            assert preset["family"] and " " not in preset["family"] and "/" not in preset["family"], (
                kind["id"],
                tier_name,
            )
            assert preset["effort"] in ("", "low", "medium", "high")
    assert [k["id"] for k in known_endpoints() if k["tier_presets"]]


def test_the_catalog_sets_an_effort_setting_only_where_the_services_documentation_confirms_it():
    """Which entries those are is in tests/test_catalog_claims.py, with the documentation's wording in its fixture;
    here only that an entry without a confirmed parameter sends nothing."""
    claims = yaml.safe_load((Path(__file__).parent / "fixtures" / "ai" / "catalog-claims.yaml").read_text("utf-8"))
    for kind in known_endpoints():
        confirmed = kind["id"] in {*claims["effort_param"], *claims["effort_option"]}
        has = "effort_param" in kind["settings"] or "effort_option" in (kind["settings"].get("agent") or {})
        assert has is confirmed, kind["id"]


def test_a_family_matches_without_regard_to_case_and_the_first_listed_wins():
    assert match_family("Alpha", ["x", "the-ALPHA-2", "alpha-1"]) == "the-ALPHA-2"
    assert match_family("alpha", ["x", "y"]) is None
    assert clean_presets({"routine": {"family": "a", "effort": "bogus"}, "deep": {"effort": "low"}, "x": 3}) == {
        "routine": {"family": "a", "effort": ""}
    }


# ---- the planner, with a preset -------------------------------------------------------------------------------------


def test_every_tier_takes_the_first_listed_model_of_its_family_and_deep_escalates_to_the_hardest():
    kind = preset_kind()
    models = short_names(ids_for(kind))
    got = plan(kind, models)
    for tier_name, preset in kind["tier_presets"].items():
        first_listed = next(k for k, i in models.items() if preset["family"].lower() in i.lower())
        assert got.use[tier_name] == first_listed and models[first_listed].endswith("-0"), tier_name
    assert got.escalate_to == {"deep": "hardest"}  # routine already escalates to deep
    assert got.unmatched == [] and got.by_price == [] and got.new_models == {}


def test_a_command_line_agent_is_matched_against_its_examples_which_are_added_to_the_account():
    kind = preset_kind(cli=True)
    only = kind["model_examples"][0]
    got = plan(kind, {only: only})
    for tier_name, preset in kind["tier_presets"].items():
        example = next(e for e in kind["model_examples"] if preset["family"].lower() in e.lower())
        assert got.use[tier_name] == example, tier_name
        assert example == only or got.new_models[example] == example


def test_a_presets_effort_goes_with_its_tier():
    entry = {
        "tier_presets": {"routine": {"family": "small", "effort": "low"}, "deep": {"family": "large", "effort": "high"}}
    }
    got = plan(entry, {"a": "v1-large", "b": "v1-small"})
    assert got.use == {"routine": "b", "deep": "a"} and got.effort == {"routine": "low", "deep": "high"}


def test_a_family_no_model_matches_is_named_and_its_tier_is_left_out():
    kind = preset_kind()
    no_hardest = plan(kind, short_names(ids_for(kind, leave_out=("hardest",))))
    assert no_hardest.unmatched == ["hardest"] and "hardest" not in no_hardest.use and no_hardest.escalate_to == {}
    no_routine = plan(kind, short_names(ids_for(kind, leave_out=("routine",))))
    assert no_routine.unmatched == ["routine"] and "routine" not in no_routine.use and "deep" in no_routine.use


def test_a_tier_on_another_real_account_stays_and_does_not_make_its_neighbor_escalate():
    kind = preset_kind()
    tiers, _ = stock_tiers()
    got = plan(kind, short_names(ids_for(kind)), tiers, {"routine"})  # deep is on an account the person chose
    assert "deep" not in got.use and got.unmatched == [] and got.escalate_to == {}
    assert got.use.keys() == {"routine", "hardest"}


def test_a_preset_tier_already_in_the_settings_and_on_the_stand_in_is_filled_without_changing_escalation():
    kind = preset_kind()
    tiers = {"routine": tier("deep"), "deep": tier(), "hardest": tier()}
    got = plan(kind, short_names(ids_for(kind)), tiers, {"routine", "deep", "hardest"})
    assert got.use.keys() == {"routine", "deep", "hardest"} and got.escalate_to == {}


def test_a_deep_tier_that_already_escalates_elsewhere_keeps_it():
    kind = preset_kind()
    tiers = {"routine": tier("deep"), "deep": tier("somewhere")}
    got = plan(kind, short_names(ids_for(kind)), tiers, {"routine", "deep"})
    assert got.escalate_to == {}


def test_the_planner_never_asks_for_prices_when_the_entry_has_a_preset():
    assert plan({"tier_presets": {"routine": {"family": "a"}}}, {"m": "a-1"}).use == {"routine": "m"}


# ---- the planner, with no preset ------------------------------------------------------------------------------------


def prices_of(table):
    return lambda: {
        i: (ModelInfo(input_per_million=p[0], output_per_million=p[1]) if p else ModelInfo()) for i, p in table
    }


def test_with_no_preset_the_cheapest_priced_model_goes_to_routine_and_the_dearest_to_deep():
    table = [("mid", (1.0, 4.0)), ("cheap", (0.1, 0.4)), ("dear", (15.0, 75.0)), ("unpriced", None)]
    models = {"m-mid": "mid", "m-cheap": "cheap", "m-dear": "dear", "m-unpriced": "unpriced"}
    got = plan({}, models, prices=prices_of(table))
    assert got.use == {"routine": "m-cheap", "deep": "m-dear"} and got.by_price == ["routine", "deep"]
    assert got.unmatched == [] and got.effort == {} and got.escalate_to == {}


def test_with_no_preset_and_no_prices_nothing_is_planned_so_the_first_model_is_used_as_before():
    got = plan({}, {"first": "one", "second": "two"}, prices=prices_of([("one", None), ("two", None)]))
    assert got.use == {} and got.by_price == []
    assert plan({}, {"first": "one"}, prices=lambda: {}).use == {}


def test_with_no_preset_a_tier_on_another_real_account_is_not_filled_by_price():
    table = [("cheap", (0.1, 0.4)), ("dear", (15.0, 75.0))]
    got = plan({}, {"c": "cheap", "d": "dear"}, stand_in={"routine"}, prices=prices_of(table))
    assert got.use == {"routine": "c"} and got.by_price == ["routine"]


# ---- the route: the plan written through the settings save ---------------------------------------------------------


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    """One workspace and client for the route tests; each test puts the AI settings and kept keys back."""
    ws = init_workspace(tmp_path_factory.mktemp("presets") / "ws", template=DEMO_B, git=False)
    cfg = load_config(ws.config_dir, env={})
    Store(ws.db_path, cfg=cfg).close()
    # Built here, not by the shared helper: the per-test patch that points a client at the app's own address is not
    # active while a module-scoped fixture is made.
    c = TestClient(create_app(ws, cfg, "t", start_worker=False), base_url=f"http://127.0.0.1:{cfg.server.port}")
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    return ws, c, api, (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")


def put_back(ws, original):
    (ws.config_dir / "ai.yaml").write_text(original, encoding="utf-8")
    for kept in (ws.private_dir / "keys").glob("*"):
        kept.unlink()


@pytest.fixture
def route(shared):
    ws, c, api, original = shared
    put_back(ws, original)
    yield ws, c, api, original
    put_back(ws, original)


def with_catalog(tmp_path, monkeypatch, *entries):
    path = tmp_path / "ai-endpoints.yaml"
    base = {"name": "A service", "adapter": COMMON, "base_url": HOSTED, "needs_key": True}
    path.write_text(yaml.safe_dump({"endpoints": [{**base, **e} for e in entries]}), encoding="utf-8")
    monkeypatch.setattr(setup, "CATALOG", path)


def add(c, api, name, kind, models, **extra):
    got = c.get(f"{api}/settings")
    assert got.status_code == 200, got.text
    fingerprint = got.json()["fingerprint"]
    body = {
        "name": name,
        "adapter": kind["adapter"],
        "endpoint": kind["id"],
        "base_url": kind["base_url"] or HOSTED,
        "key": "not-a-real-key",
        "models": models,
        "fingerprint": fingerprint,
        **extra,
    }
    return c.post(f"{api}/ai/accounts", json=body)


def test_the_recommended_setup_is_written_with_its_effort_and_deep_escalates_to_the_hardest(
    route, tmp_path, monkeypatch
):
    with_catalog(
        tmp_path,
        monkeypatch,
        {
            "id": "svc",
            "tier_presets": {
                "routine": {"family": "small", "effort": "low"},
                "deep": {"family": "medium", "effort": "medium"},
                "hardest": {"family": "large", "effort": "high"},
            },
        },
    )
    ws, c, api, _ = route
    done = add(c, api, "svc-account", setup.endpoint("svc"), {"a": "v1-large", "b": "v1-small", "c": "v1-medium"})
    assert done.status_code == 200, done.text
    assert done.json()["unmatched_tiers"] == [] and done.json()["price_filled_tiers"] == []
    tiers = load_config(ws.config_dir, env={}).ai.tiers
    assert [(t, tiers[t].use, tiers[t].effort) for t in ("routine", "deep", "hardest")] == [
        ("routine", "svc-account/b", "low"),
        ("deep", "svc-account/c", "medium"),
        ("hardest", "svc-account/a", "high"),
    ]
    assert tiers["deep"].escalate_to == "hardest" and tiers["routine"].escalate_to == "deep"


def test_an_unmatched_family_is_named_the_stand_in_is_taken_over_and_the_persons_choice_wins(route):
    kind = preset_kind()
    ws, c, api, original = route
    models = short_names(ids_for(kind, leave_out=("routine", "hardest")))
    done = add(c, api, "short-account", kind, models)
    assert done.status_code == 200, done.text
    assert done.json()["unmatched_tiers"] == ["routine", "hardest"]
    tiers = load_config(ws.config_dir, env={}).ai.tiers
    assert tiers["routine"].use == "short-account/m0" and "hardest" not in tiers  # as it would be with no preset
    assert tiers["deep"].use.startswith("short-account/") and tiers["deep"].escalate_to is None
    put_back(ws, original)
    done = add(c, api, "chosen", kind, models, use={"routine": "m0"})
    assert done.status_code == 200 and done.json()["unmatched_tiers"] == []
    tiers = load_config(ws.config_dir, env={}).ai.tiers
    assert tiers["routine"].use == "chosen/m0" and tiers["deep"].use.startswith("stub/") and "hardest" not in tiers


def test_a_service_with_no_preset_is_split_by_price_and_not_checked(route, tmp_path, monkeypatch):
    with_catalog(tmp_path, monkeypatch, {"id": "svc"})
    table = [("mid", (1.0, 4.0)), ("cheap", (0.1, 0.4)), ("dear", (15.0, 75.0))]
    listed = [(i, ModelInfo(input_per_million=p[0], output_per_million=p[1])) for i, p in table]
    monkeypatch.setattr(setup, "list_models", lambda entry, base_url, key: (listed, None))
    ws, c, api, _ = route
    done = add(c, api, "svc-account", setup.endpoint("svc"), {"m-mid": "mid", "m-cheap": "cheap", "m-dear": "dear"})
    assert done.status_code == 200, done.text
    assert done.json()["price_filled_tiers"] == ["routine", "deep"] and done.json()["unmatched_tiers"] == []
    loaded = load_config(ws.config_dir, env={})
    assert loaded.ai.tiers["routine"].use == "svc-account/m-cheap"
    assert loaded.ai.tiers["deep"].use == "svc-account/m-dear"
    # Not checked: no test has passed for them, and the person hasn't accepted the account unchecked.
    assert loaded.ai.providers["svc-account"].accepted_unchecked is False
    for tier_name in ("routine", "deep"):
        assert not is_checked(ws, loaded, loaded.ai.tiers[tier_name].use, tier_name)


# ---- effort reaches the adapter only where the account says how ----------------------------------------------------


def request_body(settings, effort):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    adapter = ADAPTERS[COMMON](settings, "k", transport=httpx.MockTransport(handler))
    adapter.run(replace(TASK, effort=effort), "m")
    return seen[0]


@pytest.mark.parametrize(
    ("effort_param", "effort", "sent"),
    [("reasoning_effort", "high", True), ("", "high", False), ("reasoning_effort", None, False), ("", None, False)],
)
def test_the_chat_format_adapter_sends_the_effort_only_when_the_account_and_the_tier_both_say(
    effort_param, effort, sent
):
    settings = ProviderSettings(adapter=COMMON, base_url=HOSTED, effort_param=effort_param)
    body = request_body(settings, effort)
    if sent:
        assert body[effort_param] == effort
    else:
        assert not {"reasoning_effort", "effort"} & set(body)


@pytest.mark.parametrize(
    ("option", "effort", "added"),
    [(["--think", "{effort}"], "low", ["--think", "low"]), ([], "low", []), (["--think", "{effort}"], None, [])],
)
def test_the_command_line_agent_gets_its_effort_option_only_when_the_account_and_the_tier_both_say(
    option, effort, added
):
    ran = []

    def runner(args, **kwargs):
        ran.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout='{"ok": true}', stderr="")

    command = [sys.executable, "-c", "pass"]
    settings = ProviderSettings(
        adapter="cli-agent", agent=AgentSettings(command=command, effort_option=option), timeout_seconds=5
    )
    CliAgentAdapter(settings, runner=runner).run(replace(TASK, effort=effort), "m")
    assert ran[0] == [*command, *added]


def tiers_with_effort(cfg, effort):
    ai = cfg.ai.model_copy(
        update={"tiers": {n: t.model_copy(update={"effort": effort.get(n)}) for n, t in cfg.ai.tiers.items()}}
    )
    return replace(cfg, files={**cfg.files, "ai": ai})


def with_effort_param(cfg):
    providers = {n: p.model_copy(update={"effort_param": "reasoning_effort"}) for n, p in cfg.ai.providers.items()}
    return replace(cfg, files={**cfg.files, "ai": cfg.ai.model_copy(update={"providers": providers})})


@pytest.fixture
def ai_cfg():
    from tests.test_ai import AI_CONFIG

    return with_effort_param(tiers_with_effort(load_config(AI_CONFIG, env={}), {"routine": "high"}))


def test_the_smoke_test_sends_the_effort_a_real_call_of_that_tier_sends(ai_cfg):
    seen = []

    def factory(name, settings, secret):
        def handler(request):
            seen.append((request.url.host, json.loads(request.content)))
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

        return ADAPTERS[COMMON](settings, secret, transport=httpx.MockTransport(handler))

    results = smoke_test(ai_cfg, {"MAIN_KEY": "k", "BACKUP_KEY": "k"}, factory)
    calls = [r for r in results if r.part == "call"]
    routine = [r for r in calls if r.tier == "routine"]
    deep = [r for r in calls if r.tier == "deep"]
    assert routine and all(r.params[-1] == "high" and "effort high" in r.account for r in routine)
    assert deep and all(len(r.params) == 3 and "effort" not in r.account for r in deep)
    by_host = {}
    for host, body in seen:
        if "This is a connection test." in body["messages"][0]["content"]:
            by_host.setdefault(host, []).append(body.get("reasoning_effort"))
    main_host = httpx.URL(ai_cfg.ai.providers["main"].base_url).host
    deep_host = httpx.URL(ai_cfg.ai.providers["public-only"].base_url).host
    assert set(by_host[main_host]) == {"high"} and set(by_host[deep_host]) == {None}


def test_a_tiers_effort_is_part_of_the_parameters_a_check_must_have_passed(ai_cfg):
    assert all(p[-1] == "high" and len(p) == 4 for p in _params_for_tier(ai_cfg, "routine"))
    assert all(len(p) == 3 for p in _params_for_tier(ai_cfg, "deep"))


def test_the_router_passes_the_tiers_effort_on_with_the_call(ai_cfg, tmp_path):
    seen = []

    def factory(name, settings, secret):
        def handler(request):
            seen.append(json.loads(request.content).get("reasoning_effort"))
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        return ADAPTERS[COMMON](settings, secret, transport=httpx.MockTransport(handler))

    class NoCatalog:
        def model(self, provider, model_id, fetch):
            return None

    store = Store(tmp_path / "t.db")
    try:
        router = Router(
            ai_cfg,
            store,
            env={"MAIN_KEY": "k", "BACKUP_KEY": "k"},
            adapter_factory=factory,
            now=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
            catalogs=NoCatalog(),
        )
        router.call(TASK, request_id="REQ-1")
    finally:
        store.close()
    assert seen == ["high"]


@pytest.mark.parametrize("send", [True, False])
def test_the_chat_format_adapter_sends_a_temperature_only_when_the_account_says_to(send):
    """A service whose current models refuse any temperature they don't set themselves is set not to be sent one."""
    body = request_body(ProviderSettings(adapter=COMMON, base_url=HOSTED, send_temperature=send), None)
    assert ("temperature" in body) is send


def test_the_recommended_service_is_sent_no_temperature():
    """The catalog's recommended service starts with temperature off, so its first connection check isn't refused."""
    entries = yaml.safe_load(setup.CATALOG.read_text(encoding="utf-8"))["endpoints"]
    entry = next(e for e in entries if e.get("recommended"))
    assert entry["settings"]["send_temperature"] is False
